"""Token stability, token format, and what a policy resolves to.

Three separate claims live here, and they fail in three different ways.

Stability failing means the model stops being able to correlate, and the
investigation quietly gets worse without anything looking broken. Format failing
means a token collides with real text and restoration corrupts a report.
Resolution failing means a cloud provider gets identifiers under a policy the
operator believed was protecting them, which is the one that ends up in a
regulator's letter.
"""

from __future__ import annotations

import pytest

from config.constants.llm import LOCAL_PROVIDERS, PROVIDER_ANTHROPIC, PROVIDER_OLLAMA
from config.constants.security import MASK_TOKEN_PREFIX
from platform.masking.apply import mask, unmask
from platform.masking.context import MaskingContext
from platform.masking.detectors import IdentifierKind
from platform.masking.mapping import TOKEN_PATTERN, MaskMapping
from platform.masking.policy import CustomPattern, MaskingLevel, MaskingPolicy

pytestmark = [pytest.mark.unit]

STANDARD = MaskingPolicy(level=MaskingLevel.STANDARD)


# -- stability -----------------------------------------------------------------


def test_the_same_identifier_gets_the_same_token() -> None:
    """The stability guarantee, at its smallest."""
    mapping = MaskMapping()

    first = mapping.token_for("POD", "checkout-7d9f8b6c5d-x2n4p")
    second = mapping.token_for("POD", "checkout-7d9f8b6c5d-x2n4p")

    assert first == second
    assert len(mapping) == 1


def test_the_same_identifier_gets_the_same_token_across_evidence_sources() -> None:
    """The case that matters: one pod, two tools, two payloads, one token.

    This is what makes a masked investigation possible at all. A model that
    cannot tell that the pod in the metrics result is the pod in the log result
    cannot draw the conclusion the investigation exists to draw.
    """
    context = MaskingContext(policy=STANDARD)
    from_metrics = 'container_memory_usage{pod="checkout-7d9f8b6c5d-x2n4p"} 2.1e9'
    from_logs = "checkout-7d9f8b6c5d-x2n4p OOMKilled after 4 restarts"

    masked_metrics = context.mask(from_metrics)
    masked_logs = context.mask(from_logs)

    token = next(name for name, value in context.mapping.entries().items() if "checkout" in value)
    assert token in masked_metrics
    assert token in masked_logs


def test_different_identifiers_of_one_kind_count_up() -> None:
    """Two pods are two tokens, and the ordinals say which is which."""
    mapping = MaskMapping()

    first = mapping.token_for("POD", "a-1234567890-aaaaa")
    second = mapping.token_for("POD", "b-1234567890-bbbbb")

    assert (first, second) == ("NSRE_MASK_POD_1", "NSRE_MASK_POD_2")


def test_each_kind_counts_independently() -> None:
    """So a prompt reads ``POD_1`` and ``CLUSTER_1`` rather than ``POD_1`` and ``CLUSTER_2``."""
    mapping = MaskMapping()

    assert mapping.token_for("POD", "a") == "NSRE_MASK_POD_1"
    assert mapping.token_for("CLUSTER", "b") == "NSRE_MASK_CLUSTER_1"


# -- the table is itself a secret ---------------------------------------------


def test_the_repr_names_nothing() -> None:
    """A repr surfaces in a traceback, which is where this must not be."""
    mapping = MaskMapping()
    mapping.token_for("POD", "checkout-7d9f8b6c5d-x2n4p")

    assert "checkout" not in repr(mapping)
    assert repr(mapping) == "MaskMapping(entries=1)"


def test_the_trace_summary_carries_counts_and_nothing_else() -> None:
    """What a run trace may record about masking."""
    context = MaskingContext(policy=STANDARD)
    context.mask("pod checkout-7d9f8b6c5d-x2n4p on node 10.42.17.203")

    summary = context.trace_summary()

    assert summary == {
        "level": "standard",
        "identifiers_masked": 2,
        "by_kind": {"POD": 1, "IP": 1},
    }
    assert "checkout-7d9f8b6c5d-x2n4p" not in str(summary)


def test_entries_returns_a_copy() -> None:
    """A caller holding the table must not be able to grow the run's mapping."""
    mapping = MaskMapping()
    mapping.token_for("POD", "a")

    mapping.entries()["NSRE_MASK_POD_99"] = "b"  # type: ignore[index]

    assert mapping.value_for("NSRE_MASK_POD_99") is None


# -- token format --------------------------------------------------------------


#: Lines taken from the shapes NinjaSRE's evidence actually arrives in. If a
#: token could occur naturally in any of these, restoration would corrupt text
#: nobody masked.
EVIDENCE_CORPUS: tuple[str, ...] = (
    'container_memory_working_set_bytes{namespace="prod",pod="checkout-7d9f8b6c5d-x2n4p"} 2.1e9',
    "2026-08-06T12:34:56.789Z ERROR checkout OOMKilled exit=137 restarts=4",
    '{"level":"error","msg":"connection refused","addr":"10.42.17.203:5432"}',
    "NAME READY STATUS RESTARTS AGE\ncheckout-7d9f8b6c5d-x2n4p 0/1 CrashLoopBackOff 4 12m",
    "arn:aws:iam::417290583641:role/checkout-task",
    "Traceback (most recent call last):\n  File core/llm/client.py, line 214",
    "SELECT count(*) FROM orders WHERE created_at > now() - interval '1 hour'",
    "MASK_TOKEN NSRE MASK POD nsre_mask_pod_1 NSREMASKPOD1",
    "-----BEGIN CERTIFICATE-----\nMIIB...\n-----END CERTIFICATE-----",
    "kubectl -n payments-prod describe pod checkout-7d9f8b6c5d-x2n4p",
)


