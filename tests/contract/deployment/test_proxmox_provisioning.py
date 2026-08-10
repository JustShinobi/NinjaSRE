"""The Proxmox provisioning flow, asserted against the constants it deploys.

The flow installs the platform directly into an LXC guest — PostgreSQL under
the guest's own init, the three processes under systemd or OpenRC, no container
runtime. Nothing here provisions anything: the properties worth pinning are
properties of the declarations, for the reason the rest of this suite gives.

Four of them are load-bearing.

The guest scripts are ``/bin/sh``. One of the two supported distributions has
no bash in its template, so a guest script with a bashism is a script that
works on the distribution its author tested and fails on the other one.

The PostgreSQL major version and the graph extension's tag are one decision in
two places. The extension is compiled against one major version and loads into
no other, so a flow that let them drift would build something the server
refuses.

Every entry point runs with the virtual environment's ``site-packages`` ahead
of the standard library. The package directory the platform lives in shares a
name with a standard library module, and the standard library wins by default —
the same shadowing the images carry a fix for.

The ports and the memory ceiling are read from ``config.constants`` rather than
written twice. A provisioning script that published a port the application does
not listen on would be wrong in a way no reader notices.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
from pathlib import Path

import pytest

from config.constants.deployment import (
    DEPLOYMENT_PROFILE_HOMELAB,
    DEPLOYMENT_PROFILES,
    HOMELAB_TOTAL_MEMORY_MIB,
    SERVICE_APP,
    SERVICE_CONSOLE,
    SERVICE_PROXY,
)
from config.constants.llm import SUPPORTED_PROVIDERS
from config.constants.persistence import DATABASE_ENCRYPTION_KEY_BYTES
from config.constants.surfaces import DEFAULT_API_PORT, DEFAULT_CONSOLE_PORT

pytestmark = pytest.mark.contract

REPO_ROOT = Path(__file__).resolve().parents[3]
PROXMOX = REPO_ROOT / "deploy" / "proxmox"
NODE_SCRIPT = PROXMOX / "ninjasre-lxc.sh"
GUEST = PROXMOX / "guest"
GUEST_SCRIPTS = (GUEST / "install-system.sh", GUEST / "bring-up.sh")

#: The two the operator may choose between. Adding a third means adding its
#: package names to the runtime installer, which is why this list is asserted
#: rather than left to whatever the script's ``case`` happens to accept.
SUPPORTED_DISTRIBUTIONS: tuple[str, ...] = ("alpine", "debian")


def shell_scripts() -> tuple[Path, ...]:
    """Return every shell script the Proxmox flow ships."""
    return tuple(sorted(PROXMOX.rglob("*.sh")))


def default_of(script: Path, name: str) -> str:
    """Return a ``NAME="value"`` default declared at the top of a script."""
    match = re.search(
        rf'^{re.escape(name)}="?([^"\n]*)"?$',
        script.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert match is not None, f"{script.name} declares no default for {name}"
    return match.group(1)


def test_the_flow_ships_a_node_script_a_guest_pair_and_the_notes_to_run_them() -> None:
    """One command on the node, and the two halves it pushes into the guest."""
    assert NODE_SCRIPT.is_file()
    assert (PROXMOX / "README.md").is_file()
    assert (PROXMOX / "ninjasre-lxc.conf.example").is_file()

    for script in GUEST_SCRIPTS:
        assert script.is_file(), script


def test_every_script_is_executable() -> None:
    """``pct push`` preserves no mode, but the operator runs the node one directly."""
    for script in shell_scripts():
        assert os.stat(script).st_mode & stat.S_IXUSR, script


def test_every_script_parses() -> None:
    """``sh -n`` on the guest scripts is the check that catches a bashism's syntax."""
    for script in shell_scripts():
        interpreter = "sh" if script.parent == GUEST else "bash"
        result = subprocess.run(  # noqa: S603 — a fixed interpreter on a repo file
            [interpreter, "-n", str(script)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, f"{script}: {result.stderr}"


def test_the_guest_scripts_run_under_the_shell_the_smaller_template_has() -> None:
    """One of the two templates ships busybox and no bash."""
    for script in GUEST_SCRIPTS:
        first_line = script.read_text(encoding="utf-8").splitlines()[0]
        assert first_line == "#!/bin/sh", script


def test_the_operator_chooses_between_the_two_distributions_and_no_others() -> None:
    offered = set(
        re.findall(
            r"\b(alpine|debian|ubuntu|fedora|arch)\b", default_of(NODE_SCRIPT, "SUPPORTED_DISTROS")
        )
    )

    assert offered == set(SUPPORTED_DISTRIBUTIONS)


def test_both_distributions_have_a_package_set_in_the_system_installer() -> None:
    """A distribution offered by the node script and unhandled in the guest fails late."""
    installer = (GUEST / "install-system.sh").read_text(encoding="utf-8")

    for distribution in SUPPORTED_DISTRIBUTIONS:
        assert f"{distribution})" in installer, distribution


def test_the_container_can_run_its_own_init() -> None:
    """Without nesting an unprivileged guest cannot manage services at all."""
    features = default_of(NODE_SCRIPT, "DEFAULT_FEATURES")

    assert "nesting=1" in features


def test_the_graph_extension_is_built_against_the_pinned_major_version() -> None:
    """It compiles against one major version and loads into no other."""
    installer = GUEST / "install-system.sh"
    major = default_of(installer, "PG_MAJOR")

    assert f"PG{major}" in default_of(installer, "AGE_SOURCE_URL")


def test_the_extensions_are_pinned_rather_than_tracking_a_branch() -> None:
    """Recall is a property of a version, so a moving ref moves retrieval quality."""
    installer = GUEST / "install-system.sh"

    assert re.fullmatch(r"v\d+\.\d+\.\d+", default_of(installer, "PGVECTOR_REF"))
    assert re.fullmatch(r"\d+\.\d+\.\d+", default_of(installer, "AGE_VERSION"))


def test_the_graph_extension_is_verified_before_it_is_compiled() -> None:
    """It becomes a shared library the database server loads into its own process."""
    installer = GUEST / "install-system.sh"

    assert re.fullmatch(r"[0-9a-f]{64}", default_of(installer, "AGE_SOURCE_SHA256"))
    assert "sha256sum -c" in installer.read_text(encoding="utf-8")


def test_the_guest_runs_the_interpreter_the_project_targets() -> None:
    """Neither distribution packages it, so the flow fetches one rather than differ."""
    installer = GUEST / "install-system.sh"
    declared = (REPO_ROOT / ".python-version").read_text(encoding="utf-8").strip()

    pinned = default_of(installer, "PYTHON_VERSION")

    assert re.fullmatch(r"\d+\.\d+\.\d+", pinned)
    assert pinned.startswith(f"{declared}."), (
        f"the guest installs {pinned} and .python-version says {declared}"
    )


def test_the_thing_that_fetches_the_interpreter_is_itself_verified() -> None:
    """A checksummed extension behind an unchecked downloader is not checked."""
    installer = GUEST / "install-system.sh"
    source = installer.read_text(encoding="utf-8")

    assert re.fullmatch(r"\d+\.\d+\.\d+", default_of(installer, "UV_VERSION"))
    for architecture in ("X86_64_GNU", "X86_64_MUSL", "AARCH64_GNU", "AARCH64_MUSL"):
        assert re.fullmatch(r"[0-9a-f]{64}", default_of(installer, f"UV_SHA256_{architecture}"))
    assert source.count("sha256sum -c") >= 2


def test_the_images_run_the_same_interpreter_as_the_guest() -> None:
    """One deployment mode on a different Python is a bug nobody reproduces."""
    declared = (REPO_ROOT / ".python-version").read_text(encoding="utf-8").strip()
    images = (REPO_ROOT / "deploy" / "images" / "base-images.env").read_text(encoding="utf-8")

    match = re.search(r"^BASE_PYTHON=python:(\d+\.\d+)\.", images, re.MULTILINE)
    assert match is not None, "base-images.env declares no BASE_PYTHON"
    assert match.group(1) == declared


def test_both_extensions_the_datastore_needs_are_created() -> None:
    """One store holds relational rows, vectors and the graph, or it holds two of them."""
    bring_up = (GUEST / "bring-up.sh").read_text(encoding="utf-8")

    assert "CREATE EXTENSION IF NOT EXISTS vector" in bring_up
    assert "CREATE EXTENSION IF NOT EXISTS age" in bring_up


def test_every_entry_point_runs_with_site_packages_ahead_of_the_standard_library() -> None:
    """The platform package shares its name with a standard library module."""
    bring_up = (GUEST / "bring-up.sh").read_text(encoding="utf-8")

    assert "PYTHONPATH=${SITE_PACKAGES}" in bring_up
    assert "Environment=PYTHONPATH=${SITE_PACKAGES}" in bring_up


def test_each_service_the_topology_declares_gets_a_unit() -> None:
    """The proxy is its own process because it is the only one holding a credential."""
    bring_up = (GUEST / "bring-up.sh").read_text(encoding="utf-8")

    for service in (SERVICE_APP, SERVICE_CONSOLE, SERVICE_PROXY):
        assert f"install_service {service} " in bring_up, service


def test_both_init_systems_are_handled() -> None:
    """systemd on one distribution, OpenRC on the other, and nothing else."""
    bring_up = (GUEST / "bring-up.sh").read_text(encoding="utf-8")

    assert "write_systemd_unit" in bring_up
    assert "write_openrc_service" in bring_up


def test_the_credential_proxy_is_never_published_beyond_loopback() -> None:
    """It is the one process holding a secret; its port is not an operator choice."""
    bring_up = (GUEST / "bring-up.sh").read_text(encoding="utf-8")

    assert '"gateway.proxy" "--host 127.0.0.1' in bring_up


def test_the_published_ports_are_the_ones_the_application_listens_on() -> None:
    assert default_of(NODE_SCRIPT, "DEFAULT_API_PORT") == str(DEFAULT_API_PORT)
    assert default_of(NODE_SCRIPT, "DEFAULT_CONSOLE_PORT") == str(DEFAULT_CONSOLE_PORT)


def test_the_default_profile_is_the_one_that_declares_a_ceiling() -> None:
    """A first deployment on somebody's own hardware is the homelab case."""
    assert default_of(NODE_SCRIPT, "DEFAULT_PROFILE") == DEPLOYMENT_PROFILE_HOMELAB


def test_every_profile_the_platform_knows_is_accepted() -> None:
    accepted = default_of(NODE_SCRIPT, "SUPPORTED_PROFILES").split()

    assert set(accepted) == set(DEPLOYMENT_PROFILES)


def test_every_provider_the_platform_supports_is_accepted() -> None:
    """A provider the flow rejects is one an operator cannot deploy with."""
    accepted = default_of(NODE_SCRIPT, "SUPPORTED_LLM_PROVIDERS").split()

    assert set(accepted) == set(SUPPORTED_PROVIDERS)


def test_provisioning_stops_rather_than_starting_without_a_provider() -> None:
    """The platform refuses to start without one; the flow says so before it tries."""
    bring_up = (GUEST / "bring-up.sh").read_text(encoding="utf-8")

    assert "no model provider is configured" in bring_up


def test_the_container_is_given_more_memory_than_the_stack_is_allowed() -> None:
    """The profile's ceiling is the stack's; the image build needs headroom above it."""
    assert int(default_of(NODE_SCRIPT, "DEFAULT_MEMORY_MIB")) > HOMELAB_TOTAL_MEMORY_MIB


def test_the_generated_encryption_key_is_the_length_the_platform_requires() -> None:
    """The platform never generates one, so the provisioning script does — correctly."""
    bring_up = (GUEST / "bring-up.sh").read_text(encoding="utf-8")

    assert f"openssl rand -base64 {DATABASE_ENCRYPTION_KEY_BYTES}" in bring_up


def test_the_notes_tell_the_operator_what_differs_between_the_two_choices() -> None:
    """The compatibility question is answered in the repository, not in a chat log."""
    readme = (PROXMOX / "README.md").read_text(encoding="utf-8").lower()

    for distribution in SUPPORTED_DISTRIBUTIONS:
        assert distribution in readme
    assert "nesting" in readme
    assert "systemd" in readme
    assert "openrc" in readme
