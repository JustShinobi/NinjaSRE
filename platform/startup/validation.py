"""Configuration checked before anything opens a socket, with actionable failures.

FR-006 asks for startup validation that fails with specific, actionable messages
naming the setting and the problem. Three decisions make that more than a
sentence in a specification.

**Every finding is collected before any is reported.** An operator with three
problems should learn all three from one boot, not from three. A validator that
raised on the first would turn a ten-minute setup into an hour of one restart
per typo.

**A finding has a remedy, not just a diagnosis.** ``NINJASRE_DATABASE_URL is not
set`` is a diagnosis. ``Set it to a postgresql:// URL for the instance holding
this deployment's data`` is something to type. The remedy is a separate field
rather than prose so a console can render it as an action.

**No finding quotes a value.** Validation runs against the environment, which
holds database passwords and API keys, and its output goes to a container log.
Names and shapes only.

The one thing this module deliberately does not do is connect to anything.
Reachability is readiness' question and it has a different answer over time; a
validator that failed on a database still starting up would make the deployment
order matter.

**And it cannot read the configuration tree.** Validation runs before the
database is open — every check after it needs the database URL this one checks —
so anything living in configuration is beyond what it can see. Which provider
and model each role runs on lives there. This module used to reach for
``NINJASRE_LLM_PROVIDER`` instead and treat it as the deployment's choice, which
gave it a fatal finding about a provider nothing would ever call: a value left
in a manifest could refuse a boot outright, and the deployment it refused was
correctly configured everywhere that counted. What the environment can still be
asked, honestly, is whether it equips *any* provider at all — see ``_provider``.
"""

from __future__ import annotations

import base64
import os
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final

