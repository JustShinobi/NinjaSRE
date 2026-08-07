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

# --- The five scoring axes ---------------------------------------------------

#: Did it reach the right conclusion.
AXIS_ACCURACY: Final = "accuracy"

#: Did the conclusion rest on evidence the run actually holds.
AXIS_EVIDENCE: Final = "evidence"

#: Were the planted confounders explicitly dismissed.
AXIS_ADVERSARIAL: Final = "adversarial"

#: How far the route was from the golden one, and how much was wasted on the way.
AXIS_TRAJECTORY: Final = "trajectory"

#: What it cost, gated apart from whether it was right.
AXIS_COST: Final = "cost"

#: Every axis, in the order a report prints them: what was concluded, what it
#: was concluded from, what it resisted, how it got there, and what that cost.
SCORING_AXES: Final[tuple[str, ...]] = (
    AXIS_ACCURACY,
    AXIS_EVIDENCE,
    AXIS_ADVERSARIAL,
    AXIS_TRAJECTORY,
    AXIS_COST,
)

#: The axes that say whether the investigation was *right*. Gated together and
#: apart from cost, because a change that improves all three at triple the price
#: is a trade-off somebody should decide on rather than a silent pass.
CORRECTNESS_AXES: Final[tuple[str, ...]] = (AXIS_ACCURACY, AXIS_EVIDENCE, AXIS_ADVERSARIAL)

# --- What a scenario is allowed to cost --------------------------------------

#: Tokens one attempt may spend, per difficulty level. A level-4 incident has
#: more to read and more to rule out, so holding it to a level-1 budget would
#: report a cost failure on every hard scenario and make the axis unreadable.
SCENARIO_TOKEN_BUDGET_BY_DIFFICULTY: Final[dict[int, int]] = {
    1: 20_000,
    2: 35_000,
    3: 60_000,
    4: 90_000,
}

#: Wall clock one attempt may take, per difficulty level. Generous, because this
#: axis is meant to catch an investigation that has started looping rather than
#: to police a slow laptop.
SCENARIO_SECONDS_BUDGET_BY_DIFFICULTY: Final[dict[int, float]] = {
    1: 60.0,
    2: 90.0,
    3: 150.0,
    4: 240.0,
}

# --- Regression gating -------------------------------------------------------

#: How far a correctness pass rate may fall before the gate fails, as a share.
#: Not zero: the system is stochastic, and a gate that failed on any movement at
#: all is a gate somebody turns off within a fortnight.
DEFAULT_REGRESSION_TOLERANCE: Final[float] = 0.05

#: How far a cost measurement may rise before the cost gate fails, as a share.
#: Wider than the correctness tolerance because token accounting varies with
#: prompt caching and provider-side batching in ways the agent did not choose.
DEFAULT_COST_TOLERANCE: Final[float] = 0.20

#: How far a trajectory measurement may rise before the trajectory gate fails.
DEFAULT_TRAJECTORY_TOLERANCE: Final[float] = 0.25

#: How many standard errors of the measured rates a drop must clear before it
#: counts as a regression. Three rather than the conventional two: at two the
#: gate is right about one comparison in twenty *by construction*, and a suite
#: comparing a dozen scenario-axis pairs per build would then go red on noise
#: most weeks. A gate that blocks a merge has to be conservative about crying
#: wolf, because the cost of a false positive is somebody widening the tolerance
#: until the gate stops gating.
VARIANCE_SIGMA_ALLOWANCE: Final[float] = 3.0

#: Attempts per scenario before the gate will widen its tolerance for noise at
#: all. Below this the spread is not a measurement of anything, and widening on
#: it would be widening on a single sample wearing statistics.
MIN_ATTEMPTS_FOR_VARIANCE: Final[int] = 3

#: The largest drop the variance allowance may forgive, whatever the arithmetic
#: says. At three or four attempts the standard error is wide enough to excuse a
#: total collapse, which is technically true — three failures after three
#: successes is not statistically remarkable — and useless as a gate. Past half
#: the attempts there is no sampling story worth waiting for another build to
#: hear.
MAX_FORGIVEN_DROP: Final[float] = 0.5

