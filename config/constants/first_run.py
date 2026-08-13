"""First run: the bootstrap credential, the self-check, the checklist, the demo.

Everything an operator meets between ``docker compose up`` and a console with
something in it. Four groups of names, and each group exists because the same
literal is needed in at least three places — the thing that produces it, the
surface that reports it, and the test that asserts it.

Two numbers here are load-bearing rather than tuning.

``BOOTSTRAP_CREDENTIAL_LIFETIME_SECONDS`` is one hour. Long enough that an
operator who starts the stack, makes coffee, and comes back can still sign in;
short enough that a token which reached a terminal scrollback, a screen share or
a shell history is worthless by the time anybody finds it. It is also the only
credential in the system whose lifetime is measured in seconds rather than days,
which is why the identity layer had to learn a sub-day lifetime at all.

``BRING_UP_TO_SIGN_IN_BUDGET_SECONDS`` is the part of the fifteen-minute first
run that happens before the operator has seen anything. A test asserts it equals
the sum of the shipped standard plan's steps up to and including signing in, so
a step added later cannot quietly push the budget out.
"""

from __future__ import annotations

from typing import Final

# --- The organisation a fresh deployment creates ------------------------------

#: The organisation bring-up creates when the store holds none. Named rather
#: than derived from the hostname: an identifier that changes when the machine
#: is renamed is one that breaks every token issued before the rename.
NINJASRE_ORGANISATION_ENV: Final = "NINJASRE_ORGANISATION"

DEFAULT_ORGANISATION_ID: Final = "default"
DEFAULT_ORGANISATION_NAME: Final = "Default organisation"

# --- The bootstrap credential -------------------------------------------------

#: Where the credential is written for the operator to read again. A file rather
#: than only a log line: an operator who closed the terminal before reading the
#: token has not lost their deployment, which is one of this feature's listed
#: edge cases.
NINJASRE_BOOTSTRAP_CREDENTIAL_PATH_ENV: Final = "NINJASRE_BOOTSTRAP_CREDENTIAL_PATH"

#: Where state that outlives one process but is not in the database goes: the
#: credential file, the last bring-up failure, a support bundle.
NINJASRE_STATE_DIR_ENV: Final = "NINJASRE_STATE_DIR"

DEFAULT_STATE_DIR: Final = "/var/lib/ninjasre"
BOOTSTRAP_CREDENTIAL_FILENAME: Final = "bootstrap-credential.json"

#: Owner read and write, nothing else. Set explicitly on creation rather than
#: left to the process umask, because a umask of 022 would leave a live
#: credential world-readable on a shared host.
BOOTSTRAP_CREDENTIAL_FILE_MODE: Final[int] = 0o600

#: One hour. See the module docstring.
BOOTSTRAP_CREDENTIAL_LIFETIME_SECONDS: Final[int] = 3600

#: What the bootstrap principal is called, in the identity store and in the
#: audit trail. A principal rather than a bypass: NFR-004 forbids an exception
#: to the identity system, so this is an ordinary owner whose token is short.
BOOTSTRAP_PRINCIPAL_ID: Final = "bootstrap-administrator"
BOOTSTRAP_PRINCIPAL_NAME: Final = "Bootstrap administrator"
BOOTSTRAP_GRANT_ID: Final = "bootstrap-administrator-owner"
BOOTSTRAP_TOKEN_NAME: Final = "bootstrap"

#: How long the credential an operator establishes with the bootstrap one lasts.
#: Ninety days rather than the identity layer's default year: this is the first
#: token on a new deployment and the one most likely to be pasted somewhere
#: careless, so it expires while somebody still remembers issuing it.
DURABLE_CREDENTIAL_LIFETIME_DAYS: Final[int] = 90

#: What the durable credential is called when the operator does not name it.
DEFAULT_DURABLE_CREDENTIAL_NAME: Final = "first administrator"

BOOTSTRAP_AUDIT_ACTION_ISSUE: Final = "bootstrap.credential_issued"
BOOTSTRAP_AUDIT_ACTION_ESTABLISH: Final = "bootstrap.durable_credential_established"
BOOTSTRAP_AUDIT_RESOURCE_KIND: Final = "bootstrap_credential"

