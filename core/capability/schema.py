"""Where a tool's JSON Schema comes from, and what it has to be before it ships.

Three sources, in decreasing order of how much the author had to write:

1. A schema written by hand, for an input a signature cannot express.
2. A model class — anything exposing ``model_json_schema()``, or a dataclass —
   for a tool with a structured request object.
3. The function signature itself, which is the common case and costs nothing.

The derivation is deliberately narrow. It handles the types that appear in tool
signatures and refuses everything else loudly, because a schema silently
widened to ``{"type": "object"}`` produces a tool the model calls confidently
and wrongly. A refused derivation is a build failure with the parameter named;
a wrong one is an incident.

No provider dialect is applied here. Normalisation happens once per provider,
later, and doing any of it now would bake one provider's rules into a catalogue
every provider reads.
"""

from __future__ import annotations

import dataclasses
import enum
import inspect
import types
import typing
from collections.abc import Mapping, Sequence
from typing import Any, Literal, Union, get_args, get_origin

#: JSON Schema's type names. A derived schema uses nothing outside this set.
_JSON_TYPES = frozenset({"object", "array", "string", "number", "integer", "boolean", "null"})

#: Python scalars and the JSON type each becomes.
_SCALARS: dict[Any, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    type(None): "null",
}

#: Parameter kinds a derivation cannot express. ``**kwargs`` is not one of them:
#: a tool declaring its schema by hand collects arguments that way on purpose.
_UNDERIVABLE_KINDS = frozenset(
    {inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.POSITIONAL_ONLY}
)


class SchemaError(Exception):
    """A tool's schema cannot be derived or is not usable as declared."""


def _is_optional(annotation: Any) -> tuple[bool, Any]:
    """Return whether ``annotation`` admits ``None``, and what remains without it."""
    origin = get_origin(annotation)
    if origin is not Union and origin is not types.UnionType:
        return False, annotation

    members = [member for member in get_args(annotation) if member is not type(None)]
    if len(members) == len(get_args(annotation)):
        return False, annotation
    if len(members) == 1:
        return True, members[0]

    # ``str | int | None`` minus the ``None``. Rebuilt rather than returned as
    # a list because the caller has one job, which is to ask for the schema of
    # what is left, and what is left is still a union.
    rebuilt = members[0]
    for member in members[1:]:
        rebuilt = rebuilt | member
    return True, rebuilt


def _schema_for(annotation: Any, *, path: str) -> dict[str, Any]:
    """Return the JSON Schema for one annotation, or explain why there is none."""
    nullable, annotation = _is_optional(annotation)
    schema = _schema_for_concrete(annotation, path=path)
    if nullable:
        # A nullable field keeps its type and gains ``null``. The provider
        # normaliser knows how to express that for a dialect that rejects a
        # union; encoding one dialect's answer here would be that dialect
        # leaking into every other provider's request.
        declared = schema.get("type")
        if isinstance(declared, str):
            schema["type"] = [declared, "null"]
    return schema


def _schema_for_concrete(annotation: Any, *, path: str) -> dict[str, Any]:
    """Return the JSON Schema for an annotation already stripped of ``None``."""
    if annotation is inspect.Parameter.empty or annotation is Any:
        raise SchemaError(
            f"{path}: every parameter needs an annotation a schema can be derived from"
        )

    if annotation in _SCALARS:
        return {"type": _SCALARS[annotation]}

    origin = get_origin(annotation)

    if origin is Literal:
        return _literal_schema(get_args(annotation), path=path)

    if isinstance(annotation, type) and issubclass(annotation, enum.Enum):
        return _literal_schema(tuple(member.value for member in annotation), path=path)

    if origin in (list, tuple, set, frozenset, Sequence):
        arguments = get_args(annotation)
        if not arguments:
            raise SchemaError(f"{path}: a sequence parameter must say what it holds")
        return {"type": "array", "items": _schema_for(arguments[0], path=f"{path}[]")}

    if origin in (dict, Mapping):
        arguments = get_args(annotation)
        if len(arguments) == 2 and arguments[0] is not str:
            raise SchemaError(f"{path}: a mapping parameter must be keyed by string")
        value_schema = _schema_for(arguments[1], path=f"{path}{{}}") if arguments else None
        schema: dict[str, Any] = {"type": "object"}
        if value_schema is not None:
            schema["additionalProperties"] = value_schema
        return schema

    if dataclasses.is_dataclass(annotation) and isinstance(annotation, type):
        return _dataclass_schema(annotation, path=path)

    if origin is Union or origin is types.UnionType:
        raise SchemaError(
            f"{path}: a union of several concrete types has no single schema — "
            "declare input_schema by hand, or take one type"
        )

    raise SchemaError(f"{path}: {annotation!r} has no JSON Schema representation")


def _literal_schema(values: tuple[Any, ...], *, path: str) -> dict[str, Any]:
    """Return an enum schema, typed by what the members actually are."""
    kinds = {type(value) for value in values}
    if len(kinds) != 1 or kinds.pop() not in _SCALARS:
        raise SchemaError(f"{path}: enum members must all be one JSON scalar type")
    return {"type": _SCALARS[type(values[0])], "enum": list(values)}


