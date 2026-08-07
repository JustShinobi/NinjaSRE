"""Scoring one attempt on five axes that fail independently.

The requirement this package exists for is negative: it must not be possible to
report a scenario as "failed" and leave the reader to run it again to find out
on what. An agent that reaches the right root cause after twenty redundant calls
has an efficiency problem; one that reaches the wrong one in three calls has an
accuracy problem; and a single boolean says the same thing about both.

So the axes are scored separately, reported together, and combined only at the
last step (FR-007) — and even then the composite keeps every axis result rather
than collapsing to the verdict.

``matching``
    Golden-trajectory comparison in three modes, with parallel batches treated
    as unordered sets within their position.
``axes``
    One module per axis. Each takes plain observations rather than a pipeline
    run, so a scorer can be tested without standing up an investigation.
``composite``
    ``ScenarioScore``: the five axes for one attempt, and the rule that a
    scenario passes only when every axis it asserted passed.
``report``
    ``SuiteScore``: many attempts aggregated, with the variance that makes a
    single lucky run distinguishable from an improvement.
"""

from __future__ import annotations
