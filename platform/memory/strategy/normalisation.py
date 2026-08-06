"""Deciding when two component names are the same subject, conservatively.

A team hits the same failure on the same service five times and the corpus
records it under `payments-api`, `payments-service`, `prod-payments`, and
`payments-7f9dd8b6c4-x7gr9`. Keyed on the raw name that is four subjects with one
or two episodes each, the synthesis threshold is never reached, and a feature
that generates playbooks generates none. Normalisation is what makes the
threshold reachable, and it is the reason this module exists at all.

It is also the module most able to do damage. Merging `payments` with
`payment-gateway` would produce a playbook about two systems presented as one,
and every claim in it would be wrong for whichever one the reader was looking at.
So the bias runs one way: **when in doubt, keep them apart.** A missed merge costs
a playbook that does not exist yet. A wrong merge costs a playbook that is
confidently misleading, and nothing downstream can detect it.

Four consequences of that bias, each of which is a rule here:

- The suffix list is short and closed. It holds the words that describe *what a
  thing is* in a deployment — `api`, `service`, `worker` — and not words that
  could name a different subject. `gateway` is deliberately absent: `payments`
  and `payment-gateway` are routinely two systems.
- Stripping never empties a name. A component called `service` normalises to
  `service`, not to nothing, because the alternative silently merges every
  generically-named component in the corpus.
- The type is always part of the key, so a `service:payments` and a
  `database:payments` never meet however their names normalise.
- Anything the rules do not cover requires an operator to say so, through the
  alias map. Inference stops here; an alias is a human decision and is recorded
  as one.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from platform.memory.models import COMPONENT_SEPARATOR, Component

#: Words that say what kind of thing a component is rather than which thing it
#: is. Stripped from either end of the name.
#:
#: Short and closed on purpose. Every entry here is a word that, removed, leaves
#: the subject intact — and the review question for a proposed addition is not
#: "is this a common suffix" but "is there any deployment in which this word
#: distinguishes two systems". `gateway`, `proxy`, `db`, and `cache` all fail
#: that question and are therefore not here.
DESCRIPTIVE_AFFIXES: frozenset[str] = frozenset(
    {
        "api",
        "app",
        "deploy",
        "deployment",
        "server",
        "service",
        "services",
        "srv",
        "svc",
        "worker",
        "workers",
    }
)

#: Words naming a deployment environment. Two environments of one service share
#: failure modes far more often than they differ, and an operator who wants them
#: apart has the alias map to say so.
ENVIRONMENT_AFFIXES: frozenset[str] = frozenset(
    {
        "canary",
        "dev",
        "development",
        "int",
        "integration",
        "live",
        "preprod",
        "prod",
        "production",
        "qa",
        "sandbox",
        "stage",
        "staging",
        "test",
        "testing",
        "uat",
    }
)

#: A generated segment: a Kubernetes replica-set hash, a pod suffix, a build id.
#: Requires a digit *and* a length no human picks, so `payments-v2` and
#: `api-2` survive while `7f9dd8b6c4` and `x7gr9` do not.
_GENERATED_SEGMENT = re.compile(r"^(?=.*\d)[0-9a-f]{5,}$|^(?=.*\d)[0-9a-z]{8,}$")

#: A trailing numeric segment, as in `payments-0` or `kafka-2`. Stripped only
#: from the end, where it is an ordinal in a stateful set rather than a version:
#: a leading or middle number is part of the name.
_ORDINAL_SEGMENT = re.compile(r"^\d+$")

#: Splits a camel-case or Pascal-case name at its boundaries, so `PaymentsAPI`
#: and `paymentsApi` reach the same segments as `payments-api`.
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")

#: Everything that separates one segment of a name from the next, across the
#: conventions in use: Kubernetes dashes, Python underscores, DNS dots, and the
#: slashes in a namespaced resource.
_SEPARATORS = re.compile(r"[^0-9a-zA-Z]+")

#: The team-configuration key an operator's alias map is read from.
ALIAS_MAP_CONFIG_KEY = "component_aliases"


def segments(name: str) -> tuple[str, ...]:
    """Return ``name`` split into lowercase segments, separators and case both."""
    spaced = _CAMEL_BOUNDARY.sub("-", name.strip())
    return tuple(part.lower() for part in _SEPARATORS.split(spaced) if part)


def _truncate_at_generated(parts: tuple[str, ...]) -> tuple[str, ...]:
    """Return ``parts`` cut at its first generated segment.

    Cut rather than filtered, because of what follows one. A Kubernetes pod is
    ``<workload>-<replicaset hash>-<five random characters>``, and the five random
    characters are indistinguishable from a real name segment on their own —
    ``x7gr9`` could be somebody's service. What identifies them is their
    *position*: nothing meaningful follows a replica-set hash, so everything after
    the first generated segment goes with it.
    """
    for index, part in enumerate(parts):
        if _GENERATED_SEGMENT.match(part):
            return parts[:index] if index else parts
    return parts


def _peel_affixes(parts: tuple[str, ...]) -> tuple[str, ...]:
    """Return ``parts`` with its describing and environment segments peeled off both ends.

    Repeatedly, because they stack: ``prod-payments-api-service`` is an
    environment, a subject, and two words for what the subject is. A single pass
    over the original edges would leave the inner ``api`` behind.

    A name made entirely of strippable words — ``prod-api``, or a component
    literally called ``service`` — is returned untouched. Peeling it would leave
    whichever word happened to survive the order of the passes, so ``prod-api``
    and ``api-prod`` would normalise to different keys while meaning the same
    thing. Keeping both whole leaves them distinct, which is the conservative
    outcome, and it stops every generically-named component in the corpus being
    filed under one key.
    """
    if all(_is_affix(part) or _ORDINAL_SEGMENT.match(part) for part in parts):
        return parts

    kept = list(parts)
    # Ordinals first. A stateful set's `api-2` peeled from the front instead
    # would lose `api` and normalise to the bare number, which is a key no
    # component should ever be filed under.
    while len(kept) > 1 and _ORDINAL_SEGMENT.match(kept[-1]):
        kept.pop()
    while len(kept) > 1 and _is_affix(kept[-1]):
        kept.pop()
    while len(kept) > 1 and _is_affix(kept[0]):
        kept.pop(0)
    return tuple(kept)


def _is_affix(part: str) -> bool:
    """Return whether one segment says what a thing is rather than which thing."""
    return part in DESCRIPTIVE_AFFIXES or part in ENVIRONMENT_AFFIXES


def normalise_name(name: str) -> str:
    """Return the canonical form of a component's name, before any alias."""
    parts = _peel_affixes(_truncate_at_generated(segments(name)))
    return "-".join(parts)


