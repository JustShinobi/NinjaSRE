"""What each detector finds, and — more interestingly — what it declines to find.

Over-masking is the failure mode that matters here. A detector that misses a pod
name leaks one identifier; a detector that masks every English word in the
report destroys the report, and the operator turns masking off. So roughly half
of what follows asserts that something is *not* masked.
"""

from __future__ import annotations

import pytest

from platform.masking.detectors import IdentifierKind, detect
from platform.masking.policy import CustomPattern, MaskingLevel, MaskingPolicy

pytestmark = [pytest.mark.unit]

STANDARD = MaskingPolicy(level=MaskingLevel.STANDARD)
STRICT = MaskingPolicy(level=MaskingLevel.STRICT)
OFF = MaskingPolicy(level=MaskingLevel.OFF)


def kinds(text: str, policy: MaskingPolicy = STANDARD) -> list[tuple[IdentifierKind, str]]:
    """Return what ``policy`` detects in ``text``, as (kind, value) pairs."""
    return [(found.kind, found.value) for found in detect(text, policy)]


# -- structural shapes ---------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("pod checkout-7d9f8b6c5d-x2n4p died", "checkout-7d9f8b6c5d-x2n4p"),
        ("api-gateway-58c4b7d9f6-mn2kx", "api-gateway-58c4b7d9f6-mn2kx"),
        ("`billing-worker-6f4d8a9c2b-qq81z`", "billing-worker-6f4d8a9c2b-qq81z"),
    ],
)
def test_a_replicaset_pod_name_needs_no_label(text: str, expected: str) -> None:
    """The two trailing hash segments are unambiguous on their own."""
    assert (IdentifierKind.POD, expected) in kinds(text)


@pytest.mark.parametrize(
    "text",
    [
        "the checkout service is degraded",
        "restart-policy-always is set",
        "commit 7d9f8b6c5d touched two files",
    ],
)
def test_ordinary_hyphenated_text_is_not_a_pod(text: str) -> None:
    """Nothing here has the shape, and nothing here should be masked."""
    assert not [found for found in kinds(text) if found[0] is IdentifierKind.POD]


def test_an_arn_is_one_identifier_not_three() -> None:
    """The account number and region inside an ARN are part of it.

    Detecting them separately would produce three tokens where the text meant
    one thing, and the model would reason about a role, an account, and a
    region that have no stated relationship.
    """
    text = "assumed arn:aws:iam::417290583641:role/checkout-task"

    found = kinds(text)

    assert found == [(IdentifierKind.ARN, "arn:aws:iam::417290583641:role/checkout-task")]


@pytest.mark.parametrize(
    "text",
    ["node 10.42.17.203 is cordoned", "endpoint 10.42.17.203.", "(10.42.17.203)"],
)
def test_an_ipv4_address_is_found_however_the_sentence_ends(text: str) -> None:
    """An address at the end of a sentence is followed by a full stop."""
    assert (IdentifierKind.IP_ADDRESS, "10.42.17.203") in kinds(text)


@pytest.mark.parametrize("text", ["version 1.2.3.4.5 shipped", "ratio 1.0.0.0.1"])
def test_a_five_part_dotted_number_is_not_an_address(text: str) -> None:
    """The guard that lets a full stop through still refuses this."""
    assert not [found for found in kinds(text) if found[0] is IdentifierKind.IP_ADDRESS]


@pytest.mark.parametrize("text", ["at 2026-08-06T12:34:56Z", "took 12:34:56"])
def test_a_timestamp_is_not_an_ipv6_address(text: str) -> None:
    """Every character of a time is a hex digit, which is the whole trap."""
    assert not [found for found in kinds(text) if found[0] is IdentifierKind.IP_ADDRESS]


def test_a_real_ipv6_address_is_found() -> None:
    """The positive control for the rule above."""
    assert (IdentifierKind.IP_ADDRESS, "fe80::1c2d:3e4f") in kinds("bound to fe80::1c2d:3e4f")


def test_a_twelve_digit_number_reads_as_an_account_id() -> None:
    """Ten digits is a Unix timestamp and thirteen is a millisecond one."""
    assert (IdentifierKind.CLOUD_ACCOUNT_ID, "417290583641") in kinds("account 417290583641")


@pytest.mark.parametrize("text", ["at 1785072000", "at 1785072000123"])
def test_a_timestamp_is_not_an_account_id(text: str) -> None:
    """The two commonest neighbours of a twelve-digit number."""
    assert not [found for found in kinds(text) if found[0] is IdentifierKind.CLOUD_ACCOUNT_ID]


@pytest.mark.parametrize(
    "text",
    [
        "checkout.payments.svc.cluster.local",
        "db-primary.internal",
        "api.acme.com",
    ],
)
def test_a_hostname_is_found_by_its_suffix(text: str) -> None:
    """The suffix is what distinguishes a host from a dotted string."""
    assert (IdentifierKind.HOSTNAME, text) in kinds(text)


@pytest.mark.parametrize(
    "text",
    [
        "raised in core.llm.client",
        "see platform.guardrails.engine",
        "opened config.constants.security",
    ],
)
def test_a_module_path_is_not_a_hostname(text: str) -> None:
    """A stack trace is the commonest dotted string in an incident, by far.

    Masking it would put a token in every traceback and make the report
    unreadable while hiding nothing that was ever secret.
    """
    assert not [found for found in kinds(text) if found[0] is IdentifierKind.HOSTNAME]


