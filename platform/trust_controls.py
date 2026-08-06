"""The two controls at the trust boundary, wired together and switchable as a pair.

Masking and guardrails are separate mechanisms with separate modules, and they
are composed here for two reasons.

**Because a deployment configures them together.** A team's masking level and
its rules path are one decision an operator makes once, and spreading that
decision across two constructors in two places is how a deployment ends up with
masking on and guardrails pointed at a file nobody wrote.

**Because the evaluation suite has to be able to turn each one off,
independently, and measure what changed.** A mechanism that cannot be ablated
cannot be claimed, and that applies to safety controls as much as to learning
ones: "masking does not hurt investigation quality" is a claim,
and the only honest way to make it is to run the suite both ways.

Turning guardrails off does **not** remove the engine. It downgrades every rule
to ``audit`` — nothing altered, nothing blocked, everything still recorded — so
an ablation run still reports what the enabled ruleset would have caught. That
is the constitutional line: the engine cannot be removed from the boundary,
only softened, and an ablation is not an exception to it.

Per-team resolution is a static default until the hierarchical configuration
service exists. ``for_team`` is the seam it will fill: the signature is already
the one a config lookup produces, so filling it is a change to one function body
rather than to every caller.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from pathlib import Path

from config.constants.security import (
    DEFAULT_MASKING_POLICY,
    MASKING_ENABLED_BY_DEFAULT,
    NINJASRE_MASKING_ENABLED_ENV,
    NINJASRE_MASKING_POLICY_ENV,
)
from core.agent.hooks.registry import HookRegistry
from core.llm.types import LLMClient
from platform.guardrails.audit import GuardrailAuditor
from platform.guardrails.engine import GuardrailEngine
from platform.guardrails.hooks import GuardrailHooks
from platform.guardrails.rules import Ruleset, RulesetLoader, configured_rules_path
from platform.guardrails.sinks import SinkGuard
from platform.masking.context import MaskingContext
from platform.masking.llm import MaskingLLMClient
from platform.masking.policy import CustomPattern, MaskingLevel, MaskingPolicy

#: The names the evaluation suite enumerates. Strings rather than an enum,
#: because an ablation axis is identified in a results table and a report, and
#: both of those are text.
MASKING_SWITCH = "masking"
GUARDRAILS_SWITCH = "guardrails"

TRUST_SWITCHES: tuple[str, ...] = (MASKING_SWITCH, GUARDRAILS_SWITCH)

#: Values that read as "off" in an environment variable. Anything else is on,
#: including a typo — a mis-spelled value must not silently disable a control.
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})


@dataclass(frozen=True, slots=True)
class TrustControls:
    """One team's masking policy and guardrail rules, with both switches.

    Frozen. ``without`` returns a new object rather than mutating this one, so
    an ablation run cannot leave a switch flipped for the run after it — which
    is exactly the bug that would make an ablation table quietly wrong.
    """

    policy: MaskingPolicy = field(default_factory=MaskingPolicy)
    rules: Ruleset | RulesetLoader | None = None
    masking_enabled: bool = True
    guardrails_enabled: bool = True

    @classmethod
    def for_team(
        cls,
        *,
        level: str = DEFAULT_MASKING_POLICY,
        custom_patterns: Iterable[CustomPattern] = (),
        rules_path: Path | None = None,
    ) -> TrustControls:
        """Return the controls for one team.

        The seam the configuration service fills. Until it exists, every team
        resolves to the same static default, which is the honest version of
        "per-team" before there is anywhere to store a per-team value.
        """
        return cls(
            policy=MaskingPolicy.from_level(level, custom_patterns=tuple(custom_patterns)),
            rules=RulesetLoader(path=rules_path) if rules_path is not None else None,
        )

    @classmethod
    def from_environment(cls) -> TrustControls:
        """Return the controls an operator configured through the environment."""
        level = os.environ.get(NINJASRE_MASKING_POLICY_ENV, "").strip() or DEFAULT_MASKING_POLICY
        enabled = os.environ.get(NINJASRE_MASKING_ENABLED_ENV, "").strip().lower()
        return cls(
            policy=MaskingPolicy.from_level(level),
            rules=RulesetLoader(path=configured_rules_path()),
            masking_enabled=(
                MASKING_ENABLED_BY_DEFAULT if not enabled else enabled not in _FALSE_VALUES
            ),
        )

    def without(self, *switches: str) -> TrustControls:
        """Return these controls with ``switches`` turned off.

        Raises on a switch nobody defined. An ablation that silently ignored an
        unknown axis would publish a table saying it measured something it never
        varied, which is worse than not measuring it.
        """
        unknown = set(switches) - set(TRUST_SWITCHES)
        if unknown:
            raise ValueError(
                f"unknown trust switch(es) {', '.join(sorted(unknown))}; "
                f"expected one of {', '.join(TRUST_SWITCHES)}"
            )
        return replace(
            self,
            masking_enabled=self.masking_enabled and MASKING_SWITCH not in switches,
            guardrails_enabled=self.guardrails_enabled and GUARDRAILS_SWITCH not in switches,
        )

    def masking_context(self) -> MaskingContext:
        """Return a fresh run-scoped masking context, empty when masking is off."""
        policy = self.policy if self.masking_enabled else MaskingPolicy(level=MaskingLevel.OFF)
        return MaskingContext(policy=policy)

    def engine(self) -> GuardrailEngine:
        """Return the guardrail engine, observing rather than acting when switched off."""
        if self.guardrails_enabled:
            return GuardrailEngine(ruleset=self.rules)
        return GuardrailEngine.observing(ruleset=self.rules)

    def sink_guard(self, context: MaskingContext | None = None) -> SinkGuard:
        """Return the guard the transmission and persistence boundaries use."""
        return SinkGuard(engine=self.engine(), masking=context)

    def wrap(self, client: LLMClient, context: MaskingContext) -> LLMClient:
        """Return ``client`` behind the masking boundary, or unchanged when off.

        Returning the client unchanged rather than wrapping it in a no-op
        matters for the ablation: "masking off" should be the same call path a
        deployment with no masking takes, not a wrapper that happens to do
        nothing.
        """
        if not self.masking_enabled or not context.active:
            return client
        return MaskingLLMClient(inner=client, context=context)

    def install(
        self,
        hooks: HookRegistry,
        *,
        auditor: GuardrailAuditor | None = None,
        org_id: str = "",
        team_id: str = "",
    ) -> GuardrailHooks:
        """Attach the guardrail hooks to ``hooks`` and return them.

        The hooks are returned rather than the registry because the caller needs
        them at the end of the run: they carry the tally the run trace records.
        """
        bound = GuardrailHooks(
            engine=self.engine(), auditor=auditor, org_id=org_id, team_id=team_id
        )
        bound.register(hooks)
        return bound

    def trace_summary(self) -> dict[str, object]:
        """Return what the run trace records about how these controls were configured.

        The configuration, not the findings. What actually happened during the
        run comes from ``MaskingContext.trace_summary`` and
        ``GuardrailHooks.trace_summary``, and keeping the three separate is what
        lets an ablation table say "masking was off" independently of "and
        therefore nothing was masked".
        """
        return {
            "masking_enabled": self.masking_enabled,
            "masking_level": self.policy.level.value if self.masking_enabled else "off",
            "guardrails_enabled": self.guardrails_enabled,
            "guardrail_rules": len(self.engine().ruleset.enabled),
        }


__all__ = [
    "GUARDRAILS_SWITCH",
    "MASKING_SWITCH",
    "TRUST_SWITCHES",
    "TrustControls",
]
