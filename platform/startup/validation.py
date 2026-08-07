"""Configuration checked before anything opens a socket, with actionable failures.

FR-006 asks for startup validation that fails with specific, actionable messages
naming the setting and the problem. Three decisions make that more than a
sentence in a specification.

**Every finding is collected before any is reported.** An operator with three
problems should learn all three from one boot, not from three. A validator that
raised on the first would turn a ten-minute setup into an hour of one restart
per typo.

**A finding has a remedy, not just a diagnosis.** ``ANTHROPIC_API_KEY is not
set`` is a diagnosis. ``Set ANTHROPIC_API_KEY, or set NINJASRE_LLM_PROVIDER to a
provider you have a credential for`` is something to type. The remedy is a
separate field rather than prose so a console can render it as an action.

**No finding quotes a value.** Validation runs against the environment, which
holds database passwords and API keys, and its output goes to a container log.
Names and shapes only.

The one thing this module deliberately does not do is connect to anything.
Reachability is readiness' question and it has a different answer over time; a
validator that failed on a database still starting up would make the deployment
order matter.
"""

from __future__ import annotations

import base64
import os
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from config.constants.deployment import (
    DEPLOYMENT_PROFILES,
    NINJASRE_AIR_GAPPED_ENV,
    NINJASRE_CA_BUNDLE_ENV,
    NINJASRE_DEPLOYMENT_PROFILE_ENV,
)
from config.constants.llm import (
    ANTHROPIC_API_KEY_ENV,
    AWS_ACCESS_KEY_ID_ENV,
    AWS_PROFILE_ENV,
    AWS_SECRET_ACCESS_KEY_ENV,
    AZURE_OPENAI_API_KEY_ENV,
    GOOGLE_API_KEY_ENV,
    GOOGLE_APPLICATION_CREDENTIALS_ENV,
    NINJASRE_LLM_PROVIDER_ENV,
    NVIDIA_API_KEY_ENV,
    OPENAI_API_KEY_ENV,
    OPENROUTER_API_KEY_ENV,
    PROVIDER_ANTHROPIC,
    PROVIDER_AWS_BEDROCK,
    PROVIDER_AZURE_OPENAI,
    PROVIDER_GOOGLE_GEMINI,
    PROVIDER_GOOGLE_VERTEX_AI,
    PROVIDER_NVIDIA_NIM,
    PROVIDER_OPENAI,
    PROVIDER_OPENROUTER,
    SUPPORTED_PROVIDERS,
)
from config.constants.persistence import (
    NINJASRE_DATABASE_ENCRYPTION_KEY_ENV,
    NINJASRE_DATABASE_URL_ENV,
)
from config.constants.security import (
    NINJASRE_CREDENTIAL_PROXY_URL_ENV,
    NINJASRE_SANDBOX_PROFILE_ENV,
    SANDBOX_PROFILES,
)
from platform.startup.egress import external_destinations, provider_is_local
from platform.startup.errors import ConfigurationInvalid, UnknownDeploymentProfile
from platform.startup.keys import ENCRYPTION_KEY_BYTES, KEY_GENERATOR_HINT
from platform.startup.profiles import (
    DeploymentProfile,
    ProfileTopology,
    resolve_profile,
    topology_for,
)

#: What each provider needs before it can authenticate. A provider whose entry
#: holds several names is satisfied by any one of them: Bedrock takes a key pair
#: or a named profile, and Vertex takes a key or an application-credentials file.
PROVIDER_CREDENTIAL_ENV: Mapping[str, tuple[str, ...]] = {
    PROVIDER_ANTHROPIC: (ANTHROPIC_API_KEY_ENV,),
    PROVIDER_OPENAI: (OPENAI_API_KEY_ENV,),
    PROVIDER_AZURE_OPENAI: (AZURE_OPENAI_API_KEY_ENV,),
    PROVIDER_AWS_BEDROCK: (AWS_ACCESS_KEY_ID_ENV, AWS_SECRET_ACCESS_KEY_ENV, AWS_PROFILE_ENV),
    PROVIDER_GOOGLE_GEMINI: (GOOGLE_API_KEY_ENV,),
    PROVIDER_GOOGLE_VERTEX_AI: (GOOGLE_API_KEY_ENV, GOOGLE_APPLICATION_CREDENTIALS_ENV),
    PROVIDER_OPENROUTER: (OPENROUTER_API_KEY_ENV,),
    PROVIDER_NVIDIA_NIM: (NVIDIA_API_KEY_ENV,),
}

