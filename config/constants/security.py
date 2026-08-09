"""Vault, credential proxy, guardrail, and masking configuration names.

Every name here is read by ``platform/`` on the trusted side of the boundary —
the vault bootstrap, the proxy, the guardrail engine. **None of them is read
from the agent's process.** The agent holds a
tenant-and-team-scoped handle; the proxy resolves the real secret at the network
edge (Constitution Article IV, clauses 1 and 2).

Naming a variable here therefore says where an operator configures something.
It never says the agent can see it.
"""

from __future__ import annotations

from typing import Final

# --- Credential vault --------------------------------------------------------

NINJASRE_VAULT_MASTER_KEY_ENV: Final = "NINJASRE_VAULT_MASTER_KEY"
NINJASRE_VAULT_KEY_FILE_ENV: Final = "NINJASRE_VAULT_KEY_FILE"

#: Rotating the master key re-encrypts every stored credential, so the vault
#: records which key version encrypted each row.
VAULT_KEY_VERSION_COLUMN: Final = "key_version"

#: A credential handle is ``<integration>/<team>``; a stored version appends
#: ``@v<n>``. Rotation writes a new version rather than overwriting the old one,
#: so rolling back is a pointer move and not a restore from somebody's notes.
CREDENTIAL_HANDLE_SEPARATOR: Final = "/"
CREDENTIAL_VERSION_SEPARATOR: Final = "@v"

#: The team component of a handle that belongs to the organisation rather than
#: to one team. A literal is needed because the empty string would make
#: ``datadog/`` and ``datadog`` two spellings of the same thing.
CREDENTIAL_ORG_WIDE_TEAM: Final = "-"

#: The first version the vault writes. Versions count up and are never reused,
#: so an audit line naming version 4 means the same row forever.
VAULT_INITIAL_CREDENTIAL_VERSION: Final[int] = 1

#: The label the vault puts on the pointer row's metadata to name the live
#: version. Metadata, so health checks, the console, and the operator CLI can
#: read which version is active without any code path touching a value.
VAULT_ACTIVE_VERSION_LABEL_PREFIX: Final = "active-version="

# --- Credential proxy --------------------------------------------------------

#: Mandatory in every deployment profile, including local development
#: (ADR 0005). There is no "direct" mode to fall back to.
NINJASRE_CREDENTIAL_PROXY_URL_ENV: Final = "NINJASRE_CREDENTIAL_PROXY_URL"
NINJASRE_CREDENTIAL_PROXY_TOKEN_ENV: Final = "NINJASRE_CREDENTIAL_PROXY_TOKEN"

#: Header carrying the opaque credential handle from a tool call to the proxy.
#: The handle names a credential; it is not one.
CREDENTIAL_HANDLE_HEADER: Final = "X-NinjaSRE-Credential-Handle"
TENANT_CONTEXT_HEADER: Final = "X-NinjaSRE-Tenant"
TEAM_CONTEXT_HEADER: Final = "X-NinjaSRE-Team"

#: Names the capability whose call this is, so an audit line answers "which
#: tool used this credential" rather than only "something did".
CAPABILITY_CONTEXT_HEADER: Final = "X-NinjaSRE-Capability"

#: Names the integration whose injection rule applies. Separate from the handle
#: because the proxy resolves the rule before it resolves the credential — an
#: undeclared host is rejected without a vault read.
INTEGRATION_CONTEXT_HEADER: Final = "X-NinjaSRE-Integration"

#: Google wants the billing project in a header of its own rather than in the
#: token. It lives here rather than beside the signer because every
#: vendor-shaped literal that is not a secret belongs in this tier, and because
#: a ``GOOGLE_``-prefixed name written anywhere else fails ``check-constants``.
GOOGLE_QUOTA_PROJECT_HEADER: Final = "x-goog-user-project"

CREDENTIAL_PROXY_TIMEOUT_SECONDS: Final[float] = 30.0

#: The proxy's internal API. Two paths and nothing else: one that forwards a
#: request and one that reports health. There is deliberately no path that
#: returns a credential, because FR-010 says no configuration may enable one.
PROXY_FORWARD_PATH: Final = "/internal/forward"
PROXY_HEALTH_PATH: Final = "/internal/health"

#: Per-tenant ceiling, counted over a fixed window. A tenant that exceeds it is
#: refused rather than queued: a queue turns a runaway loop into latency
#: everybody else pays, and the refusal is what tells the operator it happened.
CREDENTIAL_PROXY_RATE_LIMIT_WINDOW_SECONDS: Final[float] = 60.0
CREDENTIAL_PROXY_MAX_REQUESTS_PER_TENANT: Final[int] = 600

#: How long before expiry a short-lived credential (OAuth, STS) is refreshed.
#: Wide enough that a request starting just inside the margin still finishes
#: with a valid token, narrow enough that refreshes stay rare.
CREDENTIAL_REFRESH_MARGIN_SECONDS: Final[float] = 120.0

#: Exactly one (FR-013). A second retry on an expiry failure is a retry against
#: a credential that has already been refreshed once, so the failure is
#: something other than expiry and repeating it only spends the vendor's rate
#: limit.
CREDENTIAL_EXPIRY_RETRY_ATTEMPTS: Final[int] = 1

#: The p50 overhead the proxy hop is allowed to add, measured in
#: ``tests/benchmarks``. A capability's own network call dominates this by two
#: orders of magnitude; the budget exists so a regression that changes that is
#: a test failure rather than a slow week.
CREDENTIAL_PROXY_OVERHEAD_BUDGET_SECONDS: Final[float] = 0.005

#: What a resolution is called in the audit trail (FR-019).
CREDENTIAL_RESOLUTION_AUDIT_ACTION: Final = "credential.resolve"
CREDENTIAL_RESOLUTION_AUDIT_RESOURCE_KIND: Final = "integration"

# --- Guardrails --------------------------------------------------------------

NINJASRE_GUARDRAIL_RULES_PATH_ENV: Final = "NINJASRE_GUARDRAIL_RULES_PATH"

GUARDRAIL_ACTION_REDACT: Final = "redact"
GUARDRAIL_ACTION_BLOCK: Final = "block"
GUARDRAIL_ACTION_AUDIT: Final = "audit"

GUARDRAIL_ACTIONS: Final[tuple[str, ...]] = (
    GUARDRAIL_ACTION_REDACT,
    GUARDRAIL_ACTION_BLOCK,
    GUARDRAIL_ACTION_AUDIT,
)

#: What replaces a redacted span. Fixed width so a redaction cannot be sized to
#: infer the value behind it.
REDACTION_PLACEHOLDER: Final = "[REDACTED]"

#: How many matches one scan reports before it stops looking. A payload that
#: produces more than this is not a payload with a few secrets in it; it is one
#: whose every line matches, and continuing to enumerate them spends the
#: incident's time to produce a list nobody reads.
MAX_SCAN_MATCHES: Final[int] = 1_000

#: The largest input one scan reads. Beyond this the tail is truncated and the
#: truncation is recorded, because a scan that silently stopped looking is
#: indistinguishable from a scan that found nothing.
MAX_SCAN_INPUT_BYTES: Final[int] = 4 * 1024 * 1024

