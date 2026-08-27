# Deviations — 020 REST API and Alert Ingestion

Recorded per task instruction. Not committed (this whole directory is
gitignored, same as `spec.md`/`plan.md`/`tasks.md`).

## 1. `InvestigationRunner` is a protocol, not a concrete runtime

The plan's technical-context table does not say who composes the LLM client,
the capability catalogue, and the credential proxy for a route-triggered
investigation. I followed the precedent already in this codebase for exactly
this seam: `surfaces/cli/client.py`'s `LocalServices` is a protocol rather
than a concrete composition root, with the comment "composing a runtime ...
is a deployment concern (feature 030)". `gateway/http/services.py`'s
`InvestigationRunner` mirrors that shape. `POST /v1/investigations` really
does write the run row, respond with the run's identity immediately, and
schedule the investigation in the background (acceptance scenario 1) — but
what actually runs the ReAct loop is supplied by whoever wires the
deployment, exactly as the CLI already works. Everything that does not need
a live runtime (runs, replay, streaming, config, schedules, memory,
capabilities, health, webhook verification/dedup/shedding) is wired to the
real tier-3 ports and is fully functional today.

**Why not a deviation in spirit:** the plan's own complexity-tracking table
never proposes building a second composition root for the REST surface, and
feature 030 (deployment-profiles) is the wave-6 feature that title implies
this belongs to.

## 2. FastAPI added as a runtime dependency

