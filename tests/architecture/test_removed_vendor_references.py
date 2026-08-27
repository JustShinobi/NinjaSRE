"""A vendor this catalogue no longer ships leaves no trace outside its record.

Two ways a removed vendor survives its own removal, and both are checked here:

``import``
    A committed Python module still reaching into ``integrations.<vendor>``.
    Precise by construction — an import statement either names the package or
    it does not, so this half of the sweep has no false positive to reason
    about.

``reference``
    A vendor named in the surfaces an operator actually reads: the generated
    documentation's source material (``AGENTS.md`` files, ``docs/*.md``,
    ``README.md``), and the console surfaces a removed vendor could orphan
    (the i18n catalogues, the route table, the visual-screen registry). This
    half is deliberately not "every committed file": arbitrary implementation
    prose shares words with vendor names for reasons that have nothing to do
    with the integration catalogue (linear light, a temporal window, a spark
    of an idea), and a component that legitimately shares a vendor's name — a
    notification sink, a chat surface, a knowledge-base source — is not this
    vendor's package and is excluded by name, not by accident.

Three exceptions carry the intent forward on purpose: the roadmap's own
record of deferred scope, the decision record explaining why the catalogue no
longer carries it, and the archive a removed vendor's own methodology skill
waits in until the vendor returns.
"""

from __future__ import annotations

import re
import subprocess
from functools import cache
from pathlib import Path

import pytest
from contract_config import REPO_ROOT

pytestmark = pytest.mark.architecture


@cache
def _tracked_files() -> frozenset[Path]:
    """Return every file git tracks — what "committed" means for this sweep.

    A gitignored file (``docs/provenance-map.md``, a build artefact) can name
    whatever it likes; it never reaches a clone, and a rule about what committed
    files may name has nothing to say about it.
    """
    output = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=True,
        text=True,
    ).stdout
    return frozenset(REPO_ROOT / line for line in output.splitlines() if line.strip())


#: Every vendor package this catalogue no longer ships. The one place this
#: module hard-codes the list — it is what the sweep is checking for.
REMOVED_VENDORS: tuple[str, ...] = (
    "airflow",
    "amplitude",
    "aws",
    "aws_cloudtrail",
    "aws_ec2",
    "aws_ecs",
    "aws_eks",
    "aws_elb",
    "aws_lambda",
    "aws_rds",
    "aws_s3",
    "azure",
    "azure_monitor",
    "azure_sql",
    "better_stack",
    "bigquery",
    "bitbucket",
    "blameless",
    "clickhouse",
    "clickup",
    "confluence",
    "coralogix",
    "dagster",
    "datadog",
    "discord",
    "docker",
    "elasticsearch",
    "firehydrant",
    "flagd",
    "flink",
    "gcp",
    "gitlab",
    "google_docs",
    "groundcover",
    "honeycomb",
    "incident_io",
    "jaeger",
    "jenkins",
    "jira",
    "kafka",
    "linear",
    "microsoft_teams",
    "mongodb_atlas",
    "new_relic",
    "notion",
    "opensearch",
    "opsgenie",
    "pagerduty",
    "posthog",
    "prefect",
    "proxmox_backup_server",
    "rabbitmq",
    "railway",
    "rocket_chat",
    "sentry",
    "servicenow",
    "slack",
    "snowflake",
    "sourcegraph",
    "spark",
    "splunk",
    "supabase",
    "tempo",
    "temporal",
    "trello",
    "twilio",
    "vercel",
    "victorialogs",
    "victoriametrics",
    "whatsapp",
)

#: Where the intent behind a removed vendor is allowed to keep living.
ALLOWED_REFERENCE_FILES: frozenset[Path] = frozenset(
    {
        REPO_ROOT / "docs" / "roadmap.md",
    }
)

#: A path under this prefix is a decision record, and a new one for this
#: catalogue's own amendment is exactly where the removed names belong.
ADR_DIRECTORY = REPO_ROOT / "docs" / "adr"

#: A vendor's own archived methodology skill names itself throughout — that is
#: the whole content of a `SKILL.md` — and the archive exists so the text
#: returns whole the day the vendor does. Excluded here for the same reason
#: the ADR directory is: naming the vendor is the archive's entire job.
METHODOLOGY_ARCHIVE_DIRECTORY = REPO_ROOT / "docs" / "methodology" / "archive"

