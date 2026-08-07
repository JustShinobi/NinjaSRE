"""Render the documentation into a directory of HTML that works with no network.

"Offline" is the requirement and it is stricter than it sounds. A static site
generator that produces one `<script src="https://...">` is a site that is blank
on an air-gapped host, and an operator running NinjaSRE air-gapped is exactly the
operator most likely to need the documentation. So the renderer is here, in the
standard library, and the output has no external asset of any kind: no CDN, no
font, no analytics, no search index fetched at load.

The Markdown subset is the one this documentation actually uses — headings,
paragraphs, fenced code, lists, tables, block quotes, horizontal rules, and the
inline forms. A dialect nobody writes in is a dialect nobody notices is missing,
and a full CommonMark implementation is a dependency this does not need.

Links between pages are rewritten from ``.md`` to ``.html`` so the built tree
navigates the same way the source does.

Usage::

    python -m tools.build_docs [--into docs/site/build] [--serve] [--port 8000]

``--serve`` binds to loopback only. A documentation server reachable from the
network is one somebody leaves running.
"""

from __future__ import annotations

import argparse
import html
import http.server
import re
import shutil
import socketserver
import subprocess
from collections.abc import Sequence
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_ROOT = REPO_ROOT / "docs"
SITE_ROOT = DOCS_ROOT / "site"
DEFAULT_OUTPUT = SITE_ROOT / "build"

#: Bound to loopback. See the module docstring.
SERVE_HOST = "127.0.0.1"
DEFAULT_PORT = 8000

#: One stylesheet, inlined into every page. Inlined rather than linked because a
#: second file is a second thing that can fail to copy, and this one is smaller
#: than the request that would fetch it.
STYLESHEET = """
:root { color-scheme: light dark; --ink: #16181d; --paper: #fbfbfa; --muted: #5a6070;
        --rule: #d8dae0; --accent: #1f5f8b; --code: #f0f0ee; }
@media (prefers-color-scheme: dark) {
  :root { --ink: #e6e8ec; --paper: #16181d; --muted: #9aa2b1;
          --rule: #2c3038; --accent: #7db4dd; --code: #1f232b; } }
* { box-sizing: border-box; }
body { margin: 0; background: var(--paper); color: var(--ink);
       font: 16px/1.65 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
.layout { display: flex; align-items: flex-start; max-width: 1180px; margin: 0 auto; }
nav { flex: 0 0 15rem; padding: 2rem 1rem; border-right: 1px solid var(--rule);
      position: sticky; top: 0; max-height: 100vh; overflow-y: auto; }
nav h2 { font-size: .72rem; letter-spacing: .09em; text-transform: uppercase;
         color: var(--muted); margin: 1.4rem 0 .4rem; }
nav ul { list-style: none; margin: 0; padding: 0; }
nav a { display: block; padding: .18rem 0; color: var(--ink); text-decoration: none; }
nav a:hover, nav a:focus { color: var(--accent); text-decoration: underline; }
main { flex: 1 1 auto; padding: 2rem 2.5rem 6rem; min-width: 0; }
h1, h2, h3, h4 { line-height: 1.25; }
h1 { font-size: 2rem; margin-top: 0; }
h2 { margin-top: 2.2rem; border-bottom: 1px solid var(--rule); padding-bottom: .3rem; }
a { color: var(--accent); }
code { background: var(--code); padding: .12em .35em; border-radius: 3px;
       font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .9em; }
pre { background: var(--code); padding: 1rem; border-radius: 5px; overflow-x: auto; }
pre code { background: none; padding: 0; }
blockquote { margin: 1.2rem 0; padding: .1rem 1rem; border-left: 3px solid var(--accent);
             color: var(--muted); }
table { border-collapse: collapse; width: 100%; margin: 1.2rem 0; display: block;
        overflow-x: auto; }
th, td { border: 1px solid var(--rule); padding: .45rem .7rem; text-align: left;
         vertical-align: top; }
th { background: var(--code); }
hr { border: 0; border-top: 1px solid var(--rule); margin: 2rem 0; }
footer { color: var(--muted); font-size: .85rem; border-top: 1px solid var(--rule);
         margin-top: 3rem; padding-top: 1rem; }
"""