#: How long an operator-supplied pattern may spend on the adversarial corpus
#: before it is rejected at load. Generous by three orders of magnitude against
#: what a linear pattern costs, so only genuine backtracking trips it.
PATTERN_VALIDATION_BUDGET_SECONDS: Final[float] = 0.25

#: How stale a hot-reloaded ruleset may be. Polling the file's modification time
#: costs one ``stat`` per scan, which is cheaper than a watcher thread and is
#: deterministic in a test — a watcher's delivery latency is not.
GUARDRAIL_RELOAD_INTERVAL_SECONDS: Final[float] = 1.0

#: What a guardrail action is called in the audit trail.
GUARDRAIL_AUDIT_ACTION: Final = "guardrail.match"
GUARDRAIL_AUDIT_RESOURCE_KIND: Final = "guardrail_rule"

# --- Identifier masking ------------------------------------------------------

NINJASRE_MASKING_ENABLED_ENV: Final = "NINJASRE_MASKING_ENABLED"
NINJASRE_MASKING_POLICY_ENV: Final = "NINJASRE_MASKING_POLICY"

#: Masking is reversible and applied around every external LLM call, then undone
#: only when rendering to an authorised human.
MASK_TOKEN_PREFIX: Final = "NSRE_MASK_"

#: Separates the kind from the ordinal inside a token: ``NSRE_MASK_POD_1``. An
#: underscore rather than a hyphen because a token has to survive a round trip
#: through a model that may be summarising code, and a hyphen is what a model
#: line-wraps on.
MASK_TOKEN_SEPARATOR: Final = "_"

#: Disabling masking is an operator decision that has to be made explicitly.
MASKING_ENABLED_BY_DEFAULT: Final[bool] = True

#: The four policy levels, ordered by how much they hide.
#:
#: ``local_models_exempt`` is not a fifth amount of masking — it is
#: ``standard`` resolved per call against the provider, and ``off`` when the
#: provider runs on the operator's own host. It exists because a deployment
#: where nothing leaves the network has nothing to mask, and masking it anyway
#: costs investigation quality for no gain.
MASKING_POLICY_OFF: Final = "off"
MASKING_POLICY_STANDARD: Final = "standard"
MASKING_POLICY_STRICT: Final = "strict"
MASKING_POLICY_LOCAL_MODELS_EXEMPT: Final = "local_models_exempt"

MASKING_POLICY_LEVELS: Final[tuple[str, ...]] = (
    MASKING_POLICY_OFF,
    MASKING_POLICY_STANDARD,
    MASKING_POLICY_STRICT,
    MASKING_POLICY_LOCAL_MODELS_EXEMPT,
)

#: The measured sweet spot. ``strict`` adds service and deployment names, which
#: is where the evaluation suite starts showing a quality cost.
DEFAULT_MASKING_POLICY: Final = MASKING_POLICY_STANDARD

#: The wall-clock budget masking and guardrail scanning may each spend per
#: megabyte of evidence, asserted in ``tests/benchmarks``.
#:
#: Measured rather than chosen. The benchmark's corpus is built to be maximally
#: expensive — every line carries something each detector has to look at and
#: mostly reject — and the strictest policy costs a little under 0.4s per
#: megabyte on it. The budget is set at roughly 1.6 times that, which is loose
#: enough that a busy CI machine does not fail the build and tight enough that
#: the failure mode this exists to catch does: a pattern that has started
#: backtracking is slower by one to two orders of magnitude, not by half.
MASKING_BUDGET_SECONDS_PER_MEGABYTE: Final[float] = 0.60

# --- Sandbox profiles --------------------------------------------------------

#: Which isolation profile this deployment runs. Deployment-wide, never
#: per-capability: a matrix of per-tool profiles is a matrix of behaviours
#: nobody can reason about during an incident.
NINJASRE_SANDBOX_PROFILE_ENV: Final = "NINJASRE_SANDBOX_PROFILE"

#: Where the ``container`` and ``kubernetes`` profiles get the runtime image,
#: which namespace the pods land in, and how many idle instances the pool holds.
NINJASRE_SANDBOX_IMAGE_ENV: Final = "NINJASRE_SANDBOX_IMAGE"
NINJASRE_SANDBOX_NAMESPACE_ENV: Final = "NINJASRE_SANDBOX_NAMESPACE"
NINJASRE_SANDBOX_POOL_SIZE_ENV: Final = "NINJASRE_SANDBOX_POOL_SIZE"

#: Which container binary the ``container`` profile drives. Docker and Podman
#: take the same arguments for everything this profile asks for, so the choice
#: is a name rather than a second adapter.
NINJASRE_CONTAINER_RUNTIME_ENV: Final = "NINJASRE_CONTAINER_RUNTIME"

#: What the kubelet puts in a pod's environment to say where the API server is.
#: Not NinjaSRE's names — Kubernetes' — but they are environment-variable names,
#: and every one of those lives in this tier whoever chose it.
KUBERNETES_SERVICE_HOST_ENV: Final = "KUBERNETES_SERVICE_HOST"
KUBERNETES_SERVICE_PORT_ENV: Final = "KUBERNETES_SERVICE_PORT"

SANDBOX_PROFILE_PROCESS: Final = "process"
SANDBOX_PROFILE_CONTAINER: Final = "container"
SANDBOX_PROFILE_KUBERNETES: Final = "kubernetes"

SANDBOX_PROFILES: Final[tuple[str, ...]] = (
    SANDBOX_PROFILE_PROCESS,
    SANDBOX_PROFILE_CONTAINER,
    SANDBOX_PROFILE_KUBERNETES,
)

#: What an unconfigured deployment gets. ``process`` rather than a refusal to
#: start, because a contributor cloning the repository has neither a container
#: runtime nor a cluster and the alternative to the light profile is not a
#: heavier one — it is no sandbox at all. The startup report names the profile
#: and its guarantees so the weaker one is never mistaken for the strong one.
DEFAULT_SANDBOX_PROFILE: Final = SANDBOX_PROFILE_PROCESS

#: CPU seconds of *consumed* time, not wall clock. A capability that spends a
#: minute on the CPU is looping; one that spends a minute waiting on a slow
#: vendor is doing its job, and the two need different ceilings.
SANDBOX_CPU_SECONDS_LIMIT: Final[int] = 60

#: Address space, which is what the POSIX limit can actually bound. Sized for
#: sorting a few hundred megabytes of log lines and nothing more ambitious.
SANDBOX_MEMORY_BYTES_LIMIT: Final[int] = 512 * 1024 * 1024

#: The outer bound on one execution, including everything it waits for. Above
#: the per-tool timeout on purpose: this is the backstop for a capability that
#: found a way not to honour its own.
SANDBOX_WALL_CLOCK_SECONDS_LIMIT: Final[float] = 120.0

#: The writable scratch mount. A capability downloading a large log needs room;
#: a capability filling the host disk is a denial of service against every
#: other investigation on the node.
SANDBOX_SCRATCH_BYTES_LIMIT: Final[int] = 256 * 1024 * 1024

#: Capabilities fork — a shell pipeline is three processes — so the limit is
#: well above one and well below what a fork bomb needs.
SANDBOX_MAX_PROCESSES: Final[int] = 64

