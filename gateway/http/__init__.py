"""The HTTP surface: its security boundary, and the transports built on it.

``security/`` is here before any route is: the permission check has to be the
thing a route is wired *through*, not something added to routes afterwards.
"""

from __future__ import annotations
