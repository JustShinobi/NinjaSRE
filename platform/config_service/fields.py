"""Every field configuration has, derived from the schema that validates it.

An editor needs four things about a field before it can draw a control for it:
the type, the range, the default, and what it is for. There is exactly one place
in this deployment that already knows all four — the Pydantic sections in
``schema/`` — and this module reads them rather than restating them.

That direction matters more than it looks. The alternative is a table of field
descriptions kept beside whatever is rendering the form. It agrees with the
schema on the day it is written and drifts from then on, and the drift arrives
as a control that offers a value the write path refuses, or a field the
deployment gained and the form never grew. Deriving means a field added to a
section is a control on the same commit, and a control on offer is a field the
validator accepts.

**A list is a leaf.** The merge replaces a list entirely rather than merging it
(``merge.py``), so an editor offering to change one entry would be offering an
operation the write path does not have. ``leaves`` already takes this view and
this module agrees with it, because a catalogue that disagreed with the merge
would describe fields that cannot be addressed.

**A node's policies narrow the control, never widen it.** A ceiling declared on
a path tightens whatever the schema declares; a policy naming a higher one is
ignored. The schema's bound is the deployment's, and a form that offered a
value past it would be a form whose every submission is refused.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Final

from config.constants.config_service import MAX_CONFIG_DEPTH
from platform.config_service import paths
from platform.config_service.document import NodeDocument
from platform.config_service.effective import EffectiveConfig
from platform.config_service.merge import locking_node
from platform.config_service.schema.root import RootConfig

#: Where a ``$ref`` points inside a generated document.
_REF_PREFIX: Final = "#/$defs/"

#: The keywords a bound arrives under. Pydantic emits ``ge``/``le`` for a
#: constraint it cannot inline, and ``minimum``/``maximum`` when it can; a
#: reader that knew only one of the pairs would silently drop half the ranges.
_LOWER: Final = ("minimum", "exclusiveMinimum", "ge")
_UPPER: Final = ("maximum", "exclusiveMaximum", "le")


@dataclass(frozen=True, slots=True)
class ConfigField:
    """One editable field, as the schema describes it.

    ``section`` is the dotted path of the mapping this field sits in, and
    ``section_summary`` is that section's own description. The two are separate
    from ``description`` deliberately: most leaves document themselves through
    the section they belong to, and presenting a section's sentence as a field's
    own would attribute a claim to the wrong thing.
    """

    path: str
    label: str
    type: str
    description: str = ""
    section: str = ""
    section_summary: str = ""
    default: Any = None
    minimum: float | None = None
    maximum: float | None = None
    max_items: int | None = None
    max_length: int | None = None
    allowed_values: tuple[Any, ...] | None = None


@dataclass(frozen=True, slots=True)
class NodeField:
    """One field as it stands at one node: what it is, and where it comes from.

    ``set_here`` is the whole basis of clear-to-inherit. A field showing this
    node in ``provenance`` is a field this node overrides, and the only field
    for which "remove this override" is an operation at all.
    """

    field: ConfigField
    value: Any = None
    #: The node supplying the effective value, or empty when nothing sets it.
    provenance: str = ""
    set_here: bool = False
    #: The node locking this path or an ancestor of it, or empty.
    locked_by: str = ""
    approval_gated: bool = False
    required: bool = False
    #: Narrowed by this node's policies, so a control never offers a refused value.
    maximum: float | None = None
    allowed_values: tuple[Any, ...] | None = None


@lru_cache(maxsize=1)
def declared_fields() -> tuple[ConfigField, ...]:
    """Return every editable field the configuration schema declares, in path order.

    Cached because it is derived from a class rather than from a request, and a
    client caches the answer: a set that reordered between two requests would
    reorder the form under somebody's cursor.
    """
    document = RootConfig.model_json_schema()
    definitions = document.get("$defs", {})
    collected: list[ConfigField] = []
    _walk(document, definitions, "", "", collected, 0)
    return tuple(collected)


def fields_at(effective: EffectiveConfig, document: NodeDocument) -> tuple[NodeField, ...]:
    """Return every declared field as it stands at the node ``effective`` resolves.

    ``document`` is that node's *own* stored settings, unmerged. It is a second
    argument rather than something read off the effective view because the
    effective view cannot answer "does this node set it": a provenance entry
    naming the node is close, and wrong for the case a node sets a value its
    parent also sets to the same thing.
    """
    values = dict(paths.leaves(effective.values))
    own = dict(paths.leaves(document.settings))
    return tuple(_at(declared, effective, values, own) for declared in declared_fields())


def _at(
    declared: ConfigField,
    effective: EffectiveConfig,
    values: Mapping[str, Any],
    own: Mapping[str, Any],
) -> NodeField:
    """Return ``declared`` as it stands, with the node's policies applied."""
    policy = effective.policies.for_path(declared.path)
    governing = effective.policies.governing(declared.path)
    return NodeField(
        field=declared,
        value=values.get(declared.path),
        provenance=effective.provenance.get(declared.path, ""),
        set_here=declared.path in own,
        locked_by=locking_node(effective.locks, declared.path) or "",
        approval_gated=any(each.approval_gated for each in governing),
        required=policy is not None and policy.required,
        maximum=_narrower(declared.maximum, None if policy is None else policy.max_value),
        allowed_values=_intersected(
            declared.allowed_values, None if policy is None else policy.allowed_values
        ),
    )