#: Where the writable scratch mount and the read-only content mount appear
#: inside the sandbox. Fixed paths, because a capability's working directory
#: has to be the same in all three profiles for its behaviour to be.
SANDBOX_SCRATCH_MOUNT_PATH: Final = "/scratch"
SANDBOX_CONTENT_MOUNT_PATH: Final = "/opt/ninjasre/content"

#: How long a sandbox lives without a refresh. Long enough that a normal
#: investigation never touches it, short enough that an agent killed mid-run
#: does not leave a pod billing overnight.
SANDBOX_TTL_SECONDS: Final[int] = 900

#: How often an active investigation pushes its sandbox's expiry out. A third
#: of the TTL, so two consecutive missed refreshes still leave margin.
SANDBOX_TTL_REFRESH_INTERVAL_SECONDS: Final[float] = 300.0

#: Idle instances the ``kubernetes`` profile keeps claimable. Two rather than
#: one because the second concurrent alert is common and the third is not.
SANDBOX_WARM_POOL_SIZE: Final[int] = 2

#: What provisioning is allowed to cost when the pool has capacity, asserted in
#: the contract suite. A claim is a label write; anything approaching a second
#: means the pool is exhausted and the request went to on-demand provisioning.
SANDBOX_PROVISIONING_LATENCY_BUDGET_SECONDS: Final[float] = 0.5

#: How long a reaper holds a sandbox before another replica may take it. Longer
#: than a delete round-trip and shorter than the sweep interval, so a reaper
#: that dies mid-sweep releases its claims by expiry rather than by cleanup.
SANDBOX_REAPER_LEASE_SECONDS: Final[float] = 30.0
SANDBOX_REAPER_INTERVAL_SECONDS: Final[float] = 60.0

#: How often the runner samples a running sandbox's resource usage.
#:
#: The operating system's own limits — rlimits, cgroups, a pod's ``resources``
#: block — are the enforcement and are not negotiable. This poll is what makes
#: the *reason* knowable: an rlimit kill arrives as a signal with no
#: explanation, and what a caller needs is which bound was crossed. Fast enough
#: that the
#: sample which crosses a bound is the one that reports it, slow enough that
#: watching costs nothing measurable against a capability's own work.
SANDBOX_MONITOR_INTERVAL_SECONDS: Final[float] = 0.05

#: How far above a declared bound the kernel's own ceiling is set.
#:
#: The two enforcement points are deliberately not at the same value. If the
#: kernel killed first, every limit would arrive as a bare signal and "which
#: bound was crossed" would be unanswerable — so NinjaSRE's sampler holds
#: the declared bound and the kernel holds a looser one behind it. A capability
#: that crosses the declared bound is stopped with a reason; one that crosses it
#: faster than the sampler polls is stopped without one, which is the correct
#: order of preference.
SANDBOX_KERNEL_BACKSTOP_FACTOR: Final[int] = 4

#: The floor under the memory backstop. CPython reserves far more *address
#: space* than it resident-sets, and ``RLIMIT_AS`` bounds the first — an
#: address-space ceiling sized from a modest memory bound would fail during
#: interpreter startup rather than during the capability's own allocation.
SANDBOX_MEMORY_BACKSTOP_FLOOR_BYTES: Final[int] = 512 * 1024 * 1024

#: How much CPU the kernel's ``SIGXCPU`` sits above the declared budget. Seconds
#: rather than a factor, because a one-second budget and a sixty-second budget
#: need the same absolute margin for the sampler to win the race.
SANDBOX_CPU_BACKSTOP_MARGIN_SECONDS: Final[int] = 5

#: How long a terminated sandbox process is given to exit on a polite signal
#: before it is killed outright. Long enough for a Python interpreter to run its
#: exception handlers and flush the partial output that is usually the whole
#: diagnosis; short enough that cancellation still feels immediate.
SANDBOX_TERMINATION_GRACE_SECONDS: Final[float] = 2.0

#: The proxy variables the sandbox environment carries. Named here because they
#: are environment-variable names, and every one of those lives in this tier —
#: none of them holds a credential, only the address of the thing that does.
SANDBOX_HTTP_PROXY_ENV: Final = "HTTP_PROXY"
SANDBOX_HTTPS_PROXY_ENV: Final = "HTTPS_PROXY"
SANDBOX_NO_PROXY_ENV: Final = "NO_PROXY"

#: The Envoy sidecar's listener and admin ports in the ``kubernetes`` profile.
#: The listener is where the pod's egress is redirected; the admin interface is
#: bound to loopback so the sandbox container cannot reconfigure the thing
#: enforcing its allow-list.
SANDBOX_ENVOY_LISTENER_PORT: Final[int] = 15001
SANDBOX_ENVOY_ADMIN_PORT: Final[int] = 15000

#: Container names inside a sandbox pod. Stable, because interruption and log
#: streaming both address a container by name.
SANDBOX_CONTAINER_NAME: Final = "sandbox"
SANDBOX_EGRESS_SIDECAR_NAME: Final = "egress"

#: Pod annotations and labels the pool, the claim, and the reaper read. The
#: cluster is the source of truth for which sandboxes exist, so these are the
#: schema of that record.
SANDBOX_EXPIRES_AT_ANNOTATION: Final = "ninjasre.io/expires-at"
SANDBOX_INVESTIGATION_LABEL: Final = "ninjasre.io/investigation"
SANDBOX_ORG_LABEL: Final = "ninjasre.io/org"
SANDBOX_TEAM_LABEL: Final = "ninjasre.io/team"
SANDBOX_STATE_LABEL: Final = "ninjasre.io/state"
SANDBOX_LEASE_HOLDER_ANNOTATION: Final = "ninjasre.io/lease-holder"
SANDBOX_LEASE_EXPIRES_AT_ANNOTATION: Final = "ninjasre.io/lease-expires-at"

#: What a sandbox lifecycle transition and a refused egress are called in the
#: audit trail.
SANDBOX_LIFECYCLE_AUDIT_ACTION: Final = "sandbox.lifecycle"
SANDBOX_EGRESS_AUDIT_ACTION: Final = "sandbox.egress"
SANDBOX_AUDIT_RESOURCE_KIND: Final = "sandbox"

# --- Human sessions ----------------------------------------------------------

#: Two limits, because they answer two different questions. The idle timeout
#: bounds an unattended laptop; the absolute lifetime bounds a session that is
#: being kept warm on purpose. Only having the first means a stolen session
#: lives as long as somebody keeps touching it.
SESSION_IDLE_TIMEOUT_SECONDS: Final[int] = 30 * 60
SESSION_ABSOLUTE_LIFETIME_SECONDS: Final[int] = 12 * 60 * 60

#: Entropy in a session identifier. 256 bits, so guessing one is not an attack
#: anybody attempts twice.
SESSION_ID_BYTES: Final[int] = 32

#: What the session cookie is called. Named here because a surface, the console,
#: and the API all have to agree on it, and a second spelling is a sign-out
#: nobody can reproduce.
SESSION_COOKIE_NAME: Final = "ninjasre_session"

# --- Machine tokens ----------------------------------------------------------

#: Every issued token starts with this, so a leaked string is recognisable as a
#: NinjaSRE credential by a secret scanner and by a human reading a paste.
API_TOKEN_PREFIX: Final = "nsre_"

#: Entropy in the secret half of a token.
API_TOKEN_SECRET_BYTES: Final[int] = 32

