"""One fixture set for every page test: a viewer per role, and a page per area.

The role matrix, the accessibility sweep, and the omission tests all need the
same two things — every role, and every page rendered as that role — so both are
built once here from the platform's own catalogue rather than from a list this
directory keeps in step by hand. A role added to
``platform/identity/permissions.py`` appears in every one of those tests without
anybody remembering to add it.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import pytest

from platform.identity.permissions import ROLE_ORDER, Role, permissions_for
from surfaces.console.html import Document, element
from surfaces.console.pages import admin as admin_page
from surfaces.console.pages import auth as auth_page
from surfaces.console.pages import catalogue as catalogue_page
from surfaces.console.pages import config as config_page
from surfaces.console.pages import interactions as interactions_page
from surfaces.console.pages import memory as memory_page
from surfaces.console.pages import runs as runs_page
from surfaces.console.pages.shell import PageContext, page
from surfaces.console.permissions import Viewer
from surfaces.console.transcript import TranscriptEvent

ORG = "acme"
TEAM = "payments"


def viewer_for(role: Role, *, impersonating: bool = False) -> Viewer:
    """Return the viewer a principal holding ``role`` at their team presents as.

    Built from ``permissions_for`` rather than from a literal list, so this
    cannot disagree with what the API would actually allow.
    """
    return Viewer(
        principal_id=f"{role.value}-user",
        display_name=role.value.title(),
        team_node_id=TEAM,
        permissions=frozenset(permissions_for(role)),
        roles=(role.value,),
        impersonating=impersonating,
        impersonated_by="admin-user" if impersonating else None,
    )


def context_for(role: Role, *, path: str = "/runs", impersonating: bool = False) -> PageContext:
    """Return a page context for ``role``."""
    return PageContext(viewer=viewer_for(role, impersonating=impersonating), path=path)


# --- The payloads every page is rendered from --------------------------------

RUNS: tuple[Mapping[str, Any], ...] = (
    {
        "run_id": "run-1",
        "status": "running",
        "trigger": "webhook",
        "started_at": "2026-05-01T08:00:00+00:00",
        "summary": "checkout latency",
        "awaiting_interaction": True,
    },
    {
        "run_id": "run-2",
        "status": "completed",
        "trigger": "interactive",
        "started_at": "2026-04-30T22:10:00+00:00",
        "summary": "resolved: connection pool halved",
    },
)

RUN = RUNS[0]

EVENTS: tuple[TranscriptEvent, ...] = (
    TranscriptEvent(run_id="run-1", kind="run_started", sequence=0, payload={"text": "started"}),
    TranscriptEvent(
        run_id="run-1",
        kind="capability_called",
        sequence=1,
        payload={
            "capability": "datadog.search_logs",
            "arguments": {"query": "service:checkout"},
            "result": {"count": 12},
            "side_effect_level": "read",
        },
    ),
    TranscriptEvent(run_id="run-1", kind="subagent_dispatched", sequence=2, payload={"turns": []}),
    TranscriptEvent(
        run_id="run-1", kind="guardrail_action", sequence=3, payload={"detail": "masked a host"}
    ),
)

APPROVAL: Mapping[str, Any] = {
    "approval_id": "ap-1",
    "run_id": "run-1",
    "action": "kubernetes.restart_deployment",
    "side_effect_level": "disruptive",
    "summary": "restart checkout",
    "state": "pending",
    "arguments": {"deployment": "checkout", "current_state": "4 replicas, 3 crashlooping"},
    "blast_radius": [{"node": {"node_id": "storefront", "name": "storefront"}, "depth": 1}],
    "evidence": [{"summary": "the pool halved at 14:02"}],
    "rollback_plan": {
        "plan_id": "rb-1",
        "approval_id": "ap-1",
        "steps": [
            {
                "ordinal": 1,
                "description": "scale back to 4 replicas",
                "capability": "kubernetes.scale_deployment",
                "arguments": {"replicas": 4},
            }
        ],
    },
}

INTERACTIONS: tuple[Mapping[str, Any], ...] = (
    {
        "interaction_id": "ap-1",
        "approval_id": "ap-1",
        "run_id": "run-1",
        "kind": "approval",
        "text": "restart the checkout deployment?",
        "is_open": True,
    },
    {
        "interaction_id": "q-1",
        "run_id": "run-1",
        "kind": "question",
        "text": "Which cluster is authoritative?",
        "reason": "two clusters answer for this service",
        "options": ["eu-west-1", "us-east-1"],
        "is_open": True,
    },
)

EPISODES: tuple[Mapping[str, Any], ...] = (
    {
        "episode_id": "ep-1",
        "title": "Checkout pool exhaustion",
        "components": ["checkout"],
        "capabilities": ["datadog.search_logs"],
        "outcome": "resolved",
        "effectiveness": 0.8,
        "run_id": "run-1",
    },
)

STRATEGIES: tuple[Mapping[str, Any], ...] = (
    {
        "strategy_id": "st-1",
        "title": "Check the pool before the pods",
        "summary": "Connection pool exhaustion looks like a pod problem.",
        "body": "1. Look at the pool.",
        "source_episode_ids": ["ep-1"],
        "human_edited": True,
    },
)

TOPOLOGY: Mapping[str, Any] = {
    "node_id": "checkout",
    "available": True,
    "dependencies": [{"node_id": "payments-db", "name": "payments-db"}],
    "dependents": [{"node_id": "storefront", "name": "storefront"}],
    "blast_radius": [{"node": {"node_id": "storefront", "name": "storefront"}, "depth": 1}],
}

DOCUMENTS: tuple[Mapping[str, Any], ...] = (
    {
        "document_id": "doc-1",
        "title": "Checkout runbook",
        "source_uri": "https://wiki.acme.test/checkout",
        "updated_at": "2026-04-01T09:00:00+00:00",
    },
)

PROPOSALS: tuple[Mapping[str, Any], ...] = (
    {
        "proposal_id": "pr-1",
        "title": "Record the pool ceiling",
        "summary": "The pool is capped at 20.",
        "run_id": "run-1",
    },
)

NODES: tuple[Mapping[str, Any], ...] = (
    {"node_id": ORG, "kind": "organisation", "name": "Acme", "parent_id": None},
    {"node_id": TEAM, "kind": "team", "name": "Payments", "parent_id": ORG},
    {"node_id": "platform", "kind": "team", "name": "Platform", "parent_id": ORG},
)

EFFECTIVE: Mapping[str, Any] = {
    "node_id": TEAM,
    "values": {"llm": {"model": "small"}, "policies": {"masking": {"level": "standard"}}},
    "provenance": {"llm.model": ORG, "policies.masking.level": TEAM},
}

PREVIEW: Mapping[str, Any] = {
    "node_id": TEAM,
    "values": {"llm": {"model": "large"}},
    "provenance": {"llm.model": TEAM},
    "changes": [{"path": "llm.model", "before": "small", "after": "large"}],
    "locked": {"policies.masking.level": ORG},
    "approval_gated": ["llm.model"],
    "requires_approval": True,
}

CATALOGUE: Mapping[str, Any] = {
    "entries": [
        {
            "name": "datadog.search_logs",
            "kind": "tool",
            "summary": "Search logs",
            "tags": ["logs"],
            "side_effect_level": "read",
            "required_integrations": ["datadog"],
            "available": True,
            "reason": None,
        },
        {
            "name": "kubernetes.restart_deployment",
            "kind": "tool",
            "summary": "Restart a deployment",
            "tags": ["k8s"],
            "side_effect_level": "disruptive",
            "required_integrations": ["kubernetes"],
            "available": False,
            "reason": "needs the kubernetes integration",
        },
    ],
    "blocked_by_integration": {"kubernetes": ["kubernetes.restart_deployment"]},
}

SCHEMAS: tuple[Mapping[str, Any], ...] = (
    {
        "name": "datadog",
        "display_name": "Datadog",
        "credential_fields": [
            {"name": "api_key", "label": "API key", "secret": True, "required": True, "help": ""},
            {"name": "app_key", "label": "App key", "secret": True, "required": True, "help": ""},
        ],
        "settings_fields": [
            {"name": "site", "label": "Site", "secret": False, "required": False, "help": ""}
        ],
        "hosts": ["api.datadoghq.com"],
    },
)

PEOPLE: tuple[Mapping[str, Any], ...] = (
    {
        "user_id": "ada",
        "email": "ada@acme.test",
        "display_name": "Ada",
        "kind": "user",
        "is_active": True,
    },
)

GRANTS: tuple[Mapping[str, Any], ...] = (
    {"grant_id": "g-1", "principal_id": "ada", "role": "operator", "node_id": TEAM},
)

TOKENS: tuple[Mapping[str, Any], ...] = (
    {
        "token_id": "t-1",
        "user_id": "ada",
        "name": "ada-token",
        "scopes": [],
        "created_at": "2026-04-01T09:00:00+00:00",
        "expires_at": "2026-07-01T09:00:00+00:00",
        "last_used_at": None,
        "revoked": False,
    },
)

AUDIT: Mapping[str, Any] = {
    "events": [
        {
            "event_id": "ev-1",
            "occurred_at": "2026-05-01T08:00:00+00:00",
            "actor_kind": "user",
            "actor_id": "ada",
            "action": "config.write",
            "resource_kind": "config",
            "resource_id": TEAM,
            "outcome": "allowed",
            "detail": {},
        }
    ],
    "total": 1,
}

SSO: Mapping[str, Any] = {
    "provider": "okta",
    "issuer": "https://acme.okta.test",
    "active": False,
    "tested": False,
}

POLICIES: Mapping[str, Any] = {"session.lifetime_hours": 8}


#: Every page the console serves, as a builder that needs only a context. This
#: is what the role matrix and the accessibility sweep both walk — one list, so
#: a page added without being added here is a page neither test covers, and the
#: coverage test below notices.
PAGES: Mapping[str, Callable[[PageContext], Document]] = {
    "sign-in": lambda context: auth_page.sign_in_page(context),
    "runs": lambda context: page(
        context, title_key="runs.title", body=runs_page.run_list_body(context, RUNS)
    ),
    "run-detail-live": lambda context: page(
        context,
        title_key="runs.title",
        body=runs_page.run_detail_body(
            context,
            {**RUN, "cost": {"total_tokens": 1200, "total_cost": 0.04, "turns": 4}},
            EVENTS,
            is_live=True,
            interactions=INTERACTIONS,
        ),
    ),
    "run-detail-replay": lambda context: page(
        context,
        title_key="runs.title",
        body=runs_page.run_detail_body(
            context,
            {**RUNS[1], "cost": {"total_tokens": 1200, "total_cost": 0.04, "turns": 4}},
            EVENTS,
            is_live=False,
        ),
    ),
    "interactions": lambda context: page(
        context,
        title_key="interactions.title",
        body=interactions_page.interaction_queue_body(context, INTERACTIONS, (APPROVAL,)),
    ),
    "rollback": lambda context: page(
        context,
        title_key="interactions.title",
        body=element(
            "div",
            element("h1", "Executed remediations"),
            interactions_page.rollback_card(context, APPROVAL, until="2026-05-01T09:00:00+00:00"),
        ),
    ),
    "memory": lambda context: page(
        context,
        title_key="memory.title",
        body=memory_page.memory_body(
            context, EPISODES, stats={"episode_count": 1}, strategies=STRATEGIES
        ),
    ),
    "topology": lambda context: page(
        context, title_key="memory.title", body=memory_page.topology_body(context, TOPOLOGY)
    ),
    "knowledge": lambda context: page(
        context,
        title_key="knowledge.title",
        body=memory_page.knowledge_body(context, DOCUMENTS, proposals=PROPOSALS),
    ),
    "config": lambda context: page(
        context,
        title_key="config.title",
        body=config_page.config_body(
            context,
            NODES,
            node_id=TEAM,
            effective=EFFECTIVE,
            preview=PREVIEW,
            templates=("golden",),
            template_diff={"changes": [{"path": "llm.model", "before": "small", "after": "big"}]},
        ),
    ),
    "catalogue": lambda context: page(
        context,
        title_key="catalogue.title",
        body=catalogue_page.catalogue_body(
            context, CATALOGUE, schemas=SCHEMAS, api_base="https://api.acme.test"
        ),
    ),
    "admin": lambda context: page(
        context,
        title_key="admin.title",
        body=admin_page.admin_body(
            context,
            people=PEOPLE,
            grants=GRANTS,
            tokens=TOKENS,
            audit=AUDIT,
            sso=SSO,
            policies=POLICIES,
        ),
    ),
    "onboarding": lambda context: page(
        context,
        title_key="onboarding.title",
        body=admin_page.onboarding_body(context, admin_page.ONBOARDING_STEPS),
    ),
}


@pytest.fixture(params=list(ROLE_ORDER), ids=[role.value for role in ROLE_ORDER])
def role(request: pytest.FixtureRequest) -> Role:
    """Return one of the five roles, so a test parametrised on this walks all of them."""
    return request.param  # type: ignore[no-any-return]


@pytest.fixture(params=sorted(PAGES), ids=sorted(PAGES))
def page_name(request: pytest.FixtureRequest) -> str:
    """Return one page's name, so a test parametrised on this walks every page."""
    return request.param  # type: ignore[no-any-return]


def render(page_name: str, role: Role, *, impersonating: bool = False) -> Document:
    """Return one page rendered as one role."""
    return PAGES[page_name](context_for(role, impersonating=impersonating))


__all__ = [
    "APPROVAL",
    "AUDIT",
    "CATALOGUE",
    "DOCUMENTS",
    "EFFECTIVE",
    "EPISODES",
    "EVENTS",
    "GRANTS",
    "INTERACTIONS",
    "NODES",
    "ORG",
    "PAGES",
    "PEOPLE",
    "POLICIES",
    "PREVIEW",
    "PROPOSALS",
    "RUN",
    "RUNS",
    "SCHEMAS",
    "SSO",
    "STRATEGIES",
    "TEAM",
    "TOKENS",
    "TOPOLOGY",
    "context_for",
    "render",
    "viewer_for",
]
