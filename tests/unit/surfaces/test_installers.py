"""What the installers must and must not do.

Installers cannot be unit-tested by running them — they download a release that
does not exist yet from a host nobody has stood up. What *can* be asserted is
the set of properties that make them acceptable to the operator this platform
is for, and each of these is a property somebody would otherwise relax under
deadline:

- **No elevation.** No `sudo`, no `runas`, no Administrator requirement.
- **A user-local fallback with an exact PATH instruction.** Asserted by running
  the installer's own directory-selection logic against a PATH with nothing
  writable on it.
- **Integrity verification before unpacking.** The checksum is compared, and a
  mismatch stops the install.
- **No telemetry.** Nothing is transmitted except the download itself.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

INSTALL_DIR = Path(__file__).resolve().parents[3] / "install"
SHELL_INSTALLER = INSTALL_DIR / "install.sh"
POWERSHELL_INSTALLER = INSTALL_DIR / "install.ps1"
HOMEBREW_FORMULA = INSTALL_DIR / "homebrew" / "ninjasre.rb"

#: Anything that would require elevation. A tool that needs root to install
#: itself is a tool a regulated operator cannot install at all.
ELEVATION_WORDS = ("sudo", "doas", "runas", "RequireAdministrator", "-Verb RunAs")

#: Anything that reports off-host. The download itself is the only network call
#: either installer is allowed to make.
TELEMETRY_WORDS = (
    "analytics",
    "telemetry",
    "segment.io",
    "mixpanel",
    "amplitude",
    "sentry",
    "posthog",
    "install-count",
)


def test_both_installers_exist() -> None:
    assert SHELL_INSTALLER.is_file()
    assert POWERSHELL_INSTALLER.is_file()


def test_the_shell_installer_is_executable() -> None:
    mode = SHELL_INSTALLER.stat().st_mode

    assert mode & stat.S_IXUSR, "install.sh is not executable"


def test_the_shell_installer_is_valid_posix_sh() -> None:
    # POSIX sh rather than bash: the shell on a minimal container image is the
    # one somebody will run this with.
    result = subprocess.run(
        ["sh", "-n", str(SHELL_INSTALLER)], capture_output=True, text=True, check=False
    )

    assert result.returncode == 0, result.stderr


def executable_lines(source: Path) -> list[str]:
    """Return the lines of ``source`` that do something.

    Comments and here-document prose are excluded. All three files explain to
    the reader that they use no elevation and send no telemetry, and a scanner
    that could not tell a promise from a violation would flag the promise.
    """
    lines: list[str] = []
    in_block_comment = False
    in_heredoc = False
    for raw in source.read_text(encoding="utf-8").splitlines():
        line = raw.strip()

        if line.startswith("<#"):
            in_block_comment = True
        if in_block_comment:
            if line.endswith("#>"):
                in_block_comment = False
            continue

        # Ruby's ``<<~EOS`` and the shell's ``<<EOF`` both carry text shown to
        # the operator rather than code that runs.
        if not in_heredoc and ("<<~EOS" in line or "<<-EOF" in line or line.endswith("<<EOF")):
            in_heredoc = True
            continue
        if in_heredoc:
            if line in {"EOS", "EOF"}:
                in_heredoc = False
            continue

        if not line or line.startswith(("#", "//")):
            continue
        lines.append(line)
    return lines


@pytest.mark.parametrize("installer", [SHELL_INSTALLER, POWERSHELL_INSTALLER])
def test_no_installer_requires_elevation(installer: Path) -> None:
    offending = [
        line
        for line in executable_lines(installer)
        for word in ELEVATION_WORDS
        if word in line and "never" not in line
    ]

    assert not offending, f"{installer.name} would need elevation: {offending}"


@pytest.mark.parametrize("installer", [SHELL_INSTALLER, POWERSHELL_INSTALLER])
def test_no_installer_transmits_anything(installer: Path) -> None:
    body = "\n".join(executable_lines(installer)).lower()
    offending = [word for word in TELEMETRY_WORDS if word in body]

    assert not offending, f"{installer.name} mentions {offending}"


@pytest.mark.parametrize("installer", [SHELL_INSTALLER, POWERSHELL_INSTALLER])
def test_every_installer_verifies_the_archive_before_unpacking(installer: Path) -> None:
    body = installer.read_text(encoding="utf-8")

    assert "SHA256SUMS" in body, f"{installer.name} downloads no checksums"
    assert "checksum mismatch" in body, f"{installer.name} does not compare them"
    assert "Refusing to install" in body, f"{installer.name} does not stop on a mismatch"


def test_the_shell_installer_refuses_an_unverified_download() -> None:
    body = SHELL_INSTALLER.read_text(encoding="utf-8")

    # The order matters: verify, then unpack. A script that unpacked first
    # would have written the archive's contents before deciding not to.
    verify_at = body.index('verify "${work}/${archive_name}"')
    unpack_at = body.index("tar -xzf")

    assert verify_at < unpack_at, "the archive is unpacked before it is verified"


def _writable_path_dir(path_value: str, home: Path) -> str:
    """Return what the installer's own directory selection picks for ``path_value``.

    The real function, lifted out of the script and run — rather than a Python
    reimplementation of it, which would be asserting that two things agree
    without either of them being the one that ships.
    """
    script = "\n".join(
        [
            "set -eu",
            f'PATH="{path_value}"',
            f'HOME="{home}"',
            _extract_function("writable_path_dir"),
            "writable_path_dir",
        ]
    )
    result = subprocess.run(["/bin/sh", "-c", script], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _extract_function(name: str) -> str:
    """Return one shell function's source, lifted out of the installer."""
    body = SHELL_INSTALLER.read_text(encoding="utf-8")
    start = body.index(f"{name}() {{")
    depth = 0
    for index in range(start, len(body)):
        if body[index] == "{":
            depth += 1
        elif body[index] == "}":
            depth -= 1
            if depth == 0:
                return body[start : index + 1]
    raise AssertionError(f"could not find the end of {name}()")


