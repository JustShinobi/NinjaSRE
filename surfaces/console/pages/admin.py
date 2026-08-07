"""Identity, tokens, the record, the policies, and the first-run set-up.

Two properties this area has that the others do not.

**A revoked token is still listed.** "This token was revoked last Tuesday" is the
answer to the question somebody opening this screen is actually asking, and a
list that hid revoked tokens would answer it with silence.

**Single sign-on is tested before it is activated.** An SSO configuration that is
wrong locks everybody out of the console, including whoever would fix it, so the
activate control is absent until a test has passed rather than being available
with a warning next to it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from surfaces.console.html import Child, Element, element
from surfaces.console.pages.shell import (
    PageContext,
    badge,
    card,
    definitions,
    form,
    form_field,
    heading,
    table,
    value_or_dash,
)
from surfaces.console.permissions import Action, action_control


def admin_body(
    context: PageContext,
    *,
    people: Sequence[Mapping[str, Any]] = (),
    grants: Sequence[Mapping[str, Any]] = (),
    tokens: Sequence[Mapping[str, Any]] = (),
    audit: Mapping[str, Any] | None = None,
    sso: Mapping[str, Any] | None = None,
    policies: Mapping[str, Any] | None = None,
) -> Element:
    """Return the administration area."""
    return element(
        "div",
        heading(1, context.text("admin.heading")),
        _people(context, people, grants),
        _tokens(context, tokens),
        _audit(context, audit or {}),
        _policies(context, policies or {}),
        _sso(context, sso or {}),
    )


def _people(
    context: PageContext,
    people: Sequence[Mapping[str, Any]],
    grants: Sequence[Mapping[str, Any]],
) -> Element:
    """Return who exists and what each of them holds where (T045)."""
    by_principal: dict[str, list[Mapping[str, Any]]] = {}
    for grant in grants:
        by_principal.setdefault(str(grant.get("principal_id", "")), []).append(grant)

    return element(
        "section",
        heading(2, context.text("admin.people")),
        table(
            caption=context.text("admin.people"),
            columns=["Person", "Email", context.text("admin.grants")],
            rows=[
                [
                    str(person.get("display_name") or person.get("user_id", "")),
                    value_or_dash(context, person.get("email")),
                    _grants_cell(context, by_principal.get(str(person.get("user_id", "")), [])),
                ]
                for person in people
            ],
            empty=context.text("common.none"),
        ),
        action_control(
            context.viewer,
            Action.EDIT_GRANT,
            lambda: card(
                form(
                    form_field(identifier="principal_id", label="Person", required=True),
                    form_field(identifier="role", label=context.text("admin.role"), required=True),
                    form_field(identifier="node_id", label=context.text("admin.scope")),
                    element("button", "Grant", type="submit"),
                    action="/admin/grants",
                    label="Grant a role",
                )
            ),
        ),
        action_control(
            context.viewer,
            Action.IMPERSONATE,
            lambda: card(
                element("p", context.text("admin.impersonate_note"), class_="muted"),
                form(
                    form_field(
                        identifier="impersonate_principal",
                        name="principal_id",
                        label="Person",
                        required=True,
                    ),
                    element("button", context.text("admin.impersonate"), type="submit"),
                    action="/admin/impersonation",
                    label=context.text("admin.impersonate"),
                ),
            ),
        ),
        aria_label=context.text("admin.people"),
    )


def _grants_cell(context: PageContext, grants: Sequence[Mapping[str, Any]]) -> Child:
    """Return one person's grants, each naming where it applies."""
    if not grants:
        return context.text("common.none")
    return element(
        "ul",
        *[
            element(
                "li",
                f"{grant.get('role', '')} @ {grant.get('node_id') or context.text('admin.scope')}",
            )
            for grant in grants
        ],
    )


def _tokens(context: PageContext, tokens: Sequence[Mapping[str, Any]]) -> Element:
    """Return the machine tokens, revoked ones included (FR-026)."""
    return element(
        "section",
        heading(2, context.text("admin.tokens")),
        table(
            caption=context.text("admin.tokens"),
            columns=[
                context.text("admin.token_name"),
                "Owner",
                context.text("admin.token_created"),
                context.text("admin.token_expires"),
                context.text("admin.token_last_used"),
                context.text("admin.token_state"),
            ],
            rows=[
                [
                    str(token.get("name", "")),
                    str(token.get("user_id", "")),
                    value_or_dash(context, token.get("created_at")),
                    value_or_dash(context, token.get("expires_at")),
                    value_or_dash(context, token.get("last_used_at")),
                    badge(
                        context.text(
                            "admin.token_revoked" if token.get("revoked") else "admin.token_live"
                        ),
                        kind="revoked" if token.get("revoked") else "live",
                    ),
                ]
                for token in tokens
            ],
            empty=context.text("common.none"),
        ),
        action_control(
            context.viewer,
            Action.CREATE_TOKEN,
            lambda: card(
                form(
                    form_field(
                        identifier="token_name",
                        name="name",
                        label=context.text("admin.token_name"),
                        required=True,
                    ),
                    form_field(
                        identifier="token_node", name="node_id", label=context.text("admin.scope")
                    ),
                    element("button", context.text("admin.token_create"), type="submit"),
                    action="/admin/tokens",
                    label=context.text("admin.token_create"),
                )
            ),
        ),
        action_control(
            context.viewer,
            Action.REVOKE_TOKEN,
            lambda: card(
                form(
                    form_field(
                        identifier="revoke_user",
                        name="user_id",
                        label="Owner",
                        help_text="Revokes every live token this person holds.",
                    ),
                    element(
                        "button",
                        context.text("admin.token_revoke_all"),
                        type="submit",
                        class_="danger",
                    ),
                    action="/admin/tokens/revoke",
                    label=context.text("admin.token_revoke_all"),
                )
            ),
        ),
        aria_label=context.text("admin.tokens"),
    )


