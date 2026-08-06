# gateway/ — inbound transports

**Tier 1.** May import: everything below. Must never import: `surfaces`.

The REST and SSE server, alert webhook ingestion, and the chat platforms:
Slack, Microsoft Teams, Telegram, and Discord.

## Conventions

- **Never import `surfaces`.** The two tier 1 packages are peers; shared behaviour
  belongs to a lower tier, not to a sideways import.
- A webhook is untrusted until its signature verifies, and deduplicated before it
  starts an investigation.
- Load shedding is reported, never silent. An operator must be able to see exactly
  what was not investigated, and why.
- A transport translates and authorises. It does not decide what an investigation
  does.

## The permission boundary

`http/security/` is the reason permission checks belong here rather than in the
services below. A check inside business logic covers the callers that exist when
it is written; the boundary is the one place where the set of paths is
enumerable, so it can be enumerated.

Two modules, and the split matters:

- `dependencies.py` **decides**. A `PermissionGuard` is a plain callable over a
  `RequestContext` — no I/O, no framework — so a permission decision is testable
  without standing up a server. A decision that needed a running transport to
  exercise would be one nobody exercised.
- `route_permissions.py` **declares**, and is the only place a guard comes from.
  A handler asks the table for its guard; a route nobody declared raises
  `UndeclaredRoute` at wiring time, so the application fails to start rather
  than starting with an open route.

A row carries either a permission or written prose saying why the route is
public — never neither, never both, and `Route` refuses to be constructed
otherwise. `tests/security/test_route_permissions.py` fails the build on a
declaration that is missing, contradictory, or unreachable.

Adding routes in a later feature means extending the table with
`ROUTE_TABLE.extended_with(...)`, beside the handlers that serve them. The
collision check still happens in one place.

## Where things go

- HTTP surface → `http/`. Alert ingestion → `webhooks/`.
- A privileged route → a row in `http/security/route_permissions.py` first, then
  the handler wired through the guard it hands back.
- Chat platforms → one subpackage each, behind the shared chat contract.

---

Repository-wide rules — the constitution, the tier table, code style, and the
footguns — are in the root [`AGENTS.md`](../AGENTS.md). This file records only
what is specific to `gateway/`.
