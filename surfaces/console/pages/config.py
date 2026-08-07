"""The org tree, the per-node editor, and the preview that comes from the server.

Nothing in this file merges configuration. The preview it renders is whatever
``POST /v1/config/{node}/preview`` answered, field for field, including which
paths an ancestor locked and which the deployment puts behind an approval. That
is the whole of SC-005: the preview matches what the API computes because it *is*
what the API computed.

Three things this page has to be honest about, each of which is a way an
operator can be surprised by a save.

**Provenance.** A value shown without the node it came from looks like this
node's decision, and half the time it is somebody else's.

**A lock.** Rendered as locked and naming the locking node, so the next question
— who do I ask — is already answered.

**A gate.** Marked as queuing rather than applying, on the control itself, before
the click. A console that said "saved" for a change that went to a review queue
would be the one telling somebody their outage mitigation was live when it was
not.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from surfaces.console.html import Child, Element, element
from surfaces.console.pages.shell import (
    PageContext,
    card,
    form,
    form_field,
    heading,
    table,
    value_or_dash,
)
from surfaces.console.permissions import Action, action_control

#: Where a value with no node behind it came from. Not the empty string: a blank
#: provenance cell reads as "unknown" when the fact is "nobody has overridden
#: this, so it is what ships".
SHIPPED_DEFAULT = "config.provenance_default"


def org_tree(
    context: PageContext, nodes: Sequence[Mapping[str, Any]], *, selected: str = ""
) -> Element:
    """Return the organisation tree as one nested list (FR-016, SC-008).

    Built in a single pass — children indexed by parent, then one walk from the
    root — so a tree of several hundred nodes costs what a tree of ten costs
    times the number of nodes, rather than that squared. A quadratic tree
    builder is invisible on a fixture and is the whole interaction budget on a
    real organisation.
    """
    children: dict[str, list[Mapping[str, Any]]] = {}
    roots: list[Mapping[str, Any]] = []
    for node in nodes:
        parent = node.get("parent_id")
        if parent is None:
            roots.append(node)
        else:
            children.setdefault(str(parent), []).append(node)

    return element(
        "nav",
        _branch(context, roots, children, selected=selected),
        class_="tree",
        aria_label=context.text("config.tree_label"),
        data_nodes=str(len(nodes)),
    )


def _branch(
    context: PageContext,
    nodes: Sequence[Mapping[str, Any]],
    children: Mapping[str, list[Mapping[str, Any]]],
    *,
    selected: str,
) -> Element:
    """Return one level of the tree, and every level beneath it."""
    return element(
        "ul",
        *[
            element(
                "li",
                element(
                    "a",
                    str(node.get("name") or node.get("node_id", "")),
                    href=f"/config/{node.get('node_id', '')}",
                    aria_current="page" if node.get("node_id") == selected else None,
                ),
                _branch(
                    context,
                    children.get(str(node.get("node_id", "")), ()),
                    children,
                    selected=selected,
                )
                if children.get(str(node.get("node_id", "")))
                else None,
            )
            for node in nodes
        ],
    )


def config_body(
    context: PageContext,
    nodes: Sequence[Mapping[str, Any]],
    *,
    node_id: str = "",
    effective: Mapping[str, Any] | None = None,
    preview: Mapping[str, Any] | None = None,
    templates: Sequence[str] = (),
    template_diff: Mapping[str, Any] | None = None,
) -> Element:
    """Return the configuration area: the tree, the editor, and the preview."""
    return element(
        "div",
        heading(1, context.text("config.heading")),
        org_tree(context, nodes, selected=node_id),
        _editor(context, node_id, effective) if node_id else None,
        preview_panel(context, preview) if preview is not None else None,
        _templates(context, node_id, templates, template_diff) if node_id else None,
    )


def _editor(context: PageContext, node_id: str, effective: Mapping[str, Any] | None) -> Element:
    """Return the per-node editor, every value carrying where it came from (FR-017)."""
    values = (effective or {}).get("values") or {}
    provenance = (effective or {}).get("provenance") or {}
    rows: list[Sequence[Child]] = [
        [
            element("code", path),
            value_or_dash(context, value),
            _provenance(context, provenance.get(path), node_id),
        ]
        for path, value in sorted(_leaves(values))
    ]

    return element(
        "section",
        heading(2, context.text("config.editor", node=node_id)),
        table(
            caption=context.text("config.editor", node=node_id),
            columns=[
                context.text("config.path"),
                context.text("config.value"),
                context.text("config.provenance"),
            ],
            rows=rows,
            empty=context.text("common.none"),
        ),
        card(
            form(
                form_field(identifier="path", label=context.text("config.path"), required=True),
                form_field(identifier="value", label=context.text("config.value")),
                element("button", context.text("config.preview"), type="submit"),
                action=f"/config/{node_id}/preview",
                label=context.text("config.preview"),
            )
        ),
        aria_label=context.text("config.editor", node=node_id),
    )


def _provenance(context: PageContext, source: Any, node_id: str) -> Child:
    """Return where one value came from, naming this node's own overrides plainly."""
    if not source:
        return element("span", context.text(SHIPPED_DEFAULT), class_="muted")
    if str(source) == node_id:
        return element("strong", str(source))
    return element("a", str(source), href=f"/config/{source}")


