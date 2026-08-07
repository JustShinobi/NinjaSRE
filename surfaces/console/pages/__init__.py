"""One module per area of the console, each returning a tree rather than a string.

A page builder takes a ``PageContext`` — who is looking, and where they are —
plus whatever the API answered, and returns an ``Element``. It makes no request
of its own: fetching is ``app.py``'s job, so a page can be rendered in a test
from a literal payload and asserted on without a deployment behind it.

That separation is also what makes the role matrix possible. Walking every page
as every role means calling every builder with every viewer, which is cheap when
a builder is a pure function of its arguments and impossible when it is not.
"""

from __future__ import annotations

__all__: list[str] = []
