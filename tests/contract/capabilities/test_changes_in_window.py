"""The contract ``changes_in_window`` keeps, with no repository and no vendor.

Three things are worth asserting without either, and each of them is a way the
capability could reach the catalogue having promised something it does not do.

**The declaration is complete**, because it is what the selector scores, the
approval gate reads, and the console renders. A tool that arrives declaring
nothing is worse than one that is absent: it will be selected.

**The result rows carry their strength.** The whole value of this capability is
that "a deploy happened" and "the component that manages this container was
applied" are different claims; a row that reached the model without its grading
would collapse them, and the correlation might as well not exist.

**The negative comes back as a result rather than as an empty one.** A quiet
resource produces a statement with a provenance, and a deployment with nothing
configured produces an explicit unavailability — not the same statement with
zero rows, which is what would let a report say "nothing changed" about a
deployment that never looked.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from capabilities.tools.changes import binding
from capabilities.tools.changes.changes_in_window import changes_in_window
from config.constants.changes import (
    CHANGES_TOOL_NAME,
    DEFAULT_CHANGE_WINDOW_HOURS,
    MAX_CHANGE_WINDOW_HOURS,
    MAX_CHANGES_PER_WINDOW,
)
from core.capability.metadata import EvidenceType, SideEffectLevel
from core.capability.registered import capability_marker
from core.capability.result import CapabilityErrorClass
from platform.changes.correlation import ComponentMap, ResourceView
from platform.changes.models import Change, ChangeWindow
from platform.changes.service import ChangeAnswer, ChangeInquiry

pytestmark = pytest.mark.contract


#: The capability windows back from the real clock, because it answers "what
#: changed before this broke" and "this" is happening now. The fixture change is
#: therefore placed relative to that clock rather than at a fixed instant: a
#: pinned date would age out of every window and the suite would pass until it
#: silently stopped exercising anything.
def _now() -> datetime:
    """Return the instant the fixtures are placed against."""
    return datetime.now(UTC)


MONITORED = ResourceView(
    resource_id="res-aaa",
    correlation_key="hal9000/lxc/115",
    display_name="mon-prometheus",
    zone="infra-zone",
)


@dataclass(slots=True)
class RecordedSource:
    """A change source answering from a list, with a component map."""

    name: str = "infra_apply"
    answers: tuple[Change, ...] = ()
    managed: dict[str, tuple[str, ...]] = field(default_factory=dict)

    async def changes_in(
        self,
        window: ChangeWindow,
        *,
        limit: int = MAX_CHANGES_PER_WINDOW,
    ) -> Sequence[Change]:
        """Return the recorded changes inside ``window``."""
        return tuple(change for change in self.answers if window.contains(change.instant))[:limit]

    def components(self) -> dict[str, tuple[str, ...]]:
        """Return what this source's components manage."""
        return self.managed


@dataclass(slots=True)
class RecordedAccess:
    """What a composition root binds: an estate lookup and an inquiry."""

    inquiry: ChangeInquiry
    known: dict[str, ResourceView] = field(default_factory=dict)

    async def changes_for(self, resource: str, *, window: ChangeWindow) -> ChangeAnswer | None:
        """Return the answer for ``resource``, or ``None`` when it is not in the estate."""
        view = self.known.get(resource)
        if view is None:
            return None
        return await self.inquiry.about(view, window=window)


def _applied() -> Change:
    return Change(
        change_id="9f2c1ab",
        occurred_at=_now() - timedelta(minutes=20),
        author="erik",
        message="feat(monitoring): raise the scrape interval",
        paths=("services/monitoring/stack/values.yaml",),
        source="infra_apply",
        component="monitoring",
        applied_at=_now() - timedelta(minutes=13),
    )


@pytest.fixture
def bound() -> Iterator[RecordedAccess]:
    """Bind an access with one applied change against the monitored container."""
    access = RecordedAccess(
        inquiry=ChangeInquiry(
            sources=[
                RecordedSource(
                    answers=(_applied(),),
                    managed=dict(
                        ComponentMap(managed={"monitoring": ("hal9000/lxc/115",)}).managed
                    ),
                )
            ]
        ),
        known={"res-aaa": MONITORED, "mon-prometheus": MONITORED},
    )
    previous = binding.bind(access)
    try:
        yield access
    finally:
        binding.restore(previous)


@pytest.fixture
def unbound() -> Iterator[None]:
    """Leave the process with no change source, as a fresh deployment has."""
    previous = binding.bind(None)
    try:
        yield None
    finally:
        binding.restore(previous)