#: How many leading characters of the secret are kept in cleartext as the
#: token's public identifier. Enough to tell two of a team's tokens apart in a
#: list; far too few to shorten a search for the rest.
API_TOKEN_HINT_CHARS: Final[int] = 6

#: What a token gets when the caller names no expiry, and the ceiling on what
#: one may ask for. There is no "never expires": a token nobody remembers
#: issuing is the one still working after the person who made it left.
API_TOKEN_DEFAULT_LIFETIME_DAYS: Final[int] = 90
API_TOKEN_MAX_LIFETIME_DAYS: Final[int] = 365

#: How long a token may go unused before the policy revokes it, and how far
#: ahead of expiry its owner is warned.
TOKEN_INACTIVITY_REVOCATION_DAYS: Final[int] = 60
TOKEN_EXPIRY_WARNING_DAYS: Final[int] = 14

#: The tolerance applied to a token's expiry comparison. Clocks on two hosts
#: disagree, and a token rejected a second early during an incident is a page
#: nobody can act on. Applied to expiry only — never to revocation, which is
#: immediate by definition.
TOKEN_CLOCK_SKEW_SECONDS: Final[int] = 60

#: How long a resolution may be reused before it is looked up again. Short, and
#: paired with an explicit invalidation on revoke: the TTL is the backstop for a
#: replica that missed the broadcast, not the mechanism.
TOKEN_RESOLUTION_CACHE_TTL_SECONDS: Final[float] = 5.0

#: How many resolutions one process caches. A bound rather than a guess: an
#: unbounded cache keyed by token hash is a memory leak an attacker can drive.
MAX_CACHED_TOKEN_RESOLUTIONS: Final[int] = 1_000

#: How many tokens one bulk revocation may cover. High enough for "revoke
#: everything this team holds" during an incident, bounded because a single
#: statement that could revoke an entire deployment is not a control.
MAX_BULK_REVOCATIONS: Final[int] = 500

# --- Impersonation and break-glass -------------------------------------------

#: How long an admin may act in a team's context before the grant lapses
#: Long enough to reproduce a report, short enough that a forgotten session is
#: not a standing privilege.
IMPERSONATION_MAX_DURATION_SECONDS: Final[int] = 60 * 60

#: How long a break-glass session lasts. Deliberately shorter than
#: impersonation: this is the path that exists because the identity provider is
#: down, and it should expire before the outage is over.
BREAK_GLASS_MAX_DURATION_SECONDS: Final[int] = 15 * 60

#: The reason an operator gives when opening a break-glass session must be at
#: least this long. A one-character justification is not one, and this is the
#: cheapest way to make the audit row worth reading afterwards.
BREAK_GLASS_MIN_REASON_CHARS: Final[int] = 16

#: The local admin's login name. Fixed, because a break-glass account whose name
#: an operator has to look up during an outage is one they cannot use.
BREAK_GLASS_PRINCIPAL_ID: Final = "break-glass"

# --- The local account a deployment signs in with ------------------------------
#
# A deployment that has no identity provider still has to let somebody in, and
# "paste an API token" is not a sign-in a person can perform on the first run —
# there is nowhere to have got a token from yet. So a local account exists, with
# a name and a passphrase, verified in this process against the deployment's own
# configuration by the same memory-hard KDF break-glass uses.
#
# It is the same shape as break-glass and a different thing: break-glass is the
# emergency path, short and loudly audited, and this is the ordinary one.

#: The local account's login name, and what the demo profile ships with.
LOCAL_ACCOUNT_USERNAME: Final = "admin"

#: The passphrase the demo profile ships with. It exists so a first run is a
#: sign-in rather than a scavenger hunt, and a deployment that is not the demo
#: refuses to start while it is still in place — see
#: ``platform/identity/local_accounts.py``, which is where that refusal lives.
LOCAL_ACCOUNT_DEFAULT_PASSWORD: Final = "ninjasre"

#: The principal a local sign-in acts as.
LOCAL_ACCOUNT_PRINCIPAL_ID: Final = "local-admin"

#: Where a deployment configures the account: the login name, and the stored
#: form of the passphrase as ``hash_secret`` returns it.
LOCAL_ACCOUNT_USERNAME_ENV: Final = "NINJASRE_LOCAL_ACCOUNT_USERNAME"
LOCAL_ACCOUNT_PASSWORD_HASH_ENV: Final = "NINJASRE_LOCAL_ACCOUNT_PASSWORD_HASH"

#: Set by the demo and local profiles, and by nothing else. It is what makes the
#: shipped passphrase acceptable, so an operator cannot reach production with it
#: by forgetting to change something — they would have had to set this as well.
LOCAL_ACCOUNT_DEMO_ENV: Final = "NINJASRE_LOCAL_ACCOUNT_DEMO"

#: How long a session opened with the local account lasts.
LOCAL_ACCOUNT_SESSION_SECONDS: Final[int] = 12 * 60 * 60

#: The audit action a local sign-in records.
LOCAL_ACCOUNT_AUDIT_ACTION: Final = "local_account.sign_in"

# --- Single sign-on ----------------------------------------------------------

#: PKCE, always. ``plain`` is in the specification and is not offered here: an
#: operator who could choose it would eventually choose it by accident.
OIDC_CODE_CHALLENGE_METHOD: Final = "S256"

#: Entropy in the state parameter and the PKCE verifier.
OIDC_STATE_BYTES: Final[int] = 32
OIDC_CODE_VERIFIER_BYTES: Final[int] = 64

#: How long an in-flight authorisation request stays valid. A redirect that
#: takes longer than this is one the user abandoned.
OIDC_AUTHORISATION_TTL_SECONDS: Final[int] = 10 * 60

#: What NinjaSRE asks the provider for. ``groups`` is requested and never
#: required: a provider that returns no group claim maps the user to the default
#: team rather than having the sign-in refused.
OIDC_DEFAULT_SCOPES: Final[tuple[str, ...]] = ("openid", "profile", "email", "groups")

#: Which claim carries which fact. Overridable per provider, because "groups"
#: is spelled four ways across the providers operators actually run.
OIDC_SUBJECT_CLAIM: Final = "sub"
OIDC_EMAIL_CLAIM: Final = "email"
OIDC_NAME_CLAIM: Final = "name"
OIDC_GROUPS_CLAIM: Final = "groups"

#: How much clock disagreement an identity token's ``exp`` and ``iat`` are
#: allowed. Same reasoning as the token skew above, same magnitude.
OIDC_CLOCK_SKEW_SECONDS: Final[int] = 60

# --- Identity audit ----------------------------------------------------------

