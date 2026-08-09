"""How a deployment is shaped, and every bound the shaping implies.

Three profiles, one setting. ``dev`` is a contributor's laptop, ``standard`` is a
team self-hosting on one machine, and ``enterprise`` is a cluster. The profile is
not a label: it decides the sandbox profile, where the credential proxy runs, and
how much work the deployment will take at once — and it decides all three
together, because a deployment that ran the in-process proxy with cluster
concurrency would be a combination nobody chose and nobody tested.

Two numbers here are load-bearing rather than tuning.

``STANDARD_PROFILE_CONTAINER_COUNT`` is four, and a test asserts the Compose file
still is. Every additional stateful service is a backup strategy, an upgrade
path, and a failure mode the operator inherits without asking for it, so growing
this number is a decision rather than a consequence.

``FIRST_INVESTIGATION_BUDGET_SECONDS`` is fifteen minutes, which is roughly the
attention an evaluating engineer gives an unfamiliar self-hosted tool. Beyond it
most evaluations end before the tool has demonstrated anything, so it is a
product constraint that happens to be measurable rather than an aspiration.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

# --- Profile selection -------------------------------------------------------

#: The one setting that picks a deployment shape (FR-005). Everything the shape
#: implies — sandbox, proxy placement, concurrency — is derived from it rather
#: than configured a second time, so a deployment cannot be half one profile.
NINJASRE_DEPLOYMENT_PROFILE_ENV: Final = "NINJASRE_DEPLOYMENT_PROFILE"

DEPLOYMENT_PROFILE_DEV: Final = "dev"
DEPLOYMENT_PROFILE_STANDARD: Final = "standard"
DEPLOYMENT_PROFILE_ENTERPRISE: Final = "enterprise"

#: One person's own infrastructure, on one small machine. Not "standard, but
#: less": it is the only profile that declares a resource ceiling and enforces
#: it, because it is the only one running beside the things it watches, on
#: hardware whose spare capacity is somebody's media server.
DEPLOYMENT_PROFILE_HOMELAB: Final = "homelab"

#: Ordered by how much work the profile will take at once, smallest first. The
#: order is not decoration: a test asserts the concurrency ceilings rise along
#: it, which is what stops a new profile being given a ceiling nobody compared
#: to the others.
DEPLOYMENT_PROFILES: Final[tuple[str, ...]] = (
    DEPLOYMENT_PROFILE_DEV,
    DEPLOYMENT_PROFILE_HOMELAB,
    DEPLOYMENT_PROFILE_STANDARD,
    DEPLOYMENT_PROFILE_ENTERPRISE,
)

#: What an unconfigured process gets. ``dev`` rather than ``standard``, because
#: the unconfigured process is almost always a contributor who has just cloned
#: the repository — and the profiles differ in what they *require*, so guessing
#: high fails to start on a machine that has everything a contributor needs.
DEFAULT_DEPLOYMENT_PROFILE: Final = DEPLOYMENT_PROFILE_DEV

# --- What each profile is made of --------------------------------------------

#: Service names, which are also the Compose service keys and the Helm
#: deployment names. One vocabulary, so "the proxy is unhealthy" means the same
#: thing in a log line, a compose file, and a chart.
SERVICE_APP: Final = "app"
SERVICE_CONSOLE: Final = "console"
SERVICE_POSTGRES: Final = "postgres"
SERVICE_PROXY: Final = "proxy"

DEV_PROFILE_SERVICES: Final[tuple[str, ...]] = (SERVICE_APP, SERVICE_POSTGRES)
STANDARD_PROFILE_SERVICES: Final[tuple[str, ...]] = (
    SERVICE_APP,
    SERVICE_CONSOLE,
    SERVICE_POSTGRES,
    SERVICE_PROXY,
)

#: The dev profile is the application and its database, and nothing else — the
#: proxy runs in-process and the console is served by the application (FR-002).
DEV_PROFILE_CONTAINER_COUNT: Final[int] = len(DEV_PROFILE_SERVICES)

#: Four, and pinned. See the module docstring.
STANDARD_PROFILE_CONTAINER_COUNT: Final[int] = len(STANDARD_PROFILE_SERVICES)

#: The homelab profile is the same four components, and that is the decision
#: rather than an accident of copying. The credential proxy keeps its own
#: container because it is the only process holding a secret and its isolation
#: is the whole reason it exists; folding it into the application to save a
#: hundred megabytes would trade the deployment's one security boundary for
#: about two per cent of the footprint.
HOMELAB_PROFILE_SERVICES: Final[tuple[str, ...]] = STANDARD_PROFILE_SERVICES
HOMELAB_PROFILE_CONTAINER_COUNT: Final[int] = len(HOMELAB_PROFILE_SERVICES)

# --- The homelab footprint -----------------------------------------------------

#: What the whole stack is allowed, in mebibytes and in CPUs. Four gibibytes and
#: two cores is a guest an operator can spare on a machine that is already doing
#: something else, which is the only size that matters here: a guardian that
#: needed a node to itself would be competing with what it is guarding.
#:
#: Declared rather than measured-and-hoped: the numbers below are written into
#: the compose file as per-service limits, so the container runtime enforces
#: what the profile claims instead of the claim being a note in a document.
HOMELAB_TOTAL_MEMORY_MIB: Final[int] = 4_096
HOMELAB_TOTAL_CPUS: Final[float] = 2.0

#: How the ceiling is divided. Postgres gets a gibibyte because it holds the
#: signals, the incidents and the graph in one database; the application gets
#: the largest share because it is the only one that runs an investigation; the
#: proxy gets the smallest because it forwards bytes and holds no history.
HOMELAB_MEMORY_LIMITS_MIB: Final[Mapping[str, int]] = {
    SERVICE_POSTGRES: 1_024,
    SERVICE_PROXY: 256,
    SERVICE_APP: 2_304,
    SERVICE_CONSOLE: 512,
}

HOMELAB_CPU_LIMITS: Final[Mapping[str, float]] = {
    SERVICE_POSTGRES: 0.5,
    SERVICE_PROXY: 0.25,
    SERVICE_APP: 1.0,
    SERVICE_CONSOLE: 0.25,
}

#: What "idle" means when a soak is judging whether the deployment stayed inside
#: its footprint. Well under the ceiling, because a deployment sitting at its
#: limit while nothing is happening has nothing left for the hour something is.
HOMELAB_IDLE_MEMORY_MIB: Final[int] = 2_048

#: How long a soak has to run before its verdict means anything. Memory growth
#: that matters shows up over hours, and a point measurement taken a minute
#: after start is a measurement of the import graph.
HOMELAB_SOAK_HOURS: Final[float] = 24.0

#: Where the credential proxy runs in each profile. ``in_process`` is the one
#: that makes the dev profile two containers instead of three; it is still the
#: same proxy and the same injection rules, reached over loopback.
PROXY_DEPLOYMENT_IN_PROCESS: Final = "in_process"
PROXY_DEPLOYMENT_CONTAINER: Final = "container"
PROXY_DEPLOYMENT_SERVICE: Final = "service"

#: Who a person is, per profile. ``dev`` and ``standard`` can run on the local
#: admin token alone; ``enterprise`` is where an identity provider is the
#: expectation rather than an option.
IDENTITY_LOCAL_ADMIN: Final = "local_admin"
IDENTITY_SSO: Final = "sso"

#: Where scheduled work is claimed. One process owns the schedule in the two
#: single-node profiles; across replicas it is claimed by lease.
SCHEDULER_IN_PROCESS: Final = "in_process"
SCHEDULER_LEADER_CLAIMED: Final = "leader_claimed"

# --- Concurrency defaults, per profile ---------------------------------------

#: A laptop runs one investigation at a time on purpose. The second concurrent
#: run on a development machine competes with the editor, the container runtime,
#: and the test suite, and the resulting latency reads as a platform problem.
DEV_GLOBAL_CONCURRENCY: Final[int] = 2
DEV_TEAM_CONCURRENCY: Final[int] = 1

#: One host serving a team. Matches the scheduler's own defaults, because the
#: standard profile is the deployment those numbers were chosen for.
STANDARD_GLOBAL_CONCURRENCY: Final[int] = 8
STANDARD_TEAM_CONCURRENCY: Final[int] = 2

#: Across replicas. Four times the standard ceiling rather than an unbounded
#: one: the bound exists so a correlated alert storm cannot consume the whole
#: cluster's database connections, and removing it in the largest profile would
#: remove it exactly where it matters most.
ENTERPRISE_GLOBAL_CONCURRENCY: Final[int] = 32
ENTERPRISE_TEAM_CONCURRENCY: Final[int] = 8

#: One host, one person, and a CPU budget of two cores shared with a database.
#: Two concurrent investigations is what fits; the third would make all three
#: slow rather than making any of them finish, and on a homelab there is nobody
#: waiting on the second one anyway.
HOMELAB_GLOBAL_CONCURRENCY: Final[int] = 2
HOMELAB_TEAM_CONCURRENCY: Final[int] = 1

# --- First run ---------------------------------------------------------------

#: The admin token printed once at first start. Supplied by the operator when
#: they want a stable one; generated and printed when they do not, because an
#: unreachable console is a worse first five minutes than a rotated token.
NINJASRE_ADMIN_TOKEN_ENV: Final = "NINJASRE_ADMIN_TOKEN"

#: A golden configuration template applied during initial setup (FR-026). Names
#: a template from the shipped library, or a path to an operator's own.
NINJASRE_SETUP_TEMPLATE_ENV: Final = "NINJASRE_SETUP_TEMPLATE"

#: ``module:factory`` naming what drives a route-triggered investigation.
#: Composing a runtime means choosing a provider, a capability catalogue, and a
#: credential proxy — a deployment decision, and the same shape the chaos and
#: end-to-end suites already take for it.
NINJASRE_INVESTIGATOR_ENV: Final = "NINJASRE_INVESTIGATOR"

#: Fifteen minutes, from a clean machine to a finished investigation (SC-001).
FIRST_INVESTIGATION_BUDGET_SECONDS: Final[int] = 15 * 60

# --- Egress and air-gapped operation -----------------------------------------

#: Refuses to start if any configuration implies an outbound connection
#: (FR-023). Not a firewall — the firewall is the operator's — but the check
#: that catches the deployment which *believes* it is air-gapped and is not.
NINJASRE_AIR_GAPPED_ENV: Final = "NINJASRE_AIR_GAPPED"

#: Hosts the operator has consciously permitted, comma-separated. The
#: destinations the configuration already implies — the database, the provider
#: endpoint, the proxy — are permitted by being configured; this is for the ones
#: nothing else names, such as a vendor an integration reaches.
NINJASRE_EGRESS_ALLOWLIST_ENV: Final = "NINJASRE_EGRESS_ALLOWLIST"

#: A PEM bundle to trust in addition to the system store, for a corporate proxy
#: that terminates TLS (FR-025). A path rather than the certificate itself: the
#: bundle is usually already on the host, and a certificate pasted into an
#: environment variable is one nobody can update.
NINJASRE_CA_BUNDLE_ENV: Final = "NINJASRE_CA_BUNDLE"

#: Where traces and metrics are exported, when they are. Unset means nothing
#: leaves the host, which is the default (Article X).
NINJASRE_OTEL_ENDPOINT_ENV: Final = "NINJASRE_OTEL_ENDPOINT"

#: Separator for the allow-list and every other list-shaped setting here. A
#: comma, because that is what an operator types and what a shell will not eat.
SETTING_LIST_SEPARATOR: Final = ","

#: Hosts that are never an outbound connection in the sense Article X means: a
#: deployment talking to its own database over loopback has not phoned home.
LOOPBACK_HOSTS: Final[tuple[str, ...]] = ("localhost", "127.0.0.1", "::1", "0.0.0.0")

# --- Backup and restore ------------------------------------------------------

#: One artefact, two members. The manifest is read first on restore, which is
#: what makes a version check possible before anything is written (FR-017).
BACKUP_MANIFEST_FILENAME: Final = "manifest.json"
BACKUP_DUMP_FILENAME: Final = "database.sql"

#: The manifest's own schema version, so a future change is detectable by
#: reading a backup rather than by remembering when it was taken.
BACKUP_MANIFEST_VERSION: Final[int] = 1

#: What a restore does when the backup and this release disagree.
RESTORE_ACTION_RESTORE: Final = "restore"
RESTORE_ACTION_MIGRATE_FORWARD: Final = "migrate_forward"
RESTORE_ACTION_REFUSE: Final = "refuse"

# --- Keys --------------------------------------------------------------------

#: Credentials re-encrypted per transaction during an online rotation. Small
#: enough that no single transaction holds rows long enough to block a running
#: investigation's write, large enough that a thousand credentials is twenty
#: transactions rather than a thousand.
KEY_ROTATION_BATCH_SIZE: Final[int] = 50

# --- Migrations at startup ---------------------------------------------------

#: How long a replica waits for the migration advisory lock before giving up.
#: Longer than the slowest migration this schema has, so the loser of a race
#: waits for the winner rather than failing; bounded so a lock held by a process
#: that died with its session open is a startup failure rather than a hang.
MIGRATION_LOCK_WAIT_SECONDS: Final[float] = 300.0

__all__ = [
    "BACKUP_DUMP_FILENAME",
    "BACKUP_MANIFEST_FILENAME",
    "BACKUP_MANIFEST_VERSION",
    "DEFAULT_DEPLOYMENT_PROFILE",
    "DEPLOYMENT_PROFILES",
    "DEPLOYMENT_PROFILE_DEV",
    "DEPLOYMENT_PROFILE_ENTERPRISE",
    "DEPLOYMENT_PROFILE_HOMELAB",
    "DEPLOYMENT_PROFILE_STANDARD",
    "DEV_GLOBAL_CONCURRENCY",
    "DEV_PROFILE_CONTAINER_COUNT",
    "DEV_PROFILE_SERVICES",
    "DEV_TEAM_CONCURRENCY",
    "ENTERPRISE_GLOBAL_CONCURRENCY",
    "ENTERPRISE_TEAM_CONCURRENCY",
    "FIRST_INVESTIGATION_BUDGET_SECONDS",
    "HOMELAB_CPU_LIMITS",
    "HOMELAB_GLOBAL_CONCURRENCY",
    "HOMELAB_IDLE_MEMORY_MIB",
    "HOMELAB_MEMORY_LIMITS_MIB",
    "HOMELAB_PROFILE_CONTAINER_COUNT",
    "HOMELAB_PROFILE_SERVICES",
    "HOMELAB_SOAK_HOURS",
    "HOMELAB_TEAM_CONCURRENCY",
    "HOMELAB_TOTAL_CPUS",
    "HOMELAB_TOTAL_MEMORY_MIB",
    "IDENTITY_LOCAL_ADMIN",
    "IDENTITY_SSO",
    "KEY_ROTATION_BATCH_SIZE",
    "LOOPBACK_HOSTS",
    "MIGRATION_LOCK_WAIT_SECONDS",
    "NINJASRE_ADMIN_TOKEN_ENV",
    "NINJASRE_AIR_GAPPED_ENV",
    "NINJASRE_CA_BUNDLE_ENV",
    "NINJASRE_DEPLOYMENT_PROFILE_ENV",
    "NINJASRE_EGRESS_ALLOWLIST_ENV",
    "NINJASRE_INVESTIGATOR_ENV",
    "NINJASRE_OTEL_ENDPOINT_ENV",
    "NINJASRE_SETUP_TEMPLATE_ENV",
    "PROXY_DEPLOYMENT_CONTAINER",
    "PROXY_DEPLOYMENT_IN_PROCESS",
    "PROXY_DEPLOYMENT_SERVICE",
    "RESTORE_ACTION_MIGRATE_FORWARD",
    "RESTORE_ACTION_REFUSE",
    "RESTORE_ACTION_RESTORE",
    "SCHEDULER_IN_PROCESS",
    "SCHEDULER_LEADER_CLAIMED",
    "SERVICE_APP",
    "SERVICE_CONSOLE",
    "SERVICE_POSTGRES",
    "SERVICE_PROXY",
    "SETTING_LIST_SEPARATOR",
    "STANDARD_GLOBAL_CONCURRENCY",
    "STANDARD_PROFILE_CONTAINER_COUNT",
    "STANDARD_PROFILE_SERVICES",
    "STANDARD_TEAM_CONCURRENCY",
]
