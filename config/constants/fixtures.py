"""The mock data plane: where the dataset lives, how it is keyed, and its budgets.

The fixture set is a development and test facility. Nothing here is read by a
production deployment — but the names it uses still belong in this tier, because
``tools/check_constants.py`` does not care why an environment variable exists.

Two of these names carry secrets and neither has a default on purpose. The
pseudonym key is what makes anonymisation irreversible without it; the
identifier file is the operator's list of the real values the adversarial scan
hunts for. Both stay with the operator, and a pipeline run that cannot find them
fails rather than proceeding with a guess.
"""

from __future__ import annotations

from typing import Final

# --- Environment ---------------------------------------------------------------

#: Which named scenario the mock server and the console development loop serve.
NINJASRE_FIXTURE_SCENARIO_ENV: Final = "NINJASRE_FIXTURE_SCENARIO"

#: Where the fixture tree lives, for a checkout that is not the repository root.
NINJASRE_FIXTURE_ROOT_ENV: Final = "NINJASRE_FIXTURE_ROOT"

#: The key the pseudonym derivation is salted with. Supplied at run time, never
#: written down here, and the reason the output is not reversible without it.
NINJASRE_PSEUDONYM_KEY_ENV: Final = "NINJASRE_PSEUDONYM_KEY"

#: A file, outside the repository, listing the deployment's real names,
#: addresses and domains. The adversarial scan reads it and fails on any match.
NINJASRE_IDENTIFIER_FILE_ENV: Final = "NINJASRE_IDENTIFIER_FILE"

#: The live deployment the gateway half of a capture reads.
NINJASRE_CAPTURE_ENDPOINT_ENV: Final = "NINJASRE_CAPTURE_ENDPOINT"

#: The token that capture presents. Never stored, never logged.
NINJASRE_CAPTURE_TOKEN_ENV: Final = "NINJASRE_CAPTURE_TOKEN"

#: Comma-separated ``name=host`` pairs naming the cluster nodes to read.
NINJASRE_CAPTURE_NODES_ENV: Final = "NINJASRE_CAPTURE_NODES"

#: The account the read-only SSH channel connects as.
NINJASRE_CAPTURE_SSH_USER_ENV: Final = "NINJASRE_CAPTURE_SSH_USER"

#: Where a raw capture is written before anonymisation. Outside the repository
#: by default, because a raw capture is the most secret-dense artefact this
#: tooling ever holds.
NINJASRE_CAPTURE_RAW_DIR_ENV: Final = "NINJASRE_CAPTURE_RAW_DIR"

# --- The dataset ---------------------------------------------------------------

#: The fixture tree's directory name, relative to the repository root.
FIXTURE_ROOT_DIR_NAME: Final = "fixtures"

#: Where the generated OpenAPI document and the endpoint split are kept.
FIXTURE_CONTRACT_DIR_NAME: Final = "contract"

#: Where each scenario's per-endpoint responses are kept.
FIXTURE_SCENARIO_DIR_NAME: Final = "scenarios"

#: The manifest naming every scenario and its per-endpoint overrides.
FIXTURE_MANIFEST_FILENAME: Final = "manifest.json"

#: The committed copy of the gateway's OpenAPI document. Fixtures validate
#: against this, and a drift check keeps it equal to what the app generates.
FIXTURE_OPENAPI_FILENAME: Final = "openapi.json"

#: The committed endpoint split: what the gateway serves today, and what
#: features that have not landed yet will serve.
FIXTURE_ENDPOINTS_FILENAME: Final = "endpoints.json"

#: The instant every captured timestamp is shifted to land on. Fixed, so two
#: runs of the pipeline produce identical output and a visual-regression
#: baseline compares code against code rather than clock against clock.
FIXTURE_REFERENCE_INSTANT: Final = "2026-08-07T12:00:00+00:00"

#: The scenarios the dataset declares, in the order the manifest lists them.
FIXTURE_SCENARIO_NAMES: Final = (
    "populated",
    "empty",
    "first-run",
    "degraded",
    "incident-live",
    "restricted",
    "scale",
)

#: The default, and the only one a caller that names nothing gets.
DEFAULT_FIXTURE_SCENARIO: Final = "populated"

