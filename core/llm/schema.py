"""Rewrites a tool's JSON Schema into the dialect one provider will accept.

This is the module that decides whether a turn happens. Every selected tool goes
out in a single request, so one schema a provider rejects fails the whole turn —
not that tool, the turn. A `oneOf` somebody wrote without thinking, a `$ref` into
`$defs`, a `"type": ["string", "null"]`: each is idiomatic JSON Schema and each
is rejected by at least one supported provider.

The shape is a dialect plus a rule chain. A dialect states what a provider
accepts; the chain rewrites a schema until it does. A tenth provider is one
:class:`SchemaDialect` and nothing else.

Two invariants hold for every rule, and the contract suite asserts both:

- **Idempotent.** Normalising an already-normalised schema changes nothing.
  Without this, a retry that re-normalises produces a different request than the
  one that failed, and the failure becomes unreproducible.
- **No required field disappears.** A rule may retype a property, relocate a
  keyword, or drop a `format`. It may not remove something the caller declared
  required, because the model would then be unable to call the tool correctly
  and nothing would say why.

The one rule that can lose information is the depth cap, and it is loud about
it: the property survives with its type widened and the reason written into its
description. Every shipped schema sits well inside every provider's cap.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any

from config.constants.llm import (
    PROVIDER_ANTHROPIC,
    PROVIDER_AWS_BEDROCK,
    PROVIDER_AZURE_OPENAI,
    PROVIDER_GOOGLE_GEMINI,
    PROVIDER_GOOGLE_VERTEX_AI,
    PROVIDER_NVIDIA_NIM,
    PROVIDER_OLLAMA,
    PROVIDER_OPENAI,
    PROVIDER_OPENROUTER,
)
from core.llm.types import ToolSchema

#: Keywords that describe the document rather than the data. Providers either
#: ignore them or reject them; none needs them.
_META_KEYWORDS = frozenset({"$schema", "$id", "$comment", "$anchor"})

#: Where ``$ref`` targets live. Stripped only once the refs pointing at them
#: have been inlined — dropping them while a ``$ref`` still points there leaves
#: a dangling pointer, which every provider rejects and which silently takes
#: the referenced object's required fields with it.
_DEFINITION_KEYWORDS = frozenset({"definitions", "$defs"})

#: Constraints a strict dialect drops. ``enum`` and ``const`` are deliberately
#: absent — they carry meaning the model uses to pick a value, where the rest
#: only reject one after the fact.
_VALIDATION_KEYWORDS = frozenset(
    {
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
        "minLength",
        "maxLength",
        "pattern",
        "minItems",
        "maxItems",
        "uniqueItems",
        "minProperties",
        "maxProperties",
        "default",
        "examples",
        "contentEncoding",
        "contentMediaType",
    }
)

#: Where a nested schema can hang off a node, so the walk finds all of them.
_SCHEMA_VALUED_KEYS = ("items", "not", "if", "then", "else", "contains", "propertyNames")
_SCHEMA_LIST_KEYS = ("anyOf", "oneOf", "allOf", "prefixItems")
_SCHEMA_MAP_KEYS = ("properties", "patternProperties")

#: How many characters of a hash are appended when a name has to be truncated.
#: Six is enough that two 64-character prefixes cannot collide in a catalogue of
#: any size a turn could carry, and short enough to leave the name readable.
_NAME_HASH_LENGTH = 6

_JSON_TYPES = ("object", "array", "string", "number", "integer", "boolean", "null")


class AdditionalPropertiesRule(StrEnum):
    """What a dialect does with ``additionalProperties``."""

    #: Leave it as written. The permissive draft-07 dialects.
    PRESERVE = "preserve"
    #: Force ``false`` on every object. Required by strict structured output.
    FORCE_FALSE = "force_false"
    #: Remove the keyword entirely. The OpenAPI-subset dialects reject it.
    STRIP = "strip"


@dataclass(frozen=True, slots=True)
class SchemaDialect:
    """What one provider accepts in a tool schema.

    Every field is a thing at least one provider gets wrong when you assume the
    other answer. The defaults are the strictest reading, so an unregistered
    provider is safe before anyone writes its row.
    """

    provider_id: str
    allows_union_types: bool = False
    allows_any_of: bool = False
    allows_one_of: bool = False
    allows_nested_composition: bool = False
    allows_refs: bool = False
    allows_nullable_keyword: bool = False
    additional_properties: AdditionalPropertiesRule = AdditionalPropertiesRule.STRIP
    allows_validation_keywords: bool = False
    requires_all_properties_required: bool = False
    supported_formats: frozenset[str] = frozenset()
    max_tool_name_length: int = 64
    max_tool_description_length: int = 1_024
    max_schema_depth: int = 8
    #: Characters permitted in a tool name. Everything else becomes ``_``.
    name_allowed_pattern: str = r"[^a-zA-Z0-9_-]"
    #: A name must start with one of these, which rules out a leading digit.
    name_must_start_with_letter: bool = True


_BROAD_FORMATS = frozenset(
    {
        "date-time",
        "date",
        "time",
        "duration",
        "email",
        "hostname",
        "ipv4",
        "ipv6",
        "uri",
        "uuid",
    }
)

#: OpenAI's strict structured-output subset. Narrower than draft-07 and the
#: reason `format: "duration"` fails there but not on Anthropic.
_OPENAI_FORMATS = frozenset(
    {"date-time", "time", "date", "duration", "email", "hostname", "ipv4", "ipv6", "uuid"}
)

#: Gemini and Vertex speak an OpenAPI 3.0 subset, where ``format`` is only
#: meaningful on a handful of types.
_OPENAPI_FORMATS = frozenset({"date-time", "enum", "int32", "int64", "float", "double", "byte"})


_ANTHROPIC_DIALECT = SchemaDialect(
    provider_id=PROVIDER_ANTHROPIC,
    allows_union_types=True,
    allows_any_of=True,
    allows_nested_composition=True,
    allows_refs=True,
    additional_properties=AdditionalPropertiesRule.PRESERVE,
    allows_validation_keywords=True,
    supported_formats=_BROAD_FORMATS,
    max_tool_name_length=64,
    max_tool_description_length=8_192,
    max_schema_depth=12,
)

_OPENAI_DIALECT = SchemaDialect(
    provider_id=PROVIDER_OPENAI,
    allows_union_types=True,
    allows_any_of=True,
    allows_nested_composition=True,
    allows_refs=True,
    # Strict mode rejects an open object outright, and rejects a schema-valued
    # map with it. Forcing `false` is what makes a map-shaped parameter work.
    additional_properties=AdditionalPropertiesRule.FORCE_FALSE,
    allows_validation_keywords=False,
    requires_all_properties_required=True,
    supported_formats=_OPENAI_FORMATS,
    max_tool_name_length=64,
    max_tool_description_length=1_024,
    max_schema_depth=10,
)

_AZURE_DIALECT = replace(_OPENAI_DIALECT, provider_id=PROVIDER_AZURE_OPENAI)

#: An aggregator cannot promise what its upstreams accept, and a rejected
#: schema costs a turn. So the routed dialects assume the intersection.
_OPENROUTER_DIALECT = SchemaDialect(
    provider_id=PROVIDER_OPENROUTER,
    allows_union_types=False,
    allows_any_of=True,
    allows_nested_composition=False,
    allows_refs=False,
    additional_properties=AdditionalPropertiesRule.FORCE_FALSE,
    allows_validation_keywords=False,
    supported_formats=_OPENAI_FORMATS,
    max_schema_depth=8,
)

_NVIDIA_DIALECT = replace(_OPENROUTER_DIALECT, provider_id=PROVIDER_NVIDIA_NIM)

#: A quantised local model produces malformed tool calls when a schema gets
#: clever. The narrowest dialect is not a limitation here, it is the point.
_OLLAMA_DIALECT = SchemaDialect(
    provider_id=PROVIDER_OLLAMA,
    allows_union_types=False,
    allows_any_of=False,
    allows_nested_composition=False,
    allows_refs=False,
    additional_properties=AdditionalPropertiesRule.STRIP,
    allows_validation_keywords=False,
    supported_formats=frozenset(),
    max_tool_name_length=64,
    max_tool_description_length=1_024,
    max_schema_depth=6,
)

_BEDROCK_DIALECT = SchemaDialect(
    provider_id=PROVIDER_AWS_BEDROCK,
    allows_union_types=False,
    allows_any_of=True,
    allows_nested_composition=True,
    allows_refs=False,
    additional_properties=AdditionalPropertiesRule.PRESERVE,
    allows_validation_keywords=True,
    supported_formats=_BROAD_FORMATS,
    max_tool_name_length=64,
    max_tool_description_length=1_024,
    max_schema_depth=10,
)

#: The OpenAPI 3.0 subset: no `$ref`, no `additionalProperties`, nullability is
#: a keyword rather than a union.
_GEMINI_DIALECT = SchemaDialect(
    provider_id=PROVIDER_GOOGLE_GEMINI,
    allows_union_types=False,
    allows_any_of=True,
    allows_nested_composition=False,
    allows_refs=False,
    allows_nullable_keyword=True,
    additional_properties=AdditionalPropertiesRule.STRIP,
    allows_validation_keywords=False,
    supported_formats=_OPENAPI_FORMATS,
    max_tool_name_length=64,
    max_tool_description_length=1_024,
    max_schema_depth=8,
    name_allowed_pattern=r"[^a-zA-Z0-9_.-]",
)

_VERTEX_DIALECT = replace(_GEMINI_DIALECT, provider_id=PROVIDER_GOOGLE_VERTEX_AI)

_DIALECTS: dict[str, SchemaDialect] = {
    PROVIDER_ANTHROPIC: _ANTHROPIC_DIALECT,
    PROVIDER_OPENAI: _OPENAI_DIALECT,
    PROVIDER_AZURE_OPENAI: _AZURE_DIALECT,
    PROVIDER_OPENROUTER: _OPENROUTER_DIALECT,
    PROVIDER_NVIDIA_NIM: _NVIDIA_DIALECT,
    PROVIDER_OLLAMA: _OLLAMA_DIALECT,
    PROVIDER_AWS_BEDROCK: _BEDROCK_DIALECT,
    PROVIDER_GOOGLE_GEMINI: _GEMINI_DIALECT,
    PROVIDER_GOOGLE_VERTEX_AI: _VERTEX_DIALECT,
}


def dialect_for(provider_id: str) -> SchemaDialect:
    """Return the dialect for ``provider_id``.

    An unregistered provider gets the strictest dialect rather than the most
    permissive one. Being needlessly conservative costs a little schema
    expressiveness; guessing the other way costs a rejected turn on the first
    real investigation.
    """
    known = _DIALECTS.get(provider_id)
    if known is not None:
        return known
    return SchemaDialect(provider_id=provider_id)


def register_dialect(dialect: SchemaDialect) -> None:
    """Register or replace the dialect for one provider."""
    _DIALECTS[dialect.provider_id] = dialect


# --- Name and description handling -------------------------------------------


def _stable_suffix(value: str) -> str:
    """Return a short, deterministic suffix derived from ``value``."""
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return digest[:_NAME_HASH_LENGTH]


def normalise_tool_name(name: str, dialect: SchemaDialect) -> str:
    """Return ``name`` in a form ``dialect`` accepts.

    Truncation appends a hash of the *original* name rather than simply cutting.
    Two tools whose names differ only past the cap would otherwise arrive as one
    tool, and the model would call the wrong one with no error anywhere.
    """
    cleaned = re.sub(dialect.name_allowed_pattern, "_", name)
    if dialect.name_must_start_with_letter and cleaned and not re.match(r"[A-Za-z_]", cleaned):
        cleaned = f"t_{cleaned}"
    if not cleaned:
        cleaned = f"tool_{_stable_suffix(name)}"

    limit = dialect.max_tool_name_length
    if len(cleaned) <= limit:
        return cleaned

    keep = limit - (_NAME_HASH_LENGTH + 1)
    return f"{cleaned[:keep]}_{_stable_suffix(name)}"


def _truncate_description(description: str, dialect: SchemaDialect) -> str:
    limit = dialect.max_tool_description_length
    if len(description) <= limit:
        return description
    return description[:limit]


# --- Schema rewriting ---------------------------------------------------------


def _resolve_pointer(root: Mapping[str, Any], pointer: str) -> Mapping[str, Any] | None:
    """Return the node a local JSON pointer addresses, or ``None``."""
    if not pointer.startswith("#/"):
        return None
    node: Any = root
    for part in pointer[2:].split("/"):
        key = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, Mapping) or key not in node:
            return None
        node = node[key]
    return node if isinstance(node, Mapping) else None


def _inline_refs(node: Any, root: Mapping[str, Any], depth: int) -> Any:
    """Return ``node`` with every local ``$ref`` replaced by its target.

    A ref that cannot be resolved, or one that recurses past the depth budget,
    becomes a bare object rather than a dangling pointer: providers reject the
    pointer, and a bare object at least keeps the property callable.
    """
    if isinstance(node, list):
        return [_inline_refs(child, root, depth) for child in node]
    if not isinstance(node, Mapping):
        return node

    pointer = node.get("$ref")
    if isinstance(pointer, str):
        if depth <= 0:
            return {"type": "object"}
        target = _resolve_pointer(root, pointer)
        if target is None:
            return {"type": "object"}
        merged = {key: value for key, value in node.items() if key != "$ref"}
        resolved = _inline_refs(dict(target), root, depth - 1)
        if isinstance(resolved, dict):
            resolved.update(merged)
            return resolved
        return {"type": "object"}

    return {key: _inline_refs(value, root, depth) for key, value in node.items()}


def _object_branches(branches: Sequence[Any]) -> list[Mapping[str, Any]]:
    """Return the branches that are object schemas carrying properties."""
    return [
        branch
        for branch in branches
        if isinstance(branch, Mapping) and isinstance(branch.get("properties"), Mapping)
    ]


def _merge_object_branches(branches: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Return one object schema carrying every branch's properties.

    A discriminated union collapses to the union of its shapes, and ``required``
    to the intersection — the fields every alternative demands. Taking the union
    of ``required`` instead would demand `pod` *and* `node` on a schema that
    means one or the other, and the tool would become uncallable.

    Relaxing a field from required to optional is the cost. Deleting it is not
    on the table: the caller declared that parameter, and a model that cannot
    see it cannot use the tool at all.
    """
    properties: dict[str, Any] = {}
    required_sets: list[set[str]] = []
    for branch in branches:
        branch_properties = branch.get("properties")
        if isinstance(branch_properties, Mapping):
            for name, definition in branch_properties.items():
                properties.setdefault(name, definition)
        declared = branch.get("required")
        required_sets.append(set(declared) if isinstance(declared, list) else set())

    merged: dict[str, Any] = {"type": "object", "properties": properties}
    shared = set.intersection(*required_sets) if required_sets else set()
    if shared:
        merged["required"] = sorted(shared)
    return merged


