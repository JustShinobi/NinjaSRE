"""What gets written down, and what the two switches do when they are flipped.

The audit assertions are all one claim said several ways: the value never
appears. That is worth repeating because the audit table is append-only and
exempt from retention, so anything that reaches it is there permanently — which
makes it the single worst place in the deployment for a secret to land.
"""

from __future__ import annotations

import pytest

from platform.guardrails.audit import GuardrailAuditor, log_fields, records_for
from platform.guardrails.engine import GuardrailEngine
from platform.guardrails.rules import GuardrailAction, Ruleset, default_ruleset, parse_ruleset
from platform.guardrails.sinks import Sink
from platform.masking.policy import MaskingLevel
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import ActorKind, AuditOutcome, TenantScope
from platform.trust_controls import (
    GUARDRAILS_SWITCH,
    MASKING_SWITCH,
    TRUST_SWITCHES,
    TrustControls,
)

pytestmark = [pytest.mark.unit]

ORG_ID = "acme"
TEAM_ID = "payments"
SECRET = "tok_abcdefghijklmnop1234"

RULES = """
rules:
  - name: strip-tokens
    action: redact
    patterns:
      - '\\btok_[A-Za-z0-9]{16,64}\\b'
  - name: no-private-keys
    action: block
    patterns:
      - '-----BEGIN [A-Z ]{0,20}PRIVATE KEY-----'
"""


def engine() -> GuardrailEngine:
    """Return an engine over the two rules above."""
    return GuardrailEngine(ruleset=parse_ruleset(RULES, source="test"))


# -- the record ----------------------------------------------------------------


def test_a_record_names_the_rule_and_never_the_match() -> None:
    """No value for any action, not only for the two that are required to hide it."""
    result = engine().scan(f"the value is {SECRET}")

    records = records_for(result, org_id=ORG_ID, team_id=TEAM_ID, location="post_tool_use")

    assert len(records) == 1
    assert records[0].rule == "strip-tokens"
    assert records[0].action is GuardrailAction.REDACT
    assert SECRET not in str(records[0].detail())


def test_one_record_per_rule_rather_than_one_per_match() -> None:
    """A rule that matched two hundred times is one fact about that rule."""
    result = engine().scan(" ".join([SECRET] * 12))

    records = records_for(result, org_id=ORG_ID, location="post_tool_use")

    assert len(records) == 1
    assert records[0].match_count == 12


def test_a_blocked_rule_is_recorded_as_a_denial() -> None:
    """``DENIED`` is the outcome an operator most needs to be able to search for."""
    result = engine().scan("-----BEGIN RSA PRIVATE KEY-----")

    records = records_for(result, org_id=ORG_ID, location="pre_tool_use")

    assert records[0].blocked
    assert records[0].outcome is AuditOutcome.DENIED


def test_truncation_is_carried_into_the_record() -> None:
    """A scan that stopped looking must say so where somebody will read it."""
    from config.constants.security import MAX_SCAN_MATCHES

    result = GuardrailEngine(
        ruleset=parse_ruleset("rules:\n  - name: r\n    patterns: ['x']", source="t")
    ).scan("x" * (MAX_SCAN_MATCHES + 5))

    records = records_for(result, org_id=ORG_ID, location="post_tool_use")

    assert records[0].detail()["truncated"] is True


def test_log_fields_carry_no_value_either() -> None:
    """A log is read by more people than the audit table is, not fewer."""
    result = engine().scan(f"the value is {SECRET}")

    fields = log_fields(result, location="post_tool_use")

    assert fields["rules"] == ("strip-tokens",)
    assert SECRET not in str(fields)


# -- the write -----------------------------------------------------------------


async def test_the_record_reaches_the_audit_trail() -> None:
    """End to end against the fake, which passes the same contract suite as Postgres."""
    gateway = FakePersistence()
    async with gateway.begin_system() as system:
        await system.orgs.create_organisation(ORG_ID, "Acme")
    auditor = GuardrailAuditor(gateway=gateway)
    result = engine().scan(f"the value is {SECRET}")

    written = await auditor.record_scan(
        result, org_id=ORG_ID, team_id=TEAM_ID, location="post_tool_use:datadog_search_logs"
    )

    assert len(written) == 1
    assert written[0].actor_kind is ActorKind.AGENT
    assert written[0].resource_id == "strip-tokens"

    scope = TenantScope(org_id=ORG_ID, team_node_id=TEAM_ID)
    async with gateway.begin(scope) as unit:
        stored = await unit.audit.query(action="guardrail.match")
    assert len(stored) == 1
    assert SECRET not in str(stored[0].detail)


