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

## Where things go

- HTTP surface → `http/`. Alert ingestion → `webhooks/`.
- Chat platforms → one subpackage each, behind the shared chat contract.

---

Repository-wide rules — the constitution, the tier table, code style, and the
footguns — are in the root [`AGENTS.md`](../AGENTS.md). This file records only
what is specific to `gateway/`.