from config.constants.deployment import (
    DEPLOYMENT_PROFILES,
    NINJASRE_AIR_GAPPED_ENV,
    NINJASRE_CA_BUNDLE_ENV,
    NINJASRE_DEPLOYMENT_PROFILE_ENV,
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
from platform.startup.egress import (
    PROVIDER_CREDENTIAL_ENV,
    PURPOSE_PROVIDER,
    external_destinations,
    provider_destinations,
)
from platform.startup.errors import ConfigurationInvalid, UnknownDeploymentProfile
from platform.startup.keys import ENCRYPTION_KEY_BYTES, KEY_GENERATOR_HINT
from platform.startup.profiles import (
    DeploymentProfile,
    ProfileTopology,
    resolve_profile,
    topology_for,
)

#: What the provider finding names, since no single variable is the answer. Eight
#: providers carry eight credential names between them, and the supported way to
#: connect one writes to the vault and sets nothing in the environment at all —
#: so the finding names the group. It is deliberately not an environment
#: variable: nothing reads it, and the one that used to be named here reads as an
#: instruction to set a line that does nothing.
PROVIDER_CREDENTIAL_SETTING: Final = "model provider credential"

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
    _encryption_key(source, topology, findings)
    _sandbox(source, topology, findings)
    _proxy(source, topology, findings)
    _air_gapped(source, findings)
    _trust_bundle(source, findings)

    return ValidationReport(findings=tuple(findings), profile=profile, topology=topology)


def validate_proxy(environ: Mapping[str, str] | None = None) -> ValidationReport:
    """Return every configuration problem the credential proxy's own environment has.

    The credential proxy brokers credentials for other processes; it never
    calls a model itself, so ``validate``'s provider check does not belong
    here — applying it would refuse a correctly configured proxy over a
    setting that belongs to a different process, and handing the proxy a
    provider credential just to satisfy the check would spread a secret to a
    process that never needed it, which is a worse position than the refusal
    it would silence. The sandbox check is skipped for the same reason: the
    proxy isolates nothing and runs no capability.

    Everything the proxy genuinely depends on is still checked: its database,
    its encryption key, its own address, the trust bundle a TLS-terminating
    call needs, and the destinations an air-gapped deployment may not reach —
    the proxy is the process that actually carries an authenticated call to a
    vendor on another process's behalf, so that no-egress guarantee is one it
    has to uphold for everything except the one destination that is still not
    its concern (see ``_proxy_egress`` below).

    Never raises — ``raise_if_invalid`` is what a boot sequence calls when it
    wants the exception, same as ``validate``.
    """
    source = dict(environ if environ is not None else os.environ)
    findings: list[Finding] = []

    profile, topology = _profile(source, findings)
    _database(source, findings)
    _encryption_key(source, topology, findings)
    _proxy(source, topology, findings)
    _proxy_egress(source, findings)
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
    """Warn when nothing in this environment equips any model provider at all.

    The one provider question an environment can still answer. Which provider a
    role runs on is configuration, and configuration is in a database this check
    runs before opening; but whether a credential or an endpoint is present here
    is a fact about the environment itself, and it is worth saying.

    **It is advisory and stays advisory**, in both directions. A deployment that
    has not been set up yet has connected nothing, which is the state every
    deployment starts in: connecting a provider is a first-run step the console
    has a screen for, and refusing to boot would kill the process that renders
    it. And a deployment that *has* been set up keeps its provider credential in
    the vault, where this check cannot see it — so silence here is as likely to
    mean "correctly configured" as "not configured", and a fatal finding would
    be fatal about a state nobody can distinguish from success.

    An endpoint counts as well as a credential, because a local model server
    needs no credential: a deployment running Ollama would otherwise be told at
    every boot that it has no provider, which is how an advisory becomes noise
    somebody filters out.
    """
    if provider_destinations(source):
        return

    findings.append(
        Finding(
            setting=PROVIDER_CREDENTIAL_SETTING,
            problem="Nothing in this environment equips a model provider.",
            remedy=(
                "Connect one at first run, in the console: the credential is "
                "stored in the vault, which this check runs too early to read, so "
                "a deployment that has done it will still see this line. Setting a "
                "provider's own credential or endpoint here is the other way, and "
                "which provider each role then runs on is configuration rather "
                "than an environment variable."
            ),
            severity=Severity.WARNING,
        )
    )


def _encryption_key(
    source: Mapping[str, str],
    topology: ProfileTopology,
    findings: list[Finding],
) -> None:
    """Check the key's shape, and its absence against what the profile has to store.

    Whether it is the *right* key is the vault's question, not this one.

    The severity of an absent key follows the topology rather than being fixed.
    A profile that runs the credential proxy inside the application process can
    legitimately store nothing at all, so a key it will never use is not worth
    refusing a start over. Every other profile reaches the proxy through the
    vault — the model provider's own credential included — and a deployment
    without a key there cannot finish its own first run: it reaches the provider
    step and fails at the write. Naming the setting at boot costs one line;
    discovering it costs an operator the first thing they try.
    """
    material = source.get(NINJASRE_DATABASE_ENCRYPTION_KEY_ENV, "").strip()
    if not material:
        findings.append(
            Finding(
                setting=NINJASRE_DATABASE_ENCRYPTION_KEY_ENV,
                problem="No encryption key is configured, so no credential can be stored.",
                remedy=(
                    f"Generate one with {KEY_GENERATOR_HINT} and set it before "
                    f"anything is configured. NinjaSRE never generates one for you."
                ),
                severity=(Severity.WARNING if topology.runs_proxy_in_process else Severity.FATAL),
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
    """Check that an air-gapped deployment's configuration implies no egress (FR-023).

    Every external destination is a finding, model providers included — and the
    provider ones are the reason this reads the derived list rather than a
    provider name. It used to refuse a boot whenever ``NINJASRE_LLM_PROVIDER``
    named a hosted provider, and to synthesise the shipped default when nothing
    named one, so an air-gapped deployment that had set none was refused over a
    vendor it had never configured and would never call. What is left is the
    honest half: a credential or an endpoint the operator actually put here, and
    a remedy naming the one they can remove.
    """
    if source.get(NINJASRE_AIR_GAPPED_ENV, "").strip().lower() not in _TRUTHY:
        return

    for destination in external_destinations(source):
        provider = destination.purpose.startswith(PURPOSE_PROVIDER)
        findings.append(
            Finding(
                setting=destination.setting,
                problem=f"This deployment is air-gapped and {destination} leaves the host.",
                remedy=(
                    (
                        "Run a local model — Ollama or vLLM — and point that "
                        "provider's endpoint at it, or remove the credential that "
                        "equips it here. Provider neutrality is what makes a "
                        "no-egress deployment fully functional."
                    )
                    if provider
                    else (
                        "Point it at a service on the operator's own infrastructure, "
                        "or remove the setting."
                    )
                ),
            )
        )


def _proxy_egress(source: Mapping[str, str], findings: list[Finding]) -> None:
    """Check the destinations an air-gapped deployment's own proxy may not reach.

    A narrower sibling of ``_air_gapped``, for ``validate_proxy``. The proxy is
    the process that actually carries an authenticated call to a vendor on
    another process's behalf, so the no-egress guarantee is one it has to
    uphold for the database, telemetry export, and the operator's own
    allow-list.

    Every provider-purposed destination is skipped, whatever setting produced
    it. The proxy never calls a model, so refusing to start it over a provider
    credential that reached its environment by sharing a manifest is the exact
    mistake ``validate_proxy`` exists to correct.
    """
    if source.get(NINJASRE_AIR_GAPPED_ENV, "").strip().lower() not in _TRUTHY:
        return

    for destination in external_destinations(source):
        if destination.purpose.startswith(PURPOSE_PROVIDER):
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
    "PROVIDER_CREDENTIAL_SETTING",
    "Finding",
    "Severity",
    "ValidationReport",
    "validate",
    "validate_proxy",
]
