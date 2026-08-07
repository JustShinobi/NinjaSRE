"""Provision the console's toolchain on a machine that has no Node at all.

Acceptance scenario 5 of the console toolchain feature is a contributor with
nothing installed running ``make verify`` and getting the same Node, the same
package manager and the same browser as CI. That rules out "install Node first"
as an instruction and rules out a version manager as a dependency, so this
script is written in the language the repository already requires.

What it does, in order, and each step is a no-op when it has already happened:

1. Find a Node matching the pinned version — on ``PATH`` if the machine happens
   to have exactly that one, otherwise under ``console/.toolchain/``.
2. Failing both, download the official archive for this platform, check it
   against the digest committed in ``console/toolchain.lock.json``, and unpack
   it. A digest that does not match aborts before anything is unpacked: an
   archive we cannot identify is not one we install and then think about.
3. Install the pinned pnpm with that Node's own npm, into the same directory.
4. Install the console's dependencies from the committed lockfile, frozen — so
   a lockfile that has drifted from the manifest fails the build rather than
   being quietly rewritten into agreement with it.

Usage::

    python -m tools.console_toolchain setup
    python -m tools.console_toolchain run lint
    python -m tools.console_toolchain which

Exits 0 when the toolchain is ready, 1 when it is not, and says which step
failed rather than reporting that something did.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import sysconfig
import tarfile
import tempfile
import urllib.request
import zipfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from config.constants.console import (
    CONSOLE_DIR_NAME,
    CONSOLE_LOCKFILE_FILENAME,
    CONSOLE_MANIFEST_FILENAME,
    CONSOLE_NODE_VERSION_FILENAME,
    CONSOLE_PLATFORM_KEYS,
    CONSOLE_TOOLCHAIN_DIR_NAME,
    CONSOLE_TOOLCHAIN_LOCK_FILENAME,
    NINJASRE_NODE_MIRROR_ENV,
    NODE_DIST_BASE_URL,
)

REPO_ROOT: Final = Path(__file__).resolve().parents[1]

#: How much of a download is held in memory at once while it is hashed.
_CHUNK_BYTES: Final = 1024 * 1024

#: What Python calls an architecture, against what a Node archive calls it.
_ARCHITECTURES: Final[Mapping[str, str]] = {
    "x86_64": "x64",
    "amd64": "x64",
    "arm64": "arm64",
    "aarch64": "arm64",
}

#: Likewise for the operating system. Node spells Windows ``win``, and every
#: BSD-alike that is not macOS is a platform this repository does not claim.
_SYSTEMS: Final[Mapping[str, str]] = {
    "linux": "linux",
    "macosx": "darwin",
    "win": "win",
}


class ToolchainError(RuntimeError):
    """The toolchain could not be provisioned, and the message says why."""


class DigestMismatch(ToolchainError):
    """A downloaded archive is not the one the lock committed to."""


class StaleLockfile(ToolchainError):
    """The committed lockfile does not describe the committed manifest.

    Never treated as "the toolchain is unavailable", however it was discovered.
    A machine with no network cannot install; a lockfile that has drifted from
    its manifest is a change somebody has to make, and quietly resolving it into
    agreement is how a build stops being reproducible.
    """


@dataclass(frozen=True, slots=True)
class Pin:
    """The versions the repository has committed to, and how to recognise them."""

    node_version: str
    pnpm_version: str
    #: Platform key → the SHA-256 of that platform's official Node archive.
    digests: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class Toolchain:
    """Where the provisioned executables ended up."""

    node: Path
    npm: Path
    pnpm: Path

    @property
    def bin_dir(self) -> Path:
        """Return the directory to put at the head of ``PATH`` for a console command."""
        return self.node.parent


def console_root(root: Path | None = None) -> Path:
    """Return the console's directory."""
    return (root or REPO_ROOT) / CONSOLE_DIR_NAME


def toolchain_dir(root: Path | None = None) -> Path:
    """Return where a provisioned Node and pnpm are unpacked."""
    return console_root(root) / CONSOLE_TOOLCHAIN_DIR_NAME


