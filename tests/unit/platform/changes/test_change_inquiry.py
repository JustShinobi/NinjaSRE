"""Asking what changed, and getting an answer when the answer is "nothing".

An investigation that finds no recent change has learned something, and until
this file existed it had no way to say so. An empty list is not a finding: it is
indistinguishable from a list nobody built, from a source nobody configured, and
from a query that failed quietly. So the answer is a statement with a provenance
— what was consulted, over what window, and how many changes were in that window
at all — and the three cases below lead somewhere different:

- **nothing was consulted**: whether anything changed is *unknown*;
- **something was consulted and the window was empty**: nothing changed at all;
- **something was consulted, the window had changes, none touched this**: the
  changes were real and none of them is the cause here.

The third is the one that matters, because it is the one an operator disbelieves
unless the sentence carries its own working.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from config.constants.changes import MAX_CHANGES_PER_WINDOW
from platform.changes.correlation import ComponentMap, CorrelationStrength, ResourceView
from platform.changes.errors import ChangeStateInvalid
from platform.changes.models import Change, ChangeWindow
from platform.changes.service import ChangeInquiry

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 1, 15, 0, tzinfo=UTC)
DAY = ChangeWindow.ending(NOW)

COMPONENTS = ComponentMap(
    managed={
        "monitoring": ("hal9000/lxc/115",),
        "networking": ("hal9000/lxc/104",),
    }
)

MONITORED = ResourceView(
    resource_id="res-aaa",
    correlation_key="hal9000/lxc/115",
    display_name="mon-prometheus",
    zone="infra-zone",
)

QUIET = ResourceView(
    resource_id="res-bbb",
    correlation_key="hal9000/lxc/120",
    display_name="fileserver",
    zone="storage-zone",
)


def _change(change_id: str, *, component: str = "", paths: tuple[str, ...] = ()) -> Change:
    return Change(
        change_id=change_id,
        occurred_at=NOW - timedelta(minutes=20),
        author="erik",
        message=f"feat({component or 'repo'}): something",
        paths=paths,
        source="recorded",
        component=component,
        applied_at=NOW - timedelta(minutes=13),
    )


@dataclass(slots=True)
class RecordedSource:
    """A change source that answers from a list, and says what it manages."""

    name: str = "recorded"
    answers: tuple[Change, ...] = ()
    managed: dict[str, tuple[str, ...]] = field(default_factory=dict)

    async def changes_in(
        self,
        window: ChangeWindow,
        *,
        limit: int = MAX_CHANGES_PER_WINDOW,
    ) -> Sequence[Change]:
        """Return the recorded changes that fall inside ``window``."""
        return tuple(change for change in self.answers if window.contains(change.instant))[:limit]

    def components(self) -> dict[str, tuple[str, ...]]:
        """Return what this source's components manage."""
        return self.managed


@dataclass(slots=True)
class BrokenSource:
    """A source whose repository state cannot be read."""

    name: str = "broken"

    async def changes_in(
        self,
        window: ChangeWindow,
        *,
        limit: int = MAX_CHANGES_PER_WINDOW,
    ) -> Sequence[Change]:
        """Raise, as a source pointed at a malformed state directory does."""
        del window, limit
        raise ChangeStateInvalid(["monitoring.json is not a readable apply record"])


def _inquiry(*sources: object) -> ChangeInquiry:
    return ChangeInquiry(sources=list(sources))


class TestTheNegative:
    """The three ways of having nothing to report, and why they differ."""

    @pytest.mark.asyncio
    async def test_a_quiet_resource_gets_a_sentence_naming_the_sources_and_the_window(
        self,
    ) -> None:
        source = RecordedSource(
            answers=(
                _change("9f2c1ab", component="monitoring", paths=("services/monitoring/a.tf",)),
            ),
            managed=dict(COMPONENTS.managed),
        )

        answer = await _inquiry(source).about(QUIET, window=DAY)

        assert answer.linked == ()
        assert "No change touched fileserver" in answer.statement
        assert "recorded" in answer.statement
        assert "24 hour(s)" in answer.statement

    @pytest.mark.asyncio
    async def test_the_negative_says_how_many_changes_there_were_in_the_window(self) -> None:
        source = RecordedSource(
            answers=(
                _change("9f2c1ab", component="monitoring", paths=("services/monitoring/a.tf",)),
                _change("3d81e0c", component="networking", paths=("services/networking/b.tf",)),
            ),
            managed=dict(COMPONENTS.managed),
        )

        answer = await _inquiry(source).about(QUIET, window=DAY)

        # Two changes, neither of them this resource's. Said in as many words:
        # "nothing changed" and "two things changed and neither was yours" send
        # an operator to different places.
        assert answer.total == 2
        assert "2 change(s)" in answer.statement

    @pytest.mark.asyncio
    async def test_an_empty_window_says_nothing_changed_at_all(self) -> None:
        answer = await _inquiry(RecordedSource()).about(QUIET, window=DAY)

        assert answer.total == 0
        assert "No change of any kind" in answer.statement

    @pytest.mark.asyncio
    async def test_a_deployment_with_no_source_says_unknown_rather_than_nothing(self) -> None:
        # The distinction the whole entry exists for. An absence from a source
        # nobody configured is not evidence of anything, and a report that said
        # "no change touched this" on the strength of it would be lying.
        answer = await _inquiry().about(QUIET, window=DAY)

        assert answer.answered is False
        assert "No change source is configured" in answer.statement

    @pytest.mark.asyncio
    async def test_the_negative_is_an_evidence_entry_rather_than_an_absence(self) -> None:
        answer = await _inquiry(RecordedSource()).about(QUIET, window=DAY)
        record = answer.to_record()

        assert record["statement"] == answer.statement
        assert record["sources"] == ["recorded"]
        assert record["window"]["start"] == DAY.start.isoformat()
        assert record["window"]["end"] == DAY.end.isoformat()


