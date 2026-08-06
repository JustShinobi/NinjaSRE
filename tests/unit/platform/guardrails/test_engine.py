"""The three actions, the two bounds, and what the shipped rules do and do not catch.

The default-rule cases are the longest part and are worth their length. A secret
pattern that fires on everything is a pattern an operator disables within a week,
after which it protects nothing — so every shipped rule is asserted twice: once
against the shape it exists for, and once against something that looks like it
and is not.
"""

from __future__ import annotations

import pytest

from config.constants.security import MAX_SCAN_MATCHES, REDACTION_PLACEHOLDER
from platform.guardrails.engine import GuardrailEngine
from platform.guardrails.rules import GuardrailAction, default_ruleset, parse_ruleset

pytestmark = [pytest.mark.unit]


def engine_for(document: str) -> GuardrailEngine:
    """Return an engine over one inline ruleset."""
    return GuardrailEngine(ruleset=parse_ruleset(document, source="test"))


SHIPPED = GuardrailEngine(ruleset=default_ruleset())


# -- the three actions ---------------------------------------------------------


def test_redact_replaces_the_match_and_leaves_the_rest() -> None:
    """The common case."""
    engine = engine_for("rules:\n  - name: r\n    action: redact\n    patterns: ['sekret[0-9]']")

    result = engine.scan("the value is sekret7 and nothing else")

    assert result.text == f"the value is {REDACTION_PLACEHOLDER} and nothing else"
    assert not result.blocked


def test_block_denies_and_still_removes_the_text() -> None:
    """A blocked operation does not proceed, and its text is not carried onward."""
    engine = engine_for("rules:\n  - name: r\n    action: block\n    patterns: ['sekret[0-9]']")

    result = engine.scan("the value is sekret7")

    assert result.blocked
    assert result.blocking_rules == ("r",)
    assert "sekret7" not in result.text


def test_audit_records_without_altering_anything() -> None:
    """The action that lets a shape be observed before it is enforced."""
    engine = engine_for("rules:\n  - name: r\n    action: audit\n    patterns: ['sekret[0-9]']")

    result = engine.scan("the value is sekret7")

    assert result.text == "the value is sekret7"
    assert result.matches[0].action is GuardrailAction.AUDIT
    assert not result.blocked


def test_a_rule_uses_its_own_replacement() -> None:
    """So a redaction can say what was removed without saying what it was."""
    engine = engine_for(
        "rules:\n  - name: r\n    replacement: '[CARD]'\n    patterns: ['4[0-9]{15}']"
    )

    assert engine.scan("paid with 4111111111111111").text == "paid with [CARD]"


def test_a_disabled_rule_does_not_fire() -> None:
    """Individually disableable, which is the operator's escape hatch."""
    engine = engine_for("rules:\n  - name: r\n    enabled: false\n    patterns: ['sekret[0-9]']")

    assert engine.scan("sekret7").clean


def test_the_keyword_prefilter_does_not_change_the_answer() -> None:
    """It is an optimisation, and an optimisation that changes results is a bug."""
    with_keyword = engine_for(
        "rules:\n  - name: r\n    keywords: ['sekret']\n    patterns: ['sekret[0-9]']"
    )
    without = engine_for("rules:\n  - name: r\n    patterns: ['sekret[0-9]']")

    assert with_keyword.scan("sekret7").text == without.scan("sekret7").text


def test_a_keyword_that_is_absent_skips_the_rule() -> None:
    """The other half: a rule whose keyword is missing cannot match."""
    engine = engine_for(
        "rules:\n  - name: r\n    keywords: ['never-here']\n    patterns: ['sekret[0-9]']"
    )

    assert engine.scan("sekret7").clean


# -- bounds --------------------------------------------------------------------


def test_the_match_count_is_capped_and_the_cap_is_recorded() -> None:
    """A scan that quietly stopped looking is indistinguishable from a clean one."""
    engine = engine_for("rules:\n  - name: r\n    patterns: ['x']")

    result = engine.scan("x" * (MAX_SCAN_MATCHES + 50))

    assert len(result.matches) == MAX_SCAN_MATCHES
    assert result.match_limit_reached


def test_truncation_is_recorded_rather_than_silent() -> None:
    """The same claim for the input ceiling."""
    from config.constants.security import MAX_SCAN_INPUT_BYTES

    engine = engine_for("rules:\n  - name: r\n    patterns: ['zzz']")

    result = engine.scan("a" * (MAX_SCAN_INPUT_BYTES + 10))

    assert result.truncated


def test_text_beyond_the_ceiling_is_preserved_unscanned() -> None:
    """Truncation bounds the *scan*, not the text. Dropping the tail would lose evidence."""
    from config.constants.security import MAX_SCAN_INPUT_BYTES

    engine = engine_for("rules:\n  - name: r\n    patterns: ['zzz']")
    text = "a" * (MAX_SCAN_INPUT_BYTES + 10)

    assert len(engine.scan(text).text) == len(text)


