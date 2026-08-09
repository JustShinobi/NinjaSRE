"""What the model is told when its own output could not be used.

Every string here is a correction, and a correction has one job: say precisely
what was wrong, in terms the model can act on in its next turn. "Invalid tool
call" is not one of those terms. ``label_selector`` is not a parameter of
``kubernetes_list_pods``; its parameters are ``namespace`` — that is.

Two rules hold across all of them, and both are the difference between
resilience and invention.

**Nothing here supplies a value.** A correction names what is missing and asks
for it. It never suggests one, because a suggested value is a value the model
did not choose, and a capability run with parameters nobody chose produces
evidence of nothing.

**Nothing here is conditional on a provider.** These are sent to whichever model
misbehaved. A frontier model that starts emitting its tool calls as prose reads
exactly the same sentence a seven-billion-parameter local build does.
"""

from __future__ import annotations

from typing import Final

# --- Malformed calls ---------------------------------------------------------

#: Sent when the model supplied a parameter the capability does not declare.
#: Names the parameter and lists what the capability actually takes, because
#: "invalid arguments" leaves the model to guess which of the four it got wrong.
UNKNOWN_ARGUMENT_CORRECTION: Final[str] = (
    "Your call to {capability} was not made. It supplied {unknown}, which "
    "{capability} does not accept. Its parameters are: {declared}. Call it again "
    "with only those, or call something else."
)

#: Sent when a required parameter is missing. Deliberately does not propose a
#: value: the argument the model left out is not one anybody else may choose.
MISSING_ARGUMENT_CORRECTION: Final[str] = (
    "Your call to {capability} was not made. It requires {missing}, which your "
    "call did not include. Supply {missing} yourself — nothing will be filled in "
    "for you — or call a capability you can supply the arguments for."
)

#: Sent when the model wrote something that looked like a call and could not be
#: read as one. Says what was seen so the model can tell which of its output was
#: the problem.
UNREADABLE_CALL_CORRECTION: Final[str] = (
    "No capability was called. Your reply looked like it was describing a call "
    "to {capability}, but the arguments could not be read as a document. Emit the "
    "call as a tool call rather than as text, or answer in prose without one."
)

#: Sent when nothing in the reply named a capability that was offered.
NO_CALL_CORRECTION: Final[str] = (
    "No capability was called and no answer was given. The capabilities available "
    "to you this turn are: {available}. Either call one of them or state your "
    "conclusion from the evidence you already hold."
)

# --- Repetition --------------------------------------------------------------

#: Sent when the model has asked for the same thing, with the same arguments,
#: enough times running to be stuck. Names the call and the count, because a
#: model told merely that it is repeating itself frequently repeats itself.
REPETITION_BREAK: Final[str] = (
    "You have now called {capability} with the same arguments {count} times in "
    "the last {window} turns, and the result has not changed. It will not change. "
    "Call something different, change the arguments, or state your conclusion "
    "from the evidence you hold."
)

# --- Degradation -------------------------------------------------------------

#: The failure a run carries when the repair bound is spent. Names the model's
#: behaviour rather than the bound: "the repair budget was exhausted" is true and
#: tells an operator nothing about what to change.
REPAIR_BUDGET_EXHAUSTED: Final[str] = (
    "{model} on {provider} produced {attempts} unusable tool calls in a row after "
    "being told each time what was wrong ({behaviour}). The investigation stopped "
    "here rather than spending its remaining iterations on the same exchange."
)

#: The failure a run carries when the model would not stop repeating itself even
#: after being told.
REPETITION_UNBROKEN: Final[str] = (
    "{model} on {provider} kept calling {capability} with the same arguments after "
    "being told the result would not change. The investigation stopped here rather "
    "than spending its remaining iterations on one call."
)

#: The failure a call carries when it ran past its time budget. Names the
#: endpoint and the elapsed time, because a machine that has started swapping
#: produces exactly this and nothing else in the trace says so.
CALL_BUDGET_EXCEEDED: Final[str] = (
    "The call to {endpoint} did not return within its {budget:.0f}-second budget "
    "({elapsed:.0f}s elapsed). The endpoint is reachable or was; it is not "
    "answering in time. The investigation degraded rather than waiting."
)


__all__ = [
    "CALL_BUDGET_EXCEEDED",
    "MISSING_ARGUMENT_CORRECTION",
    "NO_CALL_CORRECTION",
    "REPAIR_BUDGET_EXHAUSTED",
    "REPETITION_BREAK",
    "REPETITION_UNBROKEN",
    "UNKNOWN_ARGUMENT_CORRECTION",
    "UNREADABLE_CALL_CORRECTION",
]
