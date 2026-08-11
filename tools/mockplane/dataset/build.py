"""Assembling the committed scenarios, through the one path the pipeline provides.

Both halves meet here — the records a deployment serves and the records
projected from a direct read of the cluster — and both go through
``anonymise.pipeline.process`` before anything is written. There is no second
route into the fixture tree, and an architecture test says so.

``populated`` is the full deployment mid-operation. ``empty`` is the same
endpoints answering with nothing, which is the only way an empty state gets
reviewed at all. ``first-run`` is a deployment that has been configured and not
finished. ``restricted`` and ``incident-live`` differ from ``populated`` in a
handful of endpoints and hold only those. ``degraded`` holds no files at all —
it is ``populated`` plus a declaration of which endpoints misbehave, which is
exactly what it is. ``scale`` is generated from a seed.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, Final

from integrations._catalogue.gaps import gaps
from tools.mockplane.anonymise.pipeline import ProcessedCapture, process
from tools.mockplane.anonymise.pseudonyms import PseudonymBook
from tools.mockplane.capture.projection import estate, project
from tools.mockplane.dataset import profile, served
from tools.mockplane.dataset.stream import stream_records
from tools.mockplane.endpoints import CONSOLE_ENDPOINTS, endpoint_by_slug
from tools.mockplane.identifiers import IdentifierList
from tools.mockplane.paths import scenario_dir
from tools.mockplane.records import CapturedRecord, Provenance, Request
from tools.mockplane.scenarios import arguments_key, write_fixture

#: The scenarios that hold committed files, and what each one is built from.
BUILT_SCENARIOS: Final[tuple[str, ...]] = (
    "populated",
    "empty",
    "first-run",
    "restricted",
    "incident-live",
)

#: The key the committed dataset is pseudonymised under. The values in
#: ``profile`` and ``served`` are already pseudonyms — the survey they were taken
#: from is not in this repository and never was — so this key salts nothing
#: secret. It is fixed rather than supplied so the committed output is
#: reproducible by anybody, which is what the byte-identical assertion needs.
BUILD_KEY: Final = "committed-fixture-set"


def populated_records() -> tuple[CapturedRecord, ...]:
    """Return every record of the full deployment, both halves, before the pipeline."""
    reading = profile.cluster_reading()
    return (
        *served.served_records(role="owner"),
        *estate(reading),
        *project(reading),
        *stream_records(),
        *_write_responses(),
    )


def empty_records() -> tuple[CapturedRecord, ...]:
    """Return the same endpoints answering with nothing in them.

    Every screen's empty state, in one scenario. The shapes are still the
    contract's shapes: an empty state that answered ``{}`` would be testing the
    console's tolerance of a broken deployment rather than its empty states.
    """
    reading = profile.cluster_reading()
    _ = reading
    now = served.at(minutes=0)
    bodies: Mapping[str, Any] = {
        "principal": {
            "principal_id": served.OPERATOR,
            "display_name": "Avery Lockhart",
            "email": "avery.lockhart@example.invalid",
            "kind": "person",
            "roles": ["owner"],
            "permissions": list(served.OPERATOR_PERMISSIONS),
            "team_node_id": served.ORG_NODE,
            "impersonating": False,
            "impersonated_by": None,
        },
        "runs": {"runs": []},
        "approvals": {"approvals": []},
        "episodes": {"episodes": []},
        "memory-stats": {"episode_count": 0},
        "documents": {"documents": []},
        "config-tree": {"nodes": []},
        "integrations": {"integrations": [], "known_gaps": [gap.to_record() for gap in gaps()]},
        "principals": {"users": []},
        "grants": {"grants": []},
        "tokens": {"tokens": []},
        "audit-events": {"events": [], "total": 0},
        "capabilities": {"tools": [], "skills": []},
        "health": {
            "ready": True,
            "connected": True,
            "store_state": "ready",
            "migrations_current": True,
            "providers_configured": [],
            "reasons": [],
            "recent_shedding": [],
        },
        "estate-summary": {
            "total": 0,
            "captured_at": now,
            "by_kind": {},
            "by_health": {},
            "by_source": {},
            "problems": 0,
            "maintenance": 0,
            "absent": 0,
        },
        "estate-resources": {"resources": []},
        "estate-unresolved-targets": {"targets": []},
        "estate-nodes": {"nodes": []},
        "estate-storage": {"datastores": [], "thin_pools": [], "volumes": []},
        "estate-backups": {"jobs": []},
        "incidents": {"incidents": []},
        "detectors": {"detectors": []},
        "schedules": [],
        "observations": {"observations": []},
    }
    # The seven receivers exist on any deployment, populated or not: they are
    # routes this build serves rather than something an operator filled in. An
    # empty scenario that answered 404 here would be one where the panel telling
    # somebody how to connect their first alert source is the panel that is
    # missing.
    records = [
        CapturedRecord(
            slug=slug,
            arguments={},
            status=200,
            body=body,
            provenance=Provenance.GATEWAY,
            request=Request(method="GET", path=slug),
        )
        for slug, body in bodies.items()
    ]
    records.extend(served.ingress_records())
    # The pipeline declaration is what the build *is* rather than what a
    # deployment configured, so it answers the same thing in an empty scenario
    # as in a full one. Answering 404 here would say this deployment has no
    # investigation in it, which is not what an empty deployment means.
    records.extend(record for record in served.agent_records() if record.slug == "agent-pipeline")
    # And the role catalogue, for the same reason: which roles exist is what the
    # build declares, not something an operator filled in.
    records.extend(served.role_records())
    # Seven configured routes and seven silences: the state the ingress
    # column exists for, in the scenario a first day actually looks like.
    records.extend(served.empty_transit_records())
    records.extend(_absent_detail_records())
    records.extend(_write_responses())
    # Nothing stored, nothing verified: the nine providers are still all nine,
    # because they are what this build supports rather than what this deployment
    # has done. The checklist says so in the platform's own vocabulary.
    records.extend(served.provider_records())
    records.append(served.checklist_record())
    return tuple(records)


def first_run_records() -> tuple[CapturedRecord, ...]:
    """Return a deployment that has been configured and is not finished.

    The setup checklist is the screen this exists for: the organisation node
    exists, nothing is connected, no provider is configured, and readiness says
    so in words a person can act on.
    """
    records = list(empty_records())
    replacements: Mapping[str, Any] = {
        "config-tree": {"nodes": [dict(served.CONFIG_NODES[0])]},
        "health": {
            "ready": False,
            "connected": True,
            "store_state": "ready",
            "migrations_current": True,
            "providers_configured": [],
            "reasons": [
                "no model provider is configured",
                "no integration holds a credential",
                "no principal other than the first operator exists",
            ],
            "recent_shedding": [],
        },
        "principals": {"users": [dict(served.USERS[0])]},
        "grants": {"grants": [dict(served.GRANTS[0])]},
        "integrations": {
            "known_gaps": [gap.to_record() for gap in gaps()],
            "integrations": [
                {
                    "name": "metrics-store",
                    "category": "observability",
                    "summary": "Range queries against the metrics store.",
                    "health": "unconfigured",
                    "health_detail": "no credential is stored anywhere in this deployment",
                    "hosts": ["metrics.example.invalid"],
                    "regions": [],
                    "capabilities": ["metrics.range_query"],
                    "required_credentials": ["api_token"],
                    "required_permissions": ["metrics:read"],
                    "parity": "full",
                    "missing_artefacts": [],
                }
            ],
        },
        # Declared and holding nothing, which is a different fact from not being
        # declared at all — and the one the integrations step of the guided run
        # is drawn against.
        "setup-checklist": served.checklist_record(
            integrations=(("metrics-store", "absent"),)
        ).body,
    }
    return tuple(
        record.with_body(replacements[record.slug]) if record.slug in replacements else record
        for record in records
    )


def restricted_records() -> tuple[CapturedRecord, ...]:
    """Return the one endpoint that differs when a viewer is looking.

    The rest of the scenario is ``populated``: it is the same deployment, and
    the point of the role matrix is that the data does not change while what may
    be done with it does.
    """
    return tuple(
        record for record in served.identity_records(role="viewer") if record.slug == "principal"
    )


def incident_live_records() -> tuple[CapturedRecord, ...]:
    """Return the run in flight, and the long stream the live layer is proved against."""
    return stream_records(long=True)


def _absent_detail_records() -> tuple[CapturedRecord, ...]:
    """Return a 404 for every templated read, for a scenario that holds nothing.

    Answering 200 with an empty object would be a deployment claiming a run
    exists and has no fields, which no real one does.
    """
    detail_slugs = (
        "run-detail",
        "run-replay",
        "run-threads",
        "interactions",
        "approval-detail",
        "topology",
        "document-detail",
        "config-effective",
        "config-catalogue",
        "config-fields",
        "autonomy-policy",
        "autonomy-bounds",
        "autonomy-outlook",
        "autonomy-preview",
        "config-integration-schemas",
        "estate-resource-detail",
        "incident-detail",
        # The stream too: there is no run to watch, and a stream that opened and
        # emitted nothing would look like a live run that had gone quiet.
        "run-stream",
    )
    return tuple(
        CapturedRecord(
            slug=slug,
            arguments={},
            status=404,
            body={"detail": "there is nothing here yet"},
            provenance=Provenance.GATEWAY,
            request=Request(method="GET", path=slug),
        )
        for slug in detail_slugs
    )


def _write_responses() -> tuple[CapturedRecord, ...]:
    """Return what each write answers with.

    Recorded rather than captured: a capture that posted an investigation to
    somebody's deployment would be a capture that changed the thing it was
    measuring, so the write half of the contract is written against the
    document instead.
    """
    started = {
        "run_id": "run-0007",
        "status": "running",
        "trigger": "console",
        "started_at": served.at(minutes=0),
        "finished_at": None,
        "summary": None,
    }
    cancelled = {
        "run_id": "run-0003",
        "status": "cancelling",
        "trigger": "alert",
        "started_at": served.at(minutes=4),
        "finished_at": None,
        "summary": "Cancellation was requested; it stops at the next safe point.",
    }
    answered = {
        "interaction_id": "int-0001",
        "run_id": "run-0003",
        "kind": "question",
        "text": "The hardening unit failed at boot. Should the investigation read the "
        "boot journal as well?",
        "options": ["yes", "no"],
        "is_open": False,
        "reason": "answered",
    }
    approved = {
        "interaction_id": "int-0002",
        "run_id": "run-0005",
        "kind": "approval",
        "text": "Enable the disabled backup job covering the primary's guests.",
        "options": [],
        "is_open": False,
        "reason": "approved",
    }
    rejected = {**approved, "reason": "rejected"}
    effective = {
        "node_id": "env-production",
        "values": {
            "investigation.max_loops": 16,
            "investigation.reasoning_effort": "high",
            "approval.required_above": "read",
            "retention.audit_days": 365,
        },
        "provenance": {
            "investigation.max_loops": "env-production",
            "investigation.reasoning_effort": "env-production",
            "approval.required_above": served.ORG_NODE,
            "retention.audit_days": served.ORG_NODE,
        },
    }
    preview = {
        **effective,
        "changes": [
            {"path": "investigation.max_loops", "before": 12, "after": 16},
            {"path": "investigation.reasoning_effort", "before": "medium", "after": "high"},
        ],
        "requires_approval": True,
        "approval_gated": ["investigation.max_loops"],
        "locked": {"approval.required_above": served.ORG_NODE},
    }
    issued = {
        "token": {
            "token_id": "tok-0003",
            "name": "reporting",
            "user_id": served.OPERATOR,
            "team_node_id": served.ORG_NODE,
            "scopes": ["investigation.read"],
            "created_at": served.at(minutes=0),
            "expires_at": None,
            "last_used_at": None,
            "revoked": False,
            "description": None,
        },
        "secret": "[removed]",
    }

    # What the deployment answers when a rule is simulated, and when a failed
    # report is sent again. Both are writes only in the HTTP sense — the
    # simulation stores nothing, which is the property it exists to have.
    simulated = {
        "rule_id": "critical-to-platform",
        "action": "investigate",
        "team": served.PLATFORM_TEAM_NODE,
        "reason": "",
        "signals": {
            "source": "alertmanager",
            "zone": "apps",
            "criticality": "critical",
            "resource_id": "proxmox:container/hal9000/110",
        },
    }
    resent = {
        "delivery_id": "chat-incidents:concluded:2",
        "direction": "outbound",
        "source": "chat-incidents",
        "occurred_at": served.at(minutes=0),
        "outcome": "delivered",
        "reason": "",
        "matched_rule": "",
        "team_node_id": served.PLATFORM_TEAM_NODE,
        "resource_id": "",
        "run_id": "",
        "incident_id": "",
        "event_type": "investigation_concluded",
        "attempt": 2,
        "detail": {"channel": "slack", "detail_level": "summary_with_link"},
    }

    written: tuple[tuple[str, int, Any], ...] = (
        ("transit-simulate", 200, simulated),
        ("transit-resend", 200, resent),
        ("investigation-start", 202, started),
        ("investigation-message", 202, {"queued": True, "run_id": "run-0003"}),
        ("investigation-cancel", 200, cancelled),
        ("interaction-answer", 200, answered),
        ("interaction-approve", 200, approved),
        ("interaction-reject", 200, rejected),
        (
            "approval-rollback",
            200,
            {
                "plan_id": "plan-0001",
                "approval_id": "apr-0001",
                "executed_at": served.at(minutes=0),
                "completed_steps": [1],
            },
        ),
        # The three writes the guided first run makes. The credential response
        # has no field a value could sit in, which is the shape the gateway's own
        # view enforces — a fixture with one would be a fixture teaching the
        # console to read something that never arrives.
        (
            "credential-write",
            200,
            {
                "integration": "metrics-store",
                "state": "usable",
                "usable": True,
                "version": 1,
                "fields": ["api_token"],
            },
        ),
        (
            "integration-verify",
            200,
            {"integration": "metrics-store", "state": "usable", "usable": True},
        ),
        (
            "provider-verify",
            200,
            {
                "provider_id": "anthropic",
                "verified": True,
                "model_id": "claude-sonnet-5",
                "detail": "a live request called a tool and returned structure",
                "remedy": "",
                "alternatives": [],
            },
        ),
        ("config-write", 200, effective),
        ("config-preview", 200, preview),
        ("token-create", 201, issued),
        ("token-revoke", 200, {"revoked": 1, "token_ids": ["tok-0002"]}),
    )
    return tuple(
        CapturedRecord(
            slug=slug,
            arguments={},
            status=status,
            body=body,
            provenance=Provenance.GATEWAY,
            request=Request(method=endpoint_by_slug(slug).method, path=slug),
        )
        for slug, status, body in written
    )


def records_for(scenario: str) -> tuple[CapturedRecord, ...]:
    """Return the records one built scenario holds of its own.

    Raises:
        KeyError: the scenario is not one this module builds.
    """
    builders = {
        "populated": populated_records,
        "empty": empty_records,
        "first-run": first_run_records,
        "restricted": restricted_records,
        "incident-live": incident_live_records,
    }
    return builders[scenario]()


def processed_for(scenario: str, identifiers: IdentifierList | None = None) -> ProcessedCapture:
    """Return one scenario's records after the pipeline, which is the only way in."""
    return process(
        records_for(scenario),
        book=PseudonymBook(key=BUILD_KEY.encode(), already_pseudonymous=True),
        identifiers=identifiers if identifiers is not None else IdentifierList.empty(),
        captured_at=datetime.fromisoformat(profile.CAPTURED_AT),
    )


