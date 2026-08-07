"""What the platform has learned: episodes, strategies, topology, and documents.

The traceability is the point of the whole area. An episode says which run it
came from; a strategy says which episodes it was built from; a document says
where it was ingested from. A learned thing with no provenance is a claim, and
this product's entire argument is that a claim without its evidence is a
hypothesis.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from surfaces.console.html import Child, Element, element
from surfaces.console.pages.shell import (
    PageContext,
    card,
    definitions,
    form,
    form_field,
    heading,
    table,
    value_or_dash,
)
from surfaces.console.permissions import Action, action_control


def memory_body(
    context: PageContext,
    episodes: Sequence[Mapping[str, Any]],
    *,
    component: str = "",
    stats: Mapping[str, Any] | None = None,
    strategies: Sequence[Mapping[str, Any]] = (),
) -> Element:
    """Return the memory hub: browse, search, and what each episode led to (FR-012)."""
    return element(
        "div",
        heading(1, context.text("memory.heading")),
        card(
            form(
                form_field(
                    identifier="component",
                    label=context.text("memory.search_label"),
                    value=component,
                ),
                element("button", context.text("memory.search"), type="submit"),
                action="/memory",
                method="get",
                label=context.text("memory.search"),
            ),
            definitions([("Episodes", value_or_dash(context, (stats or {}).get("episode_count")))])
            if stats
            else None,
        ),
        table(
            caption=context.text("memory.heading"),
            columns=[
                "Episode",
                context.text("memory.components"),
                context.text("memory.capabilities"),
                context.text("memory.resolution"),
                context.text("memory.effectiveness"),
                context.text("memory.from_run"),
            ],
            rows=[
                [
                    element(
                        "a",
                        str(episode.get("title") or episode.get("episode_id", "")),
                        href=f"/memory/{episode.get('episode_id', '')}",
                    ),
                    ", ".join(str(name) for name in episode.get("components") or ())
                    or context.text("common.none"),
                    ", ".join(str(name) for name in episode.get("capabilities") or ())
                    or context.text("common.none"),
                    value_or_dash(context, episode.get("outcome")),
                    value_or_dash(context, episode.get("effectiveness")),
                    _run_link(context, episode.get("run_id")),
                ]
                for episode in episodes
            ],
            empty=context.text("memory.empty"),
        ),
        _strategies(context, strategies),
    )


def _run_link(context: PageContext, run_id: Any) -> Child:
    """Return a link to the run an episode came from, or a dash."""
    if not run_id:
        return context.text("common.none")
    return element("a", str(run_id), href=f"/runs/{run_id}")


def _strategies(context: PageContext, strategies: Sequence[Mapping[str, Any]]) -> Element | None:
    """Return the strategies with their source episodes and an edit control (FR-013)."""
    if not strategies:
        return None
    return element(
        "section",
        heading(2, context.text("memory.strategies")),
        *[strategy_card(context, strategy) for strategy in strategies],
        aria_label=context.text("memory.strategies"),
    )


def strategy_card(context: PageContext, strategy: Mapping[str, Any]) -> Element:
    """Return one strategy, its sources, and the edit that survives regeneration.

    "Edited by a person" is stated on the card rather than kept as a flag
    somewhere, because the property FR-013 asks for — that an edit is preserved
    through regeneration — is only reassuring if the reader can see that it
    applies to what they are looking at.
    """
    strategy_id = str(strategy.get("strategy_id", ""))
    sources = [str(source) for source in strategy.get("source_episode_ids") or ()]
    return card(
        heading(3, str(strategy.get("title") or strategy_id)),
        element("p", str(strategy.get("summary", ""))),
        element("p", context.text("memory.strategy_edited"), class_="muted")
        if strategy.get("human_edited")
        else None,
        definitions(
            [
                (
                    context.text("memory.strategy_sources"),
                    element(
                        "ul",
                        *[
                            element("li", element("a", source, href=f"/memory/{source}"))
                            for source in sources
                        ],
                    )
                    if sources
                    else context.text("common.none"),
                )
            ]
        ),
        action_control(
            context.viewer,
            Action.EDIT_STRATEGY,
            lambda: form(
                form_field(
                    identifier=f"strategy-{strategy_id}",
                    name="body",
                    label=context.text("memory.strategy_edit"),
                    kind="textarea",
                    value=str(strategy.get("body", "")),
                ),
                element("button", context.text("memory.strategy_edit"), type="submit"),
                action=f"/memory/strategies/{strategy_id}",
                label=context.text("memory.strategy_edit"),
            ),
        ),
        data_strategy=strategy_id,
    )


def topology_body(context: PageContext, topology: Mapping[str, Any]) -> Element:
    """Return a service's dependencies, dependents, and blast radius (FR-014)."""
    if not topology.get("available", True):
        return element(
            "div",
            heading(1, context.text("memory.topology")),
            element(
                "p", str(topology.get("reason") or context.text("memory.topology_unavailable"))
            ),
        )
    return element(
        "div",
        heading(1, context.text("memory.topology")),
        card(
            form(
                form_field(
                    identifier="service",
                    label=context.text("memory.topology_label"),
                    value=str(topology.get("node_id", "")),
                ),
                element("button", context.text("memory.search"), type="submit"),
                action="/memory/topology",
                method="get",
                label=context.text("memory.topology_label"),
            )
        ),
        _node_list(context, context.text("memory.dependencies"), topology.get("dependencies")),
        _node_list(context, context.text("memory.dependents"), topology.get("dependents")),
        _radius(context, topology.get("blast_radius")),
    )