def read_pin(root: Path | None = None) -> Pin:
    """Return the pinned versions and archive digests.

    Raises:
        ToolchainError: a pin file is missing, malformed, or disagrees with its
            counterpart about which Node version this is.
    """
    directory = console_root(root)
    version_file = directory / CONSOLE_NODE_VERSION_FILENAME
    lock_file = directory / CONSOLE_TOOLCHAIN_LOCK_FILENAME

    for path in (version_file, lock_file):
        if not path.is_file():
            raise ToolchainError(f"{path} is missing; the console toolchain is not pinned")

    declared = version_file.read_text(encoding="utf-8").strip().lstrip("v")
    lock = json.loads(lock_file.read_text(encoding="utf-8"))

    node = lock.get("node", {})
    locked = str(node.get("version", ""))
    if locked != declared:
        raise ToolchainError(
            f"{CONSOLE_NODE_VERSION_FILENAME} pins Node {declared} but "
            f"{CONSOLE_TOOLCHAIN_LOCK_FILENAME} carries digests for {locked}"
        )

    digests = {str(key): str(value) for key, value in node.get("digests", {}).items()}
    missing = sorted(set(CONSOLE_PLATFORM_KEYS) - set(digests))
    if missing:
        raise ToolchainError(
            f"{CONSOLE_TOOLCHAIN_LOCK_FILENAME} has no digest for {', '.join(missing)}; "
            f"a platform with no digest is a platform we would install unverified on"
        )

    pnpm = str(lock.get("pnpm", {}).get("version", ""))
    if not pnpm:
        raise ToolchainError(f"{CONSOLE_TOOLCHAIN_LOCK_FILENAME} does not pin a pnpm version")

    return Pin(node_version=declared, pnpm_version=pnpm, digests=digests)


def platform_key(target: str | None = None) -> str:
    """Return the digest-table key for ``target``, defaulting to this machine.

    ``target`` is a ``sysconfig`` platform string — ``linux-x86_64``,
    ``macosx-14.0-arm64``, ``win-amd64``. That is the source rather than the
    ``platform`` module because this repository has a first-party package of
    that name: ``import platform`` here resolves to the tier, not the standard
    library, and no amount of aliasing changes which module it is.

    Raises:
        ToolchainError: the platform is one the lock does not cover.
    """
    described = (target if target is not None else sysconfig.get_platform()).lower()
    parts = described.split("-")

    named_system = _SYSTEMS.get(parts[0])
    named_machine = _ARCHITECTURES.get(parts[-1]) if len(parts) > 1 else None
    if named_system is None or named_machine is None:
        raise ToolchainError(
            f"{described} is not a platform the console toolchain is pinned for; "
            f"it covers {', '.join(CONSOLE_PLATFORM_KEYS)}"
        )
    return f"{named_system}-{named_machine}"


def archive_name(pin: Pin, key: str) -> str:
    """Return the official archive's filename for ``key``.

    Raises:
        ToolchainError: ``key`` is not a platform the lock covers.
    """
    if key not in CONSOLE_PLATFORM_KEYS:
        raise ToolchainError(
            f"{key} is not a platform the console toolchain is pinned for; "
            f"it covers {', '.join(CONSOLE_PLATFORM_KEYS)}"
        )
    suffix = ".zip" if key.startswith("win-") else ".tar.xz"
    return f"node-v{pin.node_version}-{key}{suffix}"


def archive_url(pin: Pin, key: str, mirror: str | None = None) -> str:
    """Return where ``key``'s archive is fetched from.

    A mirror changes the address and nothing else — the digest the archive has
    to match is the same one, which is what makes an air-gapped build a
    different route rather than a lower standard.
    """
    base = (mirror or NODE_DIST_BASE_URL).rstrip("/")
    return f"{base}/v{pin.node_version}/{archive_name(pin, key)}"


def _download(url: str, destination: Path) -> None:
    """Fetch ``url`` into ``destination``."""
    try:
        with urllib.request.urlopen(url) as response, destination.open("wb") as handle:
            shutil.copyfileobj(response, handle)
    except OSError as error:  # URLError is an OSError, and so is a full disk.
        raise ToolchainError(
            f"could not fetch {url}: {error}. Set {NINJASRE_NODE_MIRROR_ENV} to a mirror, "
            f"or install Node {url.rsplit('/v', 1)[-1].split('/')[0]} yourself."
        ) from error


