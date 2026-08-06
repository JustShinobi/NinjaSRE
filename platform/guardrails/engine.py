"""Scanning, merging, and the three things a match can cause.

The engine is one pass per enabled rule over one bounded input, followed by one
merge. Everything interesting is in the merge, because overlapping matches are
the normal case rather than the exception: a connection string matches the
connection-string rule, and the password inside it matches the generic-secret
rule, and redacting them independently produces
``postgres://user:[REDACTED]@[REDACTED]`` — two placeholders where there should
be one, and the shape of the URL still leaking.

**Merging.** Overlapping spans collapse into their union. The union's
*representative rule* is the widest individual contributing match, ties broken
by earliest start and then rule name — deterministic, so the same text produces
the same audit line on every machine and in every process. The union's *action*
is the most severe among its contributors, resolved separately, so a narrow
``block`` cannot be neutralised by writing a wide ``audit`` over it.

**Bounds.** ``MAX_SCAN_INPUT_BYTES`` and ``MAX_SCAN_MATCHES``, both recorded on
the result when they bite. A scan that quietly stopped looking is
indistinguishable from a scan that found nothing, and the difference is the
whole value of the control.

**Audit-only mode.** Every action downgrades to ``audit``: nothing is altered,
nothing is blocked, everything is still recorded. That is what the ablation
switch flips, and it is why "turn guardrails off" never means "find out
nothing" — the constitution's claim is that the engine cannot be removed from
the boundary, and this is how that claim survives an ablation.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from config.constants.security import MAX_SCAN_INPUT_BYTES, MAX_SCAN_MATCHES
from platform.guardrails.rules import (
    SEVERITY,
    GuardrailAction,
    Ruleset,
    RulesetLoader,
    default_ruleset,
)


@dataclass(frozen=True, slots=True)
class ScanMatch:
    """One rule matching one span.

    Carries the replacement rather than a reference to the rule, so a result can
    be recorded, logged, and compared without keeping a compiled pattern alive
    and without a merge having to look anything up.
    """

    rule: str
    action: GuardrailAction
    start: int
    end: int
    replacement: str

    @property
    def length(self) -> int:
        """Return how many characters this match covers."""
        return self.end - self.start


@dataclass(frozen=True, slots=True)
class MergedSpan:
    """A run of overlapping matches, collapsed, with one rule's name on it."""

    start: int
    end: int
    action: GuardrailAction
    rule: str
    replacement: str

    @property
    def length(self) -> int:
        """Return how many characters this span covers."""
        return self.end - self.start


@dataclass(frozen=True, slots=True)
class ScanResult:
    """What one scan found, and what the text looks like afterwards."""

    text: str
    matches: tuple[ScanMatch, ...] = ()
    spans: tuple[MergedSpan, ...] = ()
    blocked: bool = False
    blocking_rules: tuple[str, ...] = ()
    truncated: bool = False
    match_limit_reached: bool = False

    @property
    def clean(self) -> bool:
        """Return whether nothing matched at all."""
        return not self.matches

    @property
    def rules_fired(self) -> tuple[str, ...]:
        """Return the distinct rule names that matched, in first-seen order."""
        seen: dict[str, None] = {}
        for match in self.matches:
            seen.setdefault(match.rule, None)
        return tuple(seen)

    def denial_reason(self) -> str:
        """Return the sentence a blocked operation reports.

        Names the rules and says what to do; never quotes the match. A denial
        that echoed the matched text back would put the secret in the model's
        transcript, which is where the block was trying to keep it out of.
        """
        rules = ", ".join(self.blocking_rules)
        return (
            f"A guardrail rule refused this content: {rules}. The matched text is not "
            f"reproduced here, and repeating the call unchanged will be refused again. "
            f"Reach the same information without the blocked content, or ask an operator "
            f"to review the rule."
        )


def merge_spans(matches: tuple[ScanMatch, ...]) -> tuple[MergedSpan, ...]:
    """Return ``matches`` collapsed into non-overlapping spans, deterministically.

    A function rather than a method, because the determinism is the property
    worth testing and a free function is testable without an engine, a ruleset,
    or a file.
    """
    if not matches:
        return ()

    ordered = sorted(matches, key=lambda match: (match.start, -match.length, match.rule))
    merged: list[MergedSpan] = []
    group: list[ScanMatch] = [ordered[0]]
    end = ordered[0].end

    for match in ordered[1:]:
        # Strictly less than: touching is not overlapping. Merging ``[0,5)``
        # with ``[5,9)`` would report two unrelated rules as one match, and the
        # operator would go looking for a match that never existed.
        if match.start < end:
            group.append(match)
            end = max(end, match.end)
            continue
        merged.append(_collapse(group, end))
        group = [match]
        end = match.end

    merged.append(_collapse(group, end))
    return tuple(merged)


