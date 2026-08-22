"""What may spend hosted minutes, and what may not.

This repository's whole verification contract runs on a developer machine:
`make verify`, the console gate, the browser suite, the compose stack, the
image scan, the chart, the backup cycle. Running the same work on hosted
runners on every push spent most of a month's quota in a single afternoon —
and it bought nothing that a local run had not already shown.

So the rule is the one the cost teaches: **a workflow whose work can be done
locally does not run on a push.** It stays available on demand, which is what
`workflow_dispatch` is for, and a `schedule` is refused for the same reason a
push is — an unattended cron spends the quota with nobody watching.

The delivery path is the exception, and it is not an exception to the rule so
much as an illustration of it: it runs on the cluster's own runner, where
minutes are the operator's own hardware rather than a purchased allowance, and
it does the one thing a laptop cannot — build the images this deployment runs
and push them to the registry it pulls from.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.contract.deployment.conftest import REPO_ROOT

pytestmark = pytest.mark.contract

WORKFLOWS = REPO_ROOT / ".github" / "workflows"

#: The runner label the cluster's own executor answers to. Work placed here
#: costs the operator's hardware rather than a purchased allowance.
SELF_HOSTED = "arc-k3s"

#: The one workflow allowed to run unprompted, because what it does — building
#: images and pushing them to the registry — is the one thing that cannot be
#: done from a developer machine and then handed to the cluster.
DELIVERY = "application-ci.yml"


def workflows() -> list[Path]:
    """Return every workflow file, so a new one is covered the day it lands."""
    found = sorted(WORKFLOWS.glob("*.yml"))
    assert found, "no workflows found"
    return found


def document(path: Path) -> dict[str, Any]:
    """Return the parsed workflow."""
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def triggers(parsed: dict[str, Any]) -> list[str]:
    """Return the trigger names, past YAML reading a bare ``on`` as ``True``."""
    on = parsed.get(True, parsed.get("on"))
    if isinstance(on, dict):
        return list(on)
    if isinstance(on, str):
        return [on]
    return list(on or [])


@pytest.mark.parametrize("path", workflows(), ids=lambda path: path.name)
def test_only_the_delivery_path_runs_without_being_asked(path: Path) -> None:
    """A push or a cron may only start work that costs the operator nothing."""
    unprompted = {"push", "pull_request", "schedule"}
    started = unprompted.intersection(triggers(document(path)))

    if path.name == DELIVERY:
        assert started, f"{path.name} is the delivery path and has to run on a push"
        return

    assert not started, (
        f"{path.name} starts on {sorted(started)}. Everything it does can be run "
        f"locally, so running it on hosted minutes buys nothing a developer "
        f"machine has not already shown. Leave it on workflow_dispatch."
    )


def test_the_delivery_path_stays_on_the_cluster_runner() -> None:
    """The one workflow that runs unprompted must not spend hosted minutes."""
    parsed = document(WORKFLOWS / DELIVERY)

    for name, job in (parsed.get("jobs") or {}).items():
        runner = job.get("runs-on")
        if runner is None:
            # A reusable workflow: the executor it selects is checked where it
            # is defined, and this repository pins it by digest.
            assert job.get("uses"), f"{name} names neither a runner nor a workflow"
            continue
        assert SELF_HOSTED in str(runner), (
            f"{DELIVERY}'s {name} runs on {runner!r}. The delivery path runs on "
            f"the cluster's own executor."
        )
