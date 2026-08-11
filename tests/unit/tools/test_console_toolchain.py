"""The pinned console toolchain: what it reads, what it refuses, and idempotence.

The download itself is not exercised here — a unit test that fetches a hundred
megabytes from a public host is a unit test that fails on an aeroplane. What is
exercised is everything around it: the pin is read from committed files, the
archive name and address are derived from the pin rather than guessed, a digest
that does not match is refused before anything is unpacked, and a second
provisioning of an already-provisioned toolchain fetches nothing.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import tarfile
from pathlib import Path

import pytest

from config.constants.console import (
    CONSOLE_BROWSER_NAME,
    CONSOLE_LOCKFILE_FILENAME,
    CONSOLE_MANIFEST_FILENAME,
    CONSOLE_NODE_VERSION_FILENAME,
    CONSOLE_PLATFORM_KEYS,
    CONSOLE_TOOLCHAIN_LOCK_FILENAME,
    NODE_DIST_BASE_URL,
    PLAYWRIGHT_BROWSERS_PATH_ENV,
)
from tools.console_toolchain import (
    DigestMismatch,
    Pin,
    Toolchain,
    ToolchainError,
    archive_name,
    archive_url,
    browsers_dir,
    console_root,
    ensure_browsers,
    ensure_node,
    environment,
    platform_key,
    read_pin,
)

pytestmark = pytest.mark.unit


def test_the_pin_is_read_from_the_committed_files() -> None:
    """The Node version, the package manager and the digests come from the tree."""
    pin = read_pin()

    assert pin.node_version.count(".") == 2, pin.node_version
    assert pin.pnpm_version.count(".") == 2, pin.pnpm_version
    assert set(pin.digests) == set(CONSOLE_PLATFORM_KEYS)
    assert all(len(digest) == 64 for digest in pin.digests.values())


def test_the_node_version_file_and_the_lock_agree() -> None:
    """One version, in the file a version manager reads and in the digest lock."""
    root = console_root()
    declared = (root / CONSOLE_NODE_VERSION_FILENAME).read_text(encoding="utf-8").strip()
    locked = json.loads((root / CONSOLE_TOOLCHAIN_LOCK_FILENAME).read_text(encoding="utf-8"))

    assert declared == locked["node"]["version"]
    assert read_pin().node_version == declared


def test_the_manifest_pins_the_package_manager_the_lock_names() -> None:
    """``packageManager`` is what a pnpm-aware runner reads; the lock is what we read."""
    root = console_root()
    manifest = json.loads((root / CONSOLE_MANIFEST_FILENAME).read_text(encoding="utf-8"))

    assert manifest["packageManager"] == f"pnpm@{read_pin().pnpm_version}"


def test_the_lockfile_is_committed() -> None:
    """A manifest without its lockfile is a build that resolves differently twice."""
    assert (console_root() / CONSOLE_LOCKFILE_FILENAME).is_file()


@pytest.mark.parametrize("key", CONSOLE_PLATFORM_KEYS)
def test_every_platform_has_an_archive_name_and_an_address(key: str) -> None:
    """The three operating systems the workflow covers, on both architectures."""
    pin = read_pin()
    name = archive_name(pin, key)

    assert name.startswith(f"node-v{pin.node_version}-{key}")
    assert name.endswith(".zip" if key.startswith("win-") else ".tar.xz")
    assert archive_url(pin, key) == f"{NODE_DIST_BASE_URL}/v{pin.node_version}/{name}"


def test_a_mirror_replaces_the_address_and_nothing_else() -> None:
    """An air-gapped build fetches from elsewhere; the digest it must match is the same."""
    pin = read_pin()
    url = archive_url(pin, "linux-x64", mirror="https://mirror.internal/node")

    assert (
        url == f"https://mirror.internal/node/v{pin.node_version}/{archive_name(pin, 'linux-x64')}"
    )


def test_this_machine_maps_to_a_platform_the_lock_covers() -> None:
    """A platform with no digest is a platform we would install unverified on."""
    assert platform_key() in CONSOLE_PLATFORM_KEYS


def test_an_unknown_platform_is_refused_rather_than_guessed() -> None:
    """Guessing an archive name would download something and hope."""
    with pytest.raises(ToolchainError, match="plan9-sparc"):
        archive_name(read_pin(), "plan9-sparc")


@pytest.mark.parametrize(
    ("described", "expected"),
    [
        ("linux-x86_64", "linux-x64"),
        ("linux-aarch64", "linux-arm64"),
        ("macosx-14.0-arm64", "darwin-arm64"),
        ("macosx-10.9-x86_64", "darwin-x64"),
        ("win-amd64", "win-x64"),
        ("win-arm64", "win-arm64"),
    ],
)
def test_each_platform_python_describes_maps_to_the_archive_node_publishes(
    described: str, expected: str
) -> None:
    """The three operating systems the workflow covers, both architectures each."""
    assert platform_key(described) == expected


@pytest.mark.parametrize("described", ["sunos-sparc", "win32", "linux-mips"])
def test_a_platform_the_lock_does_not_cover_is_refused(described: str) -> None:
    """Better a refusal than a download of something nothing has a digest for."""
    with pytest.raises(ToolchainError, match="pinned for"):
        platform_key(described)


def _tarball(directory: Path, name: str) -> Path:
    """Return a tarball of ``directory`` holding a plausible Node layout."""
    root = directory / f"{name}-payload" / f"{name}"
    (root / "bin").mkdir(parents=True)
    (root / "bin" / "node").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    archive = directory / f"{name}.tar.xz"
    with tarfile.open(archive, "w:xz") as handle:
        handle.add(root, arcname=name)
    return archive


def test_a_downloaded_archive_whose_digest_does_not_match_is_refused(tmp_path: Path) -> None:
    """The verification happens before anything is unpacked, not after."""
    pin = read_pin()
    key = platform_key()
    archive = _tarball(tmp_path, f"node-v{pin.node_version}-{key}")
    into = tmp_path / "toolchain"

    def fetch(url: str, destination: Path) -> None:
        destination.write_bytes(archive.read_bytes())

    wrong = Pin(
        node_version=pin.node_version,
        pnpm_version=pin.pnpm_version,
        digests={key: "0" * 64},
    )

    with pytest.raises(DigestMismatch) as raised:
        ensure_node(wrong, into, fetch=fetch)

    assert "0" * 64 in str(raised.value)
    assert not list(into.glob(f"node-v{pin.node_version}-*/bin"))


def test_a_provisioned_toolchain_is_not_fetched_again(tmp_path: Path) -> None:
    """``make console-setup`` is run on every gate; the second run must be free."""
    pin = read_pin()
    key = platform_key()
    if key.startswith("win-"):
        pytest.skip("the fixture archive is a tarball; Windows takes the zip path")

    archive = _tarball(tmp_path, f"node-v{pin.node_version}-{key}")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    into = tmp_path / "toolchain"
    calls: list[str] = []

    def fetch(url: str, destination: Path) -> None:
        calls.append(url)
        destination.write_bytes(archive.read_bytes())

    honest = Pin(
        node_version=pin.node_version,
        pnpm_version=pin.pnpm_version,
        digests={key: digest},
    )

    first = ensure_node(honest, into, fetch=fetch)
    second = ensure_node(honest, into, fetch=fetch)

    assert first == second
    assert first.is_file()
    assert len(calls) == 1, f"provisioning fetched again: {calls}"


# --- The browser ------------------------------------------------------------------
#
# The download is not exercised here either, for the reason at the top of this
# file. What is exercised is the thing that was actually broken: the directory
# Playwright is pointed at is inside the checkout, so *something* has to fill it,
# and nothing did. A worktree that had never had a browser installed by hand ran
# the whole browser suite against an executable that was not there and reported
# it as sixty-two failing tests.


def _fake_toolchain(tmp_path: Path) -> Toolchain:
    """Return a Toolchain of paths that exist and are never executed."""
    binaries = tmp_path / "bin"
    binaries.mkdir(parents=True, exist_ok=True)
    for name in ("node", "npm", "pnpm"):
        (binaries / name).write_text("", encoding="utf-8")
    return Toolchain(node=binaries / "node", npm=binaries / "npm", pnpm=binaries / "pnpm")


def test_a_console_command_looks_for_its_browser_inside_the_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Not the home-directory cache: two checkouts may want two builds."""
    monkeypatch.delenv(PLAYWRIGHT_BROWSERS_PATH_ENV, raising=False)

    where = environment(_fake_toolchain(tmp_path))[PLAYWRIGHT_BROWSERS_PATH_ENV]

    assert Path(where) == browsers_dir()
    assert console_root() in browsers_dir().parents


