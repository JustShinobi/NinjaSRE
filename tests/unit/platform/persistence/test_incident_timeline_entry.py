"""The shape a timeline entry needs before a screen can draw an evidence step.

A conclusion without the query and result behind it is a hypothesis, not a
diagnosis (Article I) — so ``TimelineEntry``, the persistence port's own
record of one thing that happened to an incident, has to carry the query an
evidence step actually ran and the result it actually returned, alongside
the conclusion every entry already carries. This is the port's own shape,
proved without a database; the wire-level half of the same claim — whether
the console's response model can carry them too — belongs to a later phase
of the feature that grew this field.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from platform.persistence.ports.incident_store import TimelineEntry, TimelineKind

pytestmark = pytest.mark.unit

AT = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)


def test_an_evidence_entry_carries_the_query_it_ran_and_the_result_it_got() -> None:
    entry = TimelineEntry(
        entry_id="inc-1@evidence@2026-08-20T12:00:00+00:00",
        incident_id="inc-1",
        kind=TimelineKind.EVIDENCE,
        at=AT,
        cause="the primary datastore is at 95% and climbing",
        query='node_filesystem_avail_bytes{mountpoint="/data"}',
        result="12.4 GiB free of 250 GiB, falling ~1.8 GiB/hour",
    )

    assert entry.query == 'node_filesystem_avail_bytes{mountpoint="/data"}'
    assert entry.result == "12.4 GiB free of 250 GiB, falling ~1.8 GiB/hour"


def test_query_and_result_are_asserted_separately_one_without_the_other_is_not_enough() -> None:
    """The claim is that BOTH survive. An entry with a query and no result — or
    the reverse — must fail this claim rather than pass it by accident.
    """
    query_only = TimelineEntry(
        entry_id="inc-1@evidence@1",
        incident_id="inc-1",
        kind=TimelineKind.EVIDENCE,
        at=AT,
        query='up{instance="cedar"}',
    )
    assert query_only.query == 'up{instance="cedar"}'
    assert query_only.result == "", "a query alone must not be mistaken for a carried result"

    result_only = TimelineEntry(
        entry_id="inc-1@evidence@2",
        incident_id="inc-1",
        kind=TimelineKind.EVIDENCE,
        at=AT,
        result="0 (last seen 1 six minutes ago)",
    )
    assert result_only.result == "0 (last seen 1 six minutes ago)"
    assert result_only.query == "", "a result alone must not be mistaken for a carried query"


def test_query_and_result_default_to_empty_for_a_lifecycle_entry() -> None:
    """Every entry that is not evidence still has somewhere to carry them —
    it simply carries nothing, the same as ``cause`` and ``detail`` do.
    """
    entry = TimelineEntry(
        entry_id="inc-1@opened@2026-08-20T12:00:00+00:00",
        incident_id="inc-1",
        kind=TimelineKind.OPENED,
        at=AT,
        cause="the primary datastore is at 95% and climbing",
    )

    assert entry.query == ""
    assert entry.result == ""


def test_the_five_reasoning_kinds_sit_beside_the_ten_lifecycle_kinds_on_one_enum() -> None:
    """The claim is the *set* of kinds, not that a handful of them exist.

    A second, parallel vocabulary for "investigation steps" would be a second
    source of truth for the same incident's history — the wave this feature
    belongs to exists to remove exactly that shape of duplication. Proving it
    is one enum means proving the union of the two groups is the *whole*
    enum: nothing dropped from the ten, nothing beyond the five added.
    """
    lifecycle = {
        TimelineKind.OPENED,
        TimelineKind.CORRELATED,
        TimelineKind.SUBJECT_ADDED,
        TimelineKind.SUBJECT_ABSENT,
        TimelineKind.STATE_CHANGED,
        TimelineKind.RUN_STARTED,
        TimelineKind.ACTION_TAKEN,
        TimelineKind.ESCALATED,
        TimelineKind.SUPPRESSED,
        TimelineKind.CLOSED,
    }
    reasoning = {
        TimelineKind.ALERT_RECEIVED,
        TimelineKind.HYPOTHESES_DRAWN,
        TimelineKind.EVIDENCE,
        TimelineKind.DIAGNOSIS,
        TimelineKind.REPORT_DELIVERED,
    }

    assert lifecycle | reasoning == set(TimelineKind), (
        "the ten lifecycle kinds and the five reasoning kinds must be exactly "
        "the whole of TimelineKind — neither a dropped member nor a stray one"
    )
    assert {kind.value for kind in reasoning} == {
        "alert_received",
        "hypotheses_drawn",
        "evidence",
        "diagnosis",
        "report_delivered",
    }, "the wire spelling of the five reasoning kinds is fixed and not a free choice"


__all__: list[str] = []
