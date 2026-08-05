"""The six stages, each a pure ``async (state) -> updates`` function.

Grouped by what they own rather than by what they touch. ``intake`` and
``diagnose`` are packages because each is several decisions — classification,
the window, deduplication; the structured call, validation, the fallback — and
the rest are modules because each is one.
"""

from __future__ import annotations