def test_a_browser_directory_an_operator_chose_is_left_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An air-gapped machine with a populated cache still gets to point at it."""
    theirs = str(tmp_path / "their-cache")
    monkeypatch.setenv(PLAYWRIGHT_BROWSERS_PATH_ENV, theirs)

    assert environment(_fake_toolchain(tmp_path))[PLAYWRIGHT_BROWSERS_PATH_ENV] == theirs


def test_the_browser_is_installed_where_the_suite_will_look_for_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One directory, or the install and the launch disagree in silence."""
    monkeypatch.delenv(PLAYWRIGHT_BROWSERS_PATH_ENV, raising=False)
    seen: dict[str, object] = {}

    def record(command: list[str], **keywords: object) -> subprocess.CompletedProcess[str]:
        seen["command"] = command
        seen["env"] = keywords["env"]
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", record)
    toolchain = _fake_toolchain(tmp_path)

    into = ensure_browsers(toolchain)

    command = seen["command"]
    environment_used = seen["env"]
    assert isinstance(command, list)
    assert isinstance(environment_used, dict)
    assert command[2:] == ["exec", "playwright", "install", CONSOLE_BROWSER_NAME]
    # The directory the installer wrote to, the directory it reported, and the
    # directory a suite will be launched with are one directory.
    assert environment_used[PLAYWRIGHT_BROWSERS_PATH_ENV] == str(into)
    assert Path(environment(toolchain)[PLAYWRIGHT_BROWSERS_PATH_ENV]) == into


def test_a_browser_that_cannot_be_provisioned_is_not_reported_as_a_failing_suite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing browser is a thing to install; a red suite is a thing to fix."""

    def refuse(command: list[str], **keywords: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, "", "no route to the download host")

    monkeypatch.setattr(subprocess, "run", refuse)

    with pytest.raises(ToolchainError) as raised:
        ensure_browsers(_fake_toolchain(tmp_path))

    assert CONSOLE_BROWSER_NAME in str(raised.value)
    assert "no route to the download host" in str(raised.value)
