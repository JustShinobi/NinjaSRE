"""Which source answers which question about one resource, and by what key.

An investigation that reaches the wrong source does not fail. It succeeds, with
citations, about something else — and that is a worse outcome than an error,
because nothing downstream can tell the difference.

The case this module exists for is a container. An LXC guest shares the host's
kernel: the counters visible inside it are the host's, seen through a namespace
that was never built to report them, so "how much memory is this container
using" answered from inside is answered wrongly. Plausibly. Consistently. By a
call that returned 200. The correct answer is the *host's* own series for that
guest, keyed by the guest's numeric identifier — which is a rule about
correctness rather than about configuration, and belongs somewhere a test can
reach it.

Three properties hold everything else together.

**It is derived, never stored.** From the resource's kind, what discovered it,
and which integrations this deployment has configured. Storing a map per
resource means a map that is right on the day it was written; a deployment that
adds a log store would have to remember to rewrite every row.

**An absence is named.** A question with no configured source resolves to a gap
carrying the integrations that *would* answer it, not to an empty field. "No log
store is configured — loki or openobserve would answer this" is something an
operator acts on; a blank reads as "there are no logs".

**Every question is accounted for exactly once.** Answered or named, never both
and never neither, so a surface rendering the map cannot show a hole that means
"we did not consider it" beside one that means "there is nothing".

This module names integrations as strings. It has to: the estate is tier 3 and
the vendor packages are tier 2, and a signal map that imported them would be the
platform depending on which vendors happen to be installed.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from typing import Any, Final

from config.constants.signals import (
    SIGNAL_KEY_INSTANCE,
    SIGNAL_KEY_NAME,
    SIGNAL_KEY_VMID,
    SIGNAL_QUESTION_DASHBOARDS,
    SIGNAL_QUESTION_FIRING,
    SIGNAL_QUESTION_LOGS,
    SIGNAL_QUESTION_PRESSURE,
    SIGNAL_QUESTION_TRACES,
    SIGNAL_QUESTION_UP,
    SIGNAL_QUESTIONS,
)
from platform.estate.kinds import (
    KIND_CONTAINER,
    KIND_NODE,
    KIND_VIRTUAL_MACHINE,
)
from platform.persistence.ports.estate_repository import Resource

#: The attribute a hypervisor guest carries its own numeric identifier in. The
#: key every host-side series for that guest is labelled with, and the reason it
#: is a declared attribute rather than something parsed back out of an
#: identifier: a query built from a string somebody split is a query that
#: silently returns nothing the day the format changes.
VMID_ATTRIBUTE: Final = "vmid"

#: Where on the network a resource sits. What a scrape target is labelled with,
#: for the kinds that are scraped directly.
ADDRESS_ATTRIBUTE: Final = "address"

#: The kinds that are guests of a hypervisor, and therefore the kinds whose
#: resource usage is the host's to report.
GUEST_KINDS: Final[tuple[str, ...]] = (KIND_CONTAINER, KIND_VIRTUAL_MACHINE)


@dataclass(frozen=True, slots=True)
class SignalSource:
    """The source that answers one question about one resource, and how to ask.

    ``keyed_by`` and ``key`` together are what make this more than a pointer at
    a vendor. A metric store holds a series for every guest on the cluster, and
    the difference between the right answer and a plausible wrong one is which
    label the query filters on.
    """

    question: str
    integration: str
    keyed_by: str
    key: str
    detail: str

    def to_record(self) -> dict[str, str]:
        """Return the JSON-serialisable form a surface renders."""
        return {
            "question": self.question,
            "integration": self.integration,
            "keyed_by": self.keyed_by,
            "key": self.key,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class MissingSignal:
    """A question nothing configured can answer, and what would answer it."""

    question: str
    wanted: tuple[str, ...]
    why: str

    def to_record(self) -> dict[str, object]:
        """Return the JSON-serialisable form a surface renders."""
        return {"question": self.question, "wanted": list(self.wanted), "why": self.why}


@dataclass(frozen=True, slots=True)
class SignalMap:
    """Every question about one resource, answered or named."""

    resource_id: str
    sources: tuple[SignalSource, ...] = ()
    missing: tuple[MissingSignal, ...] = ()

    def source_for(self, question: str) -> SignalSource | None:
        """Return what answers ``question``, or ``None`` when nothing does."""
        return next((source for source in self.sources if source.question == question), None)

    def missing_for(self, question: str) -> MissingSignal | None:
        """Return the named gap for ``question``, or ``None`` when it is answered."""
        return next((gap for gap in self.missing if gap.question == question), None)

    def answers(self, question: str) -> bool:
        """Return whether a configured source answers ``question``."""
        return self.source_for(question) is not None

    @property
    def integrations(self) -> tuple[str, ...]:
        """Return every integration this map points at, in name order."""
        return tuple(sorted({source.integration for source in self.sources}))

    def to_record(self) -> dict[str, object]:
        """Return the JSON-serialisable form a route serves and a screen renders."""
        return {
            "resource_id": self.resource_id,
            "sources": [source.to_record() for source in self.sources],
            "missing": [gap.to_record() for gap in self.missing],
        }


@dataclass(frozen=True, slots=True)
class SignalRule:
    """How one question is answered, for the kinds it applies to.

    ``integrations`` is in preference order rather than a set: two log stores
    both hold the line, and an investigation that queried both would pay twice
    to read the same thing. The first configured one wins, and the rest are
    still named in the gap when none of them is.
    """

    question: str
    integrations: tuple[str, ...]
    keyed_by: str
    detail: str
    #: Empty means every kind. Named kinds mean this rule applies to those only,
    #: and a resource of another kind gets the rule's ``inapplicable`` sentence.
    kinds: tuple[str, ...] = ()
    inapplicable: str = ""

    def applies_to(self, kind: str) -> bool:
        """Return whether this rule speaks about ``kind`` at all."""
        return not self.kinds or kind in self.kinds


#: Why the container rule is the way it is, said once, in the entry an operator
#: reads rather than only in this file's docstring.
_LXC_RULE: Final = (
    "an LXC container shares the host's kernel, so its CPU, memory, disk and network "
    "counters are the host's to report — read from inside the guest they describe "
    "cgroup accounting through a namespace that was never built to publish it, and the "
    "wrong number comes back looking exactly like the right one. The host-side exporter "
    "series, keyed by this guest's own identifier, is the answer"
)

_VM_RULE: Final = (
    "read from the host-side exporter series keyed by this guest's own identifier, which "
    "is what the hypervisor publishes and what agrees with what the hypervisor enforces"
)

_NODE_RULE: Final = (
    "a node is the host, so its own exporter is the source and its address is what the "
    "scrape target is labelled with"
)

#: The rules, as data. Ordered as a resource page reads them.
DEFAULT_RULES: Final[tuple[SignalRule, ...]] = (
    SignalRule(
        question=SIGNAL_QUESTION_PRESSURE,
        integrations=("prometheus",),
        keyed_by=SIGNAL_KEY_VMID,
        detail=_LXC_RULE,
        kinds=(KIND_CONTAINER,),
    ),
    SignalRule(
        question=SIGNAL_QUESTION_PRESSURE,
        integrations=("prometheus",),
        keyed_by=SIGNAL_KEY_VMID,
        detail=_VM_RULE,
        kinds=(KIND_VIRTUAL_MACHINE,),
    ),
    SignalRule(
        question=SIGNAL_QUESTION_PRESSURE,
        integrations=("prometheus",),
        keyed_by=SIGNAL_KEY_INSTANCE,
        detail=_NODE_RULE,
        kinds=(KIND_NODE,),
    ),
    SignalRule(
        question=SIGNAL_QUESTION_LOGS,
        integrations=("loki", "openobserve"),
        keyed_by=SIGNAL_KEY_NAME,
        detail="log lines this resource wrote, matched on the name it ships them under",
    ),
    SignalRule(
        question=SIGNAL_QUESTION_TRACES,
        integrations=("signoz",),
        keyed_by=SIGNAL_KEY_NAME,
        detail="spans this resource emitted, for a workload that carries OTLP instrumentation",
    ),
    SignalRule(
        question=SIGNAL_QUESTION_FIRING,
        integrations=("alertmanager",),
        keyed_by=SIGNAL_KEY_NAME,
        detail="what is complaining about this resource right now",
    ),
    SignalRule(
        question=SIGNAL_QUESTION_DASHBOARDS,
        integrations=("grafana",),
        keyed_by=SIGNAL_KEY_NAME,
        detail="what a person would open to look at this",
    ),
)

#: What a *pressure* question resolves to for a kind no rule speaks about. Said
#: rather than omitted: a blank on a datastore's page reads as "under no
#: pressure", which is a claim nobody made.
_NO_PRESSURE_RULE: Final = (
    "no exporter publishes a resource-usage series for this kind of thing, so pressure "
    "is not a question this estate can answer about it — its capacity is part of what "
    "the provider reports about it directly"
)


def signal_map_for(resource: Resource, *, configured: Collection[str]) -> SignalMap:
    """Return which configured source answers each question about ``resource``.

    ``configured`` is the set of integrations this deployment holds a working
    credential for. Taken as an argument rather than discovered, because "which
    integrations does this team have" is a tenant question and a platform module
    that answered it from what happened to be installed would report a map
    pointing at vendors nobody configured.
    """
    available = set(configured)
    sources: list[SignalSource] = []
    missing: list[MissingSignal] = []

    _resolve_up(resource, available, sources, missing)
    for question in SIGNAL_QUESTIONS:
        if question == SIGNAL_QUESTION_UP:
            continue
        _resolve(question, resource, available, sources, missing)

    order = {question: index for index, question in enumerate(SIGNAL_QUESTIONS)}
    return SignalMap(
        resource_id=resource.resource_id,
        sources=tuple(sorted(sources, key=lambda source: order[source.question])),
        missing=tuple(sorted(missing, key=lambda gap: order[gap.question])),
    )


def _resolve_up(
    resource: Resource,
    available: set[str],
    sources: list[SignalSource],
    missing: list[MissingSignal],
) -> None:
    """Resolve "is it running" against whatever declares the resource exists.

    Not a rule in the table, because the answer is a property of the resource
    rather than of the deployment: the integration that discovered a thing is
    the one that reports its state, whichever integration that happens to be.
    That is what makes this question answerable for every resource in every
    estate rather than only for the ones a rule anticipated.
    """
    owner = resource.source
    if owner in available:
        sources.append(
            SignalSource(
                question=SIGNAL_QUESTION_UP,
                integration=owner,
                keyed_by=SIGNAL_KEY_NAME,
                key=resource.native_id or resource.resource_id,
                detail=(
                    f"{owner} discovered this resource and reports its state, which is the "
                    f"provider's own answer rather than a synthetic check of it"
                ),
            )
        )
        return
    missing.append(
        MissingSignal(
            question=SIGNAL_QUESTION_UP,
            wanted=(owner,) if owner else (),
            why=(
                f"{owner or 'the integration that discovered this'} is no longer configured, so "
                f"nothing here can say whether this resource is running — what is on this page "
                f"is the last thing it said before the credential went away"
            ),
        )
    )


def _resolve(
    question: str,
    resource: Resource,
    available: set[str],
    sources: list[SignalSource],
    missing: list[MissingSignal],
) -> None:
    """Resolve one question against the rules, and name it when nothing answers."""
    rules = [rule for rule in DEFAULT_RULES if rule.question == question]
    applicable = [rule for rule in rules if rule.applies_to(resource.kind)]
    if not applicable:
        missing.append(MissingSignal(question=question, wanted=(), why=_NO_PRESSURE_RULE))
        return

    rule = applicable[0]
    for integration in rule.integrations:
        if integration not in available:
            continue
        key = _key_for(rule.keyed_by, resource)
        if not key:
            missing.append(
                MissingSignal(
                    question=question,
                    wanted=(integration,),
                    why=(
                        f"{integration} is configured and this resource carries no "
                        f"{rule.keyed_by}, so there is no label to filter its series on. A "
                        f"query built without one returns nothing, which reads as an answer"
                    ),
                )
            )
            return
        sources.append(
            SignalSource(
                question=question,
                integration=integration,
                keyed_by=rule.keyed_by,
                key=key,
                detail=rule.detail,
            )
        )
        return

    missing.append(
        MissingSignal(
            question=question,
            wanted=rule.integrations,
            why=(
                f"nothing configured answers this. "
                f"{_listed(rule.integrations)} would: {rule.detail}"
            ),
        )
    )


def _key_for(keyed_by: str, resource: Resource) -> str:
    """Return the value a query for ``resource`` filters on, or the empty string."""
    attributes: dict[str, Any] = dict(resource.attributes)
    if keyed_by == SIGNAL_KEY_VMID:
        if resource.kind not in GUEST_KINDS:
            return ""
        return str(attributes.get(VMID_ATTRIBUTE) or "")
    if keyed_by == SIGNAL_KEY_INSTANCE:
        return str(attributes.get(ADDRESS_ATTRIBUTE) or "")
    return resource.display_name or resource.resource_id


def _listed(names: tuple[str, ...]) -> str:
    """Return ``names`` as prose: "a", "a or b", "a, b, or c"."""
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} or {names[1]}"
    return ", ".join(names[:-1]) + f", or {names[-1]}"


__all__ = [
    "ADDRESS_ATTRIBUTE",
    "DEFAULT_RULES",
    "GUEST_KINDS",
    "VMID_ATTRIBUTE",
    "MissingSignal",
    "SignalMap",
    "SignalRule",
    "SignalSource",
    "signal_map_for",
]
