"""The run-scoped table that makes masking reversible, and is itself a secret.

Two properties, and they pull in opposite directions.

**Stable.** The same identifier gets the same token every time it is seen, in
every evidence source, for the whole run. Random per-occurrence tokens would be
marginally safer and would destroy the product: correlating one pod across a
metrics query and a log query *is* the investigation, and a model cannot
correlate two names it has no reason to think are the same thing.

**Sensitive.** A mapping is the key to every token that was ever sent. It never
goes to a provider, never appears in a report, and never appears in a log line
or a traceback — which is why ``__repr__`` is overridden rather than left to
the dataclass. A repr that dumps the table is how it ends up in an exception
somebody pasted into a ticket.

Tokens are ``NSRE_MASK_<KIND>_<n>``. The kind is in there because the model
reasons better about ``NSRE_MASK_POD_3`` than about ``NSRE_MASK_3``; the prefix
is there because it has to be a string that never occurs in real infrastructure
output, and ``tests/unit/platform/masking`` checks that against the evidence
corpus.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from config.constants.security import MASK_TOKEN_PREFIX, MASK_TOKEN_SEPARATOR

#: Matches any token this module issues. Anchored on the prefix and bounded, so
#: it is safe to run over model output, which is the one input nobody controls.
TOKEN_PATTERN: re.Pattern[str] = re.compile(
    rf"{re.escape(MASK_TOKEN_PREFIX)}[A-Z0-9_]{{1,64}}{re.escape(MASK_TOKEN_SEPARATOR)}[0-9]{{1,6}}"
)


@dataclass(slots=True)
class MaskMapping:
    """One run's bidirectional identifier-to-token table.

    Mutable, unlike most things here, because allocation happens as text is
    masked and a frozen table would mean rebuilding the whole thing per
    evidence item. It is owned by exactly one ``MaskingContext``, which is what
    keeps that mutability from being shared state.
    """

    _tokens: dict[str, str] = field(default_factory=dict, repr=False)
    _values: dict[str, str] = field(default_factory=dict, repr=False)
    _counters: dict[str, int] = field(default_factory=dict, repr=False)

    def token_for(self, label: str, value: str) -> str:
        """Return the token for ``value``, allocating one on first sight.

        Idempotent by construction: a second call with the same value returns
        the same token, which is the whole of the stability guarantee.
        """
        existing = self._tokens.get(value)
        if existing is not None:
            return existing

        ordinal = self._counters.get(label, 0) + 1
        self._counters[label] = ordinal
        token = f"{MASK_TOKEN_PREFIX}{label}{MASK_TOKEN_SEPARATOR}{ordinal}"
        self._tokens[value] = token
        self._values[token] = value
        return token

    def value_for(self, token: str) -> str | None:
        """Return the identifier ``token`` stands for, or ``None``.

        ``None`` rather than the token itself, so a caller has to decide what an
        unknown token means. A model that invented ``NSRE_MASK_POD_99`` must not
        have it silently resolved to some other pod — leaving it visibly
        unresolved is the only honest answer.
        """
        return self._values.get(token)

    def entries(self) -> Mapping[str, str]:
        """Return a copy of the token-to-identifier table.

        A copy, so a caller holding it cannot grow the run's mapping. This is
        the sensitive half; the caller that asks for it is the one persisting
        the run, and there is no other legitimate reason to want it.
        """
        return dict(self._values)

    def counts_by_kind(self) -> Mapping[str, int]:
        """Return how many identifiers of each kind were masked.

        This is the shape that is safe everywhere — a trace line, a log, a
        console panel — because a count says masking worked without saying what
        it hid.
        """
        return dict(self._counters)

    def __len__(self) -> int:
        """Return how many distinct identifiers have been masked."""
        return len(self._tokens)

    def __repr__(self) -> str:
        """Return a description that names no identifier.

        Overridden rather than inherited. The dataclass default would print the
        whole table, and the place a repr surfaces is a traceback — which is
        the place a mapping must least of all be.
        """
        return f"MaskMapping(entries={len(self._tokens)})"


__all__ = ["TOKEN_PATTERN", "MaskMapping"]