def _audit(context: PageContext, audit: Mapping[str, Any]) -> Element:
    """Return the audit browser with its filters and an export (FR-025)."""
    events = [event for event in audit.get("events") or () if isinstance(event, Mapping)]
    return element(
        "section",
        heading(2, context.text("admin.audit")),
        card(
            form(
                form_field(identifier="actor_id", label=context.text("admin.audit_actor")),
                form_field(identifier="action", label=context.text("admin.audit_action")),
                form_field(identifier="since", label="Since", kind="date"),
                form_field(identifier="until", label="Until", kind="date"),
                element("button", "Filter", type="submit"),
                action="/admin/audit",
                method="get",
                label=context.text("admin.audit"),
            )
        ),
        table(
            caption=context.text("admin.audit"),
            columns=[
                context.text("admin.audit_when"),
                context.text("admin.audit_actor"),
                context.text("admin.audit_action"),
                context.text("admin.audit_resource"),
                context.text("admin.audit_outcome"),
            ],
            rows=[
                [
                    str(event.get("occurred_at", "")),
                    str(event.get("actor_id", "")),
                    str(event.get("action", "")),
                    f"{event.get('resource_kind', '')}/{event.get('resource_id', '')}",
                    badge(str(event.get("outcome", ""))),
                ]
                for event in events
            ],
            empty=context.text("common.none"),
        ),
        action_control(
            context.viewer,
            Action.EXPORT_AUDIT,
            lambda: element(
                "a", context.text("admin.audit_export"), href="/admin/audit/export", class_="button"
            ),
        ),
        aria_label=context.text("admin.audit"),
    )


def _policies(context: PageContext, policies: Mapping[str, Any]) -> Element:
    """Return the security policies, editable by whoever manages the organisation."""
    return element(
        "section",
        heading(2, context.text("admin.policies")),
        definitions(
            [(str(name), value_or_dash(context, value)) for name, value in sorted(policies.items())]
        )
        if policies
        else element("p", context.text("common.none"), class_="muted"),
        action_control(
            context.viewer,
            Action.EDIT_POLICY,
            lambda: card(
                form(
                    form_field(
                        identifier="policy_path", name="path", label="Policy", required=True
                    ),
                    form_field(identifier="policy_value", name="value", label="Value"),
                    element("button", "Save policy", type="submit"),
                    action="/admin/policies",
                    label=context.text("admin.policies"),
                )
            ),
        ),
        aria_label=context.text("admin.policies"),
    )


def _sso(context: PageContext, sso: Mapping[str, Any]) -> Element:
    """Return SSO configuration, activatable only once a test has passed (T049)."""
    tested = bool(sso.get("tested"))
    return element(
        "section",
        heading(2, context.text("admin.sso")),
        definitions(
            [
                ("Provider", value_or_dash(context, sso.get("provider"))),
                ("Issuer", value_or_dash(context, sso.get("issuer"))),
                (
                    "Active",
                    context.text("common.yes" if sso.get("active") else "common.no"),
                ),
            ]
        ),
        element("p", context.text("admin.sso_untested"), class_="notice") if not tested else None,
        action_control(
            context.viewer,
            Action.CONFIGURE_SSO,
            lambda: card(
                form(
                    form_field(
                        identifier="issuer", label="Issuer", value=str(sso.get("issuer", ""))
                    ),
                    form_field(identifier="client_id", label="Client id"),
                    element("button", context.text("admin.sso_test"), type="submit"),
                    action="/admin/sso/test",
                    label=context.text("admin.sso_test"),
                ),
                # Absent until the test has passed, rather than present and
                # warned about. An SSO configuration that is wrong locks out
                # the person who would fix it.
                form(
                    element(
                        "button",
                        context.text("admin.sso_activate"),
                        type="submit",
                        class_="primary",
                    ),
                    action="/admin/sso/activate",
                    label=context.text("admin.sso_activate"),
                )
                if tested
                else None,
            ),
        ),
        aria_label=context.text("admin.sso"),
    )


def onboarding_body(context: PageContext, steps: Sequence[Mapping[str, Any]]) -> Element:
    """Return the first-run set-up, mirroring the CLI wizard's order (T050).

    The same four steps in the same order as ``ninjasre onboard``, so somebody
    who started in one and finished in the other is not asked to reconstruct
    where they were.
    """
    return element(
        "div",
        heading(1, context.text("onboarding.heading")),
        element(
            "ol",
            *[
                element(
                    "li",
                    element("h2", context.text(str(step.get("label_key", "onboarding.done")))),
                    badge(
                        context.text("onboarding.done" if step.get("done") else "onboarding.todo"),
                        kind="done" if step.get("done") else "todo",
                    ),
                    element("p", str(step.get("detail", "")), class_="muted")
                    if step.get("detail")
                    else None,
                    element("a", "Open", href=str(step.get("href", "/")), class_="button")
                    if step.get("href")
                    else None,
                    data_step=str(step.get("label_key", "")),
                    data_done="true" if step.get("done") else "false",
                )
                for step in steps
            ],
            class_="onboarding",
        ),
    )


#: The steps, in the CLI wizard's order. Data rather than markup, so the console
#: and the CLI can be asserted to agree on what set-up means.
ONBOARDING_STEPS: tuple[Mapping[str, Any], ...] = (
    {"label_key": "onboarding.provider", "href": "/config"},
    {"label_key": "onboarding.integration", "href": "/catalogue"},
    {"label_key": "onboarding.team", "href": "/config"},
    {"label_key": "onboarding.investigate", "href": "/runs"},
)


__all__ = ["ONBOARDING_STEPS", "admin_body", "onboarding_body"]
