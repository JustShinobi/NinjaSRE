"""Normalisation makes the whole catalogue acceptable to every provider at once.

The unit of failure here is the *turn*, not the schema. Every selected tool goes
out in one request, so one rejected schema fails the request and the
investigation loses the step. That is why this suite normalises the entire
catalogue together and asserts the batch is clean, rather than checking schemas
one at a time and hoping the set composes.

Acceptance is decided by each provider's dialect validator rather than by a live
call: the validator encodes what the provider rejects, and running it costs
nothing, so it runs on every pull request against every provider.
"""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest
from capability_schemas import CAPABILITY_SCHEMAS

from config.constants.llm import SUPPORTED_PROVIDERS
from core.llm.schema import (
    SchemaNormaliser,
    dialect_for,
    dialect_violations,
)
from core.llm.types import ToolSchema

pytestmark = pytest.mark.contract


def _required_paths(schema: Any, prefix: str = "") -> set[str]:
    """Return every ``required`` property, addressed by path.

    Normalisation may rewrite a type, relocate a keyword, or drop a format. It
    may never make a required field unreachable.
    """
    found: set[str] = set()
    if isinstance(schema, dict):
        for name in schema.get("required", []) or []:
            found.add(f"{prefix}/{name}")
        for key, value in schema.items():
            if key in {"properties", "$defs", "definitions"} and isinstance(value, dict):
                for name, child in value.items():
                    found |= _required_paths(child, f"{prefix}/{key}/{name}")
            elif isinstance(value, dict):
                found |= _required_paths(value, f"{prefix}/{key}")
            elif isinstance(value, list):
                for index, child in enumerate(value):
                    found |= _required_paths(child, f"{prefix}/{key}/{index}")
    return found


@pytest.fixture(name="catalogue")
def _catalogue() -> tuple[ToolSchema, ...]:
    return CAPABILITY_SCHEMAS


@pytest.mark.parametrize("provider_id", SUPPORTED_PROVIDERS)
def test_the_whole_catalogue_normalises_to_something_the_provider_accepts(
    provider_id: str, catalogue: tuple[ToolSchema, ...]
) -> None:
    dialect = dialect_for(provider_id)
    normaliser = SchemaNormaliser(dialect)

    normalised = normaliser.normalise_all(catalogue)

    violations: list[str] = []
    for tool in normalised:
        violations.extend(
            f"{tool.name}: {violation}" for violation in dialect_violations(tool, dialect)
        )

    assert not violations, "\n".join(violations)


@pytest.mark.parametrize("provider_id", SUPPORTED_PROVIDERS)
def test_normalisation_is_idempotent(provider_id: str, catalogue: tuple[ToolSchema, ...]) -> None:
    normaliser = SchemaNormaliser(dialect_for(provider_id))

    once = normaliser.normalise_all(catalogue)
    twice = normaliser.normalise_all(once)

    assert [tool.parameters for tool in twice] == [tool.parameters for tool in once]
    assert [tool.name for tool in twice] == [tool.name for tool in once]


def _declared_property_names(schema: Any) -> set[str]:
    """Return every property name declared anywhere in ``schema``."""
    found: set[str] = set()
    if isinstance(schema, dict):
        properties = schema.get("properties")
        if isinstance(properties, dict):
            found |= set(properties)
        for value in schema.values():
            found |= _declared_property_names(value)
    elif isinstance(schema, list):
        for child in schema:
            found |= _declared_property_names(child)
    return found


@pytest.mark.parametrize("provider_id", SUPPORTED_PROVIDERS)
def test_no_required_parameter_is_deleted(
    provider_id: str, catalogue: tuple[ToolSchema, ...]
) -> None:
    """A parameter the caller declared required stays reachable.

    Reachable, not necessarily still required. Collapsing a discriminated union
    for a provider that has no `oneOf` genuinely cannot keep both alternatives
    mandatory — demanding `pod` *and* `node` on a schema meaning one or the
    other makes the tool uncallable. Relaxing a field is a documented trade;
    deleting the caller's parameter is not, because the model then cannot use
    the tool at all and nothing in the trace would say why.
    """
    normaliser = SchemaNormaliser(dialect_for(provider_id))

    for original in catalogue:
        normalised = normaliser.normalise(original)
        before = {path.rsplit("/", 1)[-1] for path in _required_paths(dict(original.parameters))}
        after = _declared_property_names(dict(normalised.parameters))

        lost = before - after
        assert not lost, f"{provider_id}/{original.name} deleted parameter(s): {sorted(lost)}"