#: The site's own sections, in reading order, and the reference notes after them.
NAVIGATION: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    (
        "Start here",
        (("Overview", "site/index.md"), ("Quickstart", "site/quickstart/index.md")),
    ),
    (
        "Running it",
        (
            ("Deployment", "site/deployment/index.md"),
            ("Configuration", "site/configuration/index.md"),
            ("Security", "site/security/index.md"),
        ),
    ),
    (
        "What it can do",
        (
            ("Capabilities", "site/capabilities/index.md"),
            ("Integrations", "site/integrations/index.md"),
        ),
    ),
    (
        "Whether it works",
        (("Evaluation", "site/evaluation/index.md"),),
    ),
    (
        "Changing it",
        (
            ("Contributing", "site/contributing/index.md"),
            ("Translations", "site/i18n/README.md"),
        ),
    ),
    (
        "Reference notes",
        (
            ("Architecture", "architecture.md"),
            ("Vision", "vision.md"),
            ("Roadmap", "roadmap.md"),
            ("Evaluation and ablation", "evaluation-methodology.md"),
            ("Integration framework", "integration-framework.md"),
            ("Guardrails and masking", "guardrails-and-masking.md"),
        ),
    ),
)


# -- Markdown ------------------------------------------------------------------

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_UNORDERED = re.compile(r"^\s*[-*]\s+(.*)$")
_ORDERED = re.compile(r"^\s*\d+\.\s+(.*)$")
_TABLE_RULE = re.compile(r"^\s*\|?[\s:|-]+\|[\s:|-]*$")
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)

_CODE_SPAN = re.compile(r"`([^`]+)`")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_ITALIC = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")


def _inline(text: str) -> str:
    """Return one line of Markdown as HTML, code spans protected from the rest.

    Code spans are extracted first and put back last. Rendering emphasis inside
    one would turn ``**kwargs`` in a code span into bold text, which is the sort
    of bug that only shows up in the page nobody re-read.
    """
    spans: list[str] = []

    def stash(match: re.Match[str]) -> str:
        spans.append(f"<code>{html.escape(match.group(1))}</code>")
        return f"\x00{len(spans) - 1}\x00"

    protected = _CODE_SPAN.sub(stash, text)
    escaped = html.escape(protected, quote=False)
    escaped = _LINK.sub(
        lambda match: (
            f'<a href="{html.escape(_rewrite(match.group(2)), quote=True)}">{match.group(1)}</a>'
        ),
        escaped,
    )
    escaped = _BOLD.sub(r"<strong>\1</strong>", escaped)
    escaped = _ITALIC.sub(r"<em>\1</em>", escaped)
    return re.sub(r"\x00(\d+)\x00", lambda match: spans[int(match.group(1))], escaped)


def _rewrite(target: str) -> str:
    """Return a link target with a Markdown page rewritten to its built page."""
    if target.startswith(("http://", "https://", "#", "mailto:")):
        return target
    path, _, fragment = target.partition("#")
    if path.endswith(".md"):
        path = f"{path[:-3]}.html"
    return f"{path}#{fragment}" if fragment else path


def _row(line: str) -> list[str]:
    """Return one table row's cells."""
    stripped = line.strip().strip("|")
    return [cell.strip() for cell in stripped.split("|")]


