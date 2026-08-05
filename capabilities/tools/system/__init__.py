"""Vendor-free capabilities: reasoning, recall, and sandboxed computation.

These are what the per-turn reserve holds. An incident on a well-integrated
vendor produces a ranking dominated by that vendor's tools, and without a
reserve the model loses the ability to state a hypothesis or to remember a
previous incident — at exactly the point an investigation is going badly enough
to need both.

They are cheap for the same reason they are always relevant: none of them
leaves the process, so none of them can be slow, rate-limited, or unavailable
because somebody's API key expired.
"""

from __future__ import annotations
