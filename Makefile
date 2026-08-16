# POSIX shell only. On Windows, run these targets from Git Bash — no WSL and no
# compatibility layer is required (FR-017).

.DEFAULT_GOAL := help

UV ?= uv
RUN := $(UV) run

# The seven first-party runtime packages, in tier order from the leaf upward.
PYTHON_SOURCE_PATHS := config core platform integrations capabilities gateway surfaces

# Repository tooling and tests are linted and formatted but are not part of the
# distributed package, and `tools/` is outside the import contracts entirely.
# `wildcard` keeps the targets usable before either directory exists.
LINT_PATHS := $(PYTHON_SOURCE_PATHS) $(wildcard tools) $(wildcard tests)

.PHONY: install lint format format-check typecheck test \
	console-setup console-install console-format console-format-check \
	console-lockfile console-lint console-typecheck console-test console-build \
	console-client console-client-check console-budget console-e2e console-e2e-run \
	console-e2e-sweep console-visual console-visual-accept console-check \
	check-console-boundary \
	check-imports check-constants check-protocols check-deps check-config-parity \
	check-display-names check-vendor-sdks \
	check-literals check-raw-sql check-credentials check-integrations \
	check-integration-docs check-env-example env-example \
	check-docs check-doc-examples docs docs-build docs-serve \
	backup restore rotate-key deploy-preflight bundle-images \
	preflight verify test-postgres test-synthetic \
	evaluate record-baseline benchmark benchmark-export \
	test-proxmox-scenarios record-proxmox-baseline proxmox-scenario-coverage \
	e2e-proxmox-laboratory \
	chaos-setup chaos-teardown chaos-setup-eks chaos-teardown-eks \
	chaos-list chaos-run chaos-sweep \
	e2e-demo-setup e2e-demo-teardown e2e-demo e2e-cloud e2e-reap \
	close-task clean help

install: ## Provision the development environment from uv.lock
	$(UV) sync

lint: ## Run the ruff lint rules
	$(RUN) ruff check $(LINT_PATHS)

format: ## Rewrite files with the ruff formatter
	$(RUN) ruff format $(LINT_PATHS)

format-check: ## Fail if any file is not formatted (CI uses this)
	$(RUN) ruff format --check $(LINT_PATHS)

typecheck: ## Run mypy in strict mode over the first-party packages and repo tooling
	$(RUN) mypy $(PYTHON_SOURCE_PATHS) $(wildcard tools)

test: ## Run the test suite
	$(RUN) pytest

# Not part of `verify`: it builds a PostgreSQL image, starts it, and creates a
# database per test. That is a minute the gate should not spend on every commit,
# so it runs as its own CI job — and SC-005 is only satisfied when it has.
test-postgres: ## Run the persistence contract suite against a real PostgreSQL (needs Docker)
	$(RUN) pytest tests/contract/persistence --postgres

# The scenario corpus, offline. Part of `verify` through the test suite, and
# also here as its own target because a contributor changing capability
# selection wants the corpus alone with a filter on it, not the whole gate.
#
# Variables, all optional: FILTER (scenario id substring), SUITE, DIFFICULTY,
# INTEGRATION, ATTEMPTS, ARTIFACTS (a path for JSONL verdict records).
SYNTHETIC_ARGS := $(if $(FILTER),--scenario $(FILTER),) \
	$(if $(SUITE),--suite $(SUITE),) \
	$(if $(DIFFICULTY),--difficulty $(DIFFICULTY),) \
	$(if $(INTEGRATION),--integration $(INTEGRATION),) \
	$(if $(ATTEMPTS),--attempts $(ATTEMPTS),) \
	$(if $(ARTIFACTS),--artifacts $(ARTIFACTS),)

test-synthetic: ## Run the synthetic scenario corpus offline (no credentials, no tokens)
	PYTHONPATH="$(CURDIR)" $(RUN) python -m tests.harness $(SYNTHETIC_ARGS)

# The evaluation half. Where `test-synthetic` reports whether each scenario
# passed, these score every attempt on five independent axes and compare the
# result against a stored point, which is what makes "it got worse" a sentence
# with a number in it.
#
# Variables: BASELINE (the stored baseline's identifier), ATTEMPTS.
BASELINE ?= release
EVALUATE_ARGS := $(if $(ATTEMPTS),--attempts $(ATTEMPTS),)

