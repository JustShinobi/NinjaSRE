"""The API document every fixture is measured against, and the validator that does it.

Two documents, because the console consumes two kinds of endpoint.
``openapi.json`` is the gateway's own document, generated from the application
and committed so a fixture can be checked without standing a deployment up; a
drift test keeps the committed copy equal to what the application generates, so
a route change that invalidates a fixture fails the build rather than being
discovered by a screen. ``projected.json`` declares the response shapes the
endpoints that have not been built yet will return — the same dialect, the same
validator, and the file that gets deleted a piece at a time as each of them
lands.

The validator is a subset of JSON Schema rather than a library: the subset
FastAPI actually emits. That is a deliberate trade. A dependency here would sit
in the tree of anyone who installs the repository's tooling, and the subset is
small — objects, arrays, the scalar types, ``enum``, ``anyOf``/``oneOf``/
``allOf``, and ``$ref`` into ``components/schemas``. Anything outside it is
reported as unvalidatable rather than silently passing, because a validator that
quietly accepts what it does not understand is worse than no validator.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from config.constants.fixtures import (
    FIXTURE_CONTRACT_DIR_NAME,
    FIXTURE_OPENAPI_FILENAME,
)
from tools.mockplane.endpoints import ConsoleEndpoint, EndpointSource
from tools.mockplane.paths import fixture_root

#: The declared shapes of the endpoints nothing serves yet.
PROJECTED_SCHEMA_FILENAME: Final = "projected.json"

_REF_PREFIX: Final = "#/components/schemas/"

_JSON_TYPES: Final[Mapping[str, tuple[type, ...]]] = {
    "object": (dict,),
    "array": (list,),
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
}


@dataclass(frozen=True, slots=True)
class SchemaViolation:
    """One place a payload disagrees with the schema, named so it can be fixed."""

    #: A JSON pointer into the payload: ``/runs/0/started_at``.
    pointer: str
    message: str

    def __str__(self) -> str:
        return f"{self.pointer or '/'}: {self.message}"


class ContractError(RuntimeError):
    """The document does not describe the endpoint a fixture claims to answer."""


def contract_dir(root: Path | None = None) -> Path:
    """Return the directory holding the API documents."""
    return fixture_root(root) / FIXTURE_CONTRACT_DIR_NAME


def openapi_document(root: Path | None = None) -> dict[str, Any]:
    """Return the committed copy of the gateway's OpenAPI document."""
    return _read(contract_dir(root) / FIXTURE_OPENAPI_FILENAME)


def projected_document(root: Path | None = None) -> dict[str, Any]:
    """Return the declared shapes of the endpoints nothing serves yet."""
    return _read(contract_dir(root) / PROJECTED_SCHEMA_FILENAME)


def generated_openapi_document() -> dict[str, Any]:
    """Return the document the application generates right now.

    Built from the real ``create_app`` with an unpopulated state: the document
    is a function of the declared routes and their models, and nothing in it
    reads a database, a token service or a runner.
    """
    from gateway.http.app import create_app
    from gateway.http.state import GatewayState

    state: GatewayState = object.__new__(GatewayState)
    document: dict[str, Any] = create_app(state).openapi()
    return document


def document_for(endpoint: ConsoleEndpoint, root: Path | None = None) -> dict[str, Any]:
    """Return the document that describes ``endpoint``."""
    if endpoint.source is EndpointSource.GATEWAY:
        return openapi_document(root)
    return projected_document(root)