def _collapse_composition(branches: list[Any]) -> Any:
    """Return one schema standing in for ``branches`` when composition is out.

    Object branches merge, so no declared property is lost. Anything else falls
    back to the first branch, which is arbitrary but *stable* — and stability is
    what makes a retry send the same request as the attempt that failed.
    Whatever is dropped is named in the description rather than vanishing.
    """
    if not branches:
        return {"type": "object", "properties": {}}

    objects = _object_branches(branches)
    if len(objects) > 1:
        merged = _merge_object_branches(objects)
        merged["description"] = (
            "One of several shapes; every field from each alternative is listed, "
            "so supply the fields belonging to the one you mean."
        )
        return merged

    chosen = dict(branches[0]) if isinstance(branches[0], Mapping) else {"type": "string"}
    if len(branches) > 1:
        alternatives = ", ".join(
            str(branch.get("type", "object")) if isinstance(branch, Mapping) else "object"
            for branch in branches[1:]
        )
        note = f"(this provider accepts one shape only; alternatives were: {alternatives})"
        existing = str(chosen.get("description", "")).strip()
        chosen["description"] = f"{existing} {note}".strip()
    return chosen


def _flatten_branches(branches: Iterable[Any]) -> list[Any]:
    """Return ``branches`` with any nested ``anyOf``/``oneOf`` spliced in."""
    flat: list[Any] = []
    for branch in branches:
        if isinstance(branch, Mapping):
            nested = branch.get("anyOf") or branch.get("oneOf")
            if isinstance(nested, list) and len(branch) == 1:
                flat.extend(_flatten_branches(nested))
                continue
        flat.append(branch)
    return flat