#: URL schemes that name this deployment's one datastore. Both spellings, since
#: an operator's other tools accept ``postgres://`` and the driver rewrites it.
_POSTGRES_SCHEMES: tuple[str, ...] = (
    "postgres",
    "postgresql",
    "postgresql+asyncpg",
    "postgresql+psycopg",
)

#: Values that mean yes. Everything else means no, including the empty string,
#: so an unset variable and one set to nothing behave the same way.
_TRUTHY: frozenset[str] = frozenset({"1", "true", "yes", "on"})


class Severity(StrEnum):
    """Whether a finding stops the deployment or is reported and survived."""

    FATAL = "fatal"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class Finding:
    """One configuration problem, named by setting and answered by remedy."""

    setting: str
    problem: str
    remedy: str
    severity: Severity = Severity.FATAL

    def to_record(self) -> dict[str, object]:
        """Return the JSON-serialisable form a startup report serves."""
        return {
            "setting": self.setting,
            "problem": self.problem,
            "remedy": self.remedy,
            "severity": str(self.severity),
        }

    def __str__(self) -> str:
        return f"{self.setting}: {self.problem} {self.remedy}"


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """Everything one validation pass found, and whether it permits a start."""

    findings: tuple[Finding, ...] = ()
    profile: DeploymentProfile | None = None
    topology: ProfileTopology | None = None

    @property
    def fatal(self) -> tuple[Finding, ...]:
        """Return the findings that stop the deployment."""
        return tuple(f for f in self.findings if f.severity is Severity.FATAL)

    @property
    def warnings(self) -> tuple[Finding, ...]:
        """Return the findings worth saying out loud that do not stop a start."""
        return tuple(f for f in self.findings if f.severity is Severity.WARNING)

    @property
    def ok(self) -> bool:
        """Return whether this configuration permits the deployment to start."""
        return not self.fatal

    def summary(self) -> str:
        """Return the block a deployment prints at start, one line per finding."""
        if not self.findings:
            return "No configuration problems found."
        head = (
            f"{len(self.fatal)} fatal and {len(self.warnings)} advisory configuration finding(s):"
        )
        lines = [f"  [{finding.severity}] {finding}" for finding in self.findings]
        return "\n".join([head, *lines])

    def to_record(self) -> dict[str, object]:
        """Return the JSON-serialisable form a health endpoint serves."""
        return {
            "ok": self.ok,
            "profile": None if self.profile is None else str(self.profile),
            "findings": [finding.to_record() for finding in self.findings],
        }

    def raise_if_invalid(self) -> None:
        """Raise ``ConfigurationInvalid`` when anything fatal was found."""
        if self.ok:
            return
        raise ConfigurationInvalid(
            self.summary(), settings=[finding.setting for finding in self.fatal]
        )


def validate(environ: Mapping[str, str] | None = None) -> ValidationReport:
    """Return every configuration problem this environment has (FR-006).

    Never raises on a bad configuration — the report is the answer, and
    ``raise_if_invalid`` is what a boot sequence calls when it wants the
    exception.
    """
    source = dict(environ if environ is not None else os.environ)
    findings: list[Finding] = []

    profile, topology = _profile(source, findings)
    _database(source, findings)
    _provider(source, findings)
    _encryption_key(source, findings)
    _sandbox(source, topology, findings)
    _proxy(source, topology, findings)
    _air_gapped(source, findings)
    _trust_bundle(source, findings)

    return ValidationReport(findings=tuple(findings), profile=profile, topology=topology)


# -- the checks ---------------------------------------------------------------


def _profile(
    source: Mapping[str, str],
    findings: list[Finding],
) -> tuple[DeploymentProfile | None, ProfileTopology]:
    """Return the resolved profile, falling back so the remaining checks still run."""
    try:
        profile = resolve_profile(source)
    except UnknownDeploymentProfile as error:
        findings.append(
            Finding(
                setting=NINJASRE_DEPLOYMENT_PROFILE_ENV,
                problem=f"{error.name!r} is not a deployment profile.",
                remedy=f"Set it to one of: {', '.join(DEPLOYMENT_PROFILES)}.",
            )
        )
        # The rest of the checks still run, against the profile the deployment
        # would have had. An operator with a typo *and* a missing credential
        # should learn both now rather than after fixing the first one.
        return None, topology_for(DeploymentProfile.STANDARD)
    return profile, topology_for(profile)


