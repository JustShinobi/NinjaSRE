"""The shipped detector set, with its reasoning, on a screen rather than in a file.

FR-015 asks that every shipped threshold's number, the reason for that number,
and what to do about it be "visible in the console, not only in a document", and
the requirement is not about discoverability. It is about *when*. The moment
somebody needs to know why a datastore threshold is eighty-five is the moment
they are looking at an incident raised by it and deciding whether the number is
wrong for their cluster. A document they would have to go and find is a document
they do not read, and the outcome is an operator who either turns the detector
off or obeys it without understanding — the two failures the rationale exists to
prevent.

**This page holds no rule of its own.** It renders a document the deployment
resolved: which detectors this topology activates, what each one's threshold is
after this deployment's overrides, and the reasoning that came with it. The
console could combine the shipped catalogue with the overrides itself — the
arithmetic is not difficult — and the day its copy drifted from the server's,
somebody would be shown a threshold the deployment does not use.

The page also answers the second question an operator asks, which is "why is
this one not on my cluster". A detector the topology does not activate is shown
as such rather than being absent — an absent detector reads as a detector that
does not exist.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from surfaces.console.html import Element, element
from surfaces.console.pages.shell import (
    PageContext,
    badge,
    card,
    definitions,
    heading,
    table,
)


def guardian_body(context: PageContext, resolved: Mapping[str, Any]) -> Element:
    """Return the guardian page: the topology, the active set, and what is dormant."""
    detectors = _records(resolved, "detectors")
    problems = _records(resolved, "problems")
    dormant = [str(name) for name in resolved.get("not_applicable") or ()]

    return element(
        "div",
        heading(1, context.text("guardian.heading")),
        _shape_card(context, resolved),
        *([_problems(context, problems)] if problems else []),
        _detector_table(context, detectors),
        *([_dormant(context, dormant, resolved)] if dormant else []),
    )


def detector_detail(context: PageContext, detector: Mapping[str, Any]) -> Element:
    """Return one detector in full, which is where the reasoning actually lives.

    A fixed order of terms, because an operator reading their way through
    forty-odd of these needs them to be the same shape every time.
    """
    origin = str(detector.get("origin") or "")
    origin_key = f"guardian.origin.{origin}"
    return card(
        heading(2, str(detector.get("name") or detector.get("detector_id") or "")),
        definitions(
            [
                (context.text("guardian.watches"), str(detector.get("watches") or "")),
                (context.text("guardian.threshold"), str(detector.get("threshold") or "")),
                (context.text("guardian.rationale"), str(detector.get("rationale") or "")),
                (context.text("guardian.remedy"), str(detector.get("remedy") or "")),
                (context.text("guardian.signal"), str(detector.get("signal") or "")),
                (
                    context.text("guardian.origin"),
                    context.text(origin_key) if context.catalogue.has(origin_key) else origin,
                ),
            ]
        ),
    )


def _shape_card(context: PageContext, resolved: Mapping[str, Any]) -> Element:
    """Return what the deployment detected, and what it decided from it."""
    enabled = bool(resolved.get("enabled"))
    return card(
        heading(2, context.text("guardian.topology")),
        badge(
            context.text("guardian.enabled" if enabled else "guardian.disabled"),
            kind="ok" if enabled else "muted",
        ),
        element("p", str(resolved.get("cluster_shape_description") or "")),
    )


def _detector_table(context: PageContext, detectors: Sequence[Mapping[str, Any]]) -> Element:
    """Return every active detector as a row carrying its own reasoning.

    The rationale is in the table rather than behind a link on purpose. A link
    is one click, and one click is the difference between a number somebody
    understands and a number somebody obeys.
    """
    return table(
        caption=context.text("guardian.active"),
        columns=[
            context.text("guardian.detector"),
            context.text("guardian.watches"),
            context.text("guardian.threshold"),
            context.text("guardian.rationale"),
            context.text("guardian.remedy"),
            context.text("guardian.severity"),
        ],
        rows=[
            [
                str(detector.get("name") or ""),
                str(detector.get("watches") or ""),
                str(detector.get("threshold") or ""),
                str(detector.get("rationale") or ""),
                str(detector.get("remedy") or ""),
                badge(
                    str(detector.get("severity") or ""),
                    kind=str(detector.get("severity") or ""),
                ),
            ]
            for detector in detectors
        ],
        empty=context.text("guardian.none_active"),
    )


def _dormant(
    context: PageContext, detector_ids: Sequence[str], resolved: Mapping[str, Any]
) -> Element:
    """Return the detectors this topology does not activate, and why not.

    Shown rather than omitted. An absent detector reads as one that does not
    exist, and the operator of a single-node installation deserves to know that
    the quorum detectors are waiting for a second node rather than missing.
    """
    return card(
        heading(2, context.text("guardian.dormant")),
        element(
            "p",
            context.text("guardian.dormant_why", shape=str(resolved.get("cluster_shape") or "")),
        ),
        element("ul", *[element("li", detector_id) for detector_id in detector_ids]),
    )


def _problems(context: PageContext, problems: Sequence[Mapping[str, Any]]) -> Element:
    """Return the overrides that could not be applied, with the reason for each.

    An override that changes nothing for a reason nothing states is the failure
    this exists to remove — almost always a mistyped identifier, and invisible
    without this.
    """
    return card(
        heading(2, context.text("guardian.problems")),
        element(
            "ul",
            *[
                element(
                    "li",
                    f"{problem.get('detector_id', '')}: {problem.get('reason', '')}",
                )
                for problem in problems
            ],
        ),
        danger=True,
    )


def _records(document: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    """Return the mappings under ``key``, ignoring anything that is not one."""
    return [entry for entry in document.get(key) or () if isinstance(entry, Mapping)]


__all__ = ["detector_detail", "guardian_body"]