def test_a_writable_directory_on_path_is_chosen(tmp_path: Path) -> None:
    writable = tmp_path / "bin"
    writable.mkdir()

    chosen = _writable_path_dir(str(writable), tmp_path)

    assert chosen == str(writable)


def test_with_no_writable_path_directory_the_installer_falls_back(tmp_path: Path) -> None:
    # The fallback's reason for existing. A managed workstation where every
    # PATH entry is system-owned is ordinary, not exotic.
    if hasattr(os, "getuid") and os.getuid() == 0:
        pytest.skip("root UID bypasses standard POSIX write permissions on 0555 directories")
    unwritable = tmp_path / "locked"
    unwritable.mkdir()
    unwritable.chmod(0o555)
    try:
        chosen = _writable_path_dir(str(unwritable), tmp_path)
    finally:
        unwritable.chmod(0o755)

    assert chosen == "", "a directory nobody can write to was chosen anyway"


def test_system_directories_are_never_chosen(tmp_path: Path) -> None:
    # Even when running as a user who could write to one. Installing into
    # /usr/local/bin is what needs elevation on the machines that matter.
    chosen = _writable_path_dir("/usr/local/bin:/bin:/sbin", tmp_path)

    assert chosen == ""


def test_the_fallback_directory_is_user_local() -> None:
    body = SHELL_INSTALLER.read_text(encoding="utf-8")

    assert 'FALLBACK_DIR="${HOME}/.local/bin"' in body


def test_the_path_instruction_names_the_running_shell() -> None:
    # A generic "add it to your profile" is an instruction somebody has to go
    # and translate at three in the morning.
    body = SHELL_INSTALLER.read_text(encoding="utf-8")

    for shell in ("zsh", "bash", "fish"):
        assert shell in body, f"no PATH instruction for {shell}"
    assert ".zshrc" in body
    assert ".bashrc" in body
    assert "fish_add_path" in body


def test_the_powershell_installer_updates_only_the_user_path() -> None:
    body = POWERSHELL_INSTALLER.read_text(encoding="utf-8")

    assert "'Path', 'User'" in body or "'Path','User'" in body
    assert "SetEnvironmentVariable('Path'" in body
    # The machine-wide one needs Administrator, which is what this avoids.
    assert "SetEnvironmentVariable('Path', $null, 'Machine')" not in body


def test_the_powershell_installer_tells_the_operator_how_to_refresh_the_session() -> None:
    # A new binary nobody can run until they restart the terminal reads as a
    # failed install.
    body = POWERSHELL_INSTALLER.read_text(encoding="utf-8")

    assert "Open a new terminal" in body
    assert "$env:Path" in body


def test_a_homebrew_formula_exists_and_carries_a_checksum_per_artefact() -> None:
    body = HOMEBREW_FORMULA.read_text(encoding="utf-8")

    assert body.count("sha256 ") == body.count("url "), (
        "every artefact needs its own checksum; Homebrew is the package-manager "
        "path and it verifies for us only if we give it something to verify"
    )


def test_the_homebrew_formula_makes_no_network_call_after_the_download() -> None:
    body = "\n".join(executable_lines(HOMEBREW_FORMULA)).lower()

    for word in TELEMETRY_WORDS:
        assert word not in body, f"the formula mentions {word}"


def test_the_installers_do_not_depend_on_bash(tmp_path: Path) -> None:
    # ``dash`` is what /bin/sh is on Debian and Ubuntu, and a bashism here
    # fails on exactly the hosts most likely to run this.
    dash = shutil.which("dash")
    if dash is None:
        pytest.skip("dash is not installed on this host")

    result = subprocess.run(
        [dash, "-n", str(SHELL_INSTALLER)], capture_output=True, text=True, check=False
    )

    assert result.returncode == 0, result.stderr


def test_the_installer_cleans_up_after_itself_even_when_it_refuses() -> None:
    # A rejected archive left in /tmp is one somebody eventually runs by hand.
    body = SHELL_INSTALLER.read_text(encoding="utf-8")

    assert "trap 'rm -rf \"${work}\"' EXIT INT TERM" in body
    assert "Remove-Item -Path $work -Recurse" in POWERSHELL_INSTALLER.read_text(encoding="utf-8")


def test_the_release_location_is_overridable_for_a_private_mirror() -> None:
    # An air-gapped operator mirrors the release. An installer with a hard-coded
    # host is one they cannot use at all.
    assert "NINJASRE_RELEASE_BASE" in SHELL_INSTALLER.read_text(encoding="utf-8")
    assert "NINJASRE_RELEASE_BASE" in POWERSHELL_INSTALLER.read_text(encoding="utf-8")


def test_running_as_root_is_not_required_to_read_the_installer() -> None:
    # Sanity: the file is readable by the user who will run it.
    assert os.access(SHELL_INSTALLER, os.R_OK)
