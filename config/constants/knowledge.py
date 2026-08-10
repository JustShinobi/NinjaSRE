"""The topology graph and the knowledge base: bounds, noise floors, and switches.

Two stores share this module because they share every bound worth naming twice.
Both are team-scoped, both are independently ablatable, and both answer a search
the agent makes *after* it holds evidence — so the ceilings on what one answer
may carry are the same kind of number, decided for the same reason: the agent
reads every result, and a result set large enough to bury the relevant entry is
worse than a smaller one that missed it.

The traversal bounds are **not** here. ``MAX_GRAPH_DEPTH`` and
``MAX_GRAPH_RESULTS`` belong to the storage port that enforces them, and a
second copy in this module would be a second number to change — with the failure
mode being a traversal this tier believes is bounded at four hops and storage
bounds at five.
"""

from __future__ import annotations

from typing import Final

# --- Ablation ----------------------------------------------------------------

#: Turn the topology graph off for a deployment. Independent of the knowledge
#: base, because the two answer different questions and the ablation each has to
#: settle is its own: "does knowing the blast radius change the investigation"
#: and "do the team's runbooks change it" are not one experiment.
NINJASRE_TOPOLOGY_ENV: Final = "NINJASRE_TOPOLOGY"
NINJASRE_KNOWLEDGE_ENV: Final = "NINJASRE_KNOWLEDGE"

# --- Topology ----------------------------------------------------------------

#: Operator annotations one node or edge may carry. Annotations survive every
#: discovery run forever, so without a ceiling a node annotated weekly for a year
#: arrives in the context window with fifty-two notes attached.
MAX_TOPOLOGY_ANNOTATIONS: Final[int] = 20

#: Characters one annotation may carry, so an operator who pastes a post-mortem
#: into an annotation costs that annotation rather than the node.
MAX_ANNOTATION_CHARS: Final[int] = 500

#: Days after which an edge nobody re-verified is reported as stale beside the
#: result. A week, because that is roughly how long a service dependency survives
#: a deploy cadence without being re-observed — and because the number is a
#: *label on an answer*, never a deletion: an edge is removed by reconciliation
#: seeing it gone, not by a clock running out.
TOPOLOGY_VERIFICATION_STALE_DAYS: Final[float] = 7.0

#: Nodes and edges one declarative import may declare. An import is a file an
#: operator wrote, and a file that exceeds this is a topology dump that wanted
#: a discovery adapter.
MAX_IMPORT_NODES: Final[int] = 5_000
MAX_IMPORT_EDGES: Final[int] = 20_000

#: Requests observed between two services before a service-mesh adapter calls it
#: a dependency. Every mesh reports the occasional stray connection — a health
#: probe, a misrouted retry, a scanner — and an edge drawn from one of those is a
#: dependency the agent will reason about that nobody has.
MESH_EDGE_MIN_REQUESTS: Final[int] = 5

#: The same floor for trace-derived dependencies, where a single span between two
#: services is more often an experiment than an architecture.
TRACE_EDGE_MIN_SPANS: Final[int] = 5

# --- Knowledge chunking ------------------------------------------------------

#: Characters one chunk may carry. Roughly a screen of a runbook: large enough
#: that a procedure's steps stay together, small enough that a search returning
#: five of them is still something the agent reads rather than skims.
MAX_CHUNK_CHARS: Final[int] = 1_200

#: Characters a chunk repeats from the end of the one before it. Overlap exists
#: for the sentence that spans a boundary — a condition in one chunk and its
#: consequence in the next is how a conditional instruction becomes an
#: unconditional one.
CHUNK_OVERLAP_CHARS: Final[int] = 150

#: Characters below which a trailing fragment is folded into the previous chunk
#: rather than indexed on its own. A twelve-character chunk matches everything
#: weakly and nothing well, and it costs a retrieval slot to say so.
MIN_CHUNK_CHARS: Final[int] = 200

#: Chunks one document may produce. A document past this is a manual, and a
#: manual indexed whole crowds every other document out of every search the team
#: runs. Ingestion refuses rather than truncating: half a runbook indexed as a
#: whole runbook is the version nobody can detect.
MAX_DOCUMENT_CHUNKS: Final[int] = 500

#: Depth the document hierarchy may nest to. Deeper than this and the tree is
#: being used as a filesystem, which search spans anyway.
MAX_KNOWLEDGE_TREE_DEPTH: Final[int] = 8

#: Characters of a document's text quoted around a detected secret when
#: ingestion refuses it. Enough to find the line; never enough to carry the
#: secret itself, which is why the window is reported as an offset and a section
#: rather than as text.
SECRET_LOCATION_CONTEXT_CHARS: Final[int] = 40

# --- Knowledge search --------------------------------------------------------

#: Chunks one search returns when the agent names no limit. Five, for the same
#: reason recall returns five episodes: the agent reads every one.
DEFAULT_KNOWLEDGE_SEARCH_RESULTS: Final[int] = 5

#: The ceiling the capability enforces on a requested limit.
MAX_KNOWLEDGE_SEARCH_RESULTS: Final[int] = 20

#: Candidates fetched from the index before the team check and same-document
#: collapse cut them down, as a multiple of the requested count. A document
#: whose five best chunks are all about the same paragraph should not fill the
#: answer, and collapsing needs something left over to promote.
KNOWLEDGE_SEARCH_CANDIDATE_FACTOR: Final[int] = 3

#: Chunks one document may contribute to a single answer. Without this a runbook
#: that repeats a phrase in six sections wins every slot, and the answer stops
#: being a search over the corpus.
MAX_CHUNKS_PER_DOCUMENT: Final[int] = 2

