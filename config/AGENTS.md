# config/ — constants, environment names, prompts

**Tier 4.** May import: nothing first-party. Must never import: every other first-party package.

The architectural leaf. Because it imports nothing, every other tier can read
from it without creating a cycle — which is the whole reason it exists.

## Conventions

- One module per domain under `constants/`, re-exported from `constants/__init__.py`
  with an explicit `__all__`.
- Environment-variable *names* live here. Values never do: a credential is resolved
  by the vault and injected by the proxy (Article IV).
- Every constant carries a comment saying why it holds that value, not what it is
  called. `MAX_STAGNANT_ITERATIONS = 3` is obvious; why 3 is not.

## Where things go

- A new bound, cap, or budget → the domain module that owns it, never a call site.
- A new environment variable → the same, plus the operator documentation.
- Prompt text → `prompts/`, one module per prompt domain.

---

Repository-wide rules — the constitution, the tier table, code style, and the
footguns — are in the root [`AGENTS.md`](../AGENTS.md). This file records only
what is specific to `config/`.
