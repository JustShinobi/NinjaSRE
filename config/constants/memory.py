"""Episodic memory: the bounds, the two documented formulas, and the local model.

Every number a memory decision turns on is here, and the two that matter most
are the *weights*. Effectiveness feeds ranking, ranking changes which past
incident an investigation reads first, and that changes what the agent does —
so neither may be a heuristic buried in a function. Both are stated as weighted
sums, both carry a version, and both versions are written onto the record they
produced, so a weight change does not silently reinterpret history.

The version is the point of the version. Changing a weight without bumping it
would leave a corpus of scores that mean two different things and no way to tell
which is which.
"""

from __future__ import annotations

from typing import Final

# --- Ablation ----------------------------------------------------------------

#: Turn memory recall off for a deployment, leaving writing alone. Reading and
#: writing are separate switches because the interesting ablation is a populated
#: corpus that the agent is not allowed to consult — that isolates recall's
#: contribution without also throwing away the corpus the next run would need.
NINJASRE_MEMORY_READ_ENV: Final = "NINJASRE_MEMORY_READ"
NINJASRE_MEMORY_WRITE_ENV: Final = "NINJASRE_MEMORY_WRITE"

#: Turn synthesised strategies off for a deployment, leaving episodes alone. A
#: third switch rather than a mode of the other two, because the ablation this
#: feature has to answer for is "episodes only" versus "episodes and playbooks":
#: folding it into the read switch would make the baseline a run with no memory
#: at all and the comparison would measure recall rather than synthesis.
NINJASRE_MEMORY_STRATEGY_ENV: Final = "NINJASRE_MEMORY_STRATEGY"

#: Names the embedding model an operator wants, when it is not the local default.
NINJASRE_EMBEDDING_MODEL_ENV: Final = "NINJASRE_EMBEDDING_MODEL"

# --- Writing -----------------------------------------------------------------

#: Characters an investigation's answer must reach before it is worth
#: remembering. Below this the "episode" is a sentence saying nothing was found,
#: and a corpus of those dilutes every similarity search run against it.
MIN_EPISODE_RESULT_LENGTH: Final[int] = 200

#: Ceiling on the single structured extraction call's reply. Extraction runs
#: once per investigation and produces a summary, not a report; a model given
#: unbounded room writes the transcript back out.
EPISODE_EXTRACTION_MAX_TOKENS: Final[int] = 1_024

#: Ceilings on what one episode may carry. An investigation that ran for an hour
#: can produce hundreds of findings, and an episode is a *summary* — the trace is
#: where the full record lives.
MAX_EPISODE_SUMMARY_CHARS: Final[int] = 4_000
MAX_EPISODE_KEY_FINDINGS: Final[int] = 12
MAX_EPISODE_COMPONENTS: Final[int] = 12

# --- Recall ------------------------------------------------------------------

#: Episodes one recall returns when the agent names no limit. Small on purpose:
#: the agent reads every one of these, and five relevant precedents inform an
#: investigation where twenty bury it.
DEFAULT_MEMORY_RECALL_RESULTS: Final[int] = 5

#: The ceiling the capability enforces on a requested limit.
MAX_MEMORY_RECALL_RESULTS: Final[int] = 20

#: Candidates fetched from the index before ranking, as a multiple of the
#: requested count. Ranking demotes unresolved and stale episodes, so the
#: similarity search has to return more than the answer needs or the demotion
#: has nothing to promote in their place.
MEMORY_RECALL_CANDIDATE_FACTOR: Final[int] = 4

# --- The effectiveness formula -----------------------------------------------

#: Bumped whenever a weight below changes. Stored on every episode, so a score
#: written under one set of weights is never compared against another.
EFFECTIVENESS_FORMULA_VERSION: Final[int] = 1

#: ``effectiveness = w_resolved * resolved + w_root_cause * has_root_cause
#:                 + w_evidence * evidence_backing_ratio
#:                 + w_trajectory * trajectory_efficiency``
#:
#: They sum to 1.0, which is what makes the result a score in ``[0, 1]`` rather
#: than a number whose range depends on how many terms happen to be non-zero.
EFFECTIVENESS_WEIGHT_RESOLVED: Final[float] = 0.35
EFFECTIVENESS_WEIGHT_ROOT_CAUSE: Final[float] = 0.25
EFFECTIVENESS_WEIGHT_EVIDENCE: Final[float] = 0.25
EFFECTIVENESS_WEIGHT_TRAJECTORY: Final[float] = 0.15

