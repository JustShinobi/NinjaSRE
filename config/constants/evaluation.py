"""Every bound and name the scenario harness runs inside.

The harness itself lives beside the tests, outside the package tiers — but the
things it is bounded by are still bounds, and Article II puts those here. The
environment-variable name that switches verdict records on is the clearest
case: a bare string in a test file is exactly the literal
``tools/check_constants.py`` exists to reject everywhere else, and writing it
here costs nothing.

The difficulty ladder is here rather than in the harness for a different
reason. Answer keys reference it, reports stratify by it, and a level that
meant one thing in a fixture and another in a report would make the curriculum
gradient unreadable. One definition, in the tier nothing may import above.
"""

from __future__ import annotations

from typing import Final

# --- Fixture layout ----------------------------------------------------------

#: The metadata document at the root of a scenario directory.
SCENARIO_MANIFEST_FILENAME: Final = "scenario.yml"

#: The alert that triggers the investigation.
SCENARIO_ALERT_FILENAME: Final = "alert.json"

#: The ground truth one scenario is scored against.
SCENARIO_ANSWER_FILENAME: Final = "answer.yml"

#: The recorded model transcript an offline run replays, when one was recorded.
SCENARIO_TRANSCRIPT_FILENAME: Final = "transcript.json"

#: Files in a scenario directory that are not evidence, so discovery can take
#: "every other ``.json``" as the evidence set rather than requiring a manifest
#: of fixture names that would go stale the first time somebody added one.
SCENARIO_RESERVED_FILENAMES: Final[tuple[str, ...]] = (
    SCENARIO_ALERT_FILENAME,
    SCENARIO_TRANSCRIPT_FILENAME,
)

#: The fixture schema the loader understands. A scenario declaring anything
#: else is refused rather than read on a guess.
SCENARIO_SCHEMA_VERSION: Final = "1"

# --- The curriculum ----------------------------------------------------------

#: The easiest level: one obvious cause with corroborating evidence.
SCENARIO_DIFFICULTY_MIN: Final[int] = 1

#: The hardest: the most prominent signal is misleading.
SCENARIO_DIFFICULTY_MAX: Final[int] = 4

#: The level at and above which a scenario must plant at least one confounder,
#: because "one confounder" is what level 2 *means*. A level-3 scenario with no
#: adversarial signal is mislabelled, and the loader says so.
SCENARIO_ADVERSARIAL_FROM_DIFFICULTY: Final[int] = 2

#: One sentence per level, so a report can print the ladder beside the numbers
#: rather than assuming its reader remembers what level 3 was.
SCENARIO_DIFFICULTY_DESCRIPTIONS: Final[dict[int, str]] = {
    1: "A single obvious cause with corroborating evidence.",
    2: "One planted confounder that must be explicitly ruled out.",
    3: "Several plausible causes requiring evidence to discriminate.",
    4: "The most prominent signal is misleading; the true cause is secondary.",
}

# --- Running a suite ---------------------------------------------------------

#: Attempts per scenario when nobody asked for more. One, because variance
#: measurement is something you opt into and paying for it on every run would
#: make the cheap path the expensive one.
DEFAULT_SCENARIO_ATTEMPTS: Final[int] = 1

#: Attempts per scenario a caller may ask for. A ceiling rather than a default:
#: the suite is a measurement, and an unbounded attempt count is an unbounded
#: run.
MAX_SCENARIO_ATTEMPTS: Final[int] = 20

#: What the tier-1 suite is allowed to cost on the pull-request path. The
#: primary story is "under ten minutes with no cloud access"; this is the
#: offline share of it, and the gate asserts against it rather than trusting
#: that nobody added a slow scenario.
TIER_ONE_SUITE_BUDGET_SECONDS: Final[float] = 120.0

#: What the whole corpus is allowed to cost on the scheduled path.
FULL_SUITE_BUDGET_SECONDS: Final[float] = 600.0

# --- Verdict records ---------------------------------------------------------

#: Where per-attempt verdict records are written. Unset means they are not
#: written at all, which is the default: a normal run pays nothing for an
#: artefact nobody asked for.
NINJASRE_SCENARIO_ARTIFACTS_ENV: Final = "NINJASRE_SCENARIO_ARTIFACTS"

#: The scoring axes a verdict record reports, in the order a reader should read
#: them: what was concluded, then what it was concluded from, then how it got
#: there.
VERDICT_AXES: Final[tuple[str, ...]] = (
    "root_cause_category",
    "required_keywords",
    "forbidden_keywords",
    "forbidden_categories",
    "ruling_out_keywords",
    "required_evidence_sources",
    "required_queries",
    "trajectory",
    "investigation_loops",
)


__all__ = [
    "DEFAULT_SCENARIO_ATTEMPTS",
    "FULL_SUITE_BUDGET_SECONDS",
    "MAX_SCENARIO_ATTEMPTS",
    "NINJASRE_SCENARIO_ARTIFACTS_ENV",
    "SCENARIO_ADVERSARIAL_FROM_DIFFICULTY",
    "SCENARIO_ALERT_FILENAME",
    "SCENARIO_ANSWER_FILENAME",
    "SCENARIO_DIFFICULTY_DESCRIPTIONS",
    "SCENARIO_DIFFICULTY_MAX",
    "SCENARIO_DIFFICULTY_MIN",
    "SCENARIO_MANIFEST_FILENAME",
    "SCENARIO_RESERVED_FILENAMES",
    "SCENARIO_SCHEMA_VERSION",
    "SCENARIO_TRANSCRIPT_FILENAME",
    "TIER_ONE_SUITE_BUDGET_SECONDS",
    "VERDICT_AXES",
]
