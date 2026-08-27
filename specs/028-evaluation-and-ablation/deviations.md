# Deviations — 028 Evaluation and Ablation

What was built differently from `plan.md` and `tasks.md`, and what was not built
at all. Written at the point of the implementing commit so the next person
reading the plan does not have to diff it against the tree to find out where the
two disagree.

Recorded per task instruction. Not committed (this whole directory is
gitignored, same as `spec.md`/`plan.md`/`tasks.md`).

Three sections: things done differently and why, things found wrong during
implementation, and things not done.

---

## 1. Deviations from the plan

### `strict` is an alias of the corpus's own `exact`, not a fourth mode

**Spec says** (FR-008): three matching modes, `strict`, `lcs`, and `set`.

**Feature 027 shipped**: `TRAJECTORY_MATCHINGS = {"exact", "lcs", "set"}`, and
every answer key in the corpus that names a mode names one of those.

**Shipped**: `matching.py` defines `STRICT`, `LCS`, `SET` and an alias table
mapping `exact → strict`. `normalise_mode` resolves either spelling; an
unrecognised one raises `UnknownMatchingMode` rather than defaulting.

**Why**: they are one comparison with two names. Adding `strict` as a *fourth*
mode would have meant either two implementations that must not drift, or a
schema-version bump on `answer.yml` and a rewrite of every shipped key — for a
rename. The alias is four lines and the vocabulary check stays exactly as strict
as it was.

`strict` keeps 027's shipped meaning: the golden steps in order and adjacent from
the start, with trailing steps counted as extra actions rather than failing the
match. The plan's own worked example still fails under it (`get_metrics`
interrupts the sequence), so nothing about the specified behaviour changed.

### Cost budgets are per-difficulty constants, not an answer-key field

**Spec says** (FR-006): tokens and wall clock, reported and gated separately.

**Shipped**: `SCENARIO_TOKEN_BUDGET_BY_DIFFICULTY` and
`SCENARIO_SECONDS_BUDGET_BY_DIFFICULTY` in `config/constants/evaluation.py`, with
`CostBudget.for_difficulty`. An answer key declares no budget.

**Why**: 027's `answer.yml` schema has no cost field, and adding one would have
been a schema-version bump plus an edit to all seven shipped keys, for a number
whose right value is a property of the *level* rather than of the incident. A
level-4 incident has more to read and more to rule out; holding it to a level-1
budget would fail every hard scenario on cost and leave the axis reporting the
curriculum instead of the agent. `score_cost` still takes a `CostBudget`, so a
caller with a per-scenario budget can pass one.

### One module the plan's project structure does not list

| Module | Why |
|---|---|
| `tests/harness/scoring/axes/result.py` | `AxisScore` is the shared vocabulary of the five axis modules, and `composite.py` — where the plan implies it lives — imports all five. Putting the type there means either a module-level cycle or a lazy import inside a function to hide one. A small module the axes and the composite both import is the honest version. |

Two entry points also live in modules the plan names rather than in new files:
`main()` for the CI gate is in `regression/ci.py` (the plan's own description of
that file is "CI entry point"), and `main()` for the benchmark tables is in
`benchmarks/export.py`, whose whole job is the artefacts those commands write.
Both are reachable as `python -m <module>`, so neither needed a `__main__.py`.

### Ablation switches are declared centrally and wired outward, not added per feature

**Tasks say** (T021, T022): "documented switches for [eight mechanisms]" and
"wire each switch to its owning feature's ablation control".

**Shipped**: `ablation/switches.py` declares all eight as a `MECHANISMS` table and
`MechanismSwitches` reaches each owning feature's *existing* control. Four of the
eight already publish a named switch (`MemoryPolicy`, `StrategyPolicy`,
`KnowledgePolicy` × 2). The other four had a documented "off" position that
predates this feature and no name for it, so this feature named them
(`masking`, `subagents`, `seed_calls`, `capability_planning`) without adding any
new control:

| Mechanism | The control it flips, which already existed |
|---|---|
| `masking` | `MaskingPolicy` at level `off` |
| `subagents` | no specialists passed to `ReActLoop`, so dispatch is not a tool |
| `seed_calls` | `EMPTY_SEED_CATALOGUE` — every source starts cold |
| `capability_planning` | `UNRANKED`, the neutral capability port |

**Why**: the alternative was adding four `*_SWITCH` constants and four policy
objects to tier-1 and tier-2 packages so the harness could enumerate them
uniformly. That is a test harness changing production packages to suit its own
table. The switch table records the control in prose (`Mechanism.control`) and a
test asserts every mechanism names one.

### The ablation runner takes an injected arm runner rather than composing a pipeline

**Plan says** (project structure): `ablation/runner.py — baseline plus one run per
ablation`.

**Shipped**: exactly that, with `ArmRunner` — an injected `async (Scenario,
MechanismSwitches, attempt) -> Observation` — doing the running.

