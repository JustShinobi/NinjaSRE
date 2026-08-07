# Synthetic scenarios

A scenario is a directory of recorded vendor responses, an alert, and an answer
key. Running one drives the whole investigation — the six pipeline stages, the
canonical ReAct loop, the real capabilities, the real integration clients, the
real credential proxy — against those recordings, with no credential, no
network, and (offline) no tokens.

This is the substrate the evaluation half of the platform stands on. A number
that came from a smaller pipeline would be a number about the harness.

```bash
make test-synthetic                      # the whole corpus, offline
make test-synthetic FILTER=liveness      # one scenario
make test-synthetic DIFFICULTY=4         # one rung of the curriculum
make test-synthetic ATTEMPTS=5           # variance
```

## What a scenario is

```
tests/synthetic/<suite>/<NNN-name>/
├── scenario.yml       what this incident is, and what can be seen of it
├── alert.json         the trigger, in the shape its source really sends
├── <integration>.json recorded vendor responses, one file per integration
├── answer.yml         the ground truth
└── transcript.json    a recorded model transcript, so it runs with no provider
```

Nothing registers a scenario. Discovery walks for `scenario.yml`, so
contributing one for a new integration is adding a directory — no harness edit,
no list to append to, and no credential to write: the vault-valid credential is
generated from the integration's own declared schema.

### `scenario.yml`

```yaml
schema_version: "1"
scenario_id: 002-liveness-probe-killing
base: 000-healthy              # optional; inherit and override only what differs
title: a liveness probe restarts a healthy container
failure_mode: probe_misconfiguration
severity: critical
scenario_difficulty: 2
adversarial_signals: [healthy_replicas_present, benign_prior_event]
available_evidence: [kubernetes]
integrations: [kubernetes]
team_id: payments
```

Every vocabulary is validated at load time. `failure_mode`, `severity`, and
`adversarial_signals` are closed sets; `available_evidence` is checked against
the integrations the repository actually ships plus the sources that belong to
no vendor. A typo is a load error naming the file and the field, not a silent
mismatch that scores as a miss six months later.

### `answer.yml`

```yaml
root_cause_category: configuration_error
required_keywords: [liveness, probe, restart]
model_response: |
  ROOT_CAUSE: the liveness probe's timeout is shorter than the endpoint's
  cold-start latency, so Kubernetes restarts a container that is working.

# every one of these is optional, and asserting nothing is better than
# asserting something nobody checked
equivalent_root_cause_categories: [capacity_limit]
forbidden_categories: [resource_exhaustion, healthy, unknown]
forbidden_keywords: [disk full]
ruling_out_keywords: ["no OOMKilled", "memory is within"]
required_evidence_sources: [kubernetes]
required_queries: [checkout]
optimal_trajectory: [kubernetes_workload_events, kubernetes_rollout_history]
golden_trajectory:
  ordered_actions: [kubernetes_workload_events, kubernetes_rollout_history]
  matching: lcs          # exact | lcs | set
  max_edit_distance: 1
  max_extra_actions: 1
  max_redundancy: 0
max_investigation_loops: 4
```

`root_cause_category` and every trajectory action are checked against the
*running* system: the shipped taxonomy and the live capability catalogue. A
renamed capability therefore breaks the build in the change that renamed it,
naming the scenario to update — rather than quietly scoring as a trajectory
miss.

`ruling_out_keywords` is the adversarial axis. It asserts that the agent
explicitly dismissed the planted confounders rather than never considering them,
which is what makes "resistance to misleading evidence" reportable separately
from plain accuracy.

### Evidence fixtures

```json
{
  "integration": "kubernetes",
  "responses": [
    {
      "match": { "method": "GET", "path_contains": "/events" },
      "status": 200,
      "content_type": "application/json",
      "body": { "items": [{ "reason": "OOMKilled" }] },
      "adversarial_signals": ["healthy_replicas_present"]
    }
  ]
}
```

Matching is by substring over the method, URL path, query, and body, and the
*narrowest* matcher wins whatever the file order — so a fixture can record a
broad answer for an endpoint family and a precise one for the call the incident
turns on. A call nothing matches gets an empty-but-valid response of the right
shape, never an error: an agent exploring beyond a scenario's evidence should
learn "there is nothing there", because "the tool is broken" changes its
behaviour in ways the answer key never anticipated.

`adversarial_signals` on a response says which planted confounder *this*
response carries. A scenario that declares a confounder no response carries
fails to load, so the suite can never report resistance to evidence nobody was
shown.

## The difficulty curriculum

