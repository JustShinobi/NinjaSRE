"""The normalisation fixture table, asserted in both directions.

A normalisation test that only checks merges is a test that passes when the
implementation returns a constant. Both directions are asserted, and the
non-merge table is the one that would catch the change nobody would notice —
because a wrong merge does not raise, it produces a playbook about two systems
presented as one, and every claim in it reads as a finding.

The pairs are stated as data rather than as one test per case so that adding a
rule means adding a row, and so that a proposed addition to the affix lists has
somewhere obvious to prove it does not merge something it should not.
"""

from __future__ import annotations

import pytest

from platform.memory.models import Component
from platform.memory.strategy.normalisation import (
    ALIAS_MAP_CONFIG_KEY,
    DEFAULT_NORMALISER,
    ComponentNormaliser,
    normalise_name,
)

pytestmark = pytest.mark.unit

#: Names that describe the same subject and must reach the same key.
MERGES: tuple[tuple[str, str], ...] = (
    ("payments-api", "payments-service"),
    ("payments-api", "payments"),
    ("prod-payments", "payments-prod"),
    ("payments", "payments-7f9dd8b6c4-x7gr9"),
    ("payments-api", "payments-api-7f9dd8b6c4-x7gr9"),
    ("PaymentsAPI", "payments_api"),
    ("PaymentsAPI", "payments.api"),
    ("prod-payments-api-service", "payments"),
    ("staging-checkout", "checkout-svc"),
    ("kafka-0", "kafka-2"),
    ("orders.prod.svc", "orders"),
    ("Payments-Worker", "payments-workers"),
)

#: Names that describe different subjects and must stay apart. Every row here is
#: a merge that a slightly greedier rule would make.
NON_MERGES: tuple[tuple[str, str], ...] = (
    ("payments", "payment-gateway"),
    ("payments", "payments-ledger"),
    ("orders", "orders-archive"),
    ("redis-cache", "redis-queue"),
    ("auth-db", "auth-proxy"),
    ("checkout", "cart"),
    ("payments-v1", "payments-v2"),
    ("api-gateway", "api-router"),
    ("prod-api", "api-prod"),
)


@pytest.mark.parametrize(("left", "right"), MERGES)
def test_naming_variants_of_one_subject_reach_one_key(left: str, right: str) -> None:
    assert normalise_name(left) == normalise_name(right), (
        f"{left!r} and {right!r} name the same subject; keying them separately is why "
        "the synthesis threshold is never reached in a real corpus"
    )


@pytest.mark.parametrize(("left", "right"), NON_MERGES)
def test_distinct_subjects_stay_distinct(left: str, right: str) -> None:
    assert normalise_name(left) != normalise_name(right), (
        f"{left!r} and {right!r} are two systems; merging them produces one playbook "
        "whose every claim is wrong for whichever one the reader was looking at"
    )


def test_the_type_is_part_of_the_key() -> None:
    """A service and a database of the same name are never one playbook."""
    service = DEFAULT_NORMALISER.normalise(Component(type="service", name="payments-api"))
    database = DEFAULT_NORMALISER.normalise(Component(type="database", name="payments"))

    assert service == "service:payments"
    assert database == "database:payments"
    assert service != database


def test_stripping_never_empties_a_name() -> None:
    """A component made only of describing words keeps all of them.

    Untouched rather than reduced to whichever word survived the passes: that is
    what stops ``prod-api`` and ``api-prod`` normalising to different keys while
    meaning the same thing, and it stops every generically-named component in a
    corpus being filed under one playbook.
    """
    assert normalise_name("service") == "service"
    assert normalise_name("prod-api") == "prod-api"
    assert normalise_name("api-2") == "api-2"
    # A name with one real word in it does get peeled.
    assert normalise_name("kafka-2") == "kafka"


def test_an_alias_merges_what_the_rules_will_not() -> None:
    """The operator's explicit decision, applied after the rules."""
    normaliser = ComponentNormaliser.from_config(
        {ALIAS_MAP_CONFIG_KEY: {"checkout": "cart-service"}}
    )

    assert normaliser.canonical("checkout") == "cart"
    # And it covers the variants, because the rules run first.
    assert normaliser.canonical("CheckoutAPI") == "cart"
    assert normaliser.canonical("prod-checkout") == "cart"
    # The rules alone still keep them apart.
    assert DEFAULT_NORMALISER.canonical("checkout") != DEFAULT_NORMALISER.canonical("cart")


def test_an_alias_chain_resolves_and_a_cycle_terminates() -> None:
    """An operator writing a → b and b → c means a → c; a → b → a is a typo."""
    chained = ComponentNormaliser.from_config(
        {ALIAS_MAP_CONFIG_KEY: {"alpha": "beta", "beta": "gamma"}}
    )
    assert chained.canonical("alpha") == "gamma"

    cyclic = ComponentNormaliser.from_config(
        {ALIAS_MAP_CONFIG_KEY: {"alpha": "beta", "beta": "alpha"}}
    )
    assert cyclic.canonical("alpha") in {"alpha", "beta"}


def test_a_malformed_alias_map_costs_the_entry_not_the_team() -> None:
    """Synthesis must not stop for a team because someone mistyped their config."""
    normaliser = ComponentNormaliser.from_config(
        {ALIAS_MAP_CONFIG_KEY: {"checkout": 7, 9: "cart", "orders": "orders", "ok": "fine"}}
    )

    assert normaliser.aliases == {"ok": "fine"}
    assert normaliser.canonical("checkout") == "checkout"


def test_no_alias_map_configured_is_the_documented_rules() -> None:
    assert ComponentNormaliser.from_config({}).aliases == {}
    assert ComponentNormaliser.from_config({ALIAS_MAP_CONFIG_KEY: "not a map"}).aliases == {}


def test_distinct_keys_are_returned_once_and_in_order() -> None:
    """Two components that normalise together contribute one key."""
    keys = DEFAULT_NORMALISER.keys_for(
        (
            Component(type="service", name="payments-api"),
            Component(type="deployment", name="payments-api"),
            Component(type="service", name="payments-service"),
        )
    )

    assert keys == ("service:payments", "deployment:payments")
