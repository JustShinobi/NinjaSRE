"""Every setting an operator can set, with its default, whether it is required, and why.

FR-009 asks for a ``.env.example`` documenting every setting. Writing that file
by hand produces a file that is correct on the day it is written, so this is the
catalogue and the file is generated from it — ``tools/generate_env_example.py``
renders it, ``--check`` fails the build when the shipped file has drifted, and a
test asserts that every environment variable the constants tier declares is
either catalogued here or explicitly marked as not an operator setting.

That last check is the one that keeps this honest. A new feature that adds a
setting and forgets to document it fails the build naming the variable, which is
the only mechanism that survives the fifteenth feature.

Three fields carry the weight:

``required``
    True for the two things a deployment cannot start without — a database, and
    the key its stored credentials are sealed with — and false for everything
    else. The value of this list is that it is short, and it is short here or it
    is not true.

    A model provider is deliberately not on it. Connecting one is a first-run
    step with a console screen of its own, so a deployment without one starts
    and says so; refusing to boot would kill the process that renders the screen
    that fixes it.

``effect``
    What changes if you set it. Not what it is; an operator reading a settings
    file already knows ``NINJASRE_LOG_LEVEL`` is the log level.

``secret``
    Whether the value is a credential. The generated file writes a placeholder
    rather than a plausible-looking value for these, because a plausible-looking
    default is a value somebody ships.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass
from typing import Final

from config.constants.chaos import (
    NINJASRE_CHAOS_KUBECONFIG_ENV,
    NINJASRE_E2E_ARTIFACTS_ENV,
)
from config.constants.deployment import (
    DEFAULT_DEPLOYMENT_PROFILE,
    DEPLOYMENT_PROFILES,
    NINJASRE_ADMIN_TOKEN_ENV,
    NINJASRE_AIR_GAPPED_ENV,
    NINJASRE_CA_BUNDLE_ENV,
    NINJASRE_DEPLOYMENT_PROFILE_ENV,
    NINJASRE_EGRESS_ALLOWLIST_ENV,
    NINJASRE_INVESTIGATOR_ENV,
    NINJASRE_OTEL_ENDPOINT_ENV,
    NINJASRE_SETUP_TEMPLATE_ENV,
)
from config.constants.evaluation import (
    NINJASRE_BENCHMARK_OUTPUT_ENV,
    NINJASRE_EVALUATION_BASELINES_ENV,
    NINJASRE_SCENARIO_ARTIFACTS_ENV,
)
from config.constants.first_run import (
    DEFAULT_ORGANISATION_ID,
    DEFAULT_STATE_DIR,
    NINJASRE_BOOTSTRAP_CREDENTIAL_PATH_ENV,
    NINJASRE_DEMO_MODE_ENV,
    NINJASRE_ORGANISATION_ENV,
    NINJASRE_STATE_DIR_ENV,
)
from config.constants.fixtures import (
    NINJASRE_CAPTURE_ENDPOINT_ENV,
    NINJASRE_CAPTURE_NODES_ENV,
    NINJASRE_CAPTURE_RAW_DIR_ENV,
    NINJASRE_CAPTURE_SSH_USER_ENV,
    NINJASRE_CAPTURE_TOKEN_ENV,
    NINJASRE_FIXTURE_ROOT_ENV,
    NINJASRE_FIXTURE_SCENARIO_ENV,
    NINJASRE_IDENTIFIER_FILE_ENV,
    NINJASRE_PSEUDONYM_KEY_ENV,
)
from config.constants.investigation import (
    DEFAULT_RUNTIME,
    NINJASRE_RUNTIME_ENV,
)
from config.constants.knowledge import NINJASRE_KNOWLEDGE_ENV, NINJASRE_TOPOLOGY_ENV
from config.constants.llm import (
    ANTHROPIC_API_KEY_ENV,
    ANTHROPIC_BASE_URL_ENV,
    AWS_ACCESS_KEY_ID_ENV,
    AWS_BEDROCK_ENDPOINT_ENV,
    AWS_PROFILE_ENV,
    AWS_REGION_ENV,
    AWS_SECRET_ACCESS_KEY_ENV,
    AWS_SESSION_TOKEN_ENV,
    AZURE_OPENAI_API_KEY_ENV,
    AZURE_OPENAI_API_VERSION_ENV,
    AZURE_OPENAI_DEPLOYMENT_ENV,
    AZURE_OPENAI_ENDPOINT_ENV,
    DEFAULT_MODEL_ID,
    DEFAULT_PROVIDER,
    DEFAULT_TRANSPORT,
    GOOGLE_API_KEY_ENV,
    GOOGLE_APPLICATION_CREDENTIALS_ENV,
    GOOGLE_CLOUD_LOCATION_ENV,
    GOOGLE_CLOUD_PROJECT_ENV,
    NINJASRE_LLM_MODEL_ENV,
    NINJASRE_LLM_PROVIDER_ENV,
    NINJASRE_LLM_TRANSPORT_ENV,
    NVIDIA_API_KEY_ENV,
    NVIDIA_NIM_BASE_URL_ENV,
    OLLAMA_BASE_URL_ENV,
    OPENAI_API_KEY_ENV,
    OPENAI_BASE_URL_ENV,
    OPENROUTER_API_KEY_ENV,
    OPENROUTER_BASE_URL_ENV,
    SUPPORTED_PROVIDERS,
    SUPPORTED_TRANSPORTS,
    VLLM_BASE_URL_ENV,
)
from config.constants.memory import (
    NINJASRE_EMBEDDING_MODEL_ENV,
    NINJASRE_MEMORY_READ_ENV,
    NINJASRE_MEMORY_STRATEGY_ENV,
    NINJASRE_MEMORY_WRITE_ENV,
)
from config.constants.observability import (
    DEFAULT_LOG_FORMAT,
    DEFAULT_LOG_LEVEL,
    DEFAULT_TELEMETRY_SAMPLE_RATIO,
    DEFAULT_TELEMETRY_SERVICE_NAME,
    NINJASRE_LOG_FORMAT_ENV,
    NINJASRE_LOG_LEVEL_ENV,
    NINJASRE_LOG_MODULE_LEVELS_ENV,
    NINJASRE_TELEMETRY_SAMPLE_RATIO_ENV,
    NINJASRE_TELEMETRY_SERVICE_NAME_ENV,
)
from config.constants.paths import NINJASRE_HOME_DIR_ENV
from config.constants.persistence import (
    DEFAULT_DATABASE_SCHEMA,
    NINJASRE_DATABASE_ENCRYPTION_KEY_ENV,
    NINJASRE_DATABASE_SCHEMA_ENV,
    NINJASRE_DATABASE_URL_ENV,
    NINJASRE_TEST_DATABASE_URL_ENV,
)
from config.constants.security import (
    DEFAULT_MASKING_POLICY,
    LOCAL_ACCOUNT_DEMO_ENV,
    LOCAL_ACCOUNT_PASSWORD_HASH_ENV,
    LOCAL_ACCOUNT_USERNAME,
    LOCAL_ACCOUNT_USERNAME_ENV,
    NINJASRE_AUDIT_FALLBACK_PATH_ENV,
    NINJASRE_CONTAINER_RUNTIME_ENV,
    NINJASRE_CREDENTIAL_PROXY_TOKEN_ENV,
    NINJASRE_CREDENTIAL_PROXY_URL_ENV,
    NINJASRE_GUARDRAIL_RULES_PATH_ENV,
    NINJASRE_MASKING_ENABLED_ENV,
    NINJASRE_MASKING_POLICY_ENV,
    NINJASRE_SANDBOX_IMAGE_ENV,
    NINJASRE_SANDBOX_NAMESPACE_ENV,
    NINJASRE_SANDBOX_POOL_SIZE_ENV,
    NINJASRE_SANDBOX_PROFILE_ENV,
    NINJASRE_VAULT_KEY_FILE_ENV,
    NINJASRE_VAULT_MASTER_KEY_ENV,
    SANDBOX_WARM_POOL_SIZE,
)
from config.constants.surfaces import (
    DEFAULT_API_HOST,
    DEFAULT_API_PORT,
    DEFAULT_CONSOLE_PORT,
    DEFAULT_CREDENTIAL_PROXY_PORT,
    NINJASRE_API_HOST_ENV,
    NINJASRE_API_PORT_ENV,
    NINJASRE_CONSOLE_PORT_ENV,
    NINJASRE_ENDPOINT_ENV,
    NINJASRE_NO_COLOR_ENV,
    NINJASRE_OUTPUT_FORMAT_ENV,
    NINJASRE_PROXY_PORT_ENV,
)
from platform.startup.keys import KEY_GENERATOR_HINT

#: What the generated file writes where a credential goes. Long enough to be
#: obviously a placeholder and not a value somebody leaves in place.
SECRET_PLACEHOLDER: Final = "<set this>"

#: Where a comment line wraps. Two under eighty, so the ``# `` prefix still
#: fits a terminal that has not been resized.
ENV_EXAMPLE_COMMENT_WIDTH: Final[int] = 76


@dataclass(frozen=True, slots=True)
class Setting:
    """One environment variable an operator may set."""

    name: str
    effect: str
    default: str = ""
    required: bool = False
    secret: bool = False
    section: str = ""

    @property
    def requirement(self) -> str:
        """Return the word the generated file uses for this setting's necessity."""
        return "required" if self.required else "optional"

    def to_record(self) -> dict[str, object]:
        """Return the JSON-serialisable form the console's setup view reads."""
        return {
            "name": self.name,
            "effect": self.effect,
            "default": self.default,
            "required": self.required,
            "secret": self.secret,
            "section": self.section,
        }

    def render(self) -> str:
        """Return this setting's block in ``.env.example``: comment, then the line.

        Wrapped at the width a terminal shows without folding. An operator reads
        this file in an editor beside a container log, and a paragraph on one
        line is one they scroll past.
        """
        shown = self.default if self.default else ("" if not self.secret else SECRET_PLACEHOLDER)
        default = f"default: {self.default}" if self.default else "no default"
        body = textwrap.wrap(self.effect, width=ENV_EXAMPLE_COMMENT_WIDTH)
        head = [f"# {line}" for line in body]
        meta = f"# {self.requirement}, {default}"
        line = f"{self.name}={shown}" if self.required else f"# {self.name}={shown}"
        return "\n".join([*head, meta, line])