def _rewrite_union_type(node: dict[str, Any], dialect: SchemaDialect) -> dict[str, Any]:
    """Return ``node`` with a list-valued ``type`` expressed the dialect's way."""
    declared = node.get("type")
    if not isinstance(declared, list):
        return node

    members = [entry for entry in declared if isinstance(entry, str) and entry in _JSON_TYPES]
    if not members:
        node.pop("type", None)
        return node

    if dialect.allows_union_types:
        node["type"] = members
        return node

    nullable = "null" in members
    concrete = [entry for entry in members if entry != "null"] or ["string"]

    if len(concrete) == 1:
        node["type"] = concrete[0]
    elif dialect.allows_any_of:
        shared = {key: value for key, value in node.items() if key not in {"type"}}
        branches = [{**shared, "type": entry} for entry in concrete]
        return {"anyOf": branches}
    else:
        node["type"] = concrete[0]

    if nullable and dialect.allows_nullable_keyword:
        node["nullable"] = True
    return node


def _rewrite_additional_properties(node: dict[str, Any], dialect: SchemaDialect) -> None:
    """Apply the dialect's ``additionalProperties`` rule in place."""
    if dialect.additional_properties is AdditionalPropertiesRule.STRIP:
        node.pop("additionalProperties", None)
        return
    if dialect.additional_properties is AdditionalPropertiesRule.FORCE_FALSE:
        if node.get("type") == "object" or "properties" in node:
            node["additionalProperties"] = False
        else:
            node.pop("additionalProperties", None)
        return
    # PRESERVE: a schema-valued map is still a map; leave it as written.


