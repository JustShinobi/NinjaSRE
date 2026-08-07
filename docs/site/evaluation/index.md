# Evaluation methodology

The central claim here is a measured one: that NinjaSRE learns from the incidents
it has seen, and that the learning helps. A number nobody outside the project can
reproduce is a marketing claim, not evidence. This page is what makes it
reproducible — the exact commands, what each one measures, and what to compare
the result against.

You need a checkout and Python 3.12. You do **not** need a cluster, a credential,
or a model provider for the corpus runs: the scenarios are deterministic fixtures
with answer keys, and they run offline.

## Reproducing the corpus result

```sh
git clone https://github.com/ninjasre/ninjasre.git
cd ninjasre
make install
make test-synthetic
```

That runs every scenario in `tests/synthetic/` and reports pass or fail per
scenario. Narrow it while you are working:

```sh
make test-synthetic FILTER=005-dependency-timeout
make test-synthetic DIFFICULTY=hard
make test-synthetic INTEGRATION=datadog
```

## Reproducing the scores

`test-synthetic` answers *did it pass*. Evaluation answers *how well, on five
independent axes, compared to a stored point*:

```sh
make evaluate
```

Each attempt is scored on accuracy, evidence, adversarial handling, trajectory,
and cost. They fail for different reasons and have different fixes, which is why
there are five numbers rather than one — an agent that reaches the right cause
after twenty redundant calls and one that reaches the wrong cause in three both
score badly on a single boolean, and the person holding it has to re-run the
scenario to find out which they have.

`make evaluate` compares against the baseline named `release` and fails when a
score regresses. To compare against your own point instead:

```sh
make evaluate BASELINE=my-branch
make record-baseline BASELINE=my-branch NOTE="before the ranking change"
```

Baselines are stored in the repository, so the number this project publishes and
the number you compute are compared against the same recorded reference rather
than against each other's memory of it.

Variance is real: run it more than once before believing a small difference.

```sh
make evaluate ATTEMPTS=5
```

## Reproducing the learning claim

This is the part that matters, and it is the part a reader should be most
sceptical of. "It learns" is measured by *ablation*: run the same corpus with one
mechanism switched off, and report the difference.

Eight mechanisms can be ablated one at a time — episodic recall, strategy
synthesis, the topology graph, the knowledge corpus, masking, sub-agents, seed
calls, and capability planning. **Off means absent**, not installed-and-returning-
early: a no-op hook still changes the shape of what the model sees, and an
ablation that left one in place would measure the hook rather than the mechanism.

Each arm's contribution is the delta between it and the full system on the same
corpus, with the same attempts. A mechanism whose delta is zero is a mechanism
that is not earning its complexity, and the apparatus is built to make that
discoverable rather than deniable.

`docs/evaluation-methodology.md` documents each axis' pass condition, the three
trajectory-matching modes, and what each ablation switch reaches — read it before
disagreeing with a number, because most disagreements are about what the number
measures.

## Reproducing the cross-model benchmark

```sh
make benchmark
```

Produces the table of how the corpus scores across models on the canonical
runtime. Only the first-party ReAct loop produces an evaluation number;
alternative runtime adapters are experimental and are never the default, so a
number from one is not comparable and is not published as though it were.

## What the corpus is, and what it is not

The scenarios are deterministic fixtures: an alert, the observability data an
investigation would find, and an answer key stating the root cause, the evidence
a correct investigation must collect, and the confounders it must rule out.

**They are not production traffic.** A scenario suite measures what its authors
knew to put in it, which is why the chaos and end-to-end suites exist — they
break a real cluster on purpose, and every failure mode they find that the corpus
did not contain is captured *into* the corpus, where it then runs on every
change. That loop is the honest answer to "your benchmark is your own homework".

Running those needs infrastructure and one of them spends money:

```sh
make chaos-setup
make chaos-run INVESTIGATOR=your.deployment:build
```

Without infrastructure they skip with a message naming what is missing, rather
than failing — a suite that goes red on every laptop is a suite somebody deletes.

## Disagreeing with a number

The useful form of disagreement is a scenario. If you believe the corpus is
missing a case that would change the result, the way to demonstrate it is to add
one: an alert, its observability fixtures, and an answer key. The suite is
parameterised over the corpus directory, so a scenario is a directory and no
other file changes.

That is also the mechanism by which a number nobody can reproduce becomes a
number two people can argue about with the same evidence in front of them.
