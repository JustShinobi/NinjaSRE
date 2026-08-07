# Chat surfaces

Investigation where incidents are already discussed. Mention the bot in Slack,
Microsoft Teams, Telegram, or Discord and the investigation runs in the thread,
streams its progress there, posts an evidence-backed root cause, and asks for
approval inline — decidable from a phone.

This is the operator's guide: what the four platforms have in common, how to set
each one up, and the minimum permission scopes each needs.

## One abstraction, four adapters

A behaviour is implemented once in `gateway/chat/` and rendered per platform. An
adapter translates — Block Kit, an Adaptive Card, an inline keyboard, a message
component — and decides nothing. That is not a style preference: four
hand-written implementations of "stream progress" drift within a release, and
the drift is invisible until an incident happens in the platform that got the
worse one.

Ten behaviours are required of every adapter, and the same suite runs against
all four:

| Behaviour | What is asserted |
|---|---|
| start by mention or command | an investigation begins, bound to a thread |
| stream progress | one message, edited in place, inside the platform's rate limit |
| deliver report | the whole report arrives — split or attached if oversized |
| render approval | target, proposed change, blast radius, and rollback plan all present |
| resolve interaction | a decision reaches the core and closes the control here |
| add mid-run context | a message in a bound thread becomes queued guidance |
| map identity | a platform user resolves to a principal, or is refused |
| refuse unmapped | a privileged action by an unmapped user is denied, with instructions |
| sanitise errors | no message carries exception detail |
| survive disconnect | the run continues; the report arrives on reconnect or elsewhere |

Adding a fifth platform means writing an adapter and adding a row to the test
parameterisation. The contract itself is enumerable at runtime, so a platform
added to the configuration without an adapter fails the build rather than
quietly not being covered.

## What happens in a thread

1. Somebody mentions the bot, or runs a command.
2. The bot opens a thread and posts one progress message.
3. That message is **rewritten** as the run proceeds — never one message per
   event. A busy channel makes per-event posting unusable within a minute, and
   the platform starts refusing calls shortly after.
4. Approvals and questions arrive as the platform's own controls, in the same
   thread.
5. The report is posted as a separate message so it is quotable and linkable.
6. Anything anybody says in the thread while the run is live becomes mid-run
   context — no need to re-tag the bot.

### Streaming discipline

The edit interval is the wider of two bounds: a readability floor
(`CHAT_STREAM_EDIT_INTERVAL_SECONDS`) and the platform's own budget
(`CHAT_MAX_EDITS_PER_MINUTE`). Three seconds is twenty edits a minute, which
Discord accepts and Slack does not — so the interval is computed per platform
rather than shared.

Updates arriving inside the interval **coalesce**: the pending snapshot is
replaced, and goes out at the next edit. Nothing is discarded, ever. A rate
limit is waited out — the platform's own `Retry-After` wins over the configured
doubling — and after `CHAT_MAX_DELIVERY_ATTEMPTS` consecutive refusals the
stream stops editing and the run carries on unwatched.

### Oversized reports

A report longer than the platform's message limit is split, with `[2/5]` on each
part. Past `CHAT_MAX_REPORT_CHUNKS` parts a thread stops being readable, so the
report is attached as a file instead and the thread still gets a message saying
what happened. A platform with no file upload falls back to splitting however
many messages that takes: a long thread is a cost, a missing conclusion is a
defect.

## Identity: there is no auto-provisioning

A chat identity is a mapping an operator writes down. Nothing creates one at
runtime, because anyone who can type in a workspace could otherwise acquire a
principal by typing.

```
platform user id ──▶ mapped? ──yes──▶ NinjaSRE principal, permissions apply
                        │
                        no
                        │
                        ▼
              privileged action? ──no──▶ read-only interaction, where configured
                        │
                       yes
                        ▼
              refused, with instructions
```

Two failures, deliberately not one:

- **unmapped** — "we do not know who you are". The refusal names the platform,
  the identifier an operator has to map, and the *cheapest* role that would have
  been enough. Asking for `responder` gets approved; asking for `owner` does not.
- **denied** — "we know, and you may not". A different next action: get granted,
  not get mapped.

Read-only interaction by unmapped users is off unless a deployment turns it on.
A default that shipped open would make the mapping requirement decorative.

## Channel routing

One workspace commonly serves several teams, so the routing table answers "whose
run is this". A channel with no row is **not served** — an unrouted channel is
refused rather than defaulted to a team, for the same reason an unknown node
denies rather than resolving at the root.