def _rewrite_format(node: dict[str, Any], dialect: SchemaDialect) -> None:
    """Drop an unsupported ``format``, recording it where the model can read it.

    A dropped `format` is a lost hint, not a lost constraint — so it moves into
    the description, where it still steers the model even though the provider
    will not enforce it.
    """
    declared = node.get("format")
    if not isinstance(declared, str) or declared in dialect.supported_formats:
        return
    node.pop("format", None)
    existing = str(node.get("description", "")).strip()
    note = f"(expected format: {declared})"
    node["description"] = f"{existing} {note}".strip()


def _rewrite_required(node: dict[str, Any], dialect: SchemaDialect) -> None:
    """Reconcile ``required`` with ``properties`` in place.

    A name in ``required`` with no definition is rejected by strict providers
    and is meaningless everywhere else, so it goes. Under a dialect that demands
    every property be required, the optional ones are *listed* rather than
    deleted — deleting them would be losing the caller's parameter, which is a
    far larger failure than over-constraining one.
    """
    properties = node.get("properties")
    if not isinstance(properties, dict):
        if "required" in node and not isinstance(node.get("required"), list):
            node.pop("required", None)
        return

    declared = node.get("required")
    required = (
        [name for name in declared if name in properties] if isinstance(declared, list) else []
    )

    if dialect.requires_all_properties_required:
        optional = [name for name in properties if name not in required]
        for name in optional:
            definition = properties[name]
            if isinstance(definition, dict):
                existing = str(definition.get("description", "")).strip()
                note = "(optional; pass null when not applicable)"
                if note not in existing:
                    definition["description"] = f"{existing} {note}".strip()
        required = list(properties)

    if required:
        node["required"] = required
    else:
        node.pop("required", None)