evaluate: ## Score the corpus on five axes and gate it against BASELINE
	PYTHONPATH="$(CURDIR)" $(RUN) python -m tests.harness.regression.ci \
		--baseline $(BASELINE) $(EVALUATE_ARGS)

record-baseline: ## Store the current corpus run as the baseline named BASELINE
	PYTHONPATH="$(CURDIR)" $(RUN) python -m tests.harness.regression.ci \
		--record $(BASELINE) --note "$(NOTE)" $(EVALUATE_ARGS)

# The hypervisor half. It scores the *action* as well as the diagnosis, which
# the general corpus does not, and it runs from recorded API responses with no
# cluster — so it is part of `verify` through the test suite and is here as its
# own target because somebody changing a Proxmox tool wants these twenty-eight
# scenarios alone.
#
# Variables, all optional: DOMAIN (quorum, storage, guests, backups, host),
# SCENARIO (an identifier substring), NOTE (why a re-recorded baseline moved).
PROXMOX_SCENARIOS := PYTHONPATH="$(CURDIR)" $(RUN) python -m tests.harness.proxmox
PROXMOX_SCENARIO_ARGS := $(if $(DOMAIN),--domain $(DOMAIN),) \
	$(if $(SCENARIO),--scenario $(SCENARIO),)

test-proxmox-scenarios: ## Score the Proxmox scenarios and gate them against the baseline
	$(PROXMOX_SCENARIOS) $(PROXMOX_SCENARIO_ARGS)

record-proxmox-baseline: ## Re-record the Proxmox scenario baseline, for review as a change
	$(PROXMOX_SCENARIOS) --record --note "$(NOTE)"

proxmox-scenario-coverage: ## Print which scenario scores each hypervisor write
	$(PROXMOX_SCENARIOS) --coverage

# Variables: INTO (a document to splice the table into), RECORD (a stored
# cross-model benchmark record to render instead of running the corpus).
benchmark: ## Produce the benchmark table from the corpus, on the canonical runtime
	PYTHONPATH="$(CURDIR)" $(RUN) python -m tests.benchmarks.export \
		$(if $(RECORD),--record $(RECORD),--corpus tests/synthetic) $(EVALUATE_ARGS)

benchmark-export: ## Splice the benchmark table into INTO (default docs/evaluation-results.md)
	PYTHONPATH="$(CURDIR)" $(RUN) python -m tests.benchmarks.export \
		$(if $(RECORD),--record $(RECORD),--corpus tests/synthetic) \
		--into $(if $(INTO),$(INTO),docs/evaluation-results.md) $(EVALUATE_ARGS)

# The expensive suites. Not part of `verify` and not a pull-request gate: they
# need a cluster, they break it on purpose, and one of them spends money. They
# run before a release and on a schedule, and every miss they find is turned
# into a synthetic scenario so the cheap gate covers it from then on.
#
# Every one of these skips cleanly with a message when its infrastructure is not
# there, rather than failing — a suite that went red on every laptop is a suite
# somebody deletes.
#
# INVESTIGATOR names your deployment's composition root as `module:factory`.
# Composing an investigation needs a provider and the credential proxy, which is
# a deployment question; guessing it here would run against whatever ambient
# configuration happened to be lying around.
CHAOS := PYTHONPATH="$(CURDIR)" $(RUN) python -m tests.chaos
E2E := PYTHONPATH="$(CURDIR)" $(RUN) python -m tests.e2e
INVESTIGATOR ?=
INVESTIGATOR_ARG = $(if $(INVESTIGATOR),--investigator $(INVESTIGATOR),--investigator "")

chaos-setup: ## Create the local cluster and install the chaos framework
	sh test-infra/kind/setup.sh

chaos-teardown: ## Delete the local cluster
	sh test-infra/kind/teardown.sh

chaos-setup-eks: ## Create the cloud-backed cluster (this costs money)
	sh test-infra/eks/setup.sh

chaos-teardown-eks: ## Delete the cloud-backed cluster and report what is left
	sh test-infra/eks/teardown.sh

