"""What this deployment can do, why it cannot do the rest, and how to fix that.

Two halves of one screen. The capability catalogue is rendered from the metadata
the deployment discovered — never a list written here — so a capability added by
installing a package appears without this file changing. And the integration
forms are generated from each vendor's declared credential schema, which is what
keeps eighty-five integrations addable one package at a time.

**The credential form posts to the API, not to the console.** Its ``action`` is
the deployment's own credential endpoint, so the browser sends the secret
straight there and this process never receives it — not in a request body, not
in a log line, not in a session. That is SC-006, and it is satisfied by there
being no code path rather than by a rule somebody has to remember: the console
has no route that accepts a credential field, and ``client.py`` has no method
that sends one.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from surfaces.console.html import Child, Element, element
from surfaces.console.pages.shell import (
    PageContext,
    badge,
    card,
    form,
    form_field,
    heading,
    table,
)
from surfaces.console.permissions import Action, action_control

#: Where a credential form posts: the API's own endpoint for this integration,
#: on the deployment's origin. Not a console path — a console path would mean
#: the secret arriving in this process, which is the thing being avoided.
CREDENTIAL_PATH_TEMPLATE = "{api_base}/v1/integrations/{integration}/credential"


def credential_action(api_base: str, integration: str) -> str:
    """Return where this integration's credential form posts."""
    return CREDENTIAL_PATH_TEMPLATE.format(api_base=api_base.rstrip("/"), integration=integration)


def catalogue_body(
    context: PageContext,
    catalogue: Mapping[str, Any],
    *,
    schemas: Sequence[Mapping[str, Any]] = (),
    api_base: str = "",
) -> Element:
    """Return the capability catalogue and the integration forms (FR-020, FR-021)."""
    entries = [entry for entry in catalogue.get("entries") or () if isinstance(entry, Mapping)]
    available = [entry for entry in entries if entry.get("available")]
    unavailable = [entry for entry in entries if not entry.get("available")]

    return element(
        "div",
        heading(1, context.text("catalogue.heading")),
        _blocked_summary(context, catalogue.get("blocked_by_integration")),
        _entries(context, context.text("catalogue.available"), available, with_reason=False),
        _entries(context, context.text("catalogue.unavailable"), unavailable, with_reason=True),
        _integrations(context, schemas, api_base=api_base),
    )


def _blocked_summary(context: PageContext, blocked: Any) -> Element | None:
    """Return "connecting X would enable N more", which is the actionable line.

    The one part of the picture an operator cannot assemble from a list of what
    they do have, and the reason ``CatalogueView`` computes it server-side.
    """
    if not isinstance(blocked, Mapping) or not blocked:
        return None
    return element(
        "ul",
        *[
            element(
                "li",
                context.text("catalogue.blocked", integration=str(name), count=len(names or ())),
            )
            for name, names in sorted(blocked.items())
        ],
        class_="notice",
    )


def _entries(
    context: PageContext,
    title: str,
    entries: Sequence[Mapping[str, Any]],
    *,
    with_reason: bool,
) -> Element:
    """Return one half of the catalogue as a table."""
    columns = ["Capability", "Kind", "Side effect"]
    if with_reason:
        columns.append(context.text("catalogue.reason"))
    rows: list[Sequence[Child]] = [
        [
            element("code", str(entry.get("name", ""))),
            str(entry.get("kind", "")),
            badge(str(entry.get("side_effect_level", "read"))),
            *([str(entry.get("reason") or context.text("common.none"))] if with_reason else []),
        ]
        for entry in entries
    ]
    return element(
        "section",
        heading(2, f"{title} ({len(entries)})"),
        table(
            caption=title,
            columns=columns,
            rows=rows,
            empty=context.text("common.none"),
            data_catalogue="unavailable" if with_reason else "available",
        ),
        aria_label=title,
    )


def _integrations(
    context: PageContext, schemas: Sequence[Mapping[str, Any]], *, api_base: str
) -> Element:
    """Return one generated form per installed integration."""
    return element(
        "section",
        heading(2, context.text("catalogue.integrations")),
        element("p", context.text("catalogue.credential_note"), class_="muted"),
        *[integration_form(context, schema, api_base=api_base) for schema in schemas],
        aria_label=context.text("catalogue.integrations"),
    )


def integration_form(context: PageContext, schema: Mapping[str, Any], *, api_base: str) -> Element:
    """Return the credential form a vendor's schema describes (FR-020, SC-006).

    Generated, never written: the fields, their labels, which are secret and
    which are required all come from the schema the deployment answered with. A
    console that hard-coded a vendor's field names would be a console somebody
    had to edit before a new integration could be configured.

    The form's ``action`` is the API's own endpoint and its ``method`` is
    ``post``, so the browser delivers the secret directly to the vault. Nothing
    in this process sees it.
    """
    name = str(schema.get("name", ""))
    credential_fields = [
        each for each in schema.get("credential_fields") or () if isinstance(each, Mapping)
    ]
    settings_fields = [
        each for each in schema.get("settings_fields") or () if isinstance(each, Mapping)
    ]

    return card(
        heading(3, str(schema.get("display_name") or name)),
        element(
            "p",
            "Reaches: ",
            ", ".join(str(host) for host in schema.get("hosts") or ())
            or context.text("common.none"),
            class_="muted",
        ),
        action_control(
            context.viewer,
            Action.CONNECT_INTEGRATION,
            lambda: form(
                *[_credential_field(name, spec, secret=True) for spec in credential_fields],
                *[_credential_field(name, spec, secret=False) for spec in settings_fields],
                element(
                    "button", context.text("catalogue.connect"), type="submit", class_="primary"
                ),
                action=credential_action(api_base, name),
                label=f"{context.text('catalogue.connect')} {name}",
                data_credential_form=name,
            ),
        ),
        data_integration=name,
    )


def _credential_field(integration: str, spec: Mapping[str, Any], *, secret: bool) -> Element:
    """Return one field of a credential form, as the vendor's schema declared it.

    A secret field is ``type="password"`` and ``autocomplete="off"``. Neither is
    a security control — the value is in the DOM either way — and both matter:
    the first keeps the key off a screen during the screen-share that is
    happening because there is an incident, the second keeps it out of the
    browser's saved values on a shared machine.
    """
    field_name = str(spec.get("name", ""))
    return form_field(
        identifier=f"{integration}-{field_name}",
        name=field_name,
        label=str(spec.get("label") or field_name),
        kind="password" if secret else "text",
        help_text=str(spec.get("help", "")),
        required=bool(spec.get("required", True)),
        autocomplete="off" if secret else None,
    )


__all__ = [
    "CREDENTIAL_PATH_TEMPLATE",
    "catalogue_body",
    "credential_action",
    "integration_form",
]
