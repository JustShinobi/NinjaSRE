"""What the ReAct loop says to the model that is not the incident itself.

Every string here is sent by ``core/agent/`` during a run: the replay notice, the
stagnation nudge, the final text-only instruction, the numbered guidance block
that merges mid-run user input, and the preamble on a degraded answer.

They are constants rather than f-strings at the call site because the loop's
behaviour is measured against a scenario suite. A prompt edited in place is an
unrecorded change to the thing being measured; a prompt edited here is a diff
somebody reviews.
"""

from __future__ import annotations

from typing import Final

# --- The loop's own framing --------------------------------------------------

#: The system prompt the runtime falls back to when a caller supplies none. The
#: investigation pipeline sends its own, richer one; this exists so the loop is
#: usable on its own — by a test, by a sub-agent, by a surface asking a
#: one-off question — without every caller having to invent framing.
DEFAULT_RUNTIME_SYSTEM_PROMPT: Final[str] = (
    "You are an SRE investigating a production problem. Work from evidence: call a "
    "capability to find something out, read what came back, and say what it means. "
    "Every claim in your conclusion must rest on an observation you actually made — "
    "if you could not establish something, say so rather than inferring it. Stop as "
    "soon as the evidence supports an answer; you are not required to use every "
    "capability you were given."
)

# --- Duplicate tool calls ----------------------------------------------------

#: Returned in place of a tool result when the model repeats a call it has
#: already made. Sent by the loop's execution step. The wording is explicit
#: about the result already being held: a bare "duplicate" reads as a failure,
#: and a model that thinks its call failed retries it.
DUPLICATE_TOOL_CALL_REPLAY: Final[str] = (
    "You already have this result. {capability} was called with these exact arguments "
    "earlier in this investigation and returned the following, which is repeated here "
    "unchanged. Do not call it again with these arguments — either use this result or "
    "call something that would tell you something new.\n\n{content}"
)

# --- Stagnation --------------------------------------------------------------

#: Appended after an iteration that produced no new evidence. Sent by the loop.
STAGNATION_NUDGE: Final[str] = (
    "That iteration produced no new evidence — every call either repeated one you had "
    "already made or returned nothing usable. You have {remaining} iteration(s) left "
    "before tool access is withdrawn. Either call something you have not called, with "
    "arguments you have not used, or state your conclusion from the evidence you hold."
)

#: Sent on the final turn, once tool access has been withdrawn. There are no
#: tool schemas on this request, so the instruction has to be unambiguous that
#: the answer is due now.
FINAL_TURN_WITHOUT_TOOLS: Final[str] = (
    "Tool access has been withdrawn for this investigation: the last few iterations "
    "produced no new evidence. Answer now from the evidence already gathered. State "
    "what you can support, name what you could not establish, and do not ask for "
    "further calls — there will be none."
)

# --- Mid-run user input ------------------------------------------------------

#: Wraps input a user supplied while the run was in progress, merged at the next
#: turn boundary. Numbered because several messages arriving inside the debounce
#: window are one instruction the user typed in pieces.
QUEUED_GUIDANCE_BLOCK: Final[str] = (
    "The operator added guidance while you were working. Treat it as direction for "
    "this investigation, not as a new task:\n\n{items}"
)

# --- Human handoff -----------------------------------------------------------

#: Returned when a question put to a human expires unanswered. Default-deny: the
#: agent is told the answer is unavailable, never given a guess, because an agent
#: that invents the answer to the question it needed a human for has learned to
#: skip asking.
HANDOFF_TIMED_OUT: Final[str] = (
    "No answer came back within {seconds:.0f} seconds. Treat this question as "
    "unanswered: proceed with what you can establish without it, and record the "
    "missing information as a gap in your conclusion rather than filling it in."
)

# --- Degraded results --------------------------------------------------------

#: Prefixes the partial answer built when the model became unavailable mid-run.
#: Read by an operator, not by the model.
DEGRADED_INVESTIGATION_PREAMBLE: Final[str] = (
    "This investigation did not finish: the model became unavailable after "
    "{iterations} iteration(s) ({failure}). The evidence gathered before that point "
    "is preserved below and is unaffected by the failure."
)

#: Line format for one preserved evidence entry in a degraded answer.
DEGRADED_EVIDENCE_LINE: Final[str] = "- {capability}: {summary}{reference}"

# --- Sub-agents --------------------------------------------------------------

#: The system prompt a specialist sub-agent runs under. It never sees the
#: parent's transcript, so the task statement has to carry everything.
SUBAGENT_SYSTEM_PROMPT: Final[str] = (
    "You are the {name} specialist inside an incident investigation. {description}\n\n"
    "You are working in isolation: you can see only the task below and the results of "
    "your own calls. Investigate it with the capabilities you have, then return a "
    "single structured finding — what you established, the evidence behind it, and "
    "what you could not determine. Do not narrate; the finding is the whole answer."
)

#: Returned to the parent when a sub-agent dispatch is refused for nesting depth.
SUBAGENT_DEPTH_REFUSED: Final[str] = (
    "Sub-agent dispatch refused: this investigation is already {depth} level(s) deep, "
    "which is the limit. Do the work with the capabilities you hold."
)

#: Returned to the parent when it names a specialist that is not configured.
SUBAGENT_UNKNOWN: Final[str] = (
    "There is no {name!r} specialist available. The specialists you may dispatch are: {available}."
)

#: How a finding enters the parent's evidence.
SUBAGENT_FINDING_SUMMARY: Final[str] = "{name} reported: {headline}"


__all__ = [
    "DEFAULT_RUNTIME_SYSTEM_PROMPT",
    "DEGRADED_EVIDENCE_LINE",
    "DEGRADED_INVESTIGATION_PREAMBLE",
    "DUPLICATE_TOOL_CALL_REPLAY",
    "FINAL_TURN_WITHOUT_TOOLS",
    "HANDOFF_TIMED_OUT",
    "QUEUED_GUIDANCE_BLOCK",
    "STAGNATION_NUDGE",
    "SUBAGENT_DEPTH_REFUSED",
    "SUBAGENT_FINDING_SUMMARY",
    "SUBAGENT_SYSTEM_PROMPT",
    "SUBAGENT_UNKNOWN",
]