@dataclass(frozen=True, slots=True)
class ComponentNormaliser:
    """The documented rules, plus whatever the operator has declared equivalent.

    ``aliases`` maps a normalised name onto the name it should be filed under.
    It is applied *after* the rules, so an operator declaring `cart` for
    `checkout` covers `checkout-service`, `prod-checkout`, and `CheckoutAPI`
    without having to enumerate them.

    Aliases are resolved transitively, with a bound. A chain is an operator
    writing `a → b` and later `b → c` and expecting `a → c`, which is reasonable;
    a cycle is a typo, and it must not hang the process that reads the map.
    """

    aliases: Mapping[str, str] = field(default_factory=dict)

    def normalise(self, component: Component) -> str:
        """Return the strategy key ``component`` files under, as ``type:name``.

        The type is never dropped and never aliased. It is the one part of a
        component's identity that comes from the system rather than from
        somebody's naming convention, and keeping it in the key is what
        guarantees a `service:payments` and a `database:payments` stay two
        subjects however aggressively their names are folded together.
        """
        return (
            f"{component.type.strip().lower()}{COMPONENT_SEPARATOR}{self.canonical(component.name)}"
        )

    def canonical(self, name: str) -> str:
        """Return the normalised, alias-resolved form of a bare component name."""
        current = normalise_name(name)
        seen = {current}
        # Bounded by the map's own size: a chain cannot be longer than the number
        # of entries without revisiting one, and revisiting one is the cycle.
        for _ in range(len(self.aliases)):
            target = self.aliases.get(current)
            if target is None:
                return current
            resolved = normalise_name(target)
            if resolved in seen or not resolved:
                return current
            current = resolved
            seen.add(current)
        return current

    def keys_for(self, components: tuple[Component, ...]) -> tuple[str, ...]:
        """Return the distinct strategy keys ``components`` belong to, in order."""
        found: dict[str, None] = {}
        for component in components:
            found.setdefault(self.normalise(component), None)
        return tuple(found)

    @classmethod
    def from_config(cls, values: Mapping[str, Any]) -> ComponentNormaliser:
        """Return the normaliser one team's configuration describes.

        The alias map is read from ``component_aliases`` and anything unusable in
        it is dropped rather than raising. A malformed entry in a team's config
        must not take out synthesis for that team: the consequence of ignoring it
        is two component keys that stay separate, which is the conservative
        outcome this module defaults to anyway.
        """
        declared = values.get(ALIAS_MAP_CONFIG_KEY)
        if not isinstance(declared, Mapping):
            return cls()

        aliases: dict[str, str] = {}
        for source, target in declared.items():
            if not isinstance(source, str) or not isinstance(target, str):
                continue
            key, value = normalise_name(source), normalise_name(target)
            if key and value and key != value:
                aliases[key] = value
        return cls(aliases=aliases)


#: The rules with no operator map behind them. Every caller that has not loaded a
#: team's configuration uses this one, and it is the behaviour the fixture table
#: in the test suite pins.
DEFAULT_NORMALISER = ComponentNormaliser()


__all__ = [
    "ALIAS_MAP_CONFIG_KEY",
    "DEFAULT_NORMALISER",
    "DESCRIPTIVE_AFFIXES",
    "ENVIRONMENT_AFFIXES",
    "ComponentNormaliser",
    "normalise_name",
    "segments",
]
