"""Supabase's agent-callable capabilities.

2, and the set is the methodology rather than the API surface.
Supabase has many more endpoints than this; what an investigation needs is
the shape of the answer and then a handful of records, in that order, and a
package offering both makes the wrong order possible while a package offering
only the second makes it inevitable.

Discovery walks this package, so adding a capability is one module and no edit
anywhere else.
"""

from __future__ import annotations

from integrations.supabase.tools.session_statistics import supabase_session_statistics
from integrations.supabase.tools.slow_queries import supabase_slow_queries

__all__ = [
    "supabase_session_statistics",
    "supabase_slow_queries",
]