#: What each class of privileged action is called in the audit trail.
#: One vocabulary, in one place, because an audit query is written against these
#: strings and a second spelling of "the token was revoked" is a query that
#: silently returns half the answer.
AUTH_AUDIT_ACTION_SIGN_IN: Final = "auth.sign_in"
AUTH_AUDIT_ACTION_SIGN_OUT: Final = "auth.sign_out"
AUTH_AUDIT_ACTION_DENIED: Final = "auth.denied"
TOKEN_AUDIT_ACTION_ISSUE: Final = "token.issue"
TOKEN_AUDIT_ACTION_REVOKE: Final = "token.revoke"
TOKEN_AUDIT_ACTION_REJECT: Final = "token.reject"
TOKEN_AUDIT_ACTION_EXPIRY_WARNING: Final = "token.expiry_warning"
PERMISSION_AUDIT_ACTION_GRANT: Final = "permission.grant"
PERMISSION_AUDIT_ACTION_REVOKE: Final = "permission.revoke"
PERMISSION_AUDIT_ACTION_DENIED: Final = "permission.denied"
IMPERSONATION_AUDIT_ACTION_START: Final = "impersonation.start"
IMPERSONATION_AUDIT_ACTION_END: Final = "impersonation.end"
BREAK_GLASS_AUDIT_ACTION: Final = "break_glass.open"
SSO_AUDIT_ACTION_TEST: Final = "sso.test"
SSO_AUDIT_ACTION_ACTIVATE: Final = "sso.activate"
SSO_AUDIT_ACTION_GROUP_FALLBACK: Final = "sso.group_fallback"

#: What identity actions name as the thing they acted on.
IDENTITY_AUDIT_RESOURCE_KIND_PRINCIPAL: Final = "principal"
IDENTITY_AUDIT_RESOURCE_KIND_TOKEN: Final = "api_token"
IDENTITY_AUDIT_RESOURCE_KIND_SESSION: Final = "session"
IDENTITY_AUDIT_RESOURCE_KIND_ROUTE: Final = "route"
IDENTITY_AUDIT_RESOURCE_KIND_SSO: Final = "sso_config"

#: The keys an impersonated action puts in its audit detail, so a reviewer's
#: query for "everything done under impersonation" is one filter rather than a
#: join somebody has to remember to write.
AUDIT_DETAIL_REAL_PRINCIPAL: Final = "real_principal_id"
AUDIT_DETAIL_IMPERSONATED_PRINCIPAL: Final = "impersonated_principal_id"
AUDIT_DETAIL_IMPERSONATED_NODE: Final = "impersonated_node_id"
AUDIT_DETAIL_BREAK_GLASS: Final = "break_glass"
AUDIT_DETAIL_SOURCE_ADDRESS: Final = "source_address"

#: Where an audit event goes when the database will not take it. A
#: file, because the fallback has to work in exactly the situation where the
#: datastore does not, and because an operator can ship a file to their SIEM
#: with tooling they already have.
NINJASRE_AUDIT_FALLBACK_PATH_ENV: Final = "NINJASRE_AUDIT_FALLBACK_PATH"
AUDIT_FALLBACK_FILENAME: Final = "audit-fallback.jsonl"

#: What the export writes. Newline-delimited JSON: every SIEM ingests it, it
#: streams without holding the result set in memory, and a truncated file is
#: still parseable up to the truncation.
AUDIT_EXPORT_CONTENT_TYPE: Final = "application/x-ndjson"

#: How many events one export page reads from storage at a time. The export is
#: expected to cover months; reading it in one query is how an export of a busy
#: deployment becomes an outage of its own.
AUDIT_EXPORT_PAGE_SIZE: Final[int] = 100

#: The database object that refuses an update or a delete on the audit table
#: Named here because the migration creates it and the security suite asserts it
#: exists, and those two must not drift.
AUDIT_IMMUTABILITY_TRIGGER_NAME: Final = "audit_events_append_only"
AUDIT_IMMUTABILITY_FUNCTION_NAME: Final = "reject_audit_mutation"

# --- Side-effect classification ----------------------------------------------

#: ``SIDE_EFFECT_LEVELS`` is ordered least to most dangerous, and the order is
#: load-bearing: it is what "above ``read_sensitive``" means, and everything
#: above it needs per-action approval and a stored rollback plan.
#:
#: The scale separates two distinctions that a single "write" level hides. A
#: read that returns customer data is not the same risk as a read that returns
#: a pod count, and restarting a deployment is not the same risk as deleting a
#: snapshot — the first is undone by waiting, the second is not undone at all.
SIDE_EFFECT_READ: Final = "read"
SIDE_EFFECT_READ_SENSITIVE: Final = "read_sensitive"
SIDE_EFFECT_WRITE_REVERSIBLE: Final = "write_reversible"
SIDE_EFFECT_WRITE_IRREVERSIBLE: Final = "write_irreversible"
SIDE_EFFECT_DESTRUCTIVE: Final = "destructive"

SIDE_EFFECT_LEVELS: Final[tuple[str, ...]] = (
    SIDE_EFFECT_READ,
    SIDE_EFFECT_READ_SENSITIVE,
    SIDE_EFFECT_WRITE_REVERSIBLE,
    SIDE_EFFECT_WRITE_IRREVERSIBLE,
    SIDE_EFFECT_DESTRUCTIVE,
)

#: What a capability is assumed to do when it arrives carrying no declaration
#: at all — a bridged protocol tool, for instance, described by a remote server
#: that owes us nothing (Article III, clause 1). Absence is never permission.
#:
#: A first-party capability never reaches this. Omitting the level in the
#: repository fails the build instead, because a default that is *usually* right
#: is how an undeclared destructive tool eventually ships as a write.
DEFAULT_SIDE_EFFECT_LEVEL: Final = SIDE_EFFECT_WRITE_IRREVERSIBLE

#: An approval is per-action and per-session; it never generalises to a later
#: action (Article III, clause 4). This is how long one stays valid.
APPROVAL_EXPIRY_SECONDS: Final[int] = 300

# --- Change approval ---------------------------------------------------------

#: The five kinds of change that go through one approval mechanism. Ordered as
#: a reviewer meets them: the three an operator edits, the one an agent
#: proposes, and the one that touches production.
#:
#: One tuple rather than five queues. A configuration edit, a prompt change, a
#: capability toggle, an agent's knowledge proposal, and a production
#: remediation are the same shape — proposal, reviewer, decision, audit — and
#: five mechanisms would drift until one of them was weaker than the rest.
CHANGE_TYPE_CONFIGURATION: Final = "configuration"
CHANGE_TYPE_PROMPT: Final = "prompt"
CHANGE_TYPE_CAPABILITY: Final = "capability"
CHANGE_TYPE_KNOWLEDGE: Final = "knowledge"
CHANGE_TYPE_REMEDIATION: Final = "remediation"

CHANGE_TYPES: Final[tuple[str, ...]] = (
    CHANGE_TYPE_CONFIGURATION,
    CHANGE_TYPE_PROMPT,
    CHANGE_TYPE_CAPABILITY,
    CHANGE_TYPE_KNOWLEDGE,
    CHANGE_TYPE_REMEDIATION,
)

#: How long a queued change stays answerable, and the ceiling an operator may
#: configure. Far longer than the per-action approval above, because a prompt
#: change is not something anybody should be asked to approve mid-incident —
#: and bounded, because a change nobody answered in a month is one whose
#: reviewer has forgotten what the system looked like when it was proposed.
PENDING_CHANGE_EXPIRY_HOURS: Final[float] = 72.0
PENDING_CHANGE_MAX_EXPIRY_HOURS: Final[float] = 24.0 * 30

#: How many queued changes one listing returns. A review queue longer than this
#: is not a queue anybody is working through, and paging it is the caller's
#: decision rather than a limit they discover by losing rows.
MAX_PENDING_CHANGES_LISTED: Final[int] = 200

