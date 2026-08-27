"""One investigation, reduced to what a later one would want to know.

Two types called "episode" exist in this repository and the difference matters.
``platform.persistence.ports.episode_store.Episode`` is the *stored row* — a
narrow, backend-facing record with a title, a summary, an outcome, and a JSON
payload. ``MemoryEpisode`` here is the *domain* record: typed components, typed
findings, a severity, an effectiveness score, and the formula version that
produced it. This module owns the translation between them, in one place, so
that the storage layer never learns what a key finding is and nothing above it
has to remember which fields live in the payload.

The one definition worth reading before anything else:

**``resolved`` means a root cause was established with evidence behind it. It
does not mean production was fixed.** Conflating those makes the flag a claim
nothing in this process can check, and it makes ranking meaningless — an episode
promoted for "resolved" would be promoted for somebody having restarted a pod.
The distinction is stated on the field, in the extraction prompt, in the shaped
recall result the agent reads, and in the operator documentation, because a flag
whose meaning is written down in only one of those places is a flag that will be
misread in the other three.

Unresolved episodes are kept. An investigation that failed to reach a cause is
the raw material for knowing what does not work, and a corpus of successes only
measures how well the system does on incidents it already handles.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import blake2b
from typing import Any

from config.constants.memory import (
    EFFECTIVENESS_FORMULA_VERSION,
    MAX_EPISODE_COMPONENTS,
    MAX_EPISODE_KEY_FINDINGS,
    MAX_EPISODE_SUMMARY_CHARS,
    RANKING_FORMULA_VERSION,
)
from platform.persistence.ports.episode_store import Episode, EpisodeOutcome

#: Separates a component's type from its name in the flat label the storage
#: layer and the vector metadata use. A colon, because no component type or name
#: in any vendor's namespace contains one.
COMPONENT_SEPARATOR = ":"

#: Length of the hex signature an episode is fingerprinted with. Sixteen
#: characters is far past collision risk for one team's corpus and short enough
#: to read in a trace.
SIGNATURE_LENGTH = 16


class EpisodeSeverity(StrEnum):
    """How bad the failure this episode records was.

    ``UNKNOWN`` is a real member rather than an absence. Extraction routinely
    cannot tell, and a corpus where "not stated" was silently written down as
    "low" would rank genuinely minor incidents alongside ones nobody classified.
    """

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"

    @classmethod
    def parse(cls, value: str) -> EpisodeSeverity:
        """Return the member ``value`` names, or ``UNKNOWN``."""
        try:
            return cls(str(value).strip().lower())
        except ValueError:
            return cls.UNKNOWN


class IssueType(StrEnum):
    """The closed set of failure classes an episode may be filed under.

    A corpus is only searchable to the extent that two people describing the
    same failure choose the same word for it, and two free-text guesses made at
    different moments do not. One deployment wrote ``manual_shutdown`` for a
    container somebody powered off and searched for ``ProxmoxGuestStopped``
    forty-four seconds later; both are reasonable English for the same event and
    neither matched the other.

    So the extractor picks from this list and the recall capability searches
    within it, and ``classify`` maps whatever either end says onto it. The set is
    deliberately coarse — a dozen or so buckets, each one a class of failure with
    a different investigation attached to it. Finer than that and it is free text
    again with extra steps; coarser and every incident is one bucket.

    ``OTHER`` is a real member and not a failure. A failure nobody anticipated is
    still worth remembering, and an episode dropped for being unclassifiable is
    the one case where the corpus loses exactly the incident nobody has seen
    before. The words the classifier could not place are kept beside it, on
    ``MemoryEpisode.issue_label``, rather than discarded.
    """

    OOM_KILL = "oom_kill"
    CRASH_LOOP = "crash_loop"
    WORKLOAD_STOPPED = "workload_stopped"
    DEPLOY_REGRESSION = "deploy_regression"
    CONFIGURATION_ERROR = "configuration_error"
    RESOURCE_SATURATION = "resource_saturation"
    DISK_PRESSURE = "disk_pressure"
    CONNECTION_POOL_EXHAUSTION = "connection_pool_exhaustion"
    NETWORK_FAILURE = "network_failure"
    DEPENDENCY_FAILURE = "dependency_failure"
    CERTIFICATE_EXPIRY = "certificate_expiry"
    AUTHENTICATION_FAILURE = "authentication_failure"
    DATA_INTEGRITY = "data_integrity"
    SCHEDULED_JOB_FAILURE = "scheduled_job_failure"
    LATENCY_REGRESSION = "latency_regression"
    OTHER = "other"

    @classmethod
    def classify(cls, value: str) -> IssueType:
        """Return the member ``value`` belongs to, or ``OTHER``.

        Three passes, cheapest first. An exact match on a member's own value is
        what a caller that already picked from the list gets. Otherwise the text
        is broken into words — on punctuation *and* on camel case, because an
        alert name arrives as ``ProxmoxGuestStopped`` and an extraction as
        ``manual_shutdown`` — and scored against each member's keywords, most
        keywords matched winning. Ties go to whichever member is declared first,
        so the answer does not depend on dictionary order.

        No model call, for the same reason ranking makes none: this runs inside a
        tool call the agent is waiting on, and it has to give the same answer
        twice or a trajectory comparison means nothing.
        """
        text = value.strip().lower()
        if not text:
            return cls.OTHER
        try:
            return cls(text)
        except ValueError:
            pass

        words = frozenset(word.lower() for word in _WORD_PATTERN.findall(value))
        best, best_hits = cls.OTHER, 0
        for member, keywords in ISSUE_TYPE_KEYWORDS.items():
            hits = len(words & keywords)
            if hits > best_hits:
                best, best_hits = member, hits
        return best

    @property
    def classified(self) -> bool:
        """Return whether this is a real classification rather than the bucket."""
        return self is not IssueType.OTHER


#: Words that place a free-text failure description into a bucket. Each set is
#: the vocabulary observed in alert names, exporter labels, and the sentences a
#: model writes about that class of failure — matched as whole words, so
#: ``oom`` does not fire on ``room``.
ISSUE_TYPE_KEYWORDS: Mapping[IssueType, frozenset[str]] = {
    IssueType.OOM_KILL: frozenset(
        {"oom", "oomkill", "oomkilled", "oomkiller", "137", "memorylimit"}
    ),
    IssueType.CRASH_LOOP: frozenset(
        {"crashloop", "crashloopbackoff", "crash", "crashed", "restarting", "backoff", "panic"}
    ),
    IssueType.WORKLOAD_STOPPED: frozenset(
        {
            "stopped",
            "stop",
            "shutdown",
            "vzshutdown",
            "poweroff",
            "powered",
            "halted",
            "terminated",
            "evicted",
            "drained",
        }
    ),
    IssueType.DEPLOY_REGRESSION: frozenset(
        {"deploy", "deployment", "release", "rollout", "regression", "rollback", "canary"}
    ),
    IssueType.CONFIGURATION_ERROR: frozenset(
        {"config", "configuration", "misconfiguration", "misconfigured", "manifest", "flag"}
    ),
    IssueType.RESOURCE_SATURATION: frozenset(
        {"saturation", "saturated", "throttling", "throttled", "cpu", "quota", "exhausted"}
    ),
    IssueType.DISK_PRESSURE: frozenset(
        {"disk", "diskpressure", "volume", "filesystem", "inode", "storage", "full"}
    ),
    IssueType.CONNECTION_POOL_EXHAUSTION: frozenset(
        {"pool", "connections", "maxconnections", "toomanyconnections", "checkout"}
    ),
    IssueType.NETWORK_FAILURE: frozenset(
        {"network", "dns", "timeout", "unreachable", "refused", "packet", "resolve", "tcp"}
    ),
    IssueType.DEPENDENCY_FAILURE: frozenset(
        {"dependency", "upstream", "downstream", "502", "503", "504", "gateway"}
    ),
    IssueType.CERTIFICATE_EXPIRY: frozenset(
        {"certificate", "cert", "tls", "ssl", "expiry", "expired", "expiring", "x509"}
    ),
    IssueType.AUTHENTICATION_FAILURE: frozenset(
        {"auth", "authentication", "authorisation", "authorization", "credential", "token", "401"}
    ),
    IssueType.DATA_INTEGRITY: frozenset(
        {"corruption", "corrupt", "integrity", "checksum", "replication", "consistency"}
    ),
    IssueType.SCHEDULED_JOB_FAILURE: frozenset(
        {"cron", "cronjob", "job", "scheduled", "batch", "pipeline", "dag"}
    ),
    IssueType.LATENCY_REGRESSION: frozenset(
        {"latency", "slow", "slowness", "p95", "p99", "degradation", "degraded"}
    ),
}

#: Splits text into the words ``classify`` scores, on punctuation and on case.
#: Case matters because an alert name arrives as one token — ``ProxmoxGuestStopped``
#: lowercased whole matches nothing, and split it yields ``stopped``. A run of
#: capitals stays whole, so ``OOMKilled`` gives ``oom`` and ``killed``.
_WORD_PATTERN = re.compile(r"[A-Z]+(?![a-z])|[A-Z][a-z]+|[a-z]+|[0-9]+")


@dataclass(frozen=True, slots=True)
class Component:
    """A typed subject a failure was about — ``{type, name}``.

    ``type`` is free-form on purpose. Closing it would mean editing this module
    for every vendor that names a kind of thing NinjaSRE has not met, which is
    the single thing auto-discovery exists to avoid; and a component type nobody
    anticipated is still a useful thing to match on.
    """

    type: str
    name: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "type", self.type.strip().lower())
        object.__setattr__(self, "name", self.name.strip())
        if not self.name:
            raise ValueError("a component must have a name")

    @property
    def label(self) -> str:
        """Return the flat ``type:name`` form the storage layer holds."""
        return f"{self.type}{COMPONENT_SEPARATOR}{self.name}"

    @classmethod
    def parse(cls, label: str) -> Component:
        """Return the component a flat label describes.

        A label with no separator is a bare name of unstated type rather than an
        error: episodes written before a type was extractable are still worth
        matching on.
        """
        kind, separator, name = label.partition(COMPONENT_SEPARATOR)
        if not separator:
            return cls(type="", name=kind)
        return cls(type=kind, name=name)


@dataclass(frozen=True, slots=True)
class KeyFinding:
    """What one capability revealed, and what was asked of it.

    The capability and the query travel with the finding because that is what
    makes it reusable: a later investigation reading "the pod was OOMKilled" can
    act on it, and one reading "``kubectl_describe`` on ``payments-api`` said the
    pod was OOMKilled" can go and look.
    """

    capability: str
    query: str
    finding: str

    def to_record(self) -> dict[str, str]:
        """Return a JSON-serialisable record of this finding."""
        return {"capability": self.capability, "query": self.query, "finding": self.finding}

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> KeyFinding:
        """Return the finding a stored record describes."""
        return cls(
            capability=str(record.get("capability", "")),
            query=str(record.get("query", "")),
            finding=str(record.get("finding", "")),
        )


def _clean(values: Iterable[str]) -> tuple[str, ...]:
    """Return ``values`` stripped, de-duplicated, in first-seen order."""
    seen: dict[str, None] = {}
    for value in values:
        text = str(value).strip()
        if text:
            seen.setdefault(text, None)
    return tuple(seen)


@dataclass(frozen=True, slots=True)
class MemoryEpisode:
    """One investigation conversation, with its outcome and everything ranking reads.

    Keyed by ``correlation_id`` — one conversation, one episode, however many
    turns it took. A second turn updates this record rather than writing a
    second one, which is what makes "how many incidents has this team seen"
    answerable by counting rows.
    """

    correlation_id: str
    org_id: str
    team_node_id: str
    #: The bucket this failure was filed under: one of ``IssueType``, or the free
    #: text an episode written before the vocabulary existed still carries.
    #: ``canonical_issue_type`` is what a comparison should read, never this.
    issue_type: str = ""
    #: What the model called this failure in its own words, kept verbatim beside
    #: the bucket. A classification is what makes the corpus searchable; the
    #: words are what tell a reader which of a dozen shutdowns this one was.
    issue_label: str = ""
    issue_description: str = ""
    severity: EpisodeSeverity = EpisodeSeverity.UNKNOWN
    components: tuple[Component, ...] = ()
    capabilities_used: tuple[str, ...] = ()
    key_findings: tuple[KeyFinding, ...] = ()
    #: A root cause was established with evidence behind it. **Not** a claim that
    #: production was fixed — see the module docstring.
    resolved: bool = False
    root_cause: str = ""
    summary: str = ""
    effectiveness_score: float = 0.0
    effectiveness_formula_version: int = EFFECTIVENESS_FORMULA_VERSION
    duration_seconds: float = 0.0
    iterations: int = 0
    run_id: str = ""
    occurred_at: datetime | None = None
    updated_at: datetime | None = None
    embedding_model: str = ""
    embedding_dimension: int = 0
    guardrail_rules_fired: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.correlation_id:
            raise ValueError("an episode must be keyed by a correlation id")
        if not self.org_id or not self.team_node_id:
            raise ValueError(
                f"{self.correlation_id}: an episode must carry an organisation and a team — "
                "an unscoped episode is one every team can retrieve"
            )
        object.__setattr__(self, "components", tuple(self.components[:MAX_EPISODE_COMPONENTS]))
        object.__setattr__(
            self, "key_findings", tuple(self.key_findings[:MAX_EPISODE_KEY_FINDINGS])
        )
        object.__setattr__(self, "capabilities_used", _clean(self.capabilities_used))
        object.__setattr__(self, "summary", self.summary[:MAX_EPISODE_SUMMARY_CHARS])

    # -- derived ---------------------------------------------------------------

    @property
    def outcome(self) -> EpisodeOutcome:
        """Return the stored outcome this episode's ``resolved`` flag maps to."""
        return EpisodeOutcome.RESOLVED if self.resolved else EpisodeOutcome.INCONCLUSIVE

    @property
    def title(self) -> str:
        """Return the one-line heading the stored row carries."""
        headline = self.issue_description.strip() or self.summary.strip()
        return f"{self.issue_type}: {headline}".strip(": ") if self.issue_type else headline

    @property
    def component_labels(self) -> tuple[str, ...]:
        """Return the flat labels a metadata filter and the stored row use."""
        return tuple(component.label for component in self.components)

    @property
    def canonical_issue_type(self) -> IssueType:
        """Return the bucket this episode is comparable in.

        Derived rather than stored, so the whole corpus becomes comparable the
        day the vocabulary lands. An episode written before it holds free text in
        ``issue_type``; classifying on read means the previous six months of
        incidents are searchable under the same buckets as the next six, with no
        migration and no rewrite of rows nobody is otherwise touching.
        """
        return IssueType.classify(self.issue_type or self.issue_label)

    def embedding_text(self) -> str:
        """Return the text this episode is embedded from.

        Issue type, description, summary, and root cause — and deliberately not
        the key findings. Findings are long, vendor-shaped, and full of
        identifiers; embedding them makes two unrelated incidents on the same
        cluster look similar because they name the same nodes.
        """
        return "\n".join(
            part
            for part in (self.issue_type, self.issue_description, self.summary, self.root_cause)
            if part.strip()
        )

    def signature(self) -> str:
        """Return the fingerprint episodes of the same shape share.

        The *canonical* issue type and the components involved, which is the pair
        that makes two incidents "the same alert again" without making every
        incident on one service the same incident. Canonical rather than
        verbatim, because a fingerprint built from free text fingerprints the
        wording: the same alert extracted once as ``manual_shutdown`` and once as
        ``ProxmoxGuestStopped`` would hash to two different incidents.

        Components are still the words the run used, so two episodes that named
        the same container ``container:lxc/122`` and ``guest:lxc/122`` remain
        distinct fingerprints. Closing that vocabulary too is a separate problem
        and this method does not pretend to have solved it.
        """
        return fingerprint(self.canonical_issue_type, self.components)

    def merged_with(self, earlier: MemoryEpisode) -> MemoryEpisode:
        """Return this episode carrying ``earlier``'s capability history too.

        A second turn in the same conversation sees only its own tool calls, and
        an episode that forgot the first turn's would under-report the trajectory
        the next investigation is meant to reuse. Order is preserved and
        duplicates are dropped — the earlier turn's calls happened first.
        """
        return replace(
            self,
            capabilities_used=_clean((*earlier.capabilities_used, *self.capabilities_used)),
            occurred_at=earlier.occurred_at or self.occurred_at,
        )

    # -- storage ---------------------------------------------------------------

    def payload(self) -> dict[str, Any]:
        """Return the fields the stored row keeps in its JSON payload."""
        return {
            "issue_type": self.issue_type,
            "issue_label": self.issue_label,
            "issue_description": self.issue_description,
            "severity": self.severity.value,
            "capabilities_used": list(self.capabilities_used),
            "key_findings": [finding.to_record() for finding in self.key_findings],
            "resolved": self.resolved,
            "effectiveness_score": self.effectiveness_score,
            "effectiveness_formula_version": self.effectiveness_formula_version,
            "duration_seconds": self.duration_seconds,
            "iterations": self.iterations,
            "team_node_id": self.team_node_id,
            "embedding_model": self.embedding_model,
            "embedding_dimension": self.embedding_dimension,
            "guardrail_rules_fired": list(self.guardrail_rules_fired),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def to_stored(self) -> Episode:
        """Return this episode in the shape ``EpisodeStore`` persists."""
        return Episode(
            episode_id=self.correlation_id,
            title=self.title,
            summary=self.summary,
            signature=self.signature(),
            outcome=self.outcome,
            run_id=self.run_id or None,
            occurred_at=self.occurred_at,
            components=self.component_labels,
            tags=(self.severity.value,) if self.severity is not EpisodeSeverity.UNKNOWN else (),
            resolution=self.root_cause or None,
            metadata=self.payload(),
        )

    @classmethod
    def from_stored(cls, stored: Episode, *, org_id: str) -> MemoryEpisode:
        """Return the domain episode a stored row describes.

        ``org_id`` comes from the unit of work rather than from the row: no port
        method takes an organisation, so the only honest source for it is the
        scope the row was read under.
        """
        payload = dict(stored.metadata)
        updated = payload.get("updated_at")
        return cls(
            correlation_id=stored.episode_id,
            org_id=org_id,
            team_node_id=str(payload.get("team_node_id", "")),
            issue_type=str(payload.get("issue_type", "")),
            issue_label=str(payload.get("issue_label", "")),
            issue_description=str(payload.get("issue_description", "")),
            severity=EpisodeSeverity.parse(str(payload.get("severity", ""))),
            components=tuple(Component.parse(label) for label in stored.components),
            capabilities_used=tuple(str(name) for name in payload.get("capabilities_used") or ()),
            key_findings=tuple(
                KeyFinding.from_record(item) for item in payload.get("key_findings") or ()
            ),
            resolved=bool(payload.get("resolved", stored.outcome is EpisodeOutcome.RESOLVED)),
            root_cause=stored.resolution or "",
            summary=stored.summary,
            effectiveness_score=float(payload.get("effectiveness_score", 0.0)),
            effectiveness_formula_version=int(
                payload.get("effectiveness_formula_version", EFFECTIVENESS_FORMULA_VERSION)
            ),
            duration_seconds=float(payload.get("duration_seconds", 0.0)),
            iterations=int(payload.get("iterations", 0)),
            run_id=stored.run_id or "",
            occurred_at=stored.occurred_at,
            updated_at=datetime.fromisoformat(str(updated)) if updated else None,
            embedding_model=str(payload.get("embedding_model", "")),
            embedding_dimension=int(payload.get("embedding_dimension", 0)),
            guardrail_rules_fired=tuple(
                str(rule) for rule in payload.get("guardrail_rules_fired") or ()
            ),
        )

    def vector_metadata(self) -> dict[str, Any]:
        """Return what a similarity search filters and ranks on without a second read.

        ``team_node_id`` is here because the filter is the cheap half of FR-023:
        the organisation boundary is already structural — no port method takes an
        org — and this narrows within it before any row is loaded.
        """
        return {
            "team_node_id": self.team_node_id,
            "issue_type": self.canonical_issue_type.value,
            "resolved": self.resolved,
            "components": list(self.component_labels),
            "effectiveness_score": self.effectiveness_score,
            "occurred_at": self.occurred_at.isoformat() if self.occurred_at else None,
        }


@dataclass(frozen=True, slots=True)
class ScoredEpisode:
    """A retrieval result with every term of its rank exposed.

    The components are kept rather than folded into one number because the
    number alone cannot answer the question an operator actually asks of a
    surprising result — whether it ranked highly because it was similar, because
    it was recent, or because nothing else was.
    """

    episode: MemoryEpisode
    similarity: float = 0.0
    resolved: float = 0.0
    component_overlap: float = 0.0
    issue_type_match: float = 0.0
    effectiveness: float = 0.0
    recency: float = 0.0
    score: float = 0.0
    formula_version: int = RANKING_FORMULA_VERSION
    #: This episode carries the query's exact fingerprint. Not a ranking term but
    #: a precedence: a weight can be outvoted by five other weights, and "this
    #: alert has fired before under exactly this shape" is not a preference to be
    #: outvoted. It sorts ahead of everything the similarity half found.
    exact_match: bool = False

    @property
    def correlation_id(self) -> str:
        """Return the episode this result points at."""
        return self.episode.correlation_id

    def terms(self) -> dict[str, float]:
        """Return the ranking terms, for a trace that explains the order."""
        return {
            "similarity": self.similarity,
            "resolved": self.resolved,
            "component_overlap": self.component_overlap,
            "issue_type_match": self.issue_type_match,
            "effectiveness": self.effectiveness,
            "recency": self.recency,
        }


@dataclass(frozen=True, slots=True)
class RecallQuery:
    """What the agent asked memory for.

    ``component`` and ``issue_type`` are *signals*, not filters. They say which
    episodes the caller would rather read first; they never say which episodes
    exist. That is the difference between an agent that knows the failing
    workload saying so, and an agent excluding the episode that would have
    explained the incident because it called the workload something else.

    The words are kept verbatim. Comparison happens on the canonical bucket, but
    a trace that recorded only the bucket could not answer what the agent
    actually searched for — and "why did this match" is the question a surprising
    recall gets asked.
    """

    text: str
    component: str = ""
    issue_type: str = ""
    limit: int = 0

    def components(self) -> tuple[Component, ...]:
        """Return the named component, if one was named."""
        return (Component.parse(self.component),) if self.component.strip() else ()

    def canonical_issue_type(self) -> IssueType:
        """Return the bucket this recall is searching within."""
        return IssueType.classify(self.issue_type)

    def signature(self) -> str:
        """Return the fingerprint an exact-match lookup uses, or ``""``.

        Empty only when the caller described the incident's *shape* not at all —
        no component, and an issue type that could not be classified. Both of
        those reduce to the ``other`` bucket over no components, and an episode
        carries that fingerprint whenever its own extraction managed neither: the
        lookup would promote every unclassifiable, component-less episode in the
        corpus to the top of every unfiltered search, on the strength of two runs
        having each failed to say anything.

        A component alone is enough, and so is a classified issue type alone.
        Each is a real claim about what happened, and a fingerprint over one of
        them matches only episodes that made the same claim.
        """
        components = self.components()
        classification = self.canonical_issue_type()
        if not components and not classification.classified:
            return ""
        return fingerprint(classification, components)


def now() -> datetime:
    """Return the current instant, timezone-aware."""
    return datetime.now(UTC)


def component_set(components: Sequence[Component]) -> frozenset[str]:
    """Return the labels of ``components``, for an overlap that ignores order."""
    return frozenset(component.label for component in components)


def fingerprint(issue_type: IssueType, components: Sequence[Component]) -> str:
    """Return the hash two incidents of the same shape share.

    One function, called by the episode that stores a fingerprint and by the
    query that looks one up. Two implementations of "the same alert again" that
    agreed on the day they were written and drifted afterwards is precisely the
    failure this whole module is being changed to stop.
    """
    material = "|".join((issue_type.value, *sorted(component_set(components))))
    return blake2b(material.encode("utf-8"), digest_size=SIGNATURE_LENGTH // 2).hexdigest()


__all__ = [
    "COMPONENT_SEPARATOR",
    "SIGNATURE_LENGTH",
    "ISSUE_TYPE_KEYWORDS",
    "Component",
    "EpisodeSeverity",
    "IssueType",
    "KeyFinding",
    "MemoryEpisode",
    "RecallQuery",
    "ScoredEpisode",
    "component_set",
    "fingerprint",
    "now",
]
