# Deviations — 022 Chat Surfaces

Recorded per task instruction. Not committed (this whole directory is
gitignored, same as `spec.md`/`plan.md`/`tasks.md`).

## 1. Three modules exist that the plan's project structure does not list

The plan's tree names eight modules under `gateway/chat/`. Three tasks name no
file at all — T017 (error sanitisation at the chat sink), T018 (interaction
closure integration with feature 018), and the thread-binding half of T009 —
and each needs an owner. Rather than putting them in the nearest module that
already imported something similar, which is how a `utils.py` becomes 4,000
lines, they got the modules they belong to:

- **`gateway/chat/sink.py`** — `ChatSink`. Owns everything that crosses from a
  run into a channel: the progress message, the report, the interactive
  elements, and the failures. It is feature 018's `InteractionSurface`
  (`present`/`closed`), which is T018, and it is where `SinkGuard` is applied,
  which is T017. Putting the sanitisation anywhere else would have meant every
  caller remembering to redact.
- **`gateway/chat/session.py`** — `Bindings`, `ChatDispatcher`, `ChatRuntime`.
  What an inbound message *means* (start a run / add context / run a command /
  ignore) and which thread carries which run. The plan asserts "a message in a
  bound thread becomes mid-run context" as a shared behaviour, so the
  classification has to be shared rather than written four times.
- **`gateway/chat/transport.py`** — `ProxiedChatTransport`. See deviation 2.

`AGENTS.md`'s file-placement rule ("behaviour goes in its owning module") is
what decided this. Nothing was moved *out* of a module the plan named.

## 2. One transport seam, and it routes through the credential proxy

The plan's technical-context table names per-platform mechanisms (Socket Mode,
Bot Framework, Bot API, gateway) but does not say how a call is authenticated.
A bot token is a credential, so Article IV decides it: it goes in the vault and
the proxy injects it at the network edge, exactly as
`integrations/_base/client.py` does for a vendor call.

Concretely: `ChatPlatform` methods build a `PlatformCall` (a method, a path,
and a JSON payload — every field safe in a trace) and `ProxiedChatTransport`
carries it through `integrations._base.transport.ProxyTransport`. Tier 1 may
import tier 2, so this is a legal edge.

Two consequences worth stating:

- **There is no parameter anywhere in `gateway/{chat,slack,teams,telegram,discord}/`
  that could hold a token**, and `tests/unit/gateway/chat/test_transport.py`
  asserts that structurally rather than by review.
- All four platforms are HTTP JSON APIs, so one call shape covers them and the
  per-platform part is the path and the payload — which is exactly the part
  that belongs to an adapter. This is why the contract suite drives all four
  adapters through one fake with no network and no credential.

## 3. `contract.py` states the contract; the assertions live in the tests

The plan puts `contract.py` in `gateway/chat/` and describes it as "shared
behaviour all adapters must satisfy". Taken literally that would put a test
harness in production code. What shipped instead:

- `gateway/chat/contract.py` is the **machine-readable statement** of the ten
  behaviours — one row each, naming what is asserted and which port members the
  behaviour exercises — plus `unimplemented_platforms()` and
  `missing_members()`.
- `tests/contract/chat/` holds the executable assertions and parameterises over
  the four adapters.

The property the plan wants is preserved and is stronger than a document: a
fifth platform added to `CHAT_PLATFORMS` without an adapter fails
`test_every_configured_platform_has_an_adapter_in_this_suite`, and a behaviour
added to `CHAT_CONTRACT` fails four tests until all four adapters satisfy it.

## 4. `make check-provenance` does not exist (T050)

T050 says "update `docs/provenance-map.md`; confirm `make check-provenance`".
There is no `check-provenance` target in the `Makefile` and no
`tools/check_provenance*.py`, on this branch or on `master`. It was presumably
planned before ADR 0011 amended Constitution Article XIII to 2.0.0 — that
amendment removed per-file provenance headers entirely, which is what such a
check would have verified, and the checklist in `docs/provenance-map.md`
records the header requirement as struck through and superseded.

