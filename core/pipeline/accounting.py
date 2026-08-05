"""Adding what one model call cost to what the run has already spent.

One function, used by the two stages that call a model directly. It exists so
those two agree: a run that counted the loop's tokens and forgot intake's
under-reports its own cost, and the cost is the number an operator uses to
decide whether this is affordable to run on every alert.
"""

from __future__ import annotations

from dataclasses import replace

from core.llm.types import InvokeResult
from core.state.slices import AccountingSlice


def account_for(accounting: AccountingSlice, result: InvokeResult) -> AccountingSlice:
    """Return ``accounting`` with ``result``'s call and tokens added.

    A failed call still counts. The provider charged for the attempt whether or
    not it came back usable, and a ledger that only records successes is a
    ledger that disagrees with the invoice.
    """
    tokens = accounting.tokens if result.usage is None else accounting.tokens + result.usage.tokens
    return replace(accounting, tokens=tokens, llm_calls=accounting.llm_calls + 1)


__all__ = ["account_for"]
