"""What this package raises, named so a caller can tell the cases apart.

Every type here is one a caller might reasonably handle differently, which is
the only justification for a distinct type. An invalid import file is something
an operator fixes and retries; a document carrying a secret is something they fix
at the source and never retry unchanged; an unapproved proposal is not an error
at all from the reviewer's point of view, and is a refusal from the agent's.

**No message quotes matched secret material.** ``DocumentRejected`` names the
rule, the section, and the offset, and never the text — a refusal that echoed the
secret would put it in the trace, the log, and the console, which is where the
refusal was keeping it out of.
"""

from __future__ import annotations


class KnowledgeError(Exception):
    """Base for every failure raised by the topology and knowledge packages."""


class UnknownDependency(KnowledgeError):
    """An annotation or removal named an edge the graph does not hold.

    Raised rather than silently creating one. An operator annotating a
    dependency they believe exists has either mistyped it or is looking at a
    graph that has already moved, and creating the edge on their behalf would
    turn a typo into topology.
    """

    def __init__(self, from_node_id: str, to_node_id: str, kind: str) -> None:
        super().__init__(
            f"No {kind} dependency from {from_node_id!r} to {to_node_id!r} exists in this "
            f"team's topology. Add the dependency before annotating it."
        )
        self.from_node_id = from_node_id
        self.to_node_id = to_node_id
        self.kind = kind


class ImportInvalid(KnowledgeError):
    """A declarative topology document could not be applied.

    Carries every problem rather than the first. An operator fixing an import
    file one error per run is an operator who stops using the file.
    """

    def __init__(self, problems: tuple[str, ...]) -> None:
        listed = "\n  - ".join(problems)
        super().__init__(f"This topology document cannot be applied:\n  - {listed}")
        self.problems = problems


class CorpusBoundExceeded(KnowledgeError):
    """A corpus asked for more than its bound allows.

    Raised where the corpus is enumerated rather than where a document is
    ingested, because the case it catches is a source pointed at a repository
    root instead of at its documentation directory — and the honest answer to
    that is to refuse the whole run naming the ceiling, not to embed the first
    two thousand lockfiles it happened to reach.
    """

    def __init__(self, *, parameter: str, requested: int, limit: int, constant: str) -> None:
        super().__init__(
            f"{parameter} of {requested} exceeds {limit}, which is {constant}. "
            f"Point the source at the documentation directory, or raise the constant."
        )
        self.parameter = parameter
        self.requested = requested
        self.limit = limit
        self.constant = constant


class DocumentRejected(KnowledgeError):
    """Ingestion refused a document, and says where without saying what."""

    def __init__(self, document_id: str, reason: str) -> None:
        super().__init__(f"{document_id}: {reason}")
        self.document_id = document_id
        self.reason = reason


class ProposalNotApproved(KnowledgeError):
    """Something tried to apply a proposal a human has not approved (FR-017).

    The message names the state it found, because the two ways to reach here —
    still pending, and decided the other way — are different situations for
    whoever is reading the log.
    """

    def __init__(self, proposal_id: str, state: str) -> None:
        super().__init__(
            f"Proposal {proposal_id!r} is {state} and cannot be applied to the knowledge "
            f"base. A proposal takes effect only after a human approves it."
        )
        self.proposal_id = proposal_id
        self.state = state


class ProposalUnknown(KnowledgeError):
    """A decision or application named a proposal that does not exist."""

    def __init__(self, proposal_id: str) -> None:
        super().__init__(f"No proposal {proposal_id!r} is in this team's review queue.")
        self.proposal_id = proposal_id


__all__ = [
    "CorpusBoundExceeded",
    "DocumentRejected",
    "ImportInvalid",
    "KnowledgeError",
    "ProposalNotApproved",
    "ProposalUnknown",
    "UnknownDependency",
]