async def test_a_clean_scan_writes_nothing() -> None:
    """The audit trail is for events, and nothing happening is not one."""
    gateway = FakePersistence()
    async with gateway.begin_system() as system:
        await system.orgs.create_organisation(ORG_ID, "Acme")

    written = await GuardrailAuditor(gateway=gateway).record_scan(
        engine().scan("nothing interesting here"), org_id=ORG_ID, location="post_tool_use"
    )

    assert written == ()


# -- the switches --------------------------------------------------------------


def test_both_switches_are_on_by_default() -> None:
    """A deployment that configures nothing is protected, not unprotected."""
    controls = TrustControls()

    assert controls.masking_enabled
    assert controls.guardrails_enabled
    assert controls.masking_context().active


def test_turning_masking_off_produces_an_inactive_context() -> None:
    """The ablation's "off" for masking is a policy of ``off``, not a flag elsewhere."""
    controls = TrustControls().without(MASKING_SWITCH)

    assert not controls.masking_context().active
    assert controls.masking_context().policy.level is MaskingLevel.OFF


def test_turning_masking_off_leaves_the_client_unwrapped() -> None:
    """So an ablation run takes the same call path as a deployment with no masking."""

    class Stub:
        provider_id = "anthropic"
        model_id = "claude-sonnet-5"

    client = Stub()
    controls = TrustControls().without(MASKING_SWITCH)

    assert controls.wrap(client, controls.masking_context()) is client  # type: ignore[arg-type]


def test_turning_guardrails_off_still_records_what_would_have_matched() -> None:
    """The constitutional line: the engine cannot be removed from the boundary.

    An operator who disabled guardrails still learns what the enabled ruleset
    would have caught, which is what makes turning them back on an informed
    decision rather than a hunch.
    """
    controls = TrustControls(rules=parse_ruleset(RULES, source="test")).without(GUARDRAILS_SWITCH)

    result = controls.engine().scan("-----BEGIN RSA PRIVATE KEY-----")

    assert result.rules_fired == ("no-private-keys",)
    assert not result.blocked
    assert result.text == "-----BEGIN RSA PRIVATE KEY-----"


def test_the_two_switches_are_independent() -> None:
    """Which is what makes each one an axis rather than a mode."""
    controls = TrustControls(rules=parse_ruleset(RULES, source="test"))

    only_masking_off = controls.without(MASKING_SWITCH)

    assert not only_masking_off.masking_enabled
    assert only_masking_off.guardrails_enabled
    assert not only_masking_off.engine().audit_only


def test_switching_off_returns_a_new_object() -> None:
    """An ablation run must not leave a switch flipped for the run after it."""
    controls = TrustControls()

    controls.without(MASKING_SWITCH, GUARDRAILS_SWITCH)

    assert controls.masking_enabled
    assert controls.guardrails_enabled


def test_an_unknown_switch_raises() -> None:
    """A table saying it measured an axis it never varied is worse than no table."""
    with pytest.raises(ValueError, match="unknown trust switch"):
        TrustControls().without("memory")


def test_the_switch_names_are_enumerable() -> None:
    """The evaluation suite reads this list rather than hard-coding two strings."""
    assert TRUST_SWITCHES == ("masking", "guardrails")


def test_the_trace_summary_says_how_the_run_was_configured() -> None:
    """T038: an ablation table needs the configuration as well as the outcome."""
    controls = TrustControls(rules=parse_ruleset(RULES, source="test"))

    assert controls.trace_summary() == {
        "masking_enabled": True,
        "masking_level": "standard",
        "guardrails_enabled": True,
        "guardrail_rules": 2,
    }


def test_a_team_resolves_to_the_static_default_until_feature_013() -> None:
    """The seam, asserted so its shape does not drift before it is filled."""
    controls = TrustControls.for_team(level="strict")

    assert controls.policy.level is MaskingLevel.STRICT
    assert controls.rules is None


def test_a_sink_guard_carries_the_run_context() -> None:
    """Restoration at the sink needs the run's mapping, not a fresh one."""
    controls = TrustControls(rules=Ruleset())
    context = controls.masking_context()

    guard = controls.sink_guard(context)

    assert guard.masking is context
    assert guard.render("plain text", sink=Sink.CLI) == "plain text"


def test_the_shipped_rules_are_the_default_source() -> None:
    """``rules=None`` means the shipped set, not an empty one."""
    assert len(TrustControls().engine().ruleset) == len(default_ruleset())
