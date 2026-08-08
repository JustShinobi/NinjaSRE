"""Deriving a state from named signals, and keeping the working.

Article I is the whole of this module. A conclusion carries the observations
that support it, so every state a resource is in names the rule that produced
it, the signals that rule read, the values those signals had, and — when a
provider status was involved — the raw string before anything mapped it.

The consequence worth stating: a resource with no signals is ``UNKNOWN``, not
``HEALTHY``. "Nothing told us it is broken" and "something told us it is fine"
are different facts, and only the second is health. An estate that treats the
first as the second reports a provider we cannot reach as an estate that is
fine, which is the failure this whole feature exists to avoid.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Final

from config.constants.estate import MAX_HEALTH_SIGNALS
from platform.estate.health.mapping import DEFAULT_MAPPING, StatusMapping
from platform.persistence.ports.estate_repository import (
    HealthDerivation,
    HealthSignal,
    ResourceHealth,
)

#: The rule a state derived from a provider's own status carries. Named as a
#: constant because an operator filtering their estate by "what decided this"
#: needs the string to be the same one every time.
RULE_PROVIDER_STATUS: Final = "provider_status"

#: The rule a resource nobody has observed carries.
RULE_NO_SIGNALS: Final = "no_signals"


def derive_from(
    *,
    raw_status: str,
    signals: Mapping[str, str],
    at: datetime,
    source: str = "",
    mapping: StatusMapping | None = None,
) -> HealthDerivation:
    """Return the state ``raw_status`` and ``signals`` support, with its working.

    The provider status decides the state; the other signals are recorded
    beside it as evidence rather than voting. That is deliberate and it is the
    conservative choice: a rule that let a fill-percentage signal override a
    provider saying ``running`` would be inventing a verdict the provider never
    gave, and inventing verdicts is how an estate stops being evidence.

    A resource with neither a status nor any signal is ``UNKNOWN``, and the
    explanation says so in words an operator can act on.
    """
    declared = mapping if mapping is not None else DEFAULT_MAPPING
    recorded = _recorded(raw_status, signals, at=at, source=source)

    if not raw_status.strip() and not signals:
        return HealthDerivation(
            state=ResourceHealth.UNKNOWN,
            rule=RULE_NO_SIGNALS,
            derived_at=at,
            explanation=(
                f"{source or 'the source'} reported this resource but no status and no "
                f"signals, so nothing supports a state. Not healthy: nobody said it was."
            ),
        )

    state = declared.state_for(raw_status)
    return HealthDerivation(
        state=state,
        rule=RULE_PROVIDER_STATUS,
        derived_at=at,
        signals=recorded,
        raw_status=raw_status,
        explanation=_explain(raw_status, state, declared, source=source),
    )


def _recorded(
    raw_status: str,
    signals: Mapping[str, str],
    *,
    at: datetime,
    source: str,
) -> tuple[HealthSignal, ...]:
    """Return the signals to store, status first, bounded.

    Bounded because a derivation an operator cannot read in one screen explains
    nothing, and a provider with sixty metrics would otherwise put all sixty on
    every resource on every sweep.
    """
    collected: list[HealthSignal] = []
    if raw_status.strip():
        collected.append(
            HealthSignal(name=RULE_PROVIDER_STATUS, value=raw_status, observed_at=at, source=source)
        )
    for name in sorted(signals):
        if len(collected) >= MAX_HEALTH_SIGNALS:
            break
        collected.append(
            HealthSignal(name=name, value=signals[name], observed_at=at, source=source)
        )
    return tuple(collected)


def _explain(
    raw_status: str,
    state: ResourceHealth,
    mapping: StatusMapping,
    *,
    source: str,
) -> str:
    """Return one sentence an operator can act on.

    The unmapped case says what to do about it, because "unknown" with no
    explanation is the state an operator most often mistakes for a bug in us.
    """
    who = source or "the provider"
    if not raw_status.strip():
        return f"{who} reported signals but no status, so the state is {state.value}."
    if not mapping.knows(raw_status):
        return (
            f"{who} reported {raw_status!r}, which no mapping covers, so the state is "
            f"{state.value} rather than healthy. Declare a mapping for it to get a verdict."
        )
    return f"{who} reported {raw_status!r}, which maps to {state.value}."


__all__ = ["RULE_NO_SIGNALS", "RULE_PROVIDER_STATUS", "derive_from"]
