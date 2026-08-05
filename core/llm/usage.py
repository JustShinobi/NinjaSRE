"""Token counts and money, recorded per call and summed per turn and per run.

Two rules carry the weight here.

**An unpriced call costs ``None``, never zero.** A locally hosted model has no
published price, and a model whose pricing nobody has filled in has an unknown
one. Reporting either as ``0.0`` produces a run total that looks authoritative
and is wrong, which is worse than a total that says how much of itself it could
not price.

**An estimate says so.** Providers omit usage on some streamed responses, and
the fallback is a character-count estimate. It is carried as an estimate all the
way to the ledger so no report presents it as measured.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import date

from config.constants.llm import TOKENS_PER_PRICING_UNIT


@dataclass(frozen=True, slots=True)
class Pricing:
    """Published price per million tokens.

    ``cached_input_per_million`` and ``cache_write_per_million`` are separate
    rather than derived: providers apply different multipliers, and a cache
    write costs *more* than an uncached token, which a single ratio hides.
    """

    input_per_million: float
    output_per_million: float
    cached_input_per_million: float | None = None
    cache_write_per_million: float | None = None
    reasoning_per_million: float | None = None

    def effective_cached_input(self) -> float:
        """Return the cached-read price, defaulting to the uncached price."""
        if self.cached_input_per_million is None:
            return self.input_per_million
        return self.cached_input_per_million

    def effective_cache_write(self) -> float:
        """Return the cache-write price, defaulting to the uncached price."""
        if self.cache_write_per_million is None:
            return self.input_per_million
        return self.cache_write_per_million

    def effective_reasoning(self) -> float:
        """Return the reasoning-token price, which is billed as output by default."""
        if self.reasoning_per_million is None:
            return self.output_per_million
        return self.reasoning_per_million


@dataclass(frozen=True, slots=True)
class TokenCounts:
    """What one call consumed.

    ``input_tokens`` counts only the uncached remainder: total prompt size is
    the sum of the three input fields. Adding cached reads back into
    ``input_tokens`` double-counts them, which is the mistake that makes a
    cached run look more expensive than an uncached one.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0
    estimated: bool = False

    @property
    def total_input_tokens(self) -> int:
        """Return every prompt token, cached or not."""
        return self.input_tokens + self.cached_input_tokens + self.cache_write_tokens

    @property
    def total_tokens(self) -> int:
        """Return every token the call touched."""
        return self.total_input_tokens + self.output_tokens

    def __add__(self, other: TokenCounts) -> TokenCounts:
        """Return the sum, estimated when either side was."""
        return TokenCounts(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cached_input_tokens=self.cached_input_tokens + other.cached_input_tokens,
            cache_write_tokens=self.cache_write_tokens + other.cache_write_tokens,
            reasoning_tokens=self.reasoning_tokens + other.reasoning_tokens,
            estimated=self.estimated or other.estimated,
        )


def compute_cost(tokens: TokenCounts, pricing: Pricing | None) -> float | None:
    """Return the cost of ``tokens`` in US dollars, or ``None`` when unpriced.

    Reasoning tokens are billed by every provider that reports them as part of
    the output count, so they are only charged separately when the descriptor
    gives them their own rate.
    """
    if pricing is None:
        return None

    per_unit = float(TOKENS_PER_PRICING_UNIT)
    billable_output = tokens.output_tokens
    cost = (
        tokens.input_tokens * pricing.input_per_million
        + tokens.cached_input_tokens * pricing.effective_cached_input()
        + tokens.cache_write_tokens * pricing.effective_cache_write()
        + billable_output * pricing.output_per_million
    ) / per_unit

    if pricing.reasoning_per_million is not None:
        cost += tokens.reasoning_tokens * pricing.reasoning_per_million / per_unit

    return cost


@dataclass(frozen=True, slots=True)
class UsageRecord:
    """What one call consumed, and what it cost, if that is knowable."""

    provider_id: str
    model_id: str
    tokens: TokenCounts = field(default_factory=TokenCounts)
    cost_usd: float | None = None
    pricing_as_of: date | None = None

    @property
    def is_priced(self) -> bool:
        """Return whether a cost could be computed for this call."""
        return self.cost_usd is not None

    @classmethod
    def priced(
        cls,
        *,
        provider_id: str,
        model_id: str,
        tokens: TokenCounts,
        pricing: Pricing | None,
        pricing_as_of: date | None = None,
    ) -> UsageRecord:
        """Return a record with its cost computed from ``pricing``."""
        return cls(
            provider_id=provider_id,
            model_id=model_id,
            tokens=tokens,
            cost_usd=compute_cost(tokens, pricing),
            pricing_as_of=pricing_as_of,
        )

    def with_tokens(self, tokens: TokenCounts, pricing: Pricing | None) -> UsageRecord:
        """Return a copy carrying ``tokens`` and the cost they imply."""
        return replace(self, tokens=tokens, cost_usd=compute_cost(tokens, pricing))


@dataclass(slots=True)
class UsageLedger:
    """Accumulates records at one scope — a turn, or a whole run.

    Deliberately mutable and deliberately not thread-safe: a ledger belongs to
    one turn or one run, and sharing one across concurrent turns is the bug it
    would otherwise hide.
    """

    scope: str = "run"
    records: list[UsageRecord] = field(default_factory=list)

    def add(self, record: UsageRecord | None) -> None:
        """Record one call. ``None`` is ignored so callers need no guard."""
        if record is not None:
            self.records.append(record)

    def extend(self, records: Iterable[UsageRecord]) -> None:
        """Record several calls."""
        for record in records:
            self.add(record)

    @property
    def call_count(self) -> int:
        """Return how many calls this ledger covers."""
        return len(self.records)

    @property
    def tokens(self) -> TokenCounts:
        """Return the token total across every recorded call."""
        total = TokenCounts()
        for record in self.records:
            total = total + record.tokens
        return total

    @property
    def cost_usd(self) -> float:
        """Return the cost of the calls that could be priced.

        Read this with ``unpriced_call_count``. On its own it is a floor, not a
        total, and presenting it as a total is how an unpriced provider comes to
        look free.
        """
        return sum(record.cost_usd or 0.0 for record in self.records)

    @property
    def unpriced_call_count(self) -> int:
        """Return how many calls had no published price."""
        return sum(1 for record in self.records if not record.is_priced)

    @property
    def is_complete(self) -> bool:
        """Return whether every recorded call carries a measured, priced usage."""
        return self.unpriced_call_count == 0 and not self.tokens.estimated


__all__ = [
    "Pricing",
    "TokenCounts",
    "UsageLedger",
    "UsageRecord",
    "compute_cost",
]