chaos-list: ## Print the chaos experiment catalogue (needs no cluster)
	$(CHAOS) list

# Variables: INVESTIGATOR (required), EXPERIMENT, RUN_ID, ARTIFACTS.
chaos-run: ## Inject every experiment, investigate, score, and clean up
	$(CHAOS) run $(INVESTIGATOR_ARG) \
		$(if $(EXPERIMENT),--experiment $(EXPERIMENT),) \
		$(if $(RUN_ID),--run-id $(RUN_ID),) \
		$(if $(ARTIFACTS),--artifacts $(ARTIFACTS),)

chaos-sweep: ## Remove faults a killed run left on the cluster
	$(CHAOS) sweep

e2e-demo-setup: ## Install the demo application and its observability stack
	$(E2E) demo-setup

e2e-demo-teardown: ## Remove the demo application
	$(E2E) demo-teardown

# Variables: INVESTIGATOR (required), FAULT, RUN_ID, ARTIFACTS.
e2e-demo: ## Run every demo feature-flag fault end to end
	$(E2E) $(if $(ARTIFACTS),--artifacts $(ARTIFACTS),) demo $(INVESTIGATOR_ARG) \
		$(if $(FAULT),--fault $(FAULT),) $(if $(RUN_ID),--run-id $(RUN_ID),)

# Variables: INVESTIGATOR (required), SCENARIO, RUN_ID, ARTIFACTS.
e2e-cloud: ## Provision, investigate, and destroy the cloud scenarios (this costs money)
	NINJASRE_E2E_CLOUD=1 $(E2E) $(if $(ARTIFACTS),--artifacts $(ARTIFACTS),) \
		cloud $(INVESTIGATOR_ARG) \
		$(if $(SCENARIO),--scenario $(SCENARIO),) $(if $(RUN_ID),--run-id $(RUN_ID),)

# Reports by default. DESTROY=1 is the second run, after somebody has read the
# first one — a sweep that destroys on its first invocation is one nobody dares
# point at an account that holds something else.
e2e-reap: ## Find (DESTROY=1 to remove) cloud resources a killed run left behind
	$(E2E) reap $(if $(DESTROY),--destroy,) $(if $(HOLDING),--holding $(HOLDING),)

# The destructive hypervisor scenarios and the rehearsal of every hypervisor
# write. Safe to run with no cluster: it uses the recorded stand-in and says so,
# which is the statement a release note needs. Set
# NINJASRE_PROXMOX_LABORATORY to the cluster this machine may break to run it
# for real. PLAN=1 prints the rehearsals and stops.
e2e-proxmox-laboratory: ## Run the destructive Proxmox scenarios against the laboratory
	PYTHONPATH="$(CURDIR)" $(RUN) python -m tests.e2e.proxmox $(if $(PLAN),--plan,)

# --- The console ---------------------------------------------------------------
#
# The console is TypeScript, so none of the Python tooling above sees it. These
# targets are how it is held to the same standard: every one of them is part of
# `verify`, and every one of them is individually runnable, because a
# contributor fixing a type error should not have to sit through a browser suite
# to find out whether they fixed it.
#
# Each is a thin wrapper over `tools/console_gate.py`, which owns the one piece
# of policy that cannot live in a Makefile: what to do on a machine that has no
# Node and no container runtime. It reports a named skip and succeeds, unless
# NINJASRE_CONSOLE_TOOLCHAIN=required is set — which CI sets, so the gate is
# complete where it is enforced.

console-setup: ## Provision the pinned Node, pnpm, and the console's dependencies
	$(RUN) python -m tools.console_toolchain setup

console-install: ## Update the committed lockfile from the manifest
	$(RUN) python -m tools.console_toolchain run install

console-format: ## Rewrite console files with the formatter
	$(RUN) python -m tools.console_toolchain run run format

console-format-check: ## Fail if any console file is not formatted
	$(RUN) python -m tools.console_gate format-check

console-lockfile: ## Fail if the committed lockfile has drifted from the manifest
	$(RUN) python -m tools.console_gate lockfile

console-lint: ## Run the console's lint rules
	$(RUN) python -m tools.console_gate lint

console-typecheck: ## Type-check the console
	$(RUN) python -m tools.console_gate typecheck