def write_scenario(
    scenario: str,
    root: Path | None = None,
    identifiers: IdentifierList | None = None,
) -> tuple[Path, ...]:
    """Write one scenario's fixture files and return the paths written."""
    processed = processed_for(scenario, identifiers)
    grouped: dict[str, list[CapturedRecord]] = {}
    for record in processed.records:
        grouped.setdefault(record.slug, []).append(record)

    directory = scenario_dir(scenario, root)
    written: list[Path] = []
    for slug, records in sorted(grouped.items()):
        ordered = sorted(records, key=lambda record: arguments_key(record.arguments))
        path = directory / f"{slug}.json"
        write_fixture(path, slug, ordered)
        written.append(path)

    for stale in sorted(directory.glob("*.json")):
        if stale not in written:
            stale.unlink()
    return tuple(written)


def write_all(
    root: Path | None = None,
    identifiers: IdentifierList | None = None,
    scenarios: Sequence[str] = BUILT_SCENARIOS,
) -> tuple[Path, ...]:
    """Write every committed scenario and return every path written."""
    written: list[Path] = []
    for scenario in scenarios:
        written.extend(write_scenario(scenario, root, identifiers))
    return tuple(written)


def covered_slugs() -> frozenset[str]:
    """Return the endpoints ``populated`` answers, for the coverage report."""
    return frozenset(record.slug for record in populated_records())


def uncovered_slugs() -> tuple[str, ...]:
    """Return the console-consumed endpoints nothing in ``populated`` answers."""
    covered = covered_slugs()
    return tuple(endpoint.slug for endpoint in CONSOLE_ENDPOINTS if endpoint.slug not in covered)


__all__ = [
    "BUILD_KEY",
    "BUILT_SCENARIOS",
    "covered_slugs",
    "empty_records",
    "first_run_records",
    "incident_live_records",
    "populated_records",
    "processed_for",
    "records_for",
    "restricted_records",
    "uncovered_slugs",
    "write_all",
    "write_scenario",
]