def _narrower(declared: float | None, policy: float | None) -> float | None:
    """Return the tighter of two ceilings, either of which may be absent."""
    if declared is None:
        return policy
    if policy is None:
        return declared
    return min(declared, policy)


def _intersected(
    declared: tuple[Any, ...] | None, policy: tuple[Any, ...] | None
) -> tuple[Any, ...] | None:
    """Return the values both sets allow, in the schema's order."""
    if declared is None:
        return policy
    if policy is None:
        return declared
    return tuple(value for value in declared if value in policy)


def _walk(
    schema: Mapping[str, Any],
    definitions: Mapping[str, Any],
    prefix: str,
    summary: str,
    collected: list[ConfigField],
    depth: int,
) -> None:
    """Append every leaf under ``schema`` to ``collected``, in declaration order."""
    if depth > MAX_CONFIG_DEPTH:
        return
    for name, raw in schema.get("properties", {}).items():
        spec = _resolved(raw, definitions)
        path = f"{prefix}{paths.PATH_SEPARATOR}{name}" if prefix else name
        if _descends(spec):
            _walk(
                spec,
                definitions,
                path,
                str(spec.get("description", "")),
                collected,
                depth + 1,
            )
            continue
        collected.append(
            ConfigField(
                path=path,
                label=str(raw.get("title") or spec.get("title") or name),
                type=_type_of(spec),
                description=str(raw.get("description", spec.get("description", ""))),
                section=prefix,
                section_summary=summary,
                default=raw.get("default", spec.get("default")),
                minimum=_bound(spec, _LOWER),
                maximum=_bound(spec, _UPPER),
                max_items=_int_or_none(spec.get("maxItems")),
                max_length=_int_or_none(spec.get("maxLength")),
                allowed_values=_allowed(spec),
            )
        )


def _descends(spec: Mapping[str, Any]) -> bool:
    """Return whether this schema node is a section rather than a field.

    An object with declared properties is a section. An object *without* them is
    a free-form mapping — capability parameters, a label set — and it is a leaf,
    because its keys are the operator's rather than the schema's and no control
    could be derived for a name nobody has written yet.
    """
    return spec.get("type") == "object" and bool(spec.get("properties"))


def _resolved(spec: Mapping[str, Any], definitions: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return ``spec`` with one ``$ref`` or optional ``anyOf`` branch followed.

    An optional field arrives as ``anyOf: [<the type>, null]``, and the null
    branch describes nothing an editor can draw. Following the first branch that
    is not null gives the control the operator would expect: a field that may be
    unset is still a field of some type.
    """
    reference = spec.get("$ref")
    if isinstance(reference, str) and reference.startswith(_REF_PREFIX):
        return definitions.get(reference[len(_REF_PREFIX) :], {})

    branches = spec.get("anyOf") or spec.get("oneOf")
    if isinstance(branches, Sequence):
        for branch in branches:
            if isinstance(branch, Mapping) and branch.get("type") != "null":
                return _resolved(branch, definitions)
    return spec


def _type_of(spec: Mapping[str, Any]) -> str:
    """Return the JSON type of a leaf, or ``string`` when nothing says.

    A field whose type cannot be read renders as text rather than as nothing:
    an operator can always type the value, and a control that failed to appear
    is a field they cannot reach at all.
    """
    declared = spec.get("type")
    return str(declared) if isinstance(declared, str) else "string"


def _bound(spec: Mapping[str, Any], keywords: Sequence[str]) -> float | None:
    """Return the first bound ``spec`` declares under any of ``keywords``."""
    for keyword in keywords:
        found = spec.get(keyword)
        if isinstance(found, int | float) and not isinstance(found, bool):
            return float(found)
    return None


def _int_or_none(value: Any) -> int | None:
    """Return ``value`` as an integer, or ``None`` if it is not one."""
    return int(value) if isinstance(value, int) and not isinstance(value, bool) else None


def _allowed(spec: Mapping[str, Any]) -> tuple[Any, ...] | None:
    """Return the closed set of values ``spec`` declares, if it declares one."""
    found = spec.get("enum")
    return tuple(found) if isinstance(found, Sequence) and not isinstance(found, str) else None


__all__ = ["ConfigField", "NodeField", "declared_fields", "fields_at"]