def _widen_beyond_depth(node: Mapping[str, Any]) -> dict[str, Any]:
    """Return a shallow stand-in for a subtree at the dialect's depth cap.

    The property survives — it stays in ``properties`` and stays required — but
    its type widens to a JSON string, and the description says so. Losing the
    parameter entirely would leave the model unable to call the tool at all.

    This is the one rule that can drop a *nested* field, and it is why the
    validator and this function have to agree on where the cap sits: the
    validator rejects any node deeper than the cap, so widening has to happen at
    the last permitted level rather than one below it, where the stand-in would
    itself be too deep.
    """
    existing = str(node.get("description", "")).strip()
    note = "(JSON-encoded object; nested structure exceeds this provider's schema depth limit)"
    return {"type": "string", "description": f"{existing} {note}".strip()}


def _has_nested_schemas(node: Mapping[str, Any]) -> bool:
    """Return whether ``node`` holds schemas that would sit one level deeper."""
    for key in _SCHEMA_MAP_KEYS:
        value = node.get(key)
        if isinstance(value, Mapping) and value:
            return True
    for key in _SCHEMA_LIST_KEYS:
        value = node.get(key)
        if isinstance(value, list) and value:
            return True
    for key in _SCHEMA_VALUED_KEYS:
        if isinstance(node.get(key), Mapping):
            return True
    return isinstance(node.get("additionalProperties"), Mapping)