| Level | Definition |
|---|---|
| 1 | A single obvious cause with corroborating evidence. |
| 2 | One planted confounder that must be explicitly ruled out. |
| 3 | Several plausible causes requiring evidence to discriminate. |
| 4 | The most prominent signal is misleading; the true cause is secondary. |

Levels 2 and above must declare at least one adversarial signal, and must assert
`ruling_out_keywords` — otherwise the label is a claim rather than a property.

Results are reported per level, because an improvement that helped everywhere
and one that helped only on the easy cases are different findings and a single
accuracy number cannot tell them apart.

## Recording fixtures from a live vendor

A fixture written by hand is what its author believed the vendor sends. That is
the same document right up until the vendor adds a field, renames one, or starts
paginating — and then the suite passes against a shape nothing produces. So
fixtures are recorded.

1. **Stand the integration up against the real vendor**, with a credential that
   can read what the scenario needs and nothing else. Read-only, and scoped to a
   test account or a test namespace: the recording will be committed.
2. **Put `RecordingSender` in front of the real sender.** It satisfies the same
   port the mock boundary does and sits in the same place in the proxy, so a
   recording session and a replay session are one code path with one object
   swapped:

   ```python
   from tests.harness.backends.recording import RecordingSender

   recorder = RecordingSender(inner=live_sender, hosts=host_map, secrets=used_values)
   # ... build the proxy engine with sender=recorder, run the capability ...
   recorder.write(Path("tests/synthetic/<suite>/<NNN-name>"))
   ```

3. **Everything is scrubbed before it is written.** The credential values the
   session used are removed by identity; AWS key identifiers, JSON Web Tokens,
   `Authorization` values echoed into a body, PEM blocks, signed-URL signatures,
   and named secret fields are removed by pattern. The document's *shape* is
   preserved, because the shape is the thing the recording exists to capture.
4. **Read the diff before committing it.** Scrubbing is eager and it is not a
   substitute for looking: a false positive costs one unreadable field, and a
   false negative costs the repository a live credential in its history.
5. **Narrow the matchers.** A recorded `path_contains` is the whole path, which
   is usually narrower than the scenario needs. Trim it to the part that
   identifies the endpoint so the fixture survives a client adding a query
   parameter.
6. **Run the scenario and check nothing fell through.** Every recorded response
   should be reached; a fixture that never matches means the scenario is
   measuring the empty fallback, and the corpus test asserts this.

## Recording a model transcript

Offline mode is what makes regression gating affordable: a suite that spent
tokens on every pull request is one somebody eventually turns off, and a gate
nobody runs gates nothing.

```python
from tests.harness.offline import TranscriptRecorder, write_transcript

recorder = TranscriptRecorder(inner=real_llm_client)
await run_scenario(scenario, llm=recorder)
write_transcript(recorder.transcript(), scenario.directory / "transcript.json")
```

The recorder wraps the live client rather than reimplementing it, so whatever
the provider really returned is what lands in the file. Replaying it runs the
same investigation with the provider removed and spends nothing.

A replay that runs past its transcript raises rather than inventing a closing
turn. The run has diverged from the one that was recorded, and reporting that as
a scenario failure would blame the agent for a stale fixture.

## Verdict records

Off by default. Set `NINJASRE_SCENARIO_ARTIFACTS` to a path — or pass
`--artifacts` — and every attempt appends one JSON line carrying what the answer
key asked for, what the run actually did, and the difference per axis: the
trajectory, the evidence sources, every vendor call with whether a fixture
answered it, the iteration count, the pipeline outcome, and the determinism
profile the run was made under.

The point is that somebody who was not there can read one line and say what went
wrong. A record that only said `false` would send them back to the corpus with a
stopwatch.

## Mock backends

A backend declares two things: which integration it speaks for, and what that
vendor answers when it has nothing to report. Everything else comes from the
fixtures.

An integration with no backend module is not broken — it gets the generic JSON
vendor, whose empty document is `{}`, and that is the right answer for the many
clients that read a document and treat an empty one as "nothing to report". A
module is worth writing when the empty answer has a *shape*: a Kubernetes list
with an empty continue token, a Prometheus result envelope, an AWS
query-protocol XML document, an Elasticsearch hit envelope reporting zero hits.

Adding one is adding a module under `tests/harness/backends/` that exposes
`BACKENDS`. Discovery walks the package; nothing registers.

## Adding a scenario

1. Create `tests/synthetic/<suite>/<NNN-name>/`.
2. Record the vendor responses, or write them and plan to re-record.
3. Write `scenario.yml`, `alert.json`, and `answer.yml`.
4. Record a transcript so the pull-request gate can run it for free.
5. `make test-synthetic FILTER=<name>`.

No harness code, and nothing to register.
