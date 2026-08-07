"""A scenario directory builder, so a malformed-fixture test states one mistake.

Every test here is about a single defect in a single file. Writing four
fixtures by hand in each one would bury that defect in three files nobody is
asserting about, and the first time the schema gained a field every test would
need editing. So: one valid scenario, and each test names the one thing it
breaks.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pytest
import yaml

#: A scenario that loads. Every malformed case starts from this and breaks one
#: thing, so the assertion is about the break rather than about the shape.
VALID_SCENARIO: dict[str, Any] = {
    "schema_version": "1",
    "scenario_id": "001-oom-kill",
    "failure_mode": "memory_exhaustion",
    "severity": "critical",
    "scenario_difficulty": 1,
    "available_evidence": ["kubernetes"],
    "integrations": ["kubernetes"],
}

VALID_ANSWER: dict[str, Any] = {
    "root_cause_category": "resource_exhaustion",
    "required_keywords": ["memory", "limit"],
    "model_response": "ROOT_CAUSE: the checkout container exceeded its memory limit.\n",
}

VALID_ALERT: dict[str, Any] = {
    "payload": {
        "receiver": "payments-oncall",
        "status": "firing",
        "alerts": [
            {
                "status": "firing",
                "labels": {"alertname": "HighErrorRate", "severity": "critical"},
                "annotations": {"summary": "checkout error rate above 5%"},
                "startsAt": "2026-08-07T12:18:00+00:00",
                "endsAt": "0001-01-01T00:00:00Z",
            }
        ],
    },
    "received_at": "2026-08-07T12:30:00+00:00",
}

VALID_EVIDENCE: dict[str, Any] = {
    "integration": "kubernetes",
    "responses": [
        {
            "match": {"path_contains": "/events"},
            "status": 200,
            "content_type": "application/json",
            "body": {"items": [{"reason": "OOMKilled"}]},
        }
    ],
}


#: A Kubernetes scenario that really runs: the recorded response matches the
#: path ``kubernetes_workload_events`` calls, and the answer key is about what
#: that response says.
RUNNABLE_SCENARIO: dict[str, Any] = {
    "schema_version": "1",
    "scenario_id": "001-oom-kill",
    "title": "checkout is OOM-killed under load",
    "failure_mode": "memory_exhaustion",
    "severity": "critical",
    "scenario_difficulty": 1,
    "available_evidence": ["kubernetes"],
    "integrations": ["kubernetes"],
    "team_id": "payments",
}

RUNNABLE_ANSWER: dict[str, Any] = {
    "root_cause_category": "resource_exhaustion",
    "required_keywords": ["memory", "limit"],
    "forbidden_categories": ["healthy"],
    "required_evidence_sources": ["kubernetes"],
    "optimal_trajectory": ["kubernetes_workload_events"],
    "max_investigation_loops": 4,
    "model_response": "ROOT_CAUSE: the checkout container exceeded its 512Mi memory limit.\n",
}

RUNNABLE_EVIDENCE: dict[str, Any] = {
    "integration": "kubernetes",
    "responses": [
        {
            "match": {"method": "GET", "path_contains": "/events"},
            "status": 200,
            "content_type": "application/json",
            "body": {
                "items": [
                    {
                        "reason": "OOMKilled",
                        "type": "Warning",
                        "message": "Container checkout exceeded its memory limit of 512Mi",
                        "count": 3,
                        "involvedObject": {"name": "checkout-7f4c"},
                        "lastTimestamp": "2026-08-07T11:58:02Z",
                    }
                ],
                "metadata": {"continue": ""},
            },
        }
    ],
}


ScenarioWriter = Callable[..., Path]


@pytest.fixture
def write_scenario(tmp_path: Path) -> ScenarioWriter:
    """Return a factory writing one scenario directory and returning its path."""

    def write(
        *,
        suite: str = "kubernetes",
        name: str = "001-oom-kill",
        scenario: Mapping[str, Any] | None = VALID_SCENARIO,
        answer: Mapping[str, Any] | None = VALID_ANSWER,
        alert: Mapping[str, Any] | None = VALID_ALERT,
        evidence: Mapping[str, Mapping[str, Any]] | None = None,
        raw_scenario: str | None = None,
        root: Path | None = None,
    ) -> Path:
        base = root if root is not None else tmp_path
        directory = base / suite / name
        directory.mkdir(parents=True, exist_ok=True)

        if raw_scenario is not None:
            (directory / "scenario.yml").write_text(raw_scenario, encoding="utf-8")
        elif scenario is not None:
            (directory / "scenario.yml").write_text(
                yaml.safe_dump(dict(scenario)), encoding="utf-8"
            )

        if answer is not None:
            (directory / "answer.yml").write_text(yaml.safe_dump(dict(answer)), encoding="utf-8")
        if alert is not None:
            (directory / "alert.json").write_text(json.dumps(dict(alert)), encoding="utf-8")

        fixtures = {"kubernetes.json": VALID_EVIDENCE} if evidence is None else evidence
        for filename, document in fixtures.items():
            (directory / filename).write_text(json.dumps(dict(document)), encoding="utf-8")

        return directory

    return write


@pytest.fixture
def runnable_scenario(write_scenario: ScenarioWriter) -> Any:
    """Return a loaded scenario whose fixture answers a real Kubernetes capability."""
    from tests.harness.loader import load_scenario

    return load_scenario(
        write_scenario(
            scenario=RUNNABLE_SCENARIO,
            answer=RUNNABLE_ANSWER,
            evidence={"kubernetes.json": RUNNABLE_EVIDENCE},
        )
    )
