"""What a guardrail rule is, where the operator writes it, and how it reloads.

A rule is declarative and lives in YAML at a path the operator controls. That
is not a convenience: rules get tuned *during* incidents, by whoever is on call,
and a control that needs a deployment to change is a control that gets bypassed
instead of adjusted.

Three decisions about loading are worth the sentences they cost.

**Operator rules are merged onto the shipped ones, by name.** A file that
forgets a rule does not remove it; a rule that repeats a shipped name replaces
it. That is how a shipped rule gets disabled — same name, ``enabled: false`` —
and it means an operator can never accidentally turn off the default secret
shapes by writing a file that only mentions their own.

**A parse failure keeps the previous ruleset.** Never zero rules, never the
shipped set alone if operator rules were previously good. A platform that
started unguarded because somebody left a tab in a YAML file would be a
platform whose safety property depends on nobody making a typo.

**Every pattern is validated before it is used.** Same treatment as an
operator's masking pattern, in ``platform.patterns``, and for the same reason:
the input these run against is a log line somebody else wrote.
"""

from __future__ import annotations

import os
import re
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml

from config.constants.security import (
    GUARDRAIL_ACTIONS,
    GUARDRAIL_RELOAD_INTERVAL_SECONDS,
    NINJASRE_GUARDRAIL_RULES_PATH_ENV,
    REDACTION_PLACEHOLDER,
)
from platform.observability.logging import get_logger
from platform.patterns import UnsafePatternError, compile_untrusted

logger = get_logger(__name__)

#: Where the rules NinjaSRE ships live. Beside the code because they are part of
#: it — an operator who deletes this file should get a platform that still has
#: the default secret shapes, not one that has none.
DEFAULT_RULES_PATH: Path = Path(__file__).parent / "defaults" / "rules.yml"


class GuardrailAction(StrEnum):
    """What happens when a rule matches.

    Ordered by severity in ``SEVERITY``, which is what makes overlap resolution
    answerable: a ``block`` overlapping an ``audit`` is a block, or writing a
    wide auditing rule would be a way to switch off a narrow blocking one.
    """

    AUDIT = "audit"
    REDACT = "redact"
    BLOCK = "block"


#: Least to most severe. Read by ``engine.merge_spans``.
SEVERITY: tuple[GuardrailAction, ...] = (
    GuardrailAction.AUDIT,
    GuardrailAction.REDACT,
    GuardrailAction.BLOCK,
)


class RulesetError(ValueError):
    """A ruleset document is not one.

    Distinct from a pattern failure so the loader can say whether the file is
    malformed or one rule in it is, which are different things for the person
    fixing it at three in the morning.
    """


@dataclass(frozen=True, slots=True)
class GuardrailRule:
    """One declarative rule, with its patterns already compiled.

    ``keywords`` is a cheap prefilter rather than a second matcher. A rule whose
    keywords are absent from the text cannot match, so its patterns are never
    run — which is what keeps a forty-rule ruleset affordable on a ten-megabyte
    evidence payload.
    """

    name: str
    description: str = ""
    patterns: tuple[re.Pattern[str], ...] = ()
    keywords: tuple[str, ...] = ()
    action: GuardrailAction = GuardrailAction.REDACT
    replacement: str = REDACTION_PLACEHOLDER
    enabled: bool = True

    def applies_to(self, lowered: str) -> bool:
        """Return whether this rule's patterns are worth running at all.

        ``lowered`` is the whole scanned text, lowercased once by the caller
        for the whole ruleset. Lowercasing per rule is the difference between
        one pass over ten megabytes and forty.
        """
        if not self.keywords:
            return True
        return any(keyword in lowered for keyword in self.keywords)


@dataclass(frozen=True, slots=True)
class Ruleset:
    """An ordered, immutable set of rules, and where they came from."""

    rules: tuple[GuardrailRule, ...] = ()
    source: str = ""

    @property
    def enabled(self) -> tuple[GuardrailRule, ...]:
        """Return the rules that are turned on, in declaration order."""
        return tuple(rule for rule in self.rules if rule.enabled)

    def __len__(self) -> int:
        """Return how many rules are declared, enabled or not."""
        return len(self.rules)

    def merged_with(self, override: Ruleset) -> Ruleset:
        """Return this ruleset with ``override``'s rules applied by name.

        A name that already exists is replaced in place, keeping the shipped
        ordering; a name that does not is appended. Replacing in place matters:
        an operator raising a rule's specificity should not also move it behind
        forty others and change which rule represents an overlap.
        """
        by_name = {rule.name: index for index, rule in enumerate(self.rules)}
        merged = list(self.rules)
        for rule in override.rules:
            index = by_name.get(rule.name)
            if index is None:
                by_name[rule.name] = len(merged)
                merged.append(rule)
            else:
                merged[index] = rule
        return Ruleset(rules=tuple(merged), source=override.source or self.source)