def _collapse(group: list[ScanMatch], end: int) -> MergedSpan:
    """Return the span ``group`` collapses to, attributed and classified."""
    representative = min(group, key=lambda match: (-match.length, match.start, match.rule))
    action = max(group, key=lambda match: SEVERITY.index(match.action)).action
    return MergedSpan(
        start=group[0].start,
        end=end,
        action=action,
        rule=representative.rule,
        replacement=representative.replacement,
    )


class GuardrailEngine:
    """The scan every boundary calls, over whichever ruleset is live.

    Holds a *source* of rules rather than a ruleset, so a hot reload takes
    effect on the next scan without anything having to be rebuilt or told.
    """

    __slots__ = ("_audit_only", "_source")

    def __init__(
        self,
        *,
        ruleset: Ruleset | RulesetLoader | None = None,
        audit_only: bool = False,
    ) -> None:
        self._source: Callable[[], Ruleset]
        if ruleset is None:
            self._source = default_ruleset
        elif isinstance(ruleset, RulesetLoader):
            self._source = ruleset.current
        else:
            fixed = ruleset
            self._source = lambda: fixed
        self._audit_only = audit_only

    @classmethod
    def observing(cls, *, ruleset: Ruleset | RulesetLoader | None = None) -> GuardrailEngine:
        """Return an engine that records what would have matched and alters nothing.

        This is the ablation's "off", and it is deliberately not "no engine".
        An operator who disables guardrails still gets the audit trail saying
        what the enabled ruleset would have caught, which is what makes turning
        them back on an informed decision rather than a hunch.
        """
        return cls(ruleset=ruleset, audit_only=True)

    @property
    def ruleset(self) -> Ruleset:
        """Return the ruleset that would be used for the next scan."""
        return self._source()

    @property
    def audit_only(self) -> bool:
        """Return whether this engine observes without altering or blocking."""
        return self._audit_only

    def scan(self, text: str) -> ScanResult:
        """Return what the live ruleset finds in ``text``, and the resulting text."""
        if not text:
            return ScanResult(text=text)

        scanned, truncated = _bounded(text)
        matches, limited = self._collect(scanned)
        if not matches:
            return ScanResult(text=text, truncated=truncated, match_limit_reached=limited)

        spans = merge_spans(matches)
        blocking = tuple(
            dict.fromkeys(span.rule for span in spans if span.action is GuardrailAction.BLOCK)
        )
        rewritten = _apply(scanned, spans) + text[len(scanned) :]

        return ScanResult(
            text=rewritten,
            matches=matches,
            spans=spans,
            blocked=bool(blocking),
            blocking_rules=blocking,
            truncated=truncated,
            match_limit_reached=limited,
        )

    def _collect(self, text: str) -> tuple[tuple[ScanMatch, ...], bool]:
        """Return every match in ``text``, capped, and whether the cap was hit."""
        lowered = text.lower()
        found: list[ScanMatch] = []

        for rule in self.ruleset.enabled:
            if not rule.applies_to(lowered):
                continue
            action = GuardrailAction.AUDIT if self._audit_only else rule.action
            for pattern in rule.patterns:
                for match in pattern.finditer(text):
                    start, end = match.span()
                    if start == end:
                        continue
                    found.append(
                        ScanMatch(
                            rule=rule.name,
                            action=action,
                            start=start,
                            end=end,
                            replacement=rule.replacement,
                        )
                    )
                    if len(found) >= MAX_SCAN_MATCHES:
                        return tuple(found), True

        return tuple(found), False


def _bounded(text: str) -> tuple[str, bool]:
    """Return ``text`` cut to the scan ceiling, and whether it was cut.

    The ceiling is in bytes because that is what an operator budgets in, but
    the cut is made in characters — slicing UTF-8 by byte offset can land
    mid-codepoint, and the patterns would then be run against a string that is
    not the text. One character is never more than four bytes, so cutting at
    the byte ceiling's worth of characters is always within it.
    """
    if len(text) <= MAX_SCAN_INPUT_BYTES and len(text.encode("utf-8")) <= MAX_SCAN_INPUT_BYTES:
        return text, False
    return text[:MAX_SCAN_INPUT_BYTES], True


def _apply(text: str, spans: tuple[MergedSpan, ...]) -> str:
    """Return ``text`` with every altering span replaced.

    Built from slices in one left-to-right pass. Replacing in place would shift
    every subsequent offset, and the offsets were computed against the original.
    """
    pieces: list[str] = []
    cursor = 0
    for span in spans:
        if span.action is GuardrailAction.AUDIT:
            continue
        pieces.append(text[cursor : span.start])
        pieces.append(span.replacement)
        cursor = span.end
    if not pieces:
        return text
    pieces.append(text[cursor:])
    return "".join(pieces)


__all__ = [
    "GuardrailEngine",
    "MergedSpan",
    "ScanMatch",
    "ScanResult",
    "merge_spans",
]
