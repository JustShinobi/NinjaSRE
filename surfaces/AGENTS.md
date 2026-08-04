# surfaces/ — human-facing clients

**Tier 1.** May import: everything below. Must never import: `gateway`.

The `ninjasre` CLI, the interactive REPL, and the web console's
backend-for-frontend.

## Conventions

- **Never import `gateway`.** The same peer rule, from the other side.
- Every command supports `--json`. Output degrades gracefully without colour or
  Unicode — a terminal at 03:00 is not guaranteed to be a good one.
- An approval prompt appears at the surface the human is already using
  (Article III, clause 2). It never sends them elsewhere to say yes.
- The same investigation started from any surface produces the same result and the
  same trace. A surface records where a run came in, not what it may do.

## Where things go

- Command definitions and output formatting → `cli/`.
- Stateful interactive session and slash commands → `repl/`.
- Console backend-for-frontend → `console/`.

---

Repository-wide rules — the constitution, the tier table, code style, and the
footguns — are in the root [`AGENTS.md`](../AGENTS.md). This file records only
what is specific to `surfaces/`.