def _dataclass_schema(declared: type, *, path: str) -> dict[str, Any]:
    """Return the object schema for a dataclass used as a parameter type."""
    hints = typing.get_type_hints(declared)
    properties: dict[str, Any] = {}
    required: list[str] = []

    for entry in dataclasses.fields(declared):
        properties[entry.name] = _schema_for(hints[entry.name], path=f"{path}.{entry.name}")
        if entry.default is dataclasses.MISSING and entry.default_factory is dataclasses.MISSING:
            required.append(entry.name)

    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def _model_schema(model: Any) -> dict[str, Any]:
    """Return a model class's own schema, whatever library produced it.

    Duck-typed on ``model_json_schema`` rather than importing a validation
    library: no vendor model library is a runtime dependency here, and a tool
    that wants one can bring it as an extra without every deployment paying for
    it.
    """
    generator = getattr(model, "model_json_schema", None)
    if callable(generator):
        produced = generator()
        if isinstance(produced, Mapping):
            return dict(produced)
        raise SchemaError(f"{model!r}: model_json_schema() did not return a mapping")

    if dataclasses.is_dataclass(model) and isinstance(model, type):
        return _dataclass_schema(model, path=model.__name__)

    raise SchemaError(
        f"{model!r}: an input_model must be a dataclass or expose model_json_schema()"
    )


def validate_schema(schema: Mapping[str, Any], *, label: str) -> dict[str, Any]:
    """Return ``schema`` as a plain dict, or explain why it is not usable.

    Checked here rather than at the provider, because a schema the provider
    rejects fails the whole turn — every tool in it, not just this one.
    """
    if not isinstance(schema, Mapping):
        raise SchemaError(f"{label}: a schema must be a mapping")

    declared = schema.get("type", "object")
    if declared not in _JSON_TYPES:
        raise SchemaError(f"{label}: {declared!r} is not a JSON Schema type")

    resolved = dict(schema)
    resolved.setdefault("type", "object")

    if resolved["type"] == "object":
        properties = resolved.setdefault("properties", {})
        if not isinstance(properties, Mapping):
            raise SchemaError(f"{label}: properties must be a mapping")
        required = resolved.get("required", [])
        if not isinstance(required, list):
            raise SchemaError(f"{label}: required must be a list")
        dangling = [name for name in required if name not in properties]
        if dangling:
            raise SchemaError(f"{label}: required names no property: {sorted(dangling)}")

    return resolved


def derive_input_schema(
    *,
    label: str,
    function: Any = None,
    input_schema: Mapping[str, Any] | None = None,
    input_model: Any = None,
    skip_first: bool = False,
) -> dict[str, Any]:
    """Return the input schema for a tool, from whichever source it declared.

    ``skip_first`` drops the leading parameter, which is what makes a bound
    ``run(self, ...)`` derive the same schema as the equivalent free function.
    """
    if input_schema is not None and input_model is not None:
        raise SchemaError(f"{label}: declare input_schema or input_model, not both")

    if input_schema is not None:
        return validate_schema(input_schema, label=f"{label} input")

    if input_model is not None:
        return validate_schema(_model_schema(input_model), label=f"{label} input")

    if function is None:
        raise SchemaError(f"{label}: no signature, input_schema, or input_model to derive from")

    return validate_schema(
        _signature_schema(function, label=label, skip_first=skip_first), label=f"{label} input"
    )


def _signature_schema(function: Any, *, label: str, skip_first: bool) -> dict[str, Any]:
    """Return the object schema a callable's signature describes."""
    signature = inspect.signature(function)
    hints = typing.get_type_hints(function)

    parameters = list(signature.parameters.values())
    if skip_first and parameters:
        parameters = parameters[1:]

    properties: dict[str, Any] = {}
    required: list[str] = []

    for parameter in parameters:
        if parameter.kind is inspect.Parameter.VAR_KEYWORD:
            # ``**kwargs`` says the author is collecting whatever arrives, which
            # only makes sense alongside a hand-written schema. Deriving an open
            # object here would produce a tool with no declared parameters at
            # all, which the model cannot call.
            raise SchemaError(
                f"{label}: {parameter.name} is **kwargs — declare input_schema by hand"
            )
        if parameter.kind in _UNDERIVABLE_KINDS:
            raise SchemaError(
                f"{label}: {parameter.name} is {parameter.kind.description}, which a "
                "model cannot supply by name"
            )

        annotation = hints.get(parameter.name, parameter.annotation)
        properties[parameter.name] = _schema_for(annotation, path=f"{label}.{parameter.name}")
        if parameter.default is inspect.Parameter.empty:
            required.append(parameter.name)

    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def derive_output_schema(
    *,
    label: str,
    function: Any = None,
    output_schema: Mapping[str, Any] | None = None,
    output_model: Any = None,
) -> dict[str, Any]:
    """Return the output schema for a tool.

    A return annotation that has no schema is not an error. The output schema
    documents the result for the console and the evaluation suite; it is never
    sent to a provider, so an unrepresentable return type costs a description
    rather than a tool.
    """
    if output_schema is not None:
        return validate_schema(output_schema, label=f"{label} output")

    if output_model is not None:
        return validate_schema(_model_schema(output_model), label=f"{label} output")

    if function is None:
        return {"type": "object", "properties": {}}

    hints = typing.get_type_hints(function)
    annotation = hints.get("return")
    if annotation is None:
        return {"type": "object", "properties": {}}

    try:
        return validate_schema(_schema_for(annotation, path=f"{label}()"), label=f"{label} output")
    except SchemaError:
        return {"type": "object", "properties": {}}


__all__ = [
    "SchemaError",
    "derive_input_schema",
    "derive_output_schema",
    "validate_schema",
]