def parse_ruleset(document: str, *, source: str) -> Ruleset:
    """Return the ruleset ``document`` declares, or raise ``RulesetError``.

    Strict about shape and unforgiving about unknown keys. A ``patern:`` that
    was silently ignored would be a rule the operator believes is running and
    is not, which is worse than a file that will not load.
    """
    try:
        loaded = yaml.safe_load(document)
    except yaml.YAMLError as error:
        raise RulesetError(f"{source}: not valid YAML: {error}") from error

    if loaded is None:
        return Ruleset(source=source)
    if not isinstance(loaded, Mapping):
        raise RulesetError(f"{source}: expected a mapping at the top level")

    declared = loaded.get("rules", ())
    if not isinstance(declared, Sequence) or isinstance(declared, str):
        raise RulesetError(f"{source}: 'rules' must be a list")

    rules: list[GuardrailRule] = []
    seen: set[str] = set()
    for position, entry in enumerate(declared):
        rule = _parse_rule(entry, source=source, position=position)
        if rule.name in seen:
            raise RulesetError(f"{source}: two rules are named {rule.name!r}")
        seen.add(rule.name)
        rules.append(rule)

    return Ruleset(rules=tuple(rules), source=source)


_ALLOWED_KEYS = frozenset(
    {"name", "description", "patterns", "keywords", "action", "replacement", "enabled"}
)


def _parse_rule(entry: Any, *, source: str, position: int) -> GuardrailRule:
    """Return one rule from one YAML mapping, or raise ``RulesetError``."""
    where = f"{source}: rule {position}"
    if not isinstance(entry, Mapping):
        raise RulesetError(f"{where} is not a mapping")

    unknown = set(entry) - _ALLOWED_KEYS
    if unknown:
        raise RulesetError(
            f"{where}: unknown field(s) {', '.join(sorted(map(str, unknown)))}. "
            f"A field nobody reads is a rule the operator believes is running and is not."
        )

    name = entry.get("name")
    if not isinstance(name, str) or not name.strip():
        raise RulesetError(f"{where} has no name")
    name = name.strip()

    action_name = entry.get("action", GuardrailAction.REDACT.value)
    if action_name not in GUARDRAIL_ACTIONS:
        raise RulesetError(
            f"{source}: rule {name!r} declares action {action_name!r}; "
            f"expected one of {', '.join(GUARDRAIL_ACTIONS)}"
        )

    raw_patterns = entry.get("patterns", ())
    if isinstance(raw_patterns, str) or not isinstance(raw_patterns, Sequence):
        raise RulesetError(f"{source}: rule {name!r} needs 'patterns' as a list")
    if not raw_patterns:
        raise RulesetError(
            f"{source}: rule {name!r} declares no patterns, so it can never match. "
            f"Delete it, or set 'enabled: false' if it is being kept for later."
        )

    compiled: list[re.Pattern[str]] = []
    for index, pattern in enumerate(raw_patterns):
        if not isinstance(pattern, str):
            raise RulesetError(f"{source}: rule {name!r} pattern {index} is not a string")
        try:
            compiled.append(compile_untrusted(f"{name}[{index}]", pattern))
        except UnsafePatternError as error:
            raise RulesetError(f"{source}: {error}") from error

    keywords = entry.get("keywords", ())
    if isinstance(keywords, str) or not isinstance(keywords, Iterable):
        raise RulesetError(f"{source}: rule {name!r} needs 'keywords' as a list")

    replacement = entry.get("replacement", REDACTION_PLACEHOLDER)
    if not isinstance(replacement, str):
        raise RulesetError(f"{source}: rule {name!r} has a non-string replacement")

    description = entry.get("description", "")
    if not isinstance(description, str):
        raise RulesetError(f"{source}: rule {name!r} has a non-string description")

    return GuardrailRule(
        name=name,
        description=description,
        patterns=tuple(compiled),
        keywords=tuple(str(keyword).lower() for keyword in keywords),
        action=GuardrailAction(action_name),
        replacement=replacement,
        enabled=bool(entry.get("enabled", True)),
    )


def load_ruleset(path: Path) -> Ruleset:
    """Return the ruleset at ``path``, or raise ``RulesetError``."""
    try:
        document = path.read_text(encoding="utf-8")
    except OSError as error:
        raise RulesetError(f"{path}: cannot be read: {error}") from error
    return parse_ruleset(document, source=str(path))


