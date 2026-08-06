"""Declarative rules applied at every point text is used, transmitted, or stored.

    from platform.guardrails import GuardrailEngine, RulesetLoader, register

    loader = RulesetLoader(path=configured_rules_path())
    engine = GuardrailEngine(ruleset=loader)
    register(hooks, engine=engine, auditor=auditor, org_id=org_id)

Three application points, deliberately: ``pre_tool_use`` for arguments,
``post_tool_use`` for results, and ``sinks`` for everything published,
transmitted, or written down. An argument can exfiltrate, a result can poison,
and a sink can publish — one point would miss two of the three.
"""

from __future__ import annotations

from platform.guardrails.audit import GuardrailAuditor, GuardrailAuditRecord
from platform.guardrails.engine import (
    GuardrailEngine,
    MergedSpan,
    ScanMatch,
    ScanResult,
    merge_spans,
)
from platform.guardrails.hooks import GuardrailHooks, register
from platform.guardrails.rules import (
    DEFAULT_RULES_PATH,
    GuardrailAction,
    GuardrailRule,
    Ruleset,
    RulesetError,
    RulesetLoader,
    configured_rules_path,
    default_ruleset,
    load_ruleset,
    parse_ruleset,
)
from platform.guardrails.sinks import EXTERNAL_SINKS, LOCAL_SINKS, Sink, SinkGuard, is_external

__all__ = [
    "DEFAULT_RULES_PATH",
    "EXTERNAL_SINKS",
    "LOCAL_SINKS",
    "GuardrailAction",
    "GuardrailAuditRecord",
    "GuardrailAuditor",
    "GuardrailEngine",
    "GuardrailHooks",
    "GuardrailRule",
    "MergedSpan",
    "Ruleset",
    "RulesetError",
    "RulesetLoader",
    "ScanMatch",
    "ScanResult",
    "Sink",
    "SinkGuard",
    "configured_rules_path",
    "default_ruleset",
    "is_external",
    "load_ruleset",
    "merge_spans",
    "parse_ruleset",
    "register",
]