def _database(source: Mapping[str, str], findings: list[Finding]) -> None:
    url = source.get(NINJASRE_DATABASE_URL_ENV, "").strip()
    if not url:
        findings.append(
            Finding(
                setting=NINJASRE_DATABASE_URL_ENV,
                problem="No database is configured.",
                remedy=(
                    "Set it to a postgresql:// URL for the instance holding this deployment's data."
                ),
            )
        )
        return
    scheme = url.partition("://")[0].lower()
    if scheme not in _POSTGRES_SCHEMES:
        findings.append(
            Finding(
                setting=NINJASRE_DATABASE_URL_ENV,
                problem=f"The URL names the {scheme!r} scheme.",
                remedy=(
                    "NinjaSRE keeps relational, vector, and graph data in one "
                    "PostgreSQL instance with pgvector and Apache AGE. Point it at "
                    "a postgresql:// URL."
                ),
            )
        )


def _provider(source: Mapping[str, str], findings: list[Finding]) -> None:
    """Check the one credential a minimum viable configuration needs (FR-010)."""
    named = source.get(NINJASRE_LLM_PROVIDER_ENV, "").strip().lower()

    if not named:
        configured = [
            provider
            for provider, names in PROVIDER_CREDENTIAL_ENV.items()
            if any(source.get(name, "").strip() for name in names)
        ]
        if not configured:
            findings.append(
                Finding(
                    setting=NINJASRE_LLM_PROVIDER_ENV,
                    problem="No model provider is configured.",
                    remedy=(
                        "Set it to one of: "
                        f"{', '.join(SUPPORTED_PROVIDERS)}, and set that provider's "
                        "credential. One provider credential is the whole minimum "
                        "viable configuration."
                    ),
                )
            )
        return

    if named not in SUPPORTED_PROVIDERS:
        findings.append(
            Finding(
                setting=NINJASRE_LLM_PROVIDER_ENV,
                problem=f"{named!r} is not a supported provider.",
                remedy=f"Set it to one of: {', '.join(SUPPORTED_PROVIDERS)}.",
            )
        )
        return

    required = PROVIDER_CREDENTIAL_ENV.get(named, ())
    if required and not any(source.get(name, "").strip() for name in required):
        findings.append(
            Finding(
                setting=required[0],
                problem=f"The {named} provider is selected and has no credential.",
                remedy=(
                    f"Set {' or '.join(required)} to the credential your {named} "
                    f"account uses, or select a different provider."
                ),
            )
        )


def _encryption_key(source: Mapping[str, str], findings: list[Finding]) -> None:
    """Check the key's shape. Whether it is the *right* key is the vault's question.

    An unset key is advisory rather than fatal, and that asymmetry is deliberate:
    a deployment that stores no credentials is legitimate and should not fail to
    start over a key it will never use. The first credential write is where the
    absence becomes an error, and ``keys.require_encryption_key`` is what raises
    it (FR-019).
    """
    material = source.get(NINJASRE_DATABASE_ENCRYPTION_KEY_ENV, "").strip()
    if not material:
        findings.append(
            Finding(
                setting=NINJASRE_DATABASE_ENCRYPTION_KEY_ENV,
                problem="No encryption key is configured, so no credential can be stored.",
                remedy=(
                    f"Generate one with {KEY_GENERATOR_HINT} and set it before "
                    f"configuring an integration. NinjaSRE never generates one for you."
                ),
                severity=Severity.WARNING,
            )
        )
        return

    try:
        decoded = base64.b64decode(material, validate=True)
    except (ValueError, TypeError):
        findings.append(
            Finding(
                setting=NINJASRE_DATABASE_ENCRYPTION_KEY_ENV,
                problem="The key is not valid base64.",
                remedy=(
                    f"A key is bytes, and base64 is how bytes survive an environment "
                    f"variable. Generate one with {KEY_GENERATOR_HINT}."
                ),
            )
        )
        return

    if len(decoded) != ENCRYPTION_KEY_BYTES:
        findings.append(
            Finding(
                setting=NINJASRE_DATABASE_ENCRYPTION_KEY_ENV,
                problem=f"The key decodes to {len(decoded)} bytes.",
                remedy=(
                    f"AES-256 needs exactly {ENCRYPTION_KEY_BYTES} bytes. Generate "
                    f"one with {KEY_GENERATOR_HINT} rather than padding this one."
                ),
            )
        )


