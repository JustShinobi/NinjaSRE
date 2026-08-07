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
	check-imports check-constants check-protocols check-deps check-vendor-sdks \
	check-literals check-raw-sql check-credentials check-integrations \
	check-integration-docs preflight verify test-postgres test-synthetic \
	evaluate record-baseline benchmark benchmark-export \
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

# Not part of `verify`: it spends real tokens against a configured provider.
# Run it once per deployment, before anyone depends on that provider.
preflight: ## Verify the configured LLM provider end to end (makes live calls)
	$(RUN) python -m core.llm.preflight $(PROVIDER)

# The single gate CI runs. Ordered cheapest-first so an obvious failure reports
# in seconds rather than after the suite.
verify: lint format-check typecheck check-imports check-constants \
	check-protocols check-deps check-vendor-sdks check-literals check-raw-sql \
	check-credentials check-integrations check-integration-docs \
	test ## The single quality gate CI runs

close-task: verify ## Fast-forward master to the current task branch and open the next one
	$(RUN) python tools/close_task_branch.py

clean: ## Remove caches and build artefacts
	rm -rf build dist .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov
	find . -type d -name __pycache__ -not -path './.venv/*' -not -path './_research/*' \
		-exec rm -rf {} + 2>/dev/null || true

help: ## List the available targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
