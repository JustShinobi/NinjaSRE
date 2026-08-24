"""Who may accept a certificate nobody verified, and why it is not who configures.

Pinning a fingerprint and supplying an authority do not weaken anything: they
redirect verification to a narrower anchor than the system store, which is
strictly stronger for a host that issues its own certificate. Requiring an
administrator for those would push an operator towards the worse option
precisely because the better one is harder to reach.

Not verifying is the one operation here that gives up a guarantee for nothing
but convenience, and it gets a gate of its own.
"""

from __future__ import annotations

import pytest

from platform.identity.permissions import (
    ROLE_ORDER,
    Permission,
    Role,
    permissions_for,
    roles_granting,
)

pytestmark = pytest.mark.unit


def test_the_permission_exists_and_is_its_own() -> None:
    assert Permission.INTEGRATION_TRUST_UNVERIFIED.value == "integration.trust_unverified"
    assert Permission.INTEGRATION_TRUST_UNVERIFIED is not Permission.INTEGRATION_MANAGE


def test_it_is_classified_as_a_write_by_the_verb_and_not_by_a_second_list() -> None:
    """The derivation already treats an unlisted verb as a write. Confirmed, not assumed."""
    assert not Permission.INTEGRATION_TRUST_UNVERIFIED.is_read_only
    assert Permission.INTEGRATION_TRUST_UNVERIFIED.verb == "trust_unverified"
    assert Permission.INTEGRATION_TRUST_UNVERIFIED.domain == "integration"


def test_the_role_that_only_operates_integrations_does_not_hold_it() -> None:
    operator = permissions_for(Role.OPERATOR)

    assert Permission.INTEGRATION_MANAGE in operator
    assert Permission.INTEGRATION_TRUST_UNVERIFIED not in operator


@pytest.mark.parametrize("role", [Role.ADMIN, Role.OWNER])
def test_an_administrator_and_above_hold_it(role: Role) -> None:
    assert Permission.INTEGRATION_TRUST_UNVERIFIED in permissions_for(role)


@pytest.mark.parametrize("role", [Role.VIEWER, Role.RESPONDER, Role.OPERATOR])
def test_nobody_below_an_administrator_holds_it(role: Role) -> None:
    assert Permission.INTEGRATION_TRUST_UNVERIFIED not in permissions_for(role)


def test_a_denial_names_the_cheapest_role_that_would_have_worked() -> None:
    assert roles_granting(Permission.INTEGRATION_TRUST_UNVERIFIED)[0] is Role.ADMIN


def test_the_roles_still_nest_with_it_in_place() -> None:
    """The nesting is the whole reason a denial has one answer. It still holds."""
    for lower, higher in zip(ROLE_ORDER, ROLE_ORDER[1:], strict=False):
        assert permissions_for(lower) < permissions_for(higher)


def test_pinning_and_supplying_stay_on_the_permission_that_writes_an_address() -> None:
    """The distinction is the design, and it is the part somebody will simplify.

    An operator may point an integration at their cluster and say which
    certificate to trust there. Only an administrator may say to trust whatever
    turns up.
    """
    operator = permissions_for(Role.OPERATOR)

    assert Permission.INTEGRATION_MANAGE in operator
    assert Permission.CREDENTIAL_WRITE in operator
    assert Permission.INTEGRATION_TRUST_UNVERIFIED not in operator