def _digest_of(path: Path) -> str:
    """Return the SHA-256 of ``path``, read in chunks rather than all at once."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _unpack(archive: Path, into: Path) -> None:
    """Unpack ``archive`` into ``into``, keeping its single top-level directory."""
    if archive.name.endswith(".zip"):
        with zipfile.ZipFile(archive) as zipped:
            zipped.extractall(into)
        return
    with tarfile.open(archive) as tarred:
        # ``data`` refuses absolute paths, parent traversal, and device nodes.
        # The archive is digest-verified by the time we get here; this is the
        # second lock on a door that is already bolted.
        tarred.extractall(into, filter="data")


def _node_executable(directory: Path) -> Path:
    """Return the ``node`` inside an unpacked distribution, whatever it is called."""
    for candidate in (directory / "bin" / "node", directory / "node.exe"):
        if candidate.is_file():
            return candidate
    raise ToolchainError(f"{directory} does not contain a node executable")


def node_on_path(pin: Pin) -> Path | None:
    """Return a ``node`` already on ``PATH`` at exactly the pinned version.

    Exactly, not "at least": the point of the pin is that everybody runs the
    same one, and a machine one patch ahead is a machine whose failures nobody
    else can reproduce. An operator who installed the pinned version themselves
    — the air-gapped case — gets to keep it.
    """
    found = shutil.which("node")
    if found is None:
        return None
    try:
        finished = subprocess.run([found, "--version"], capture_output=True, text=True, check=False)
    except OSError:
        return None
    if finished.returncode != 0:
        return None
    if finished.stdout.strip().lstrip("v") != pin.node_version:
        return None
    return Path(found).resolve()


def ensure_node(
    pin: Pin,
    into: Path,
    *,
    key: str | None = None,
    mirror: str | None = None,
    fetch: Callable[[str, Path], None] = _download,
    allow_path: bool = False,
) -> Path:
    """Return the pinned Node, downloading and verifying it if it is not there yet.

    Idempotent: an already-unpacked distribution is returned without fetching
    anything, which is what makes this safe to depend on from every gate target.

    Raises:
        DigestMismatch: the archive is not the one the lock committed to.
        ToolchainError: the download failed or the archive is not a Node.
    """
    resolved = key or platform_key()
    unpacked = into / f"node-v{pin.node_version}-{resolved}"
    if unpacked.is_dir():
        return _node_executable(unpacked)
    if allow_path:
        already = node_on_path(pin)
        if already is not None:
            return already

    expected = pin.digests.get(resolved)
    if expected is None:
        raise ToolchainError(f"{CONSOLE_TOOLCHAIN_LOCK_FILENAME} has no digest for {resolved}")

    into.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=into) as staging:
        staged = Path(staging)
        archive = staged / archive_name(pin, resolved)
        fetch(archive_url(pin, resolved, mirror), archive)

        found = _digest_of(archive)
        if found != expected:
            raise DigestMismatch(
                f"{archive.name} hashes to {found} but the lock expects {expected}. "
                f"Nothing was unpacked."
            )

        _unpack(archive, staged)
        extracted = staged / f"node-v{pin.node_version}-{resolved}"
        if not extracted.is_dir():
            raise ToolchainError(f"{archive.name} does not contain {extracted.name}")
        # Rename last, so a killed run leaves no half-unpacked distribution that
        # the next run would mistake for a provisioned one.
        extracted.rename(unpacked)

    return _node_executable(unpacked)


def _npm_for(node: Path) -> Path:
    """Return the npm shipped with ``node``."""
    for candidate in (
        node.parent / "npm",
        node.parent / "npm.cmd",
        node.parent / "bin" / "npm",
    ):
        if candidate.is_file():
            return candidate
    raise ToolchainError(f"the distribution at {node.parent} ships no npm")


def _installed_version(executable: Path, node: Path) -> str:
    """Return what ``executable`` reports for ``--version``, or an empty string."""
    try:
        finished = subprocess.run(
            [str(node), str(executable), "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return ""
    return finished.stdout.strip() if finished.returncode == 0 else ""


def ensure_pnpm(pin: Pin, node: Path, into: Path) -> Path:
    """Return the pinned pnpm, installing it with ``node``'s own npm if need be.

    Installed into the toolchain directory rather than globally: a contributor's
    machine may well have another pnpm for another repository, and this one has
    to be the version the lockfile was written by whatever that is.
    """
    prefix = into / "pnpm"
    entry = prefix / "node_modules" / "pnpm" / "bin" / "pnpm.cjs"
    if entry.is_file() and _installed_version(entry, node).lstrip("v") == pin.pnpm_version:
        return entry

    prefix.mkdir(parents=True, exist_ok=True)
    finished = subprocess.run(
        [
            str(node),
            str(_npm_for(node)),
            "install",
            "--prefix",
            str(prefix),
            "--no-audit",
            "--no-fund",
            f"pnpm@{pin.pnpm_version}",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if finished.returncode != 0 or not entry.is_file():
        raise ToolchainError(
            f"installing pnpm@{pin.pnpm_version} failed:\n{finished.stdout}\n{finished.stderr}"
        )
    return entry


def environment(toolchain: Toolchain) -> dict[str, str]:
    """Return the environment a console command runs in.

    The pinned Node leads ``PATH`` so a package's own shebang finds it, and
    ``COREPACK_ENABLE_STRICT`` is off because the package manager is already
    pinned by the lock this script read — corepack would only be a second
    opinion about the same question.
    """
    env = dict(os.environ)
    env["PATH"] = os.pathsep.join([str(toolchain.bin_dir), env.get("PATH", "")])
    env["COREPACK_ENABLE_STRICT"] = "0"
    return env


def run_pnpm(
    arguments: Sequence[str],
    toolchain: Toolchain,
    *,
    root: Path | None = None,
    check: bool = True,
) -> int:
    """Run pnpm in the console directory and return its exit status.

    Raises:
        ToolchainError: ``check`` is set and pnpm reported a failure.
    """
    finished = subprocess.run(
        [str(toolchain.node), str(toolchain.pnpm), *arguments],
        cwd=console_root(root),
        env=environment(toolchain),
        check=False,
    )
    if check and finished.returncode != 0:
        raise ToolchainError(f"pnpm {' '.join(arguments)} failed with {finished.returncode}")
    return finished.returncode


def resolve(root: Path | None = None, *, mirror: str | None = None) -> Toolchain:
    """Return the provisioned toolchain, provisioning Node and pnpm if needed.

    Does not install the console's dependencies — ``provision`` does that, and
    keeping the two apart is what lets ``make console-setup`` be the only target
    that writes to ``node_modules``.
    """
    pin = read_pin(root)
    into = toolchain_dir(root)
    node = ensure_node(
        pin,
        into,
        mirror=mirror or os.environ.get(NINJASRE_NODE_MIRROR_ENV),
        allow_path=True,
    )
    return Toolchain(node=node, npm=_npm_for(node), pnpm=ensure_pnpm(pin, node, into))


#: What pnpm calls a lockfile that no longer describes its manifest. Matched on
#: rather than inferred from the exit status, because "could not install" and
#: "the lockfile has drifted" are the same exit status and must not be the same
#: outcome: the first may be skipped on a machine with no registry, the second
#: never may.
_OUTDATED_LOCKFILE: Final = "ERR_PNPM_OUTDATED_LOCKFILE"


def install_dependencies(toolchain: Toolchain, root: Path | None = None) -> None:
    """Install the console's dependencies from the committed lockfile, frozen.

    ``--frozen-lockfile`` is the whole of the stale-lockfile rule: a manifest
    the lockfile does not describe fails here, naming the difference, rather
    than being resolved into a build nobody can reproduce.

    Raises:
        StaleLockfile: the lockfile and the manifest disagree.
        ToolchainError: the install failed for any other reason.
    """
    finished = subprocess.run(
        [str(toolchain.node), str(toolchain.pnpm), "install", "--frozen-lockfile"],
        cwd=console_root(root),
        env=environment(toolchain),
        capture_output=True,
        text=True,
        check=False,
    )
    if finished.returncode == 0:
        return
    output = f"{finished.stdout}\n{finished.stderr}"
    if _OUTDATED_LOCKFILE in output:
        raise StaleLockfile(
            f"{CONSOLE_LOCKFILE_FILENAME} is out of date with {CONSOLE_MANIFEST_FILENAME}. "
            f"Run `make console-install` and commit the result.\n{output.strip()}"
        )
    raise ToolchainError(f"installing the console's dependencies failed:\n{output.strip()}")


def provision(root: Path | None = None, *, mirror: str | None = None) -> Toolchain:
    """Provision the toolchain and install the console's dependencies, frozen."""
    toolchain = resolve(root, mirror=mirror)
    directory = console_root(root)
    for required in (CONSOLE_MANIFEST_FILENAME, CONSOLE_LOCKFILE_FILENAME):
        if not (directory / required).is_file():
            raise ToolchainError(f"{directory / required} is missing")
    install_dependencies(toolchain, root)
    return toolchain


def is_provisioned(root: Path | None = None) -> bool:
    """Return whether the toolchain and the console's dependencies are both there."""
    try:
        pin = read_pin(root)
    except ToolchainError:
        return False
    unpacked = toolchain_dir(root) / f"node-v{pin.node_version}-{platform_key()}"
    has_node = unpacked.is_dir() or node_on_path(pin) is not None
    return has_node and (console_root(root) / "node_modules").is_dir()


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="console_toolchain", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("setup", help="provision the toolchain and install dependencies")
    commands.add_parser("which", help="print where the provisioned executables are")
    run = commands.add_parser("run", help="run a pnpm script in the console directory")
    run.add_argument("script", nargs=argparse.REMAINDER)

    arguments = parser.parse_args(argv)

    try:
        if arguments.command == "setup":
            toolchain = provision()
            print(f"node {toolchain.node}\npnpm {toolchain.pnpm}")
            return 0
        if arguments.command == "which":
            toolchain = resolve()
            print(f"node {toolchain.node}\nnpm {toolchain.npm}\npnpm {toolchain.pnpm}")
            return 0
        toolchain = resolve()
        return run_pnpm(arguments.script, toolchain, check=False)
    except ToolchainError as error:
        print(f"console toolchain: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(_main())
