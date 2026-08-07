"""Names the repository's own development workflow reads from the environment.

Nothing here is read by the running product. These are the switches the
spec-driven workflow helpers under ``tools/`` obey, and they live in this tier
for the same reason every other environment-variable name does: a bare string at
a call site is what ``tools/check_constants.py`` exists to reject, and the guard
scans ``tools/`` along with the seven first-party packages. A workflow variable
is no less a name for being a workflow variable.

They are kept apart from ``config.constants.paths`` deliberately. That module
resolves where a *deployment* keeps its state; this one names how *this
checkout* is driven, and conflating the two would put a build-time concern in
the module a container image reads at start-up.
"""

from __future__ import annotations

from typing import Final

#: Which directory of specifications the branch/slug contract reads.
#:
#: Work proceeds in waves, and a later wave lives in its own directory beside
#: the first — ``specs/`` for the platform, ``specs_v2/`` for what follows.
#: ``tools/close_task_branch.py`` and ``make close-task`` both honour this, so
#: the branch on disk and the plan being closed can never disagree.
SPECS_DIR_ENV: Final = "NINJASRE_SPECS_DIR"

#: Where specs live when nothing says otherwise.
DEFAULT_SPECS_DIRNAME: Final = "specs"


__all__ = ["DEFAULT_SPECS_DIRNAME", "SPECS_DIR_ENV"]
