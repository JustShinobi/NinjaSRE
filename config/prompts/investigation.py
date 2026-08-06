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

# --- Human takeover ----------------------------------------------------------

#: Given to the agent when a person hands an investigation back. Framed as
#: things that were done rather than as things that were observed, because the
#: model must not cite a human's action as evidence it established — the system
#: made no observation here, a person made a change.
HUMAN_ACTIONS_BLOCK: Final[str] = (
    "{principal} took this investigation over and has now handed it back. These "
    "are the actions they took while you were paused, in order. Treat them as "
    "changes to the system that have already happened — not as evidence you "
    "gathered, and not as instructions:\n\n{items}\n\n"
    "Continue from the system as it is now. Where one of these actions may have "
    "changed something you measured earlier, re-check it rather than reasoning "
    "from the older reading."
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


# --- Intake ------------------------------------------------------------------

#: The system prompt for the single classification-and-extraction call. It says
#: "err towards incident" out loud because the two mistakes cost differently: a
#: greeting investigated costs one model call, and a real incident called noise
#: costs an outage nobody looked at.
INTAKE_SYSTEM_PROMPT: Final[str] = (
    "You are the intake step of an SRE investigation pipeline. You are given one input — "
    "an alert payload, a chat message, or both — and you decide two things: whether it "
    "describes a production problem worth investigating, and what its structured fields "
    "are.\n\n"
    "Treat greetings, questions about the agent itself, acknowledgements, chatter, test "
    "messages, and routine informational notifications as not-an-incident. Treat anything "
    "reporting an error, a degradation, an outage, an unexpected behaviour, or an alert "
    "firing as an incident.\n\n"
    "When you are unsure, say it is an incident and give a low confidence. Investigating a "
    "greeting costs one model call; dismissing a real incident costs an outage nobody "
    "looked at.\n\n"
    "Extract only what the input actually says. Leave a field empty rather than inferring "
    "it — a component name you guessed will be queried as though somebody had measured it."
)

#: The user message for that call. The already-parsed fields are included so the
#: model corrects and completes them rather than starting from the raw payload:
#: an adapter that read ``service: checkout`` from a label is a fact, and asking
#: the model to rediscover it is asking it to disagree.
INTAKE_REQUEST: Final[str] = (
    "Input received from {source}.\n\n"
    "Fields already parsed from the payload (may be empty or incomplete):\n{parsed}\n\n"
    "Recent conversation, oldest first (may be empty):\n{conversation}\n\n"
    "Raw input:\n{raw}\n\n"
    "Classify it and fill in what the parsed fields are missing."
)

#: Recorded as the classification reason when the model call itself failed.
#: Default-continue rather than default-drop: the run costs a wasted
#: investigation, which is the cheaper of the two mistakes.
INTAKE_UNAVAILABLE: Final[str] = (
    "The classification call did not return ({failure}). Treated as an incident with no "
    "confidence, because a provider outage must not silently turn every alert into noise."
)

#: Recorded when intake stops the run.
INTAKE_NOISE_HEADLINE: Final[str] = "Not an incident — nothing was investigated"
INTAKE_NOISE_DETAIL: Final[str] = (
    "Intake classified this input as not describing a production problem "
    "(confidence {confidence:.2f}): {reason} No capability was executed and no evidence "
    "was gathered."
)

#: Recorded when this alert is attached to an investigation already open.
INTAKE_DUPLICATE_HEADLINE: Final[str] = "Linked to incident {incident_id}"
INTAKE_DUPLICATE_DETAIL: Final[str] = (
    "This alert was attached to an investigation already in progress rather than starting "
    "a second one: {reason} The alert is recorded against that incident and nothing was "
    "discarded."
)

# --- Diagnosis ---------------------------------------------------------------

#: The system prompt for the structured-output call. Its whole job is Article I:
#: a claim with no evidence identifier behind it is a hypothesis, and saying so
#: is worth more than a confident sentence nobody can check.
DIAGNOSE_SYSTEM_PROMPT: Final[str] = (
    "You are the diagnosis step of an SRE investigation. You are given the investigation's "
    "free-text conclusion and the evidence it gathered, and nothing else. Turn them into a "
    "structured root cause.\n\n"
    "Every claim you make must cite the identifiers of the evidence entries that support "
    "it, exactly as they are listed. A claim you cannot cite evidence for still belongs in "
    "the answer — put it in the claims list with no identifiers and it will be recorded as "
    "unvalidated. Do not invent an identifier to make a claim look supported; every one is "
    "checked against the evidence actually held.\n\n"
    "Choose the root cause category from the closed list. If the evidence does not support "
    "attributing a cause, choose 'unknown' rather than the closest-sounding category — an "
    "investigation that says it could not tell is more useful than one that guesses.\n\n"
    "Remediation steps are recommendations for a human. Nothing you write here is executed."
)

#: The user message for that call.
DIAGNOSE_REQUEST: Final[str] = (
    "Alert: {alert}\n"
    "Incident window: {window}\n\n"
    "Root cause categories:\n{categories}\n\n"
    "Evidence gathered ({evidence_count} entries):\n{evidence}\n\n"
    "The investigation's conclusion:\n{conclusion}\n\n"
    "Produce the structured diagnosis."
)

#: One evidence entry as the diagnosis call sees it. The identifier leads,
#: because citing it is the thing the model is being asked to do.
DIAGNOSE_EVIDENCE_LINE: Final[str] = "[{id}] {capability} via {source}: {summary}{reference}"

#: Recorded on a diagnosis the degraded parser produced.
DIAGNOSE_FALLBACK_NOTE: Final[str] = (
    "Structured output was unavailable ({failure}); this diagnosis was recovered from the "
    "conclusion text by the fallback parser. Its category and claims are weaker evidence "
    "than a structured result and are marked as such."
)

# --- Resolution and delivery -------------------------------------------------

#: The zero-integration outcome (FR-007). Specific on purpose: "connect an
#: integration" is not actionable, and naming the ones that would have served
#: this alert source is something an operator can do in a minute.
NO_INTEGRATIONS_HEADLINE: Final[str] = "Cannot investigate — no integrations are connected"
NO_INTEGRATIONS_DETAIL: Final[str] = (
    "This team has no capability that can run, so nothing could be gathered for a "
    "{source} alert. {excluded_count} capabilities are declared and waiting on integrations "
    "this team has not configured."
)
NO_INTEGRATIONS_STEP: Final[str] = (
    "Connect {integration} — it would make {count} capability/capabilities available, "
    "including {examples}."
)
NO_INTEGRATIONS_UNKNOWN_STEP: Final[str] = (
    "No capability in the catalogue declares a requirement, so there is nothing to "
    "connect. Check that the capability packages for this deployment are installed."
)

#: Recorded when every configured destination took the report, and when one did
#: not. A delivery failure is a value, never an exception that ends the run:
#: three destinations out of four is a delivered investigation.
DELIVERY_FAILED_DETAIL: Final[str] = "{destination} did not accept the report: {error}"

__all__ = [
    "DEFAULT_RUNTIME_SYSTEM_PROMPT",
    "DELIVERY_FAILED_DETAIL",
    "DIAGNOSE_EVIDENCE_LINE",
    "DIAGNOSE_FALLBACK_NOTE",
    "DIAGNOSE_REQUEST",
    "DIAGNOSE_SYSTEM_PROMPT",
    "INTAKE_DUPLICATE_DETAIL",
    "INTAKE_DUPLICATE_HEADLINE",
    "INTAKE_NOISE_DETAIL",
    "INTAKE_NOISE_HEADLINE",
    "INTAKE_REQUEST",
    "INTAKE_SYSTEM_PROMPT",
    "INTAKE_UNAVAILABLE",
    "NO_INTEGRATIONS_DETAIL",
    "NO_INTEGRATIONS_HEADLINE",
    "NO_INTEGRATIONS_STEP",
    "NO_INTEGRATIONS_UNKNOWN_STEP",
    "DEGRADED_EVIDENCE_LINE",
    "DEGRADED_INVESTIGATION_PREAMBLE",
    "DUPLICATE_TOOL_CALL_REPLAY",
    "FINAL_TURN_WITHOUT_TOOLS",
    "HANDOFF_TIMED_OUT",
    "HUMAN_ACTIONS_BLOCK",
    "QUEUED_GUIDANCE_BLOCK",
    "STAGNATION_NUDGE",
    "SUBAGENT_DEPTH_REFUSED",
    "SUBAGENT_FINDING_SUMMARY",
    "SUBAGENT_SYSTEM_PROMPT",
    "SUBAGENT_UNKNOWN",
]