def preview_panel(context: PageContext, preview: Mapping[str, Any] | None) -> Element:
    """Return what saving would do, exactly as the server computed it (FR-017, SC-005).

    Read straight off the response. Nothing here recomputes a value, decides
    whether a field is locked, or works out what needs approval — those are the
    three things a console reimplementing them would eventually get wrong, and
    the failure would be silent.
    """
    detail = preview or {}
    changes = [change for change in detail.get("changes") or () if isinstance(change, Mapping)]
    locked = detail.get("locked") or {}
    gated = [str(path) for path in detail.get("approval_gated") or ()]
    provenance = detail.get("provenance") or {}

    return element(
        "section",
        heading(2, context.text("config.preview_heading")),
        element("p", context.text("config.unchanged"), class_="muted") if not changes else None,
        table(
            caption=context.text("config.preview_heading"),
            columns=[
                context.text("config.path"),
                context.text("config.before"),
                context.text("config.after"),
                context.text("config.provenance"),
            ],
            rows=[
                [
                    element("code", str(change.get("path", ""))),
                    value_or_dash(context, change.get("before")),
                    value_or_dash(context, change.get("after")),
                    value_or_dash(context, provenance.get(str(change.get("path", "")))),
                ]
                for change in changes
            ],
            empty=context.text("config.unchanged"),
            data_preview="changes",
        ),
        _locked_notices(context, locked),
        _gated_notice(context, gated),
        _save_control(context, detail, gated),
        aria_label=context.text("config.preview_heading"),
        data_requires_approval="true" if detail.get("requires_approval") else "false",
    )


def _locked_notices(context: PageContext, locked: Mapping[str, Any]) -> Element | None:
    """Return one notice per locked field, naming the node holding the lock (FR-018)."""
    if not locked:
        return None
    return element(
        "ul",
        *[
            element(
                "li",
                element("code", str(path)),
                " ",
                context.text("config.locked", node=str(node)),
                data_locked=str(path),
            )
            for path, node in sorted(locked.items())
        ],
        class_="notice",
        role="status",
    )


def _gated_notice(context: PageContext, gated: Sequence[str]) -> Element | None:
    """Return the notice that saving queues rather than applies (FR-019)."""
    if not gated:
        return None
    return element(
        "p",
        context.text("config.gated"),
        " ",
        ", ".join(gated),
        class_="notice",
        role="status",
        data_gated="true",
    )


def _save_control(
    context: PageContext, preview: Mapping[str, Any], gated: Sequence[str]
) -> Element | None:
    """Return the save control, saying on itself whether it saves or queues."""
    node_id = str(preview.get("node_id", ""))
    label = context.text("config.gated") if gated else context.text("config.save")
    return action_control(
        context.viewer,
        Action.EDIT_CONFIG,
        lambda: form(
            element("button", label, type="submit", class_="primary"),
            action=f"/config/{node_id}",
            label=label,
        ),
    )


def _templates(
    context: PageContext,
    node_id: str,
    templates: Sequence[str],
    diff: Mapping[str, Any] | None,
) -> Element | None:
    """Return template application, with the diff shown before anything is applied."""
    if not templates:
        return None
    return element(
        "section",
        heading(2, context.text("config.template")),
        action_control(
            context.viewer,
            Action.APPLY_TEMPLATE,
            lambda: card(
                form(
                    element(
                        "div",
                        element("label", context.text("config.template"), for_="template"),
                        element(
                            "select",
                            *[element("option", name, value=name) for name in templates],
                            id="template",
                            name="template",
                        ),
                        class_="field",
                    ),
                    element("button", context.text("config.template_preview"), type="submit"),
                    action=f"/config/{node_id}/template",
                    label=context.text("config.template"),
                )
            ),
        ),
        _template_diff(context, diff),
        aria_label=context.text("config.template"),
    )


def _template_diff(context: PageContext, diff: Mapping[str, Any] | None) -> Element | None:
    """Return what applying a template would change, before it is applied."""
    if diff is None:
        return None
    changes = [change for change in diff.get("changes") or () if isinstance(change, Mapping)]
    return table(
        caption=context.text("config.template_preview"),
        columns=[
            context.text("config.path"),
            context.text("config.before"),
            context.text("config.after"),
        ],
        rows=[
            [
                element("code", str(change.get("path", ""))),
                value_or_dash(context, change.get("before")),
                value_or_dash(context, change.get("after")),
            ]
            for change in changes
        ],
        empty=context.text("config.unchanged"),
        data_preview="template",
    )


def _leaves(values: Mapping[str, Any], prefix: str = "") -> list[tuple[str, Any]]:
    """Return every leaf of a nested mapping as a dotted path and its value.

    Flattening for display only. This is not the merge — the values arrived
    merged — and it holds no opinion about what any of them mean.
    """
    found: list[tuple[str, Any]] = []
    for key, value in values.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, Mapping):
            found.extend(_leaves(value, path))
        else:
            found.append((path, value))
    return found


__all__ = ["SHIPPED_DEFAULT", "config_body", "org_tree", "preview_panel"]