#: The point past which a diff is summarised rather than shown whole, and how
#: much of each section survives the summary.
#:
#: Summarised, never truncated. A truncated diff that looks complete is worse
#: than no diff at all: the reviewer approves what they were shown and the rest
#: applies unread. A summary says how much it left out and can be drilled into.
DIFF_SUMMARY_THRESHOLD_LINES: Final[int] = 200
DIFF_SUMMARY_SECTION_LINES: Final[int] = 20

#: The longest single value a diff renders inline. Above it the value is
#: reported by its size and its fingerprint, which is what a reviewer can
#: actually compare — a ten-kilobyte certificate rendered in full is a diff
#: nobody reads.
MAX_DIFF_VALUE_CHARS: Final[int] = 2_000

#: How many reviewers one queued change notifies. High enough for a division's
#: on-call rota, bounded because a change that pages two hundred people is how
#: an organisation learns to filter the notification.
MAX_REVIEWER_NOTIFICATIONS: Final[int] = 25

#: How many affected nodes a blast radius enumerates before it reports a count
#: instead. A reviewer reads a list of ten teams; they read "412 teams" the same
#: way whether the list is there or not.
MAX_BLAST_RADIUS_NODES_REPORTED: Final[int] = 100

#: What a policy says about self-approval when it says nothing. Forbidden,
#: because the multi-person deployment is where the control matters and the
#: single-operator deployment can turn it off deliberately.
ALLOW_SELF_APPROVAL_BY_DEFAULT: Final[bool] = False

#: What each stage of a change's life is called in the audit trail. The
#: vocabulary an audit query is written against, so a second spelling of "the
#: change was queued" is a query that silently returns half the answer.
APPROVAL_AUDIT_ACTION_QUEUE: Final = "approval.queue"
APPROVAL_AUDIT_ACTION_EXPIRE: Final = "approval.expire"
APPROVAL_AUDIT_ACTION_CONFLICT: Final = "approval.conflict"
SECURITY_POLICY_AUDIT_ACTION_CHANGE: Final = "security_policy.change"

#: What an approval action names as the thing it acted on.
APPROVAL_AUDIT_RESOURCE_KIND_CHANGE: Final = "pending_change"
APPROVAL_AUDIT_RESOURCE_KIND_POLICY: Final = "security_policy"

#: The keys an approval record puts in its audit detail. ``AUDIT_DETAIL_DIFF``
#: is the one that makes a past decision reconstructable: the record holds the
#: diff that was shown, not a pointer to state that has since moved on.
AUDIT_DETAIL_CHANGE_TYPE: Final = "change_type"
AUDIT_DETAIL_DIFF: Final = "diff"
AUDIT_DETAIL_TARGET: Final = "target"
AUDIT_DETAIL_TARGET_FINGERPRINT: Final = "target_fingerprint"

# --- Remediation and rollback ------------------------------------------------

#: The levels a deployment gates before anybody configures anything: everything
#: above ``read_sensitive``. Written out rather than derived by rank, because a
#: policy that gated "everything above X" would silently start gating a level
#: added later, and a control whose coverage changes when somebody edits an enum
#: is not one an operator agreed to.
DEFAULT_GATED_SIDE_EFFECT_LEVELS: Final[tuple[str, ...]] = (
    SIDE_EFFECT_WRITE_REVERSIBLE,
    SIDE_EFFECT_WRITE_IRREVERSIBLE,
    SIDE_EFFECT_DESTRUCTIVE,
)

#: How long a remediation approval stays answerable. Minutes rather than the
#: days a configuration change gets, because the two are answered on different
#: clocks: an approval that arrives forty minutes into an incident may apply to
#: a cluster that has already moved, and applying it would be a change nobody
#: reviewed against the system it lands on. Expiry is default-deny.
REMEDIATION_APPROVAL_EXPIRY_SECONDS: Final[int] = 15 * 60

#: How long after an execution its recorded plan may still be applied. Long
#: enough that the engineer who approved the change is still awake and still
#: holds the context; short enough that "roll it back" a day later goes through
#: a fresh approval against fresh state rather than through a stale handle.
REMEDIATION_ROLLBACK_WINDOW_SECONDS: Final[int] = 60 * 60

#: How deep the topology traversal at request time goes. Three hops is where the
#: answer stops changing an approver's decision: the first hop is who breaks,
#: the second is who notices, and past the third every estate is connected to
#: every other part of itself.
REMEDIATION_BLAST_RADIUS_DEPTH: Final[int] = 3

#: How many affected services a remediation approval request enumerates before
#: it reports a count instead.
MAX_REMEDIATION_BLAST_RADIUS_REPORTED: Final[int] = 25

#: How long a caller waits for another action's hold on the same target before
#: giving up. Waiting is correct — two concurrent writes to one workload is the
#: case serialisation exists for — and waiting forever is not, because an
#: execution that hung holding the lock would block every later one silently.
REMEDIATION_TARGET_LOCK_TIMEOUT_SECONDS: Final[float] = 30.0

#: What an allow-list entry permits when it names no rate of its own, counted
#: over a fixed window per team and action type. Three per hour is enough for a
#: bad afternoon and few enough that a loop is visible before it is expensive.
AUTONOMY_DEFAULT_RATE_LIMIT: Final[int] = 3
AUTONOMY_RATE_LIMIT_WINDOW_SECONDS: Final[float] = 60 * 60.0

#: The blast radius an allow-list entry tolerates when it names no ceiling.
#: Deliberately small: autonomy is for the action nobody would have paged a
#: human about, and an action reaching six downstream services is not that.
AUTONOMY_DEFAULT_MAX_BLAST_RADIUS: Final[int] = 5

#: The environment autonomy never covers unless an entry names it explicitly.
#: A default that included production would be a default nobody chose.
PRODUCTION_ENVIRONMENT: Final = "production"

#: What each stage of a remediation is called in the audit trail. Execution and
#: rollback are named in ``platform.identity.audit.recorder`` alongside the other
#: audited action classes; these are the three that are specific to this
#: feature's own decisions rather than to the action itself.
REMEDIATION_AUDIT_ACTION_WAIVER: Final = "remediation.waiver"
REMEDIATION_AUDIT_ACTION_AUTONOMOUS: Final = "remediation.autonomous"
REMEDIATION_AUDIT_ACTION_KILL_SWITCH: Final = "remediation.kill_switch"

#: What a remediation action names as the thing it acted on.
REMEDIATION_AUDIT_RESOURCE_KIND: Final = "remediation_action"

#: The keys a remediation payload carries through the approval store. The
#: reviewer's diff is rendered from ``steps`` and ``rollback``; the rest is what
#: makes the decision an informed one rather than a yes/no on a tool name.
REMEDIATION_PAYLOAD_STEPS: Final = "steps"
REMEDIATION_PAYLOAD_ROLLBACK: Final = "rollback"
REMEDIATION_PAYLOAD_BLAST_RADIUS: Final = "blast_radius"
REMEDIATION_PAYLOAD_EVIDENCE: Final = "evidence"
REMEDIATION_PAYLOAD_CAPABILITY: Final = "capability"
REMEDIATION_PAYLOAD_ARGUMENTS: Final = "arguments"
REMEDIATION_PAYLOAD_ENVIRONMENT: Final = "environment"
REMEDIATION_PAYLOAD_WAIVER: Final = "rollback_waiver"