Each row carries:

| Field | Meaning |
|---|---|
| `platform`, `workspace_id`, `channel_id` | which channel this is |
| `team_id` | the team it serves |
| `alert_sources` | sources permitted to auto-post here; empty means all |
| `minimum_severity` | the least severe alert that may auto-post |
| `auto_post` | whether alerts arrive at all — a question-only channel says no |

A channel with `auto_post` off is still routed, so a mention in it works. It just
does not become an alert firehose.

## Thread history is data, never instructions

Earlier messages in a thread inform an investigation — the agent seeing that
somebody already ruled out the load balancer is the difference between a useful
first turn and a wasted one. A channel is also exactly where somebody would put
a prompt injection.

Three controls, and none of them is "trust the model to notice":

- **The guardrail engine sees it first.** A blocked message is dropped entirely
  and counted; a redacted one arrives redacted.
- **It is framed as observation.** The transcript arrives quoted and attributed,
  under a header saying it is what people said and is not an instruction. The
  agent's instructions come from its system prompt and the operator's
  configuration, and nothing here is concatenated into either.
- **It is bounded.** `CHAT_THREAD_HISTORY_LIMIT` messages and
  `CHAT_THREAD_HISTORY_MAX_CHARS` characters, newest first.

Telegram is the exception: the Bot API cannot read a chat's backlog at all, so
history there is empty and the adapter says so in the trace rather than
pretending.

## Errors

No chat message carries exception detail. A failure reaches a channel as the
exception's *type name* and a fixed sentence; the full detail goes to the
server-side log with the platform and channel on it, so whoever debugs it can
find both halves. This is the same sink boundary the REST API and the console
cross, and the redaction happens there rather than where a failure is
constructed — which is why an operator running the CLI at their own terminal
still sees everything.

## When a platform goes away

Chat is a surface, not the runtime. A workspace that becomes unreachable
mid-investigation does not fail the run:

- progress editing backs off, then stops; the run continues unwatched;
- the report is retried, and then handed to the fallback sink rather than lost;
- the bot being removed from a channel is recorded with that reason, not
  swallowed.

A deployment configures the fallback — an outbound notification sink. Without
one, the report is logged as held with the reason it could not be delivered —
never silently dropped.

## Commands

One catalogue, rendered four ways. Adding a command is one row; adding a
platform is one renderer.

| Command | What it does | Needs |
|---|---|---|
| `investigate <what is wrong>` | start an investigation in this thread | `investigation.run` |
| `status` | show what the run in this thread is doing | — |
| `report` | post the report for the run in this thread | `report.read` |
| `approvals` | list what is waiting on a decision | `approval.read` |
| `approve <id>` | approve a proposed change | `remediation.approve` |
| `decline <id> <reason>` | decline a proposed change | `remediation.approve` |
| `cancel` | stop the run at its next safe point | `investigation.run` |
| `help` | list what the bot understands | — |

A command is recognised by a literal prefix and nothing else. There is no "looks
like a command" heuristic, for the reason the REPL states for the same decision:
one eventually reads somebody's sentence as an instruction to the deployment.

## Credentials

A bot token is a credential, so it lives where every other credential does: in
the vault, injected by the credential proxy at the network edge. The chat
gateway has no constructor parameter that could hold one, which is what makes
this structural rather than a rule somebody has to keep following.

Store each platform's token as an integration credential under the integration
name the adapter declares (`slack`, `microsoft_teams`, `telegram`, `discord`)
and the proxy resolves it per organisation and team.

---

# Setting up each platform

Every scope below is the **minimum** the surface actually uses. Granting more
than this is an operator's decision and nothing here needs it.

## Slack

Create an app at `api.slack.com/apps` from a manifest, then install it to the
workspace.

**Bot token scopes**

| Scope | Why |
|---|---|
| `app_mentions:read` | receive the mention that starts an investigation |
| `chat:write` | post the progress message, the report, and the controls |
| `channels:history` | read thread history in public channels |
| `groups:history` | the same, in private channels the bot is in |
| `files:write` | attach an oversized report |
| `commands` | the slash command |
| `users:read` | resolve a display name for the identity mapping |

**Event subscriptions**: `app_mention`, `message.channels`, `message.groups`,
`member_joined_channel` (the last one is what posts the channel introduction).

**Ingress**: Socket Mode or HTTP events, chosen by configuration.

