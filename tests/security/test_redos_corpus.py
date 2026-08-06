"""Every pattern that runs on untrusted text, timed against input built to break it.

A guardrail engine is a regular-expression engine pointed at whatever a log line
happened to contain, which makes catastrophic backtracking a denial of service
an attacker reaches through a *log message*. There is no authentication in front
of that, and the payload is a string.

So the corpus here is adversarial rather than representative. Each input is the
shape that makes a backtracking pattern explode — a long run of the characters
the pattern is built from, ending in one that cannot complete the match — and
every detector, every shipped rule, and the merge step are timed against all of
them.

The assertion is wall clock rather than step count because wall clock is what an
operator experiences. The budget is three orders of magnitude above what a
linear pattern costs on this corpus, so a failure here is never a slow machine;
it is a pattern that has started backtracking.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import pytest

from config.constants.security import PATTERN_VALIDATION_BUDGET_SECONDS
from platform.guardrails.engine import GuardrailEngine
from platform.guardrails.rules import default_ruleset
from platform.masking.apply import mask
from platform.masking.detectors import DETECTORS, Detector
from platform.masking.mapping import MaskMapping
from platform.masking.policy import CustomPattern, CustomPatternError, MaskingLevel, MaskingPolicy

pytestmark = [pytest.mark.security]

#: How long a run of adversarial characters to build. Long enough that an
#: exponential pattern is hopeless and a linear one is unbothered, short enough
#: that the whole corpus runs in the gate's budget.
_RUN_LENGTH = 4_000


def _adversarial_corpus() -> tuple[tuple[str, str], ...]:
    """Return ``(name, text)`` pairs shaped to make a backtracking pattern explode.

    Each one is a long homogeneous run followed by a character that forces the
    engine to fail the match at the very end — which is the only place a
    backtracking pattern is expensive.
    """
    return (
        ("hyphens", "-" * _RUN_LENGTH + "!"),
        ("lowercase", "a" * _RUN_LENGTH + "!"),
        ("digits", "1" * _RUN_LENGTH + "!"),
        ("dots", "a." * _RUN_LENGTH + "!"),
        ("dashed-labels", "a-" * _RUN_LENGTH + "!"),
        ("dotted-labels", "ab." * _RUN_LENGTH + "!"),
        ("colons", "a:" * _RUN_LENGTH + "!"),
        ("slashes", "a/" * _RUN_LENGTH + "!"),
        ("equals", "a=" * _RUN_LENGTH + "!"),
        ("mixed-alnum", "a1" * _RUN_LENGTH + "!"),
        ("base64ish", "aA0+/" * (_RUN_LENGTH // 5) + "!"),
        ("ip-prefix", "1.1.1." * (_RUN_LENGTH // 6) + "!"),
        ("arn-prefix", "arn:aws:s3:::" * (_RUN_LENGTH // 13) + "!"),
        ("pem-header", "-----BEGIN " * (_RUN_LENGTH // 11) + "!"),
        ("jwt-ish", "eyJhbGci." * (_RUN_LENGTH // 9) + "!"),
        ("connection-string", "postgres://a:b@" * (_RUN_LENGTH // 15) + "!"),
        ("whitespace", " " * _RUN_LENGTH + "!"),
        ("newlines", "a\n" * _RUN_LENGTH + "!"),
        ("quotes", 'a="' * _RUN_LENGTH + "!"),
        ("namespace-label", "namespace=" * (_RUN_LENGTH // 10) + "!"),
    )


CORPUS = _adversarial_corpus()


def _elapsed(work: Callable[[], object]) -> float:
    """Return how long ``work`` took, called once."""
    started = time.perf_counter()
    work()
    return time.perf_counter() - started


@pytest.mark.parametrize("detector", DETECTORS, ids=lambda d: d.name)
@pytest.mark.parametrize("case", CORPUS, ids=lambda c: c[0])
def test_every_detector_is_bounded_on_adversarial_input(
    detector: Detector, case: tuple[str, str]
) -> None:
    """No masking detector backtracks on the corpus."""
    name, text = case

    elapsed = _elapsed(lambda: list(detector.pattern.finditer(text)))

    assert elapsed < PATTERN_VALIDATION_BUDGET_SECONDS, (
        f"{detector.name} spent {elapsed:.3f}s on {name}"
    )


@pytest.mark.parametrize("case", CORPUS, ids=lambda c: c[0])
def test_masking_as_a_whole_is_bounded(case: tuple[str, str]) -> None:
    """The detectors are bounded individually and bounded composed."""
    _, text = case
    policy = MaskingPolicy(level=MaskingLevel.STRICT)

    elapsed = _elapsed(lambda: mask(text, policy=policy, mapping=MaskMapping()))

    assert elapsed < PATTERN_VALIDATION_BUDGET_SECONDS, f"masking spent {elapsed:.3f}s"


@pytest.mark.parametrize("case", CORPUS, ids=lambda c: c[0])
def test_every_shipped_rule_is_bounded(case: tuple[str, str]) -> None:
    """The same claim, for the rules that ship rather than the detectors."""
    _, text = case
    engine = GuardrailEngine(ruleset=default_ruleset())

    elapsed = _elapsed(lambda: engine.scan(text))

    assert elapsed < PATTERN_VALIDATION_BUDGET_SECONDS, f"the ruleset spent {elapsed:.3f}s"


def test_a_backtracking_custom_pattern_is_rejected_at_load() -> None:
    """An operator's pattern is validated against this corpus before it is used.

    Rejecting at load is the only place the rejection is cheap. Rejecting during
    a scan means the scan already paid for it.
    """
    with pytest.raises(CustomPatternError) as raised:
        CustomPattern(name="greedy", pattern=r"(a+)+$").compile()

    assert "greedy" in str(raised.value)


def test_a_linear_custom_pattern_is_accepted_at_load() -> None:
    """The positive control: validation rejects backtracking, not custom patterns."""
    compiled = CustomPattern(name="ticket", pattern=r"\bINC-[0-9]{4,8}\b").compile()

    assert compiled.search("incident INC-4821 is open") is not None
