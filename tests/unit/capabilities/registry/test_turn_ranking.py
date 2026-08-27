"""Choosing the bounded set again before every turn, from what the run has learned.

Measured on a staging run, out of that run's own selection rationale::

    ranked 76, offered 40, cut by the ceiling 20

Selection ran once, before the first model call, and the toolset was then fixed
for the whole investigation. So those twenty capabilities were not missing from
one turn — they were unreachable for the entire run, and nothing the model
observed or said could bring one of them back. An investigation that reads a
saturating node and concludes it needs the backup catalogue has no way to reach
it.

The cap is not what was wrong. Article II clause 3 bounds *a turn's payload*,
which is a statement about what is sent to a model, not about what a run may
ever reach. The implementation had turned it into the second. So the ceiling
stays exactly where it is and applies to every turn, and what changes is that
*which* capabilities fill it is decided again each time.

Three properties hold across that re-decision, and each has a test here:

- what the run learned reaches the ranking, or re-ranking is a synonym for
  ranking the same thing twice;
- the reserve for cheap, vendor-free reasoning survives every turn rather than
  only the first, because an investigation going badly is exactly the one whose
  later turns are flooded by one well-integrated vendor;
- a capability the model is mid-way through using does not vanish underneath
  it, because a toolset that reshuffles every turn is a different failure from
  the one being fixed.
"""

from __future__ import annotations

import pytest

from capabilities.registry.catalogue import ResolvedCatalogue
from capabilities.registry.planning import TurnCatalogueSelector, TurnProgress
from capabilities.registry.scoring import Incident
from core.capability.metadata import (
    EvidenceType,
    Requirements,
    SideEffectLevel,
    ToolMetadata,
)
from core.capability.registered import RegisteredTool

pytestmark = pytest.mark.unit


def _tool(
    name: str,
    *,
    source: str = "datadog",
    tags: tuple[str, ...] = (),
    use_cases: tuple[str, ...] = (),
) -> RegisteredTool:
    """Return a throwaway tool declaring exactly what a test wants ranked."""
    return RegisteredTool(
        metadata=ToolMetadata(
            name=name,
            display_name=name,
            description="Reads something and reports what it read.",
            tags=tags,
            use_cases=use_cases,
            requires=Requirements(),
            evidence_source=source,
            evidence_type=EvidenceType.LOG,
            side_effect_level=SideEffectLevel.READ,
            parallel_safe=True,
        ),
        input_schema={"type": "object", "properties": {}},
        output_schema={"type": "object", "properties": {}},
        call=lambda: None,
        source_module="capabilities.tools.example",
        source_qualname=name,
    )


#: A tool about the vendor the alert came from, and one about a vendor nothing
#: in the opening alert mentions. Which of the two a turn is offered is the
#: whole question this file asks.
ALERTING = _tool(
    "alertmanager_incident_statistics",
    source="alertmanager",
    tags=("alertmanager", "alert"),
    use_cases=("count how many alerts fired in a window",),
)
BACKUPS = _tool(
    "proxmox_backup_failures",
    source="proxmox",
    tags=("proxmox", "backup"),
    use_cases=("list the backup jobs that failed on a node",),
)

#: Cheap, vendor-free, and useful on any incident. ``memory`` is one of the
#: evidence sources the reserve is defined over.
REASONING = _tool("recall_similar_incidents", source="memory", tags=("memory",))

#: Declares nothing either turn's signals name, so it scores zero throughout.
#: Whatever puts it in a payload is not the ranking.
FILLER = _tool("datadog_unrelated_read", source="datadog")


def _selector(*tools: RegisteredTool, cap: int, reserved: int = 0) -> TurnCatalogueSelector:
    """Return a selector over ``tools`` for an alert Alertmanager reported."""
    return TurnCatalogueSelector(
        catalogue=ResolvedCatalogue(tools=tools),
        opening=Incident(
            alert_source="alertmanager",
            summary="alertmanager reported that something fired",
            tags=("alertmanager",),
        ),
        max_schemas=cap,
        reserved=reserved,
    )


def _names(selector: TurnCatalogueSelector, progress: TurnProgress) -> tuple[str, ...]:
    """Return the tool names one turn would be offered."""
    return tuple(found.name for found in selector.for_turn(progress).tools)


def test_the_opening_turn_ranks_on_the_alert_and_nothing_else() -> None:
    """With nothing learned yet, the first turn is the selection that shipped.

    Stated as a test rather than assumed, because the change here has to be
    additive: a run whose first turn started ranking differently would move
    every trajectory comparison in the evaluation suite for a reason that has
    nothing to do with the loop.
    """
    selector = _selector(ALERTING, BACKUPS, cap=1)

    assert _names(selector, TurnProgress()) == (ALERTING.name,), (
        "the opening turn no longer spends its one slot on the vendor that reported "
        "the alert, which is what it did before per-turn ranking existed."
    )