@pytest.mark.parametrize("provider_id", SUPPORTED_PROVIDERS)
def test_top_level_required_parameters_stay_required(
    provider_id: str, catalogue: tuple[ToolSchema, ...]
) -> None:
    """No dialect may relax a tool's own mandatory arguments."""
    normaliser = SchemaNormaliser(dialect_for(provider_id))

    for original in catalogue:
        expected = set(dict(original.parameters).get("required", []) or [])
        actual = set(dict(normaliser.normalise(original).parameters).get("required", []) or [])

        assert expected <= actual, f"{provider_id}/{original.name}: {sorted(expected - actual)}"


@pytest.mark.parametrize("provider_id", SUPPORTED_PROVIDERS)
def test_a_required_property_still_has_a_definition(
    provider_id: str, catalogue: tuple[ToolSchema, ...]
) -> None:
    """A dangling ``required`` entry is rejected by strict providers, and is a lie anywhere."""
    normaliser = SchemaNormaliser(dialect_for(provider_id))

    for tool in normaliser.normalise_all(catalogue):
        _assert_required_are_defined(dict(tool.parameters), f"{provider_id}/{tool.name}")


def _assert_required_are_defined(node: Any, where: str) -> None:
    if isinstance(node, dict):
        required = node.get("required")
        properties = node.get("properties")
        if isinstance(required, list) and isinstance(properties, dict):
            dangling = [name for name in required if name not in properties]
            assert not dangling, f"{where}: required without a definition: {dangling}"
        for value in node.values():
            _assert_required_are_defined(value, where)
    elif isinstance(node, list):
        for child in node:
            _assert_required_are_defined(child, where)


@pytest.mark.parametrize("provider_id", SUPPORTED_PROVIDERS)
def test_normalisation_does_not_mutate_the_input(
    provider_id: str, catalogue: tuple[ToolSchema, ...]
) -> None:
    """The catalogue is shared across providers; one provider's rules must not reach another's."""
    before = copy.deepcopy([dict(tool.parameters) for tool in catalogue])

    SchemaNormaliser(dialect_for(provider_id)).normalise_all(catalogue)

    assert [dict(tool.parameters) for tool in catalogue] == before


@pytest.mark.parametrize("provider_id", SUPPORTED_PROVIDERS)
def test_the_result_is_json_serialisable(
    provider_id: str, catalogue: tuple[ToolSchema, ...]
) -> None:
    for tool in SchemaNormaliser(dialect_for(provider_id)).normalise_all(catalogue):
        json.dumps({"name": tool.name, "parameters": tool.parameters})


@pytest.mark.parametrize("provider_id", SUPPORTED_PROVIDERS)
def test_tool_names_stay_unique_after_truncation(
    provider_id: str, catalogue: tuple[ToolSchema, ...]
) -> None:
    """Truncating to a name cap must not collapse two tools onto one name."""
    long_prefix = "observability_platform_query_metrics_across_every_datasource"
    crowded = tuple(
        ToolSchema(name=f"{long_prefix}_{suffix}", description="x", parameters={"type": "object"})
        for suffix in ("prometheus", "cloudwatch", "datadog", "stackdriver")
    )

    names = [
        tool.name for tool in SchemaNormaliser(dialect_for(provider_id)).normalise_all(crowded)
    ]

    assert len(set(names)) == len(names), names


def test_an_unregistered_provider_falls_back_to_the_strictest_dialect() -> None:
    """A tenth provider is safe before anyone writes its dialect."""
    dialect = dialect_for("a-provider-nobody-has-added-yet")

    normalised = SchemaNormaliser(dialect).normalise_all(CAPABILITY_SCHEMAS)

    for tool in normalised:
        assert not dialect_violations(tool, dialect)
