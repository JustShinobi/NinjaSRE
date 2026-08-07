"""Anonymisation: replace identity, keep everything else, and keep the awkwardness.

It would be easy to normalise while renaming — round the percentages, even out
the node balance, drop the failed units — and it would destroy the entire reason
for capturing a real deployment. The rule is the opposite: shape, scale,
distribution and the awkward cases survive intact, and only identity is
replaced.
"""

from __future__ import annotations

__all__: list[str] = []