def test_an_empty_string_scans_clean_without_touching_a_rule() -> None:
    """The commonest input in the system."""
    assert SHIPPED.scan("").clean


# -- audit-only mode -----------------------------------------------------------


def test_audit_only_downgrades_every_action() -> None:
    """The ablation's "off": nothing altered, nothing blocked, everything recorded."""
    engine = GuardrailEngine.observing(
        ruleset=parse_ruleset(
            "rules:\n  - name: r\n    action: block\n    patterns: ['sekret[0-9]']",
            source="test",
        )
    )

    result = engine.scan("the value is sekret7")

    assert result.text == "the value is sekret7"
    assert not result.blocked
    assert result.rules_fired == ("r",)


# -- the denial the model reads ------------------------------------------------


def test_the_denial_names_the_rule_and_never_the_match() -> None:
    """Both halves in one sentence: actionable, and not a leak."""
    engine = engine_for(
        "rules:\n  - name: no-keys\n    action: block\n    patterns: ['sekret[0-9]']"
    )

    reason = engine.scan("sekret7").denial_reason()

    assert "no-keys" in reason
    assert "sekret7" not in reason
    assert "refused again" in reason


# -- the shipped rules ---------------------------------------------------------

#: ``(rule, text that should match, text that should not)``. The second column
#: is what makes each rule worth shipping; the third is what stops it being
#: turned off within a week.
SHIPPED_CASES: tuple[tuple[str, str, str], ...] = (
    (
        "aws-access-key-id",
        "AKIAIOSFODNN7EXAMPLE",
        "AKIA is the prefix we look for",
    ),
    (
        "aws-secret-access-key",
        "aws_secret_access_key=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        "aws_secret_access_key is rotated nightly",
    ),
    (
        "private-key-block",
        "-----BEGIN RSA PRIVATE KEY-----",
        "-----BEGIN CERTIFICATE-----",
    ),
    (
        "json-web-token",
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
        "eyJhbGciOiJIUzI1NiJ9 is only a header",
    ),
    (
        "database-connection-string",
        "postgresql://ninjasre:hunter2@db-primary.internal:5432/ninjasre",
        "postgresql://db-primary.internal:5432/ninjasre",
    ),
    (
        "bearer-token",
        "Authorization: Bearer eyJraWQiOiJ0ZXN0Iiwic3ViIjoiYWJjIn0AAAA",
        "use a Bearer token from the vault",
    ),
    (
        "github-token",
        "ghp_16C7e42F292c6912E7710c838347Ae178B4a",
        "the ghp_ prefix identifies a classic token",
    ),
    (
        "slack-token",
        "xoxb-2404881234-2404881234-abcdefghijklmnopqrst",
        "rotate the xoxb- token quarterly",
    ),
    (
        "openai-style-api-key",
        "sk-proj-abcdefghijklmnopqrstuvwxyz0123456789",
        "keys start with sk- and are stored in the vault",
    ),
    (
        "google-api-key",
        "AIzaSyD-abcdefghijklmnopqrstuvwxyz01234",
        "AIza is the Google prefix",
    ),
    (
        "generic-labelled-secret",
        'client_secret="s3cr3tv4lu3thatislong"',
        "the client_secret is stored in the vault",
    ),
    (
        "pem-certificate-key-material",
        "DEK-Info: AES-256-CBC,0123456789ABCDEF0123456789ABCDEF",
        "DEK-Info headers appear in encrypted keys",
    ),
    (
        "kubernetes-service-account-token",
        "service_account_token=eyJhbGciOiJSUzI1NiIsImtpZCI6ImFiYyJ9AAAA",
        "the service_account_token is projected by the kubelet",
    ),
)


@pytest.mark.parametrize(("rule", "hit", "miss"), SHIPPED_CASES, ids=[c[0] for c in SHIPPED_CASES])
def test_each_shipped_rule_matches_its_shape(rule: str, hit: str, miss: str) -> None:
    """T024, first half: the rule fires on the thing it exists for."""
    del miss

    assert rule in SHIPPED.scan(hit).rules_fired


@pytest.mark.parametrize(("rule", "hit", "miss"), SHIPPED_CASES, ids=[c[0] for c in SHIPPED_CASES])
def test_no_shipped_rule_matches_a_benign_lookalike(rule: str, hit: str, miss: str) -> None:
    """T024, second half, and the half that decides whether the rule survives.

    Prose *about* a secret is not a secret. A rule that cannot tell the two
    apart fires on every runbook, and the operator turns it off.
    """
    del hit

    assert rule not in SHIPPED.scan(miss).rules_fired


def test_the_shipped_rules_leave_ordinary_incident_text_alone() -> None:
    """The false-positive control over a realistic payload."""
    text = (
        "checkout-7d9f8b6c5d-x2n4p OOMKilled after 4 restarts; memory limit 512Mi, "
        "working set 2.1GiB. Upstream db-primary.internal:5432 refused 12 connections "
        "between 12:31 and 12:34. See runbook RB-118 and the pod's authorization "
        "settings in the namespace policy."
    )

    assert SHIPPED.scan(text).clean
