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

from config.constants.first_run import SETUP_READINESS_CONFIGURED, SETUP_READINESS_VERIFIED
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


#: The Gemini models the curated listing endpoint offers on this deployment —
#: including the generation the static onboarding list has never heard of,
#: which is the whole point of the endpoint existing (feature 010's own
#: motivating defect). A handful, not the full curated set: the fixture proves
#: the mechanism (a name the static list does not carry, reached through the
#: dynamic route) rather than duplicating the curation unit tests' own fixture.
_GEMINI_MODELS_OFFERED: Final[tuple[tuple[str, str], ...]] = (
    ("gemini-pro-latest", "Gemini Pro (Latest)"),
    ("gemini-flash-latest", "Gemini Flash (Latest)"),
    ("gemini-2.5-pro", "Gemini 2.5 Pro"),
    ("gemini-2.5-flash", "Gemini 2.5 Flash"),
    ("gemini-3.6-flash", "Gemini 3.6 Flash"),
    ("gemini-3.7-flash", "Gemini 3.7 Flash"),
)


def _gemini_models_record() -> CapturedRecord:
    """Return the curated listing `GET /v1/providers/google_gemini/models` serves.

    A provider-specific override, layered over no catch-all — this endpoint
    has no scenario-independent default, because "what a provider currently
    lists" is not a fact any provider shares with another.
    """
    return CapturedRecord(
        slug="provider-models",
        arguments={"provider_id": "google_gemini"},
        status=200,
        body={
            "provider_id": "google_gemini",
            "models": [
                {"model_id": model_id, "display_name": display_name}
                for model_id, display_name in _GEMINI_MODELS_OFFERED
            ],
            "source": "endpoint",
            "reason": "",
        },
        provenance=Provenance.GATEWAY,
        request=Request(method="GET", path="provider-models"),
    )


def _gemini_verify_record() -> CapturedRecord:
    """Return what `POST /v1/providers/google_gemini/verify` answers: degraded, not failing.

    The scenario this whole feature exists to close: tool calling reads
    degraded — this build's registry declares no tool support for the
    configured model — and every other check passed, so the verdict is
    satisfied rather than refused. Mirrored by the checks array rather than
    collapsed into the boolean, which is what a screen built against this
    fixture has to prove it does.
    """
    return CapturedRecord(
        slug="provider-verify",
        arguments={"provider_id": "google_gemini"},
        status=200,
        body={
            "provider_id": "google_gemini",
            "verified": True,
            "model_id": "gemini-2.5-flash",
            "detail": (
                "gemini-2.5-flash on google_gemini calls tools and returns structure "
                "(tool calling is degraded — this build's registry declares no tool "
                "support for this model, so it was not exercised; investigations may "
                "stall on it)"
            ),
            "remedy": "",
            "alternatives": [],
            "checks": [
                {
                    "name": "credentials",
                    "status": "passed",
                    "detail": "present: api_key",
                    "duration_ms": 1.0,
                },
                {"name": "authentication", "status": "passed", "detail": "", "duration_ms": 210.0},
                {
                    "name": "tool calling",
                    "status": "degraded",
                    "detail": "model declares no tool support",
                    "duration_ms": 0.0,
                },
                {
                    "name": "structured output",
                    "status": "passed",
                    "detail": "via native",
                    "duration_ms": 340.0,
                },
                {
                    "name": "streaming",
                    "status": "passed",
                    "detail": "298 characters",
                    "duration_ms": 260.0,
                },
            ],
        },
        provenance=Provenance.GATEWAY,
        request=Request(method="POST", path="provider-verify"),
    )


def _with_investigator_on_gemini(record: CapturedRecord) -> CapturedRecord:
    """Return `record` with the investigator role pointed at the degraded Gemini model.

    A targeted overlay on the organisation root's own effective-configuration
    record, not a replacement of it: every other field (`investigation.*`,
    `approval.*`, `agents`, `capabilities`, and their provenance) carries over
    unchanged, and only the two paths this feature is about — the investigator's
    provider and model — move from the dataset's shared default (`anthropic`)
    to the provider `_gemini_verify_record` reports as degraded, so the two
    stay coherent: an operator opening Models & providers sees the same model
    the verify endpoint is about to grade.
    """
    body = dict(record.body)
    values = dict(body.get("values", {}))
    values["models"] = {
        "investigator": {"provider": "google_gemini", "model": "gemini-2.5-flash"},
    }
    body["values"] = values
    provenance = dict(body.get("provenance", {}))
    provenance["models.investigator.provider"] = str(record.body.get("node_id", ""))
    provenance["models.investigator.model"] = str(record.body.get("node_id", ""))
    body["provenance"] = provenance
    return record.with_body(body)