# --- The self-check -----------------------------------------------------------

#: Every dependency the self-check covers. The order is the report's order when
#: nothing is wrong; a finding reorders by how much it blocks.
CHECK_DATABASE: Final = "database"
CHECK_SCHEMA: Final = "schema"
CHECK_CREDENTIAL_PROXY: Final = "credential-proxy"
CHECK_MODEL_PROVIDER: Final = "model-provider"
CHECK_INTEGRATIONS: Final = "integrations"
CHECK_SCHEDULER: Final = "scheduler"
CHECK_OBSERVER: Final = "observer"
CHECK_DISK_SPACE: Final = "disk-space"
CHECK_CLOCK_SKEW: Final = "clock-skew"

SELF_CHECK_NAMES: Final[tuple[str, ...]] = (
    CHECK_DATABASE,
    CHECK_SCHEMA,
    CHECK_CREDENTIAL_PROXY,
    CHECK_MODEL_PROVIDER,
    CHECK_INTEGRATIONS,
    CHECK_SCHEDULER,
    CHECK_OBSERVER,
    CHECK_DISK_SPACE,
    CHECK_CLOCK_SKEW,
)

#: How much of the deployment one finding takes away. The ordering is the whole
#: point of the vocabulary: a report sorted by it puts what blocks the most
#: first, which is FR-008.
BLOCKS_EVERYTHING: Final = "blocks-everything"
BLOCKS_INVESTIGATION: Final = "blocks-investigation"
BLOCKS_ONE_FEATURE: Final = "blocks-one-feature"
DEGRADES: Final = "degrades"

#: Most blocking first. A report is sorted by this index, then by check name, so
#: two findings of equal weight come out in a stable order rather than in
#: whatever order the checks happened to finish.
BLOCKING_ORDER: Final[tuple[str, ...]] = (
    BLOCKS_EVERYTHING,
    BLOCKS_INVESTIGATION,
    BLOCKS_ONE_FEATURE,
    DEGRADES,
)

#: What one check is allowed before it is abandoned. Per check rather than for
#: the whole run: a single unreachable dependency must not consume the budget
#: the other eight need, and NFR-003 says the check may not hang on one.
SELF_CHECK_TIMEOUT_SECONDS: Final[float] = 5.0

#: What the whole pass is allowed. Larger than one timeout because the checks
#: run together and the slowest decides, with headroom for the store round trips
#: that are genuinely sequential.
SELF_CHECK_BUDGET_SECONDS: Final[float] = 15.0

#: Below this, an investigation's evidence and the database's write-ahead log
#: start competing for the same disk. Two gigabytes is enough for a day of runs
#: on the standard profile and is the point at which telling somebody is still
#: useful rather than merely accurate.
MINIMUM_FREE_DISK_BYTES: Final[int] = 2 * 1024 * 1024 * 1024

#: Beyond this, a token issued on one host is rejected on another before it has
#: been used. The identity layer already tolerates a smaller skew per request;
#: this is the point at which the tolerance stops covering it.
MAXIMUM_CLOCK_SKEW_SECONDS: Final[float] = 60.0

# --- The setup checklist ------------------------------------------------------

SETUP_STEP_DURABLE_CREDENTIAL: Final = "durable-credential"
SETUP_STEP_MODEL_PROVIDER: Final = "model-provider"
SETUP_STEP_INFRASTRUCTURE_SOURCE: Final = "infrastructure-source"
SETUP_STEP_INVESTIGATION_RUNTIME: Final = "investigation-runtime"
SETUP_STEP_FIRST_INVESTIGATION: Final = "first-investigation"

#: The order the console shows them in, which is also the order they depend on
#: each other: a first investigation needs a runtime to run in, a runtime needs
#: a source worth pointing it at, a source needs somebody who may configure one,
#: and that is the durable credential.
#:
#: The runtime step is fourth because it is the one a deployment can satisfy
#: without noticing it has not. Everything else here leaves a trace an operator
#: can see from the console; a process with no investigation runtime composed
#: looks exactly like one that has, right up to the moment somebody presses
#: Investigate and the run fails before it starts.
SETUP_STEP_ORDER: Final[tuple[str, ...]] = (
    SETUP_STEP_DURABLE_CREDENTIAL,
    SETUP_STEP_MODEL_PROVIDER,
    SETUP_STEP_INFRASTRUCTURE_SOURCE,
    SETUP_STEP_INVESTIGATION_RUNTIME,
    SETUP_STEP_FIRST_INVESTIGATION,
)

