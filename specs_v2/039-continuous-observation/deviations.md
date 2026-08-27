# Deviations — 039 Continuous Observation and Incident Lifecycle

Every place the implementation differs from `plan.md` or `tasks.md`, and why.
Recorded as they happened rather than reconstructed afterwards.

---

## 1. Two ports, not one — and the port count moved from thirteen to fifteen

**Planned.** The technical context says "Postgres: a bounded signal table with a
retention sweep, and incident tables beside the run tables". It does not say
whether those are new repository ports.

**Done.** Two: `SignalStore` (fourteenth) and `IncidentStore` (fifteenth), with
fakes, Postgres implementations, migrations `0006_signals` and `0007_incidents`,
contract suites, and rows in `test_tenant_isolation.py`.

**Why.** `platform/persistence/ports/__init__.py` is the whole export surface of
the storage layer and nothing above tier 3 may name a backend. A signal table
reached any other way would be the first storage in the deployment that a caller
could hold outside a transaction, and an incident table reached any other way
would be the first record with no tenant-isolation case.

`tests/unit/platform/persistence/test_port_conformance.py` asserts the count
deliberately — "a fourteenth is a specification change, not a refactor" — so the
number was moved with the same commit that added each port, and its docstring
now names both. That test is doing exactly what it was written for; changing the
number without a plan behind it is what it exists to catch, and there is a plan
behind it.

---

## 2. Signal retention is not a `DataClass`

**Planned.** "A bounded signal table with a retention sweep."

**Done.** `platform/observation/retention.py`, deriving the horizon from the
detector declarations, rather than a seventh `DataClass` in
`platform/persistence/ports/retention.py`.

**Why.** Every other data class has a window in *days*, configured by an
operator who decided how far back they want to be able to look. A signal's
window is in *minutes to hours* and is not a preference at all: a sample is
worth keeping exactly as long as some detector's window still reaches it, which
is a fact about the declarations. FR-004 says "long enough to evaluate every
detector's longest window, and no longer by default", and a day-granularity
setting beside the detectors could not express that — an operator who lengthened
a window and forgot to lengthen retention would own a detector that can never
fire and no way to tell that from a quiet estate.

Incident retention *is* a day-scale question and `RETENTION_DAYS_INCIDENTS`
exists for it; `IncidentStore.purge` is the operation, and only closed incidents
are removed.

---

## 3. Detectors live under `policies`, not in a seventh configuration section

**Planned.** "Detector definitions: configuration through the hierarchical
config service, validated against a schema."

**Done.** `policies.observation.detectors`, a typed list of `DetectorSettings`
on the existing `PoliciesConfig`.

**Why.** `platform/config_service/schema/root.py` says six sections and says why:
"that closure is what makes the rest of the feature possible — a reference to a
capability can be validated because there is one field it can appear in, and the
console can render a form because the shape is knowable". A seventh section
would have been a change to the tier table of configuration for something that is
a policy: whether this team watches for this, which is the same kind of decision
as whether this team's runs may write to memory.

---

## 4. Phases 1 and 2 landed in one commit

**Planned.** Eight phases, and the task list separates signals from detectors.

**Done.** `feat: give the deployment a memory of what it has been watching`
carries both.

**Why.** T-007 — "retention bounded to the longest detector window" — is a
phase-1 task whose implementation needs the phase-2 detector declaration to read
a window off. Landing phase 1 without it would have meant either a retention
module with a placeholder or a commit that did not satisfy its own task. Every
task was still done in order and test-first; only the commit boundary moved.

Phases 6 and 7 landed together for the mirror-image reason: suppression's
"recorded, never silent" and dispatch's rate limits both change
`DetectionIntake`, and splitting them would have meant landing an intake that
recorded suppressions and could not say why a dispatch was held.

---

## 5. `covers` gained a grace clause, which is a bug fix the plan did not
   anticipate