__all__ = [
    "ALLOW_SELF_APPROVAL_BY_DEFAULT",
    "API_TOKEN_DEFAULT_LIFETIME_DAYS",
    "API_TOKEN_HINT_CHARS",
    "API_TOKEN_MAX_LIFETIME_DAYS",
    "API_TOKEN_PREFIX",
    "API_TOKEN_SECRET_BYTES",
    "APPROVAL_AUDIT_ACTION_CONFLICT",
    "APPROVAL_AUDIT_ACTION_EXPIRE",
    "APPROVAL_AUDIT_ACTION_QUEUE",
    "APPROVAL_AUDIT_RESOURCE_KIND_CHANGE",
    "APPROVAL_AUDIT_RESOURCE_KIND_POLICY",
    "APPROVAL_EXPIRY_SECONDS",
    "AUDIT_DETAIL_BREAK_GLASS",
    "AUDIT_DETAIL_CHANGE_TYPE",
    "AUDIT_DETAIL_DIFF",
    "AUDIT_DETAIL_IMPERSONATED_NODE",
    "AUDIT_DETAIL_IMPERSONATED_PRINCIPAL",
    "AUDIT_DETAIL_REAL_PRINCIPAL",
    "AUDIT_DETAIL_SOURCE_ADDRESS",
    "AUDIT_DETAIL_TARGET",
    "AUDIT_DETAIL_TARGET_FINGERPRINT",
    "AUDIT_EXPORT_CONTENT_TYPE",
    "AUDIT_EXPORT_PAGE_SIZE",
    "AUDIT_FALLBACK_FILENAME",
    "AUDIT_IMMUTABILITY_FUNCTION_NAME",
    "AUDIT_IMMUTABILITY_TRIGGER_NAME",
    "AUTH_AUDIT_ACTION_DENIED",
    "AUTH_AUDIT_ACTION_SIGN_IN",
    "AUTH_AUDIT_ACTION_SIGN_OUT",
    "AUTONOMY_DEFAULT_MAX_BLAST_RADIUS",
    "AUTONOMY_DEFAULT_RATE_LIMIT",
    "AUTONOMY_RATE_LIMIT_WINDOW_SECONDS",
    "BREAK_GLASS_AUDIT_ACTION",
    "BREAK_GLASS_MAX_DURATION_SECONDS",
    "BREAK_GLASS_MIN_REASON_CHARS",
    "BREAK_GLASS_PRINCIPAL_ID",
    "CAPABILITY_CONTEXT_HEADER",
    "CHANGE_TYPES",
    "CHANGE_TYPE_CAPABILITY",
    "CHANGE_TYPE_CONFIGURATION",
    "CHANGE_TYPE_KNOWLEDGE",
    "CHANGE_TYPE_PROMPT",
    "CHANGE_TYPE_REMEDIATION",
    "CREDENTIAL_EXPIRY_RETRY_ATTEMPTS",
    "CREDENTIAL_HANDLE_HEADER",
    "CREDENTIAL_HANDLE_SEPARATOR",
    "CREDENTIAL_ORG_WIDE_TEAM",
    "CREDENTIAL_PROXY_MAX_REQUESTS_PER_TENANT",
    "CREDENTIAL_PROXY_OVERHEAD_BUDGET_SECONDS",
    "CREDENTIAL_PROXY_RATE_LIMIT_WINDOW_SECONDS",
    "CREDENTIAL_PROXY_TIMEOUT_SECONDS",
    "CREDENTIAL_REFRESH_MARGIN_SECONDS",
    "CREDENTIAL_RESOLUTION_AUDIT_ACTION",
    "CREDENTIAL_RESOLUTION_AUDIT_RESOURCE_KIND",
    "CREDENTIAL_VERSION_SEPARATOR",
    "DEFAULT_GATED_SIDE_EFFECT_LEVELS",
    "DEFAULT_MASKING_POLICY",
    "DEFAULT_SANDBOX_PROFILE",
    "DEFAULT_SIDE_EFFECT_LEVEL",
    "DIFF_SUMMARY_SECTION_LINES",
    "DIFF_SUMMARY_THRESHOLD_LINES",
    "GOOGLE_QUOTA_PROJECT_HEADER",
    "GUARDRAIL_ACTIONS",
    "GUARDRAIL_ACTION_AUDIT",
    "GUARDRAIL_ACTION_BLOCK",
    "GUARDRAIL_ACTION_REDACT",
    "GUARDRAIL_AUDIT_ACTION",
    "GUARDRAIL_AUDIT_RESOURCE_KIND",
    "GUARDRAIL_RELOAD_INTERVAL_SECONDS",
    "IDENTITY_AUDIT_RESOURCE_KIND_PRINCIPAL",
    "IDENTITY_AUDIT_RESOURCE_KIND_ROUTE",
    "IDENTITY_AUDIT_RESOURCE_KIND_SESSION",
    "IDENTITY_AUDIT_RESOURCE_KIND_SSO",
    "IDENTITY_AUDIT_RESOURCE_KIND_TOKEN",
    "IMPERSONATION_AUDIT_ACTION_END",
    "IMPERSONATION_AUDIT_ACTION_START",
    "IMPERSONATION_MAX_DURATION_SECONDS",
    "INTEGRATION_CONTEXT_HEADER",
    "KUBERNETES_SERVICE_HOST_ENV",
    "KUBERNETES_SERVICE_PORT_ENV",
    "LOCAL_ACCOUNT_AUDIT_ACTION",
    "LOCAL_ACCOUNT_DEFAULT_PASSWORD",
    "LOCAL_ACCOUNT_DEMO_ENV",
    "LOCAL_ACCOUNT_PASSWORD_HASH_ENV",
    "LOCAL_ACCOUNT_PRINCIPAL_ID",
    "LOCAL_ACCOUNT_SESSION_SECONDS",
    "LOCAL_ACCOUNT_USERNAME",
    "LOCAL_ACCOUNT_USERNAME_ENV",
    "MASKING_BUDGET_SECONDS_PER_MEGABYTE",
    "MASKING_ENABLED_BY_DEFAULT",
    "MASKING_POLICY_LEVELS",
    "MASKING_POLICY_LOCAL_MODELS_EXEMPT",
    "MASKING_POLICY_OFF",
    "MASKING_POLICY_STANDARD",
    "MASKING_POLICY_STRICT",
    "MASK_TOKEN_PREFIX",
    "MASK_TOKEN_SEPARATOR",
    "MAX_BLAST_RADIUS_NODES_REPORTED",
    "MAX_BULK_REVOCATIONS",
    "MAX_CACHED_TOKEN_RESOLUTIONS",
    "MAX_DIFF_VALUE_CHARS",
    "MAX_PENDING_CHANGES_LISTED",
    "MAX_REMEDIATION_BLAST_RADIUS_REPORTED",
    "MAX_REVIEWER_NOTIFICATIONS",
    "MAX_SCAN_INPUT_BYTES",
    "MAX_SCAN_MATCHES",
    "NINJASRE_AUDIT_FALLBACK_PATH_ENV",
    "NINJASRE_CONTAINER_RUNTIME_ENV",
    "NINJASRE_CREDENTIAL_PROXY_TOKEN_ENV",
    "NINJASRE_CREDENTIAL_PROXY_URL_ENV",
    "NINJASRE_GUARDRAIL_RULES_PATH_ENV",
    "NINJASRE_MASKING_ENABLED_ENV",
    "NINJASRE_MASKING_POLICY_ENV",
    "NINJASRE_SANDBOX_IMAGE_ENV",
    "NINJASRE_SANDBOX_NAMESPACE_ENV",
    "NINJASRE_SANDBOX_POOL_SIZE_ENV",
    "NINJASRE_SANDBOX_PROFILE_ENV",
    "NINJASRE_VAULT_KEY_FILE_ENV",
    "NINJASRE_VAULT_MASTER_KEY_ENV",
    "OIDC_AUTHORISATION_TTL_SECONDS",
    "OIDC_CLOCK_SKEW_SECONDS",
    "OIDC_CODE_CHALLENGE_METHOD",
    "OIDC_CODE_VERIFIER_BYTES",
    "OIDC_DEFAULT_SCOPES",
    "OIDC_EMAIL_CLAIM",
    "OIDC_GROUPS_CLAIM",
    "OIDC_NAME_CLAIM",
    "OIDC_STATE_BYTES",
    "OIDC_SUBJECT_CLAIM",
    "PATTERN_VALIDATION_BUDGET_SECONDS",
    "PENDING_CHANGE_EXPIRY_HOURS",
    "PENDING_CHANGE_MAX_EXPIRY_HOURS",
    "PERMISSION_AUDIT_ACTION_DENIED",
    "PERMISSION_AUDIT_ACTION_GRANT",
    "PERMISSION_AUDIT_ACTION_REVOKE",
    "PRODUCTION_ENVIRONMENT",
    "PROXY_FORWARD_PATH",
    "PROXY_HEALTH_PATH",
    "REDACTION_PLACEHOLDER",
    "REMEDIATION_APPROVAL_EXPIRY_SECONDS",
    "REMEDIATION_AUDIT_ACTION_AUTONOMOUS",
    "REMEDIATION_AUDIT_ACTION_KILL_SWITCH",
    "REMEDIATION_AUDIT_ACTION_WAIVER",
    "REMEDIATION_AUDIT_RESOURCE_KIND",
    "REMEDIATION_BLAST_RADIUS_DEPTH",
    "REMEDIATION_PAYLOAD_ARGUMENTS",
    "REMEDIATION_PAYLOAD_BLAST_RADIUS",
    "REMEDIATION_PAYLOAD_CAPABILITY",
    "REMEDIATION_PAYLOAD_ENVIRONMENT",
    "REMEDIATION_PAYLOAD_EVIDENCE",
    "REMEDIATION_PAYLOAD_ROLLBACK",
    "REMEDIATION_PAYLOAD_STEPS",
    "REMEDIATION_PAYLOAD_WAIVER",
    "REMEDIATION_ROLLBACK_WINDOW_SECONDS",
    "REMEDIATION_TARGET_LOCK_TIMEOUT_SECONDS",
    "SANDBOX_AUDIT_RESOURCE_KIND",
    "SANDBOX_CONTAINER_NAME",
    "SANDBOX_CONTENT_MOUNT_PATH",
    "SANDBOX_CPU_BACKSTOP_MARGIN_SECONDS",
    "SANDBOX_CPU_SECONDS_LIMIT",
    "SANDBOX_EGRESS_AUDIT_ACTION",
    "SANDBOX_EGRESS_SIDECAR_NAME",
    "SANDBOX_ENVOY_ADMIN_PORT",
    "SANDBOX_ENVOY_LISTENER_PORT",
    "SANDBOX_EXPIRES_AT_ANNOTATION",
    "SANDBOX_HTTPS_PROXY_ENV",
    "SANDBOX_HTTP_PROXY_ENV",
    "SANDBOX_INVESTIGATION_LABEL",
    "SANDBOX_KERNEL_BACKSTOP_FACTOR",
    "SANDBOX_LEASE_EXPIRES_AT_ANNOTATION",
    "SANDBOX_LEASE_HOLDER_ANNOTATION",
    "SANDBOX_LIFECYCLE_AUDIT_ACTION",
    "SANDBOX_MAX_PROCESSES",
    "SANDBOX_MEMORY_BACKSTOP_FLOOR_BYTES",
    "SANDBOX_MEMORY_BYTES_LIMIT",
    "SANDBOX_MONITOR_INTERVAL_SECONDS",
    "SANDBOX_NO_PROXY_ENV",
    "SANDBOX_ORG_LABEL",
    "SANDBOX_PROFILES",
    "SANDBOX_PROFILE_CONTAINER",
    "SANDBOX_PROFILE_KUBERNETES",
    "SANDBOX_PROFILE_PROCESS",
    "SANDBOX_PROVISIONING_LATENCY_BUDGET_SECONDS",
    "SANDBOX_REAPER_INTERVAL_SECONDS",
    "SANDBOX_REAPER_LEASE_SECONDS",
    "SANDBOX_SCRATCH_BYTES_LIMIT",
    "SANDBOX_SCRATCH_MOUNT_PATH",
    "SANDBOX_STATE_LABEL",
    "SANDBOX_TEAM_LABEL",
    "SANDBOX_TERMINATION_GRACE_SECONDS",
    "SANDBOX_TTL_REFRESH_INTERVAL_SECONDS",
    "SANDBOX_TTL_SECONDS",
    "SANDBOX_WALL_CLOCK_SECONDS_LIMIT",
    "SANDBOX_WARM_POOL_SIZE",
    "SECURITY_POLICY_AUDIT_ACTION_CHANGE",
    "SESSION_ABSOLUTE_LIFETIME_SECONDS",
    "SESSION_COOKIE_NAME",
    "SESSION_IDLE_TIMEOUT_SECONDS",
    "SESSION_ID_BYTES",
    "SIDE_EFFECT_DESTRUCTIVE",
    "SIDE_EFFECT_LEVELS",
    "SIDE_EFFECT_READ",
    "SIDE_EFFECT_READ_SENSITIVE",
    "SIDE_EFFECT_WRITE_IRREVERSIBLE",
    "SIDE_EFFECT_WRITE_REVERSIBLE",
    "SSO_AUDIT_ACTION_ACTIVATE",
    "SSO_AUDIT_ACTION_GROUP_FALLBACK",
    "SSO_AUDIT_ACTION_TEST",
    "TEAM_CONTEXT_HEADER",
    "TENANT_CONTEXT_HEADER",
    "TOKEN_AUDIT_ACTION_EXPIRY_WARNING",
    "TOKEN_AUDIT_ACTION_ISSUE",
    "TOKEN_AUDIT_ACTION_REJECT",
    "TOKEN_AUDIT_ACTION_REVOKE",
    "TOKEN_CLOCK_SKEW_SECONDS",
    "TOKEN_EXPIRY_WARNING_DAYS",
    "TOKEN_INACTIVITY_REVOCATION_DAYS",
    "TOKEN_RESOLUTION_CACHE_TTL_SECONDS",
    "VAULT_ACTIVE_VERSION_LABEL_PREFIX",
    "VAULT_INITIAL_CREDENTIAL_VERSION",
    "VAULT_KEY_VERSION_COLUMN",
]
