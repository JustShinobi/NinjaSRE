"""Every bound the chaos and end-to-end suites run inside.

The suites live beside the tests, outside the package tiers, for the same
reason the scenario harness does — apparatus is not something a deployment
ships. The bounds are still bounds, so they live here with every other bound,
and the environment-variable names with them: a bare string naming a variable is the
literal ``tools/check_constants.py`` exists to reject everywhere else.

Three sets of numbers dominate. The **timeouts** decide how long a suite waits
before calling an injection a non-event rather than a slow one; too short and
every run is invalid, too long and a broken cluster costs an afternoon. The
**cost bounds** are the only thing standing between a cloud scenario and an
unbounded bill, so they are declared per scenario and reported against. And the
**lock and reaper ages** decide when a run that never came back stops holding
the cluster and its resources — both are recovery from a process that was
killed rather than stopped, which is the case no amount of careful teardown
covers.
"""

from __future__ import annotations

from typing import Final

# --- Chaos experiment layout -------------------------------------------------

#: The declarative fault, in the chaos framework's own manifest form.
CHAOS_MANIFEST_FILENAME: Final = "chaos.yaml"

#: The alert the injected fault is expected to raise, as the pipeline's real
#: entry point receives one.
CHAOS_ALERT_FILENAME: Final = "alert.json"

#: What the experiment says it will produce, written down before it runs.
CHAOS_EXPECTATION_FILENAME: Final = "expected.yml"

#: The fourteen faults the suite covers, in the order the catalogue reads them:
#: process, resource, storage, network, then name resolution and HTTP.
CHAOS_EXPERIMENT_IDS: Final[tuple[str, ...]] = (
    "pod-kill",
    "container-kill",
    "cpu-stress",
    "memory-stress",
    "io-latency",
    "network-delay",
    "network-partition",
    "network-corrupt",
    "bandwidth-limit",
    "dns-error",
    "dns-random",
    "http-abort",
    "http-delay",
    "http-response-fault",
)

#: The label every resource this suite creates carries, so a sweep can find
#: what a killed run left behind without knowing what it was doing.
CHAOS_SUITE_LABEL: Final = "app.kubernetes.io/managed-by"

#: The value of that label.
CHAOS_SUITE_LABEL_VALUE: Final = "ninjasre-chaos"

#: The label carrying the experiment a resource belongs to.
CHAOS_EXPERIMENT_LABEL: Final = "ninjasre.io/experiment"

#: The manifest API group a chaos experiment must declare. A manifest outside it
#: is not a fault this suite knows how to remove, and applying something it
#: cannot clean up is the one thing cleanup cannot recover from.
CHAOS_API_GROUP: Final = "chaos-mesh.org"

# --- What a generated alert says raised it ------------------------------------

#: The label carrying the chaos experiment an alert belongs to.
ALERT_EXPERIMENT_LABEL: Final = "ninjasre_experiment"

#: The label carrying the injected fault's own name — the chaos object, or the
#: demo's feature flag.
ALERT_FAULT_LABEL: Final = "ninjasre_fault"

#: The label carrying the cloud scenario an alert belongs to.
ALERT_SCENARIO_LABEL: Final = "ninjasre_scenario"

#: Every label a real-run suite may use to say what raised an alert, in the
#: order a reader should prefer them: what was injected, then what object it
#: became. One list, because a report that had to know which suite it was
#: looking at to find the answer would be a report with three code paths.
ALERT_ORIGIN_LABELS: Final[tuple[str, ...]] = (
    ALERT_EXPERIMENT_LABEL,
    ALERT_SCENARIO_LABEL,
    ALERT_FAULT_LABEL,
)

# --- Chaos timing ------------------------------------------------------------

#: How long a validity probe waits for the injected fault to produce its
#: declared symptom before the run is reported invalid.
CHAOS_VALIDITY_TIMEOUT_SECONDS: Final[float] = 60.0

#: How often a validity probe re-reads the cluster while it waits.
CHAOS_VALIDITY_POLL_SECONDS: Final[float] = 2.0

#: How long cleanup waits for the cluster to return to its pre-injection
#: baseline before reporting that it did not.
CHAOS_BASELINE_TIMEOUT_SECONDS: Final[float] = 120.0

#: How long the preflight check waits for a cluster to answer at all.
CHAOS_PREFLIGHT_TIMEOUT_SECONDS: Final[float] = 30.0

