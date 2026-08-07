"""Repository tooling: check scripts, scaffolding, and generators.

Not agent-callable, not packaged, and outside the import contracts — anything
the agent can call is a capability and lives in ``capabilities/tools/``.

This file exists so the modules here are one package rather than a namespace of
loose scripts. Several of them import each other — the drift check runs the
generator, the documentation build reads the generator's output tree — and
without it the type checker sees each file under two names at once.
"""

from __future__ import annotations