def _rewrite_node(node: Any, dialect: SchemaDialect, depth: int) -> Any:
    """Return ``node`` rewritten for ``dialect``.

    Post-order: children are normalised before the node that holds them, so a
    parent flattening a composition is looking at branches that are already in
    the dialect's terms.
    """
    if isinstance(node, list):
        return [_rewrite_node(child, dialect, depth) for child in node]
    if not isinstance(node, Mapping):
        return node

    if depth >= dialect.max_schema_depth and _has_nested_schemas(node):
        # At the last permitted level, so anything nested inside would be one
        # level too deep. Widening here rather than one level down is what keeps
        # the result inside the cap — a stand-in placed below it would be the
        # very node the provider rejects.
        return _widen_beyond_depth(node)

    rewritten: dict[str, Any] = {}
    for key, value in node.items():
        if key in _META_KEYWORDS:
            continue
        if key in _DEFINITION_KEYWORDS:
            # Refs were already inlined for dialects that reject them, so any
            # definition block still standing is one a supporting provider will
            # follow. Its contents are schemas and get the same rewrite.
            if dialect.allows_refs and isinstance(value, Mapping):
                rewritten[key] = {
                    name: _rewrite_node(child, dialect, depth) for name, child in value.items()
                }
            continue
        if not dialect.allows_validation_keywords and key in _VALIDATION_KEYWORDS:
            continue
        if key in _SCHEMA_MAP_KEYS and isinstance(value, Mapping):
            rewritten[key] = {
                name: _rewrite_node(child, dialect, depth + 1) for name, child in value.items()
            }
        elif key in _SCHEMA_LIST_KEYS and isinstance(value, list):
            rewritten[key] = [_rewrite_node(child, dialect, depth + 1) for child in value]
        elif (
            key == "additionalProperties"
            and isinstance(value, Mapping)
            or key in _SCHEMA_VALUED_KEYS
        ):
            rewritten[key] = _rewrite_node(value, dialect, depth + 1)
        else:
            rewritten[key] = value

    if "oneOf" in rewritten and not dialect.allows_one_of:
        branches = rewritten.pop("oneOf")
        rewritten["anyOf"] = _flatten_branches(branches) if isinstance(branches, list) else branches

    if "allOf" in rewritten and not dialect.allows_nested_composition:
        # An `allOf` of object schemas is a merge; performing it here means the
        # provider never sees a keyword it would reject.
        branches = rewritten.pop("allOf")
        if isinstance(branches, list):
            merged: dict[str, Any] = {}
            properties: dict[str, Any] = {}
            required: list[str] = []
            for branch in branches:
                if not isinstance(branch, Mapping):
                    continue
                for key, value in branch.items():
                    if key == "properties" and isinstance(value, Mapping):
                        properties.update(value)
                    elif key == "required" and isinstance(value, list):
                        required.extend(value)
                    else:
                        merged.setdefault(key, value)
            if properties:
                merged["properties"] = {**properties, **rewritten.get("properties", {})}
            if required:
                merged["required"] = sorted({*required, *rewritten.get("required", [])})
            rewritten = {**merged, **{k: v for k, v in rewritten.items() if k != "properties"}}
            if properties:
                rewritten["properties"] = merged["properties"]

    if "anyOf" in rewritten:
        branches = rewritten["anyOf"]
        if isinstance(branches, list):
            if not dialect.allows_nested_composition:
                branches = _flatten_branches(branches)
            if not dialect.allows_any_of:
                collapsed = _collapse_composition(branches)
                sibling = {key: value for key, value in rewritten.items() if key != "anyOf"}
                rewritten = {**collapsed, **sibling} if sibling else dict(collapsed)
            else:
                rewritten["anyOf"] = branches

    rewritten = _rewrite_union_type(rewritten, dialect)

    if isinstance(rewritten.get("type"), str) and rewritten["type"] == "object":
        rewritten.setdefault("properties", {})

    _rewrite_additional_properties(rewritten, dialect)
    _rewrite_format(rewritten, dialect)
    _rewrite_required(rewritten, dialect)

    return rewritten