class TestWhenSomethingDidChange:
    """The positive answer, which is the same shape with entries in it."""

    @pytest.mark.asyncio
    async def test_a_change_that_manages_the_resource_comes_back_graded(self) -> None:
        source = RecordedSource(
            answers=(
                _change("9f2c1ab", component="monitoring", paths=("services/monitoring/a.tf",)),
            ),
            managed=dict(COMPONENTS.managed),
        )

        answer = await _inquiry(source).about(MONITORED, window=DAY)

        assert len(answer.linked) == 1
        assert answer.linked[0].strength is CorrelationStrength.MANAGES_RESOURCE
        assert "1 of them altered something that manages this resource" in answer.statement

    @pytest.mark.asyncio
    async def test_a_temporal_coincidence_is_returned_and_is_not_counted_as_a_link(
        self,
    ) -> None:
        source = RecordedSource(
            answers=(
                _change("3d81e0c", component="networking", paths=("services/networking/b.tf",)),
            ),
            managed=dict(COMPONENTS.managed),
        )

        answer = await _inquiry(source).about(MONITORED, window=DAY)

        assert answer.linked == ()
        assert len(answer.changes) == 1
        assert answer.changes[0].strength is CorrelationStrength.WINDOW_ONLY

    @pytest.mark.asyncio
    async def test_the_component_map_is_gathered_from_whichever_sources_have_one(self) -> None:
        # A git-host source has no component map. A deployment with both still
        # correlates through the one that does.
        without = RecordedSource(name="git:gitlab", answers=())
        with_map = RecordedSource(
            answers=(
                _change("9f2c1ab", component="monitoring", paths=("services/monitoring/a.tf",)),
            ),
            managed=dict(COMPONENTS.managed),
        )

        answer = await _inquiry(without, with_map).about(MONITORED, window=DAY)

        assert answer.linked[0].strength is CorrelationStrength.MANAGES_RESOURCE
        assert answer.sources == ("git:gitlab", "recorded")


class TestWhenASourceFails:
    """A source that could not answer, reported rather than swallowed."""

    @pytest.mark.asyncio
    async def test_a_failing_source_does_not_stop_the_ones_that_work(self) -> None:
        working = RecordedSource(
            answers=(
                _change("9f2c1ab", component="monitoring", paths=("services/monitoring/a.tf",)),
            ),
            managed=dict(COMPONENTS.managed),
        )

        answer = await _inquiry(BrokenSource(), working).about(MONITORED, window=DAY)

        assert len(answer.linked) == 1

    @pytest.mark.asyncio
    async def test_a_failing_source_is_named_so_the_negative_is_not_believed_too_much(
        self,
    ) -> None:
        answer = await _inquiry(BrokenSource()).about(QUIET, window=DAY)

        assert answer.degraded == (
            "broken: the change state has 1 problem(s): "
            "monitoring.json is not a readable apply record",
        )
        # And the claim is downgraded: a window nobody could read is not a
        # window nothing happened in.
        assert answer.answered is False


@pytest.mark.asyncio
async def test_the_answer_is_capped_across_every_source_at_once() -> None:
    many = RecordedSource(
        answers=tuple(
            _change(f"c{index:05d}", component="monitoring", paths=("services/monitoring/a.tf",))
            for index in range(MAX_CHANGES_PER_WINDOW + 10)
        ),
        managed=dict(COMPONENTS.managed),
    )

    answer = await _inquiry(many).about(MONITORED, window=DAY)

    assert len(answer.changes) == MAX_CHANGES_PER_WINDOW
    assert answer.truncated is True


@pytest.mark.asyncio
async def test_the_same_question_answered_twice_reads_identically() -> None:
    source = RecordedSource(
        answers=(
            _change("9f2c1ab", component="monitoring", paths=("services/monitoring/a.tf",)),
            _change("3d81e0c", component="networking", paths=("services/networking/b.tf",)),
        ),
        managed=dict(COMPONENTS.managed),
    )

    first = await _inquiry(source).about(MONITORED, window=DAY)
    second = await _inquiry(source).about(MONITORED, window=DAY)

    assert first.to_record() == second.to_record()
