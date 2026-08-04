# platform/ — cross-cutting services

**Tier 3.** May import: `config`, `core`. Must never import: `capabilities`, `integrations`, `gateway`, `surfaces`.

Persistence, the credential vault and proxy, the guardrail engine, masking, the
sandbox, memory stores, the knowledge graph, the scheduler, notifications,
identity, reporting delivery, and observability. No investigation logic.

## Conventions

- **This package deliberately shadows the stdlib `platform` module.** It re-exports
  the whole stdlib API so third-party callers are unaffected. Read the footgun in
  the root `AGENTS.md` before touching `__init__.py`.
- No SQL and no Cypher outside `persistence/`. Everything else reaches storage
  through a repository port (Article XI).
- Logging is configured once, in `observability/logging.py`. No other module calls
  `structlog.configure` or `logging.basicConfig`, and a test enforces it.
- This package is the trust boundary. Code here sees credentials; code above it
  never does (Article IV).

## Where things go

- A repository port and its Postgres implementation → `persistence/`.
- Anything that touches a secret → `credentials/`, behind the proxy.
- A service the agent uses but does not reason about → its own subpackage here,
  not into `core/`.

---

Repository-wide rules — the constitution, the tier table, code style, and the
footguns — are in the root [`AGENTS.md`](../AGENTS.md). This file records only
what is specific to `platform/`.