#: Iterations a well-run investigation is expected to take. Trajectory
#: efficiency is ``reference / max(iterations, reference)``, so a run at or under
#: the reference scores 1.0 and a run of twice that scores 0.5 — a bounded
#: inverse rather than a cliff, because the difference between eleven iterations
#: and twelve is not the difference between good and bad.
EFFECTIVENESS_TRAJECTORY_REFERENCE_ITERATIONS: Final[int] = 5

# --- The ranking formula -----------------------------------------------------

#: Bumped whenever a ranking weight changes, for the same reason as above. At 2
#: because the issue-type term below was added: every episode scored under
#: version 1 was scored by a formula with one fewer term in it.
RANKING_FORMULA_VERSION: Final[int] = 2

#: ``score = w_similarity * similarity + w_resolved * resolved
#:         + w_components * component_overlap + w_issue_type * issue_type_match
#:         + w_effectiveness * effectiveness + w_recency * recency``
#:
#: Similarity leads because a precedent that is not about this failure helps
#: nobody however well it went. The other five break ties among things that are
#: all plausibly about this failure, which is the case that actually occurs.
#:
#: The issue-type term is what the named classification became when it stopped
#: being a filter. A filter on it excluded the episode that would have explained
#: the incident whenever the run that wrote it chose different words; a weight
#: promotes the episode that agrees and merely declines to promote the one that
#: does not.
#:
#: Room for it was made by scaling all five original weights by 0.9 — 0.45
#: becomes 0.405, 0.15 becomes 0.135, 0.10 becomes 0.09 — rather than by taking
#: it out of whichever term looked least important. A uniform haircut leaves
#: every preference among the original five exactly as it was, so a reordering
#: after this change is the new term's doing and nothing else's.
RANK_WEIGHT_SIMILARITY: Final[float] = 0.405
RANK_WEIGHT_RESOLVED: Final[float] = 0.135
RANK_WEIGHT_COMPONENT_OVERLAP: Final[float] = 0.135
RANK_WEIGHT_ISSUE_TYPE_MATCH: Final[float] = 0.10
RANK_WEIGHT_EFFECTIVENESS: Final[float] = 0.135
RANK_WEIGHT_RECENCY: Final[float] = 0.09

#: Credit a component scores when the query and the episode agree on its *name*
#: but not on what kind of thing it is. The corpus proves the case: two runs
#: recorded the same container as ``container:lxc/122`` and ``guest:lxc/122``,
#: and one of them had to be wrong about nothing at all for the pair to stop
#: matching. Half, rather than one, because the two runs did disagree about
#: something — and rather than zero, because they plainly meant the same box.
#:
#: A query naming a component with no type at all scores full credit on a name
#: match instead. That caller asserted nothing to disagree with: an agent that
#: knows the failing workload is called ``payments-api`` should not have to know
#: whether an earlier run filed it as a service or as a deployment.
RANK_COMPONENT_NAME_ONLY_CREDIT: Final[float] = 0.5

#: Days after which an episode's recency term has halved. A month, because that
#: is roughly the interval over which a service's failure modes stop being the
#: same failure modes — deploys, dependency versions, and traffic shape all move.
RANKING_RECENCY_HALF_LIFE_DAYS: Final[float] = 30.0

# --- Strategy synthesis ------------------------------------------------------

#: Episodes sharing an issue type and a normalised component key before a
#: playbook is worth synthesising. Two episodes are a coincidence; three is the
#: smallest set from which "this keeps happening for these reasons" can be said
#: at all, and below it the anti-patterns section would be one failed run
#: generalised into a rule.
MIN_EPISODES_FOR_STRATEGY: Final[int] = 3

#: Episodes fed to one synthesis call, highest-scoring first. A bound on cost
#: and on quality both: a playbook drawn from forty episodes is a literature
#: review, and the twelve best-ranked ones already carry the recurring causes.
STRATEGY_MAX_INPUT_EPISODES: Final[int] = 12

#: Ceiling on the synthesis call's reply. A playbook is read inside an
#: investigation's context budget alongside the episodes it was drawn from, so
#: one that does not fit is one the agent never finishes reading.
STRATEGY_MAX_OUTPUT_TOKENS: Final[int] = 1_536

#: Items one playbook section may carry. The sections are ordered by
#: effectiveness, so the cut is at the tail — and a "recommended steps" list
#: longer than this is a transcript rather than a recommendation.
MAX_STRATEGY_SECTION_ITEMS: Final[int] = 8

#: Characters one item in a section may carry, so a model that answers a bullet
#: with a paragraph costs that bullet rather than the playbook.
MAX_STRATEGY_ITEM_CHARS: Final[int] = 600