def _node_list(context: PageContext, title: str, nodes: Any) -> Element:
    """Return a titled list of topology nodes."""
    found = [node for node in (nodes or []) if isinstance(node, Mapping)]
    return element(
        "section",
        heading(2, title),
        element(
            "ul",
            *[
                element(
                    "li",
                    element(
                        "a",
                        str(node.get("name") or node.get("node_id", "")),
                        href=f"/memory/topology?service={node.get('node_id', '')}",
                    ),
                )
                for node in found
            ],
        )
        if found
        else element("p", context.text("common.none"), class_="muted"),
        aria_label=title,
    )


def _radius(context: PageContext, radius: Any) -> Element:
    """Return the blast radius, nearest first, with hop distances."""
    entries = [entry for entry in (radius or []) if isinstance(entry, Mapping)]
    return element(
        "section",
        heading(2, context.text("memory.blast_radius")),
        table(
            caption=context.text("memory.blast_radius"),
            columns=["Service", "Hops"],
            rows=[
                [
                    str(
                        (entry.get("node") or {}).get("name")
                        or (entry.get("node") or {}).get("node_id", "")
                    ),
                    str(entry.get("depth", "")),
                ]
                for entry in entries
            ],
            empty=context.text("common.none"),
        ),
        aria_label=context.text("memory.blast_radius"),
    )


def knowledge_body(
    context: PageContext,
    documents: Sequence[Mapping[str, Any]],
    *,
    proposals: Sequence[Mapping[str, Any]] = (),
) -> Element:
    """Return the knowledge corpus and the proposals awaiting review (FR-015)."""
    return element(
        "div",
        heading(1, context.text("knowledge.heading")),
        table(
            caption=context.text("knowledge.heading"),
            columns=["Document", "Source", "Updated"],
            rows=[
                [
                    element(
                        "a",
                        str(document.get("title", "")),
                        href=f"/knowledge/{document.get('document_id', '')}",
                    ),
                    value_or_dash(context, document.get("source_uri")),
                    value_or_dash(context, document.get("updated_at")),
                ]
                for document in documents
            ],
            empty=context.text("knowledge.empty"),
        ),
        _proposals(context, proposals),
    )


def _proposals(context: PageContext, proposals: Sequence[Mapping[str, Any]]) -> Element | None:
    """Return the agent's proposed knowledge, each with the run that proposed it."""
    if not proposals:
        return None
    return element(
        "section",
        heading(2, context.text("knowledge.proposals")),
        *[_proposal_card(context, proposal) for proposal in proposals],
        aria_label=context.text("knowledge.proposals"),
    )


def _proposal_card(context: PageContext, proposal: Mapping[str, Any]) -> Element:
    """Return one proposal with the investigation that produced it visible."""
    proposal_id = str(proposal.get("proposal_id", ""))
    return card(
        heading(3, str(proposal.get("title", ""))),
        element("p", str(proposal.get("summary", ""))),
        definitions(
            [(context.text("knowledge.proposal_from"), _run_link(context, proposal.get("run_id")))]
        ),
        action_control(
            context.viewer,
            Action.REVIEW_PROPOSAL,
            lambda: form(
                element(
                    "button",
                    context.text("knowledge.approve"),
                    type="submit",
                    name="decision",
                    value="accept",
                    class_="primary",
                ),
                element(
                    "button",
                    context.text("knowledge.reject"),
                    type="submit",
                    name="decision",
                    value="reject",
                ),
                action=f"/knowledge/proposals/{proposal_id}",
                label=context.text("knowledge.approve"),
            ),
        ),
        data_proposal=proposal_id,
    )


__all__ = [
    "knowledge_body",
    "memory_body",
    "strategy_card",
    "topology_body",
]