def normalise_schema(schema: Mapping[str, Any], dialect: SchemaDialect) -> dict[str, Any]:
    """Return ``schema`` rewritten into ``dialect``.

    The input is never mutated: the same catalogue is normalised once per
    provider, and one provider's rules reaching another's request is the kind
    of bug that only shows up under a specific configuration.
    """
    root = dict(schema)
    if not dialect.allows_refs:
        inlined = _inline_refs(root, root, dialect.max_schema_depth)
        root = inlined if isinstance(inlined, dict) else {"type": "object"}

    rewritten = _rewrite_node(root, dialect, depth=1)
    if not isinstance(rewritten, dict):
        return {"type": "object", "properties": {}}
    rewritten.setdefault("type", "object")
    if rewritten["type"] == "object":
        rewritten.setdefault("properties", {})
    return rewritten


class SchemaNormaliser:
    """Applies one dialect to whole batches of tools.

    Batches, not schemas, because name collisions are only visible across a
    batch — and a collision is what silently sends the model's call to the wrong
    tool.
    """

    def __init__(self, dialect: SchemaDialect) -> None:
        self.dialect = dialect

    def normalise(self, tool: ToolSchema) -> ToolSchema:
        """Return one tool rewritten for this dialect."""
        return ToolSchema(
            name=normalise_tool_name(tool.name, self.dialect),
            description=_truncate_description(tool.description, self.dialect),
            parameters=normalise_schema(tool.parameters, self.dialect),
        )

    def normalise_all(self, tools: Sequence[ToolSchema]) -> tuple[ToolSchema, ...]:
        """Return every tool rewritten, with names kept distinct."""
        seen: set[str] = set()
        normalised: list[ToolSchema] = []
        for tool in tools:
            candidate = self.normalise(tool)
            name = candidate.name
            if name in seen:
                name = _disambiguate(name, tool.name, self.dialect)
                candidate = replace(candidate, name=name)
            seen.add(name)
            normalised.append(candidate)
        return tuple(normalised)


def _disambiguate(name: str, original: str, dialect: SchemaDialect) -> str:
    """Return a distinct name for a tool whose normalised name already exists."""
    suffix = f"_{_stable_suffix(original)}"
    keep = dialect.max_tool_name_length - len(suffix)
    return f"{name[:keep]}{suffix}"


# --- Validation ---------------------------------------------------------------


