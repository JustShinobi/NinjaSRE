"""The relate is two fields, not one: ``headline`` and ``report``, over the real route.

``summary`` carried both, mixed, and a console assuming it was a sentence
rendered a whole markdown document as a title. This is the contract that
closes that: a sentence a reader can use as a name, and a document, as two
distinct fields — for a run this feature wrote and for one that predates it.
"""

from __future__ import annotations

import pytest

from config.constants.runs import TRIGGER_ALERT
from platform.persistence.ports.run_trace_store import RunStatus
from platform.persistence.ports.transaction import TenantScope
from platform.runs.recorder import RunRecorder
from tests.contract.runs._deployment import ORG, TEAM, Deployment, bearer

pytestmark = pytest.mark.contract


async def _seed_completed_run(
    deployment: Deployment, *, run_id: str, summary: str, headline: str = ""
) -> None:
    """Seed one completed run through the real recorder, exactly as a run closes in production."""
    scope = TenantScope(org_id=ORG, team_node_id=TEAM)
    async with deployment.gateway.begin(scope) as uow:
        recorder = RunRecorder(store=uow.run_traces)
        await recorder.start_run(
            trigger=TRIGGER_ALERT, principal_id="alertmanager", team_node_id=TEAM, run_id=run_id
        )
        await recorder.complete_run(
            run_id, status=RunStatus.COMPLETED, summary=summary, headline=headline
        )


class TestTheContractCarriesTwoDistinctFields:
    async def test_a_run_with_a_stored_headline_returns_both_fields_distinctly(
        self, deployment: Deployment
    ) -> None:
        await _seed_completed_run(
            deployment,
            run_id="run-1",
            summary="## Root cause\n\nThe disk on host-1 filled up.",
            headline="Disk on host-1 filled up, blocking writes",
        )

        response = await deployment.client.get(
            "/v1/runs/run-1", headers=bearer(deployment.operator_secret)
        )

        assert response.status_code == 200
        body = response.json()
        assert body["headline"] == "Disk on host-1 filled up, blocking writes"
        assert body["report"] == "## Root cause\n\nThe disk on host-1 filled up."
        assert body["headline"] != body["report"]

    async def test_the_headline_is_one_line_without_markdown(self, deployment: Deployment) -> None:
        await _seed_completed_run(
            deployment,
            run_id="run-1",
            summary="body",
            headline="Disk on host-1 filled up",
        )

        response = await deployment.client.get(
            "/v1/runs/run-1", headers=bearer(deployment.operator_secret)
        )

        headline = response.json()["headline"]
        assert "\n" not in headline
        for marker in ("#", "*", "`", "_"):
            assert marker not in headline

    async def test_summary_still_serves_the_same_text_as_the_document(
        self, deployment: Deployment
    ) -> None:
        """FR: ``summary`` survives this feature, serving the document, until the
        console-side feature that reads the two new fields removes it."""
        await _seed_completed_run(
            deployment, run_id="run-1", summary="the whole report", headline="a name"
        )

        response = await deployment.client.get(
            "/v1/runs/run-1", headers=bearer(deployment.operator_secret)
        )

        body = response.json()
        assert body["summary"] == body["report"] == "the whole report"


class TestARunFromBeforeThisFeatureIsStillLegible:
    async def test_it_returns_the_document_it_always_had(self, deployment: Deployment) -> None:
        await _seed_completed_run(
            deployment, run_id="run-old", summary="### Incident Findings\n\ndisk full"
        )

        response = await deployment.client.get(
            "/v1/runs/run-old", headers=bearer(deployment.operator_secret)
        )

        assert response.json()["report"] == "### Incident Findings\n\ndisk full"

    async def test_it_returns_a_synthesised_non_empty_headline(
        self, deployment: Deployment
    ) -> None:
        await _seed_completed_run(
            deployment, run_id="run-old", summary="### Incident Findings\n\ndisk full"
        )

        response = await deployment.client.get(
            "/v1/runs/run-old", headers=bearer(deployment.operator_secret)
        )

        headline = response.json()["headline"]
        assert headline.strip() != ""

    async def test_the_synthesised_headline_is_not_the_documents_own_heading(
        self, deployment: Deployment
    ) -> None:
        """The exact regression this feature exists to eliminate."""
        await _seed_completed_run(
            deployment, run_id="run-old", summary="### Incident Findings for host-1\n\ndisk full"
        )

        response = await deployment.client.get(
            "/v1/runs/run-old", headers=bearer(deployment.operator_secret)
        )

        assert response.json()["headline"] != "Incident Findings for host-1"