#: How many pods may be unhealthy before the cluster is refused as a baseline.
#: Zero: an experiment scored against a cluster that was already broken measures
#: the cluster, not the agent.
CHAOS_MAX_UNHEALTHY_PODS: Final[int] = 0

# --- Cluster lock ------------------------------------------------------------

#: The file one cluster's lock is held in.
CHAOS_LOCK_FILENAME: Final = "cluster.lock"

#: How long a lock may go untouched before a later run treats it as abandoned.
#: A killed runner leaves its lock behind, and a suite that then refuses forever
#: is a suite somebody deletes the lock file for by hand.
CHAOS_LOCK_STALE_SECONDS: Final[float] = 3600.0

#: How long a second run waits for the lock before skipping.
CHAOS_LOCK_WAIT_SECONDS: Final[float] = 0.0

#: Where cluster locks live when the environment does not say.
NINJASRE_CHAOS_LOCK_DIR_ENV: Final = "NINJASRE_CHAOS_LOCK_DIR"

#: The kubeconfig the suites use. Unset means "whatever the tooling defaults
#: to", which is what a developer with one cluster expects.
NINJASRE_CHAOS_KUBECONFIG_ENV: Final = "NINJASRE_CHAOS_KUBECONFIG"

#: The cluster context the suites act on, when the kubeconfig holds several.
NINJASRE_CHAOS_CONTEXT_ENV: Final = "NINJASRE_CHAOS_CONTEXT"

# --- otel-demo ---------------------------------------------------------------

#: The namespace the demo application and its observability stack are installed
#: into.
OTEL_DEMO_NAMESPACE: Final = "otel-demo"

#: The feature-flag faults the demo suite exercises.
OTEL_DEMO_FAULT_IDS: Final[tuple[str, ...]] = (
    "cart-failure",
    "product-catalogue-failure",
    "recommendation-cache-failure",
    "ad-failure",
    "payment-failure",
)

#: The configuration object the demo's feature flags are read from. Patching it
#: is how a fault is turned on, which is why the fault injector needs nothing
#: but cluster access.
OTEL_DEMO_FLAG_CONFIG: Final = "flagd-config"

#: How long the demo suite waits for a flipped flag to show up as a symptom.
OTEL_DEMO_FAULT_TIMEOUT_SECONDS: Final[float] = 90.0

#: How long the demo's own installation is given to become ready.
OTEL_DEMO_INSTALL_TIMEOUT_SECONDS: Final[float] = 600.0

# --- Cloud end-to-end --------------------------------------------------------

#: The managed services the cloud suite exercises, one scenario each.
CLOUD_SCENARIO_IDS: Final[tuple[str, ...]] = (
    "eks",
    "ec2",
    "cloudwatch",
    "lambda",
    "ecs",
    "rds",
)

#: The tag every provisioned resource carries, naming the suite that made it.
#: A reaper that swept on anything less specific would be a reaper nobody dares
#: run in an account that holds something else.
CLOUD_SUITE_TAG_KEY: Final = "ninjasre:suite"

#: The value of that tag.
CLOUD_SUITE_TAG_VALUE: Final = "e2e"

#: The tag carrying the run a resource was provisioned for, which is what makes
#: teardown by identifier possible without an inventory file.
CLOUD_RUN_TAG_KEY: Final = "ninjasre:run-id"

#: The tag carrying the scenario, so a cost report can be read per scenario.
CLOUD_SCENARIO_TAG_KEY: Final = "ninjasre:scenario"

#: The tag carrying when the resource was provisioned, in ISO 8601. The reaper
#: reads it rather than the provider's own creation time, because the two differ
#: for anything created in stages and the suite's own stamp is the one it can
#: reason about.
CLOUD_CREATED_TAG_KEY: Final = "ninjasre:created-at"

#: How old a tagged resource must be, with no active run holding it, before the
#: reaper destroys it. Long enough that a slow provisioning step is never
#: reaped out from under a live run.
CLOUD_ORPHAN_MAX_AGE_SECONDS: Final[float] = 7200.0

#: What one run of each cloud scenario is allowed to cost, in US dollars.
#: Declared per scenario rather than as one number, because a managed database
#: and a function invocation are not the same order of expense and a single
#: bound would be either useless or wrong.
CLOUD_SCENARIO_COST_BOUNDS_USD: Final[dict[str, float]] = {
    "eks": 4.00,
    "ec2": 1.00,
    "cloudwatch": 0.50,
    "lambda": 0.25,
    "ecs": 1.50,
    "rds": 2.50,
}

