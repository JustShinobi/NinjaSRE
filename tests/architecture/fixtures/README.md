# Architecture fixtures

Six deliberately broken module trees, one per forbidden or independence
contract in `.importlinter`. Each tree carries all seven first-party package
names so the real contract set can be run against it unmodified, and exactly
one illegal import.

They are never imported by the real package graph: `pytest.ini` excludes this
directory via `norecursedirs`, `mypy.ini` excludes it from type checking, and
`ruff.toml` grants it the per-file ignores the violations require.

`tests/architecture/test_import_contracts.py` runs them.