#: Age at which a playbook is regenerated even though nothing invalidated it.
#: Infrastructure moves without producing an episode — a service is retired, a
#: dependency is replaced — and a playbook nobody contradicted is not thereby
#: a playbook anybody confirmed.
STRATEGY_MAX_AGE_DAYS: Final[float] = 30.0

#: How long a caller that lost the race for a strategy key waits for the winner
#: before generating for itself. Long enough for one structured call to finish,
#: short enough that a wedged generation does not hold an incident response.
STRATEGY_LOCK_WAIT_SECONDS: Final[float] = 60.0

#: Strategy keys one recall may look up. A recall that returned five episodes
#: touching six components would otherwise be six cache reads and, on a cold
#: cache, six synthesis calls — on the critical path of an incident. Two, because
#: the ranking already put the most relevant subject first and the second slot is
#: what covers a failure that spans a service and its datastore.
MAX_STRATEGY_KEYS_PER_RECALL: Final[int] = 2

#: Operator amendments kept on one playbook. They survive regeneration, so
#: without a bound a strategy edited weekly for a year would carry fifty-two
#: notes into every future context window.
MAX_STRATEGY_OPERATOR_EDITS: Final[int] = 10

# --- Embeddings --------------------------------------------------------------

#: The default embedder: in-process, deterministic, and reaching no network.
#: A deployment that may not egress keeps full memory function on this one, and
#: a deployment that may swap it for a stronger model behind the same port.
LOCAL_EMBEDDING_MODEL: Final = "ninjasre-local-hash-v1"
LOCAL_EMBEDDING_DIMENSION: Final[int] = 256

#: Character n-gram widths the local model hashes. Unigram tokens carry the
#: vocabulary; bigrams carry the little word order that matters in an error
#: string — "connection refused" and "refused connection" are the same incident,
#: but "out of memory" and "memory out" are not the same phrase.
LOCAL_EMBEDDING_NGRAM_SIZES: Final[tuple[int, ...]] = (1, 2)

#: Episodes embedded per unit of work during a re-embedding pass.
EMBEDDING_BATCH_SIZE: Final[int] = 256


__all__ = [
    "DEFAULT_MEMORY_RECALL_RESULTS",
    "EFFECTIVENESS_FORMULA_VERSION",
    "EFFECTIVENESS_TRAJECTORY_REFERENCE_ITERATIONS",
    "EFFECTIVENESS_WEIGHT_EVIDENCE",
    "EFFECTIVENESS_WEIGHT_RESOLVED",
    "EFFECTIVENESS_WEIGHT_ROOT_CAUSE",
    "EFFECTIVENESS_WEIGHT_TRAJECTORY",
    "EMBEDDING_BATCH_SIZE",
    "EPISODE_EXTRACTION_MAX_TOKENS",
    "LOCAL_EMBEDDING_DIMENSION",
    "LOCAL_EMBEDDING_MODEL",
    "LOCAL_EMBEDDING_NGRAM_SIZES",
    "MAX_EPISODE_COMPONENTS",
    "MAX_EPISODE_KEY_FINDINGS",
    "MAX_EPISODE_SUMMARY_CHARS",
    "MAX_MEMORY_RECALL_RESULTS",
    "MAX_STRATEGY_ITEM_CHARS",
    "MAX_STRATEGY_KEYS_PER_RECALL",
    "MAX_STRATEGY_OPERATOR_EDITS",
    "MAX_STRATEGY_SECTION_ITEMS",
    "MEMORY_RECALL_CANDIDATE_FACTOR",
    "MIN_EPISODES_FOR_STRATEGY",
    "MIN_EPISODE_RESULT_LENGTH",
    "NINJASRE_EMBEDDING_MODEL_ENV",
    "NINJASRE_MEMORY_READ_ENV",
    "NINJASRE_MEMORY_STRATEGY_ENV",
    "NINJASRE_MEMORY_WRITE_ENV",
    "RANKING_FORMULA_VERSION",
    "RANKING_RECENCY_HALF_LIFE_DAYS",
    "RANK_COMPONENT_NAME_ONLY_CREDIT",
    "RANK_WEIGHT_COMPONENT_OVERLAP",
    "RANK_WEIGHT_EFFECTIVENESS",
    "RANK_WEIGHT_ISSUE_TYPE_MATCH",
    "RANK_WEIGHT_RECENCY",
    "RANK_WEIGHT_RESOLVED",
    "RANK_WEIGHT_SIMILARITY",
    "STRATEGY_LOCK_WAIT_SECONDS",
    "STRATEGY_MAX_AGE_DAYS",
    "STRATEGY_MAX_INPUT_EPISODES",
    "STRATEGY_MAX_OUTPUT_TOKENS",
]