#: The smallest *absolute* rise in each tracked measurement that the gate will
#: act on, whatever the percentage says. A ratio computed against a tiny base is
#: not a measurement of anything: an offline scenario that took 30 milliseconds
#: and then 42 has risen by forty per cent and by nothing at all, and a gate that
#: reported it would be red every second build for a reason nobody can fix.
MEASUREMENT_NOISE_FLOORS: Final[dict[str, float]] = {
    "cost.tokens": 200.0,
    "cost.seconds": 1.0,
    "trajectory.distance": 0.5,
    "trajectory.iterations": 0.5,
    "trajectory.redundant_calls": 0.5,
}

#: Where stored baselines live when nobody says otherwise.
NINJASRE_EVALUATION_BASELINES_ENV: Final = "NINJASRE_EVALUATION_BASELINES"

#: The filename suffix a stored baseline carries.
BASELINE_FILE_SUFFIX: Final = ".baseline.json"

# --- Ablation ----------------------------------------------------------------

#: The mechanisms the harness can switch off, one at a time, to price each one's
#: contribution. Names rather than an enum because a mechanism is identified in
#: a results table and a report, and both of those are text. Each name is the
#: one its owning feature already publishes where the feature has one.
ABLATION_MECHANISMS: Final[tuple[str, ...]] = (
    "memory_read",
    "memory_strategy",
    "topology",
    "knowledge_base",
    "masking",
    "subagents",
    "seed_calls",
    "capability_planning",
)

#: The name the un-ablated arm runs under. Reserved: an ablation configuration
#: may not call itself this, because two rows called "baseline" in one report is
#: a report nobody can read.
BASELINE_ARM: Final = "baseline"

#: A contribution smaller than this, either way, is reported as "no measurable
#: effect" rather than as a number. Below it the difference is one attempt in
#: twenty changing its mind, and dressing that up as a percentage point is how a
#: table stops being trusted.
ABLATION_NOISE_FLOOR: Final[float] = 0.02

# --- Benchmarks --------------------------------------------------------------

#: The external benchmark the adapter port ships a reference implementation for.
CLOUD_OPS_BENCH: Final = "cloud_opsbench"

#: Where a benchmark's exported tables are written when nobody says otherwise.
NINJASRE_BENCHMARK_OUTPUT_ENV: Final = "NINJASRE_BENCHMARK_OUTPUT"

#: The markers an exported table is spliced between when it is written into a
#: document that has other content. Comments, so the document renders unchanged.
BENCHMARK_TABLE_BEGIN: Final = "<!-- benchmark:begin -->"
BENCHMARK_TABLE_END: Final = "<!-- benchmark:end -->"


__all__ = [
    "ABLATION_MECHANISMS",
    "ABLATION_NOISE_FLOOR",
    "AXIS_ACCURACY",
    "AXIS_ADVERSARIAL",
    "AXIS_COST",
    "AXIS_EVIDENCE",
    "AXIS_TRAJECTORY",
    "BASELINE_ARM",
    "BASELINE_FILE_SUFFIX",
    "BENCHMARK_TABLE_BEGIN",
    "BENCHMARK_TABLE_END",
    "CLOUD_OPS_BENCH",
    "CORRECTNESS_AXES",
    "DEFAULT_COST_TOLERANCE",
    "DEFAULT_REGRESSION_TOLERANCE",
    "DEFAULT_SCENARIO_ATTEMPTS",
    "DEFAULT_TRAJECTORY_TOLERANCE",
    "FULL_SUITE_BUDGET_SECONDS",
    "MAX_FORGIVEN_DROP",
    "MAX_SCENARIO_ATTEMPTS",
    "MEASUREMENT_NOISE_FLOORS",
    "MIN_ATTEMPTS_FOR_VARIANCE",
    "NINJASRE_BENCHMARK_OUTPUT_ENV",
    "NINJASRE_EVALUATION_BASELINES_ENV",
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
    "SCENARIO_SECONDS_BUDGET_BY_DIFFICULTY",
    "SCENARIO_TOKEN_BUDGET_BY_DIFFICULTY",
    "SCENARIO_TRANSCRIPT_FILENAME",
    "SCORING_AXES",
    "TIER_ONE_SUITE_BUDGET_SECONDS",
    "VARIANCE_SIGMA_ALLOWANCE",
    "VERDICT_AXES",
]
