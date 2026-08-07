"""Test doubles shared by more than one suite.

Not fixtures — a ``conftest.py`` reaches one directory tree, and the surfaces
are exercised from ``tests/unit``, ``tests/contract``, and ``tests/security``.
What lives here is importable from all three, and each declares its own
fixtures over it.
"""

from __future__ import annotations
