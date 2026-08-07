"""Running the same corpus with one mechanism removed, so its worth is a number.

Constitution Article VII forbids claiming a learning mechanism that has not been
measured. Everything in this package exists to make that enforceable rather than
aspirational: without an ablation harness "memory helps" is a sentence somebody
wrote in a README, and the only way to check it is to delete the feature and run
the suite twice by hand.

Three properties are what make the resulting numbers worth publishing.

**One difference.** An arm differs from the baseline in exactly one respect. Each
switch reaches the owning feature's own control — the policy it already publishes
— rather than a second control beside it, and the configuration every arm ran
under is recorded so "identical in every other respect" is checkable.

**Off means absent.** A disabled mechanism is not installed and returning early.
A no-op hook still dispatches, still appears in the trace, and still perturbs the
ordering the trajectory scorer reads; "off" has to be the code path a deployment
without the feature takes.

**A negative result is a result.** A mechanism whose removal *improves* the score
is flagged at the top of the report. That is the finding the harness is most
valuable for and the one it would be easiest to bury.

``switches``
    The eight mechanisms, and the value that holds one arm's configuration.
``config``
    Declarative, file-backed, reproducible arm definitions.
``runner``
    The baseline plus one run per arm, over one corpus.
``report``
    Contribution per mechanism, per axis, per difficulty, with the harm flag.
"""

from __future__ import annotations
