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

.PHONY: install lint format format-check typecheck test fast test-fast test-sweeps \
	console-setup console-install console-format console-format-check \
	console-lockfile console-lint console-typecheck console-test console-build \
	console-client console-client-check console-budget console-e2e console-e2e-run \
	console-e2e-sweep console-visual console-visual-accept console-static console-check \
	console-dynamic-routes \
	check-console-boundary \
	check-imports check-constants check-protocols check-deps check-vendor-sdks \
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

# How many workers the suite runs across. A number rather than `auto`, because
# `auto` asks the machine how many CPUs it has and a container is told the
# node's count, not its own cgroup's — on the CI runner that is ten workers
# against a six-CPU, 4Gi limit, which thrashes instead of finishing sooner.
#
# Four rather than more because `--dist loadgroup` keeps the console suites on
# one worker, so the run is bounded by how long they take. Past a couple of
# workers everything else already finishes before they do, and further workers
# buy memory pressure and nothing else.
PYTEST_WORKERS ?= 4

# Two runs, and the split is the point. A latency budget measured while three
# other workers have the CPU measures contention, not the code it names — and a
# budget that fails for that reason teaches people to widen budgets. The
# `benchmark` marker already means "asserts a latency budget rather than a
# behaviour", so it is exactly the line to cut along: everything else in
# parallel, the budgets alone on an uncontended machine.
# Two suites are held out of the default run, and both for the same reason:
# they are about the console's own gate rather than about this repository's
# behaviour, and running them here costs twenty minutes and leaves debris.
#
# `test_console_gate.py` proves each console check fails on a seeded fault. To
# do that it splices broken files into `console/` and removes them again — so a
# lint or a format-check running beside it sees a file that is not the tree's,
# and an interrupted run leaves a `seeded.spec.ts` behind for somebody to find
# and wonder about. It takes a lock for exactly this reason; holding the lock
# does not stop the other run, it just makes the collision legible.
#
# `test_console_visual_regression.py` compares committed baselines. On a branch
# that is changing screens those baselines are *meant* to differ, so it reports
# a difference that means "the work happened" and reddens the gate for it.
#
# Neither is dropped: `ci-run` below runs `console-visual` as its own job, and
# the gate contract belongs beside it. Run them deliberately —
# `pytest tests/contract/console/test_console_gate.py` — not on every commit.
HELD_OUT_OF_TEST := \
	--ignore=tests/contract/console/test_console_gate.py \
	--ignore=tests/contract/console/test_console_visual_regression.py

test: ## Run the test suite: behaviour across $(PYTEST_WORKERS) workers, budgets alone
	$(RUN) pytest -n $(PYTEST_WORKERS) --dist loadgroup -m "not benchmark" $(HELD_OUT_OF_TEST)
	$(RUN) pytest -m benchmark $(HELD_OUT_OF_TEST)

# --- The inner loop ----------------------------------------------------------
#
# `verify` is the gate, it runs before a push, and nothing below takes anything
# away from it. This is the other target: what to run *during* an edit, when the
# question is "did I just break something" rather than "does the repository
# still hold". Those are different questions and they deserve different runs.
#
# Two measurements decided the shape, and both are worth writing down because
# the obvious design fails on them.
#
# **Collection costs more than most tests do.** Importing all thirteen thousand
# of them takes about fifty seconds here — and a marker filter cannot buy any of
# it back, because `-m` deselects *after* collection. `pytest -m "not slow"`
# over the whole tree therefore has a fifty-second floor no matter what it then
# skips. A tier that finishes in seconds has to collect less, which means naming
# paths, not naming markers. `tests/unit/platform/memory` collects in two.
#
# **A few tests are not about the edit at all.** They walk every committed file
# and answer "does the repository still hold" — one directory of scenario
# fixtures, no committed module importing a removed vendor, no stated catalogue
# total that has gone stale. An edit to `platform/memory` cannot change their
# answer, and they are most of what makes `tests/unit/tools` take thirty-five
# seconds rather than twelve. They now carry the `sweep` marker. One more test
# posts a thousand webhooks to prove the shedder bounds them: that is a real
# behaviour assertion and it stays in `make test`, but the wall clock is the
# volume rather than the assertion, so it carries `load` and sits this out.
#
# So: paths from what changed, markers to drop what an edit cannot change.

