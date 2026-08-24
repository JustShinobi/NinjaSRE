"""Every credential field carries the orientation its own kind owes.

A secret field without a minimum permission is a value an operator pastes in
blind; an address or public field carrying one is a permission that grants
nothing pretending to be real; a field with no guide, of any kind, sends an
operator hunting for a value this deployment could have named a source for.
``integrations._catalogue.guidance`` is the rule; this suite is what proves the
whole embedded catalogue actually holds it, one vendor at a time so a failure
names the vendor and the field rather than the whole catalogue at once.
"""

from __future__ import annotations

import pytest

from integrations._catalogue.guidance import (
    GUIDE_MISSING_RULE,
    GUIDE_NOT_ABSOLUTE_RULE,
    MIN_SCOPE_FORBIDDEN_RULE,
    MIN_SCOPE_MISSING_RULE,
    guidance_problems,
)
from tests.contract.integrations.conftest import CATALOGUE, ENTRIES, PROFILES, integration_ids

pytestmark = pytest.mark.contract

IDS = integration_ids()

#: The count this spec's own reading of the schemas affirms, checked once
#: below rather than only per-field: 15 embedded vendors, 40 credential
#: fields, 21 of them secret. Embedding a sixteenth vendor is meant to move
#: these numbers, deliberately, in the same commit that adds it.
EXPECTED_VENDOR_COUNT = 15
EXPECTED_FIELD_COUNT = 40
EXPECTED_SECRET_FIELD_COUNT = 21


@pytest.mark.parametrize("name", IDS)
def test_every_secret_field_declares_a_minimum_permission(name: str) -> None:
    schema = ENTRIES[name].descriptor.schema
    found = [
        problem for problem in guidance_problems(schema) if problem.rule == MIN_SCOPE_MISSING_RULE
    ]
    assert found == [], "\n".join(str(problem) for problem in found)


@pytest.mark.parametrize("name", IDS)
def test_no_address_or_public_field_declares_a_minimum_permission(name: str) -> None:
    """This one is expected to hold today, before any field content is filled in.

    Nineteen of the forty fields are address or public-configuration fields,
    and none of them has ever declared a minimum permission — there was
    nothing here to make it wrong yet. It stays in this suite as the rail that
    catches a future content change inventing a scope for a hostname or a
    namespace, which is exactly the reading of the backlog this feature's own
    specification rejected.
    """
    schema = ENTRIES[name].descriptor.schema
    found = [
        problem for problem in guidance_problems(schema) if problem.rule == MIN_SCOPE_FORBIDDEN_RULE
    ]
    assert found == [], "\n".join(str(problem) for problem in found)


@pytest.mark.parametrize("name", IDS)
def test_every_field_declares_a_guide(name: str) -> None:
    schema = ENTRIES[name].descriptor.schema
    found = [
        problem
        for problem in guidance_problems(schema)
        if problem.rule in {GUIDE_MISSING_RULE, GUIDE_NOT_ABSOLUTE_RULE}
    ]
    assert found == [], "\n".join(str(problem) for problem in found)


@pytest.mark.parametrize("name", IDS)
def test_every_vendor_declares_where_to_get_its_credential(name: str) -> None:
    profile = PROFILES[name]
    assert profile.where_to_get_it.strip() != "", (
        f"{name} declares no where_to_get_it phrase, so the two screens that ask for its "
        f"credential have nothing to show"
    )


def test_the_catalogue_wide_arithmetic_this_feature_affirms() -> None:
    """The forty-field, twenty-one-secret count the specification derived from the schemas.

    A per-vendor failure above already names which field is short; this is the
    total the whole feature is measured against, and a change here without a
    matching change to a vendor's fields is the signal that the catalogue grew
    without this suite growing with it.
    """
    assert len(CATALOGUE) == EXPECTED_VENDOR_COUNT

    total_fields = 0
    secret_fields = 0
    secret_with_scope = 0
    non_secret_without_scope = 0
    guided = 0
    for entry in CATALOGUE:
        for declared in entry.descriptor.schema.fields:
            total_fields += 1
            if declared.is_secret:
                secret_fields += 1
                if declared.min_scope.strip():
                    secret_with_scope += 1
            elif not declared.min_scope.strip():
                non_secret_without_scope += 1
            if declared.guide_url.strip():
                guided += 1

    assert total_fields == EXPECTED_FIELD_COUNT
    assert secret_fields == EXPECTED_SECRET_FIELD_COUNT
    assert non_secret_without_scope == EXPECTED_FIELD_COUNT - EXPECTED_SECRET_FIELD_COUNT

    # These two are the ones this feature exists to move from a partial count
    # to the full one — see this feature's own control file for where the
    # catalogue actually stands and why, if either assertion below is red.
    assert secret_with_scope == EXPECTED_SECRET_FIELD_COUNT, (
        f"{secret_with_scope} of {EXPECTED_SECRET_FIELD_COUNT} secret fields carry a "
        f"minimum permission"
    )
    assert guided == EXPECTED_FIELD_COUNT, (
        f"{guided} of {EXPECTED_FIELD_COUNT} fields carry a guide"
    )
