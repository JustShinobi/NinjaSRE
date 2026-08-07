"""The authored documentation: complete, executable, and buildable with no network.

Three properties, and each one is here because of a failure that is invisible
until somebody is depending on it.

**Every documented example still works** (SC-007). A quickstart with a command
that no longer exists costs a reader the twenty minutes they spend assuming the
mistake is theirs.

**The quickstart is self-contained** (SC-006). A new operator has to reach a
successful investigation using only that page, which means it cannot send them
anywhere before the end.

**The build fetches nothing** (FR-019). An operator running air-gapped is
exactly the operator most likely to need the documentation, and a site with one
external script is a blank page on their host.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tools import build_docs, test_doc_examples

pytestmark = pytest.mark.contract

REPO_ROOT = Path(__file__).resolve().parents[3]
SITE = REPO_ROOT / "docs" / "site"

#: FR-015's list, as directories.
REQUIRED_SECTIONS = (
    "quickstart",
    "deployment",
    "configuration",
    "capabilities",
    "integrations",
    "security",
    "evaluation",
    "contributing",
)


def _authored() -> list[Path]:
    """Return the pages a person wrote, which are the ones these rules apply to."""
    return test_doc_examples.documents(SITE)


# -- the sections exist (FR-015) ------------------------------------------------


def test_every_section_the_documentation_promises_exists() -> None:
    for section in REQUIRED_SECTIONS:
        assert (SITE / section / "index.md").is_file(), section


def test_the_site_index_links_to_every_section() -> None:
    index = (SITE / "index.md").read_text(encoding="utf-8")

    missing = [section for section in REQUIRED_SECTIONS if f"{section}/index.md" not in index]

    assert missing == []


# -- every example is checked (FR-020, SC-007) ----------------------------------


def test_every_documented_example_checks_out() -> None:
    """SC-007. The same sweep ``tools/test_doc_examples.py`` runs."""
    checked, problems = test_doc_examples.check(SITE)

    assert problems == []
    assert checked > 0, "no examples were found at all, which means the sweep proves nothing"


def test_the_sweep_would_catch_a_command_that_no_longer_exists(tmp_path: Path) -> None:
    """A negative test that never fires is a test that proves nothing."""
    page = tmp_path / "index.md"
    page.write_text("# x\n\n```sh\nninjasre teleport --now\n```\n", encoding="utf-8")

    _, problems = test_doc_examples.check(tmp_path)

    assert any("teleport" in problem for problem in problems)


def test_the_sweep_would_catch_a_make_target_that_went(tmp_path: Path) -> None:
    page = tmp_path / "index.md"
    page.write_text("# x\n\n```sh\nmake reticulate-splines\n```\n", encoding="utf-8")

    _, problems = test_doc_examples.check(tmp_path)

    assert any("reticulate-splines" in problem for problem in problems)


def test_the_sweep_would_catch_a_path_that_moved(tmp_path: Path) -> None:
    page = tmp_path / "index.md"
    page.write_text("# x\n\n```sh\ncat deploy/compose/nonexistent.yml\n```\n", encoding="utf-8")

    _, problems = test_doc_examples.check(tmp_path)

    assert any("nonexistent.yml" in problem for problem in problems)


def test_a_failing_python_example_is_reported(tmp_path: Path) -> None:
    page = tmp_path / "index.md"
    page.write_text("# x\n\n```python\nraise ValueError('nope')\n```\n", encoding="utf-8")

    _, problems = test_doc_examples.check(tmp_path)

    assert any("ValueError" in problem for problem in problems)


def test_an_illustrative_block_is_not_executed(tmp_path: Path) -> None:
    """A configuration snippet is not a program, and running it would be absurd."""
    page = tmp_path / "index.md"
    page.write_text(
        "# x\n\n```ini\nNINJASRE_LOG_LEVEL=DEBUG\n```\n\n```\nsome output\n```\n",
        encoding="utf-8",
    )

    checked, problems = test_doc_examples.check(tmp_path)

    assert (checked, problems) == (0, [])


# -- the quickstart stands alone (SC-006) ---------------------------------------


def test_the_quickstart_sends_nobody_anywhere_before_the_end() -> None:
    """SC-006: a new operator reaches a successful investigation using only this page."""
    text = (SITE / "quickstart" / "index.md").read_text(encoding="utf-8")
    body, _, _ = text.partition("## Where to go next")

    internal = [
        target
        for _, target in re.findall(r"\[([^\]]+)\]\(([^)]+)\)", body)
        if not target.startswith(("http://", "https://", "#"))
    ]

    assert internal == [], f"the quickstart needs another page before it finishes: {internal}"


def test_the_quickstart_reaches_a_finished_investigation() -> None:
    text = (SITE / "quickstart" / "index.md").read_text(encoding="utf-8")

    assert "docker compose up -d" in text
    assert "ninjasre doctor" in text
    assert "ninjasre investigate" in text


def test_the_quickstart_names_what_the_operator_needs_before_starting() -> None:
    text = (SITE / "quickstart" / "index.md").read_text(encoding="utf-8").lower()

    assert "docker" in text
    assert "api key" in text


# -- the security model names its threats (FR-021) ------------------------------


def test_the_security_model_covers_all_five_controls_with_their_threats() -> None:
    text = (SITE / "security" / "index.md").read_text(encoding="utf-8")

    for control in ("credential proxy", "Masking", "Guardrails", "Sandbox", "approval model"):
        assert control in text, control

    #: Five controls, each with the threat it addresses stated before the
    #: control. A control whose threat nobody can state is the first one
    #: somebody turns off.
    assert text.count("**The threat.**") >= 5
    assert text.count("**The control.**") >= 5


def test_the_security_model_says_what_it_does_not_defend_against() -> None:
    """A model that claims everything is one nobody believes."""
    text = (SITE / "security" / "index.md").read_text(encoding="utf-8")

    assert "not defended against" in text


# -- the evaluation methodology is reproducible (FR-022) ------------------------


def test_the_evaluation_page_gives_the_exact_commands() -> None:
    text = (SITE / "evaluation" / "index.md").read_text(encoding="utf-8")

    for command in (
        "make test-synthetic",
        "make evaluate",
        "make record-baseline",
        "make benchmark",
    ):
        assert command in text, command


def test_the_evaluation_page_names_the_baseline_a_reader_compares_against() -> None:
    text = (SITE / "evaluation" / "index.md").read_text(encoding="utf-8")

    assert "BASELINE" in text
    assert "ablation" in text.lower()


# -- the offline build (FR-019) -------------------------------------------------


def test_the_site_builds_into_a_directory_of_html(tmp_path: Path) -> None:
    written = build_docs.build(tmp_path)

    assert written
    assert (tmp_path / "index.html").is_file()
    assert (tmp_path / "site" / "quickstart" / "index.html").is_file()


def test_nothing_in_the_built_site_is_fetched_from_anywhere(tmp_path: Path) -> None:
    """FR-019, checked the only way worth checking: read the output.

    The property is about *fetches*, not about the string ``http``. A page may
    perfectly well quote a URL — a collector endpoint, a local model's base URL —
    and quoting one costs an air-gapped reader nothing. What costs them the page
    is a tag that goes and gets something, so the assertion is about tags.
    """
    build_docs.build(tmp_path)
    fetching = re.compile(r"<(?:script|link|img|iframe|source|video|audio|object|embed)\b")

    for page in tmp_path.rglob("*.html"):
        html = page.read_text(encoding="utf-8")
        assert not fetching.search(html), f"{page} pulls in an asset"
        assert "@import" not in html, page
        assert "url(" not in html, f"{page} references an asset from CSS"


def test_a_markdown_link_between_pages_becomes_a_link_between_pages(tmp_path: Path) -> None:
    build_docs.build(tmp_path)
    index = (tmp_path / "site" / "index.html").read_text(encoding="utf-8")

    assert 'href="quickstart/index.html"' in index
    assert '.md"' not in index


def test_the_build_does_not_publish_a_document_the_repository_ignores(
    tmp_path: Path,
) -> None:
    """A local note beside the documentation is not a page."""
    ignored = build_docs.ignored_documents()

    assert ignored is not None, "git could not report the ignored set"

    built = {path.relative_to(build_docs.DOCS_ROOT) for path in build_docs.sources(tmp_path)}
    forbidden = {path.relative_to(build_docs.DOCS_ROOT) for path in ignored}

    assert built & forbidden == set()


def test_rebuilding_removes_a_page_whose_source_went(tmp_path: Path) -> None:
    """A site serving a deleted page lies more confidently than a missing one."""
    build_docs.build(tmp_path)
    stale = tmp_path / "site" / "invented.html"
    stale.write_text("<html></html>", encoding="utf-8")

    build_docs.build(tmp_path)

    assert not stale.exists()


def test_the_renderer_handles_what_this_documentation_actually_uses() -> None:
    rendered = build_docs.render_markdown(
        "# Title\n\n"
        "A paragraph with `code`, **bold**, and a [link](other.md).\n\n"
        "- one\n- two\n\n"
        "1. first\n2. second\n\n"
        "| A | B |\n|---|---|\n| 1 | 2 |\n\n"
        "> A quote.\n\n"
        "```sh\nmake verify\n```\n"
    )

    assert "<h1>Title</h1>" in rendered
    assert "<code>code</code>" in rendered
    assert "<strong>bold</strong>" in rendered
    assert 'href="other.html"' in rendered
    assert "<ul><li>one</li><li>two</li></ul>" in rendered
    assert "<ol><li>first</li><li>second</li></ol>" in rendered
    assert "<table>" in rendered and "<th>A</th>" in rendered
    assert "<blockquote><p>A quote.</p></blockquote>" in rendered
    assert "<pre><code" in rendered


def test_emphasis_inside_a_code_span_is_left_alone() -> None:
    """``**kwargs`` in a code span is an argument list, not bold text."""
    rendered = build_docs.render_markdown("Pass `**kwargs` through.\n")

    assert "<code>**kwargs</code>" in rendered
    assert "<strong>" not in rendered


def test_a_generated_pages_banner_does_not_reach_the_reader() -> None:
    """It is an instruction to a contributor, not something a reader needs."""
    rendered = build_docs.render_markdown("<!-- Generated by something -->\n\n# Title\n")

    assert "Generated by" not in rendered


# -- llms.txt (T039) ------------------------------------------------------------


def test_llms_txt_ships_and_points_at_pages_that_exist() -> None:
    text = (REPO_ROOT / "llms.txt").read_text(encoding="utf-8")

    assert text.startswith("# NinjaSRE")
    assert text.splitlines()[2].startswith("> ")

    targets = [
        target
        for _, target in re.findall(r"\[([^\]]+)\]\(([^)]+)\)", text)
        if not target.startswith(("http://", "https://"))
    ]

    assert targets
    missing = [target for target in targets if not (REPO_ROOT / target).exists()]
    assert missing == []


def test_llms_txt_says_the_thing_that_distinguishes_this_project() -> None:
    text = (REPO_ROOT / "llms.txt").read_text(encoding="utf-8")

    assert "no telemetry" in text.lower()
    assert "self-hosted" in text.lower()


# -- translations (T040) ---------------------------------------------------------


def test_the_translation_structure_exists_with_english_as_the_source() -> None:
    readme = (SITE / "i18n" / "README.md").read_text(encoding="utf-8")

    assert (SITE / "i18n" / "locales.md").is_file()
    assert "English is the normative source" in readme
    assert "translated-from" in readme


def test_the_generated_reference_is_declared_untranslatable() -> None:
    """A translated copy of a generated page is stale the day after the next change."""
    readme = (SITE / "i18n" / "README.md").read_text(encoding="utf-8")

    assert "Not the generated reference" in readme