def populated_records() -> tuple[CapturedRecord, ...]:
    """Return every record of the full deployment, both halves, before the pipeline."""
    reading = profile.cluster_reading()
    base = served.served_records(role="owner")
    # The organisation root's own effective configuration, overlaid rather than
    # duplicated: `served.config_records()` already emits exactly one record
    # for this `(slug, node_id)` pair, and a second one under the same key
    # would leave which one a reader actually gets to depend on list order
    # nobody declared.
    records = [
        _with_investigator_on_gemini(record)
        if record.slug == "config-effective" and record.arguments.get("node_id") == served.ORG_NODE
        else record
        for record in base
        # The base listing and per-provider detail (`anthropic` alone
        # configured and verified) are replaced below, whole, by the same
        # helper `first_run_records` already uses for the same reason: a
        # provider's `configured`/`verified` pair is a fact of the listing
        # record, not of the investigator's own selection, and the two have
        # to agree — the state card reads both.
        if record.slug not in ("providers", "provider-detail")
    ]
    # Anthropic keeps its prior state; Google Gemini gains a credential that
    # has answered before — the persisted, boolean fact a page load reads
    # without spending a token. `_gemini_verify_record` is the token-costing
    # detail behind "Check again": a live check that still finds tool calling
    # degraded, on the same model this configuration now names.
    records.extend(
        served.provider_records(
            configured=("anthropic", "google_gemini"),
            verified=("anthropic", "google_gemini"),
        )
    )
    return (
        *records,
        *estate(reading),
        *project(reading),
        *stream_records(),
        *_write_responses(),
        _gemini_models_record(),
        _gemini_verify_record(),
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
            # Read off `USERS[0]` (the same operator) rather than repeated as a
            # literal, so this can never drift from the real `PrincipalKind`
            # the backend declares (`platform/persistence/ports/identity_repository.py`).
            "kind": served.USERS[0]["kind"],
            "roles": ["owner"],
            "permissions": list(served.OPERATOR_PERMISSIONS),
            "team_node_id": served.ORG_NODE,
            "impersonating": False,
            "impersonated_by": None,
        },
        "runs": {"runs": []},
        "approvals": {"approvals": []},
        "proposals": {
            "proposals": [],
            "acceptance": {"decided": 0, "approved": 0, "rate": 0.0},
        },
        "proposal-count": {"pending": 0},
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


#: Two of the fifteen validated integrations, connected and verified — the
#: Verify step's own worked example (mockup `#m5`): a metrics source and a
#: cloud control plane, the same two kinds `_INTEGRATION_READINESS` covers for
#: `populated` but with names this scenario's own catalogue does not carry
#: otherwise.
_PROMETHEUS_INTEGRATION: Final[Mapping[str, Any]] = {
    "name": "prometheus",
    "display_name": "Prometheus",
    "category": "metrics",
    "summary": (
        "PromQL evaluation and the alert rules currently firing, from the server "
        "that holds the series rather than from a dashboard on top of it."
    ),
    "health": "healthy",
    "health_detail": "a live request reached this endpoint",
    "hosts": ["prometheus.example.com"],
    "regions": ["self-hosted"],
    "capabilities": [
        "prometheus_active_alerts",
        "prometheus_metric_statistics",
        "prometheus_resource_pressure",
    ],
    "fields": [
        {
            "name": "token",
            "label": "Token",
            "secret": True,
            "required": True,
            "help": "Bearer token accepted by whatever fronts Prometheus, which usually has no auth of its own",
            "min_scope": "",
            "guide_url": "",
        }
    ],
    "permissions": [
        {
            "name": "query",
            "grants": "evaluate PromQL over the stored series",
            "where": "Your reverse proxy, ingress, or Grafana Cloud access policy",
            "capabilities": ["prometheus_metric_statistics"],
        }
    ],
    "parity": "complete",
    "missing_artefacts": [],
}

_PROXMOX_INTEGRATION: Final[Mapping[str, Any]] = {
    "name": "proxmox",
    "display_name": "Proxmox VE",
    "category": "cloud_control_plane",
    "summary": (
        "A Proxmox VE cluster read whole: quorum, nodes, containers, virtual "
        "machines, datastores, thin pools, backups and replication."
    ),
    "health": "healthy",
    "health_detail": "a live request reached this endpoint",
    "hosts": ["proxmox.example.com"],
    "regions": ["self-hosted"],
    "capabilities": ["proxmox_cluster_health", "proxmox_guest_pressure"],
    "fields": [
        {
            "name": "api_token",
            "label": "API Token",
            "secret": True,
            "required": True,
            "help": "Proxmox API token as one line: user@realm!tokenid=secret",
            "min_scope": "",
            "guide_url": "",
        }
    ],
    "permissions": [
        {
            "name": "Sys.Audit on /",
            "grants": "read cluster status, quorum and the cluster log",
            "where": "Datacenter → Permissions",
            "capabilities": ["proxmox_cluster_health"],
        }
    ],
    "parity": "complete",
    "missing_artefacts": [],
}


