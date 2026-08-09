"""Turning a team's configuration into a bridge, and refusing the parts that lie.

The same shape ``platform/observation/detectors/config.py`` has, for the same
reason: a rule that was silently skipped is indistinguishable from a metrics
system with nothing in it. Errors are collected rather than raised on the first
one, so an operator who has three mistakes in a document finds out about three
of them the first time they save.

**The shipped rules are on by default and can be turned off.** A deployment that
declares its own complete set does not want the shipped Proxmox and node
exporter rules underneath, because two rules claiming one series is exactly the
ambiguity the mapping reports. Declared rules are tried first either way, so an
operator overriding one shipped rule does not have to disable the rest.

**Nothing here reaches a provider.** Resolution is a pure function of the
document: it produces rules, selectors, mappings, precedence and bounds. What
answers a query is handed in by whoever composes the deployment, which is why
this module holds no client and no endpoint beyond the host the self-hosting
check needs.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from config.constants.observability_bridge import MAX_DASHBOARD_MAPPINGS, MAX_LABEL_RULES
from platform.config_service.schema.policies import (
    DashboardMappingSettings,
    LabelRuleSettings,
    LogSelectorSettings,
    ObservabilityBridgeSettings,
    SignalPrecedenceSettings,
)
from platform.observability.logging import get_logger
from platform.observation.bridge.catalogue import (
    SHIPPED_LOG_SELECTORS,
    LogSelectorRule,
)
from platform.observation.bridge.dashboards import DashboardMapping
from platform.observation.bridge.exporters import SHIPPED_RULES
from platform.observation.bridge.mapping import LabelRule, MappingSchedule, SeriesView
from platform.observation.bridge.precedence import PrecedenceRule, SignalPrecedence

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ResolvedBridge:
    """What one node's configuration resolved to, and what it got wrong.

    Both halves, for the reason the detector resolution gives: a caller that only
    received the valid rules would have no way to surface the invalid ones, and
    an operator whose series never map deserves a reason rather than silence.
    """

    enabled: bool = False
    rules: tuple[LabelRule, ...] = ()
    log_selectors: tuple[LogSelectorRule, ...] = ()
    dashboards: tuple[DashboardMapping, ...] = ()
    precedence: SignalPrecedence = field(default_factory=SignalPrecedence)
    mapping: MappingSchedule = field(default_factory=MappingSchedule)
    history_lookback_seconds: int = 0
    log_window_seconds: int = 0
    log_line_limit: int = 0
    #: Component name to endpoint, for the check that asks whether the stack is
    #: hosted inside the estate it observes.
    endpoints: Mapping[str, str] = field(default_factory=dict)
    #: One per declaration that could not be built, as ``(identifier, reason)``.
    problems: tuple[tuple[str, str], ...] = ()

    @property
    def metrics_enabled(self) -> bool:
        """Return whether a metrics source is configured and switched on."""
        return self.enabled and "prometheus" in self.endpoints

    @property
    def logs_enabled(self) -> bool:
        """Return whether a log source is configured and switched on."""
        return self.enabled and "loki" in self.endpoints


def read(settings: ObservabilityBridgeSettings) -> ResolvedBridge:
    """Return the bridge ``settings`` declares, and the reasons for any of it it does not."""
    problems: list[tuple[str, str]] = []

    rules = _rules(settings, problems)
    selectors = _selectors(settings, problems)
    dashboards = _dashboards(settings, problems)
    precedence = _precedence(settings, problems)

    return ResolvedBridge(
        enabled=settings.enabled,
        rules=rules,
        log_selectors=selectors,
        dashboards=dashboards,
        precedence=precedence,
        mapping=MappingSchedule(interval_seconds=settings.mapping_interval_seconds),
        history_lookback_seconds=settings.history_lookback_seconds,
        log_window_seconds=settings.log_window_seconds,
        log_line_limit=settings.log_line_limit,
        endpoints=_endpoints(settings),
        problems=tuple(problems),
    )


def _endpoints(settings: ObservabilityBridgeSettings) -> dict[str, str]:
    """Return the component-to-host map the self-hosting check reads."""
    found: dict[str, str] = {}
    if settings.metrics.enabled and settings.metrics.endpoint:
        found[settings.metrics.name or "prometheus"] = settings.metrics.endpoint
    if settings.logs.enabled and settings.logs.endpoint:
        found[settings.logs.name or "loki"] = settings.logs.endpoint
    if settings.dashboard_base_url:
        found["grafana"] = settings.dashboard_base_url
    return found


def _rules(
    settings: ObservabilityBridgeSettings, problems: list[tuple[str, str]]
) -> tuple[LabelRule, ...]:
    """Return the declared rules first, then the shipped ones unless they are off."""
    declared: list[LabelRule] = []
    for entry in settings.label_rules[:MAX_LABEL_RULES]:
        try:
            declared.append(_rule_of(entry))
        except ValueError as invalid:
            problems.append((entry.rule_id, str(invalid)))
            logger.warning("bridge.rule_invalid", rule_id=entry.rule_id, reason=str(invalid))

    if len(settings.label_rules) > MAX_LABEL_RULES:
        problems.append(
            (
                "",
                f"{len(settings.label_rules)} label rules are declared and {MAX_LABEL_RULES} "
                f"is the most one deployment may hold; the rest were not loaded",
            )
        )

    shipped = SHIPPED_RULES if settings.use_shipped_rules else ()
    return (*declared, *shipped)


def _rule_of(entry: LabelRuleSettings) -> LabelRule:
    """Return the label rule ``entry`` describes, or raise naming what is wrong."""
    when: dict[str, str] = {}
    for pair in entry.when_labels:
        label, separator, value = pair.partition("=")
        if not separator or not label.strip():
            raise ValueError(
                f"when_labels entry {pair!r} is not 'label=prefix'. A condition nothing "
                f"can parse would make the rule claim every series or none."
            )
        when[label.strip()] = value
    return LabelRule(
        rule_id=entry.rule_id,
        metric_prefixes=tuple(entry.metric_prefixes),
        resource_kind=entry.resource_kind,
        integration=entry.integration,
        native_template=entry.native_template,
        when_labels=when,
        view=SeriesView(entry.view),
        description=entry.description,
    )


def _selectors(
    settings: ObservabilityBridgeSettings, problems: list[tuple[str, str]]
) -> tuple[LogSelectorRule, ...]:
    """Return the declared log selectors first, then the shipped ones unless off."""
    declared: list[LogSelectorRule] = []
    for entry in settings.log_selectors:
        try:
            declared.append(_selector_of(entry))
        except ValueError as invalid:
            problems.append((entry.rule_id, str(invalid)))

    shipped = SHIPPED_LOG_SELECTORS if settings.use_shipped_log_selectors else ()
    return (*declared, *shipped)


def _selector_of(entry: LogSelectorSettings) -> LogSelectorRule:
    """Return the log selector ``entry`` describes."""
    if not entry.template:
        raise ValueError(
            f"log selector {entry.rule_id!r} has no template, so it would query nothing "
            f"and the empty result would read as a quiet guest"
        )
    return LogSelectorRule(
        rule_id=entry.rule_id,
        resource_kind=entry.resource_kind,
        template=entry.template,
        description=entry.description,
    )


def _dashboards(
    settings: ObservabilityBridgeSettings, problems: list[tuple[str, str]]
) -> tuple[DashboardMapping, ...]:
    """Return the declared dashboard mappings, dropping the ones that resolve to nothing."""
    found: list[DashboardMapping] = []
    for entry in settings.dashboards[:MAX_DASHBOARD_MAPPINGS]:
        try:
            found.append(_dashboard_of(entry, settings.dashboard_base_url))
        except ValueError as invalid:
            problems.append((entry.dashboard_uid, str(invalid)))
    return tuple(found)


def _dashboard_of(entry: DashboardMappingSettings, fallback_url: str) -> DashboardMapping:
    """Return the dashboard mapping ``entry`` describes."""
    return DashboardMapping(
        dashboard_uid=entry.dashboard_uid,
        title=entry.title or entry.dashboard_uid,
        base_url=entry.base_url or fallback_url,
        resource_kinds=tuple(entry.resource_kinds),
        detector_ids=tuple(entry.detector_ids),
        panel_id=entry.panel_id,
        description=entry.description,
    )


def _precedence(
    settings: ObservabilityBridgeSettings, problems: list[tuple[str, str]]
) -> SignalPrecedence:
    """Return the declared precedence, dropping the rules that cannot be built."""
    rules: list[PrecedenceRule] = []
    for entry in settings.precedence:
        try:
            rules.append(_precedence_of(entry))
        except ValueError as invalid:
            problems.append((entry.signal, str(invalid)))
    try:
        return SignalPrecedence(rules=tuple(rules))
    except ValueError as invalid:
        problems.append(("", str(invalid)))
        return SignalPrecedence()


def _precedence_of(entry: SignalPrecedenceSettings) -> PrecedenceRule:
    """Return the precedence rule ``entry`` describes."""
    return PrecedenceRule(signal=entry.signal, winner=entry.winner, reason=entry.reason)


__all__ = ["ResolvedBridge", "read"]
