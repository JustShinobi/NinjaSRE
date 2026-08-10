"""What counts as a change, how far back one may look, and how much may come back.

An investigation asks "what changed just before this broke" and the answer has
to be bounded in three directions at once: how wide the window may be, how many
changes may come out of it, and how much of any one change may be carried. All
three are here rather than at the call sites, because the interesting failure is
not one of them being wrong — it is two of them being set in different modules
and nobody being able to say what the tool will actually return.

The two window numbers are separate on purpose, and the distinction is the whole
of what this feature is for. The *first look* is what a report quotes when it
says a deploy landed thirteen minutes before the error; it is short because a
change further back than that is not what an operator means by "just before".
The *default* window is what the negative claim is made over — "nothing touched
this resource in the last day" is a useful sentence and "nothing touched it in
the last half hour" is not, because half an hour of quiet is the ordinary state
of every resource in any estate.
"""

from __future__ import annotations

from typing import Final

# --- Windows -----------------------------------------------------------------

#: How far back the negative claim reaches when nobody names a window. A day,
#: because "no change touched this resource in the last 24 hours" is the
#: sentence that makes somebody stop looking at deploys and start looking
#: elsewhere, and a shorter window makes that sentence true and useless.
DEFAULT_CHANGE_WINDOW_HOURS: Final[float] = 24.0

#: The window a report's own sentence is drawn from — "at 14:19 the monitoring
#: component was applied" about an error at 14:32. Thirty minutes, because that
#: is the span an SRE means by "did something just change", and it is the same
#: number the question is asked in.
FIRST_LOOK_WINDOW_MINUTES: Final[float] = 30.0

#: The widest window a single query may cover. A week: past this the question
#: has stopped being "what changed before this broke" and become a report about
#: the repository, which is a different tool and a different cost.
MAX_CHANGE_WINDOW_HOURS: Final[float] = 168.0

# --- Bounds on one answer ----------------------------------------------------

#: Changes one window may return. The agent reads every one of them, and a busy
#: window that returned three hundred commits would bury the one that touched
#: the resource under the ones that did not.
MAX_CHANGES_PER_WINDOW: Final[int] = 50

#: Paths one change may carry. A refactor that moved four hundred files is real,
#: and carrying all of them would spend the whole answer on one change; the
#: correlation only needs the paths that resolve to a component, and the record
#: says when it kept fewer than the change had.
MAX_PATHS_PER_CHANGE: Final[int] = 40

#: Characters one change message may carry. A commit message longer than this is
#: a design document, and the identifier in the record is what somebody opens to
#: read it.
MAX_CHANGE_MESSAGE_CHARS: Final[int] = 500

#: Components one deployment's change state may declare. A repository past this
#: is not a cluster's infrastructure repository, which is what the path-to-
#: component rule assumes it is reading.
MAX_COMPONENTS: Final[int] = 200

#: Bytes one apply-record document may carry. The record arrives from a
#: repository this deployment does not control, so its size is not a decision
#: this process takes.
MAX_APPLY_RECORD_BYTES: Final[int] = 512_000

# --- Where the change state lives --------------------------------------------

#: The directory an infrastructure repository records its applications under.
#: One apply-record document per component, which is what ``./infra apply
#: --component <x>`` writes and what makes "did anybody actually apply this"
#: answerable at all.
INFRA_STATE_ROOT: Final = ".infra-state"

#: The suffix of an apply-record document inside that directory.
APPLY_RECORD_SUFFIX: Final = ".json"

#: Directory names under which a component owns its own subdirectory, so
#: ``services/monitoring/stack/values.yaml`` resolves to the ``monitoring``
#: component. The component names themselves are read from the apply records —
#: only the *shape* is declared here, and a path whose second segment names no
#: known component resolves to no component at all rather than to a guess.
COMPONENT_PATH_ROOTS: Final[tuple[str, ...]] = ("services", "components", "infra")

#: The directory holding declarative policy that several resources share. A
#: change here is correlated by what the file names rather than by which
#: component owns the directory, because a firewall profile belongs to the
#: workload it protects and not to whoever applied it.
SHARED_POLICY_ROOT: Final = "policies"

# --- The capability ----------------------------------------------------------

#: The name the change capability is registered under, so the console and the
#: run screen can find its result in a trace without matching on prose.
CHANGES_TOOL_NAME: Final = "changes_in_window"

#: How a change is referenced from an evidence entry, so a reader can tell a
#: change record from something observed during the investigation.
CHANGE_REFERENCE_PREFIX: Final = "change"


__all__ = [
    "APPLY_RECORD_SUFFIX",
    "CHANGES_TOOL_NAME",
    "CHANGE_REFERENCE_PREFIX",
    "COMPONENT_PATH_ROOTS",
    "DEFAULT_CHANGE_WINDOW_HOURS",
    "FIRST_LOOK_WINDOW_MINUTES",
    "INFRA_STATE_ROOT",
    "MAX_APPLY_RECORD_BYTES",
    "MAX_CHANGES_PER_WINDOW",
    "MAX_CHANGE_MESSAGE_CHARS",
    "MAX_CHANGE_WINDOW_HOURS",
    "MAX_COMPONENTS",
    "MAX_PATHS_PER_CHANGE",
    "SHARED_POLICY_ROOT",
]