#: Generated documentation (``docs/site/``, ``docs/capabilities.md``,
#: ``docs/integrations-catalogue.md``) is deliberately *not* excluded here — a
#: removed vendor drops out the moment the generator runs again, and this
#: sweep is what proves the regeneration actually happened rather than taking
#: it on faith.

#: Components that share a name with a removed vendor package without being
#: it — a notification sink, a chat surface, a knowledge-base source, the
#: report-destination vocabulary a formatter renders into. Excluded by the
#: boundary the specification itself draws (notification destination and chat
#: surface are named explicitly; a report destination and a knowledge-base
#: source are the same boundary applied to the same two components), not by
#: accident.
ALLOWED_REFERENCE_DIRECTORIES: tuple[Path, ...] = (
    REPO_ROOT / "gateway" / "slack",
    REPO_ROOT / "gateway" / "discord",
    REPO_ROOT / "gateway" / "teams",
    REPO_ROOT / "platform" / "knowledge" / "base" / "sync",
    REPO_ROOT / "platform" / "reporting",
)

#: A word that is also a vendor name, in a file where it never means the
#: vendor — an ordinary Portuguese noun in the pt-BR catalogue, a review
#: rationale's "temporal coincidence" in a visual-screen record. A whole-file
#: exception would stop this sweep from catching a real vendor string leaking
#: into the same file; a (file, word) pair does not.
ALLOWED_WORD_IN_FILE: frozenset[tuple[str, str]] = frozenset(
    {
        # "tempo" is Portuguese for "time" and appears throughout the ordinary
        # catalogue ("há muito tempo" — "a long time ago"); it never names the
        # Grafana Tempo integration in this file.
        ("console/src/i18n/pt-BR.ts", "tempo"),
        # "a temporal coincidence" — the English adjective, in a captured
        # review rationale; not the Temporal workflow-engine integration.
        ("console/visual/screens.json", "temporal"),
        # "AWS key identifiers" as an example of a secret *shape* the masking
        # rules redact — a property of the string, not of whether the AWS
        # integration package is installed.
        ("docs/synthetic-scenarios.md", "aws"),
        # "A change reported as a temporal coincidence is not evidence of a
        # cause" — the English adjective, in the changes-correlation tool's
        # own description; not the Temporal workflow-engine integration.
        # Generated into both capability reference pages.
        ("docs/capabilities.md", "temporal"),
        ("docs/site/capabilities/changes.md", "temporal"),
    }
)

ALLOWED_REFERENCE_FILE_NAMES: frozenset[str] = frozenset(
    {
        # Notification sinks: the destination, not the removed integration package.
        "platform/notifications/sinks/pagerduty.py",
        "config/constants/notifications.py",
        "platform/config_service/templates/golden/incident-triage-slack.yml",
        # Chat surfaces and the console's cross-surface approval sync, by name.
        "docs/architecture.md",
        "docs/chat-surfaces.md",
        "docs/change-approval.md",
        "docs/configuration.md",
        "docs/notifications-and-reporting.md",
        "docs/topology-and-knowledge.md",
        "docs/vision.md",
        "gateway/AGENTS.md",
        # Secret-shape patterns (masking) and export-format interoperability —
        # neither is about whether the named vendor is in the catalogue.
        "docs/guardrails-and-masking.md",
        "docs/identity-and-audit.md",
        # Docker as the deployment technology this product ships on
        # (`docker compose up`), not the removed target-monitoring
        # integration.
        "docs/deployment.md",
        "docs/site/deployment/index.md",
        "docs/site/contributing/index.md",
        "docs/site/quickstart/index.md",
        # A sandbox profile's own container-runtime default, and the LLM
        # providers a deployment may choose (Azure OpenAI, AWS Bedrock) —
        # both a different catalogue from the integrations one.
        "docs/site/configuration/isolation--masking--and-the-credential-proxy.md",
        "docs/site/configuration/model-provider.md",
        # "AWS SigV4" as the industry-recognised example of a signing scheme
        # that needs the key at request-construction time — explaining why
        # the credential proxy signs proxy-side, not a claim that AWS is in
        # the catalogue.
        "docs/site/security/index.md",
    }
)