SETUP_STATE_DONE: Final = "done"
SETUP_STATE_READY: Final = "ready"
SETUP_STATE_BLOCKED: Final = "blocked"

SETUP_STATES: Final[tuple[str, ...]] = (SETUP_STATE_DONE, SETUP_STATE_READY, SETUP_STATE_BLOCKED)

#: How far along one *thing* is — a model provider, one vendor integration — as
#: distinct from how far along the step that configures it is. Three words
#: rather than a boolean, because "nothing is stored" and "a key is stored and
#: nobody has checked it" are different screens with different next actions, and
#: the second is the state a wrong key sits in until an incident finds it.
#:
#: ``absent`` for an integration means declared and holding nothing: the list
#: only ever contains integrations this deployment knows about.
SETUP_READINESS_ABSENT: Final = "absent"
SETUP_READINESS_CONFIGURED: Final = "configured"
SETUP_READINESS_VERIFIED: Final = "verified"

SETUP_READINESS: Final[tuple[str, ...]] = (
    SETUP_READINESS_ABSENT,
    SETUP_READINESS_CONFIGURED,
    SETUP_READINESS_VERIFIED,
)

# --- What a check concluded, and about what ------------------------------------

#: What one verification concluded. Two words and no third: a check that could
#: not be run at all is a check nobody recorded, and writing "unknown" down would
#: make the absence of a record and the presence of an inconclusive one two
#: spellings of the same screen.
SETUP_CHECK_PASSED: Final = "passed"
SETUP_CHECK_FAILED: Final = "failed"

SETUP_CHECK_OUTCOMES: Final[tuple[str, ...]] = (SETUP_CHECK_PASSED, SETUP_CHECK_FAILED)

#: What a check was run against. The two the verify routes accept, and the reason
#: they are separate rather than one namespace of names: a vendor integration and
#: a model provider are checked by different code, answer with different
#: evidence, and an operator reading "prometheus is verified" is not being told
#: anything about their model.
SETUP_CHECK_SUBJECT_INTEGRATION: Final = "integration"
SETUP_CHECK_SUBJECT_PROVIDER: Final = "model-provider"

SETUP_CHECK_SUBJECTS: Final[tuple[str, ...]] = (
    SETUP_CHECK_SUBJECT_INTEGRATION,
    SETUP_CHECK_SUBJECT_PROVIDER,
)

#: How many recorded checks one read returns. A deployment has one row per thing
#: it can check, so this bounds a listing that is already bounded by how many
#: integrations exist — it is here so a corrupted table cannot page a console to
#: death, not because anybody expects to reach it.
MAX_VERIFICATION_PAGE_SIZE: Final[int] = 500

#: What the guided first investigation is called in the run trace, so a
#: deployment can tell the one it was shown from the ones it went on to run.
GUIDED_INVESTIGATION_TRIGGER: Final = "guided-first-investigation"

# --- Demo mode ----------------------------------------------------------------

#: Whether this deployment serves demonstration data. Read once at composition:
#: a deployment that could turn demo mode on at runtime is one where a request
#: might be answered from a fixture without anybody deciding it should be.
NINJASRE_DEMO_MODE_ENV: Final = "NINJASRE_DEMO_MODE"

#: What the demonstration seeder is allowed. NFR-002; asserted by a benchmark
#: that loads the whole dataset.
DEMO_POPULATION_BUDGET_SECONDS: Final[float] = 30.0

#: The scripted investigation's identity and pacing. It streams like a real one
#: so the live transcript can be demonstrated with no model behind it; the delay
#: is what makes it read as a run rather than as a page that appeared at once.
DEMO_SCRIPTED_RUN_TRIGGER: Final = "demonstration-scripted-run"
DEMO_SCRIPTED_EVENT_INTERVAL_SECONDS: Final[float] = 0.25

# --- Diagnostics --------------------------------------------------------------