#: Generated from a seed rather than committed, because committing it would
#: breach the size budget on its own.
GENERATED_FIXTURE_SCENARIOS: Final = ("scale",)

# --- The dataset as a demonstration deployment ---------------------------------

#: The field every record loaded into a real database carries, and what it is
#: set to. It lives here rather than beside either consumer because there are
#: two — the seeder that writes it and the sweep that later has to find every
#: record carrying it — and a label the two spelled differently would be a
#: removal that silently left rows behind.
DEMONSTRATION_LABEL_FIELD: Final = "is_demonstration"
DEMONSTRATION_LABEL: Final = True

#: The organisation the fictional deployment lives under is deliberately *not*
#: declared here. It is a property of the dataset — the root of its own
#: configuration tree — and naming it in the constants tier would be a second
#: place it is written down, which is how a second fictional deployment starts.
#: ``platform.startup.demo.dataset`` reads it; ``tests/architecture/
#: test_one_fictional_deployment.py`` is what keeps it that way.

# --- Budgets -------------------------------------------------------------------

#: How long loading one scenario may take. The console's development loop must
#: not wait on the dataset, and a budget nobody measures is a wish.
FIXTURE_SCENARIO_LOAD_BUDGET_SECONDS: Final = 2.0

#: How large the committed fixture tree may grow. Generous enough for a real
#: estate, small enough that a clone is not an event.
FIXTURE_COMMITTED_BYTES_BUDGET: Final = 4 * 1024 * 1024

# --- The generated scale scenario ----------------------------------------------

#: The seed the scale generator runs from. Fixed, so the tenth generation is the
#: first one again.
SCALE_SEED: Final = 20260807

SCALE_RUN_COUNT: Final = 10_000
SCALE_EVENT_COUNT: Final = 10_000
SCALE_RESOURCE_COUNT: Final = 10_000
SCALE_CONFIG_NODE_COUNT: Final = 500

# --- The mock server -----------------------------------------------------------

#: The port ``python -m tools.mockplane serve`` binds by default. One above the
#: console's own, so the development loop can run both without a flag.
MOCK_SERVER_DEFAULT_PORT: Final = 8422

#: How many events per second the streaming mock emits when nothing says
#: otherwise. Slow enough to watch, fast enough not to bore a reviewer.
MOCK_STREAM_EVENTS_PER_SECOND: Final = 4.0


__all__ = [
    "DEFAULT_FIXTURE_SCENARIO",
    "DEMONSTRATION_LABEL",
    "DEMONSTRATION_LABEL_FIELD",
    "FIXTURE_COMMITTED_BYTES_BUDGET",
    "FIXTURE_CONTRACT_DIR_NAME",
    "FIXTURE_ENDPOINTS_FILENAME",
    "FIXTURE_MANIFEST_FILENAME",
    "FIXTURE_OPENAPI_FILENAME",
    "FIXTURE_REFERENCE_INSTANT",
    "FIXTURE_ROOT_DIR_NAME",
    "FIXTURE_SCENARIO_DIR_NAME",
    "FIXTURE_SCENARIO_LOAD_BUDGET_SECONDS",
    "FIXTURE_SCENARIO_NAMES",
    "GENERATED_FIXTURE_SCENARIOS",
    "MOCK_SERVER_DEFAULT_PORT",
    "MOCK_STREAM_EVENTS_PER_SECOND",
    "NINJASRE_CAPTURE_ENDPOINT_ENV",
    "NINJASRE_CAPTURE_NODES_ENV",
    "NINJASRE_CAPTURE_RAW_DIR_ENV",
    "NINJASRE_CAPTURE_SSH_USER_ENV",
    "NINJASRE_CAPTURE_TOKEN_ENV",
    "NINJASRE_FIXTURE_ROOT_ENV",
    "NINJASRE_FIXTURE_SCENARIO_ENV",
    "NINJASRE_IDENTIFIER_FILE_ENV",
    "NINJASRE_PSEUDONYM_KEY_ENV",
    "SCALE_CONFIG_NODE_COUNT",
    "SCALE_EVENT_COUNT",
    "SCALE_RESOURCE_COUNT",
    "SCALE_RUN_COUNT",
    "SCALE_SEED",
]