def render_markdown(text: str) -> str:
    """Return ``text`` as the HTML body of one page."""
    lines = _COMMENT.sub("", text).splitlines()
    out: list[str] = []
    index = 0

    while index < len(lines):
        line = lines[index]

        if line.startswith("```"):
            language = line[3:].strip()
            index += 1
            block: list[str] = []
            while index < len(lines) and not lines[index].startswith("```"):
                block.append(lines[index])
                index += 1
            index += 1
            attribute = f' class="language-{html.escape(language, quote=True)}"' if language else ""
            out.append(f"<pre><code{attribute}>{html.escape(chr(10).join(block))}</code></pre>")
            continue

        heading = _HEADING.match(line)
        if heading:
            level = len(heading.group(1))
            out.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
            index += 1
            continue

        if line.strip() in {"---", "***", "___"}:
            out.append("<hr>")
            index += 1
            continue

        if "|" in line and index + 1 < len(lines) and _TABLE_RULE.match(lines[index + 1]):
            header = _row(line)
            index += 2
            body: list[list[str]] = []
            while index < len(lines) and "|" in lines[index] and lines[index].strip():
                body.append(_row(lines[index]))
                index += 1
            head = "".join(f"<th>{_inline(cell)}</th>" for cell in header)
            rows = "".join(
                "<tr>" + "".join(f"<td>{_inline(cell)}</td>" for cell in row) + "</tr>"
                for row in body
            )
            out.append(f"<table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table>")
            continue

        if _UNORDERED.match(line) or _ORDERED.match(line):
            ordered = _ORDERED.match(line) is not None
            pattern = _ORDERED if ordered else _UNORDERED
            items: list[str] = []
            while index < len(lines) and (match := pattern.match(lines[index])):
                collected = [match.group(1)]
                index += 1
                # A continuation is an indented line that is not itself an item.
                while (
                    index < len(lines)
                    and lines[index].startswith("  ")
                    and lines[index].strip()
                    and not pattern.match(lines[index])
                ):
                    collected.append(lines[index].strip())
                    index += 1
                items.append(f"<li>{_inline(' '.join(collected))}</li>")
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>{''.join(items)}</{tag}>")
            continue

        if line.startswith(">"):
            quoted: list[str] = []
            while index < len(lines) and lines[index].startswith(">"):
                quoted.append(lines[index].lstrip(">").strip())
                index += 1
            out.append(f"<blockquote><p>{_inline(' '.join(quoted))}</p></blockquote>")
            continue

        if not line.strip():
            index += 1
            continue

        paragraph: list[str] = []
        while index < len(lines) and lines[index].strip() and not _starts_block(lines[index]):
            paragraph.append(lines[index].strip())
            index += 1
        if paragraph:
            out.append(f"<p>{_inline(' '.join(paragraph))}</p>")

    return "\n".join(out)


def _starts_block(line: str) -> bool:
    """Return whether ``line`` begins something that is not a paragraph."""
    return bool(
        line.startswith(("```", ">", "|"))
        or _HEADING.match(line)
        or _UNORDERED.match(line)
        or _ORDERED.match(line)
        or line.strip() in {"---", "***", "___"}
    )


# -- the page and the tree -------------------------------------------------------


def _title(text: str, fallback: str) -> str:
    """Return a page's first level-one heading, or ``fallback``."""
    for line in text.splitlines():
        heading = _HEADING.match(line)
        if heading and len(heading.group(1)) == 1:
            return heading.group(2).strip()
    return fallback


def _navigation(depth: int) -> str:
    """Return the sidebar, with every link relative to a page ``depth`` deep."""
    up = "../" * depth
    sections: list[str] = []
    for heading, entries in NAVIGATION:
        links = "".join(
            f'<li><a href="{up}{_rewrite(target)}">{html.escape(label)}</a></li>'
            for label, target in entries
        )
        sections.append(f"<h2>{html.escape(heading)}</h2><ul>{links}</ul>")
    return f"<nav>{''.join(sections)}</nav>"


def _page(title: str, body: str, depth: int) -> str:
    """Return one whole HTML document."""
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{html.escape(title)} — NinjaSRE</title>\n"
        f"<style>{STYLESHEET}</style>\n</head>\n<body>\n"
        f'<div class="layout">{_navigation(depth)}<main>{body}'
        "<footer>Built from this repository by <code>tools/build_docs.py</code>. "
        "Nothing on this page is fetched from anywhere.</footer>"
        "</main></div>\n</body>\n</html>\n"
    )


