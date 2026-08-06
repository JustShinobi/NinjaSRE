"""Strategy synthesis: what a set of episodes says that no single one of them does.

An episode is an anecdote. Five episodes of the same failure on the same
component are a pattern, and this package is what turns the second into a
playbook — the causes that recur, the investigation order that worked, the
capabilities that produced findings, and the approaches that looked promising and
did not.

That last section is the reason the feature exists. Runbooks describe what should
work; documentation describes what a system is for. Only accumulated failure
describes what an experienced engineer would have told you not to bother with,
and the anti-patterns section is the only part of a playbook that cannot be
written from documentation. It is derived from the runs that failed and it is
labelled as such, because it is also the section where an invention would be
indistinguishable from a finding.

Four decisions shape the package.

**Component keys are normalised, conservatively.** Without it, ``payments``,
``payments-api``, and ``payments-7f9dd-x7gr9`` are three keys with two episodes
each and the synthesis threshold is never reached. With it done carelessly,
``payments`` and ``payment-gateway`` become one playbook describing two systems.
The bias runs toward keeping things apart, and merging anything the rules do not
cover requires an operator to say so.

**Playbooks are cached and invalidated on the write side.** Synthesis is a model
call over a dozen episodes and cannot sit on an incident's critical path. The
episode write marks the keys it bears on stale, so the cache is invalidated by a
fact rather than by a guess, and age forces regeneration on its own because
infrastructure is retired without producing an episode.

**Concurrent requests for one key produce one generation.** An alert storm is N
investigations of the same component at once, and the alternative is N playbooks
of which one survives at random.

**Operator edits survive regeneration.** A human correcting a playbook is the
highest-quality signal this system receives, and an operator whose correction
disappears at the next regeneration learns to stop correcting.

Everything is behind one switch, separate from the two that gate episodic memory,
because the question this feature has to answer is not "does memory help" but "do
playbooks help, given the episodes were already there".
"""

from __future__ import annotations

from platform.memory.strategy.cache import KeyedLock, StrategyCache, StrategyLookup
from platform.memory.strategy.generator import (
    StrategyGenerator,
    SynthesisOutcome,
    split_by_outcome,
    synthesis_input,
)
from platform.memory.strategy.invalidation import StrategyInvalidator, invalidation_keys
from platform.memory.strategy.models import (
    OperatorEdit,
    Strategy,
    StrategyKey,
    StrategySection,
    SynthesisInput,
)
from platform.memory.strategy.normalisation import (
    DEFAULT_NORMALISER,
    ComponentNormaliser,
    normalise_name,
)
from platform.memory.strategy.policy import STRATEGY_SWITCH, STRATEGY_SWITCHES, StrategyPolicy
from platform.memory.strategy.prompt import synthesis_request
from platform.memory.strategy.service import (
    StrategyDirectory,
    StrategyRecall,
    candidate_keys,
    episodes_on_key,
    keys_for_episode,
)

__all__ = [
    "DEFAULT_NORMALISER",
    "STRATEGY_SWITCH",
    "STRATEGY_SWITCHES",
    "ComponentNormaliser",
    "KeyedLock",
    "OperatorEdit",
    "Strategy",
    "StrategyCache",
    "StrategyDirectory",
    "StrategyGenerator",
    "StrategyInvalidator",
    "StrategyKey",
    "StrategyLookup",
    "StrategyPolicy",
    "StrategyRecall",
    "StrategySection",
    "SynthesisInput",
    "SynthesisOutcome",
    "candidate_keys",
    "episodes_on_key",
    "invalidation_keys",
    "keys_for_episode",
    "normalise_name",
    "split_by_outcome",
    "synthesis_input",
    "synthesis_request",
]
