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

## The REST/SSE surface (`http/`)

The application (`http/app.py`) is composed from `GatewayState`
(`http/state.py`) — the one object a deployment profile builds to stand the
whole surface up: a `PersistenceGateway`, a `TokenService`, and an
`InvestigationRunner` (`http/services.py`). That last one is a protocol, not a
concrete class, for the same reason `surfaces/cli/client.py`'s `LocalServices`
is one — composing a runtime (the LLM client, the capability catalogue, the
credential proxy) is a deployment concern. Everything that does not need a
live runtime — runs, replay, streaming, configuration, schedules, memory,
capabilities, health — is wired straight to the tier-3 ports, because those
already work without a model attached.

`http/security/gateway_routes.py` extends feature 014's `ROUTE_TABLE`, beside
the handlers it guards. `http/state.py`'s `APPLICATION_ROUTE_TABLE` is the
composed result the application actually checks every request against —
`GatewayState.route_table` defaults to it.

Streaming (`http/streaming/`) is HTTP framing around `platform.runs.stream`
(feature 016), which already does catch-up, exactly-once delivery on
reconnect, and stalled-subscriber disconnect. A client reconnects with
`Last-Event-ID: <run_id>:<sequence>`.

## Alert ingestion (`webhooks/`)

`webhooks/router.py` serves one path per source
(`/webhooks/{alertmanager,pagerduty,datadog,grafana,sentry,opsgenie,generic}`).
Configuring a source means giving `gateway.http.app.create_app` a
`webhook_routes` mapping of path name to a tuple of `WebhookSourceConfig`
(verifier, org, team, principal) — an operator gives every team its own
verifier against the same URL, and whichever one verifies decides the team
(FR-023). A path with no configured routes exists and answers 401 to
everything, rather than not existing: an unconfigured deployment audits and
rejects, it does not expose an open endpoint.

Verification (`webhooks/verification/`) is one of three mechanisms:
`HmacVerifier` (PagerDuty, Sentry, the generic signed webhook), or
`SharedSecretVerifier` (Alertmanager, Datadog, Grafana, Opsgenie). `MutualTlsVerifier`
is available for any source an operator puts behind an mTLS-terminating
ingress — it trusts the two headers a reverse proxy sets after a successful
handshake (`X-SSL-Client-Verify`, `X-SSL-Client-Subject`) rather than parsing
a certificate itself.

Tuning: `config/constants/surfaces.py` — `ALERT_DEDUP_WINDOW_SECONDS`
(FR-018), `WEBHOOK_MAX_REQUESTS_PER_TEAM` / `WEBHOOK_RATE_LIMIT_WINDOW_SECONDS`
(FR-020, per source and team), `WEBHOOK_MAX_PAYLOAD_BYTES` (FR-021). Every
shed decision is recorded (`webhooks/shedding.py`) and readable from
`GET /health/ready`.

## The chat surface (`chat/`, `slack/`, `teams/`, `telegram/`, `discord/`)

One abstraction, four thin adapters. **A behaviour is implemented in `chat/` and
rendered per platform.** An adapter translates — Block Kit, an Adaptive Card, an
inline keyboard, a message component — and decides nothing. Writing "stream
progress" four times is how the four quietly stop agreeing.

`chat/contract.py` states the ten shared behaviours as data, and
`tests/contract/chat/` runs every row against every adapter. That is what makes
SC-001 enforceable rather than aspirational: a platform added to `CHAT_PLATFORMS`
without an adapter fails the suite, and a behaviour added to the contract fails
four tests until all four adapters satisfy it.

| Module | Owns |
|---|---|
| `chat/port.py` | the `ChatPlatform` protocol and the vocabulary the four speak |
| `chat/contract.py` | the ten behaviours, enumerable at runtime |
| `chat/streaming.py` | one progress message, rewritten; coalescing; rate-limit backoff |
| `chat/chunking.py` | splitting or attaching a report, losing nothing |
| `chat/identity.py` | platform user → `ChatIdentity` → principal, and the refusal |
| `chat/routing.py` | channel → team, and which alerts may auto-post there |
| `chat/history.py` | thread history through the guardrail engine, as data |
| `chat/commands.py` | the one command catalogue, rendered four ways |
| `chat/sink.py` | the run's output, and feature 018's `InteractionSurface` |
| `chat/session.py` | what an inbound message means, and thread → run bindings |
| `chat/transport.py` | one platform call, carried through the credential proxy |

Three things worth knowing before changing anything here.

**A chat sink is called `chat`, all of them.** An interaction addressed to the
chat surface reaches every configured channel, which is what makes an approval
decided in one channel close in the other (SC-008) and one decided in the console
close in a thread (SC-002).

**Nothing raises into a run.** A platform that has gone away is recorded, handed
to the fallback sink, and left behind. A chat surface that could fail an
investigation would make the investigation less reliable than not having one.

**There is no token anywhere in these packages.** A bot token is a credential and
goes through `platform/credentials/proxy/` like every other one;
`chat/transport.py` is the only path out, and it has no parameter that could
accept a secret. A test asserts that structurally.

The edit interval is *computed* from each platform's own budget rather than
shared — three seconds is twenty edits a minute, which Discord accepts and Slack
does not, and a two-hundred-event run is exactly where that difference bites.

Tuning: `config/constants/surfaces.py` — `CHAT_STREAM_EDIT_INTERVAL_SECONDS`,
`CHAT_MAX_EDITS_PER_MINUTE`, `CHAT_MESSAGE_LIMITS`, `CHAT_MAX_REPORT_CHUNKS`,
`CHAT_RATE_LIMIT_BACKOFF_SECONDS`, `CHAT_MAX_DELIVERY_ATTEMPTS`,
`CHAT_THREAD_HISTORY_LIMIT`. Per-platform setup and the minimum permission
scopes are in [`docs/chat-surfaces.md`](../docs/chat-surfaces.md).

---

Repository-wide rules — the constitution, the tier table, code style, and the
footguns — are in the root [`AGENTS.md`](../AGENTS.md). This file records only
what is specific to `gateway/`.