_DEFAULTS: Ruleset | None = None


def default_ruleset() -> Ruleset:
    """Return the rules NinjaSRE ships, parsed once and shared.

    Cached because the result is immutable and parsing it compiles thirty-odd
    patterns, each of which is validated against the backtracking probes. Paying
    that per ``GuardrailEngine`` would be paying it per investigation.
    """
    global _DEFAULTS
    if _DEFAULTS is None:
        _DEFAULTS = load_ruleset(DEFAULT_RULES_PATH)
    return _DEFAULTS


def configured_rules_path() -> Path | None:
    """Return the operator's rules path, or ``None`` if none is configured."""
    configured = os.environ.get(NINJASRE_GUARDRAIL_RULES_PATH_ENV, "").strip()
    return Path(configured) if configured else None


@dataclass(slots=True)
class RulesetLoader:
    """The live ruleset, reloaded when its file changes, never left empty.

    Reload is a modification-time poll on read rather than a watcher thread.
    Two reasons, and the second is the one that decided it: a ``stat`` is
    cheaper than a thread, and a poll is *deterministic in a test* — a watcher's
    delivery latency is not, and a test that sleeps hoping the event arrived is
    a test that fails on somebody else's machine.
    """

    path: Path | None = None
    base: Ruleset = field(default_factory=default_ruleset)
    reload_interval: float = GUARDRAIL_RELOAD_INTERVAL_SECONDS
    clock: Callable[[], float] = time.monotonic

    _current: Ruleset = field(init=False, repr=False, default=Ruleset())
    _fingerprint: tuple[int, int] | None = field(init=False, repr=False, default=None)
    _checked_at: float = field(init=False, repr=False, default=0.0)
    _last_error: str = field(init=False, repr=False, default="")
    _reloads: int = field(init=False, repr=False, default=0)

    def __post_init__(self) -> None:
        self._current = self.base
        self._checked_at = self.clock()
        self._load()

    @property
    def last_error(self) -> str:
        """Return the most recent load failure, or the empty string.

        Kept rather than only logged, because the console and the health check
        both need to be able to say "your rules are stale and here is why" —
        a log line that scrolled past is not an answer to that.
        """
        return self._last_error

    @property
    def reloads(self) -> int:
        """Return how many times the file has been successfully re-read."""
        return self._reloads

    def current(self) -> Ruleset:
        """Return the live ruleset, reloading first if the file has changed."""
        if self.path is None:
            return self._current
        now = self.clock()
        if now - self._checked_at < self.reload_interval:
            return self._current
        self._checked_at = now
        self._load()
        return self._current

    def reload(self) -> Ruleset:
        """Re-read the file now, whatever the interval says, and return the result."""
        self._checked_at = self.clock()
        self._load()
        return self._current

    def _load(self) -> None:
        """Read the file if it has changed, keeping the last known good set."""
        if self.path is None:
            return

        try:
            stat = self.path.stat()
        except OSError as error:
            # A file that has never loaded and is not there is not a failure:
            # an operator who has written no rules gets the shipped set, which
            # is the right answer rather than an error to be dismissed on every
            # start. A file that *was* loaded and has since vanished is a
            # failure, because somebody's rules just stopped applying.
            if self._fingerprint is not None:
                self._fail(f"{self.path}: {error}")
            return

        fingerprint = (stat.st_mtime_ns, stat.st_size)
        if fingerprint == self._fingerprint:
            return

        try:
            override = load_ruleset(self.path)
        except RulesetError as error:
            self._fail(str(error))
            return

        self._fingerprint = fingerprint
        self._current = self.base.merged_with(override)
        self._last_error = ""
        self._reloads += 1
        logger.info(
            "guardrails.ruleset_loaded",
            source=str(self.path),
            rules=len(self._current),
            enabled=len(self._current.enabled),
        )

    def _fail(self, detail: str) -> None:
        """Record a load failure loudly, and keep the rules that were working."""
        self._last_error = detail
        logger.error(
            "guardrails.ruleset_rejected",
            source=str(self.path),
            error=detail,
            retained_rules=len(self._current),
        )


__all__ = [
    "DEFAULT_RULES_PATH",
    "SEVERITY",
    "GuardrailAction",
    "GuardrailRule",
    "Ruleset",
    "RulesetError",
    "RulesetLoader",
    "configured_rules_path",
    "default_ruleset",
    "load_ruleset",
    "parse_ruleset",
]