def _sandbox(
    source: Mapping[str, str],
    topology: ProfileTopology,
    findings: list[Finding],
) -> None:
    """Check the sandbox against the profile that already implies one (FR-005)."""
    named = source.get(NINJASRE_SANDBOX_PROFILE_ENV, "").strip().lower()
    if not named:
        return
    if named not in SANDBOX_PROFILES:
        findings.append(
            Finding(
                setting=NINJASRE_SANDBOX_PROFILE_ENV,
                problem=f"{named!r} is not a sandbox profile.",
                remedy=f"Set it to one of: {', '.join(SANDBOX_PROFILES)}, or leave it unset.",
            )
        )
        return
    if named != str(topology.sandbox_profile):
        findings.append(
            Finding(
                setting=NINJASRE_SANDBOX_PROFILE_ENV,
                problem=(
                    f"The {topology.profile} deployment profile isolates capabilities "
                    f"with the {topology.sandbox_profile} sandbox, and this asks for "
                    f"{named!r}."
                ),
                remedy=(
                    f"Leave it unset to take the {topology.profile} profile's own "
                    f"sandbox, or change the deployment profile to the one whose "
                    f"sandbox you want."
                ),
            )
        )


def _proxy(
    source: Mapping[str, str],
    topology: ProfileTopology,
    findings: list[Finding],
) -> None:
    """Check that a profile running the proxy out of process knows where it is."""
    if topology.runs_proxy_in_process:
        return
    if source.get(NINJASRE_CREDENTIAL_PROXY_URL_ENV, "").strip():
        return
    findings.append(
        Finding(
            setting=NINJASRE_CREDENTIAL_PROXY_URL_ENV,
            problem=(
                f"The {topology.profile} profile runs the credential proxy as its own "
                f"service and nothing says where it is."
            ),
            remedy=(
                "Set it to the proxy's address. Authenticated calls go through the "
                "proxy, so a deployment without one can investigate nothing that "
                "needs a credential."
            ),
        )
    )


def _air_gapped(source: Mapping[str, str], findings: list[Finding]) -> None:
    """Check that an air-gapped deployment's configuration implies no egress (FR-023)."""
    if source.get(NINJASRE_AIR_GAPPED_ENV, "").strip().lower() not in _TRUTHY:
        return

    if not provider_is_local(source):
        provider = source.get(NINJASRE_LLM_PROVIDER_ENV, "").strip().lower()
        findings.append(
            Finding(
                setting=NINJASRE_LLM_PROVIDER_ENV,
                problem=(
                    f"This deployment is air-gapped and {provider or 'the default provider'} "
                    f"is reached over the internet."
                ),
                remedy=(
                    "Run a local model — Ollama or vLLM — and point the provider "
                    "endpoint at it. Provider neutrality is what makes a no-egress "
                    "deployment fully functional."
                ),
            )
        )

    for destination in external_destinations(source):
        if destination.setting == NINJASRE_LLM_PROVIDER_ENV:
            continue
        findings.append(
            Finding(
                setting=destination.setting,
                problem=f"This deployment is air-gapped and {destination} leaves the host.",
                remedy=(
                    "Point it at a service on the operator's own infrastructure, or "
                    "remove the setting."
                ),
            )
        )


def _trust_bundle(source: Mapping[str, str], findings: list[Finding]) -> None:
    """Check the TLS trust bundle exists before something fails to verify (FR-025)."""
    configured = source.get(NINJASRE_CA_BUNDLE_ENV, "").strip()
    if not configured:
        return
    path = Path(configured)
    if path.is_file() and os.access(path, os.R_OK):
        return
    findings.append(
        Finding(
            setting=NINJASRE_CA_BUNDLE_ENV,
            problem="The trust bundle is not a readable file.",
            remedy=(
                "Point it at a PEM bundle that is readable by the user this "
                "deployment runs as. A proxy that terminates TLS needs its "
                "certificate trusted, and an unreadable bundle fails every "
                "outbound call with a verification error instead."
            ),
        )
    )


__all__ = [
    "PROVIDER_CREDENTIAL_ENV",
    "Finding",
    "Severity",
    "ValidationReport",
    "validate",
]
