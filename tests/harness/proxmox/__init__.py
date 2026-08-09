"""The hypervisor scenario suite: what it adds to the harness beside it.

The general scenario harness scores an investigation on five axes and does it
well. This package does not replace any of that. It adds the half a hypervisor
needs and a reporting system does not.

``verdicts``
    Four closed vocabularies. The one that matters is ``ActionVerdict``:
    correct, harmful, unnecessary, absent. A wrong diagnosis on somebody's
    homelab costs an hour; a wrong action costs a filesystem, and a scheme that
    reports the second as "diagnosis correct" is measuring the wrong half.
``declaration``
    What a scenario has to say before it may be scored — the situation, the
    fixtures, the true cause, the evidence, the correct response, the red
    herrings — with the checking where the scenario is written.
``readings``
    The shipped investigation tools, run for real over recorded API responses.
    This is what makes the corpus catch a change to the system rather than only
    a change to a model, and what makes a rotted fixture a loud failure.
``transcripts``
    What one model produced under one ablation arm, recorded.
``scoring``
    The deterministic scorer, with the reasoning kept beside every verdict.
``report``
    Aggregation that cannot hide a scenario going from correct to harmful.
``baseline``
    The committed scores, and the gate that compares a run against them.
``coverage``
    Every hypervisor write exercised by at least one scenario, asserted.
``laboratory``
    The two-node cluster the destructive scenarios need, and the restore
    between them.
``suite``
    Loading the corpus and running it, for both front doors.
"""

from __future__ import annotations
