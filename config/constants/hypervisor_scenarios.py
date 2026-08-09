"""Every bound and name the hypervisor scenario suite runs inside.

The suite scores two things the general scenario harness does not: whether the
*action* was right, and whether a diagnosis rested on the evidence it claimed.
Both need vocabularies, and a vocabulary written down in a test file is one that
drifts the first time somebody adds a scenario in a hurry.

The budget is here for the same reason the tier-one one is: it is the number the
gate asserts against, and a suite that cannot say what it is allowed to cost is
a suite that quietly becomes the slowest thing in the build.
"""

from __future__ import annotations

from typing import Final

# --- Fixture layout ----------------------------------------------------------

#: The declaration at the root of a hypervisor scenario directory. Deliberately
#: not ``scenario.yml``: the general corpus loader walks for that name, and a
#: document it cannot read would turn the whole corpus into a load error.
HYPERVISOR_SCENARIO_FILENAME: Final = "proxmox-scenario.yml"

#: The recorded API responses one scenario overlays on the baseline cluster.
#: Optional — most scenarios differ from the reference cluster in one reading,
#: and the ones that differ in none carry no file at all.
HYPERVISOR_READINGS_FILENAME: Final = "readings.json"

#: The fixture schema the loader understands. A declaration naming anything else
#: is refused rather than read on a guess.
HYPERVISOR_SCENARIO_SCHEMA_VERSION: Final = "1"

#: Where the committed scores live, relative to the corpus root. Committed so
#: that moving one is a reviewable change rather than an invisible one.
HYPERVISOR_BASELINE_FILENAME: Final = "baseline.json"

#: The instant the corpus's recorded responses are read as of.
#:
#: Fixed, and it has to be. Every recorded task, backup and lock in the corpus
#: carries an absolute timestamp, so a tool that measured their age against the
#: process clock would report a different number every second the suite ran —
#: which is the difference between a gate and a number that drifts. Fixing it
#: also keeps each scenario's own narrative true: a job that failed for eleven
#: days reads as eleven days rather than as however long ago the recording was
#: taken. Just after the latest observation any scenario carries, which is what
#: "we have just read this cluster" means.
HYPERVISOR_SCENARIO_OBSERVED_AT: Final = "2025-08-10T07:00:00+00:00"

# --- The four domains --------------------------------------------------------

#: The four areas a hypervisor fails in, which is also the order an
#: investigation asks about them: a cluster that cannot act has already answered
#: "why will this guest not start".
HYPERVISOR_SCENARIO_DOMAINS: Final[tuple[str, ...]] = (
    "quorum",
    "storage",
    "guests",
    "backups",
    "host",
)

# --- How a scenario is run ---------------------------------------------------

#: Runs from recorded responses, needs no cluster, and is what CI executes.
SCENARIO_MODE_FIXTURE: Final = "fixture"

#: Ran against the laboratory cluster, which is the only way to produce it.
SCENARIO_MODE_LABORATORY: Final = "laboratory"

#: Both modes, in report order. A run states which one each scenario used, so a
#: release note citing the number can say what was simulated and what was real.
SCENARIO_MODES: Final[tuple[str, ...]] = (SCENARIO_MODE_FIXTURE, SCENARIO_MODE_LABORATORY)

# --- The closed verdict sets -------------------------------------------------

#: What the system did about the situation, and what the scenario said it should
#: have done. Closed, because the whole value of scoring the action separately is
#: that "harmful" is a word the report can count.
ACTION_VERDICTS: Final[tuple[str, ...]] = ("correct", "harmful", "unnecessary", "absent")

#: What the conclusion was worth. ``unsupported`` is the one that matters: a
#: right answer reached without the evidence it should have rested on is not a
#: right answer, and folding it into ``correct`` would reward guessing.
DIAGNOSIS_VERDICTS: Final[tuple[str, ...]] = ("correct", "unsupported", "incorrect", "absent")

#: Whether the model got to the end at all. Reported apart from the diagnosis so
#: a model too small to finish is distinguishable from one that finished wrongly.
COMPLETION_VERDICTS: Final[tuple[str, ...]] = ("completed", "incomplete")