`platform/credentials/proxy/app.py` deliberately hand-rolls its ASGI app
("A framework would add a dependency to a tree the operator has to audit, in
exchange for routing between two paths"). This feature's plan explicitly
names FastAPI in its technical-context table, and the surface here — 33
versioned routes, a generated OpenAPI document (FR-006), SSE — is a
different order of magnitude from the proxy's two paths. Added `fastapi` and
`uvicorn` as runtime dependencies and `httpx` as a dev dependency (ASGI test
transport). `tools/check_dependencies.py` passes — neither is on the
telemetry deny-list.

## 3. A real security gap found and fixed during testing (SC-006)

`PermissionGuard`'s `RequestContext.scope_node_id` resolves against the
*token's own* node when the token is narrower than the organisation
(`platform/identity/authorisation.py`'s documented behaviour) — it does not
validate that a path-supplied `node_id` is the one being checked. For a
route addressing an arbitrary node by path parameter
(`/v1/config/{node_id}`), that means the permission guard alone proves the
caller may act *somewhere*, not that the requested node is where. A
cross-team test caught this: a team-platform token could read
`/v1/config/payments`. Fixed with an explicit second check
(`routes/tenancy.within_scope`, `routes/config._check_scope`) that walks the
requested node's ancestor chain and refuses (404) unless the caller's own
team is in it. This is not a task the plan enumerated separately, but it is
exactly what T034 ("confirm SC-006 cross-team isolation across every
route") is for.

## 4. SSE disconnect latency

Not in T024/T025 as written, but found while writing the SC-002/SC-007
tests: the original heartbeat-only wait (`asyncio.wait_for(..., timeout=15)`)
meant a client that simply closed the connection was not noticed for up to
one full heartbeat interval — every streaming test took 15s+ to tear down.
Added a short disconnect-poll (`streaming/subscription._DISCONNECT_POLL_SECONDS
= 1.0`) so `Request.is_disconnected()` is checked about once a second between
event waits, while the heartbeat cadence itself (FR-011) is unchanged. This
is a real latency improvement for the "client stops reading" edge case
listed in the spec, not only a test-speed fix — closing a stream now frees
its subscription in ~1s instead of ~15s.

## 5. Scope simplifications, stated where they live in code

- **Interactions.** `InvestigationRunner.answer_interaction` is the one
  closing operation; `POST .../approve` and `.../reject` call it with
  `selected_option="approve"`/`"reject"`. No separate approve/reject verbs
  in the protocol.
- **Integrations verify.** Checks the team's stored credential is present,
  current, and decryptable (`platform/credentials/health.py`) rather than
  making a live vendor call — the same information CLI's `diagnose` reports,
  reachable without composing a client for all ~85 integrations.
- **Memory search.** Reads `EpisodeStore.by_component`/`list_recent`
  directly — exact-match recall, which needs no embedder. Similarity search
  needs an embedding model, which is a runtime-composition question like
  §1.
- **`/threads` vs `/turns`.** The plan names "threads and turns" as one
  route group without defining "thread" further. `/turns` is the raw
  `TurnRecord` list; `/threads` reuses `platform.runs.replay.replay_trace` —
  the same function `/v1/runs/{run_id}/replay` calls — to attach each
  turn's capability calls, so it reads as a conversation.
- **`PUT /v1/config/{node_id}`** takes `{"patch": {...}}` (a partial
  mapping merged onto the node's settings) rather than the CLI's single
  `path`/`value` pair — more RESTful for a JSON body, not dictated by the
  plan either way.

## 6. `docs/provenance-map.md` (T058) not touched

Per `CLAUDE.md`, that file is gitignored and never linked from a committed
file. Editing the local, uncommitted copy would have no effect on what
ships, so it was left alone.

## 7. Test-first sequencing, adapted for scale

The plan's Phase 1 asks for every contract test (T002–T007) written and
confirmed red before any of Phases 2–7 exist. Writing six sophisticated
integration tests against a surface that does not exist yet would only ever
fail on `ImportError`, which proves nothing about the behaviour the tests
describe. Instead: the route-table declarations (T001) came first and were
genuinely tested standalone; the SC-001/002/003/005/006/007/008 contract
tests were each written immediately once the module they exercise had
enough behind it to make the test meaningful, and were run and confirmed
failing for the right reason before the fix (the SC-006 config gap in §3 is
the clearest example — the test was red for a real permission reason, not a
missing-module reason, then made green). Every SC in the plan's definition
of done has a test that exercises real collaborators (a real issued
`TokenService` token, a real `FakePersistence`-backed `PersistenceGateway`,
the real permission table) rather than a mock standing in for the boundary
being proven.

## 8. Definition-of-done coverage, closed in a second pass

The first pass covered every SC with at least one real test, but three were
narrower than the DoD's own wording asks for. Closed in a follow-up round,
same session:

- **SC-003** ("forged webhooks rejected for all seven sources") originally
  had forgery tests for two sources (Alertmanager, PagerDuty).
  `tests/unit/gateway/webhooks/test_router.py` now parametrises
  valid-signature, forged-signature, and missing-signature tests across all
  seven, each using that source's real mechanism (HMAC or shared secret),
  built from `core.domain.alerts.normalisation`'s own per-vendor payload
  shapes so the adapters are exercised too, not just the verifier.
- **SC-004** ("1,000-event storm bounded, with a complete shed record") had
  no test at all — `LoadShedder`/`ShedLog` were implemented (T053) but T055
  was never written. Added
  `test_a_1000_event_storm_is_bounded_with_a_complete_shed_record`: 1,000
  deliveries against the real `WEBHOOK_MAX_REQUESTS_PER_TEAM` limit (500),
  asserting exactly 500 admitted, exactly 500 shed and recorded with a
  reason, the admitted ones collapsing to one investigation via
  deduplication, and the shed count visible from `GET /health/ready`.
- **SC-006** ("cross-team access impossible through every route") covered
  investigations, config, and schedules. Added the same shape of test for
  runs (get + replay + list), interactions (list + answer), and the SSE
  stream endpoint. All pass against the existing `tenancy.visible()` /
  `_check_scope` checks with no further code changes — the first pass's
  fix (§3) already covered these, this just proves it per route rather than
  by inference.
- **SC-008** ("graceful shutdown loses nothing") tested that draining waits
  for in-flight runs and refuses new ones, but never checked that a
  completed run's result survives, or what happens to one still running
  past the grace period. Added: (a) a test that the persisted run row is
  read back with the right status and summary after a normal drain, and
  (b) a test where the investigation never finishes on its own — `drain`
  reaches for `investigator.cancel()` after the grace period, and the run
  is still recorded (not abandoned) with whatever the runner returned.

`make verify` was re-run after this round: same 10 pre-existing failures
(9 parametrisations of one LLM-transport network test, 1 file-permission
check on `install.sh`), confirmed unrelated before this feature's first
commit via `git stash`; nothing under `gateway/` or the new tests
introduced a new failure. Test count: 4179 → 4204 passed.