def first_run_records() -> tuple[CapturedRecord, ...]:
    """Return a deployment that has been configured and is not finished.

    The setup checklist is the screen this exists for: the model provider is
    google_gemini, configured and not yet verified, and Prometheus and Proxmox
    VE are connected and verified — the Verify step's own worked example.
    """
    records = [
        record
        for record in empty_records()
        # Replaced below by a listing where google_gemini is configured,
        # rather than patched by slug: `provider_records` returns one row
        # per provider and a naive slug-keyed replacement cannot tell them
        # apart by `provider_id`.
        if record.slug not in ("providers", "provider-detail")
    ]
    records.extend(served.provider_records(configured=("google_gemini",), verified=()))
    records.append(
        CapturedRecord(
            slug="config-integration-schemas",
            arguments={"node_id": "org-northwind"},
            status=200,
            body={
                "schemas": [
                    {
                        "name": "prometheus",
                        "display_name": "Prometheus",
                        "hosts": ["prometheus.example.com"],
                        "credential_fields": [
                            {
                                "name": "token",
                                "label": "Token",
                                "secret": True,
                                "required": True,
                                "help": "Bearer token accepted by whatever fronts Prometheus",
                            }
                        ],
                        "settings_fields": [],
                    },
                    {
                        "name": "proxmox",
                        "display_name": "Proxmox VE",
                        "hosts": ["proxmox.example.com"],
                        "credential_fields": [
                            {
                                "name": "api_token",
                                "label": "API Token",
                                "secret": True,
                                "required": True,
                                "help": "Proxmox API token as one line: user@realm!tokenid=secret",
                            }
                        ],
                        "settings_fields": [],
                    },
                ]
            },
            provenance=Provenance.GATEWAY,
            request=Request(method="GET", path="config-integration-schemas"),
        )
    )
    records.append(_gemini_verify_record())
    records.append(_gemini_models_record())
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
                dict(_PROMETHEUS_INTEGRATION),
                dict(_PROXMOX_INTEGRATION),
                {
                    "name": "metrics-store",
                    "display_name": "Metrics store",
                    "category": "observability",
                    "summary": "Range queries against the metrics store.",
                    "health": "unconfigured",
                    "health_detail": "no credential is stored anywhere in this deployment",
                    "hosts": ["metrics.example.invalid"],
                    "regions": [],
                    "capabilities": ["metrics.range_query"],
                    "fields": [
                        {
                            "name": "api_token",
                            "label": "API token",
                            "secret": True,
                            "required": True,
                            "help": "Generated from the metrics store's own settings page.",
                            "min_scope": "read-only",
                            # Relative, for the same reason served.py's copy is.
                            "guide_url": "/integrations/metrics-store/guide",
                        }
                    ],
                    "permissions": [
                        {
                            "name": "metrics:read",
                            "grants": "run range queries against stored series",
                            "where": "Metrics store → Settings → API tokens → Scopes",
                            "capabilities": ["metrics.range_query"],
                        }
                    ],
                    "parity": "full",
                    "missing_artefacts": [],
                },
            ],
        },
        # A provider configured and not yet verified, and the two connected
        # integrations the Verify step's own worked example needs — declared
        # and holding nothing is still the fact for `metrics-store`, which is
        # what the Integrations step of the guided run is drawn against.
        "setup-checklist": served.checklist_record(
            provider=SETUP_READINESS_CONFIGURED,
            integrations=(
                ("metrics-store", "absent"),
                ("prometheus", SETUP_READINESS_VERIFIED),
                ("proxmox", SETUP_READINESS_VERIFIED),
            ),
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
        "config-operating-context",
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
    # The prompt a pending operating context would send. Written out in full
    # rather than assembled here: this record is what a screen claiming to show
    # "the exact text the model receives" is photographed against, and a
    # fixture that built it from parts would be the second implementation of the
    # assembly the screen exists to avoid.
    context_preview = {
        "node_id": served.ORG_NODE,
        "prompt": (
            "You are an SRE investigator. Establish the root cause from evidence.\n\n"
            "## Operating context for this deployment\n\n"
            "Facts an operator of this environment wrote down.\n\n"
            "### Where the signals really are\n\n"
            "A container shares its host's kernel, so memory and CPU for a guest "
            "are read from the host's own series for it, keyed by the guest's "
            "numeric id (vmid)."
        ),
        "context": (
            "## Operating context for this deployment\n\n"
            "### Where the signals really are\n\n"
            "A container shares its host's kernel."
        ),
        "tokens_used": 174,
        "token_budget": 1200,
        "over_budget": False,
        "accepted": True,
        "errors": [],
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
        ("config-operating-context-preview", 200, context_preview),
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
