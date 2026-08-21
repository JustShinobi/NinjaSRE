"""Typed attributes, and the screening every provider value passes before storage.

Two jobs, and they are separate on purpose.

**Typing** is what keeps a generic resource model from becoming a schemaless
bag. A kind declares the attributes it has and what type each one is; anything
else a provider sends is dropped rather than stored, and a declared attribute of
the wrong type is reported rather than coerced. Coercion would be friendlier and
would mean an operator's "cores" column silently holding the string ``"many"``.

**Screening** is what keeps a secret or a personal identifier out of the
database. It reuses the two mechanisms the deployment already has rather than
inventing a third: the guardrail ruleset, which is where secret shapes are
declared, and the masking policy, which is where identifier shapes are. Neither
gains an estate-specific rule — a rule that applied to the estate and not to a
report would be a rule an operator could not reason about.

Screening applies to attribute *values* and never to a resource's kind, source,
native identifier, display name, or parent. Those are the estate's own
structure: an operator looking for ``pve1`` has to be able to find ``pve1``, and
a display name replaced by a token is a resource nobody can search for.
Attributes are the free-form half — the half where a hypervisor cheerfully
returns a guest's cloud-init user data — and they are what NFR-005 is about.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Final

from platform.guardrails.engine import GuardrailEngine
from platform.masking.apply import mask
from platform.masking.mapping import MaskMapping
from platform.masking.policy import DEFAULT_POLICY, MaskingPolicy


class AttributeType(StrEnum):
    """What a declared attribute holds.

    Five, and no ``object``. An attribute whose type is "anything" is the bag
    this module exists to prevent, and a provider that genuinely has nested
    structure to report has a kind of its own to declare.
    """

    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    TIMESTAMP = "timestamp"

    def accepts(self, value: Any) -> bool:
        """Return whether ``value`` is already of this type.

        ``bool`` is checked before ``int`` throughout, because Python's ``bool``
        *is* an ``int`` and an ``enabled: True`` landing in an integer column
        would store ``1`` and read back as a number nobody wrote.
        """
        match self:
            case AttributeType.STRING:
                return isinstance(value, str)
            case AttributeType.INTEGER:
                return isinstance(value, int) and not isinstance(value, bool)
            case AttributeType.FLOAT:
                return isinstance(value, float | int) and not isinstance(value, bool)
            case AttributeType.BOOLEAN:
                return isinstance(value, bool)
            case AttributeType.TIMESTAMP:
                return isinstance(value, datetime)

    def stored(self, value: Any) -> Any:
        """Return ``value`` in the form the repository persists.

        Only timestamps change: everything else is already JSON. An ISO 8601
        string rather than an epoch number, because an operator reading a JSONB
        column should not have to convert one in their head.
        """
        if self is AttributeType.TIMESTAMP and isinstance(value, datetime):
            return value.isoformat()
        return value


@dataclass(frozen=True, slots=True)
class TypedAttributes:
    """What survived typing, and what did not.

    ``dropped`` and ``invalid`` are returned rather than logged here, because
    the caller knows which resource and which sweep they belong to and this
    function does not. The sweep logs them once per sweep rather than once per
    resource, which is the difference between a diagnosable warning and a wall.
    """

    values: Mapping[str, Any] = field(default_factory=dict)
    dropped: tuple[str, ...] = ()
    invalid: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ScreenedAttributes:
    """Attribute values with secrets redacted and identifiers masked.

    ``screened`` names the attributes that were altered, so a sweep can report
    that something was found without reporting what it was.
    """

    values: Mapping[str, Any] = field(default_factory=dict)
    screened: tuple[str, ...] = ()


def typed(
    declared: Mapping[str, AttributeType],
    raw: Mapping[str, Any],
) -> TypedAttributes:
    """Return ``raw`` reduced to what ``declared`` allows, with the rest named."""
    values: dict[str, Any] = {}
    dropped: list[str] = []
    invalid: list[str] = []

    for name in sorted(raw):
        attribute_type = declared.get(name)
        if attribute_type is None:
            dropped.append(name)
        elif attribute_type.accepts(raw[name]):
            values[name] = attribute_type.stored(raw[name])
        else:
            invalid.append(name)

    return TypedAttributes(values=values, dropped=tuple(dropped), invalid=tuple(invalid))


#: Attributes that are the estate's own structure rather than free-form provider
#: detail, and are therefore redacted but never masked.
#:
#: The rule this extends is the one the kind, source, native identifier and
#: display name already hold: an operator looking for ``pve1`` has to be able to
#: find ``pve1``, and a value replaced by a token is a resource nobody can
#: search for. An address is the same kind of thing twice over — it is how a
#: resource is found *and* what its zone is derived from, so a masked one turns
#: an estate divided into seven networks into an estate divided into none. A
#: domain is the edge between "the site is not answering" and "this container
#: is down", and a masked one cannot be resolved to anything.
#:
#: Secret *redaction* still applies to them. What is exempt is identifier
#: masking, which exists to stop an infrastructure name reaching a model the
#: deployment does not host — a decision taken where a prompt is built, not by
#: making the estate unable to describe itself.
STRUCTURAL_ATTRIBUTES: Final[frozenset[str]] = frozenset({"address", "domain"})


def screened(
    values: Mapping[str, Any],
    *,
    engine: GuardrailEngine | None = None,
    policy: MaskingPolicy | None = None,
) -> ScreenedAttributes:
    """Return ``values`` with secrets redacted and identifiers masked.

    Non-string values pass through untouched: a core count cannot carry a
    secret, and scanning an integer costs a string conversion per attribute per
    sweep for nothing.

    The mask mapping is local to this call and is deliberately thrown away. It
    is the table that would turn a token back into the identifier, so keeping it
    beside the masked value in the same database would make the masking
    decorative. An operator who needs the identifier has the resource's own
    display name and native identifier, which are never masked.
    """
    scanner = engine if engine is not None else GuardrailEngine()
    masking = policy if policy is not None else DEFAULT_POLICY
    mapping = MaskMapping()

    kept: dict[str, Any] = {}
    altered: list[str] = []

    for name in sorted(values):
        value = values[name]
        if not isinstance(value, str):
            kept[name] = value
            continue

        redacted = scanner.scan(value).text
        masked = (
            redacted
            if name in STRUCTURAL_ATTRIBUTES
            else mask(redacted, policy=masking, mapping=mapping)
        )
        kept[name] = masked
        if masked != value:
            altered.append(name)

    return ScreenedAttributes(values=kept, screened=tuple(altered))


__all__ = [
    "STRUCTURAL_ATTRIBUTES",
    "AttributeType",
    "ScreenedAttributes",
    "TypedAttributes",
    "screened",
    "typed",
]
