"""``python -m tools.mockplane`` — the one command this tooling is driven by."""

from __future__ import annotations

from tools.mockplane.cli import main

if __name__ == "__main__":  # pragma: no cover — the module entry point
    raise SystemExit(main())