**What happened.** `SignalWindow.covers(seconds)` originally required the samples
to span the full duration. A source reporting every minute over a five-minute
window contributes samples spanning *four* minutes at best — the fifth would
have to land exactly on the boundary instant — so a detector whose duration
matched its source's interval could never fire at all.

**Done.** A window is also covered when its oldest sample is the first one after
the window opened, within one of that source's own declared intervals. The
reason is in the method's docstring, because the next person to read the first
clause will wonder about the second.

**Why it is recorded here.** It is arithmetic rather than a design change, but it
is the kind of thing that looks like a loophole to somebody tightening the
evaluator later, and a deviations file is where the reason for a suspicious-
looking line belongs.

---

## 6. Observations are computed at read time rather than stored

**Planned.** Not specified either way. `/v1/observations` is an endpoint the
console already read, and the fixture describes "what the detectors saw".

**Done.** `DetectorService.observations` evaluates every enabled detector against
the stored signals when the endpoint is called. There is no observation table.

**Why.** A table holding every verdict of every detector over every resource
would be the largest one in the deployment — at the declared scale that is a
hundred thousand rows a tick — and it would answer a question the signals
already answer. It would also answer it *worse*: a stored verdict is what was
true whenever something last wrote a row, and a computed one is what is true
now. Purity is what makes this possible at all; the same function the tick calls
is the one the endpoint calls.

**What this costs.** "What did this detector conclude last Tuesday" is answerable
only by replaying it — `replay()` exists and is tested — rather than by reading a
row. That is the trade, and it is the right way round: replay is exact and a
stored verdict is a copy that can disagree with the signals it came from.

---

## 7. The webhook route still starts its run directly

**Planned.** T-030 rewires every `/webhooks/*` route to raise an incident rather
than start a run directly. T-037 and T-038 put dispatch behind rate limits.

**Done.** The webhook route raises the incident through the lifecycle and
*attaches* the run to it, but still calls `start_investigation` rather than
`IncidentDispatcher`.

**Why.** The dispatcher's `RunStarter` is a protocol a composition root
satisfies, and the gateway's composition root starts a run by creating a
background task it tracks for graceful shutdown — `state.track(task)`, drained by
`lifespan`. Wiring the dispatcher in would have meant either moving that
draining into `platform/` (which cannot know about an ASGI lifespan) or giving
the gateway a second way to start a run. Both are worse than the honest gap.

**What this means.** An ingested alert is not subject to the per-team dispatch
limit today; a detected condition is, because the tick constructs the dispatcher
itself. The webhook path keeps its own load shedder and its deduplication window,
so it is not unbounded — but the two paths bound their dispatch differently, and
that is a real difference the unification has not finished removing. It is one
`RunStarter` implementation in the gateway's composition root away, and the
contract test that holds the two incidents against each other will keep them
honest about everything else in the meantime.

---

## 8. The global pause is on every surface but the console's screens

**Planned.** T-034: "Global pause stopping all detection without unconfiguring;
visible everywhere it matters."

**Done.** The pause is resolved from configuration, applied by the `Suppressor`
before anything else, reported on `TickOutcome` so a tick that found nothing can
say which kind of nothing, carried on the `/v1/incidents` and `/v1/detectors`
responses, and printed *above* both CLI listings rather than below them — an
operator reading an empty incident list has drawn a conclusion by the time they
reach a footnote, and the conclusion is that nothing is wrong.

**Not done.** The console reads `/v1/incidents`, so the flag is in the payload
its screens receive, and neither screen renders it.

**Why.** Rendering it is a design decision in a console that has a design system,
a component vocabulary and committed visual baselines. Inventing a banner here
would mean either picking a treatment nobody reviewed or reusing one that means
something else, and then re-accepting the baselines for it. The payload is there
and the decision is a small, reviewable console change; making it unilaterally
inside an observation feature is what would be wrong.

