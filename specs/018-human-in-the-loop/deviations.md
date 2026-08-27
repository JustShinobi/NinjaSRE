# Deviations — 018 Human in the Loop

Everything the implementation did that the plan did not say, or said
differently. Recorded as it happened, not reconstructed afterwards.

## 1. Test-first ordering was not honoured in Phase 1

**Plan:** T001–T002 build the model and the constants; T003–T008 write the
failing tests, "All red"; the implementation follows in Phases 2–7.

**What happened:** the Phase 1 contract tests (T003, T004, T005, and the
attention tests belonging to T033) were written *after* `models.py`,
`registry.py`, `closure.py`, `persistence.py` and `attention.py` existed, so
they never ran red. They passed 27/27 on their first execution.

**Why:** the five modules are one design — the registry's conditional transition
*is* the concurrency resolution, and the closure's addressee filter *is* the
routing rule — and writing an assertion against an API that had not been decided
would have produced tests shaped by a guess at the API rather than by the
property.

**Cost, stated plainly:** those four tests have not been shown to be capable of
failing. The three that were genuinely red first — the secret refusal (T006),
the five-message merge (T007), and the takeover tests (T008) — were written
before `handoff.py`, `message_queue.py` and `takeover.py` were touched, and were
observed failing.

## 2. `core/agent/interaction/progress.py` is a sixth module

**Plan:** the project structure lists five modules under
`core/agent/interaction/`. T034 and T035 ask for progress notification on a
timer with a cooldown and name no home for it.

**What happened:** added `progress.py`.

**Why:** attention answers "which run needs me" and progress answers "is it
still working". They are read by different people at different moments and share
no state; folding the notifier into `attention.py` would have put a timer, a
cooldown map, and a sink fan-out into a module whose job is deriving one value
from a set of interactions.

## 3. Attention is recorded as a trace event, not as run metadata

**Plan:** T036, "Attention state exposed in the run history API for the
console." Silent on where the state is stored.

**What happened:** `RunRecorder.record_attention` writes an
`attention_changed` trace event, and `RunHistory.attention_of` reads the latest
one. `Attention.to_metadata()` exists and is used for the payload, but nothing
writes attention onto the run row.

**Why:** the run row is written twice — once by `start_run` and once by
`complete_run` — and the persistence port has no operation that updates a
running run's metadata. An investigation blocks and unblocks several times, so a
field would only ever record the state the run happened to be in when it
finished, which for a concluded run is always "waiting on nobody". Adding an
update operation would have meant changing `RunTraceStore`, both
implementations, the Postgres model, and the persistence contract tests — a
migration this feature's plan does not mention and does not need.

## 4. A latent spin in `MessageQueue.drain`, fixed here

**Not in the plan at all.** Found while writing the SC-004 test.

The debounce compared a float difference against zero. With five messages the
remaining wait converged on a residue (~2e-16) too small to add to the clock,
and `drain` looped forever without ever delivering the guidance it was holding.
The three-message case in the existing feature-004 test happened to land on
exact binary fractions and passed.

Fixed with a named floor, `MESSAGE_QUEUE_DEBOUNCE_FLOOR_SECONDS` (1 ms), in
`config/constants/investigation.py` per Article II. This is a pre-existing
defect in feature 004's code, repaired rather than worked around in the test.

## 5. `ReActLoop` gained `pause`, `children_of`, and `share_control_with`

**Plan:** T027 "pause the loop at a safe point", T028 "sub-agent reaping during
pause". It does not say what the runtime has to grow to support them.

**What happened:** three additions to `ReActLoop` —

- `pause(session_id)`, checked between iterations after the cancellation check,
  producing a `SUSPENDED` session and a `PARTIAL` result;
- `children_of(session_id)`, so a reaper can find in-flight specialists without
  a second registry;
- `share_control_with(parent)`, because a specialist runs in its *own*
  `ReActLoop` instance and would otherwise never see the parent's stop signal —
  a reap that did nothing would have been the silent failure T028 exists to
  prevent.

`share_control_with` reaches into another instance's private sets. Same class,
one `noqa` per line, stated here because it is the kind of thing a reviewer
should be told about rather than discover.

## 6. Approval unification is by conversion and delegation, not by replacement

**Plan:** T037, "Migrate feature 015's approval requests onto the `Interaction`
abstraction."

**What happened:** `PendingChange` was **not** replaced.
`platform/approvals/interaction.py` converts one into an `ApprovalInteraction`,
and `ClosurePublisher` became a shell over `core.agent.interaction.closure`,
keeping the `DecisionEvent`/`DecisionSubscriber` vocabulary its surfaces already
speak.

**Why:** the approvals service enforces Article III's "and" — no approval
without a stored rollback plan — along with fingerprint conflict detection,
self-approval refusal, and the five appliers. Moving decision state into the
interaction layer would have moved those guarantees into a layer that does not
own them. The interaction is the *waiting* half; the change stays the source of
truth for the decision.

**How the plan's intent is met anyway:** all four properties are exercised
against an approval, through the question machinery, in
`tests/unit/platform/approvals/test_approval_interactions.py` — closure,
persistence, concurrency, attention. Feature 015's and 017's suites (307 tests)
pass unchanged.

## 7. The guardrail filter is a port, wired from `platform`

**Plan:** FR-005 requires answers to pass the guardrail engine.

**What happened:** `core` declares a `ContentFilter` protocol and defaults to no
filtering; `platform/guardrails/interaction.py` supplies the implementation over
`GuardrailEngine`.

**Why:** `core` and `platform` may import each other, so a direct import would
have passed the import contracts. But the runtime's behaviour must not depend on
a ruleset being configured, and a closure-path test should not have to compile
thirty regular expressions to run. This mirrors how feature 008 already attaches
to the loop — as a hook supplied from `platform`, not as an import from `core`.

The consequence is that **a deployment that does not wire the filter gets no
screening**, and that is deliberate rather than defaulted to something
plausible.

## 8. Two out-of-scope files were touched

- `docs/capabilities.md` — regenerated, because `ask_human` is now a declared
  capability and `tools/generate_capability_docs.py --check` is in `make
  verify`. Not a hand edit.
- `platform/runs/events.py` — one new `TraceEventKind`, `attention_changed`,
  required by deviation 3. Event kinds are a closed enum by design, so a new one
  is an addition there rather than a string at a call site.

## 9. `make verify` is green except for pre-existing benchmark flakiness

`tests/benchmarks` fails intermittently on this machine, with a *different*
throughput test failing on each run (`test_masking_overhead`,
`test_proxy_overhead`). Confirmed pre-existing: the same failures reproduce on a
stashed, unmodified tree, and neither the guardrail engine nor the credential
proxy was touched by this feature.

Everything else: **3811 passed, 15 skipped**, plus lint, format, typecheck,
import contracts, and the three guard checks.

## Not done

- **T042's `make check-provenance`.** `docs/provenance-map.md` was updated
  locally with feature 018's two sections. The `check-provenance` target the
  task names does not exist in the `Makefile` and never has — the map is
  gitignored, so a CI check over it could not run anyway, which is presumably
  why it was never built. Not added: inventing a target that only ever passes on
  one machine is worse than the task being stale.