#: Prose and reference surfaces a removed vendor would actually be visible in.
#: Not "every committed file" — see the module docstring for why.
REFERENCE_GLOBS: tuple[str, ...] = (
    "**/AGENTS.md",
    "docs/**/*.md",
    "README.md",
    "NOTICE",
    "console/src/i18n/*.ts",
    "console/src/shell/routes.ts",
    "console/visual/screens.json",
)

_IMPORT_PATTERN = re.compile(
    r"^\s*(?:from\s+integrations\.(\w+)(?:\.\w+)*\s+import\b|import\s+integrations\.(\w+))",
    re.MULTILINE,
)


def _word_pattern(vendor: str) -> re.Pattern[str]:
    return re.compile(rf"\b{re.escape(vendor)}\b", re.IGNORECASE)


def _is_allowed(path: Path) -> bool:
    if path in ALLOWED_REFERENCE_FILES:
        return True
    if ADR_DIRECTORY in path.parents or METHODOLOGY_ARCHIVE_DIRECTORY in path.parents:
        return True
    if path.relative_to(REPO_ROOT).as_posix() in ALLOWED_REFERENCE_FILE_NAMES:
        return True
    return any(directory in path.parents for directory in ALLOWED_REFERENCE_DIRECTORIES)


def _is_planning_record(relative) -> bool:
    """Return whether ``relative`` sits in a wave's planning directory.

    Those directories are now committed, which is what makes a control file
    readable beside the code it measured. They are a record of what was decided
    at a moment, not a surface anybody reads to learn what this deployment is
    today — a wave that planned against a catalogue of a different size states
    that size truthfully about its own moment. Matched by shape, because a list
    of wave names is out of date the first time nobody remembers to add one.
    """
    if relative.as_posix() == "docs/provenance-map.md":
        # The same kind of record, kept beside the docs rather than in a wave:
        # it says where each module came from, which is a fact about a moment
        # and not a claim about what this deployment ships today.
        return True
    return any(part == "specs" or re.fullmatch(r"specs_v\d+", part) for part in relative.parts)


def _python_files() -> tuple[Path, ...]:
    excluded_top = {".venv", "node_modules", "_research", ".git", ".codegraph"}
    tracked = _tracked_files()
    found: list[Path] = []
    for path in REPO_ROOT.rglob("*.py"):
        relative = path.relative_to(REPO_ROOT)
        if (
            relative.parts[0] in excluded_top
            or "__pycache__" in relative.parts
            or _is_planning_record(relative)
        ):
            continue
        if path not in tracked:
            continue
        found.append(path)
    return tuple(found)


def _reference_files() -> tuple[Path, ...]:
    tracked = _tracked_files()
    found: list[Path] = []
    for pattern in REFERENCE_GLOBS:
        for path in REPO_ROOT.glob(pattern):
            if not path.is_file() or path not in tracked:
                continue
            relative = path.relative_to(REPO_ROOT)
            if (
                "node_modules" in relative.parts
                or "_research" in relative.parts
                or _is_planning_record(relative)
            ):
                continue
            found.append(path)
    return tuple(found)


@pytest.mark.sweep
def test_no_committed_python_module_imports_a_removed_vendor_package() -> None:
    offenders: dict[str, list[str]] = {}
    for path in _python_files():
        text = path.read_text(encoding="utf-8")
        for match in _IMPORT_PATTERN.finditer(text):
            named = match.group(1) or match.group(2)
            if named in REMOVED_VENDORS:
                offenders.setdefault(str(path.relative_to(REPO_ROOT)), []).append(named)

    assert not offenders, (
        "committed modules still import a package this catalogue no longer ships:\n"
        + "\n".join(f"  {file}: {names}" for file, names in sorted(offenders.items()))
    )


@pytest.mark.sweep
def test_no_reference_surface_names_a_removed_vendor() -> None:
    offenders: dict[str, list[str]] = {}
    for path in _reference_files():
        if _is_allowed(path):
            continue
        relative_name = path.relative_to(REPO_ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        found = [
            vendor
            for vendor in REMOVED_VENDORS
            if _word_pattern(vendor).search(text)
            and (relative_name, vendor) not in ALLOWED_WORD_IN_FILE
        ]
        if found:
            offenders[relative_name] = found

    assert not offenders, (
        "a reference surface still names a vendor outside the validated scope, only the "
        "roadmap and the decision record may still name one:\n"
        + "\n".join(f"  {file}: {names}" for file, names in sorted(offenders.items()))
    )
