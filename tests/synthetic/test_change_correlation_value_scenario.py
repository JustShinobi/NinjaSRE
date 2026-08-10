"""What correlating through the resource is worth, measured by removing it.

The scenario is the one the specification is written around. An error starts at
14:32. Three things happened in the half hour before it, and only one of them
could have caused it:

- **14:28** — the ``storage`` component was applied. Four minutes before the
  error, and it built a different container on a different network.
- **14:19** — the ``monitoring`` component was applied, altering
  ``services/monitoring/stack/``. It built the container that is now failing.
- **14:12** — somebody committed a change to the monitoring alert rules and
  nobody applied it. It touched the cluster not at all.

Two arms over that one apply record.

**With correlation**, the question runs through the resource: a path names a
component, the component's own state names what it built, and one of those is
the failing container. The 14:19 apply comes back first, graded
``manages_resource``, and the 14:28 apply comes back labelled a temporal
coincidence.

**Without it**, the only ordering available is the clock, and the clock says the
storage apply. That is not a strawman: "what was deployed most recently before
this broke" is exactly what an investigation does when nothing tells it
otherwise, and it is the answer this feature exists to stop being given.

The arms differ because the mechanism was removed, not because the fixture said
so — both read the same apply record through the same source.

The second scenario is the negative. A container nothing in the record manages
gets a sentence naming the window and the sources, and an investigation that
reads it stops looking at deploys.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from capabilities.tools.changes import binding
from capabilities.tools.changes.changes_in_window import changes_in_window
from platform.changes.correlation import CorrelationStrength, ResourceView
from platform.changes.infra_apply import InfraApplySource
from platform.changes.models import Change, ChangeWindow
from platform.changes.service import ChangeAnswer, ChangeInquiry

pytestmark = pytest.mark.synthetic

#: The moment the error started, and the moment every window ends. Relative to
#: the real clock because the capability windows back from it; the offsets below
#: are what the scenario is actually about.
ERROR_AT = datetime.now(UTC)

#: When the component that manages the failing container was applied. Thirteen
#: minutes, which is the number the specification's own sentence uses.
MANAGING_APPLY_MINUTES = 13

#: When an unrelated component was applied. Nearer in time, which is the whole
#: point: it wins on the clock and loses on the estate.
UNRELATED_APPLY_MINUTES = 4

#: The failing container: built by the monitoring component, on the
#: infrastructure network.
FAILING = ResourceView(
    resource_id="res-mon-115",
    correlation_key="hal9000/lxc/115",
    display_name="mon-prometheus",
    zone="infra-zone",
    kind="container",
)

#: A container nothing in the apply record manages. The quiet resource.
QUIET = ResourceView(
    resource_id="res-dns-199",
    correlation_key="hal9000/lxc/199",
    display_name="adguard-primary",
    zone="apps-zone",
    kind="container",
)


def _at(minutes: int) -> str:
    """Return the instant ``minutes`` before the error, as the record spells it."""
    return (ERROR_AT - timedelta(minutes=minutes)).isoformat().replace("+00:00", "Z")


def _record(root: Path) -> None:
    """Write the apply record this cluster would have written for that half hour."""
    state = root / ".infra-state"
    state.mkdir()
    (state / "monitoring.json").write_text(
        json.dumps(
            {
                "component": "monitoring",
                "manages": ["hal9000/lxc/115", "hal9000/lxc/116"],
                "applies": [
                    {
                        "revision": "9f2c1ab",
                        "author": "erik",
                        "message": "feat(monitoring): raise the scrape interval on the stack",
                        "committed_at": _at(MANAGING_APPLY_MINUTES + 8),
                        "applied_at": _at(MANAGING_APPLY_MINUTES),
                        "outcome": "applied",
                        "paths": ["services/monitoring/stack/values.yaml"],
                    },
                    {
                        "revision": "3d81e0c",
                        "author": "erik",
                        "message": "chore(monitoring): tidy the alert rule comments",
                        "committed_at": _at(20),
                        "outcome": "committed",
                        "paths": ["services/monitoring/rules/node.yaml"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    (state / "storage.json").write_text(
        json.dumps(
            {
                "component": "storage",
                "manages": ["hal9000/lxc/120"],
                "applies": [
                    {
                        "revision": "b0c99fe",
                        "author": "erik",
                        "message": "feat(storage): widen the backup datastore",
                        "committed_at": _at(UNRELATED_APPLY_MINUTES + 6),
                        "applied_at": _at(UNRELATED_APPLY_MINUTES),
                        "outcome": "applied",
                        "paths": ["services/storage/datastore/main.tf"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


class RecordedEstate:
    """The composition root's half: an estate lookup and the inquiry.

    The same object a deployment binds, built here over a real ``InfraApplySource``
    reading a real directory. Nothing in either arm is simulated except the
    repository.
    """

    def __init__(self, root: Path, known: dict[str, ResourceView]) -> None:
        self.inquiry = ChangeInquiry(sources=[InfraApplySource(root=root)])
        self.known = known

    async def changes_for(self, resource: str, *, window: ChangeWindow) -> ChangeAnswer | None:
        """Return the answer for ``resource``, or ``None`` when it is not in the estate."""
        view = self.known.get(resource)
        return None if view is None else await self.inquiry.about(view, window=window)


@pytest.fixture
def cluster(tmp_path: Path) -> Iterator[RecordedEstate]:
    """Bind the capability against the recorded apply record."""
    _record(tmp_path)
    access = RecordedEstate(
        tmp_path,
        {FAILING.resource_id: FAILING, QUIET.resource_id: QUIET},
    )
    previous = binding.bind(access)
    try:
        yield access
    finally:
        binding.restore(previous)


def nearest_in_time(changes: Sequence[Change]) -> Change:
    """Return what an investigation picks when nothing tells it otherwise.

    The ablation arm, and it is not a strawman: with no correlation available,
    "the most recent deploy before the symptom" is the ordering every runbook
    reaches for, and it is what a model does with a list of changes and a
    timestamp.
    """
    return max(changes, key=lambda change: change.instant)


class TestTheApplyThatCausedIt:
    """One error, three changes, two ways of choosing between them."""

    @pytest.mark.asyncio
    async def test_with_correlation_the_managing_apply_is_the_one_reported_first(
        self, cluster: RecordedEstate
    ) -> None:
        result = await changes_in_window(FAILING.resource_id)

        rows = result.value["changes"]
        assert rows[0]["change_id"] == "9f2c1ab"
        assert rows[0]["strength"] == CorrelationStrength.MANAGES_RESOURCE.value
        assert rows[0]["chain"] == [
            "services/monitoring/stack/values.yaml",
            "monitoring",
            "hal9000/lxc/115",
        ]

    @pytest.mark.asyncio
    async def test_without_correlation_the_nearest_deploy_is_the_wrong_one(
        self, cluster: RecordedEstate
    ) -> None:
        # The same apply record, read by the same source, ordered the only way
        # available when the correlation is removed.
        source = InfraApplySource(root=Path(cluster.inquiry.sources[0].root))
        window = ChangeWindow.ending(datetime.now(UTC))

        picked = nearest_in_time(await source.changes_in(window))

        assert picked.change_id == "b0c99fe"
        assert picked.component == "storage"

    @pytest.mark.asyncio
    async def test_the_arms_disagree_which_is_the_delta_this_scenario_measures(
        self, cluster: RecordedEstate
    ) -> None:
        with_correlation = (await changes_in_window(FAILING.resource_id)).value["changes"][0]
        source = InfraApplySource(root=Path(cluster.inquiry.sources[0].root))
        without = nearest_in_time(await source.changes_in(ChangeWindow.ending(datetime.now(UTC))))

        assert with_correlation["change_id"] != without.change_id

    @pytest.mark.asyncio
    async def test_the_unrelated_apply_is_still_reported_and_is_labelled_a_coincidence(
        self, cluster: RecordedEstate
    ) -> None:
        # Not hidden. An investigation that never saw it could not rule it out,
        # and ruling things out is half of what a report is for.
        rows = {
            row["change_id"]: row
            for row in (await changes_in_window(FAILING.resource_id)).value["changes"]
        }

        assert rows["b0c99fe"]["strength"] == CorrelationStrength.WINDOW_ONLY.value
        assert rows["b0c99fe"]["temporal_only"] is True
        assert "coincidence" in rows["b0c99fe"]["why"].lower()

    @pytest.mark.asyncio
    async def test_the_commit_nobody_applied_never_outranks_the_apply(
        self, cluster: RecordedEstate
    ) -> None:
        rows = (await changes_in_window(FAILING.resource_id)).value["changes"]
        order = [row["change_id"] for row in rows]

        assert order.index("9f2c1ab") < order.index("3d81e0c")
        assert rows[order.index("3d81e0c")]["applied"] is False

    @pytest.mark.asyncio
    async def test_the_conclusion_can_quote_the_sentence_the_specification_asks_for(
        self, cluster: RecordedEstate
    ) -> None:
        # "The error started at 14:32. At 14:19 the monitoring component was
        # applied, altering services/monitoring/stack/. The affected workload is
        # managed by that component." Every clause of it is in the result.
        result = await changes_in_window(FAILING.resource_id)
        text = result.value["text"]

        assert "monitoring" in text
        assert "services/monitoring/stack/values.yaml" in text
        assert "manages this resource" in text
        assert result.evidence[0].reference == "change:9f2c1ab"


class TestTheQuietResource:
    """The negative, which is the other half of being useful."""

    @pytest.mark.asyncio
    async def test_a_resource_nothing_manages_gets_the_sentence_rather_than_silence(
        self, cluster: RecordedEstate
    ) -> None:
        result = await changes_in_window(QUIET.resource_id)

        assert result.succeeded
        assert "No change touched adguard-primary" in result.value["statement"]
        assert "infra_apply" in result.value["statement"]

    @pytest.mark.asyncio
    async def test_the_negative_says_how_many_changes_it_looked_past(
        self, cluster: RecordedEstate
    ) -> None:
        result = await changes_in_window(QUIET.resource_id)

        # Three changes in the window, none of them this container's. "Nothing
        # changed" and "three things changed and none was yours" send an
        # operator to different places.
        assert result.value["total"] == 3
        assert "3 change(s)" in result.value["statement"]

    @pytest.mark.asyncio
    async def test_the_negative_enters_the_trace_as_evidence(self, cluster: RecordedEstate) -> None:
        result = await changes_in_window(QUIET.resource_id)

        assert result.evidence[0].reference == f"change:none:{QUIET.resource_id}"
        assert "No change touched adguard-primary" in result.evidence[0].summary

    @pytest.mark.asyncio
    async def test_nothing_in_the_quiet_answer_is_graded_above_a_coincidence(
        self, cluster: RecordedEstate
    ) -> None:
        result = await changes_in_window(QUIET.resource_id)

        assert all(row["temporal_only"] for row in result.value["changes"])


@pytest.mark.asyncio
async def test_the_scenario_reads_the_same_twice(cluster: RecordedEstate) -> None:
    # Two runs of one fixture have to agree. The apply record is read from a
    # directory, and a filesystem promises no order.
    first = (await changes_in_window(FAILING.resource_id)).value["changes"]
    second = (await changes_in_window(FAILING.resource_id)).value["changes"]

    assert [row["change_id"] for row in first] == [row["change_id"] for row in second]
