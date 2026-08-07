# Evaluation and ablation

How NinjaSRE is measured, precisely enough that somebody who did not write it can
reproduce a number and disagree with it.

The claim this document exists to support is that NinjaSRE learns from the
incidents it has seen. That is an ordinary marketing sentence right up until
somebody asks *how much*, at which point it either has a number behind it or it
does not. The apparatus below is what puts a number behind it — and, just as
importantly, what makes it possible to discover that a mechanism is worth nothing
or is actively harmful.

## The five axes

Every attempt at every scenario is scored on five axes that fail independently.

| Axis | Passes when | Reported detail |
|---|---|---|
| **accuracy** | The root-cause category is one the answer key accepts, every required keyword appears in what the agent said, no forbidden category was chosen, and no forbidden keyword appears | Which keywords were missing; which forbidden category was matched |
| **evidence** | Every source the key requires was actually collected, and every validated claim cites an evidence entry the run holds | Which sources were never reached; which claims cite nothing real |
| **adversarial** | Every ruling-out keyword appears, showing the planted confounders were dismissed rather than unnoticed | Which confounders were never mentioned |
| **trajectory** | The route is within the answer key's edit distance, extra and redundant calls are within their limits, and the loop count is within the key's ceiling | The route taken, the diff, and four counts |
| **cost** | Tokens and wall clock are inside the budget for that difficulty level | Actual against budget, on both |

A scenario passes only when every axis it *asserted* passes. An axis the answer
key says nothing about is reported as unasserted rather than folded in as a free
win — a suite whose adversarial number was mostly scenarios that planted no
confounder would flatter the agent and measure the corpus.

**Why five rather than one.** They fail for different reasons and the fixes are
different. An agent that reaches the right cause after twenty redundant calls has
an efficiency problem; one that reaches the wrong cause in three has an accuracy
problem; a single boolean says the same thing about both, and the person holding
it has to re-run the scenario to find out which they have.

## Trajectory matching

The answer key names the route an ideal investigation takes and how close still
counts. Three modes:

| Mode | Means |
|---|---|
| `strict` (spelled `exact` in fixtures) | The golden steps in order and adjacent, from the start. Trailing steps count as extra actions rather than failing the match. |
| `lcs` | The order without the adjacency: how many insertions and deletions separate the two, against `max_edit_distance`. |
| `set` | The actions, ignoring order entirely. |

A *position* is whatever the loop ran in one iteration, not one call. A parallel
batch is compared as an unordered set within its position, because the runtime may
schedule a batch however it likes and comparing calls would make the score depend
on which coroutine finished first.

Extra calls and redundant calls are counted separately. An action the golden path
does not mention is wandering; an action taken twice is looping. They are
different defects with different fixes, and adding them together produces a number
nobody can act on.

**A different valid route is a deviation, not a failure.** An investigation that
skipped a golden step and still reached the right cause is reported as a
trajectory deviation with the accuracy axis untouched. Whether the deviation is
acceptable is what the key's `max_edit_distance` says, and that is a decision its
author made in writing.

## Ablation

Eight mechanisms can be switched off, one at a time, over the same corpus:

| Mechanism | What removing it does |
|---|---|
| `memory_read` | Episodic recall is not consulted. The corpus stays populated and stays written to, so this isolates recall rather than measuring the pre-memory system. |
| `memory_strategy` | No playbook is synthesised or served. Generation and retrieval go together: an arm that could retrieve but not generate would report whatever happened to be cached. |
| `topology` | The dependency-graph guidance is not appended and the retrieval path is unreachable. |
| `knowledge_base` | The runbook corpus is not searched. |
| `masking` | Identifiers are sent unreplaced, so masking's quality cost is measured rather than assumed. |
| `subagents` | No specialists are offered, so dispatch is not a tool rather than a tool that refuses. |
| `seed_calls` | Every alert source starts cold. |
| `capability_planning` | The catalogue arrives unranked. |

Each switch reaches the owning feature's own control — the policy object it
already publishes — rather than a second control beside it. **Off means absent.** A
disabled mechanism is not installed and returning early: a no-op hook still
dispatches, still appears in the trace, and still perturbs the ordering the
trajectory scorer reads.

Every arm records the configuration it ran under, and the property that makes the
whole table trustworthy is checked mechanically: flipping one switch must move
exactly one key in that record. An arm that differed from the baseline in two
respects would attribute the sum of two effects to one mechanism, with nothing in
the report saying so.

### Reading a contribution

A contribution is a subtraction: the baseline's rate minus the rate the arm
without the mechanism achieved. **Positive means the mechanism helped.** One
convention, obeyed everywhere.

Three things the report refuses to do:

- **Price an arm that did not run.** A mechanism whose arm failed appears under
  "not measured" and nowhere else. A broken experiment and a null result look
  identical in a table and mean opposite things.
- **Dress noise as a finding.** A difference inside the noise floor is reported as
  "no measurable effect" rather than as a number with two decimal places.
- **Bury a harmful mechanism.** A negative contribution is flagged *above* the
  table. Discovering that a mechanism degrades hard scenarios is exactly what the
  harness is for, and the response is to fix or disable it.

## Variance and gating

The system is stochastic, so a single run is not evidence. Attempts are repeated,
every rate carries a spread, and a regression has to clear three hurdles before it
fails a build:

1. **A tolerance** — a fixed share, because some movement is always expected.
2. **The uncertainty in both rates** — the Laplace-smoothed standard error of each
   measured rate, times a three-sigma allowance. Smoothed, because a baseline that
   passed five times out of five is not thereby certain: five successes at a true
   rate of 0.8 happen a third of the time, and a gate that read that as certainty
   would fail the next honest run.