def ignored_documents() -> frozenset[Path] | None:
    """Return the documents this repository ignores, or ``None`` when git cannot say.

    A build is a publication, and a file the repository deliberately ignores is
    a local note — something an author keeps beside the documentation and does
    not ship. Publishing it because it happened to be in the directory is how a
    private file becomes a page.

    Ignored rather than untracked, so a page somebody has just written and not
    yet committed still builds. No name appears here for either rule to hold.
    """
    try:
        completed = subprocess.run(  # noqa: S603 — fixed argument list, no shell
            [  # noqa: S607 — resolved from PATH
                "git",
                "ls-files",
                "-z",
                "--others",
                "--ignored",
                "--exclude-standard",
                "--",
                "docs",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            check=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return frozenset(
        REPO_ROOT / name for name in completed.stdout.split("\0") if name.endswith(".md")
    )


def sources(output: Path) -> list[Path]:
    """Return every Markdown page the site is built from.

    Without git — a source tarball, say — only ``docs/site/`` is built. Fewer
    pages is the safe way to be wrong here; publishing an ignored one is not.
    """
    ignored = ignored_documents()
    candidates = [
        path
        for path in sorted(DOCS_ROOT.rglob("*.md"))
        if output not in path.parents and "build" not in path.relative_to(DOCS_ROOT).parts
    ]
    if ignored is None:
        return [path for path in candidates if SITE_ROOT in path.parents]
    return [path for path in candidates if path not in ignored]


def build(output: Path = DEFAULT_OUTPUT) -> list[Path]:
    """Render every page into ``output`` and return what was written.

    The output directory is emptied first. A stale page from a document that has
    since been deleted is a page somebody can still reach, and a documentation
    site that serves a deleted page is one that is lying more confidently than a
    missing one would.
    """
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / ".gitignore").write_text("*\n!.gitignore\n", encoding="utf-8")

    written: list[Path] = []
    for path in sources(output):
        relative = path.relative_to(DOCS_ROOT).with_suffix(".html")
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        text = path.read_text(encoding="utf-8")
        destination.write_text(
            _page(
                _title(text, relative.stem),
                render_markdown(text),
                depth=len(relative.parts) - 1,
            ),
            encoding="utf-8",
            newline="\n",
        )
        written.append(destination)

    #: The site's own overview is also the root of the built tree, so opening
    #: the directory lands on it rather than on a file listing. Rendered again
    #: at depth zero rather than copied: the sidebar's links are relative, and a
    #: copy would carry one page's ``../`` prefixes into another page's depth.
    overview = SITE_ROOT / "index.md"
    if overview in sources(output):
        text = overview.read_text(encoding="utf-8")
        (output / "index.html").write_text(
            _page(_title(text, "NinjaSRE"), render_markdown(_reroot(text)), depth=0),
            encoding="utf-8",
            newline="\n",
        )
    return written


def _reroot(text: str) -> str:
    """Return the overview's links as they read from the root of the built tree.

    The page lives at ``site/index.md`` and its links are relative to there. The
    root copy is one level up, so every one of them gains a ``site/`` prefix.
    """
    return _LINK.sub(
        lambda match: (
            f"[{match.group(1)}]({match.group(2)})"
            if match.group(2).startswith(("http://", "https://", "#", "mailto:", "../"))
            else f"[{match.group(1)}](site/{match.group(2)})"
        ),
        text,
    )


def serve(output: Path, port: int) -> None:
    """Serve the built site on loopback until interrupted."""
    handler = _handler_for(output)
    with socketserver.TCPServer((SERVE_HOST, port), handler) as server:
        print(f"serving {output} at http://{SERVE_HOST}:{port}/site/  (Ctrl+C to stop)")  # noqa: T201
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")  # noqa: T201


def _handler_for(directory: Path) -> type[http.server.SimpleHTTPRequestHandler]:
    """Return a handler rooted at ``directory`` and silent about every request."""

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *arguments: object, **keywords: object) -> None:
            super().__init__(*arguments, directory=str(directory), **keywords)  # type: ignore[arg-type]

        def log_message(self, format: str, *args: object) -> None:
            """Say nothing. A documentation server is not a thing to watch."""

    return Handler


def main(argv: Sequence[str] | None = None) -> int:
    """Build the site, and optionally serve it."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--into", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--serve", action="store_true", help="serve the build on loopback")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    arguments = parser.parse_args(argv)

    written = build(arguments.into)
    print(f"built {len(written)} page(s) into {arguments.into}")  # noqa: T201

    if arguments.serve:
        serve(arguments.into, arguments.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