def response_schema(
    endpoint: ConsoleEndpoint, status: int = 200, root: Path | None = None
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    """Return the JSON schema for ``endpoint``'s ``status`` response, and its document.

    Raises:
        ContractError: the document does not describe that endpoint, that
            method, or a JSON body for that status.
    """
    document = document_for(endpoint, root)
    operations = document.get("paths", {}).get(endpoint.path)
    if not isinstance(operations, dict):
        raise ContractError(f"{endpoint.path} is not in the API document")
    operation = operations.get(endpoint.method.lower())
    if not isinstance(operation, dict):
        raise ContractError(f"{endpoint.method} {endpoint.path} is not in the API document")
    responses = operation.get("responses", {})
    answer = responses.get(str(status))
    if not isinstance(answer, dict):
        raise ContractError(
            f"{endpoint.method} {endpoint.path} declares no {status} response; "
            f"it declares {', '.join(sorted(responses)) or 'nothing'}"
        )
    content = answer.get("content", {}).get("application/json", {})
    schema = content.get("schema")
    if not isinstance(schema, dict):
        raise ContractError(f"{endpoint.method} {endpoint.path} declares no JSON body for {status}")
    return schema, document


def validate(
    instance: Any, schema: Mapping[str, Any], document: Mapping[str, Any]
) -> tuple[SchemaViolation, ...]:
    """Return every way ``instance`` disagrees with ``schema``.

    Empty means it validates. Each violation names a JSON pointer into the
    payload, so a failure says which field of which record is wrong rather than
    that something somewhere is.
    """
    return tuple(_walk(instance, schema, document, ""))


def _read(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ContractError(f"{path} does not exist; regenerate the contract documents")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ContractError(f"{path} does not hold a JSON object")
    return loaded


def _resolve(schema: Mapping[str, Any], document: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return ``schema`` with a top-level ``$ref`` followed, as many times as needed."""
    seen: set[str] = set()
    current = schema
    while isinstance(current, dict) and "$ref" in current:
        reference = str(current["$ref"])
        if reference in seen:
            raise ContractError(f"{reference} refers to itself")
        seen.add(reference)
        if not reference.startswith(_REF_PREFIX):
            raise ContractError(f"{reference} is not a components/schemas reference")
        name = reference[len(_REF_PREFIX) :]
        found = document.get("components", {}).get("schemas", {}).get(name)
        if not isinstance(found, dict):
            raise ContractError(f"{reference} is not in the document")
        current = found
    return current


def _type_names(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _walk(
    instance: Any, raw: Mapping[str, Any], document: Mapping[str, Any], pointer: str
) -> Iterator[SchemaViolation]:
    schema = _resolve(raw, document)

    for keyword in ("anyOf", "oneOf"):
        branches = schema.get(keyword)
        if isinstance(branches, list):
            if any(not tuple(_walk(instance, branch, document, pointer)) for branch in branches):
                return
            yield SchemaViolation(
                pointer,
                f"{_type_names(instance)} matches none of the {len(branches)} declared shapes",
            )
            return

    branches = schema.get("allOf")
    if isinstance(branches, list):
        for branch in branches:
            yield from _walk(instance, branch, document, pointer)
        return

    if "const" in schema and instance != schema["const"]:
        yield SchemaViolation(pointer, f"must be {schema['const']!r}, not {instance!r}")
        return

    allowed = schema.get("enum")
    if isinstance(allowed, list) and instance not in allowed:
        yield SchemaViolation(pointer, f"{instance!r} is not one of {allowed!r}")
        return

    declared = schema.get("type")
    if declared is None:
        # A schema with no type and no combinator constrains nothing — FastAPI
        # emits one for a bare ``dict[str, Any]``. Accepting it is correct.
        return

    names = [declared] if isinstance(declared, str) else list(declared)
    if not any(_matches(instance, name) for name in names):
        yield SchemaViolation(
            pointer, f"expected {' or '.join(names)}, found {_type_names(instance)}"
        )
        return

    if isinstance(instance, dict) and "object" in names:
        yield from _walk_object(instance, schema, document, pointer)
    elif isinstance(instance, list) and "array" in names:
        items = schema.get("items")
        if isinstance(items, dict):
            for index, element in enumerate(instance):
                yield from _walk(element, items, document, f"{pointer}/{index}")


def _matches(instance: Any, name: str) -> bool:
    if name == "null":
        return instance is None
    if name == "boolean":
        return isinstance(instance, bool)
    expected = _JSON_TYPES.get(name)
    if expected is None:
        raise ContractError(f"the validator does not understand the type {name!r}")
    if name in {"integer", "number"} and isinstance(instance, bool):
        return False
    return isinstance(instance, expected)


def _walk_object(
    instance: Mapping[str, Any],
    schema: Mapping[str, Any],
    document: Mapping[str, Any],
    pointer: str,
) -> Iterator[SchemaViolation]:
    properties = schema.get("properties")
    properties = properties if isinstance(properties, dict) else {}

    required = schema.get("required")
    if isinstance(required, Sequence) and not isinstance(required, str):
        for name in required:
            if name not in instance:
                yield SchemaViolation(f"{pointer}/{name}", "is required and is missing")

    for name, value in instance.items():
        declared = properties.get(name)
        if isinstance(declared, dict):
            yield from _walk(value, declared, document, f"{pointer}/{name}")
            continue
        extra = schema.get("additionalProperties")
        if extra is False:
            yield SchemaViolation(f"{pointer}/{name}", "is not a declared field")
        elif isinstance(extra, dict):
            yield from _walk(value, extra, document, f"{pointer}/{name}")


__all__ = [
    "PROJECTED_SCHEMA_FILENAME",
    "ContractError",
    "SchemaViolation",
    "contract_dir",
    "document_for",
    "generated_openapi_document",
    "openapi_document",
    "projected_document",
    "response_schema",
    "validate",
]