3. **An absolute floor, for measurements** — a percentage on a tiny base is not a
   measurement. An offline scenario that took thirty milliseconds and then
   forty-two has risen by forty per cent and by nothing at all.

The allowance is also capped: past half the attempts there is no sampling story
worth waiting for another build to hear.

Below three attempts the gate falls back to the bare tolerance rather than
pretending a couple of samples have statistics. **A variance-aware comparison
wants ten attempts per scenario.** At five, an unchanged 80%-accurate system
produces "five out of five, then two out of five" often enough to matter, and no
honest rule can call that a regression.

### Three gates, not one

| Gate | Fails when |
|---|---|
| **correctness** | accuracy, evidence, or adversarial drops beyond tolerance |
| **trajectory** | the route lengthens: edit distance, loop count, or redundant calls rise beyond tolerance |
| **cost** | tokens or wall clock rise beyond tolerance |

Separate, so a change that improves accuracy at triple the price is visible as the
trade-off it is rather than as a silent pass — and so a cost regression cannot be
waved through by an accuracy improvement arriving in the same commit.

Every failure names the scenario and the axis. "The suite got worse" sends
somebody to read forty scenarios; "kubernetes/003 regressed on accuracy" sends
them to one.

## Baselines

A baseline is a stored suite result with an identifier, so "compared to what?"
always has an answer that survives the shell that produced it. Baselines are JSON
files in a directory — something a release can commit and a bisect can check out.

Every baseline records the **corpus version**: a digest of which scenarios it
covered. Comparing across two different corpora is refused rather than subtracted,
because a fixture change and an agent regression look identical in a pass rate and
mean opposite things. A corpus change requires a new baseline, which makes the
distinction explicit rather than a matter of somebody remembering.

## Benchmarks

An external benchmark asks a different question from the scenario corpus. The
corpus is ours — we wrote the incidents and the answer keys, so a number from it is
only as honest as the people who chose the fixtures. A published benchmark is
somebody else's, which is what makes it worth running and why it gets an adapter
rather than a fork.

Benchmark datasets are not vendored; the adapter takes a path to one the operator
downloaded. Cross-model comparison runs the same cases across every supported
provider, including the ones expected to do badly, because the shape of the
trade-off is made of the low rows as much as the high ones.

**Benchmark numbers come from the canonical runtime only.** Alternative runtimes
exist so a team can migrate; they never produce a published number, because a
score that could have moved because the runtime changed measures nothing. The
guard fires before the first case runs, not after — refusing once the tokens are
spent would make the refusal a formality.

## Running it

```sh
# Score the corpus on five axes and gate it against a stored baseline.
make evaluate BASELINE=release ATTEMPTS=10

# Establish a new baseline (do this when the corpus changes).
make record-baseline BASELINE=v0.29.0 NOTE="after the topology change"

# Produce the publishable table, and splice it into a document.
make benchmark
make benchmark-export INTO=docs/evaluation-results.md
```

The whole of the above runs offline against recorded transcripts, for zero tokens.
That is deliberate and it is what makes the gate affordable enough to run at all:
a gate that spent tokens on every schedule is a gate somebody eventually turns
off, and a gate nobody runs gates nothing.

## What has been measured so far

The first quantified learning claim, stated with the caveat that makes it honest.

Running the nine-arm ablation over a four-scenario corpus spanning difficulty 1
and 3 — through the real hook registry, a real populated episode corpus, the real
knowledge-guidance hook, and the canonical loop:

| Mechanism | accuracy | adversarial | trajectory | at level 3 |
|---|---|---|---|---|
| `memory_read` | +50% | +50% | +50% | +100% |
| `memory_strategy` | +50% | +50% | +50% | +100% |
| `topology` | +50% | +50% | +50% | +100% |
| `knowledge_base` | — | — | — | — |
| `masking` | — | — | — | — |
| `subagents` | — | — | — | — |
| `seed_calls` | — | — | — | — |
| `capability_planning` | — | — | — | — |

All three contributions are concentrated at level 3, where the iteration budget is
tight enough that knowing which approach *not* to take is the difference between
reaching the cause and running out of loops. At level 1 there is budget to work
through every backend, so all three contribute nothing — which is a finding, and
the reason contributions are reported per level rather than as one number each.

**The five dashes are as much the point as the three rows.** This corpus does not
exercise those mechanisms, and the report says "no measurable effect" rather than
attributing a percentage point to whichever way the noise fell. A harness that
could not produce an honest zero could not produce an honest number either.

**The caveat.** The model in that run is a deterministic policy, not a production
model. It reads the system prompt the hooks actually built and the recall results
the tools actually returned, and decides from what is there — so the arms differ
*because* a mechanism was removed rather than because a fixture said so. What this
measures is the mechanism: a synthesised anti-pattern warning reaching the agent
early enough to change the trajectory. Whether a given production model exploits
it as reliably is what a live ablation run measures, and that run has not happened
yet. The claim above is therefore "the mechanism works and here is its size on
this corpus", not "model X gains fifty points".

## Reproducing a published number

A number is reproducible when four things are stated with it, and every artefact
this harness writes carries all four:

- **the corpus version** — which scenarios, at which revision of their answer keys;
- **the runtime** — always the canonical one for a published number;
- **the attempt count** — because a mean without its sample size is not a mean;
- **the determinism profile** — temperature, top-p, seed, reasoning effort, and
  whether prompt caching was on.

Given those, `make evaluate` on the same commit produces the same table. Given a
different model, it produces a different table and says which model produced it.
Neither is a claim about the other, which is the entire reason the four are
recorded rather than assumed.
