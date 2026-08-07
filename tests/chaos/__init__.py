"""The chaos suite: real faults, a live cluster, and a score with a caveat.

Synthetic scenarios prove the agent reasons correctly over evidence somebody
recorded. This suite proves it against infrastructure failing for real reasons,
which is a different claim: live telemetry is noisier, carries signal nobody
thought to plant, and fails in ways nobody thought to record.

The pieces, in the order one experiment touches them:

``framework.lock``
    One suite per cluster. Two runs injecting faults into the same cluster
    would score each other's damage.
``framework.preflight``
    The cluster is healthy *before* the fault. An experiment run against an
    already-broken cluster measures the cluster.
``framework.injector``
    The declarative manifest applied, registered for removal before it exists.
``framework.alerts``
    The alert the fault raises, so the pipeline is entered where production
    enters it rather than through a side door.
``framework.validity``
    Did the injection actually produce its declared symptom? Without this,
    a flaky fault is indistinguishable from an agent regression, and that is
    the failure mode that makes a suite's number untrusted.
``framework.cleanup``
    The fault removed on success, on failure, and on interruption — and a
    label sweep for the run that was killed rather than stopped.
``runner``
    The whole cycle, once per experiment, scored on the evaluation
    harness's five axes.
"""

from __future__ import annotations