# --- Agent-proposed knowledge ------------------------------------------------

#: Characters an agent's proposed document may carry. A proposal is reviewed by
#: a human during or shortly after an incident, and one longer than this is one
#: nobody reads before approving.
MAX_PROPOSAL_CHARS: Final[int] = 8_000

#: Hours a proposal waits for review before it expires. A week: long enough to
#: survive an on-call rotation, short enough that nobody approves a proposal
#: whose incident they no longer remember.
PROPOSAL_REVIEW_TTL_HOURS: Final[float] = 168.0

#: The action name a knowledge proposal is recorded under in the approval store,
#: so a review queue can be listed without the store learning what knowledge is.
PROPOSAL_APPROVAL_ACTION: Final = "knowledge.proposal"

#: Proposals one listing returns. The queue is read by a human in a console;
#: past this it is a backlog report rather than a queue.
MAX_PROPOSAL_QUEUE_RESULTS: Final[int] = 50

# --- Sync --------------------------------------------------------------------

#: Documents one sync run may ingest from a single source. A first sync against
#: a large wiki should land in several runs rather than one that holds a
#: transaction open for an hour.
MAX_SYNC_DOCUMENTS_PER_RUN: Final[int] = 200

#: The scheduled-job kind a knowledge sync is registered under.
KNOWLEDGE_SYNC_JOB_KIND: Final = "knowledge.sync"

# --- The documentation corpus ------------------------------------------------

#: The directory a repository's prose lives in, and the only Markdown root the
#: corpus source will walk. Named rather than configured because the whole point
#: of the source is that it reads two directories of a repository that holds
#: fifteen thousand files, and a configurable root is one somebody eventually
#: points at the repository.
CORPUS_DOCUMENT_ROOT: Final = "docs"

#: The directory a repository's declarative policy lives in. Firewall rules are
#: operational knowledge: half of "I cannot reach X" is answered there.
CORPUS_POLICY_ROOT: Final = "policies"

#: Files one corpus may hold across both roots. A tree past this is a repository
#: somebody pointed the source at rather than a documentation directory, and
#: reading it would be an embedding bill for lockfiles. Refused rather than
#: truncated: a corpus silently missing its second half is one nobody detects.
MAX_CORPUS_FILES: Final[int] = 2_000

#: Bytes one corpus file may carry. Past this the file is a manual or a data
#: dump that happens to end in ``.md``; it is skipped by name, with the constant
#: in the reason, rather than failing the other sixty-six documents.
MAX_CORPUS_FILE_BYTES: Final[int] = 512_000

#: Characters of a verification query's own text quoted onto the candidate
#: detector it becomes. Enough that an operator deciding whether to enable it
#: reads the sentence the author wrote; short enough to sit in a table row.
MAX_DETECTOR_ORIGIN_EXCERPT_CHARS: Final[int] = 400

#: Candidate detectors one document may propose. A verification document past
#: this is a signal catalogue, and importing it wholesale would bury the
#: detectors somebody actually enabled.
MAX_DETECTOR_CANDIDATES: Final[int] = 50

#: Documents one resource's detail panel lists. The panel answers "what has
#: been written about this"; past this it is a corpus listing, which the
#: knowledge screen already is.
MAX_DOCUMENTS_PER_RESOURCE: Final[int] = 10

#: The scheduled-job kind a topology discovery run is registered under.
TOPOLOGY_DISCOVERY_JOB_KIND: Final = "topology.discovery"


__all__ = [
    "CHUNK_OVERLAP_CHARS",
    "CORPUS_DOCUMENT_ROOT",
    "CORPUS_POLICY_ROOT",
    "DEFAULT_KNOWLEDGE_SEARCH_RESULTS",
    "KNOWLEDGE_SEARCH_CANDIDATE_FACTOR",
    "KNOWLEDGE_SYNC_JOB_KIND",
    "MAX_ANNOTATION_CHARS",
    "MAX_CHUNKS_PER_DOCUMENT",
    "MAX_CHUNK_CHARS",
    "MAX_CORPUS_FILES",
    "MAX_CORPUS_FILE_BYTES",
    "MAX_DETECTOR_CANDIDATES",
    "MAX_DETECTOR_ORIGIN_EXCERPT_CHARS",
    "MAX_DOCUMENTS_PER_RESOURCE",
    "MAX_DOCUMENT_CHUNKS",
    "MAX_IMPORT_EDGES",
    "MAX_IMPORT_NODES",
    "MAX_KNOWLEDGE_SEARCH_RESULTS",
    "MAX_KNOWLEDGE_TREE_DEPTH",
    "MAX_PROPOSAL_CHARS",
    "MAX_PROPOSAL_QUEUE_RESULTS",
    "MAX_SYNC_DOCUMENTS_PER_RUN",
    "MAX_TOPOLOGY_ANNOTATIONS",
    "MESH_EDGE_MIN_REQUESTS",
    "MIN_CHUNK_CHARS",
    "NINJASRE_KNOWLEDGE_ENV",
    "NINJASRE_TOPOLOGY_ENV",
    "PROPOSAL_APPROVAL_ACTION",
    "PROPOSAL_REVIEW_TTL_HOURS",
    "SECRET_LOCATION_CONTEXT_CHARS",
    "TOPOLOGY_DISCOVERY_JOB_KIND",
    "TOPOLOGY_VERIFICATION_STALE_DAYS",
    "TRACE_EDGE_MIN_SPANS",
]