#: What a scenario says the right response was, and what a run says it did.
#: ``escalate`` is a response, not the absence of one — several of these
#: scenarios have no safe automatic answer and reporting is the correct act.
RESPONSE_KINDS: Final[tuple[str, ...]] = ("act", "escalate", "wait", "none")

#: The risk classes at which proposing the wrong action is harmful rather than
#: merely unnecessary. A wrong low-risk action wastes an operator's afternoon; a
#: wrong high-risk one costs a filesystem.
HARMFUL_RISK_CLASSES: Final[tuple[str, ...]] = ("high", "critical")

# --- The two recorded model profiles -----------------------------------------

#: The hosted model the corpus's primary transcripts were recorded against.
#: A profile rather than a vendor's model identifier, because the number this
#: suite publishes is about a class of model and outlives any one release.
MODEL_HOSTED: Final = "hosted-frontier"

#: The self-hosted model the same scenarios were recorded against, which is the
#: comparison feature 043 exists to make measurable.
MODEL_SELF_HOSTED: Final = "self-hosted-compact"

#: Every profile the corpus records, in report order.
SCENARIO_MODEL_PROFILES: Final[tuple[str, ...]] = (MODEL_HOSTED, MODEL_SELF_HOSTED)

#: The run with episodic memory and strategy synthesis available.
ARM_FULL: Final = "full"

#: The same run with both switched off, which is what makes "memory helps" a
#: number rather than an assumption.
ARM_NO_MEMORY: Final = "no-memory"

#: Both arms, in report order.
SCENARIO_ABLATION_ARMS: Final[tuple[str, ...]] = (ARM_FULL, ARM_NO_MEMORY)

# --- The laboratory ----------------------------------------------------------

#: Names the laboratory cluster the destructive suite may break. Unset means
#: there is no laboratory, and the suite runs against the recorded stand-in and
#: says so — rather than failing on every machine that is not somebody's rack.
NINJASRE_PROXMOX_LABORATORY_ENV: Final = "NINJASRE_PROXMOX_LABORATORY"

# --- Bounds ------------------------------------------------------------------

#: What the fixture-backed hypervisor suite is allowed to cost on the
#: pull-request path. Small, because it reads recorded responses and runs no
#: model: anything approaching this is a scenario doing something it should not.
HYPERVISOR_SUITE_BUDGET_SECONDS: Final[float] = 60.0

#: How many scenarios the corpus must hold before the suite will call itself
#: complete. The four domains have twenty-four between them and the host layer
#: adds four more from the documented incidents.
HYPERVISOR_SCENARIO_MINIMUM: Final[int] = 28

#: How far the aggregate pass rate may fall before the gate fails. Zero: the
#: fixture suite runs recorded transcripts over recorded readings, so nothing
#: about it is stochastic and any movement is somebody's change.
HYPERVISOR_REGRESSION_TOLERANCE: Final[float] = 0.0

__all__ = [
    "ACTION_VERDICTS",
    "ARM_FULL",
    "ARM_NO_MEMORY",
    "COMPLETION_VERDICTS",
    "DIAGNOSIS_VERDICTS",
    "HARMFUL_RISK_CLASSES",
    "HYPERVISOR_BASELINE_FILENAME",
    "HYPERVISOR_READINGS_FILENAME",
    "HYPERVISOR_REGRESSION_TOLERANCE",
    "HYPERVISOR_SCENARIO_DOMAINS",
    "HYPERVISOR_SCENARIO_FILENAME",
    "HYPERVISOR_SCENARIO_MINIMUM",
    "HYPERVISOR_SCENARIO_OBSERVED_AT",
    "HYPERVISOR_SCENARIO_SCHEMA_VERSION",
    "HYPERVISOR_SUITE_BUDGET_SECONDS",
    "MODEL_HOSTED",
    "MODEL_SELF_HOSTED",
    "NINJASRE_PROXMOX_LABORATORY_ENV",
    "RESPONSE_KINDS",
    "SCENARIO_ABLATION_ARMS",
    "SCENARIO_MODEL_PROFILES",
    "SCENARIO_MODES",
    "SCENARIO_MODE_FIXTURE",
    "SCENARIO_MODE_LABORATORY",
]
