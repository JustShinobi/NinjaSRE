"""Loading rules, merging an operator's onto the shipped ones, and never starting bare.

The claim this file exists for: a malformed ruleset leaves the previous one
active and reports the error, and the platform never runs with zero rules
because of a parse failure. That is a property about a *failure* path,
which means it only holds if somebody drives the failure — a ruleset that has
never failed to load is a ruleset whose recovery has never run.

Reload is a modification-time poll rather than a watcher, which is what makes
these tests deterministic: an injected clock decides when the next check
happens, so nothing here sleeps and nothing here is flaky on a loaded machine.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from platform.guardrails.rules import (
    GuardrailAction,
    Ruleset,
    RulesetError,
    RulesetLoader,
    default_ruleset,
    parse_ruleset,
)

pytestmark = [pytest.mark.unit]

OPERATOR_RULES = """
rules:
  - name: internal-ticket-id
    description: Our ticket identifiers are not for a third party.
    action: redact
    keywords: ["inc-"]
    patterns:
      - '\\bINC-[0-9]{4,8}\\b'
"""

DISABLES_A_SHIPPED_RULE = """
rules:
  - name: json-web-token
    description: We index JWT headers deliberately and need them intact.
    action: audit
    enabled: false
    patterns:
      - 'never-matches-anything-at-all'
"""


class FakeClock:
    """A clock a test moves by hand, so nothing here has to sleep."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def write(path: Path, document: str) -> Path:
    """Write ``document`` to ``path`` and return it."""
    path.write_text(document, encoding="utf-8")
    return path


# -- parsing -------------------------------------------------------------------


def test_a_rule_parses_into_the_shape_the_engine_reads() -> None:
    """The happy path, so the failures below mean something."""
    ruleset = parse_ruleset(OPERATOR_RULES, source="test")

    assert len(ruleset) == 1
    rule = ruleset.rules[0]
    assert rule.name == "internal-ticket-id"
    assert rule.action is GuardrailAction.REDACT
    assert rule.keywords == ("inc-",)
    assert rule.patterns[0].search("see INC-4821") is not None


def test_an_empty_document_is_an_empty_ruleset_not_an_error() -> None:
    """An operator who has commented everything out has said something valid."""
    assert parse_ruleset("", source="test").rules == ()


@pytest.mark.parametrize(
    ("document", "expected"),
    [
        ("rules: [", "not valid YAML"),
        ("- a\n- b", "expected a mapping"),
        ("rules: not-a-list", "'rules' must be a list"),
        ("rules:\n  - description: no name\n    patterns: ['a']", "has no name"),
        ("rules:\n  - name: a\n    patterns: ['x']\n    action: shout", "expected one of"),
        ("rules:\n  - name: a\n    patterns: []", "declares no patterns"),
        ("rules:\n  - name: a\n    patterns: 'x'", "needs 'patterns' as a list"),
        ("rules:\n  - name: a\n    patern: ['x']", "unknown field"),
        (
            "rules:\n  - name: a\n    patterns: ['x']\n  - name: a\n    patterns: ['y']",
            "two rules are named",
        ),
        ("rules:\n  - name: a\n    patterns: ['(a+)+$']", "backtracks exponentially"),
        ("rules:\n  - name: a\n    patterns: ['[unclosed']", "will not compile"),
    ],
)
def test_a_malformed_document_is_rejected_with_a_reason(document: str, expected: str) -> None:
    """Every rejection names what is wrong, because somebody has to fix it."""
    with pytest.raises(RulesetError, match=expected):
        parse_ruleset(document, source="test")


def test_an_unknown_field_is_rejected_rather_than_ignored() -> None:
    """A silently ignored ``patern:`` is a rule the operator believes is running.

    That is strictly worse than a file that will not load: the operator sees no
    error, believes they are covered, and finds out otherwise from an incident.
    """
    with pytest.raises(RulesetError, match="believes is running"):
        parse_ruleset("rules:\n  - name: a\n    patterns: ['x']\n    replacment: 'y'", source="t")


# -- the shipped set -----------------------------------------------------------


def test_the_shipped_ruleset_loads() -> None:
    """It is packaged data, so a packaging mistake shows up here first."""
    shipped = default_ruleset()

    assert len(shipped) > 10
    assert shipped.enabled == shipped.rules


def test_the_shipped_ruleset_is_parsed_once() -> None:
    """Thirty patterns, each validated against the backtracking probes.

    Paying that per engine would be paying it per investigation.
    """
    assert default_ruleset() is default_ruleset()


# -- merging -------------------------------------------------------------------


def test_operator_rules_are_added_to_the_shipped_ones() -> None:
    """A file that mentions one rule does not remove the other thirty."""
    shipped = default_ruleset()

    merged = shipped.merged_with(parse_ruleset(OPERATOR_RULES, source="operator"))

    assert len(merged) == len(shipped) + 1
    assert "internal-ticket-id" in {rule.name for rule in merged.rules}


