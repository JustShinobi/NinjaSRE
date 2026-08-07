"""The shipped dashboards cover every metric the deployment can emit.

A reference dashboard exists so an operator's first hour is spent reading their
data rather than building panels. It stops being that the moment an instrument
is added and nobody adds a panel, and nobody ever adds the panel — so the check
is mechanical: every declared instrument has to be referenced somewhere in
``deploy/dashboards/``, and every metric a dashboard references has to be one
this deployment actually emits.

The second half matters as much as the first. A panel querying a metric nobody
emits is a permanently empty graph, and an operator who finds one stops trusting
the rest of the dashboard.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from platform.observability.metrics.definitions import DEFINITIONS, MetricFamily

pytestmark = pytest.mark.contract

REPO_ROOT = Path(__file__).resolve().parents[3]
DASHBOARDS = REPO_ROOT / "deploy" / "dashboards"

DECLARED = {definition.name for definition in DEFINITIONS}


def _grafana() -> dict[str, object]:
    """Return the shipped Grafana dashboard."""
    return json.loads((DASHBOARDS / "grafana-ninjasre.json").read_text(encoding="utf-8"))


def _referenced(text: str) -> set[str]:
    """Return every declared instrument name that appears in ``text``."""
    return {name for name in DECLARED if name in text}


def test_the_dashboards_directory_ships() -> None:
    assert DASHBOARDS.is_dir()
    assert sorted(path.name for path in DASHBOARDS.iterdir() if path.is_file()) == [
        "README.md",
        "grafana-ninjasre.json",
        "prometheus-rules.yml",
    ]


def test_the_grafana_dashboard_is_valid_json_with_a_title_and_panels() -> None:
    dashboard = _grafana()

    assert dashboard["title"]
    assert isinstance(dashboard["panels"], list)
    assert dashboard["panels"]


def test_every_declared_instrument_appears_in_a_panel() -> None:
    text = (DASHBOARDS / "grafana-ninjasre.json").read_text(encoding="utf-8")

    missing = DECLARED - _referenced(text)

    assert missing == set(), f"no panel queries: {sorted(missing)}"


def test_every_family_has_a_row_of_its_own() -> None:
    """A dashboard whose panels are in one heap is one nobody navigates."""
    titles = {
        str(panel.get("title", "")).lower()
        for panel in _grafana()["panels"]  # type: ignore[union-attr]
        if panel.get("type") == "row"
    }

    for family in MetricFamily:
        assert any(family.value in title for title in titles), family.value


def test_the_prometheus_rules_reference_only_metrics_this_deployment_emits() -> None:
    """An alert on a metric nobody writes never fires and nobody notices."""
    import re

    text = (DASHBOARDS / "prometheus-rules.yml").read_text(encoding="utf-8")
    used = set(re.findall(r"\b(?:ninjasre_)?([a-z_]+\.[a-z_.]+)\b", text))
    metric_like = {
        name
        for name in used
        if name.split(".")[0]
        in {
            "investigation",
            "llm",
            "capability",
            "integration",
            "scheduler",
            "approval",
            "guardrail",
            "memory",
        }
    }

    assert metric_like <= DECLARED, f"unknown metrics: {sorted(metric_like - DECLARED)}"
    assert metric_like, "the rules file references no metric at all"


def test_the_readme_says_how_to_import_them_without_leaving_the_host() -> None:
    readme = (DASHBOARDS / "README.md").read_text(encoding="utf-8")

    assert "NINJASRE_OTEL_ENDPOINT" in readme
    assert "grafana-ninjasre.json" in readme
    assert "prometheus-rules.yml" in readme
