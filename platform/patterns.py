"""Compiling a regular expression somebody else wrote, without inheriting their bug.

Two parts of the platform accept patterns from outside the repository: an
operator's custom masking shapes and an operator's guardrail rules. Both run
against text an attacker can influence — a log line, an error message, a tool
result — which makes catastrophic backtracking a denial of service reachable
through *data*. There is no authentication in front of a log line.

So a pattern from outside is validated before it is ever used, in two layers,
because either alone leaves a gap.

**Structurally**, an unbounded quantifier applied to a group that already
contains one is rejected outright. ``(a+)+`` and ``(\\s*)*`` are the canonical
shape and the check is exact, deterministic, and instant.

**Empirically**, the compiled pattern is timed against short runs of its own
alphabet at increasing lengths. This is what catches the shapes a structural
check cannot name — overlapping alternations, mostly — and it costs a fraction
of a second, once, at load.

Validation happens at load and nowhere else. A pattern rejected mid-scan has
already cost the scan the time it spent backtracking, which is the entire thing
being prevented.
"""

from __future__ import annotations

import re
import time

from config.constants.security import PATTERN_VALIDATION_BUDGET_SECONDS


class UnsafePatternError(ValueError):
    """A pattern will not compile, or backtracks on adversarial input.

    Carries the name the operator gave the pattern rather than the pattern
    itself. Somebody who has just added six rules to a YAML file needs to know
    which of the six is the problem, and a regular expression quoted back at
    them does not answer that.
    """


#: Runs fed to a candidate, escalating in length. Short on purpose: the point is
#: to observe superlinear growth, and an exponential pattern at four thousand
#: characters would not return this decade.
_PROBE_LENGTHS: tuple[int, ...] = (12, 16, 20, 22)

#: The alphabets a candidate is probed over. Between them they cover the shapes
#: infrastructure identifiers and secrets are written in, which is what an
#: operator's pattern will be built out of.
_PROBE_ALPHABETS: tuple[str, ...] = ("a", "0", "-", " ", "a-", "a0", "aA0+/")

#: Quantifiers admitting unboundedly many repetitions. A bounded one cannot
#: produce exponential backtracking, which is why ``{0,63}`` is everywhere in
#: ``masking/detectors.py`` and ``*`` is nowhere.
_UNBOUNDED = frozenset({"*", "+"})


def compile_untrusted(name: str, pattern: str) -> re.Pattern[str]:
    """Return ``pattern`` compiled, or raise ``UnsafePatternError`` naming ``name``."""
    try:
        compiled = re.compile(pattern)
    except re.error as error:
        raise UnsafePatternError(f"pattern {name!r} will not compile: {error}") from error

    if has_nested_unbounded_quantifier(pattern):
        raise UnsafePatternError(
            f"pattern {name!r} applies an unbounded quantifier to a group that already "
            f"contains one, which backtracks exponentially on input that nearly matches. "
            f"Bound the inner repetition — {{1,64}} rather than + — and it becomes linear."
        )

    _reject_if_it_backtracks(name, compiled)
    return compiled


def has_nested_unbounded_quantifier(pattern: str) -> bool:
    """Return whether ``pattern`` repeats a group that itself repeats unboundedly.

    Walks the string rather than using ``re``'s parse tree, which is private and
    has changed shape between releases. The walk only has to be right about
    escapes, character classes, and balanced parentheses — all local facts.
    """
    starts: list[int] = []
    index = 0
    in_class = False

    while index < len(pattern):
        char = pattern[index]

        if char == "\\":
            index += 2
            continue
        if in_class:
            in_class = char != "]"
            index += 1
            continue
        if char == "[":
            in_class = True
            index += 1
            continue
        if char == "(":
            starts.append(index)
            index += 1
            continue
        if char == ")" and starts:
            start = starts.pop()
            if _quantifier_is_unbounded(pattern, index + 1) and _contains_unbounded_quantifier(
                pattern[start + 1 : index]
            ):
                return True
        index += 1

    return False


def _quantifier_is_unbounded(pattern: str, index: int) -> bool:
    """Return whether the quantifier at ``index`` admits unboundedly many repeats."""
    if index >= len(pattern):
        return False
    if pattern[index] in _UNBOUNDED:
        return True
    if pattern[index] != "{":
        return False
    closing = pattern.find("}", index)
    if closing == -1:
        return False
    # ``{2,}`` is unbounded; ``{2,8}`` and ``{4}`` are not.
    return pattern[index + 1 : closing].endswith(",")


def _contains_unbounded_quantifier(body: str) -> bool:
    """Return whether ``body`` holds an unbounded quantifier outside a character class."""
    index = 0
    in_class = False
    while index < len(body):
        char = body[index]
        if char == "\\":
            index += 2
            continue
        if in_class:
            in_class = char != "]"
            index += 1
            continue
        if char == "[":
            in_class = True
            index += 1
            continue
        if char in _UNBOUNDED or (char == "{" and _quantifier_is_unbounded(body, index)):
            return True
        index += 1
    return False


def _reject_if_it_backtracks(name: str, compiled: re.Pattern[str]) -> None:
    """Raise if ``compiled`` grows superlinearly on runs of its own alphabet.

    The budget is cumulative across probes rather than per probe, so a pattern
    that is merely slow at every length is caught as surely as one that explodes
    only at the last — and the whole validation stays bounded either way.
    """
    spent = 0.0
    for alphabet in _PROBE_ALPHABETS:
        for run in _PROBE_LENGTHS:
            probe = alphabet * run + "\x00"
            started = time.perf_counter()
            compiled.search(probe)
            spent += time.perf_counter() - started
            if spent > PATTERN_VALIDATION_BUDGET_SECONDS:
                raise UnsafePatternError(
                    f"pattern {name!r} spent more than {PATTERN_VALIDATION_BUDGET_SECONDS}s "
                    f"on a {run}-character run of {alphabet!r}, which means it backtracks. "
                    f"The text it would run against is a log line somebody else wrote, so a "
                    f"pattern that is slow on adversarial input is a denial of service "
                    f"reachable by writing a log message."
                )


__all__ = [
    "UnsafePatternError",
    "compile_untrusted",
    "has_nested_unbounded_quantifier",
]