def test_an_operator_rule_of_the_same_name_replaces_the_shipped_one() -> None:
    """This is how a shipped rule gets disabled, without editing the package."""
    shipped = default_ruleset()

    merged = shipped.merged_with(parse_ruleset(DISABLES_A_SHIPPED_RULE, source="operator"))

    assert len(merged) == len(shipped)
    jwt = next(rule for rule in merged.rules if rule.name == "json-web-token")
    assert not jwt.enabled
    assert jwt not in merged.enabled


def test_a_replaced_rule_keeps_its_position() -> None:
    """Order decides which rule represents an overlap, so it must not drift."""
    shipped = default_ruleset()
    before = [rule.name for rule in shipped.rules]

    merged = shipped.merged_with(parse_ruleset(DISABLES_A_SHIPPED_RULE, source="operator"))

    assert [rule.name for rule in merged.rules] == before


# -- hot reload and last known good --------------------------------------------


def test_no_operator_file_means_the_shipped_rules(tmp_path: Path) -> None:
    """A deployment that has written no rules is guarded, not unguarded."""
    loader = RulesetLoader(path=tmp_path / "absent.yml")

    assert loader.current().rules == default_ruleset().rules
    assert loader.last_error == ""


def test_an_operator_file_is_merged_on_the_first_read(tmp_path: Path) -> None:
    """The control the reload tests below are measured against."""
    loader = RulesetLoader(path=write(tmp_path / "rules.yml", OPERATOR_RULES))

    assert "internal-ticket-id" in {rule.name for rule in loader.current().rules}


def test_a_changed_file_is_picked_up_without_a_restart(tmp_path: Path) -> None:
    """Rules are tuned during incidents, by whoever is on call."""
    clock = FakeClock()
    path = write(tmp_path / "rules.yml", OPERATOR_RULES)
    loader = RulesetLoader(path=path, reload_interval=1.0, clock=clock)
    assert "second-rule" not in {rule.name for rule in loader.current().rules}

    write(path, OPERATOR_RULES.replace("internal-ticket-id", "second-rule"))
    clock.advance(2.0)

    assert "second-rule" in {rule.name for rule in loader.current().rules}


def test_the_file_is_not_stat_ed_more_often_than_the_interval(tmp_path: Path) -> None:
    """The reload is a poll, and a poll that ran per scan would be a syscall per scan."""
    clock = FakeClock()
    path = write(tmp_path / "rules.yml", OPERATOR_RULES)
    loader = RulesetLoader(path=path, reload_interval=10.0, clock=clock)

    write(path, OPERATOR_RULES.replace("internal-ticket-id", "second-rule"))
    clock.advance(1.0)

    assert "second-rule" not in {rule.name for rule in loader.current().rules}


def test_a_malformed_reload_keeps_the_previous_ruleset(tmp_path: Path) -> None:
    """The recovery claim, the whole of it.

    The operator's good rules stay active, the error is reported, and the
    platform does not fall back to "no rules" — which is the outcome a naive
    reload produces and the one that matters.
    """
    clock = FakeClock()
    path = write(tmp_path / "rules.yml", OPERATOR_RULES)
    loader = RulesetLoader(path=path, reload_interval=1.0, clock=clock)
    good = loader.current()

    write(path, "rules:\n  - name: broken\n    patterns: [")
    clock.advance(2.0)
    after = loader.current()

    assert after.rules == good.rules
    assert "internal-ticket-id" in {rule.name for rule in after.rules}
    assert "not valid YAML" in loader.last_error


def test_a_malformed_file_at_startup_leaves_the_shipped_rules_active(tmp_path: Path) -> None:
    """Never zero rules. The platform starts guarded or it does not start guarded-ish."""
    loader = RulesetLoader(path=write(tmp_path / "rules.yml", "rules: ["))

    assert loader.current().rules == default_ruleset().rules
    assert loader.last_error != ""


def test_a_file_deleted_after_a_good_load_keeps_the_rules(tmp_path: Path) -> None:
    """A ``mv`` mid-edit must not disarm the platform for the length of the edit."""
    clock = FakeClock()
    path = write(tmp_path / "rules.yml", OPERATOR_RULES)
    loader = RulesetLoader(path=path, reload_interval=1.0, clock=clock)
    loader.current()

    path.unlink()
    clock.advance(2.0)

    assert "internal-ticket-id" in {rule.name for rule in loader.current().rules}
    assert loader.last_error != ""


def test_recovery_clears_the_error(tmp_path: Path) -> None:
    """An operator who fixed the file needs to be told they fixed it."""
    clock = FakeClock()
    path = write(tmp_path / "rules.yml", "rules: [")
    loader = RulesetLoader(path=path, reload_interval=1.0, clock=clock)
    assert loader.last_error != ""

    write(path, OPERATOR_RULES)
    clock.advance(2.0)
    loader.current()

    assert loader.last_error == ""
    assert loader.reloads == 1


def test_a_loader_with_no_path_never_reloads() -> None:
    """The static case, so a deployment with no operator rules costs no syscalls."""
    loader = RulesetLoader(base=Ruleset())

    assert loader.current().rules == ()
    assert loader.reloads == 0