**What this means for the definition of done.** "Everywhere it matters" is
satisfied for the API, the CLI, and the tick's own record. It is not satisfied
for the console. That is a real gap and it is deliberate.

---

## 9. The four observation endpoints moved out of the console's projected list

**Not a deviation from the plan** — T-041 and T-043 imply it — but it is the
largest single ripple in the change and is worth writing down.

`console/src/lib/api.ts` said of `PROJECTED_PATHS`: "**The list shrinks.** When
an endpoint lands in the document it moves to `read` and comes out of here, and
the contract test fails until it does." Serving `/v1/incidents`,
`/v1/incidents/{incident_id}`, `/v1/detectors` and `/v1/observations` from the
gateway made that fail, correctly. So:

- `tools/mockplane/endpoints.py` marks the four as gateway-served;
- `tools/mockplane/capture/projection.py` renders them in the routes' own
  shapes — the detector gains its `signal`, the incident its `origin`, the
  timeline its `actor` and `cause`, and evidence values become strings;
- the console's four screens read through the generated client;
- `fixtures/contract/projected.json` loses the four paths and the schemas
  nothing references any more.

The fixture *content* is still Proxmox-shaped and still comes from the cluster
projection, because the homelab detector set is features 047 and 048 and this
feature's out-of-scope list says so. What moved is where the shape comes from:
the endpoints exist, so the fixtures are rendered in the shape the routes send
rather than in a shape nothing answered.

---

## 10. Two permissions were added

`incident.read` and `incident.manage`, with `fixtures/contract/roles.json`
regenerated. A viewer may read incidents; a responder may close and suppress one
and toggle a detector.

**Why not reuse `estate.read` and `estate.manage`.** They would have worked and
would have said something untrue: an incident is not a resource, closing one is
not opening a maintenance window, and a deployment that wanted to let somebody
read the estate without reading its incidents would have had no way to express
it. The responder holds the write half for the same reason they hold
`estate.manage` — deciding an incident is noise is an incident-time judgement,
and a list only an operator may close is a list that stops being read.

---

## 11. Two test modules were renamed for a basename collision

`tests/unit/platform/observation/test_detectors.py` collides with
`tests/unit/platform/masking/test_detectors.py`, and
`tests/unit/platform/incidents/test_lifecycle.py` with
`tests/unit/core/pipeline/test_lifecycle.py`. pytest imports test modules by
basename, so both broke collection of the whole suite while passing in
isolation.

Renamed to `test_detector_rules.py` and `test_incident_lifecycle.py`. Worth
recording because the failure is invisible when running one directory and
obvious only in a full run.

---

## Not deviations, recorded because they look like they might be

- **The tick's `covers` grace and the flap window are both bounds, and both are
  constants.** `FLAP_WINDOW_SECONDS` and `FLAP_CROSSING_THRESHOLD` are in
  `config/constants/observation.py` like every other bound. The grace is not a
  constant because it is not a policy: it is the source's own declared interval,
  carried on the sample.

- **`DetectorRegistry.set_enabled` toggles in-process and the gateway does not
  use it.** The registry's own docstring says persisting is a configuration
  write; the route therefore goes through `ConfigService.set_settings`, which
  keeps the audit line, the field locks and the approval gate. The in-process
  method stays because a worker composing a registry for one tick has a
  legitimate use for it and no configuration service to hand.

- **A dry run takes `incident.manage` rather than `incident.read`.** It writes
  nothing and fires nothing. It is how somebody decides whether to change a
  threshold, and it reads the team's own signals to do it; giving it the read
  permission would have made "test this detector" available to a role that
  cannot then act on the answer.

- **The evaluation tick has no worker loop.** `EvaluationTick`,
  `ObservationClaiming` and `tick_job` are the pieces; nothing in this feature
  runs them on a timer, exactly as `platform/estate/discovery/` ships a sweep
  and its claiming without a daemon. Composing a worker is a deployment
  question, and the scheduler's executor is what will do it.