console-test: ## Run the console's unit suite against its coverage threshold
	$(RUN) python -m tools.console_gate test

console-build: ## Produce the console's standalone production build
	$(RUN) python -m tools.console_gate build

console-client: ## Regenerate the API client from the committed OpenAPI document
	$(RUN) python -m tools.console_toolchain run run client

console-client-check: ## Fail if the committed API client is not what the document generates
	$(RUN) python -m tools.console_gate client-check

console-budget: ## Fail if the stylesheet or the icon set is over its declared budget
	$(RUN) python -m tools.console_budget

console-e2e: ## Drive a browser against the built console and the committed dataset
	$(RUN) python -m tools.console_gate e2e

# Variables: BACKING (mock or compose), REPEAT (how many times to run it).
console-e2e-run: ## Run the browser suite against BACKING, REPEAT times
	$(RUN) python -m tools.console_e2e run \
		$(if $(BACKING),--backing $(BACKING),) $(if $(REPEAT),--repeat $(REPEAT),)

# The determinism sweep. Twenty runs, and a single flake is a defect to fix or a
# behaviour to demote to a unit test — never a test to disable.
console-e2e-sweep: ## Run the browser suite twenty times and fail on any flake
	$(RUN) python -m tools.console_e2e run --repeat 20

console-visual: ## Compare every registered screen against its committed baseline
	$(RUN) python -m tools.console_gate visual

# Not a flag on the comparison: accepting a baseline rewrites committed PNGs, so
# the acceptance is the commit somebody reviews.
console-visual-accept: ## Recapture the baselines, for review as a committed change
	$(RUN) python -m tools.console_visual accept

console-check: ## Every console check, cheapest failure first
	$(RUN) python -m tools.console_gate all

check-console-boundary: ## Reject a Python import of the console, or the reverse
	$(RUN) python tools/check_console_boundary.py

check-imports: ## Enforce the tier boundaries declared in .importlinter
	# On Linux, stdlib uuid.py unconditionally does `import platform` to tell
	# AIX from Linux, and click (imported by import-linter's CLI) pulls in uuid
	# before the CLI adds the repo root to sys.path. That caches the stdlib
	# platform module under the name our platform/ package needs. Leading
	# PYTHONPATH with the repo root wins the name before click ever runs.
	PYTHONPATH="$(CURDIR)" $(RUN) lint-imports

check-constants: ## Reject environment-variable names outside config/constants/
	$(RUN) python tools/check_constants.py

check-protocols: ## Reject a Protocol method body that is more than a docstring
	$(RUN) python tools/check_protocol_bodies.py

check-deps: ## Reject a telemetry package in the runtime dependency tree
	$(RUN) python tools/check_dependencies.py

# Wraps the contract suite directly rather than a standalone script: the map
# and the schema it is checked against both change from the Python side, and
# a second implementation of "walk the schema, walk the map" would be a
# second place for the two to drift apart.
check-config-parity: ## Reject a configuration field with no declared owner
	$(RUN) pytest tests/contract/console/test_console_config_ownership.py

check-display-names: ## Reject a catalogue id with no display name
	$(RUN) python -m tools.check_display_names

check-vendor-sdks: ## Reject a vendor LLM SDK imported outside core/llm/
	$(RUN) python tools/check_vendor_sdks.py

check-literals: ## Reject a missing comma that merges two capability metadata entries
	$(RUN) python tools/check_metadata_literals.py

check-raw-sql: ## Reject SQL, Cypher, or a database driver outside platform/persistence/
	$(RUN) python tools/check_raw_sql.py

check-credentials: ## Reject a credential read outside the vault and the proxy (FR-017)
	$(RUN) python tools/check_direct_credentials.py

# Run as a module rather than a script: this check imports the first-party
# packages instead of parsing them, and `platform/` only wins its name over the
# stdlib module when the repository root leads sys.path.
check-integrations: ## Reject an integration missing an artefact or an unprobed permission
	$(RUN) python -m tools.verify_integrations

check-integration-docs: ## Reject a stale generated integration catalogue
	$(RUN) python -m tools.generate_integration_docs --check

