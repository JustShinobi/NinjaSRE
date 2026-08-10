"""What changed, when, by whom — and whether it reached the cluster at all.

The question an SRE asks before any metric is "what changed just before this
broke", and until this package existed the platform had no way to answer it. It
had vendor tools that could list commits, which is a different thing: a commit
is a statement about a repository, and the estate is broken by an *application*.
A commit nobody applied changed nothing, and treating the two as one is the
difference between correlation and coincidence.

Three pieces, in the order they are used.

**A change and a window** (``models``), with the applied/committed distinction as
a field rather than as two types. A caller that ignores the field gets a
superset of the truth rather than a different answer.

**A source** (``port``), which is the one seam a deployment fills. The infra-apply
source reads a repository's own record of what it applied and needs no
credential; a git-host source reads whichever vendor the deployment already has
a credential for. Both produce the same record, so nothing above this line knows
which one answered.

**A correlation** (``correlation``), which is why the package is not just a
listing. Correlating a change to an incident by time alone produces a false
positive in every busy window; the correlation here runs through the resource —
path to component, component to the workloads it manages, workload to the
resource under investigation — and reports its own strength, so a change that
merely shares a window is labelled as sharing a window and nothing more.

The negative is a first-class answer rather than an empty list. "No change
touched this resource in the last day" is the sentence that stops somebody
searching in the wrong place, and it is only worth anything if it names what was
consulted to establish it.
"""

from __future__ import annotations

from platform.changes.errors import ChangeStateInvalid, ChangeWindowInvalid
from platform.changes.models import Change, ChangeWindow
from platform.changes.port import ChangeSource

__all__ = [
    "Change",
    "ChangeSource",
    "ChangeStateInvalid",
    "ChangeWindow",
    "ChangeWindowInvalid",
]