# The one to type. `lint` costs four tenths of a second over the whole tree and
# catches the break that would otherwise be found sixty seconds into a
# selection, so the inner loop pays for it without noticing.
fast: lint test-fast ## The inner loop: lint, then the tests that mirror what you changed

#: The test paths `test-fast` runs. Empty means "work it out from git".
SCOPE ?=

# How a path is worked out. Three rules, and they are applied to whatever names
# a path — a file `git status` reported, or an entry a person put in `SCOPE`:
#
#   1. A path under a runtime package selects the mirroring directory under
#      `tests/unit`, walking up until one exists: `platform/memory/store.py`
#      selects `tests/unit/platform/memory`, `core/llm/x/y/z.py` selects
#      `tests/unit/core/llm`. A path that *is* a directory maps from itself
#      rather than from its parent, so `SCOPE=platform/memory` selects
#      `tests/unit/platform/memory` and not `tests/unit/platform`.
#   2. Any component of its path that names a suite under `tests/contract` or
#      `tests/security` selects that suite too. `gateway/http/routes/runs.py`
#      selects `tests/contract/runs`; `platform/persistence/store.py` selects
#      `tests/contract/persistence`. Crude, and it earns its keep: those are the
#      suites that break for a reason `tests/unit` never sees.
#   3. A path under `tests/` selects itself.
#
# Without SCOPE the paths come from `git status --untracked-files=all` — the
# working tree, which is what "after every edit" means.
#
# `console/` selects nothing here — it has its own gate, `make console-check`.
# Anything else that maps to nothing is *named on stdout* rather than passed
# over in silence, because a file whose change this tier cannot test is the one
# thing somebody needs to be told.
#
# **One mapping, used by both modes.** It used to exist only in the automatic
# branch, and `SCOPE=` handed its string to pytest untouched — so naming the
# source directory you had just edited collected zero tests, hit pytest's exit
# code 5, and was reported as a pass. A fast tier that runs nothing and goes
# green is one people stop believing, so the mapping moved into `map_path` and
# both branches call it. The two branches differ only in what an unmappable
# path means: the automatic mode is reading a working tree it did not choose,
# so it names the file and carries on, while a SCOPE entry is a request that
# cannot be honoured and refuses the whole invocation before spending a minute
# on the paths that did map.
#
# **One pytest per path, not one pytest over all of them.** Several test modules
# import their sibling `conftest` by bare name, which resolves through the
# `sys.path` entry pytest adds per rootdir-relative test directory. Hand it two
# directories that both have a `conftest.py` and the wrong one can win:
# `tests/unit/gateway/http` plus `tests/contract/runs` fails collection with
# `cannot import name ORG from conftest`, naming the other suite's file. The
# whole-tree run in `make test` does not hit this and neither does either path
# alone, so the defect belongs to the combination, not to the tests. A process
# per path also means one broken selection reports and the rest still run.
#
# Pytest's exit code 5 — "collected something, selected nothing" — is a pass
# here and only here. Editing a module whose every test is a `sweep` deselects
# the lot, and a tier that went red for having correctly skipped what it says it
# skips would be untrustworthy within a week. Every other non-zero code fails.
# It stays a pass because the selection is now proved to name real test
# directories before pytest is reached; an empty selection never gets that far.
test-fast: ## The inner loop: the tests that mirror what you changed, in seconds
	@map_path() { \
		file="$${1%/}"; \
		case "$$file" in \
			console|console/*) return 2 ;; \
			tests|tests/*) \
				if [ -e "$$file" ]; then printf '%s\n' "$$file"; return 0; fi; \
				return 2 ;; \
		esac; \
		hit=1; \
		if [ -d "$$file" ]; then dir="tests/unit/$$file"; \
		else dir="tests/unit/$${file%/*}"; fi; \
		while [ "$$dir" != "tests/unit" ] && [ ! -d "$$dir" ]; do \
			dir="$${dir%/*}"; \
		done; \
		if [ -d "$$dir" ] && [ "$$dir" != "tests/unit" ]; then \
			printf '%s\n' "$$dir"; hit=0; \
		fi; \
		for part in $$(echo "$$file" | tr / ' '); do \
			for suite in tests/contract/$$part tests/security/$$part; do \
				if [ -d "$$suite" ]; then printf '%s\n' "$$suite"; hit=0; fi; \
			done; \
		done; \
		return $$hit; \
	}; \
	paths=""; unmapped=""; \
	if [ -n "$(SCOPE)" ]; then \
		for file in $(SCOPE); do \
			selected=$$(map_path "$$file"); code=$$?; \
			if [ $$code -eq 0 ]; then paths="$$paths $$selected"; \
			else unmapped="$$unmapped $$file"; fi; \
		done; \
		if [ -n "$$unmapped" ]; then \
			printf 'test-fast: SCOPE selects no tests:\n'; \
			printf '  %s\n' $$unmapped; \
			printf '  A scope that runs nothing must not report success, so this is a\n'; \
			printf '  failure rather than an empty pass. Name a source path — it is\n'; \
			printf '  mapped the same way the automatic mode maps it — or a tests/ path.\n'; \
			case "$$unmapped" in *console*) \
				printf '  The console is not in this tier at all: make console-check.\n' ;; \
			esac; \
			exit 2; \
		fi; \
	else \
		for file in $$(git status --porcelain=1 --untracked-files=all \
				| cut -c4- | sed 's/.* -> //'); do \
			selected=$$(map_path "$$file"); code=$$?; \
			if [ $$code -eq 0 ]; then paths="$$paths $$selected"; \
			elif [ $$code -eq 1 ]; then unmapped="$$unmapped $$file"; fi; \
		done; \
		if [ -n "$$unmapped" ]; then \
			printf 'test-fast: no test path mirrors these, so nothing here covers them:\n'; \
			printf '  %s\n' $$unmapped; \
			printf '  `make verify` does. This tier is not a substitute for it.\n'; \
		fi; \
	fi; \
	if [ -n "$$paths" ]; then \
		paths=$$(printf '%s\n' $$paths | sort -u | tr '\n' ' '); \
	fi; \
	if [ -z "$$paths" ]; then \
		echo "test-fast: nothing selected. Name it — make test-fast SCOPE=tests/unit/core"; \
		exit 0; \
	fi; \
	echo "test-fast: $$paths"; \
	status=0; \
	for path in $$paths; do \
		$(RUN) pytest "$$path" -p no:cacheprovider --no-header -q \
			-m "not benchmark and not sweep and not load and not e2e" \
			$(HELD_OUT_OF_TEST); \
		code=$$?; \
		if [ $$code -ne 0 ] && [ $$code -ne 5 ]; then status=1; fi; \
	done; \
	exit $$status

# What `test-fast` drops, by name, so the drop is a thing you can run rather
# than a thing you have to reconstruct. `verify` runs all of it through `test`;
# this target is here for the moment you have touched a guard on purpose and
# want its answer without waiting for the whole gate.
test-sweeps: ## Run only the whole-repository sweeps, the budgets, and the load assertion
	$(RUN) pytest -m "sweep or load" $(HELD_OUT_OF_TEST)
	$(RUN) pytest -m benchmark $(HELD_OUT_OF_TEST)

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
# targets are how it is held to the same standard: the static checks are part of
# `verify`, and every check is individually runnable. The browser checks remain
# explicit targets because a contributor fixing a type error should not have to
# sit through a browser suite to find out whether they fixed it.
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

console-dynamic-routes: ## Fail if a shell route is prerendered instead of served live
	$(RUN) python -m tools.console_gate dynamic-routes

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

console-static: ## Run the console checks without browser or visual-baseline suites
	$(RUN) python -m tools.console_gate static

console-check: ## Every console check, cheapest failure first
	$(RUN) python -m tools.console_gate all

console-gate-contract: ## Contract test proving console gate checks fail on seeded faults
	$(RUN) pytest tests/contract/console/test_console_gate.py

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

check-vendor-sdks: ## Reject a vendor LLM SDK imported outside core/llm/
	$(RUN) python tools/check_vendor_sdks.py

check-literals: ## Reject a missing comma that merges two capability metadata entries
	$(RUN) python tools/check_metadata_literals.py

check-raw-sql: ## Reject SQL, Cypher, or a database driver outside platform/persistence/
	$(RUN) python tools/check_raw_sql.py

# Run as a module for the same reason check-integrations is: it imports the
# persistence store's own status enumeration, and `platform/` only wins its
# name over the stdlib module when the repository root leads sys.path.
check-run-status-vocabulary: ## Reject a fixture or console run status the persistence store does not declare
	$(RUN) python -m tools.check_run_status_vocabulary

# The same guard for the enumeration that never had one, and for the same
# reason it is a module rather than a script.
check-incident-states: ## Reject a console incident state the persistence store does not declare
	$(RUN) python -m tools.check_incident_state_vocabulary

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
# The console's static checks come after the Python ones and before the Python
# suite. Browser and visual-baseline checks remain available through their
# dedicated targets and are included in `ci-run` below.



# The loop for changing one screen and looking at it.
#
# Builds here, pushes to the registry, and writes the digests into the
# repository the cluster reconciles from. It bypasses the delivery pipeline —
# no SBOM, no scan, no verification of the source — and the commit it writes
# says so, because a staging image nobody can trace is worth exactly as much
# as the note explaining where it came from.
#
# Not `kubectl set image`. Argo runs this application with `selfHeal` on and
# reverts anything the cluster is told directly, which looks like a deploy that
# worked until it quietly is not there any more.
deploy-stg: ## Build here, publish, and point staging at it (COMPONENTS=web to narrow)
	scripts/deploy/stg $(COMPONENTS)

# What a local run leaves behind, and why this has its own target.
#
# `make ci` builds four images for the scan and three more for the browser
# suite, every time. Left alone they accumulate — this repository put four
# gigabytes of build cache and three and a half of scratch tags on one disk in
# a single afternoon.
#
# The reason to care is that a full disk does not announce itself as one. Trivy
# reported `no space left on device` while a hundred gigabytes were free, and
# two image layers were written truncated, so containers started and Python
# refused their own source for containing null bytes. Neither symptom mentions
# the disk, and both cost hours to trace back to it.
#
# Scoped to this repository's own images. Nothing here touches another
# project's, which is why it is not `docker system prune`.
clean-containers: ## Remove the images, caches and containers a local run leaves behind
	@echo "Removing this repository's scratch images..."
	-@docker images --format '{{.Repository}}:{{.Tag}}' \
		| grep -E '^(ninjasre-verify-|ninjasre/[a-z]+:(ci|cve|scan|fix))' \
		| xargs -r docker rmi -f >/dev/null 2>&1
	@echo "Removing stopped containers and dangling layers..."
	-@docker container prune -f >/dev/null 2>&1
	-@docker image prune -f >/dev/null 2>&1
	@echo "Removing unused build cache..."
	-@docker builder prune -f >/dev/null 2>&1
	@echo "Removing browser traces and rendered output..."
	-@rm -rf console/test-results console/playwright-report
	@# The built site's contents, not its directory: `docs/site/build/.gitignore`
	@# is tracked, and removing the directory deleted a committed file. A sweep
	@# that takes something out of Git is worse than the accumulation it was
	@# written to prevent.
	-@find docs/site/build -mindepth 1 ! -name .gitignore -delete 2>/dev/null || true
	@$(MAKE) --no-print-directory disk

disk: ## Report what this repository is occupying, and what is left
	@df -h . | tail -1 | awk '{printf "disk:   %s of %s used, %s free (%s)\n", $$3, $$2, $$4, $$5}'
	@docker system df 2>/dev/null \
		| awk 'NR>1 {printf "docker: %-14s %8s total, %8s reclaimable\n", $$1" "$$2, $$4, $$5}'
	@# Images no container is using and this repository does not declare. Named
	@# rather than removed: this machine builds more than this project, and a
	@# sweep that guessed would take somebody else's base image with it. A
	@# toolchain pulled for one experiment is easy to forget and expensive to
	@# keep — the Go image behind one abandoned attempt was 1.26GB.
	@echo 'unused, not declared in deploy/images/base-images.env:'
	@docker images --format '{{.Repository}}:{{.Tag}} {{.Size}}' 2>/dev/null \
		| grep -vE "^($$(sed -n 's/^BASE_[A-Z_]*=//p' deploy/images/base-images.env \
			| paste -sd'|' -)|ninjasre)" \
		| while read -r image size; do \
			docker ps -a --format '{{.Image}}' | grep -qxF "$$image" || printf '  %-46s %s\n' "$$image" "$$size"; \
		done | sort -k2 -hr | head -8

# Everything the hosted workflow used to do, here.
#
# `verify.yml` no longer runs on a push. Every job it had runs on a developer
# machine, and running them on hosted minutes for every push spent most of a
# month's allowance in an afternoon without once showing something a local run
# had not. This target is what replaced it, and the workflow is still there for
# the runs where a clean machine is the point.
#
# Ordered cheapest first, so a failure that a second of linting would have
# caught does not arrive twenty minutes into a browser suite.
#
# Needs Docker for the persistence, compose, visual, image and backup halves,
# and `helm` for the chart. Each says so when it cannot run.
ci: ## Everything CI used to run, locally, cleaning up after itself
	$(MAKE) ci-run
	@$(MAKE) --no-print-directory clean

# The work itself. Separate from `ci` so the cleanup above runs whether this
# passed or failed — a failed run leaves the most behind, and is exactly when
# somebody is least likely to remember to sweep.
ci-run: verify test-postgres test-synthetic docs-build console-build console-visual \
	console-e2e-run console-gate-contract images-scan chart-check backup-cycle ## The gate, without the sweep

images-scan: ## Build every deployment image and scan it for fixable HIGH/CRITICAL
	@for component in app console proxy; do \
		docker build -f "deploy/images/$$component.Dockerfile" -t "ninjasre/$$component:ci" . || exit 1; \
	done
	docker build -f deploy/images/postgres.Dockerfile -t ninjasre/postgres:ci .
	@for image in app console proxy postgres; do \
		docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
			-v "$(PWD)/.trivyignore.yaml:/tmp/ignore.yaml:ro" \
			aquasec/trivy:0.74.0 image --severity HIGH,CRITICAL --ignore-unfixed \
			--ignorefile /tmp/ignore.yaml --exit-code 1 --quiet "ninjasre/$$image:ci" || exit 1; \
	done

chart-check: ## Lint the chart and render it, the way the workflow did
	helm lint deploy/helm/ninjasre
	helm template ninjasre deploy/helm/ninjasre > /dev/null

backup-cycle: ## Back up, restore into a clean database, and verify the result
	sh test-infra/backup/cycle.sh

verify: lint format-check typecheck check-imports check-constants \
	check-protocols check-deps check-vendor-sdks check-literals check-raw-sql \
	check-run-status-vocabulary check-incident-states \
	check-credentials check-console-boundary check-integrations \
	check-integration-docs check-env-example check-docs check-doc-examples \
	console-static test ## The single quality gate

# Which wave of specs the branch/slug contract reads. Override per invocation
# (`make close-task SPECS_DIR=specs_v2`) or export NINJASRE_SPECS_DIR once for a
# whole session; the script honours both, preferring the flag.
SPECS_DIR ?= $(or $(NINJASRE_SPECS_DIR),specs)

close-task: verify ## Fast-forward master to the current task branch and open the next one
	$(RUN) python tools/close_task_branch.py --specs-dir $(SPECS_DIR)

clean: clean-containers ## Remove caches and build artefacts, containers included
	rm -rf build dist .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov
	find . -type d -name __pycache__ -not -path './.venv/*' -not -path './_research/*' \
		-exec rm -rf {} + 2>/dev/null || true

help: ## List the available targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
