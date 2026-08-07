"""FR-006. Seven categories, one table, no vendor's opinion.

The value of a shared taxonomy is not that it exists but that nothing may add to
it. A vendor whose 403 arrived as "transient" would be retried through the whole
retry budget on an authorisation failure, every incident, and the only symptom
would be an investigation that is slow for reasons nobody can see.

The second thing asserted here is that the two vocabularies stay in step. The
fine-grained reason is what an operator reads; the category is what the contract
suite asserts and the loop acts on. Every reason has to have a category, and the
test that proves it is the one that fires when somebody adds an eleventh reason.
"""

from __future__ import annotations

import pytest

from core.capability.result import CapabilityErrorClass
from integrations._base.errors import (
    ErrorCategory,
    IntegrationError,
    IntegrationErrorReason,
    categories,
    category_for,
)


def test_the_taxonomy_has_exactly_the_seven_names_the_framework_contracts_on() -> None:
    assert {category.value for category in categories()} == {
        "auth",
        "permission",
        "not_found",
        "rate_limited",
        "transient",
        "invalid_request",
        "unavailable",
    }


@pytest.mark.parametrize("reason", list(IntegrationErrorReason))
def test_every_reason_has_a_category(reason: IntegrationErrorReason) -> None:
    """An unmapped reason would raise at the moment a vendor first produced it."""
    error = IntegrationError("failed", integration="acme", reason=reason)

    assert isinstance(error.category, ErrorCategory)


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, ErrorCategory.AUTH),
        (403, ErrorCategory.PERMISSION),
        (404, ErrorCategory.NOT_FOUND),
        (408, ErrorCategory.TRANSIENT),
        (422, ErrorCategory.INVALID_REQUEST),
        (429, ErrorCategory.RATE_LIMITED),
        (500, ErrorCategory.TRANSIENT),
        (502, ErrorCategory.TRANSIENT),
        (504, ErrorCategory.TRANSIENT),
    ],
)
def test_a_vendor_status_lands_in_the_same_category_whichever_vendor_sent_it(
    status: int, expected: ErrorCategory
) -> None:
    assert category_for(status) is expected


def test_a_credential_the_proxy_cannot_resolve_is_an_auth_problem_for_the_operator() -> None:
    """And a permission problem for the model — both readings are right."""
    error = IntegrationError(
        "no credential", integration="acme", reason=IntegrationErrorReason.CREDENTIAL_UNAVAILABLE
    )

    assert error.category is ErrorCategory.AUTH
    assert error.to_capability_error().classification is CapabilityErrorClass.PERMISSION_DENIED


def test_only_the_two_categories_worth_repeating_are_retryable() -> None:
    """Repeating a denial produces the same denial and spends a loop iteration."""
    retryable = {category for category in categories() if category.retryable}

    assert retryable == {ErrorCategory.TRANSIENT, ErrorCategory.RATE_LIMITED}