# Run as a module for the same reason: it imports the settings catalogue, and
# `platform/` only wins its name over the stdlib module when the repository root
# leads sys.path.
check-env-example: ## Reject a .env.example that has drifted from the settings catalogue
	PYTHONPATH="$(CURDIR)" $(RUN) python tools/generate_env_example.py --check

# Run as a module for the same reason again: the generator imports the
# capability registry, the integration catalogue, and the settings catalogue.
check-docs: ## Reject generated documentation that has drifted from the declarations
	$(RUN) python -m tools.check_docs_drift

docs: ## Regenerate the capability, integration, and configuration references
	$(RUN) python -m tools.generate_docs

check-doc-examples: ## Reject a documented command, target, or path that no longer works
	$(RUN) python -m tools.test_doc_examples

docs-build: ## Build the offline documentation site into docs/site/build
	$(RUN) python -m tools.build_docs $(if $(INTO),--into $(INTO),)

docs-serve: ## Build the site and serve it locally, with no network access at all
	$(RUN) python -m tools.build_docs --serve $(if $(PORT),--port $(PORT),)

env-example: ## Regenerate deploy/compose/.env.example from the settings catalogue
	PYTHONPATH="$(CURDIR)" $(RUN) python tools/generate_env_example.py

# --- Operating a deployment --------------------------------------------------
#
# Thin wrappers over the scripts in `deploy/ops/`. They are here because the
# Makefile is where an operator already looks, and the scripts are there because
# a deployment that has not cloned the repository still has to be able to run
# them.

# Variables: INTO (a directory for the artefact, default ./backups).
backup: ## Take one backup artefact covering relational, vector, and graph data
	sh deploy/ops/backup.sh $(if $(INTO),$(INTO),./backups)

# Variables: ARCHIVE (required).
restore: ## Version-check and restore ARCHIVE into NINJASRE_DATABASE_URL
	sh deploy/ops/restore.sh $(ARCHIVE)

# Variables: ORG (required), PREVIOUS_KEY (required), BATCH.
rotate-key: ## Re-encrypt every stored credential under the new key, online
	PYTHONPATH="$(CURDIR)" $(RUN) python deploy/ops/rotate_key.py \
		--org $(ORG) --previous-key $(PREVIOUS_KEY) $(if $(BATCH),--batch-size $(BATCH),)

deploy-preflight: ## Check a deployment's configuration and report what it may reach
	PYTHONPATH="$(CURDIR)" $(RUN) python deploy/ops/preflight.py

# Variables: OUTPUT (the archive path).
bundle-images: ## Export every image as one archive, for an air-gapped install
	sh deploy/images/bundle.sh $(if $(OUTPUT),$(OUTPUT),ninjasre-images.tar.gz)

# Not part of `verify`: it spends real tokens against a configured provider.
# Run it once per deployment, before anyone depends on that provider.
preflight: ## Verify the configured LLM provider end to end (makes live calls)
	$(RUN) python -m core.llm.preflight $(PROVIDER)

# The single gate CI runs. Ordered cheapest-first so an obvious failure reports
# in seconds rather than after the suite.
# The console's checks come after the Python ones and before the Python suite:
# they are the ones a contributor is most likely to have broken while working on
# the console, and the Python suite is the longest single step in the gate.
verify: lint format-check typecheck check-imports check-constants \
	check-protocols check-deps check-config-parity check-display-names check-vendor-sdks check-literals check-raw-sql \
	check-credentials check-console-boundary check-integrations \
	check-integration-docs check-env-example check-docs check-doc-examples \
	console-check test ## The single quality gate CI runs

# Which wave of specs the branch/slug contract reads. Override per invocation
# (`make close-task SPECS_DIR=specs_v2`) or export NINJASRE_SPECS_DIR once for a
# whole session; the script honours both, preferring the flag.
SPECS_DIR ?= $(or $(NINJASRE_SPECS_DIR),specs)

close-task: verify ## Fast-forward master to the current task branch and open the next one
	$(RUN) python tools/close_task_branch.py --specs-dir $(SPECS_DIR)

clean: ## Remove caches and build artefacts
	rm -rf build dist .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov
	find . -type d -name __pycache__ -not -path './.venv/*' -not -path './_research/*' \
		-exec rm -rf {} + 2>/dev/null || true

help: ## List the available targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