class TestTheDeclaration:
    """What the selector, the approval gate and the console read."""

    def test_the_declaration_is_complete(self) -> None:
        registered = capability_marker(changes_in_window)

        assert registered is not None
        assert registered.metadata.name == CHANGES_TOOL_NAME
        assert registered.metadata.description.strip()
        assert registered.metadata.use_cases
        assert registered.metadata.anti_examples
        assert registered.metadata.evidence_type is EvidenceType.CHANGE

    def test_it_reads_and_never_writes(self) -> None:
        registered = capability_marker(changes_in_window)
        assert registered is not None

        # Sensitive rather than plain read: the result carries what people
        # wrote in commit messages, so masking applies and a trace of it is
        # treated accordingly.
        assert registered.metadata.side_effect_level is SideEffectLevel.READ_SENSITIVE
        assert registered.metadata.side_effect_level.needs_approval is False
        assert registered.metadata.parallel_safe is True

    def test_the_input_schema_is_bounded_and_is_the_shape_the_model_is_given(self) -> None:
        registered = capability_marker(changes_in_window)
        assert registered is not None

        schema = registered.input_schema
        assert schema["type"] == "object"
        assert set(schema["properties"]) == {"resource", "hours"}
        assert schema["properties"]["hours"]["type"] in {"number", "integer"}

    def test_it_declares_no_integration_because_the_local_source_needs_none(self) -> None:
        # The infra-apply source reads a directory and needs no credential, so
        # gating the tool on a vendor would hide it from the deployment it is
        # most useful to. What is missing is reported at call time instead.
        registered = capability_marker(changes_in_window)
        assert registered is not None

        assert registered.metadata.requires.integrations == ()


class TestWhatComesBack:
    """The rows, the grading, and the two kinds of nothing."""

    @pytest.mark.asyncio
    async def test_a_correlated_change_comes_back_with_its_strength(
        self, bound: RecordedAccess
    ) -> None:
        result = await changes_in_window("res-aaa")

        assert result.succeeded
        rows = result.value["changes"]
        assert [row["change_id"] for row in rows] == ["9f2c1ab"]
        assert rows[0]["strength"] == "manages_resource"
        assert rows[0]["temporal_only"] is False
        assert rows[0]["applied"] is True

    @pytest.mark.asyncio
    async def test_the_evidence_entry_carries_the_change_as_its_citation(
        self, bound: RecordedAccess
    ) -> None:
        result = await changes_in_window("res-aaa")

        assert len(result.evidence) == 1
        assert result.evidence[0].reference == "change:9f2c1ab"
        assert "monitoring" in result.evidence[0].summary

    @pytest.mark.asyncio
    async def test_a_quiet_resource_produces_evidence_rather_than_an_empty_answer(
        self, bound: RecordedAccess
    ) -> None:
        bound.known["res-bbb"] = ResourceView(
            resource_id="res-bbb", correlation_key="hal9000/lxc/120", display_name="fileserver"
        )

        result = await changes_in_window("res-bbb")

        assert result.succeeded
        assert all(row["temporal_only"] for row in result.value["changes"])
        assert "No change touched fileserver" in result.value["statement"]
        # The point of the whole entry: an absence with a provenance is
        # evidence, and an absence without one is silence. It comes first, and
        # it comes even though the window held a change — because the window
        # holding one is exactly when the sentence is needed.
        assert "No change touched fileserver" in result.evidence[0].summary
        assert "infra_apply" in result.evidence[0].summary

    @pytest.mark.asyncio
    async def test_a_deployment_with_no_change_source_says_so_rather_than_saying_nothing(
        self, unbound: None
    ) -> None:
        result = await changes_in_window("res-aaa")

        assert not result.succeeded
        assert result.error is not None
        assert result.error.classification is CapabilityErrorClass.UNAVAILABLE

    @pytest.mark.asyncio
    async def test_a_resource_this_estate_does_not_hold_is_named_rather_than_answered(
        self, bound: RecordedAccess
    ) -> None:
        result = await changes_in_window("res-nothing")

        assert not result.succeeded
        assert result.error is not None
        assert "res-nothing" in result.error.message + (result.error.detail or "")


class TestTheWindow:
    """The bound, applied where the argument arrives rather than at a source."""

    @pytest.mark.asyncio
    async def test_the_default_window_is_the_named_constant(self, bound: RecordedAccess) -> None:
        result = await changes_in_window("res-aaa")

        assert result.value["window"]["hours"] == pytest.approx(DEFAULT_CHANGE_WINDOW_HOURS)

    @pytest.mark.asyncio
    async def test_a_window_past_the_ceiling_is_refused_as_a_classified_failure(
        self, bound: RecordedAccess
    ) -> None:
        # Refused rather than clamped: a query silently narrowed returns a
        # shorter history than the caller believes it has, and the negative
        # built on it is then wrong in the direction that matters.
        result = await changes_in_window("res-aaa", hours=MAX_CHANGE_WINDOW_HOURS + 1)

        assert not result.succeeded
        assert result.error is not None
        assert result.error.classification is CapabilityErrorClass.INVALID_ARGUMENTS

    @pytest.mark.asyncio
    async def test_a_change_outside_the_window_is_not_in_the_answer(
        self, bound: RecordedAccess
    ) -> None:
        result = await changes_in_window("res-aaa", hours=0.1)

        assert result.succeeded
        assert result.value["changes"] == []


@pytest.mark.asyncio
async def test_a_failure_comes_back_classified_rather_than_raised(unbound: None) -> None:
    registered = capability_marker(changes_in_window)
    assert registered is not None

    result = await registered.invoke({})

    assert not result.succeeded
    assert result.error is not None
