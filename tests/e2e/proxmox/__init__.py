"""The half of the hypervisor suite that needs a cluster it is allowed to break.

Some of these conditions cannot be faked. A thin pool whose metadata is
genuinely exhausted behaves differently from a recording of one, and the
difference is exactly where a system that writes to a hypervisor is most likely
to be wrong. So the destructive scenarios run against a two-node laboratory
before a release, and the report says which of them were real.

``rehearsal``
    Every hypervisor write, and how the laboratory exercises it. Separate from
    the scenarios because a scenario is about a *failure* and there are thirteen
    writes — several of which no failure in the corpus asks for, and all of which
    have to have been run against real hardware at least once before anybody
    should let them run unattended on somebody's homelab.
``suite``
    Running the destructive scenarios and the rehearsals against a driver,
    restoring between them, and stating what was simulated and what was not.

Everything here runs with no cluster too, against the recorded stand-in. That is
not a convenience: it is what keeps the restore path exercised on the
pull-request machine, so a broken restore is found before a release rather than
during one.
"""

from __future__ import annotations
