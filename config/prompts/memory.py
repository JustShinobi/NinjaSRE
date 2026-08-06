"""What the agent is told about memory, and what memory is asked afterwards.

Three pieces of text, and the first one is the feature's central design decision
written down.

``MEMORY_RECALL_GUIDANCE`` is appended to the root system prompt and says *when*
to search, not *what* was found. Nothing about any past incident enters the
prompt: on a vague alert, similarity search returns episodes that share
vocabulary rather than a cause, and an agent handed one of those before it has
looked at anything anchors on it. Guidance costs a few dozen tokens; a wrong
precedent costs the investigation.

The extraction prompts run once, after the investigation, against the answer and
the trace. They are here rather than at the call site for the usual reason: the
loop is measured against a scenario suite, and a prompt edited in place is an
unrecorded change to the thing being measured.
"""

from __future__ import annotations

from typing import Final

# --- Recall ------------------------------------------------------------------

#: Appended to the root system prompt at ``on_run_start`` when memory reading is
#: enabled. It carries no episode content, and a test asserts that.
MEMORY_RECALL_GUIDANCE: Final[str] = (
    "You have a memory of previous investigations. Search it only once you hold "
    "concrete evidence — an error string, an exit code, a failing component, a "
    "boundary you have established — and search on that evidence rather than on the "
    "alert text. Memory searched on a raw alert returns incidents that merely share "
    "vocabulary with it, and reasoning from one of those is worse than having no "
    "precedent at all.\n\n"
    "When a search returns something, treat it as a lead rather than an answer: check "
    "its root cause against what you have actually observed in this incident before "
    "you rely on it. A returned episode also records the capabilities that "
    "investigation used, and repeating a sequence that worked is usually cheaper than "
    "rediscovering it. An empty result is a normal outcome and means this failure is "
    "new to the team, not that the search failed."
)

#: What the capability returns when the deployment has no memory configured.
#: Deliberately distinguishable from an empty result: "nothing found" and
#: "nowhere to look" lead to different next moves.
MEMORY_UNCONFIGURED: Final[str] = (
    "Episodic memory is not configured for this deployment, so no previous "
    "investigation can be recalled. Treat this incident as unseen rather than as one "
    "with no precedent."
)

#: What it returns when an operator has switched recall off for the team.
MEMORY_RECALL_DISABLED: Final[str] = (
    "Episodic memory recall is switched off for this team, so no previous "
    "investigation was consulted. Treat this incident as unseen rather than as one "
    "with no precedent."
)

#: What it returns when the search ran and matched nothing.
MEMORY_RECALL_EMPTY: Final[str] = (
    "No previous investigation resembles this one. That is a normal result — this "
    "failure is new to this team — and it is not a reason to search again with "
    "different wording."
)

#: One recalled episode, as the agent is shown it. The outcome leads because it
#: decides how much weight the rest of the line deserves.
MEMORY_RECALL_EPISODE: Final[str] = (
    "[{rank}] {outcome} — {issue_type}: {issue_description}\n"
    "    when: {occurred}\n"
    "    components: {components}\n"
    "    root cause: {root_cause}\n"
    "    capabilities used: {capabilities}\n"
    "    summary: {summary}"
)

#: The header the shaped result carries, so the model can see how much it got
#: and how it was ordered without inferring either.
MEMORY_RECALL_HEADER: Final[str] = (
    "{count} previous investigation(s) matched, ranked by similarity, whether a root "
    "cause was established, component overlap, how effective the run was, and how "
    "recent it is."
)

# --- Extraction --------------------------------------------------------------

#: The system prompt for the single post-investigation extraction call.
#:
#: The paragraph about ``resolved`` is the one that earns its place. Left to
#: itself a model reads "resolved" as "the incident is over", which is a claim
#: about production that nothing in this process can check — and an episode
#: corpus whose ``resolved`` flag means two things is a corpus no ranking can use.
EPISODE_EXTRACTION_SYSTEM_PROMPT: Final[str] = (
    "You are summarising a finished SRE investigation into one durable record, so a "
    "future investigation into a similar failure can learn from it. You are given the "
    "objective, the conclusion, and the capabilities that were called. Extract only "
    "what those actually say.\n\n"
    "'resolved' means: this investigation established a root cause and had evidence "
    "behind it. It does NOT mean production was fixed, and it does not mean anyone "
    "acted. An investigation that correctly concluded 'the cause is a bad deploy' is "
    "resolved even if the deploy is still live; an investigation that guessed without "
    "evidence is not resolved even if the guess was right.\n\n"
    "Components are the systems the failure was about, each with a type and a name — "
    "service, deployment, database, job, node, queue, and so on. Name only components "
    "the investigation actually looked at. Leave a field empty rather than inferring "
    "it: an invented component name will be searched against as though somebody had "
    "observed it.\n\n"
    "Key findings are what a specific capability revealed. Each one names the "
    "capability, what was asked of it, and what came back. A finding no capability "
    "produced is not a finding."
)

#: The user message for that call.
EPISODE_EXTRACTION_REQUEST: Final[str] = (
    "Investigation objective:\n{objective}\n\n"
    "Capabilities called, in order:\n{capabilities}\n\n"
    "Observations recorded during the run:\n{observations}\n\n"
    "The investigation's conclusion:\n{conclusion}\n\n"
    "Produce the episode record."
)

#: Recorded on the run when extraction did not produce a record. Extraction never
#: fails an investigation, so this is the whole consequence of it failing.
EPISODE_EXTRACTION_FAILED: Final[str] = (
    "Episode extraction did not return a record ({failure}). The investigation is "
    "unaffected and nothing was written to memory."
)

#: Recorded when the answer was too short to be worth remembering.
EPISODE_SKIPPED_TOO_SHORT: Final[str] = (
    "The investigation produced {length} characters, below the {minimum}-character "
    "minimum for an episode. Nothing was written to memory."
)

#: Recorded when the team's write switch is off.
EPISODE_SKIPPED_DISABLED: Final[str] = (
    "Episodic memory writing is switched off for this team. Nothing was written."
)


__all__ = [
    "EPISODE_EXTRACTION_FAILED",
    "EPISODE_EXTRACTION_REQUEST",
    "EPISODE_EXTRACTION_SYSTEM_PROMPT",
    "EPISODE_SKIPPED_DISABLED",
    "EPISODE_SKIPPED_TOO_SHORT",
    "MEMORY_RECALL_DISABLED",
    "MEMORY_RECALL_EMPTY",
    "MEMORY_RECALL_EPISODE",
    "MEMORY_RECALL_GUIDANCE",
    "MEMORY_RECALL_HEADER",
    "MEMORY_UNCONFIGURED",
]
