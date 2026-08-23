# Deviations — 023 Notifications and Reporting

Recorded per task instruction. Not committed (this whole directory is
gitignored, same as `spec.md`/`plan.md`/`tasks.md`).

## 1. "Ruled out" has no upstream producer, so the builder derives it

The plan's Phase 2 says the builder assembles a `Report` "from the diagnosis and
evidence", and FR-001/FR-002 require a *ruled out* section. Nothing upstream
produces one: `core.domain.diagnosis.result.Diagnosis` carries `root_cause`,
`causal_chain`, `validated_claims`, `non_validated_claims`, `remediation_steps`,
`confidence`, and `summary`, and no pipeline stage tracks eliminated hypotheses
as a distinct concept.

Resolved two ways rather than by leaving the section empty:

- `build_report(..., ruled_out=...)` takes the list explicitly, so a caller that
  *does* know — a future stage, an operator, a chat interaction — supplies it and
  it is used verbatim.
- When nothing is supplied, it is **derived**: a non-validated claim that cites
  evidence the run actually holds is a hypothesis somebody looked at and could
  not confirm, and it becomes a `RuledOut` with the reason "the evidence gathered
  for this hypothesis did not support it" and that evidence attached. A
  non-validated claim citing *nothing* is deliberately excluded — it was never
  examined, and reporting it as eliminated would send the next engineer past the
  thing that is actually wrong.

