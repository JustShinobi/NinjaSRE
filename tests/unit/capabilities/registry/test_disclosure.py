"""A skill costs its index entry every turn and its body only when chosen.

That split is the whole reason a catalogue of integrations fits in
a context window. Get it wrong in the obvious way — read the file when the
skill is discovered — and the saving disappears silently, because everything
still works and the only symptom is a context bill nobody attributes.

So the tests here are about *when* the file is read, not only about what comes
out of it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from capabilities.registry.disclosure import (
    SkillManifestError,
    body_violations,
    load_skill,
    parse_skill_manifest,
)
from config.constants.capabilities import MAX_SKILL_METADATA_TOKENS
from core.capability.metadata import SkillMetadata

pytestmark = pytest.mark.unit


MANIFEST = """---
name: observability-datadog
description: Datadog log, metric, and APM investigation. Statistics before samples.
domain: observability
applies_when:
  alert_sources: [datadog]
  tags: [logs, metrics, apm]
directs_tools:
  - datadog_log_statistics
  - datadog_sample_logs
requires:
  integrations: [datadog]
---

# Datadog investigation

Start with statistics. Sampling before you know the shape of the data is how an
investigation ends up reasoning about the first fifty lines.
"""


def _write(tmp_path: Path, text: str, *, name: str = "observability-datadog") -> Path:
    directory = tmp_path / name
    directory.mkdir(parents=True, exist_ok=True)
    manifest = directory / "SKILL.md"
    manifest.write_text(text, encoding="utf-8")
    return manifest


def test_a_manifest_parses_into_metadata_and_a_body() -> None:
    metadata, body = parse_skill_manifest(MANIFEST, source="observability-datadog/SKILL.md")

    assert isinstance(metadata, SkillMetadata)
    assert metadata.name == "observability-datadog"
    assert metadata.domain == "observability"
    assert metadata.applies_when.alert_sources == ("datadog",)
    assert metadata.applies_when.tags == ("logs", "metrics", "apm")
    assert metadata.directs_tools == ("datadog_log_statistics", "datadog_sample_logs")
    assert metadata.requires.integrations == ("datadog",)
    assert "Start with statistics" in body


def test_both_list_notations_mean_the_same_thing() -> None:
    """Hand-written manifests will use both. Neither may surprise."""
    inline = MANIFEST.replace(
        "directs_tools:\n  - datadog_log_statistics\n  - datadog_sample_logs",
        "directs_tools: [datadog_log_statistics, datadog_sample_logs]",
    )

    from_block, _ = parse_skill_manifest(MANIFEST, source="a")
    from_inline, _ = parse_skill_manifest(inline, source="b")

    assert from_block.directs_tools == from_inline.directs_tools


def test_a_manifest_without_frontmatter_is_rejected_by_name() -> None:
    with pytest.raises(SkillManifestError, match="frontmatter"):
        parse_skill_manifest("# Just a document\n", source="orphan/SKILL.md")


def test_an_unterminated_frontmatter_block_is_rejected() -> None:
    with pytest.raises(SkillManifestError, match="frontmatter"):
        parse_skill_manifest("---\nname: x\n", source="orphan/SKILL.md")


@pytest.mark.parametrize("missing", ["name", "description", "domain"])
def test_every_required_frontmatter_field_is_enforced(missing: str) -> None:
    lines = [line for line in MANIFEST.splitlines() if not line.startswith(f"{missing}:")]

    with pytest.raises(SkillManifestError, match=missing):
        parse_skill_manifest("\n".join(lines), source="incomplete/SKILL.md")


def test_an_unknown_frontmatter_key_is_rejected() -> None:
    """A typo in a key is a field that silently did nothing."""
    with pytest.raises(SkillManifestError, match="allowed_when"):
        parse_skill_manifest(
            MANIFEST.replace("applies_when:", "allowed_when:"), source="typo/SKILL.md"
        )


def test_a_duplicate_key_is_rejected_rather_than_last_one_winning() -> None:
    with pytest.raises(SkillManifestError, match="domain"):
        parse_skill_manifest(
            MANIFEST.replace("domain: observability", "domain: observability\ndomain: infra"),
            source="duplicate/SKILL.md",
        )


def test_a_tab_indent_is_rejected_with_an_explanation() -> None:
    with pytest.raises(SkillManifestError, match="tab"):
        parse_skill_manifest(
            MANIFEST.replace("  alert_sources: [datadog]", "\talert_sources: [datadog]"),
            source="tabbed/SKILL.md",
        )


def test_the_body_is_not_read_until_it_is_asked_for(tmp_path: Path) -> None:
    """The property progressive disclosure actually rests on.

    The manifest is opened once at discovery to read its frontmatter. What must
    not happen is the body being *retained* — so the file is deleted after
    loading, and a skill that had kept the body would still answer.
    """
    manifest = _write(tmp_path, MANIFEST)
    skill = load_skill(manifest)

    assert skill.metadata.name == "observability-datadog"

    manifest.write_text("---\nname: x\n---\nreplaced body\n", encoding="utf-8")

    assert "replaced body" in skill.body()


def test_a_loaded_body_is_read_once_and_then_cached(tmp_path: Path) -> None:
    manifest = _write(tmp_path, MANIFEST)
    skill = load_skill(manifest)

    first = skill.body()
    manifest.unlink()

    assert skill.body() == first


def test_a_skill_reports_what_its_index_entry_costs(tmp_path: Path) -> None:
    skill = load_skill(_write(tmp_path, MANIFEST))

    assert 0 < skill.metadata_tokens <= MAX_SKILL_METADATA_TOKENS


def test_the_metadata_cost_excludes_the_body(tmp_path: Path) -> None:
    """Otherwise the budget measures the thing disclosure exists not to pay for."""
    long_body = MANIFEST + ("\nA further paragraph of methodology. " * 200)
    skill = load_skill(_write(tmp_path, long_body))

    assert skill.metadata_tokens <= MAX_SKILL_METADATA_TOKENS


def test_the_counter_is_replaceable_so_a_provider_tokeniser_can_be_used(
    tmp_path: Path,
) -> None:
    skill = load_skill(_write(tmp_path, MANIFEST), counter=lambda text: len(text))

    assert skill.metadata_tokens > MAX_SKILL_METADATA_TOKENS


@pytest.mark.parametrize(
    "body",
    [
        "Run `python check_pods.py` against the cluster.",
        "```bash\nkubectl delete pod checkout-api\n```",
        "$ curl -X POST https://api.example.com/restart",
        "Execute kubectl rollout restart deployment/checkout.",
        "```shell\nssh prod-01 'systemctl restart nginx'\n```",
    ],
)
def test_a_body_instructing_shell_execution_is_rejected(body: str) -> None:
    """ADR 0002's safety property, kept true as skills are ported from a format
    that permitted arbitrary shell.

    A skill directs tools. A skill that tells the model to run a command has
    routed around every approval, every rollback plan, and every audit record
    the tool layer exists to provide.
    """
    assert body_violations(body)


@pytest.mark.parametrize(
    "body",
    [
        "Prefer `datadog_log_statistics` before `datadog_sample_logs`.",
        "The kubectl equivalent of this tool is `kubectl get pods`, for orientation.",
        "```python\n# illustrative only: the tool does this for you\ncount_by_status(logs)\n```",
        "```yaml\nalert_sources: [datadog]\n```",
        "# The five phases\n\n## 1. Establish the symptom\n",
        "### When the metric looks fine\n",
    ],
)
def test_prose_about_a_command_is_not_an_instruction_to_run_one(body: str) -> None:
    """The lint has to survive every shipped skill without being switched off.

    A rule that fires on the word `kubectl` would be disabled within a week,
    and a disabled rule protects nothing.
    """
    assert body_violations(body) == ()


def test_a_violation_names_the_line_it_found(tmp_path: Path) -> None:
    violations = body_violations("Fine paragraph.\n\nRun `bash deploy.sh` on the host.\n")

    assert len(violations) == 1
    assert "3" in violations[0]
