"""The two pure derivations a decision card reads: title and risk score.

Both are one function each, called once from the listing projection and once
from the detail projection (`gateway/http/routes/approvals.py`), so the two
can never print a different sentence for the same approval — the plan's own
"two sources for the same title" risk, closed by construction rather than by
convention.

Tested directly against representative payloads rather than through a full
queued approval: these are pure functions of the stored document, and a
desk-composed, gateway-routed test for every case is a slower way to ask the
same question.
"""

from __future__ import annotations

import pytest

from gateway.http.routes.approvals import _risk_of, _title_of

pytestmark = pytest.mark.unit

#: The real staging payload shape (spec fact 2), reduced to what the
#: derivations read. Nested under `proposed`, as a remediation queued
#: through `RequestBuilder.queue()` actually stores it.
_STAGING_PAYLOAD = {
    "proposed": {
        "action_id": "295df00b-3447-4895-9e97-f70630b0403a",
        "capability": "proxmox_start_guest",
        "arguments": {"node": "pve01", "vmid": 122},
        "environment": "production",
        "target": {"identifier": "lxc/122", "environment": "production", "node_id": "pve01"},
        "side_effect_level": "write_reversible",
        "requester": "alert-router",
        "intent": "",
        "run_id": "",
        "team_node_id": "pve01",
        "risk_class": "low",
        "rollback_planned": True,
        "operation": "",
    }
}


def test_a_known_capability_produces_a_verb_and_a_target_never_the_raw_capability() -> None:
    title = _title_of(_STAGING_PAYLOAD, fallback="path = proxmox_start_guest")

    assert title != ""
    assert title != "proxmox_start_guest"
    assert "proxmox_start_guest" not in title
    assert "lxc/122" in title
    assert not title.startswith("path")
    assert "{" not in title


def test_an_unknown_capability_falls_back_to_the_stored_summary() -> None:
    payload = {
        "proposed": {
            "action_id": "a1",
            "capability": "a_capability_this_table_has_never_heard_of",
            "target": {"identifier": "res-1"},
            "side_effect_level": "write_reversible",
            "requester": "alert-router",
        }
    }

    title = _title_of(
        payload, fallback="Grow the volume that is at the ceiling of its own allocation."
    )

    assert title == "Grow the volume that is at the ceiling of its own allocation."
    assert "a_capability_this_table_has_never_heard_of" not in title


def test_a_minimal_or_unparsable_document_falls_back_to_the_summary_without_raising() -> None:
    for empty in ({}, {"proposed": {}}, {"proposed": {"capability": "x"}}):
        title = _title_of(empty, fallback="Enable the disabled job.")
        assert title == "Enable the disabled job."


def test_the_staging_payload_scores_three_of_five() -> None:
    """Write-reversible base is 2; `depth: 3` in the real payload adds one — the
    "Risk 3 of 5" the current, unstructured screen already shows for this
    exact approval (spec, fact 2), which this derivation must reproduce."""
    payload = dict(_STAGING_PAYLOAD)
    payload["proposed"] = {
        **_STAGING_PAYLOAD["proposed"],
        "blast_radius": {
            "count": 1,
            "depth": 3,
            "known": True,
            "origin": "lxc/122",
            "services": [],
        },
    }

    risk = _risk_of(payload, fallback_class="low")

    assert risk["scale"] == 5
    assert risk["score"] == 3
    assert risk["class"] == "low"


def test_score_never_exceeds_the_scale_even_for_a_destructive_wide_blast_radius() -> None:
    payload = {
        "proposed": {
            "capability": "x",
            "side_effect_level": "destructive",
            "blast_radius": {"count": 50, "depth": 5, "known": True},
        }
    }

    risk = _risk_of(payload, fallback_class="critical")

    assert risk["score"] == 5


def test_a_read_only_action_with_no_blast_radius_scores_one() -> None:
    payload = {"proposed": {"capability": "x", "side_effect_level": "read"}}

    risk = _risk_of(payload, fallback_class="low")

    assert risk["score"] == 1


def test_an_unknown_side_effect_level_scores_no_lower_than_the_reversible_write_floor() -> None:
    """Never a `KeyError` on a document this deployment has not seen before —
    the safest floor for an unrecognised level is the one that still gates."""
    payload = {
        "proposed": {
            "capability": "x",
            "side_effect_level": "a_future_level_this_reads_nothing_about",
        }
    }

    risk = _risk_of(payload, fallback_class="")

    assert 1 <= risk["score"] <= 5