The claim stays in `non_validated_claims` as well. The two sections answer
different questions ("what did the evidence not confirm" and "what was
eliminated, and how"), and FR-001 lists both.

## 2. Modules the plan's structure sketch does not name

The plan's `Project structure` block is a sketch of the two packages. Six
modules were added inside it that it does not list, each for a stated reason:

- **`reporting/formatters/sections.py`** — the eight report sections, built once
  and rendered five ways. Building them per formatter would be five places for a
  section to be dropped, and the one that gets dropped is always "ruled out", in
  the report that reached no conclusion. Audience filtering lives here for the
  same reason: a per-formatter decision about evidence bodies would be four
  chances to get FR-018 wrong.
- **`reporting/delivery/trace.py`** — the adapter from `DeliveryRecord` to a
  `RunRecorder` event (FR-012). Kept out of `dispatcher.py` so the dispatcher
  holds a two-method port and the delivery suite runs with no store.
- **`notifications/models.py`** — `Severity`, `Outcome`, `SinkKind`,
  `NotificationSink`, `Notification`, `NotificationRecord`, `SinkCall`, and the
  two transport protocols. The plan lists no models module for this package; the
  five sinks and four policy modules all need the same vocabulary, and defining
  it in whichever one happened to be written first is how a circular import
  starts.
- **`notifications/service.py`** — routes, redacts per sink, delivers, records.
  `policy.py` decides and the sinks send; something has to do both in the right
  order, and the order is where two properties live (§below). Keeping it out of
  `policy.py` is what keeps routing a pure function a test can drive through a
  week of clock time in milliseconds.
- **`notifications/trace.py`** — the same adapter shape as `delivery/trace.py`,
  for notification decisions.
- **`notifications/configuration.py`** — reads a team's resolved `SurfacesConfig`
  into `Destination`s, `NotificationSink`s, and a `NotificationPolicy` (T038,
  FR-021). Put here rather than in `config_service/schema/` so the schema stays a
  plain typed surface with no imports from the reporting or notification layers.

## 3. `route` and `commit` are split, which the plan does not describe

The plan's routing flowchart ends at "Notify". `NotificationPolicy` splits the
decision (`route`) from spending the cooldown window and the rate-limit
allowance (`commit`), and `NotificationService` commits **after** delivery, only
if at least one sink took the notification.

Not in tasks.md, and it is the difference between a correct feature and a
plausible one: opening a fifteen-minute quiet window on a notification that
reached nobody turns one vendor's outage into a silent outage of the whole
notification system for the duration of the window. Two tests cover it
(`test_a_notification_that_reached_nobody_does_not_open_a_quiet_window`,
`..._does_not_spend_the_rate_limit`).

## 4. Two new `TraceEventKind` members, and their console labels

FR-012 requires delivery outcomes in the run trace, and T037 requires suppression
and rate-limit decisions surfaced. `platform.runs.events.TraceEventKind` is
closed by design, so `REPORT_DELIVERED` and `NOTIFICATION_DECIDED` were added to
it — the route the root `platform/AGENTS.md` names for exactly this — together
with labels in `surfaces/console/transcript.py`'s `EVENT_LABELS`. Without the
labels the console's fallback would title-case the kind, which renders but reads
as an event nobody named.

One event per *destination* and per *sink*, not per run. "Reports delivered"
cannot answer "did the Jira ticket get created", which is the question asked the
morning after.

## 5. Transports and probes are ports; SC-001 is verified against recorded contracts

`platform/reporting/` and `platform/notifications/` are tier 3 and must not
import `integrations/`, so no vendor client exists here. `DeliveryTransport`,
`VerificationProbe`, `NotificationTransport`, and `ChatNotifier` are protocols
the deployment satisfies — the same seam `gateway/chat/port.py` uses for the four
chat adapters, and `integrations/_base/transport.py` for authenticated calls.

SC-001 ("verified against real or recorded destination responses") is therefore
satisfied with the *recorded* half:
`tests/contract/reporting/test_thirteen_destinations.py` drives all thirteen
through a transport that enforces each destination's own published constraints —
its body limit, its refusal of an empty title or body, email's refusal of a
message with no plain-text part — and answers with that vendor's reference shape.
A stub that accepted everything would prove nothing, so the refusals are the
substance of the test. Live-vendor verification needs `integrations/` clients,
which is feature 024/025.

## 6. Config schema: generic kinds kept, `notification_sinks` retyped

`platform/config_service/schema/surfaces.py` already had
`report_destinations`/`notification_sinks`, both typed `DestinationSettings` over
five *generic* kinds (`chat`, `webhook`, `email`, `pull_request_comment`,
`knowledge_base`), and three shipped golden templates store `kind: chat` /
`kind: knowledge_base`.

- `DESTINATION_KINDS` is now the union of those five and the thirteen named
  destinations, so a stored generic kind keeps validating.
  `notifications/configuration.py` resolves a generic kind through a
  deployment-supplied mapping and **skips and logs** an unmapped one rather than
  guessing which of four chat platforms a team meant.
- `notification_sinks` is retyped to a new `SinkSettings` validated against the
  five notification sinks, with `options` for per-vendor extras. No shipped
  template sets it, so nothing stored breaks.
- Added `DestinationSettings.audience` / `.verified` (FR-006, FR-022) and a
  `NotificationPolicySettings` section (quiet hours, cooldown, per-hour limit).
  Team values **narrow** only: the schema refuses a limit above the platform
  ceiling and `policy_of` takes the longer of the team's cooldown and the
  platform default (Article II — the constants are ceilings).

## 7. Pushover is the one place content is cut rather than summarised

FR-007 and SC-007 are about *destinations*, and the report path honours them
structurally: `sizing.py` shortens by dropping whole blocks, so no code path
slices report content at an arbitrary offset.

A Pushover *notification* is different. The vendor's API refuses a title over 250
characters or a message over 1,024, so `sinks/pushover.py` cuts to fit — marked
with an ellipsis, and the link to the full run survives the cut. Discovering the
refusal at 03:00 instead would be worse than a visibly shortened message, and the
whole report is one tap away.

## 8. `Audience` lives in `reporting/models.py`

FR-006 (restore identifiers only for authorised *destinations*) and FR-018
(redact at the *sink* by audience) both need it. Defined once, in the lower of
the two packages, and imported by `notifications/`; the dependency runs
notifications → reporting and never back.

## 9. Test-first sequencing, adapted per module rather than per phase

The plan's Phase 1 asks for T003–T007 written and confirmed red before Phases
2–7 exist. Written that way they would fail on `ImportError`, which proves
nothing about the behaviour they describe — the same reasoning recorded in
`specs/020/deviations.md` §7.

What was done instead: each module's tests were written first, run, and confirmed
failing for the right reason before the implementation landed
(`tests/unit/platform/reporting/test_models.py` was confirmed red against a
missing module *and then* against the real one for each invariant it asserts).
Every SC in the definition of done has a test exercising real collaborators — the
real guardrail engine and ruleset, the real `SinkGuard` and `MaskingContext`, the
real registry, the real dispatcher and policy — rather than a mock standing in
for the boundary being proven.

## 10. T044 (`docs/provenance-map.md`, `make check-provenance`) not done

Two reasons, both outside this feature:

- `docs/provenance-map.md` is gitignored per `CLAUDE.md`, and a committed file
  must not depend on an uncommitted one. Editing the local copy has no effect on
  what ships. Same disposition as `specs/020/deviations.md` §6.
- There is no `check-provenance` target in the `Makefile`; the gate is `lint,
  format-check, typecheck, check-imports, check-constants, check-protocols,
  check-deps, check-vendor-sdks, check-literals, check-raw-sql,
  check-credentials, test`. Nothing was loosened to make that true.

Provenance is instead recorded where it is allowed to be: this feature's prior
art is described by capability in `platform/AGENTS.md` and
`docs/notifications-and-reporting.md`, naming no upstream project.

## 11. Test module basenames must be unique

`tests/` has no `__init__.py` files, so pytest imports test modules by basename
and two files called `test_policy.py` collide at collection. The notification
tests were renamed `test_notification_policy.py` and
`test_notification_service.py` after `make verify` reported the clash against
`tests/unit/platform/memory/strategy/test_policy.py` and
`tests/unit/platform/config_service/test_service.py`.

## 12. The suite was larger than the task's stated baseline

The task states "4223 passed, 15 skipped" before this feature. The tree as found
collects **5065** tests excluding everything added here; `make verify` on it was
green. After this feature: **5299 passed, 15 skipped**, no failures, same 15
skips. The 249 added tests are 18 model, 16 builder, 34 formatter, 26 delivery,
97 notification, 54 thirteen-destination contract, and 4 end-to-end.
