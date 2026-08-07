"""A raw capture is the most secret-dense artefact this tooling ever holds.

It carries hostnames, addresses, guest configuration and, potentially,
cloud-init blocks. It is never committed, it is never logged, and it stops
existing once anonymised output does. These assertions are those three rules,
and the first one is enforced by geography rather than by care: the default
destination is outside the working tree, and writing inside it is refused.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from config.constants.paths import REPO_ROOT
from tools.mockplane.allowlist import Allowlist
from tools.mockplane.capture.channel import (
    ChannelError,
    NodeConfiguration,
    ReadOnlyChannel,
    SshCommandRunner,
)
from tools.mockplane.paths import is_inside_repository, raw_capture_dir

pytestmark = pytest.mark.unit


def test_a_raw_capture_defaults_to_somewhere_outside_the_repository() -> None:
    assert not is_inside_repository(raw_capture_dir()), (
        "the default destination for a raw capture is inside the working tree, "
        "which is one 'git add .' away from committing hostnames and guest configuration"
    )


def test_the_repository_is_recognised_as_the_repository() -> None:
    assert is_inside_repository(REPO_ROOT / "fixtures") is True
    assert is_inside_repository(Path("/tmp")) is False


def test_no_raw_capture_is_committed() -> None:
    tracked = subprocess.run(  # noqa: S603 — a fixed argument vector, no shell
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.splitlines()
    offending = [
        path
        for path in tracked
        if "capture" in Path(path).name and Path(path).suffix == ".json" and "fixtures/" in path
    ]
    assert not offending, f"something that looks like a raw capture is committed: {offending}"


def test_a_failed_read_does_not_repeat_what_the_node_printed() -> None:
    # A node's diagnostics routinely carry hostnames and paths, and the raw
    # capture's error path is the one place an identifier reaches a log line
    # before anonymisation has run.
    configuration = NodeConfiguration(hosts={"node01": "198.51.100.1"}, user="reader")
    runner = SshCommandRunner(configuration=configuration, timeout_seconds=0.01)
    channel = ReadOnlyChannel(runner=runner, allowlist=Allowlist.load())

    try:
        channel.read("node01", "uname -r")
    except ChannelError as failure:
        assert "198.51.100.1" not in str(failure), "the failure repeats the address it reached for"
    except OSError:  # pragma: no cover — no ssh binary on this machine
        pytest.skip("ssh is not installed here, so this path cannot be exercised")


def test_reading_from_an_unconfigured_node_names_the_node_and_nothing_else() -> None:
    channel = ReadOnlyChannel(
        runner=SshCommandRunner(configuration=NodeConfiguration(hosts={})),
        allowlist=Allowlist.load(),
    )
    with pytest.raises(ChannelError) as failure:
        channel.read("node01", "uname -r")
    assert "node01" in str(failure.value)
    assert "@" not in str(failure.value), "the failure carries a connection string"


def test_the_fixture_tree_holds_only_anonymised_output() -> None:
    from tools.mockplane.paths import fixture_root

    stray = [
        path.name
        for path in fixture_root().rglob("*")
        if path.is_file() and path.suffix not in {".json", ".md"}
    ]
    assert not stray, f"something that is not part of the dataset is in the fixture tree: {stray}"