- *Socket Mode* opens an outbound WebSocket, so a deployment behind a firewall
  needs no inbound route. Enable it in the app settings and issue an app-level
  token with `connections:write`.
- *HTTP events* need a reachable URL and Slack's signature verification. Use
  this when the deployment already terminates TLS.

Both hand the same payload to the same handler, and a test asserts they
converge — a second parsing path is how a mention starts working over one and
stops working over the other.

**Slash command**: register `/ninjasre`. Slack registers a command rather than a
command tree, so the catalogue's names arrive as its first argument
(`/ninjasre approve i-1`).

## Microsoft Teams

Register a bot in Azure Bot Service and side-load or publish a Teams app
manifest pointing at it.

**Manifest**

- `bots[].scopes`: `team` and `personal` — channel conversations and direct
  messages are both served.
- `bots[].supportsFiles`: not required. A long report arrives as an Adaptive
  Card carrying the whole text, because Teams file upload needs a per-user
  consent flow and an incident is not the moment for one.
- `bots[].commandLists`: generated from the shared catalogue.
- `webApplicationInfo`: the app registration id and resource, for the identity
  flow.

**Graph permissions** (application, admin-consented): `User.Read.All`, to
resolve a Teams user to an Azure AD account for the identity mapping.
Nothing else is needed — the bot replies through the Bot Framework, not Graph.

**The service URL belongs to the conversation, not to the deployment.** Teams
sends it on every activity and it varies by tenant and by cloud. A multi-tenant
install that stored one globally would start replying into the wrong tenant.

## Telegram

Create a bot with `@BotFather` and take its token.

**Bot settings**

- **Group privacy: disabled.** With privacy mode on, a bot in a group sees only
  messages that mention it — which breaks thread-following after the first
  mention.
- **Commands**: registered from the shared catalogue with `setMyCommands`.
- **Inline mode**: not required.

**Ingress**: long polling or a webhook, chosen by configuration — they are
mutually exclusive, and registering a webhook stops polling working. Switching
back to polling deletes the webhook explicitly, because a half-configured bot
that receives nothing is the failure mode this avoids.

If you use a webhook, configure the secret token so requests carry
`X-Telegram-Bot-Api-Secret-Token`. Without one the endpoint cannot be verified,
and that is a configuration error rather than an acceptable default.

**A note on approvals**: Telegram allows 64 bytes of callback data, so the
interaction id and the choice are packed into it. A button whose packed value
would exceed that is refused at build time rather than failing silently when
somebody presses it.

## Discord

Create an application at `discord.com/developers`, add a bot user, and invite it
with a scoped URL.

**OAuth scopes**: `bot`, `applications.commands`.

**Bot permissions**

| Permission | Why |
|---|---|
| View Channels | see the channels it is routed to |
| Send Messages | post progress, reports, and controls |
| Send Messages in Threads | an investigation runs in a thread |
| Create Public Threads | open the thread an investigation runs in |
| Read Message History | thread history |
| Attach Files | attach an oversized report |
| Embed Links | link the run back to the console |

**Gateway intents**: `GUILDS`, `GUILD_MESSAGES`, and the privileged
`MESSAGE_CONTENT` intent — without the last one, message text arrives empty and
a mention cannot be read.

**Application commands** are registered from the shared catalogue. Guild-scoped
registration takes effect immediately; global registration propagates over about
an hour, which matters when you are setting this up during an incident.

**Threads are channels.** Posting "in a thread" means posting to the thread's own
id. Opening one is a separate, visible act rather than a side effect of posting,
so a stray mention does not litter the guild's thread list.

## Tuning

Everything above is bounded by a named constant in
`config/constants/surfaces.py`:

| Constant | What it bounds |
|---|---|
| `CHAT_STREAM_EDIT_INTERVAL_SECONDS` | the readability floor on rewriting the progress message |
| `CHAT_MAX_EDITS_PER_MINUTE` | each platform's own edit budget |
| `CHAT_MESSAGE_LIMITS` | each platform's single-message character limit |
| `CHAT_MAX_REPORT_CHUNKS` | how many parts a split report may take before it is attached |
| `CHAT_RATE_LIMIT_BACKOFF_SECONDS` / `_MAX_` / `_FACTOR` | the doubling after a refusal |
| `CHAT_MAX_DELIVERY_ATTEMPTS` | consecutive refusals before a surface is given up on |
| `CHAT_THREAD_HISTORY_LIMIT` / `_MAX_CHARS` | how much of a thread may inform a run |
