"""Measuring what a catalogue entry costs to keep in context.

The budgets in this feature are enforced by a test on every build, and a build
must not need a configured provider to run — so the default counter is the
character estimate, which is deterministic, offline, and consistently a little
pessimistic on English prose.

Where a provider is configured, its tokeniser is the better answer and the
caller passes it in. Both go through the same ``TokenCounter`` shape so a budget
measured one way and enforced the other cannot drift apart unnoticed.
"""

from __future__ import annotations

from collections.abc import Callable

from config.constants.llm import CHARACTERS_PER_TOKEN_ESTIMATE

#: Anything that can price a string. The provider clients satisfy it via a
#: one-line adapter; the default below satisfies it with arithmetic.
TokenCounter = Callable[[str], int]


def estimate_tokens(text: str) -> int:
    """Return an offline estimate of what ``text`` costs, rounded up.

    Rounded up rather than down because this number is compared against a
    ceiling. Rounding toward the budget would let a catalogue drift over it one
    entry at a time, with each individual entry measuring as compliant.
    """
    if not text:
        return 0
    return -(-len(text) // CHARACTERS_PER_TOKEN_ESTIMATE)


__all__ = [
    "TokenCounter",
    "estimate_tokens",
]