**Why**: the same reason `surfaces/cli/client.py` and `gateway/http/services.py`
take an injected runner. Composing a deployment is feature 030's job, and a
harness that composed one would be a second composition root drifting away from
the real one the first time a port changed. Scoring stays inside the harness, so
every arm is scored by the same rule as the baseline — a caller that returned its
own `ScenarioScore` could hand back a number produced under a different rule.

### The corpus table, not a cross-model table, is what `make benchmark` produces

**Tasks say** (T044): `make benchmark` and `make benchmark-export` targets.

**Shipped**: both targets, defaulting to the scenario corpus scored on five axes
and rendered as a per-difficulty Markdown table with a provenance line. A stored
cross-model record can be rendered instead with `RECORD=<path>`.

**Why**: see §3 — a real cross-model run needs nine sets of credentials and real
token spend, so a `make benchmark` that defaulted to it would be a target nobody
in this repository can run. The corpus table is the number this repository can
produce today, offline, for nothing, and the cross-model path is the same command
pointed at a record.

### Two Makefile targets beyond the two the tasks name

`make evaluate` and `make record-baseline`, because T036 asks for a CI entry point
"with baseline reference" and T047 asks for the first release baseline to be
established and stored. Both are one command over `regression/ci.py`, and the
scheduled workflow calls `make evaluate` rather than spelling the invocation out
in YAML.

### `MIN_ATTEMPTS_FOR_VARIANCE` is 3, but the documented answer is 10

The constant is the floor below which the gate stops widening for noise at all.
The *usable* attempt count is higher, and §2 explains why. `docs/evaluation-
methodology.md` says so plainly rather than leaving a reader to infer that three
attempts is enough.

---

## 2. Things found during implementation

### The variance rule was wrong twice, and the corpus found both

The first implementation widened the tolerance by **the baseline's observed
standard deviation**. That is zero for a baseline that passed every attempt — and
a baseline that passed five times out of five at a true rate of 0.8 is not
thereby certain; that outcome happens a third of the time. SC-005 failed on the
first seed it was given: 100% then 80%, called a regression.

Fixed by widening on the **estimate's** uncertainty instead: the Laplace-smoothed
binomial standard error of *both* rates, combined. One imagined pass and one
imagined failure, so a perfect run does not become an impossible bar.

That surfaced the second problem. At three attempts a three-sigma smoothed error
is wide enough to forgive a drop from 100% to 0%, which is statistically true
(three failures after three successes is not remarkable) and useless as a gate. So
the allowance is capped at `MAX_FORGIVEN_DROP = 0.5`: past half the attempts there
is no sampling story worth waiting for another build to hear.

The sigma allowance also moved from two to three. At two the gate is wrong about
one comparison in twenty *by construction*, and a suite comparing a dozen
scenario-axis pairs per build would go red on noise most weeks — which is how a
gate gets widened until it stops gating.

Verified afterwards by sweeping 300 comparisons of an unchanged 80%-accurate
system at ten attempts each: **zero false positives**. The SC-005 test runs ten
pairs at ten attempts for the same reason — at five, "five out of five then two
out of five" happens often enough to appear in a fixture that size, and no honest
rule can call it a regression.

### A percentage on a tiny base put the gate permanently red

Found the first time `regression/ci.py` ran against the shipped corpus twice in a
row:

```
COST REGRESSION (3)
  database/006-connection-pool-exhaustion [cost] seconds rose from 0 to 0 (+39%)
  delivery/007-misleading-cpu-signal      [cost] seconds rose from 0 to 0 (+21%)
  kubernetes/002-liveness-probe-killing   [cost] seconds rose from 0 to 0 (+30%)
```

An offline scenario takes about thirty milliseconds; the next run takes
forty-two. That is a forty per cent rise and it is nothing at all, and a gate
reporting it would be red every other build over something nobody can fix. Added
`MEASUREMENT_NOISE_FLOORS`: a measurement has to clear both the share *and* an
absolute floor (200 tokens, one second, half a call) before it counts.

This is the clearest argument for the CI entry point's test running against the
real corpus rather than a fixture. A fixture would have had round numbers and
this would have shipped.

### Four of the seven shipped scenarios reach the right answer by a route their key does not name

Not a defect, and the first thing the five-axis scorer said when pointed at the
corpus:

```
  deviation: observability/005-dependency-timeout   reached the right answer by a route the key does not name
  deviation: database/006-connection-pool-exhaustion reached the right answer by a route the key does not name
  deviation: kubernetes/003-rollout-regression       reached the right answer by a route the key does not name
  deviation: delivery/007-misleading-cpu-signal      reached the right answer by a route the key does not name
```

This is SC-009 demonstrated on real data on the first run rather than on a
fixture built to demonstrate it. All four pass every axis; the deviation is
reported and gates nothing.

### Topology turned out to move two axes, and the test had to be rewritten to say so

The proof scenario originally asserted that topology guidance "shortens the route
without changing the answer". It does not. On a scenario with iterations to spare
it is a pure route change; on the tight level-3 budget the call it saves is the
one that reaches the cause, so it buys accuracy as well.