`docs/provenance-map.md` **is** updated: the three rows in section 8 that cover
this feature's upstreams are marked shipped, and a "Feature 022 — what came
from where" / "written fresh, not adapted" pair was added in the format
features 018 and 019 use. Adding a `check-provenance` target was not done: it
would be inventing a gate the constitution no longer asks for, in a feature
that is about chat.

## 5. Telegram has no thread history, and the adapter says so

FR-006 makes thread history a *may* ("Thread history MAY inform an
investigation"), and the Bot API has no way to read a chat's backlog — a bot
sees messages as they arrive and cannot ask for earlier ones. There is no
workaround that does not involve the bot maintaining its own message store,
which would be a second copy of a conversation the platform already owns.

`TelegramPlatform.thread_history` therefore returns empty and logs
`telegram.thread_history_unsupported` with the chat and the requested limit, so
the trace records that history was asked for and was not available rather than
implying the thread was empty. The other three platforms read history normally.

## 6. Teams delivers an oversized report as a card, not a file upload

FR-005 requires an oversized report to be "split or attached, never truncated
silently". Teams file upload needs a per-user consent flow (`fileConsent/invoke`
round-trip), which an incident is not the moment for and which would fail
outright in a channel conversation.

`TeamsPlatform.attach` sends an Adaptive Card carrying the whole report text
instead. That satisfies what the requirement is for — one addressable message
holding the complete report, nothing truncated — through the mechanism Teams
actually offers. `PlatformLimits.supports_attachments` exists for a platform
where even that is unavailable, and `deliver_report` then splits into however
many messages it takes; that path is tested
(`test_an_attachment_falls_back_to_splitting_where_a_platform_has_no_files`).

## 7. A real gap found while writing the SC-003 test

The plan and T009 describe the streaming interval as one bounded interval, and
T008 asks for "streaming edit interval" as a single constant. Written that way,
`CHAT_STREAM_EDIT_INTERVAL_SECONDS = 3.0` produces twenty edits a minute — which
is inside Discord's budget and **past Slack's and Telegram's**. The 200-event
test (SC-003) failed on exactly those two platforms.

Fixed rather than accommodated: `gateway/chat/streaming.interval_for()` returns
the wider of the configured readability floor and `60 / edits_per_minute` for
the platform in question, and `ProgressStream` computes its interval from the
platform's own limits unless a caller overrides it. Both constants are still
named constants in `config/constants/surfaces.py`; there are now two of them
because there are two independent bounds, and only one of them is the same on
every platform.

This is a deviation from the plan's wording, not from its intent — the plan's
own risk table names "rate limits cause dropped updates" as the risk SC-003
validates.

## 8. `ChatDispatcher` gates mid-run context with `investigation.run`

Neither the spec nor `commands.py`'s catalogue says which permission adding
mid-run context needs; the catalogue only covers commands, and mid-run context
is free text rather than a command. Adding context is *steering* a run — it is
guidance the agent acts on — so somebody who may not start an investigation
must not be able to direct one. `_permission_for` therefore maps both
`START_INVESTIGATION` and `ADD_CONTEXT` to the `investigate` command's
`Permission.INVESTIGATION_RUN`.

The alternative reading — that adding context is a read-adjacent act anyone in a
routed channel may perform — would make FR-002's "permissions apply as on every
other surface" false in the one place where it is easiest to abuse.

## 9. The chat constants are re-exported from `config/constants/__init__.py`

Features 020 and 021 added constants to `config/constants/surfaces.py` without
re-exporting them from the package `__init__.py` (`WEBHOOK_*`,
`API_RATE_LIMIT_*`, `CONSOLE_TRANSCRIPT_*` are all absent from it), and no test
enforces the re-export. `AGENTS.md` states the rule — "every constant lives in
`config/constants/`, in the domain module that owns it, re-exported from
`__init__.py`" — so this feature follows the rule rather than the two most
recent precedents. Nothing depends on the choice either way; it is noted only
because it makes this feature inconsistent with its two immediate predecessors.