#: Where the last bring-up failure is left, so the console and the CLI can show
#: the same message the terminal did to somebody who was not watching it.
BRING_UP_FAILURE_FILENAME: Final = "bring-up-failure.json"

SUPPORT_BUNDLE_FILENAME: Final = "ninjasre-support-bundle.json"

#: How much of the log a bundle carries. Enough to cover a failed start and the
#: minute before it, bounded so a bundle is something an operator can read
#: before deciding to share it.
SUPPORT_BUNDLE_LOG_LINES: Final[int] = 500

# --- Budgets ------------------------------------------------------------------

#: Clean machine to a signed-in console, on the standard profile. Asserted equal
#: to the shipped plan's steps up to and including sign-in, so the two cannot
#: drift. NFR-001.
BRING_UP_TO_SIGN_IN_BUDGET_SECONDS: Final[int] = 630


__all__ = [
    "BLOCKING_ORDER",
    "BLOCKS_EVERYTHING",
    "BLOCKS_INVESTIGATION",
    "BLOCKS_ONE_FEATURE",
    "BOOTSTRAP_AUDIT_ACTION_ESTABLISH",
    "BOOTSTRAP_AUDIT_ACTION_ISSUE",
    "BOOTSTRAP_AUDIT_RESOURCE_KIND",
    "BOOTSTRAP_CREDENTIAL_FILENAME",
    "BOOTSTRAP_CREDENTIAL_FILE_MODE",
    "BOOTSTRAP_CREDENTIAL_LIFETIME_SECONDS",
    "BOOTSTRAP_GRANT_ID",
    "BOOTSTRAP_PRINCIPAL_ID",
    "BOOTSTRAP_PRINCIPAL_NAME",
    "BOOTSTRAP_TOKEN_NAME",
    "BRING_UP_FAILURE_FILENAME",
    "BRING_UP_TO_SIGN_IN_BUDGET_SECONDS",
    "CHECK_CLOCK_SKEW",
    "CHECK_CREDENTIAL_PROXY",
    "CHECK_DATABASE",
    "CHECK_DISK_SPACE",
    "CHECK_INTEGRATIONS",
    "CHECK_MODEL_PROVIDER",
    "CHECK_OBSERVER",
    "CHECK_SCHEDULER",
    "CHECK_SCHEMA",
    "DEFAULT_DURABLE_CREDENTIAL_NAME",
    "DEFAULT_ORGANISATION_ID",
    "DEFAULT_ORGANISATION_NAME",
    "DEFAULT_STATE_DIR",
    "DEGRADES",
    "DEMO_POPULATION_BUDGET_SECONDS",
    "DEMO_SCRIPTED_EVENT_INTERVAL_SECONDS",
    "DEMO_SCRIPTED_RUN_TRIGGER",
    "DURABLE_CREDENTIAL_LIFETIME_DAYS",
    "GUIDED_INVESTIGATION_TRIGGER",
    "MAXIMUM_CLOCK_SKEW_SECONDS",
    "MINIMUM_FREE_DISK_BYTES",
    "NINJASRE_BOOTSTRAP_CREDENTIAL_PATH_ENV",
    "NINJASRE_DEMO_MODE_ENV",
    "NINJASRE_ORGANISATION_ENV",
    "NINJASRE_STATE_DIR_ENV",
    "SELF_CHECK_BUDGET_SECONDS",
    "SELF_CHECK_NAMES",
    "SELF_CHECK_TIMEOUT_SECONDS",
    "SETUP_READINESS",
    "SETUP_READINESS_ABSENT",
    "SETUP_READINESS_CONFIGURED",
    "SETUP_READINESS_VERIFIED",
    "SETUP_STATES",
    "SETUP_STATE_BLOCKED",
    "SETUP_STATE_DONE",
    "SETUP_STATE_READY",
    "SETUP_STEP_DURABLE_CREDENTIAL",
    "SETUP_STEP_FIRST_INVESTIGATION",
    "SETUP_STEP_INFRASTRUCTURE_SOURCE",
    "SETUP_STEP_MODEL_PROVIDER",
    "SETUP_STEP_ORDER",
    "SUPPORT_BUNDLE_FILENAME",
    "SUPPORT_BUNDLE_LOG_LINES",
]