The assertion was wrong, not the code. Rewritten to assert what is true — zero
accuracy contribution at level 1, positive at level 3 — which is a better test,
because it is the clearest case in the repository for why contributions are
reported per axis *and* per difficulty rather than as one number per mechanism.

### The stated test baseline was stale

The task brief said the suite stood at 4,223 passed. `git stash` on a clean tree
collects **8,607**. This feature adds 137 tests, for 8,744 collected and 8,729
passed / 15 skipped with `make verify` green. Checked for duplicate collection
(none) before concluding the brief's figure was simply out of date.

---

## 3. Things not done

### T040 and T042 — the cross-model table is exercised, not measured

`benchmarks/models/comparison.py` runs the corpus across all nine providers,
refuses a non-canonical runtime, and produces a table; the test asserts nine rows
covering exactly `SUPPORTED_PROVIDERS`. What it does *not* do is spend real
tokens against nine live providers, because that needs nine sets of credentials
and money the constitution keeps out of the gate.

So SC-008 is satisfied as "the comparison produces a table covering all nine
providers" and not as "here are nine measured numbers". The first real cross-model
run will be the first time the path is exercised against live providers — the
same position feature 027 recorded for live-provider recording.

### T039 — the Cloud-OpsBench dataset is not vendored

The adapter is implemented, tested, and takes a path. The dataset itself is its
authors' work; vendoring it would put a file this repository cannot redistribute
into the test tree and make the suite depend on it. The tests write their own
dataset in the shape the adapter reads and read it back, which exercises every
line of the loader including all five field aliases and both refusal paths.

### `models/` and `cloudopsbench/` are one module each, not packages of several

The plan's structure draws them as directories. Each holds a single module
(`comparison.py`, `dataset.py`) because that is what the behaviour came to. A
second benchmark adapter is a second module beside `dataset.py`, which is the
shape the port was built to support and what the docstring claims.

### T051 — `docs/provenance-map.md` not touched, and there is no `make check-provenance`

Per `CLAUDE.md` that file is gitignored and never linked from a committed file, so
editing the local copy would have no effect on what ships. There is no
`check-provenance` target in this repository's `Makefile`. The general-audience
documentation this feature ships is `docs/evaluation-methodology.md`, which covers
the five axes, the matching modes, the eight mechanisms, the variance rule, the
gates, baselines, and how to reproduce a published number — with no reference to
any prior-art project, per the naming rule.

### The ablation's proof runs against a policy double, not a live model

`tests/synthetic/test_ablation_value_scenario.py` runs the full nine-arm ablation
over the real hook registry, the real `MemoryService` on a real populated episode
corpus, the real knowledge-guidance hook, the canonical `ReActLoop`, real
capability registrations, and the same five-axis scorer the gate uses. The only
double is the model, and it is a deterministic *policy* that reads the system
prompt the hooks actually built and the recall results the tools actually
returned — not a script with the answer written into it.

What that measures is the **mechanism**: a synthesised anti-pattern warning
reaching the agent early enough to change the trajectory. Whether a real model
exploits it as reliably is what a live ablation run would measure, and that needs
token spend the gate does not have. The claim the harness supports today is
therefore "the mechanism reaches the agent and changes the outcome, and here is
the number", not "a production model gains N points". The distinction is stated
in the test's own module docstring rather than left to a reader.

The measured result on that corpus, for the record:

```
memory_read      accuracy +50%   adversarial +50%   trajectory +50%   (level 3: +100%)
memory_strategy  accuracy +50%   adversarial +50%   trajectory +50%   (level 3: +100%)
topology         accuracy +50%   adversarial +50%   trajectory +50%   (level 3: +100%)
knowledge_base, masking, subagents, seed_calls, capability_planning
                 no measurable effect on any axis
```

The five zeros are as much the point as the three contributions: this corpus does
not exercise those mechanisms, and a harness that could not produce an honest zero
could not produce an honest number either.

### The first release baseline is recorded at one attempt per scenario, not ten

`tests/synthetic/baselines/release.baseline.json` was recorded with
`--attempts 3`. The offline corpus is deterministic by construction — a replayed
transcript has nothing left to sample — so repeat attempts add no variance
information on that path and cost wall clock the pull-request gate would pay. The
scheduled workflow passes `ATTEMPTS=5` by default and the documentation says ten
is what a variance-aware comparison over a *live* provider wants.

### SC-005 is verified over a simulated stochastic system, not the real one

The criterion says "verified by running an unchanged codebase N times". The
offline corpus cannot demonstrate it, because it is deterministic and would pass
trivially. So the gate's noise behaviour is verified against a seeded stochastic
fixture at a known true pass rate — ten pairs in the test, and a 300-comparison
sweep during development that found zero false positives. That is a stronger test
of the *rule* than ten runs of a deterministic corpus would be; it is not the same
thing as ten runs of a live model, and that run has not happened.
