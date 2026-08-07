"""Fitting a report to a destination that will not take all of it.

The rule is one sentence: **summarised with a link, never truncated**. A cut
report is indistinguishable from a short one, so the reader never learns that the
section answering their question was the part that did not fit — and the sections
at the end are "what was ruled out" and "how this was investigated", which are
precisely the ones somebody goes looking for.

That property is structural rather than promised. A formatter hands over its
body *and its blocks*, and shortening happens by dropping whole blocks: there is
no code path here that slices a string of report content at an arbitrary offset.

The degradation is ordered. Everything but the conclusion and the actions goes
first; then the actions; then the summary; and what is left when even that will
not fit is the title and the link, which is still a delivery somebody can follow.
"""

from __future__ import annotations

from config.constants.notifications import REPORT_SUMMARY_BUDGET_RATIO, REPORT_SUMMARY_NOTICE
from platform.reporting.formatters.sections import (
    SECTION_ACTIONS,
    SECTION_ROOT_CAUSE,
    SECTION_SUMMARY,
)
from platform.reporting.models import Destination, FormattedReport

#: The blocks a summary keeps, most important first. Order is the order they are
#: given up in, reversed: the root cause is the last thing to go.
SUMMARY_BLOCK_KEYS: tuple[str, ...] = (
    "headline",
    SECTION_ROOT_CAUSE,
    SECTION_SUMMARY,
    SECTION_ACTIONS,
)


def fit_to_destination(
    formatted: FormattedReport, destination: Destination, *, link: str
) -> FormattedReport:
    """Return ``formatted`` as ``destination`` can accept it.

    Returns the rendering unchanged when it already fits. Otherwise returns a
    summary carrying ``link``, marked ``summarised`` so nothing downstream can
    mistake it for a report that had nothing more to say.
    """
    limit = destination.size_limit
    if formatted.length <= limit:
        return formatted

    notice = f"{REPORT_SUMMARY_NOTICE} {link}".strip() if link else REPORT_SUMMARY_NOTICE
    budget = min(limit, max(int(limit * REPORT_SUMMARY_BUDGET_RATIO), len(notice)))

    kept = [block for block in formatted.blocks if block.key in SUMMARY_BLOCK_KEYS]
    while kept:
        body = "\n\n".join([*(block.text for block in kept), notice])
        if len(body) <= budget:
            return formatted.with_body(body, summarised=True)
        kept.pop()

    return formatted.with_body(_last_resort(formatted.title, notice, link, limit), summarised=True)


def _last_resort(title: str, notice: str, link: str, limit: int) -> str:
    """Return the shortest delivery that is still a pointer at the whole report.

    Three forms, each a complete thing rather than a piece of a longer one: the
    title with the notice, the notice alone, and — for a destination whose limit
    is under the length of an English sentence — the link by itself.
    """
    for candidate in (f"{title}\n\n{notice}", notice, link):
        if len(candidate) <= limit:
            return candidate
    return link


__all__ = ["SUMMARY_BLOCK_KEYS", "fit_to_destination"]