@pytest.mark.parametrize("line", EVIDENCE_CORPUS, ids=range(len(EVIDENCE_CORPUS)))
def test_no_token_shape_occurs_naturally_in_evidence(line: str) -> None:
    """A collision would make restoration replace text nobody masked."""
    assert TOKEN_PATTERN.search(line) is None


def test_the_token_pattern_matches_what_the_mapping_issues() -> None:
    """The positive control: the pattern and the allocator agree."""
    mapping = MaskMapping()

    token = mapping.token_for("CLOUD_ACCOUNT_ID", "417290583641")

    assert TOKEN_PATTERN.fullmatch(token) is not None
    assert token.startswith(MASK_TOKEN_PREFIX)


def test_an_unknown_token_survives_restoration_untouched() -> None:
    """Resolving a token nobody issued would name a pod the sentence was not about."""
    mapping = MaskMapping()
    mapping.token_for("POD", "checkout-7d9f8b6c5d-x2n4p")

    assert unmask("also check NSRE_MASK_POD_99", mapping=mapping) == "also check NSRE_MASK_POD_99"


def test_masking_is_idempotent() -> None:
    """Masking already-masked text must not mask the tokens.

    Tokens are uppercase with underscores and no detector's value class admits
    that shape, so this holds by construction — but it holds by construction
    only until somebody adds a detector, which is why it is asserted.
    """
    mapping = MaskMapping()
    once = mask("pod checkout-7d9f8b6c5d-x2n4p", policy=STANDARD, mapping=mapping)
    twice = mask(once, policy=STANDARD, mapping=mapping)

    assert once == twice


# -- policy resolution ---------------------------------------------------------


def test_local_models_exempt_resolves_to_off_for_a_local_provider() -> None:
    """Nothing leaves the host, so masking would cost quality for nothing."""
    policy = MaskingPolicy(level=MaskingLevel.LOCAL_MODELS_EXEMPT)

    assert policy.resolve_for_provider(PROVIDER_OLLAMA).level is MaskingLevel.OFF


def test_local_models_exempt_resolves_to_standard_for_a_cloud_provider() -> None:
    """The same policy, the other destination."""
    policy = MaskingPolicy(level=MaskingLevel.LOCAL_MODELS_EXEMPT)

    assert policy.resolve_for_provider(PROVIDER_ANTHROPIC).level is MaskingLevel.STANDARD


@pytest.mark.parametrize("level", [MaskingLevel.OFF, MaskingLevel.STANDARD, MaskingLevel.STRICT])
def test_every_other_level_resolves_to_itself(level: MaskingLevel) -> None:
    """Only the exemption is provider-dependent."""
    policy = MaskingPolicy(level=level)

    assert policy.resolve_for_provider(PROVIDER_ANTHROPIC) == policy
    assert policy.resolve_for_provider(LOCAL_PROVIDERS[0]) == policy


def test_resolution_keeps_the_custom_patterns() -> None:
    """An operator's patterns are not a property of the destination."""
    patterns = (CustomPattern(name="ticket", pattern=r"(?P<value>INC-[0-9]{4})"),)
    policy = MaskingPolicy(level=MaskingLevel.LOCAL_MODELS_EXEMPT, custom_patterns=patterns)

    assert policy.resolve_for_provider(PROVIDER_ANTHROPIC).custom_patterns == patterns


def test_a_resolved_context_shares_the_mapping() -> None:
    """One run, two providers, one table — so tokens stay stable across both."""
    context = MaskingContext(policy=MaskingPolicy(level=MaskingLevel.LOCAL_MODELS_EXEMPT))

    cloud = context.for_provider(PROVIDER_ANTHROPIC)

    assert cloud.mapping is context.mapping


def test_an_unknown_level_raises_rather_than_defaulting() -> None:
    """A typo must not silently select the least protective level."""
    with pytest.raises(ValueError, match="unknown masking level"):
        MaskingPolicy.from_level("strictt")


def test_an_unresolved_exemption_reads_as_masking() -> None:
    """Answering "nothing" to an unanswerable question is the unsafe half."""
    assert MaskingPolicy(level=MaskingLevel.LOCAL_MODELS_EXEMPT).masks_anything


def test_the_kind_taxonomy_covers_every_detector_label() -> None:
    """A kind nobody enumerated would produce a token nobody expects."""
    assert IdentifierKind.POD.value.upper() == "POD"
    assert {kind.value for kind in IdentifierKind} >= {"pod", "cluster", "namespace", "arn"}