#: What a whole cloud suite run is allowed to cost, whatever the per-scenario
#: bounds sum to. A second ceiling rather than a derived one: a scenario added
#: without anybody revisiting the total is exactly the change this catches.
CLOUD_SUITE_COST_BOUND_USD: Final[float] = 12.00

#: How long provisioning is given before a scenario is abandoned and torn down.
CLOUD_PROVISION_TIMEOUT_SECONDS: Final[float] = 1800.0

#: Where the cloud suite writes its per-run cost records when nobody says.
NINJASRE_E2E_ARTIFACTS_ENV: Final = "NINJASRE_E2E_ARTIFACTS"

# --- Capture -----------------------------------------------------------------

#: The suite a captured scenario is filed under, so a corpus reader can tell at
#: a glance which fixtures came from a real failure rather than from a design.
CAPTURE_SUITE: Final = "captured"

#: What a captured scenario's difficulty is set to before a human reviews it.
#: The easiest level, and not because a captured miss is easy. Every level above
#: this one *means* "at least one planted confounder", and a run against real
#: infrastructure has noise nobody planted and therefore none to declare —
#: writing a higher number would assert a confounder that does not exist, and
#: the corpus loader rightly refuses it. The review notes tell the reviewer to
#: raise it once they can name what misled the agent.
CAPTURE_DEFAULT_DIFFICULTY: Final[int] = 1

#: The marker a drafted answer key carries on every line a human still has to
#: decide. A draft that read like a finished key is how an unreviewed guess
#: becomes ground truth.
CAPTURE_REVIEW_MARKER: Final = "REVIEW"

#: How many recorded vendor exchanges one captured scenario may hold. A bound
#: rather than a preference: a run that called a log search forty times would
#: otherwise write a fixture nobody can read and a suite nobody can run fast.
CAPTURE_MAX_EXCHANGES: Final[int] = 200


__all__ = [
    "ALERT_EXPERIMENT_LABEL",
    "ALERT_FAULT_LABEL",
    "ALERT_ORIGIN_LABELS",
    "ALERT_SCENARIO_LABEL",
    "CAPTURE_DEFAULT_DIFFICULTY",
    "CAPTURE_MAX_EXCHANGES",
    "CAPTURE_REVIEW_MARKER",
    "CAPTURE_SUITE",
    "CHAOS_ALERT_FILENAME",
    "CHAOS_API_GROUP",
    "CHAOS_BASELINE_TIMEOUT_SECONDS",
    "CHAOS_EXPECTATION_FILENAME",
    "CHAOS_EXPERIMENT_IDS",
    "CHAOS_EXPERIMENT_LABEL",
    "CHAOS_LOCK_FILENAME",
    "CHAOS_LOCK_STALE_SECONDS",
    "CHAOS_LOCK_WAIT_SECONDS",
    "CHAOS_MANIFEST_FILENAME",
    "CHAOS_MAX_UNHEALTHY_PODS",
    "CHAOS_PREFLIGHT_TIMEOUT_SECONDS",
    "CHAOS_SUITE_LABEL",
    "CHAOS_SUITE_LABEL_VALUE",
    "CHAOS_VALIDITY_POLL_SECONDS",
    "CHAOS_VALIDITY_TIMEOUT_SECONDS",
    "CLOUD_CREATED_TAG_KEY",
    "CLOUD_ORPHAN_MAX_AGE_SECONDS",
    "CLOUD_PROVISION_TIMEOUT_SECONDS",
    "CLOUD_RUN_TAG_KEY",
    "CLOUD_SCENARIO_COST_BOUNDS_USD",
    "CLOUD_SCENARIO_IDS",
    "CLOUD_SCENARIO_TAG_KEY",
    "CLOUD_SUITE_COST_BOUND_USD",
    "CLOUD_SUITE_TAG_KEY",
    "CLOUD_SUITE_TAG_VALUE",
    "NINJASRE_CHAOS_CONTEXT_ENV",
    "NINJASRE_CHAOS_KUBECONFIG_ENV",
    "NINJASRE_CHAOS_LOCK_DIR_ENV",
    "NINJASRE_E2E_ARTIFACTS_ENV",
    "OTEL_DEMO_FAULT_IDS",
    "OTEL_DEMO_FAULT_TIMEOUT_SECONDS",
    "OTEL_DEMO_FLAG_CONFIG",
    "OTEL_DEMO_INSTALL_TIMEOUT_SECONDS",
    "OTEL_DEMO_NAMESPACE",
]