SECTION_PROFILE = "Deployment profile"
SECTION_DATABASE = "Database"
SECTION_PROVIDER = "Model provider"
SECTION_NETWORK = "Ports and addresses"
SECTION_SECURITY = "Isolation, masking, and the credential proxy"
SECTION_MEMORY = "Memory, knowledge, and the runtime"
SECTION_OPERATIONS = "Logging, telemetry, and air-gapped operation"
SECTION_CLIENT = "The ninjasre command"


SETTINGS: Final[tuple[Setting, ...]] = (
    # -- profile ---------------------------------------------------------------
    Setting(
        name=NINJASRE_DEPLOYMENT_PROFILE_ENV,
        effect=(
            "Which deployment shape this is. Decides the sandbox, where the "
            "credential proxy runs, and the concurrency ceiling — all three "
            f"together. One of: {', '.join(DEPLOYMENT_PROFILES)}."
        ),
        default=DEFAULT_DEPLOYMENT_PROFILE,
        section=SECTION_PROFILE,
    ),
    Setting(
        name=NINJASRE_ADMIN_TOKEN_ENV,
        effect=(
            "The first administrator's token. Generated and printed once at first "
            "start when unset, which is the fastest path to a reachable console."
        ),
        secret=True,
        section=SECTION_PROFILE,
    ),
    Setting(
        name=NINJASRE_ORGANISATION_ENV,
        effect=(
            "The organisation bring-up creates on a store that holds none. Named "
            "rather than derived from the hostname: an identifier that changes "
            "when the machine is renamed breaks every token issued before it."
        ),
        default=DEFAULT_ORGANISATION_ID,
        section=SECTION_PROFILE,
    ),
    Setting(
        name=NINJASRE_STATE_DIR_ENV,
        effect=(
            "Where state that outlives one process but does not belong in the "
            "database is kept: the bootstrap credential, the last bring-up "
            "failure, a support bundle. Must survive a container restart, or an "
            "operator who closed the terminal loses their way in."
        ),
        default=DEFAULT_STATE_DIR,
        section=SECTION_PROFILE,
    ),
    Setting(
        name=NINJASRE_BOOTSTRAP_CREDENTIAL_PATH_ENV,
        effect=(
            "Where the bootstrap credential is written, when it should not go "
            "under the state directory. The file is owner-readable only and is "
            "removed the moment the credential is exchanged for a durable one."
        ),
        secret=True,
        section=SECTION_PROFILE,
    ),
    Setting(
        name=NINJASRE_DEMO_MODE_ENV,
        effect=(
            "Serve the demonstration dataset instead of a real deployment. Every "
            "provider response comes from a fixture and a real network call "
            "raises, so nothing external is reached and nothing is billed."
        ),
        default="false",
        section=SECTION_PROFILE,
    ),
    Setting(
        name=NINJASRE_SETUP_TEMPLATE_ENV,
        effect=(
            "A golden configuration template applied during initial setup: a "
            "shipped template's name, or a path to one of your own."
        ),
        section=SECTION_PROFILE,
    ),
    Setting(
        name=NINJASRE_INVESTIGATOR_ENV,
        effect=(
            "Which investigation runtime this deployment runs, as "
            "'module:factory'. Composing one means choosing a provider, a "
            "capability catalogue, and a credential proxy — a deployment "
            "decision. Unset, every route works except starting an "
            "investigation, which refuses with a message naming this setting."
        ),
        section=SECTION_PROFILE,
    ),
    Setting(
        name=NINJASRE_HOME_DIR_ENV,
        effect=(
            "Where the command keeps its state. Follows the platform's own "
            "conventions when unset — XDG on Linux, Application Support on macOS."
        ),
        section=SECTION_PROFILE,
    ),
    # -- database --------------------------------------------------------------
    Setting(
        name=NINJASRE_DATABASE_URL_ENV,
        effect=(
            "The one PostgreSQL instance holding relational rows, vectors, and the "
            "service graph. Needs the pgvector and Apache AGE extensions."
        ),
        default="postgresql://ninjasre:ninjasre@postgres:5432/ninjasre",
        required=True,
        section=SECTION_DATABASE,
    ),
    Setting(
        name=NINJASRE_DATABASE_SCHEMA_ENV,
        effect="Which schema the platform's tables live in.",
        default=DEFAULT_DATABASE_SCHEMA,
        section=SECTION_DATABASE,
    ),
    Setting(
        name=NINJASRE_DATABASE_ENCRYPTION_KEY_ENV,
        effect=(
            "Encrypts stored credentials at rest — your model provider's key "
            "included, since that one is stored rather than set here. NinjaSRE "
            f"never generates one: produce it with {KEY_GENERATOR_HINT} and back "
            "it up separately from your database dumps. Lose it and every stored "
            "credential has to be re-entered. Only the dev profile, which runs "
            "the credential proxy in-process and may store nothing, starts "
            "without one."
        ),
        secret=True,
        required=True,
        section=SECTION_DATABASE,
    ),
    # -- provider --------------------------------------------------------------
    Setting(
        name=NINJASRE_LLM_PROVIDER_ENV,
        effect=(
            "Which model provider to use. Connecting one is a first-run step, "
            "done in the console, where the credential goes to the vault instead "
            "of into this file; setting it here is the other way, for an operator "
            "who would rather hand the deployment its provider than click one. A "
            "deployment with neither starts, says it has no provider, and shows "
            f"where to connect one. One of: {', '.join(SUPPORTED_PROVIDERS)}."
        ),
        default=DEFAULT_PROVIDER,
        section=SECTION_PROVIDER,
    ),
    Setting(
        name=NINJASRE_LLM_MODEL_ENV,
        effect="Which model, when the effective configuration names none.",
        default=DEFAULT_MODEL_ID,
        section=SECTION_PROVIDER,
    ),
    Setting(
        name=NINJASRE_LLM_TRANSPORT_ENV,
        effect=(
            "How requests reach the provider. The vendor SDK is the path the "
            f"contract suite treats as normative. One of: {', '.join(SUPPORTED_TRANSPORTS)}."
        ),
        default=DEFAULT_TRANSPORT,
        section=SECTION_PROVIDER,
    ),
    Setting(
        name=ANTHROPIC_API_KEY_ENV,
        effect="Authenticates the anthropic provider.",
        secret=True,
        section=SECTION_PROVIDER,
    ),
    Setting(
        name=ANTHROPIC_BASE_URL_ENV,
        effect="Points the anthropic provider at your own gateway instead of the vendor's.",
        section=SECTION_PROVIDER,
    ),
    Setting(
        name=OPENAI_API_KEY_ENV,
        effect="Authenticates the openai provider.",
        secret=True,
        section=SECTION_PROVIDER,
    ),
    Setting(
        name=OPENAI_BASE_URL_ENV,
        effect="Points the openai provider at your own gateway, or at a local vLLM.",
        section=SECTION_PROVIDER,
    ),
    Setting(
        name=AZURE_OPENAI_API_KEY_ENV,
        effect="Authenticates the azure_openai provider.",
        secret=True,
        section=SECTION_PROVIDER,
    ),
    Setting(
        name=AZURE_OPENAI_ENDPOINT_ENV,
        effect="Your Azure OpenAI resource's endpoint.",
        section=SECTION_PROVIDER,
    ),
    Setting(
        name=AZURE_OPENAI_DEPLOYMENT_ENV,
        effect="Which Azure OpenAI deployment name to call.",
        section=SECTION_PROVIDER,
    ),
    Setting(
        name=AZURE_OPENAI_API_VERSION_ENV,
        effect="Which Azure OpenAI API version to send.",
        section=SECTION_PROVIDER,
    ),
    Setting(
        name=AWS_ACCESS_KEY_ID_ENV,
        effect="Authenticates the aws_bedrock provider, with the secret key below.",
        secret=True,
        section=SECTION_PROVIDER,
    ),
    Setting(
        name=AWS_SECRET_ACCESS_KEY_ENV,
        effect="The other half of the Bedrock key pair.",
        secret=True,
        section=SECTION_PROVIDER,
    ),
    Setting(
        name=AWS_SESSION_TOKEN_ENV,
        effect="A session token, when Bedrock is reached with temporary credentials.",
        secret=True,
        section=SECTION_PROVIDER,
    ),
    Setting(
        name=AWS_PROFILE_ENV,
        effect="A named AWS profile, instead of a key pair.",
        section=SECTION_PROVIDER,
    ),
    Setting(
        name=AWS_REGION_ENV,
        effect="Which region Bedrock is called in.",
        section=SECTION_PROVIDER,
    ),
    Setting(
        name=AWS_BEDROCK_ENDPOINT_ENV,
        effect="Points Bedrock at a VPC endpoint instead of the public one.",
        section=SECTION_PROVIDER,
    ),
    Setting(
        name=GOOGLE_API_KEY_ENV,
        effect="Authenticates the google_gemini provider.",
        secret=True,
        section=SECTION_PROVIDER,
    ),
    Setting(
        name=GOOGLE_APPLICATION_CREDENTIALS_ENV,
        effect="Path to a service-account file, for google_vertex_ai.",
        section=SECTION_PROVIDER,
    ),
    Setting(
        name=GOOGLE_CLOUD_PROJECT_ENV,
        effect="Which project Vertex AI calls are billed to.",
        section=SECTION_PROVIDER,
    ),
    Setting(
        name=GOOGLE_CLOUD_LOCATION_ENV,
        effect="Which region Vertex AI is called in.",
        section=SECTION_PROVIDER,
    ),
    Setting(
        name=OPENROUTER_API_KEY_ENV,
        effect="Authenticates the openrouter provider.",
        secret=True,
        section=SECTION_PROVIDER,
    ),
    Setting(
        name=OPENROUTER_BASE_URL_ENV,
        effect="Points openrouter somewhere other than its own endpoint.",
        section=SECTION_PROVIDER,
    ),
    Setting(
        name=NVIDIA_API_KEY_ENV,
        effect="Authenticates the nvidia_nim provider.",
        secret=True,
        section=SECTION_PROVIDER,
    ),
    Setting(
        name=NVIDIA_NIM_BASE_URL_ENV,
        effect="Points NIM at your own inference microservice rather than the hosted one.",
        section=SECTION_PROVIDER,
    ),
    Setting(
        name=OLLAMA_BASE_URL_ENV,
        effect=(
            "Where your Ollama server is. This is the air-gapped path: a local "
            "model means a deployment with no egress at all is fully functional."
        ),
        default="http://ollama:11434/v1",
        section=SECTION_PROVIDER,
    ),
    Setting(
        name=VLLM_BASE_URL_ENV,
        effect="Where your vLLM server is, as the other local-model option.",
        section=SECTION_PROVIDER,
    ),
    # -- network ---------------------------------------------------------------
    Setting(
        name=NINJASRE_API_HOST_ENV,
        effect=(
            "Which interface the API binds. Loopback by default: binding to every "
            "interface is a decision, not a default that ships open."
        ),
        default=DEFAULT_API_HOST,
        section=SECTION_NETWORK,
    ),
    Setting(
        name=NINJASRE_API_PORT_ENV,
        effect="Which port the REST and SSE surface listens on.",
        default=str(DEFAULT_API_PORT),
        section=SECTION_NETWORK,
    ),
    Setting(
        name=NINJASRE_CONSOLE_PORT_ENV,
        effect="Which port the web console listens on.",
        default=str(DEFAULT_CONSOLE_PORT),
        section=SECTION_NETWORK,
    ),
    Setting(
        name=NINJASRE_PROXY_PORT_ENV,
        effect="Which port the credential proxy listens on.",
        default=str(DEFAULT_CREDENTIAL_PROXY_PORT),
        section=SECTION_NETWORK,
    ),
    # -- security --------------------------------------------------------------
    Setting(
        name=LOCAL_ACCOUNT_USERNAME_ENV,
        effect=(
            "The name somebody types to sign in when this deployment has no "
            "identity provider. Only meaningful alongside the passphrase below."
        ),
        default=LOCAL_ACCOUNT_USERNAME,
        section=SECTION_SECURITY,
    ),
    Setting(
        name=LOCAL_ACCOUNT_PASSWORD_HASH_ENV,
        effect=(
            "The stored form of that passphrase, as 'ninjasre hash-password' "
            "prints it. Unset, there is no local account and the sign-in page "
            "refuses everything — which is correct for a deployment whose "
            "operators come from a directory."
        ),
        secret=True,
        section=SECTION_SECURITY,
    ),
    Setting(
        name=LOCAL_ACCOUNT_DEMO_ENV,
        effect=(
            "Declares this a demonstration deployment, which is the only thing "
            "that makes the passphrase this project ships with acceptable. Set "
            "it and a first run needs no configuration at all; leave it unset "
            "and a deployment still carrying that passphrase refuses to start."
        ),
        section=SECTION_SECURITY,
    ),
    Setting(
        name=NINJASRE_CREDENTIAL_PROXY_URL_ENV,
        effect=(
            "Where the credential proxy is. Required on any profile that runs it "
            "as its own service; the dev profile runs it in-process and needs none."
        ),
        default="http://proxy:8422",
        section=SECTION_SECURITY,
    ),
    Setting(
        name=NINJASRE_CREDENTIAL_PROXY_TOKEN_ENV,
        effect="Authenticates the application to the credential proxy.",
        secret=True,
        section=SECTION_SECURITY,
    ),
    Setting(
        name=NINJASRE_VAULT_MASTER_KEY_ENV,
        effect="The vault's master key, when it is supplied inline rather than from a file.",
        secret=True,
        section=SECTION_SECURITY,
    ),
    Setting(
        name=NINJASRE_VAULT_KEY_FILE_ENV,
        effect="Path to the vault's master key, which is the shape a secrets mount takes.",
        section=SECTION_SECURITY,
    ),
    Setting(
        name=NINJASRE_SANDBOX_PROFILE_ENV,
        effect=(
            "Overrides the isolation profile the deployment profile implies. "
            "Leave unset: a disagreement between the two is refused at startup."
        ),
        section=SECTION_SECURITY,
    ),
    Setting(
        name=NINJASRE_SANDBOX_IMAGE_ENV,
        effect="Which image the container and kubernetes sandbox profiles run capabilities in.",
        section=SECTION_SECURITY,
    ),
    Setting(
        name=NINJASRE_SANDBOX_NAMESPACE_ENV,
        effect="Which Kubernetes namespace sandbox pods land in.",
        section=SECTION_SECURITY,
    ),
    Setting(
        name=NINJASRE_SANDBOX_POOL_SIZE_ENV,
        effect="How many warm sandboxes stay claimable, so provisioning is off the critical path.",
        default=str(SANDBOX_WARM_POOL_SIZE),
        section=SECTION_SECURITY,
    ),
    Setting(
        name=NINJASRE_CONTAINER_RUNTIME_ENV,
        effect="Which container binary the container sandbox profile drives.",
        default="docker",
        section=SECTION_SECURITY,
    ),
    Setting(
        name=NINJASRE_MASKING_ENABLED_ENV,
        effect="Whether sensitive values are masked before they reach a model or a log.",
        default="true",
        section=SECTION_SECURITY,
    ),
    Setting(
        name=NINJASRE_MASKING_POLICY_ENV,
        effect="How aggressively masking rewrites what it finds.",
        default=DEFAULT_MASKING_POLICY,
        section=SECTION_SECURITY,
    ),
    Setting(
        name=NINJASRE_GUARDRAIL_RULES_PATH_ENV,
        effect="Path to your own guardrail ruleset, layered over the shipped one.",
        section=SECTION_SECURITY,
    ),
    Setting(
        name=NINJASRE_AUDIT_FALLBACK_PATH_ENV,
        effect=(
            "Where audit records go when the database cannot take them. An audit "
            "trail with a gap is not an audit trail."
        ),
        section=SECTION_SECURITY,
    ),
    # -- memory and runtime ----------------------------------------------------
    Setting(
        name=NINJASRE_RUNTIME_ENV,
        effect=(
            "Which agent runtime runs investigations. The canonical loop is the "
            "only one that produces a published evaluation number."
        ),
        default=DEFAULT_RUNTIME,
        section=SECTION_MEMORY,
    ),
    Setting(
        name=NINJASRE_MEMORY_READ_ENV,
        effect="Whether investigations recall past episodes.",
        default="true",
        section=SECTION_MEMORY,
    ),
    Setting(
        name=NINJASRE_MEMORY_WRITE_ENV,
        effect="Whether finished investigations are written to the episode corpus.",
        default="true",
        section=SECTION_MEMORY,
    ),
    Setting(
        name=NINJASRE_MEMORY_STRATEGY_ENV,
        effect="Whether synthesised strategies are offered to the loop.",
        default="true",
        section=SECTION_MEMORY,
    ),
    Setting(
        name=NINJASRE_EMBEDDING_MODEL_ENV,
        effect=(
            "Which model embeds episodes and knowledge. Changing it needs a "
            "re-embedding generation, not just a restart."
        ),
        section=SECTION_MEMORY,
    ),
    Setting(
        name=NINJASRE_TOPOLOGY_ENV,
        effect="Whether the service graph is consulted for blast radius and dependencies.",
        default="true",
        section=SECTION_MEMORY,
    ),
    Setting(
        name=NINJASRE_KNOWLEDGE_ENV,
        effect="Whether the knowledge base is retrieved from during investigations.",
        default="true",
        section=SECTION_MEMORY,
    ),
    # -- operations ------------------------------------------------------------
    Setting(
        name=NINJASRE_LOG_LEVEL_ENV,
        effect="How much the deployment logs.",
        default=DEFAULT_LOG_LEVEL,
        section=SECTION_OPERATIONS,
    ),
    Setting(
        name=NINJASRE_LOG_FORMAT_ENV,
        effect="Structured JSON for a log pipeline, or console output for a person.",
        default=DEFAULT_LOG_FORMAT,
        section=SECTION_OPERATIONS,
    ),
    Setting(
        name=NINJASRE_LOG_MODULE_LEVELS_ENV,
        effect=(
            "Per-module log levels as module=LEVEL pairs, comma-separated, for "
            "turning one subsystem up without raising the whole deployment's "
            "volume. Re-read on demand rather than only at start."
        ),
        section=SECTION_OPERATIONS,
    ),
    Setting(
        name=NINJASRE_OTEL_ENDPOINT_ENV,
        effect=(
            "Where traces, metrics, and logs are exported, as an OTLP/HTTP base "
            "URL. Unset means nothing leaves the host, which is the default."
        ),
        section=SECTION_OPERATIONS,
    ),
    Setting(
        name=NINJASRE_TELEMETRY_SERVICE_NAME_ENV,
        effect="What this deployment calls itself to the collector.",
        default=DEFAULT_TELEMETRY_SERVICE_NAME,
        section=SECTION_OPERATIONS,
    ),
    Setting(
        name=NINJASRE_TELEMETRY_SAMPLE_RATIO_ENV,
        effect=(
            "The share of traces exported, between 0 and 1. Lower it when "
            "instrumentation shows up in investigation latency."
        ),
        default=str(DEFAULT_TELEMETRY_SAMPLE_RATIO),
        section=SECTION_OPERATIONS,
    ),
    Setting(
        name=NINJASRE_AIR_GAPPED_ENV,
        effect=(
            "Refuses to start if any setting implies an outbound connection. Turn "
            "it on with a local model to prove the deployment cannot phone home."
        ),
        default="false",
        section=SECTION_OPERATIONS,
    ),
    Setting(
        name=NINJASRE_EGRESS_ALLOWLIST_ENV,
        effect=(
            "Hosts you have consciously permitted, comma-separated. Everything the "
            "configuration already names is permitted by being configured."
        ),
        section=SECTION_OPERATIONS,
    ),
    Setting(
        name=NINJASRE_CA_BUNDLE_ENV,
        effect=(
            "A PEM bundle to trust in addition to the system store, for a corporate "
            "proxy that terminates TLS."
        ),
        section=SECTION_OPERATIONS,
    ),
    # -- the command -----------------------------------------------------------
    Setting(
        name=NINJASRE_ENDPOINT_ENV,
        effect="Which deployment the ninjasre command talks to.",
        default="http://localhost:8420",
        section=SECTION_CLIENT,
    ),
    Setting(
        name=NINJASRE_OUTPUT_FORMAT_ENV,
        effect="Whether the command renders for a person or emits JSON for a script.",
        section=SECTION_CLIENT,
    ),
    Setting(
        name=NINJASRE_NO_COLOR_ENV,
        effect="Turns colour off, for a terminal or a CI log that does not want it.",
        section=SECTION_CLIENT,
    ),
)


