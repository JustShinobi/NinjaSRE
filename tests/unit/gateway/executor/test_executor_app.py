"""The executor as a process: the one thing in this system that holds an SSH key.

Everything that decides whether a command may run already exists and is tested.
What this adds is the surface, and a surface is where an authority leaks if it
leaks at all — so the tests are about what the surface will not do.

**It answers about itself without being asked for a node.** An operator needs to
know what this executor can be asked for before pointing anything at it, and a
catalogue that required a node would make discovery a privileged operation.

**A malformed request is refused rather than guessed at.** A missing node is not
an empty node; a missing command is not a default one.

**It never reports a key.** Not in health, not in the catalogue, not in an
error. The one process holding the identity is the one with the most reason
never to mention it.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gateway.executor.app import build_executor_app

pytestmark = pytest.mark.unit


class _Runner:
    def __init__(self, *, code: int = 0, out: str = "ok") -> None:
        self.code = code
        self.out = out
        self.ran: list[list[str]] = []

    async def run(
        self, *, node: str, argv: list[str], timeout_seconds: float
    ) -> tuple[int, str, str]:
        del node, timeout_seconds
        self.ran.append(argv)
        return self.code, self.out, ""


def _client(runner: object | None = None) -> TestClient:
    return TestClient(build_executor_app(runner=runner or _Runner()))  # type: ignore[arg-type]


def test_a_declared_read_runs_and_comes_back() -> None:
    runner = _Runner(out="nginx.service failed")

    answer = _client(runner).post("/execute", json={"node": "pve01", "command_id": "failed-units"})

    assert answer.status_code == 200
    assert answer.json()["stdout"] == "nginx.service failed"
    assert runner.ran[0][0] == "systemctl"


def test_a_command_nobody_declared_is_refused_and_never_run() -> None:
    runner = _Runner()

    answer = _client(runner).post("/execute", json={"node": "pve01", "command_id": "curl"})

    # Two hundred with refused set, rather than a four hundred: the caller asked
    # a well-formed question and the answer is that the command is not allowed.
    assert answer.status_code == 200
    assert answer.json()["refused"] is True
    assert runner.ran == []


def test_a_request_missing_its_node_is_refused_rather_than_defaulted() -> None:
    answer = _client().post("/execute", json={"command_id": "failed-units"})

    assert answer.status_code == 422


def test_a_write_needs_the_caller_to_have_said_so() -> None:
    runner = _Runner()

    answer = _client(runner).post(
        "/execute",
        json={
            "node": "pve01",
            "command_id": "restart-unit",
            "arguments": {"unit": "pve-cluster.service"},
        },
    )

    assert answer.json()["refused"] is True
    assert runner.ran == []


def test_the_catalogue_says_what_can_be_asked_for_without_naming_a_node() -> None:
    answer = _client().get("/commands")

    assert answer.status_code == 200
    listed = answer.json()["commands"]
    assert {entry["command_id"] for entry in listed} >= {"failed-units", "restart-unit"}
    assert any(entry["writes"] for entry in listed)


def test_the_catalogue_explains_why_each_authority_exists() -> None:
    """An entry nobody can justify is one that should not have been added, and
    an operator deciding whether to run this executor needs to read them."""
    listed = _client().get("/commands").json()["commands"]

    assert all(entry["reason"].strip() for entry in listed)


def test_health_answers_without_naming_a_key() -> None:
    answer = _client().get("/health")

    assert answer.status_code == 200
    body = answer.text.lower()
    assert "key" not in body
    assert "identity" not in body


def test_an_executor_with_no_identity_refuses_to_start(monkeypatch: pytest.MonkeyPatch) -> None:
    """An executor without a key answers every request as an unreachable node,
    which reads as a cluster problem and is a provisioning one. Failing at
    startup puts the error where somebody is already looking."""
    from gateway.executor.__main__ import IDENTITY_ENV, main

    monkeypatch.delenv(IDENTITY_ENV, raising=False)

    assert main(["--port", "0"]) == 1


def test_an_identity_that_is_not_there_is_refused_at_startup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    from gateway.executor.__main__ import IDENTITY_ENV, main

    monkeypatch.setenv(IDENTITY_ENV, "/no/such/key")

    assert main(["--port", "0"]) == 1