def test_what_the_run_learned_changes_which_capabilities_the_next_turn_carries() -> None:
    """The model saying what it needs is what makes the twenty reachable.

    This is the defect, at its smallest: one slot, two capabilities, and a run
    that has established the incident is about Proxmox backups. Ranked once
    against the opening alert the slot goes to Alertmanager for all twenty
    iterations; ranked again against what the run knows, it goes where the
    investigation actually is.
    """
    selector = _selector(ALERTING, BACKUPS, cap=1)

    learned = TurnProgress(
        learned=("the failing job is a proxmox backup on node pve01, not an alert storm",)
    )

    assert _names(selector, learned) == (BACKUPS.name,), (
        "the turn was offered the same capability the opening alert chose, after the "
        "run had established the incident is a Proxmox backup failure. Ranking that "
        "cannot read what the run learned re-ranks nothing."
    )


def test_a_capability_the_model_is_mid_way_through_using_keeps_its_slot() -> None:
    """Re-ranking must not pull a tool out from under a call in progress.

    The failure this guards against is subtle and would read as a model defect:
    a turn calls a capability, the next turn's ranking drops it, and the model's
    follow-up call comes back "unknown capability" for a tool it was holding one
    turn ago.

    The capability in flight is the one that scores *nothing* against this
    turn's signals, and there is room for two out of three. So the ranking on
    its own would have dropped it, and its surviving is the pin and not a
    coincidence — while the second slot still goes where the run has moved.
    """
    selector = _selector(ALERTING, BACKUPS, FILLER, cap=2)

    learned = ("the failing job is a proxmox backup on node pve01, not an alert storm",)
    unpinned = _names(selector, TurnProgress(learned=learned))
    assert FILLER.name not in unpinned, (
        f"{FILLER.name} earned a slot on its own score, so this case cannot tell a "
        f"pinned capability from a well-ranked one: {unpinned}"
    )

    pinned = _names(selector, TurnProgress(learned=learned, in_flight=(FILLER.name,)))

    assert FILLER.name in pinned, (
        f"{FILLER.name} was called on the previous turn and the next turn's ranking "
        f"dropped it. The model's follow-up call would come back as an unknown "
        f"capability for a tool it was holding one turn ago."
    )
    assert BACKUPS.name in pinned, (
        "pinning what is in flight consumed the whole payload; the point of re-ranking "
        "is that the rest of it still moves."
    )


def test_the_reserve_holds_its_slots_on_every_turn_not_only_the_first() -> None:
    """A vendor that floods the ranking must not crowd out reasoning, ever.

    The reserve existed before this and applied once. A run whose later turns
    are all about one vendor is precisely the run that loses recall exactly when
    it needs it, so the property is asserted against a turn deep in a run rather
    than against the opening one.
    """
    selector = _selector(ALERTING, BACKUPS, REASONING, cap=2, reserved=1)

    deep = TurnProgress(
        learned=("proxmox backup proxmox backup alertmanager alert alertmanager alert",)
    )

    assert REASONING.name in _names(selector, deep), (
        "no vendor-free reasoning capability survived a turn whose signals were all "
        "vendor. The reserve exists so an investigation going badly can still think."
    )


def test_no_turn_carries_more_than_the_cap_it_was_given() -> None:
    """Article II clause 3, restated as the per-turn property it always was.

    The cap is on the payload of a turn. Re-deciding the payload every turn is
    only allowed because the cap is re-applied every turn, so the two halves are
    asserted together: many more capabilities than fit, and every turn still
    inside the bound.
    """
    crowd = tuple(_tool(f"vendor_read_{index}") for index in range(50))
    selector = _selector(*crowd, ALERTING, BACKUPS, cap=8, reserved=2)

    for progress in (
        TurnProgress(),
        TurnProgress(learned=("proxmox backup on pve01",)),
        TurnProgress(learned=("alertmanager alert storm",), in_flight=(ALERTING.name,)),
    ):
        offered = _names(selector, progress)
        assert len(offered) <= 8, (
            f"a turn carried {len(offered)} tool schemas against a cap of 8. The cap is "
            f"on the payload of every turn, not on the first one."
        )
        assert len(set(offered)) == len(offered), f"a turn offered a duplicate: {offered}"


def test_the_turn_reports_what_it_was_offered_and_what_the_ceiling_cut() -> None:
    """Per turn, not per run: the record has to follow the decision.

    An operator asking why a capability was missing is asking about a turn once
    the set changes between turns, and a rationale written once for the run
    would be answering about a payload that no longer exists.
    """
    selector = _selector(ALERTING, BACKUPS, cap=1)

    turn = selector.for_turn(TurnProgress(learned=("proxmox backup on pve01",)))

    offered = {found.name for found in turn.tools}
    cut = {entry.name for entry in turn.cut}
    assert offered == {BACKUPS.name}, offered
    assert cut == {ALERTING.name}, (
        f"the ceiling cut {ALERTING.name} and the turn does not say so: {cut}. "
        f"'These were offered' cannot distinguish a capability that scored badly "
        f"from one that scored well and lost to the ceiling."
    )
    assert {entry.name for entry in turn.ranked} == offered | cut, (
        "the ranking does not account for every capability the turn chose between"
    )
