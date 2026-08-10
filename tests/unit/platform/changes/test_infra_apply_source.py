"""What the cluster's own apply record says, and what it refuses to say.

The tree under ``tests/corpus/operational/.infra-state/`` is shaped like the
record a repository driven by ``./infra apply --component <x>`` keeps: one
document per component, each holding what that component manages and every
revision anybody applied through it. The message shapes are the real ones —
``fix(networking)!: …``, ``feat(monitoring): …`` — because a source that only
ever met tidy fixtures is one that meets a breaking-change marker for the first
time in production.

The assertion this file exists for is the second one: **a revision somebody
committed and nobody applied is reported as such.** That single field is the
difference between correlation and coincidence, and a source that reported the
two identically would make every merged pull request a suspect in an outage on
an environment it was never deployed to.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from config.constants.changes import INFRA_STATE_ROOT, MAX_APPLY_RECORD_BYTES
from platform.changes.errors import ChangeStateInvalid
from platform.changes.infra_apply import INFRA_APPLY_SOURCE, InfraApplySource
from platform.changes.models import ChangeWindow

pytestmark = pytest.mark.unit

CORPUS = Path(__file__).resolve().parents[3] / "corpus" / "operational"

#: The moment the fixture's applies are read against. Fixed rather than "now":
#: a window computed from the wall clock is a suite whose two runs disagree the
#: day the fixture ages out of it.
NOW = datetime(2026, 8, 1, 15, 0, tzinfo=UTC)

#: The window the whole file works in unless a test says otherwise.
DAY = ChangeWindow.ending(NOW)


def _source(root: Path | None = None) -> InfraApplySource:
    """Return the source pointed at the fixture repository."""
    return InfraApplySource(root=root or CORPUS)


class TestWhatItReads:
    """The window question, answered against a record shaped like the real one."""

    @pytest.mark.asyncio
    async def test_a_window_returns_what_was_altered_in_it_newest_first(self) -> None:
        found = await _source().changes_in(DAY)

        assert [change.change_id for change in found] == ["3d81e0c", "9f2c1ab", "7ba4d19"]

    @pytest.mark.asyncio
    async def test_every_change_carries_author_instant_message_and_paths(self) -> None:
        found = {change.change_id: change for change in await _source().changes_in(DAY)}

        applied = found["9f2c1ab"]
        assert applied.author == "erik"
        assert applied.message == "feat(monitoring): raise the scrape interval on the stack"
        assert applied.occurred_at == datetime(2026, 8, 1, 14, 2, 11, tzinfo=UTC)
        assert applied.applied_at == datetime(2026, 8, 1, 14, 19, 3, tzinfo=UTC)
        assert applied.paths == (
            "services/monitoring/stack/main.tf",
            "services/monitoring/stack/values.yaml",
        )
        assert applied.component == "monitoring"
        assert applied.source == INFRA_APPLY_SOURCE

    @pytest.mark.asyncio
    async def test_a_revision_nobody_applied_is_marked_as_one(self) -> None:
        found = {change.change_id: change for change in await _source().changes_in(DAY)}

        assert found["3d81e0c"].applied is False
        assert found["3d81e0c"].applied_at is None
        # And it still carries everything else, because a commit that changed
        # nothing is still a fact somebody may want to see.
        assert found["3d81e0c"].component == "monitoring"
        assert found["9f2c1ab"].applied is True

    @pytest.mark.asyncio
    async def test_an_apply_older_than_the_window_is_not_in_it(self) -> None:
        found = await _source().changes_in(DAY)

        assert "b0c99fe" not in {change.change_id for change in found}

        wider = await _source().changes_in(ChangeWindow.ending(NOW, hours=24 * 6))
        assert "b0c99fe" in {change.change_id for change in wider}

    @pytest.mark.asyncio
    async def test_a_change_is_placed_in_the_window_by_when_it_reached_the_cluster(self) -> None:
        # The monitoring apply was committed at 14:02 and applied at 14:19. A
        # window that opens at 14:15 holds it, because 14:19 is when the cluster
        # changed and 14:02 is when somebody wrote a file.
        late = ChangeWindow(start=datetime(2026, 8, 1, 14, 15, tzinfo=UTC), end=NOW)

        found = {change.change_id for change in await _source().changes_in(late)}

        assert "9f2c1ab" in found
        assert "7ba4d19" not in found

    @pytest.mark.asyncio
    async def test_the_same_window_read_twice_returns_the_same_order(self) -> None:
        first = [change.change_id for change in await _source().changes_in(DAY)]
        second = [change.change_id for change in await _source().changes_in(DAY)]

        assert first == second

    @pytest.mark.asyncio
    async def test_a_limit_cuts_the_newest_end_rather_than_an_arbitrary_one(self) -> None:
        found = await _source().changes_in(DAY, limit=2)

        assert [change.change_id for change in found] == ["3d81e0c", "9f2c1ab"]

    def test_the_components_map_to_what_each_one_manages(self) -> None:
        assert _source().components() == {
            "monitoring": ("hal9000/lxc/115", "hal9000/lxc/116"),
            "networking": ("hal9000/lxc/104",),
            "storage": ("hal9000/lxc/120",),
        }

    def test_the_outcome_the_record_declared_travels_with_the_change(self) -> None:
        state = _source().read_state()
        found = {change.change_id: change for change in state.changes}

        assert found["9f2c1ab"].detail["outcome"] == "applied"
        assert found["3d81e0c"].detail["outcome"] == "committed"


class TestWhatItRefuses:
    """A state directory that is not one, and one that is not there at all."""

    @pytest.mark.asyncio
    async def test_a_repository_with_no_state_directory_reports_nothing_rather_than_failing(
        self, tmp_path: Path
    ) -> None:
        # The ordinary condition of a repository nobody has applied through this
        # tooling. Not a fault, and not a reason for an investigation to stop.
        source = _source(tmp_path)

        assert await source.changes_in(DAY) == ()
        assert source.components() == {}

    def test_a_document_that_is_not_an_apply_record_names_every_problem_at_once(
        self, tmp_path: Path
    ) -> None:
        state = tmp_path / INFRA_STATE_ROOT
        state.mkdir()
        (state / "broken.json").write_text("{not json", encoding="utf-8")
        (state / "empty.json").write_text(
            json.dumps({"applies": [{"author": "erik"}]}), encoding="utf-8"
        )

        with pytest.raises(ChangeStateInvalid) as refusal:
            _source(tmp_path).read_state()

        assert len(refusal.value.problems) == 2
        assert any("broken.json" in problem for problem in refusal.value.problems)
        assert any("empty.json" in problem for problem in refusal.value.problems)

    def test_a_record_past_the_byte_ceiling_is_refused_naming_the_constant(
        self, tmp_path: Path
    ) -> None:
        state = tmp_path / INFRA_STATE_ROOT
        state.mkdir()
        (state / "huge.json").write_text(
            " " * (MAX_APPLY_RECORD_BYTES + 1) + "{}", encoding="utf-8"
        )

        with pytest.raises(ChangeStateInvalid) as refusal:
            _source(tmp_path).read_state()

        assert any("MAX_APPLY_RECORD_BYTES" in problem for problem in refusal.value.problems)

    def test_an_apply_with_no_instant_is_a_problem_rather_than_a_change_at_epoch(
        self, tmp_path: Path
    ) -> None:
        state = tmp_path / INFRA_STATE_ROOT
        state.mkdir()
        (state / "monitoring.json").write_text(
            json.dumps(
                {
                    "component": "monitoring",
                    "applies": [{"revision": "abc1234", "author": "erik", "message": "x"}],
                }
            ),
            encoding="utf-8",
        )

        with pytest.raises(ChangeStateInvalid) as refusal:
            _source(tmp_path).read_state()

        assert any("committed_at" in problem for problem in refusal.value.problems)