@dataclass(slots=True)
class _Walker:
    """Collects the reasons one schema would be rejected."""

    dialect: SchemaDialect
    violations: list[str] = field(default_factory=list)

    def visit(self, node: Any, path: str, depth: int) -> None:
        if isinstance(node, list):
            for index, child in enumerate(node):
                self.visit(child, f"{path}[{index}]", depth)
            return
        if not isinstance(node, Mapping):
            return

        if depth > self.dialect.max_schema_depth:
            self.violations.append(f"{path}: nested deeper than {self.dialect.max_schema_depth}")
            return

        self._check_node(node, path)

        for key, value in node.items():
            if key in _DEFINITION_KEYWORDS and isinstance(value, Mapping):
                # A definition block is followed by the provider, so what it
                # holds has to satisfy the dialect just as the inline tree does.
                for name, child in value.items():
                    self.visit(child, f"{path}.{key}.{name}", depth)
            elif key in _SCHEMA_MAP_KEYS and isinstance(value, Mapping):
                for name, child in value.items():
                    self.visit(child, f"{path}.{key}.{name}", depth + 1)
            elif key in _SCHEMA_LIST_KEYS and isinstance(value, list):
                self.visit(value, f"{path}.{key}", depth + 1)
            elif key == "additionalProperties" and isinstance(value, Mapping):
                self.visit(value, f"{path}.additionalProperties", depth + 1)
            elif key in _SCHEMA_VALUED_KEYS:
                self.visit(value, f"{path}.{key}", depth + 1)

    def _check_node(self, node: Mapping[str, Any], path: str) -> None:
        dialect = self.dialect

        for keyword in _META_KEYWORDS:
            if keyword in node:
                self.violations.append(f"{path}: unsupported keyword {keyword!r}")
        if not dialect.allows_refs:
            if "$ref" in node:
                self.violations.append(f"{path}: $ref is not supported")
            for keyword in _DEFINITION_KEYWORDS:
                if keyword in node:
                    self.violations.append(f"{path}: unsupported keyword {keyword!r}")
        if isinstance(node.get("type"), list) and not dialect.allows_union_types:
            self.violations.append(f"{path}: union type {node['type']!r} is not supported")
        if "oneOf" in node and not dialect.allows_one_of:
            self.violations.append(f"{path}: oneOf is not supported")
        if "allOf" in node and not dialect.allows_nested_composition:
            self.violations.append(f"{path}: allOf is not supported")
        if "anyOf" in node:
            if not dialect.allows_any_of:
                self.violations.append(f"{path}: anyOf is not supported")
            elif not dialect.allows_nested_composition:
                branches = node["anyOf"]
                if isinstance(branches, list):
                    for index, branch in enumerate(branches):
                        if isinstance(branch, Mapping) and ("anyOf" in branch or "oneOf" in branch):
                            self.violations.append(f"{path}.anyOf[{index}]: nested composition")

        if not dialect.allows_validation_keywords:
            for keyword in sorted(_VALIDATION_KEYWORDS & set(node)):
                self.violations.append(f"{path}: unsupported constraint {keyword!r}")

        declared_format = node.get("format")
        if isinstance(declared_format, str) and declared_format not in dialect.supported_formats:
            self.violations.append(f"{path}: unsupported format {declared_format!r}")

        if dialect.additional_properties is AdditionalPropertiesRule.STRIP:
            if "additionalProperties" in node:
                self.violations.append(f"{path}: additionalProperties is not supported")
        elif dialect.additional_properties is AdditionalPropertiesRule.FORCE_FALSE:
            is_object = node.get("type") == "object" or "properties" in node
            if is_object and node.get("additionalProperties") is not False:
                self.violations.append(f"{path}: additionalProperties must be false")

        if "nullable" in node and not dialect.allows_nullable_keyword:
            self.violations.append(f"{path}: nullable is not supported")

        properties = node.get("properties")
        required = node.get("required")
        if isinstance(properties, Mapping):
            declared = list(required) if isinstance(required, list) else []
            dangling = [name for name in declared if name not in properties]
            if dangling:
                self.violations.append(f"{path}: required without a definition: {dangling}")
            if dialect.requires_all_properties_required:
                missing = [name for name in properties if name not in declared]
                if missing:
                    self.violations.append(f"{path}: every property must be required: {missing}")


def schema_violations(schema: Mapping[str, Any], dialect: SchemaDialect) -> tuple[str, ...]:
    """Return every reason ``dialect``'s provider would reject ``schema``."""
    walker = _Walker(dialect)
    walker.visit(schema, "$", depth=1)
    return tuple(walker.violations)


def dialect_violations(tool: ToolSchema, dialect: SchemaDialect) -> tuple[str, ...]:
    """Return every reason ``dialect``'s provider would reject ``tool``.

    This stands in for a live call in the contract suite. It encodes what the
    provider rejects, so it runs on every pull request, against every provider,
    for nothing.
    """
    violations: list[str] = []

    if len(tool.name) > dialect.max_tool_name_length:
        violations.append(
            f"name is {len(tool.name)} characters, over the {dialect.max_tool_name_length} limit"
        )
    if re.search(dialect.name_allowed_pattern, tool.name):
        violations.append(f"name {tool.name!r} contains characters the provider rejects")
    if dialect.name_must_start_with_letter and not re.match(r"[A-Za-z_]", tool.name or "_"):
        violations.append(f"name {tool.name!r} must start with a letter or underscore")
    if len(tool.description) > dialect.max_tool_description_length:
        violations.append(
            f"description is {len(tool.description)} characters, over the "
            f"{dialect.max_tool_description_length} limit"
        )

    violations.extend(schema_violations(tool.parameters, dialect))
    return tuple(violations)


__all__ = [
    "AdditionalPropertiesRule",
    "SchemaDialect",
    "SchemaNormaliser",
    "dialect_for",
    "dialect_violations",
    "normalise_schema",
    "normalise_tool_name",
    "register_dialect",
    "schema_violations",
]