#: Variables the constants tier declares that an operator never sets. Named
#: explicitly rather than filtered by prefix, so adding one is a decision that
#: appears in a diff — which is the whole reason the completeness test can be
#: strict about everything else.
NOT_A_DEPLOYMENT_SETTING: Final[tuple[str, ...]] = (
    # Points the persistence contract suite at a live PostgreSQL.
    NINJASRE_TEST_DATABASE_URL_ENV,
    # The evaluation harness's own artefact and baseline paths. A deployment
    # never runs the corpus; a contributor and CI do.
    NINJASRE_SCENARIO_ARTIFACTS_ENV,
    NINJASRE_EVALUATION_BASELINES_ENV,
    NINJASRE_BENCHMARK_OUTPUT_ENV,
    # The chaos and end-to-end suites' cluster and artefact settings. Those
    # suites need infrastructure a deployment does not have and are never a
    # pull-request gate, let alone something an operator configures.
    NINJASRE_CHAOS_KUBECONFIG_ENV,
    NINJASRE_E2E_ARTIFACTS_ENV,
    # The mock data plane: which fixture scenario to serve, where the tree is,
    # and what a capture reads. A deployment never runs any of it — it is how
    # the console is built and reviewed with no backend behind it — and two of
    # them carry secrets that deliberately have no default: the pseudonym key
    # and the operator's list of real values both stay with the operator.
    NINJASRE_FIXTURE_SCENARIO_ENV,
    NINJASRE_FIXTURE_ROOT_ENV,
    NINJASRE_PSEUDONYM_KEY_ENV,
    NINJASRE_IDENTIFIER_FILE_ENV,
    NINJASRE_CAPTURE_ENDPOINT_ENV,
    NINJASRE_CAPTURE_TOKEN_ENV,
    NINJASRE_CAPTURE_NODES_ENV,
    NINJASRE_CAPTURE_SSH_USER_ENV,
    NINJASRE_CAPTURE_RAW_DIR_ENV,
)


