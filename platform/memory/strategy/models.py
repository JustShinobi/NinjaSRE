"""A playbook: what N episodes of the same failure add up to, and where it came from.

An episode is an anecdote. A strategy is what a set of them says together — the
causes that recur, the order of investigation that worked, the capabilities that
produced findings, and the approaches that looked promising and did not.

Two fields carry most of this module's weight.

**``source_episode_ids``.** Every claim in a playbook is a generalisation over
runs, and a generalisation with no way back to its inputs is an assertion.
Recording the ids makes a wrong playbook diagnosable: an operator reading a
recommendation that makes no sense can go and read the five investigations it was
drawn from, and usually finds that four of them were the same misdiagnosis.
``anti_pattern_episode_ids`` narrows that further for the section most likely to
be argued with.

**``prompt_version``.** A playbook is the output of a prompt over a set of
episodes, so it can change for two reasons and they need telling apart. Without
the version on the record, editing the synthesis prompt silently reinterprets
every cached playbook in the deployment and the quality shift has no attributable
cause.

Operator edits are kept beside the generated sections rather than merged into
them. A human correcting a playbook is the highest-quality signal this system
receives, and the next regeneration must neither lose it nor be unable to tell it
apart from what the model produced.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from config.constants.memory import (
    MAX_STRATEGY_ITEM_CHARS,
    MAX_STRATEGY_OPERATOR_EDITS,
    MAX_STRATEGY_SECTION_ITEMS,
    STRATEGY_MAX_AGE_DAYS,
)
from platform.memory.models import COMPONENT_SEPARATOR, ScoredEpisode
from platform.persistence.ports.episode_store import StoredStrategy

#: Separates the issue type from the component key in the label a strategy is
#: identified by in a trace, in the shaped recall result, and in the console.
#: A slash, because neither half can contain one — the component key's own
#: separator is a colon and an issue type is a lowercase token.
STRATEGY_LABEL_SEPARATOR = "/"

#: Prefixes that label, so a run's answer citing a playbook is distinguishable
#: from one citing an episode. The recall ledger matches on this string.
STRATEGY_REFERENCE_PREFIX = "strategy"


class StrategySection(StrEnum):
    """The four sections a playbook has, in the order it presents them.

    Ordered deliberately, and the order is an argument. Causes first, because
    they are what the reader is trying to establish; steps second, because they
    are what the reader will do next; capabilities third, because they are how;
    and anti-patterns last, because they are read against everything above them —
    "and here is what did not work" only means something once the reader knows
    what did.
    """

    ROOT_CAUSES = "common_root_causes"
    INVESTIGATION_STEPS = "recommended_investigation_steps"
    CAPABILITIES = "key_capabilities"
    ANTI_PATTERNS = "anti_patterns"


@dataclass(frozen=True, slots=True)
class StrategyKey:
    """What a playbook is about: one team's experience of one failure on one subject.

    The organisation is in the key even though no repository method takes one.
    That is not redundancy — it is what lets a key be passed between the memory
    service, the cache, and the invalidation hook as a single value without any
    of them having to remember which tenant it belonged to.
    """

    org_id: str
    team_node_id: str
    issue_type: str
    component_key: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "issue_type", self.issue_type.strip().lower())
        object.__setattr__(self, "component_key", self.component_key.strip().lower())
        if not self.org_id or not self.team_node_id:
            raise ValueError(
                "a strategy must be scoped to an organisation and a team — an "
                "unscoped playbook is one every team can read"
            )
        if not self.issue_type or not self.component_key:
            raise ValueError(
                "a strategy needs both an issue type and a component key: a playbook "
                "for 'anything that went wrong on anything' generalises over episodes "
                "that have nothing in common"
            )

    @property
    def label(self) -> str:
        """Return the identifier this playbook is cited by."""
        return (
            f"{STRATEGY_REFERENCE_PREFIX}{COMPONENT_SEPARATOR}"
            f"{self.issue_type}{STRATEGY_LABEL_SEPARATOR}{self.component_key}"
        )

    def matches(self, other: StrategyKey) -> bool:
        """Return whether ``other`` names the same playbook."""
        return self == other


@dataclass(frozen=True, slots=True)
class OperatorEdit:
    """A human amendment to a playbook, preserved across regeneration.

    Kept as an addition rather than as a rewrite of the section it corrects. A
    rewrite would be indistinguishable from generated text at the next
    regeneration and would either be lost or silently attributed to the model;
    an addition survives both, and the reader can see who said it.
    """

    author: str
    note: str
    edited_at: datetime | None = None
    section: StrategySection | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "author", self.author.strip() or "unattributed")
        object.__setattr__(self, "note", self.note.strip()[:MAX_STRATEGY_ITEM_CHARS])
        if not self.note:
            raise ValueError("an operator edit must say something")

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this edit."""
        return {
            "author": self.author,
            "note": self.note,
            "edited_at": self.edited_at.isoformat() if self.edited_at else None,
            "section": self.section.value if self.section else None,
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> OperatorEdit:
        """Return the edit a stored record describes."""
        return cls(
            author=str(record.get("author", "")),
            note=str(record.get("note", "")),
            edited_at=_moment(record.get("edited_at")),
            section=_section(record.get("section")),
        )


def bounded(items: Iterable[str]) -> tuple[str, ...]:
    """Return ``items`` trimmed, de-duplicated, and cut to the section bounds."""
    seen: dict[str, None] = {}
    for item in items:
        text = str(item).strip()[:MAX_STRATEGY_ITEM_CHARS]
        if text:
            seen.setdefault(text, None)
    return tuple(seen)[:MAX_STRATEGY_SECTION_ITEMS]


@dataclass(frozen=True, slots=True)
class Strategy:
    """One synthesised playbook, with everything needed to weigh it.

    ``episode_count`` and the date range are not decoration. A playbook drawn
    from three investigations last week and one drawn from twenty over a year
    deserve different amounts of trust, and an agent shown neither number has no
    way to apply any. They travel with the playbook to the model for that reason.
    """

    key: StrategyKey
    root_causes: tuple[str, ...] = ()
    investigation_steps: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    anti_patterns: tuple[str, ...] = ()
    source_episode_ids: tuple[str, ...] = ()
    anti_pattern_episode_ids: tuple[str, ...] = ()
    episode_count: int = 0
    earliest_episode_at: datetime | None = None
    latest_episode_at: datetime | None = None
    generated_at: datetime | None = None
    prompt_version: int = 0
    operator_edits: tuple[OperatorEdit, ...] = ()
    guardrail_rules_fired: tuple[str, ...] = ()
    stale: bool = False

    def __post_init__(self) -> None:
        for name in ("root_causes", "investigation_steps", "capabilities", "anti_patterns"):
            object.__setattr__(self, name, bounded(getattr(self, name)))
        object.__setattr__(
            self, "operator_edits", tuple(self.operator_edits[-MAX_STRATEGY_OPERATOR_EDITS:])
        )

    # -- what it says ----------------------------------------------------------

    @property
    def usable(self) -> bool:
        """Return whether there is enough here to be worth showing anybody.

        A playbook whose every section came back empty is a synthesis call that
        produced nothing. Storing it would spend a cache entry to serve the model
        four empty headings, and would suppress the regeneration that might have
        produced something.
        """
        return bool(
            self.root_causes or self.investigation_steps or self.capabilities or self.anti_patterns
        )

    def sections(self) -> dict[StrategySection, tuple[str, ...]]:
        """Return the four sections in presentation order."""
        return {
            StrategySection.ROOT_CAUSES: self.root_causes,
            StrategySection.INVESTIGATION_STEPS: self.investigation_steps,
            StrategySection.CAPABILITIES: self.capabilities,
            StrategySection.ANTI_PATTERNS: self.anti_patterns,
        }

    def age_days(self, now: datetime) -> float:
        """Return how old this playbook is, or ``inf`` when it never recorded a time."""
        if self.generated_at is None:
            return float("inf")
        return (now - self.generated_at).total_seconds() / timedelta(days=1).total_seconds()

    def expired(self, now: datetime) -> bool:
        """Return whether age alone is reason enough to regenerate."""
        return self.age_days(now) >= STRATEGY_MAX_AGE_DAYS

    def fresh(self, now: datetime) -> bool:
        """Return whether this playbook may be served without regenerating it."""
        return not self.stale and not self.expired(now)

    # -- operator edits --------------------------------------------------------

    def with_edit(self, edit: OperatorEdit) -> Strategy:
        """Return this playbook carrying one more operator amendment."""
        return replace(self, operator_edits=(*self.operator_edits, edit))

    def carrying_edits_from(self, earlier: Strategy | None) -> Strategy:
        """Return this freshly generated playbook with ``earlier``'s edits preserved.

        A requirement rather than a nicety: an operator whose correction
        disappears at the next regeneration learns that correcting playbooks is
        wasted effort, and stops. The edits are appended
        rather than merged, so they remain attributable and remain visibly
        separate from what this generation produced.
        """
        if earlier is None or not earlier.operator_edits:
            return self
        return replace(self, operator_edits=(*earlier.operator_edits, *self.operator_edits))

    # -- storage ---------------------------------------------------------------

    def content(self) -> dict[str, Any]:
        """Return the payload the stored row keeps."""
        return {
            StrategySection.ROOT_CAUSES.value: list(self.root_causes),
            StrategySection.INVESTIGATION_STEPS.value: list(self.investigation_steps),
            StrategySection.CAPABILITIES.value: list(self.capabilities),
            StrategySection.ANTI_PATTERNS.value: list(self.anti_patterns),
            "source_episode_ids": list(self.source_episode_ids),
            "anti_pattern_episode_ids": list(self.anti_pattern_episode_ids),
            "episode_count": self.episode_count,
            "earliest_episode_at": _iso(self.earliest_episode_at),
            "latest_episode_at": _iso(self.latest_episode_at),
            "prompt_version": self.prompt_version,
            "operator_edits": [edit.to_record() for edit in self.operator_edits],
            "guardrail_rules_fired": list(self.guardrail_rules_fired),
        }

    def to_stored(self) -> StoredStrategy:
        """Return this playbook in the shape ``EpisodeStore`` persists."""
        return StoredStrategy(
            team_node_id=self.key.team_node_id,
            issue_type=self.key.issue_type,
            component_key=self.key.component_key,
            content=self.content(),
            generated_at=self.generated_at,
            stale=self.stale,
        )

    @classmethod
    def from_stored(cls, stored: StoredStrategy, *, org_id: str) -> Strategy:
        """Return the domain playbook a stored row describes.

        ``org_id`` comes from the unit of work rather than from the row, for the
        same reason it does for an episode: no port method takes an organisation,
        so the only honest source is the scope the row was read under.
        """
        content = dict(stored.content)
        return cls(
            key=StrategyKey(
                org_id=org_id,
                team_node_id=stored.team_node_id,
                issue_type=stored.issue_type,
                component_key=stored.component_key,
            ),
            root_causes=_items(content.get(StrategySection.ROOT_CAUSES.value)),
            investigation_steps=_items(content.get(StrategySection.INVESTIGATION_STEPS.value)),
            capabilities=_items(content.get(StrategySection.CAPABILITIES.value)),
            anti_patterns=_items(content.get(StrategySection.ANTI_PATTERNS.value)),
            source_episode_ids=_items(content.get("source_episode_ids")),
            anti_pattern_episode_ids=_items(content.get("anti_pattern_episode_ids")),
            episode_count=int(content.get("episode_count", 0) or 0),
            earliest_episode_at=_moment(content.get("earliest_episode_at")),
            latest_episode_at=_moment(content.get("latest_episode_at")),
            generated_at=stored.generated_at,
            prompt_version=int(content.get("prompt_version", 0) or 0),
            operator_edits=tuple(
                OperatorEdit.from_record(record)
                for record in content.get("operator_edits") or ()
                if isinstance(record, Mapping) and str(record.get("note", "")).strip()
            ),
            guardrail_rules_fired=_items(content.get("guardrail_rules_fired")),
            stale=stored.stale,
        )


@dataclass(frozen=True, slots=True)
class SynthesisInput:
    """The scored episodes feeding one generation, and what they say about themselves.

    A separate type rather than a bare sequence, because the split that matters
    to synthesis — which episodes established a cause and which did not — is
    computed once, here, and read by the prompt, by the anti-pattern
    attribution, and by the date range. Recomputing it at each of those is how
    the playbook comes to claim anti-patterns from episodes that resolved.
    """

    key: StrategyKey
    resolved: tuple[ScoredEpisode, ...] = ()
    unresolved: tuple[ScoredEpisode, ...] = ()

    @property
    def episodes(self) -> tuple[ScoredEpisode, ...]:
        """Return every episode in the set, resolved first."""
        return (*self.resolved, *self.unresolved)

    @property
    def count(self) -> int:
        """Return how many episodes this generation was drawn from."""
        return len(self.resolved) + len(self.unresolved)

    @property
    def source_episode_ids(self) -> tuple[str, ...]:
        """Return every episode this generation may cite."""
        return tuple(found.correlation_id for found in self.episodes)

    @property
    def anti_pattern_episode_ids(self) -> tuple[str, ...]:
        """Return the episodes the anti-patterns section may be drawn from.

        The unresolved half, and only that half. The provenance of this one
        section is a requirement, because the way a synthesis prompt goes wrong is
        by generalising a dead end from a run that in fact found the cause.
        """
        return tuple(found.correlation_id for found in self.unresolved)

    def range(self) -> tuple[datetime | None, datetime | None]:
        """Return the span of time these episodes cover."""
        return date_range([found.episode.occurred_at for found in self.episodes])


def _items(value: Any) -> tuple[str, ...]:
    """Return a stored list as text, dropping anything unusable."""
    if not isinstance(value, list):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


def _iso(moment: datetime | None) -> str | None:
    """Return ``moment`` as text, or ``None``."""
    return moment.isoformat() if moment else None


def _moment(value: Any) -> datetime | None:
    """Return the instant a stored string describes, or ``None``.

    A malformed timestamp costs the field rather than the playbook. The two
    fields this reads feed a date range shown to the agent and an age check that
    already treats "no time recorded" as expired, so both degrade to the
    conservative answer.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _section(value: Any) -> StrategySection | None:
    """Return the section a stored string names, or ``None``."""
    try:
        return StrategySection(str(value))
    except ValueError:
        return None


def date_range(moments: Sequence[datetime | None]) -> tuple[datetime | None, datetime | None]:
    """Return the earliest and latest of ``moments``, ignoring the missing ones."""
    known = sorted(moment for moment in moments if moment is not None)
    return (known[0], known[-1]) if known else (None, None)


__all__ = [
    "STRATEGY_LABEL_SEPARATOR",
    "STRATEGY_REFERENCE_PREFIX",
    "OperatorEdit",
    "Strategy",
    "StrategyKey",
    "StrategySection",
    "SynthesisInput",
    "bounded",
    "date_range",
]