# -- contextual shapes ---------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "namespace=payments-prod",
        "namespace: payments-prod",
        "--namespace payments-prod",
        "| namespace | payments-prod |",
        'k8s_namespace="payments-prod"',
    ],
)
def test_a_namespace_is_found_behind_any_recognised_label(text: str) -> None:
    """Five spellings, because evidence arrives in five formats."""
    assert (IdentifierKind.NAMESPACE, "payments-prod") in kinds(text)


@pytest.mark.parametrize("word", ["frontend", "production", "checkout", "staging", "default"])
def test_a_generic_word_is_not_masked_without_a_label(word: str) -> None:
    """The reason contextual detectors exist at all.

    Every one of these is a namespace somewhere and an ordinary English word
    everywhere else. Masking them unlabelled would replace half the prose in
    the report.
    """
    text = f"the {word} path is slow and {word} has been slow all week"

    assert kinds(text, STRICT) == []


def test_a_label_that_is_part_of_a_longer_word_does_not_count() -> None:
    """``my_namespace`` is somebody's variable, not the platform's label."""
    assert kinds("my_namespace_default = 3") == []


def test_service_names_are_masked_only_at_strict() -> None:
    """The level where the quality trade-off becomes real."""
    text = "service=checkout is returning 503"

    assert kinds(text, STANDARD) == []
    assert (IdentifierKind.SERVICE, "checkout") in kinds(text, STRICT)


def test_deployment_names_are_masked_only_at_strict() -> None:
    """Same level, same reason."""
    text = "deployment=checkout-api scaled to zero"

    assert kinds(text, STANDARD) == []
    assert (IdentifierKind.DEPLOYMENT, "checkout-api") in kinds(text, STRICT)


def test_nothing_is_detected_when_the_policy_is_off() -> None:
    """``off`` means off, not "off for the contextual ones"."""
    assert kinds("pod checkout-7d9f8b6c5d-x2n4p in namespace=prod", OFF) == []


# -- custom patterns -----------------------------------------------------------


def test_a_custom_pattern_names_its_own_tokens() -> None:
    """``NSRE_MASK_TICKET_1`` reads better in a prompt than ``NSRE_MASK_CUSTOM_1``."""
    policy = MaskingPolicy(
        level=MaskingLevel.STRICT,
        custom_patterns=(CustomPattern(name="ticket", pattern=r"(?P<value>\bINC-[0-9]{4,8}\b)"),),
    )

    found = detect("see INC-4821 for detail", policy)

    assert [(item.label, item.value) for item in found] == [("TICKET", "INC-4821")]


def test_a_custom_pattern_wins_an_overlap_with_a_shipped_detector() -> None:
    """The operator knows their environment; the shipped detector guessed."""
    policy = MaskingPolicy(
        level=MaskingLevel.STRICT,
        custom_patterns=(
            CustomPattern(name="node", pattern=r"(?P<value>node-10\.42\.[0-9]{1,3}\.[0-9]{1,3})"),
        ),
    )

    found = detect("drained node-10.42.17.203 at noon", policy)

    assert [(item.label, item.value) for item in found] == [("NODE", "node-10.42.17.203")]


# -- the prefilter -------------------------------------------------------------

#: Every shape, in one payload, so the filter has nothing to skip and the two
#: paths have to agree on everything rather than on nothing.
EVERYTHING = (
    "pod checkout-7d9f8b6c5d-x2n4p namespace=payments-prod cluster=prod-eu-west-1-blue "
    "service=checkout deployment=checkout-api node 10.42.17.203 via fe80::1c2d:3e4f "
    "host db-primary.payments.svc.cluster.local account 417290583641 "
    "role arn:aws:iam::417290583641:role/checkout-task"
)


@pytest.mark.parametrize("text", [EVERYTHING, "nothing here at all", ""])
def test_the_prefilter_does_not_change_what_is_detected(text: str) -> None:
    """It is an optimisation, and an optimisation that changes results is a bug.

    Comparing ``detect`` against running every pattern unconditionally is what
    catches a ``requires`` literal that is narrower than the pattern behind it —
    which would silently stop detecting a shape rather than fail loudly.
    """
    from platform.masking.detectors import detectors_for

    unfiltered = sorted(
        (found.kind, found.value, found.start)
        for detector in detectors_for(STRICT)
        for found in detector.scan(text)
    )
    filtered = sorted(
        (found.kind, found.value, found.start)
        for detector in detectors_for(STRICT)
        if detector.applies_to(text.lower())
        for found in detector.scan(text)
    )

    assert filtered == unfiltered


def test_custom_patterns_are_off_below_strict() -> None:
    """They are declared at ``strict`` because that is the level that turns them on."""
    policy = MaskingPolicy(
        level=MaskingLevel.STANDARD,
        custom_patterns=(CustomPattern(name="ticket", pattern=r"(?P<value>\bINC-[0-9]{4,8}\b)"),),
    )

    assert detect("see INC-4821", policy) == ()