def setting_names() -> frozenset[str]:
    """Return every variable this catalogue documents."""
    return frozenset(setting.name for setting in SETTINGS)


def required_settings() -> tuple[Setting, ...]:
    """Return the settings a deployment cannot start without (FR-010)."""
    return tuple(setting for setting in SETTINGS if setting.required)


def sections() -> tuple[str, ...]:
    """Return the section headings, in the order the generated file uses them."""
    ordered: dict[str, None] = {}
    for setting in SETTINGS:
        ordered.setdefault(setting.section, None)
    return tuple(ordered)


def render_env_example() -> str:
    """Return the whole ``.env.example`` document, generated from the catalogue.

    Commented-out lines for everything optional, live lines for the two things
    a deployment needs: where its database is, and the key its stored
    credentials are sealed with. The database URL carries a working default and
    the key deliberately does not, because NinjaSRE never generates one — so a
    copied file starts a deployment that refuses, by name, over the one value
    only the operator can produce. That is the intended first failure, and it
    is a better one than a deployment that boots and cannot store anything.
    """
    lines = [
        "# NinjaSRE — every setting, its default, whether it is required, and what it affects.",
        "#",
        "# Generated from platform/startup/settings.py by tools/generate_env_example.py.",
        "# Edit the catalogue, not this file: `make check-env-example` fails on drift.",
        "#",
        "# Copy to .env, set the two required values, and start. Everything commented",
        "# out already has a working default.",
    ]
    for section in sections():
        lines.extend(["", f"# --- {section} " + "-" * max(0, 72 - len(section)), ""])
        for setting in SETTINGS:
            if setting.section != section:
                continue
            lines.append(setting.render())
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "ENV_EXAMPLE_COMMENT_WIDTH",
    "NOT_A_DEPLOYMENT_SETTING",
    "SECRET_PLACEHOLDER",
    "SETTINGS",
    "Setting",
    "render_env_example",
    "required_settings",
    "sections",
    "setting_names",
]