## 10. Two behaviours of the ten are asserted in their own modules

`tests/contract/chat/test_shared_contract.py` covers seven of the ten shared
behaviours directly. The remaining three — refuse-unmapped, sanitise-errors,
and survive-disconnect — are asserted in `test_identity_refusal.py`,
`test_error_sanitisation.py`, and `test_disconnect_resilience.py`, because T003,
T004, and T006 ask for those files by name and each needs fault injection the
shared file would have made unreadable. All three are still parameterised over
all four adapters, so every behaviour still runs four times; the split is which
file it lives in, not which platforms it covers. A comment in
`test_shared_contract.py` points at the three.

## 11. The new unit test files carry a platform prefix in their names

`tests/contract/chat/` is a package (it has an `__init__.py`, because the
contract suite imports `tests.contract.chat.conftest` by name). The repository's
convention elsewhere is that a leaf test directory gets an `__init__.py` only
when its file basenames would otherwise collide — `tests/unit/surfaces/console/`
has one for exactly that reason.

A `tests/unit/gateway/chat/` package would have been a *second* top-level `chat`
package, which pytest cannot import alongside the first. Rather than adding
`__init__.py` files up the whole tree — which would give the unit tests a
top-level `gateway` package colliding with the real one — the three new unit
directories have no `__init__.py` and their files are named
`test_chat_routing.py`, `test_slack_ingress_and_intro.py`,
`test_discord_worker.py`, and so on. Unique basenames, no packages, and the name
says which adapter it covers.

## 12. Where each Definition-of-done item is asserted

For the record, since several are asserted across more than one file:

| Item | Where |
|---|---|
| SC-001 four platforms, one suite | `tests/contract/chat/test_shared_contract.py` (+ the four files below, all parameterised over all four adapters) |
| SC-002 cross-surface propagation | `tests/contract/chat/test_cross_surface_closure.py` |
| SC-003 200-event streaming in budget | `tests/contract/chat/test_streaming_budget.py` |
| SC-004 oversized reports complete | `tests/contract/chat/test_oversized_report.py` |
| SC-005 unmapped users refused | `tests/contract/chat/test_identity_refusal.py` |
| SC-006 no exception detail | `tests/contract/chat/test_error_sanitisation.py` |
| SC-007 connectivity loss | `tests/contract/chat/test_disconnect_resilience.py` |
| SC-008 concurrent approvals | `tests/contract/chat/test_concurrent_approvals.py` |
| `make verify` | green: 5048 passed, 15 skipped |

The two edge cases with their own tasks and no success criterion — T044 (bot
removed from a channel mid-investigation) and T046 (an expired approval) — are
in `test_disconnect_resilience.py`
(`test_the_bot_being_removed_from_the_channel_is_recorded_not_swallowed`) and
`test_cross_surface_closure.py`
(`test_an_expired_approval_closes_in_chat_with_a_message_not_a_silent_no_op`).

## 13. Requirement identifiers stripped from committed files

`CLAUDE.md`'s writing-style rule: "Do not cite requirement identifiers
(`FR-018`), success criteria (`SC-003`), constitution article numbers, or
feature numbers in committed code. Those point at documents a contributor
cloning the repository will not have. State the substance instead."

The first draft cited them heavily, matching what the surrounding committed code
already does — `gateway/AGENTS.md`, `gateway/http/errors.py`,
`config/constants/surfaces.py`'s webhook block, and
`tests/architecture/test_console_is_a_pure_client.py` all cite `FR-` numbers
today, so features 019 through 021 did not follow this rule. Every citation
added by *this* feature was removed and replaced with the substance it stood
for. Pre-existing citations elsewhere were left alone: rewriting other features'
prose is outside this feature's scope.

The docstrings are longer for it, and better — a reader without `specs/` now
learns why the bound exists rather than which document to go and find.
