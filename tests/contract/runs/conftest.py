"""Fixture discovery for this directory: re-exports ``deployment`` from ``_deployment``.

Kept separate from ``_deployment.py`` itself so the shared helpers
(``ORG``, ``TEAM``, ``Deployment``, ``bearer``) live in a module test files
import explicitly and by full path — a bare ``from conftest import ...``
elsewhere in the suite resolves to whichever ``conftest.py`` Python's import
cache saw first, and a second module also named ``conftest`` is how that
breaks. This file exists only so pytest's own fixture discovery finds
``deployment`` without every test file repeating the import.
"""

from __future__ import annotations

from tests.contract.runs._deployment import deployment

__all__ = ["deployment"]
