"""The browser harness's ports: pinned when free, never shared, never collided.

The suite itself is not exercised here — it needs a build, a browser and two
servers, and that is what ``make console-e2e`` is. What is exercised is the one
piece of the harness that was quietly wrong under concurrency.

A fixed port is not merely inconvenient when two checkouts run at once. The
harness waits for *something* to answer on the port before it starts the browser,
and something does answer: the other checkout's console. Its own server has
already died with ``EADDRINUSE``, the wait succeeded against a stranger, and the
suite then reports on a build that is not in this working tree — which is how a
green run and a red run stop meaning anything.
"""

from __future__ import annotations

import contextlib
import socket
import subprocess
from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest

from config.constants.console import CONSOLE_E2E_MOCK_PORT, CONSOLE_E2E_PORT
from tools import console_e2e
from tools.console_e2e import ports
from tools.console_toolchain import Toolchain

pytestmark = pytest.mark.unit


@contextlib.contextmanager
def _taken() -> Iterator[int]:
    """Hold a listener on some port, the way another checkout's run would.

    The kernel picks it, rather than the test claiming a pinned one. A test that
    binds 8423 to prove something about 8423 fails on the very machine this is
    about — one already running the suite from another checkout — and a test
    that goes red when the situation it describes actually occurs is worse than
    no test.
    """
    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        holder.bind(("127.0.0.1", 0))
        holder.listen(1)
        yield holder.getsockname()[1]
    finally:
        holder.close()


def _is_free(port: int) -> bool:
    """Return whether ``port`` can still be bound on loopback."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def test_a_free_port_is_handed_back_exactly_as_it_was_asked_for() -> None:
    """A lone machine still gets 8423 and 8424, which is what the config documents.

    Asserted against a port this test has just proved free rather than against
    the constants themselves, so it says the same thing on a machine that is
    running the suite from another checkout — where the constants are precisely
    what is *not* available, and where a test that bound them would fail for
    agreeing with the code.
    """
    with _taken() as released:
        pass  # Closed on the way out, so this is a port known bindable just now.

    assert ports(released) == (released,)


def test_a_port_another_run_is_holding_is_replaced_rather_than_collided_with() -> None:
    """The second checkout gets a console of its own, not somebody else's."""
    with _taken() as held:
        (chosen,) = ports(held)

    assert chosen != held


def test_a_replacement_port_is_one_that_can_actually_be_bound() -> None:
    """An address nobody can serve on would only move the failure."""
    with _taken() as held:
        (chosen,) = ports(held)

    assert _is_free(chosen)


def test_two_servers_in_one_run_are_never_handed_the_same_port() -> None:
    """Every port is reserved before any is returned, so the fallbacks differ.

    The console and the data plane behind it are both replaced when both pinned
    ports are taken, and handing them one number would trade a collision with
    another checkout for a collision with ourselves.
    """
    with _taken() as one, _taken() as two:
        mock, console = ports(one, two)

    assert mock != console
    assert {mock, console}.isdisjoint({one, two})


def test_one_port_is_returned_for_each_one_asked_for() -> None:
    """In order, because the caller unpacks them positionally."""
    assert len(ports(CONSOLE_E2E_MOCK_PORT, CONSOLE_E2E_PORT)) == 2
    assert ports() == ()


def test_the_compose_backing_builds_the_images_it_is_about_to_run() -> None:
    """A stack brought up from a stale image tests code nobody has in their tree.

    ``docker compose up`` reuses an existing image rather than rebuilding it, so
    a backing that only brought the stack up would serve whatever the image was
    built from — which is the same failure as a gate that reports success
    without doing the work, and harder to notice because the result looks like
    a real answer about the current code.

    Asserted against the command itself rather than by starting anything, so
    this runs on a machine with no container runtime.
    """
    source = Path(console_e2e.__file__).read_text(encoding="utf-8")
    start = source.index("def compose_stack(")
    end = source.index("\ndef ", start)
    body = source[start:end]

    assert '"build"' in body, (
        "the compose backing brings the stack up without rebuilding what it is about to run"
    )

    built = next(line for line in body.splitlines() if '"build"' in line)

    # The database is not in the rebuild set on purpose: its image carries none
    # of this repository's source and builds by fetching an extension over the
    # network, so rebuilding it every run would fail the whole backing on a
    # machine that cannot reach the download.
    assert "_SOURCE_SERVICES" in built, built.strip()
    assert console_e2e._SOURCE_SERVICES == ("app", "console", "proxy")


# --- The staging backing: brings nothing up, refuses loudly -----------------
#
# `run_staging` does not exist yet when these land — that is the point.
# The refusals have to be proved red before the backing works at all, so a
# refusal that silently stopped refusing would fail one of these rather than
# being noticed by a person three weeks later.


def test_the_staging_backing_refuses_without_a_credential_and_never_provisions_anything(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing credential is a named refusal before a browser is touched.

    `resolve` and `ensure_browsers` are replaced with a function that fails
    the test if it is ever called — proving the credential is checked before
    either has a chance to run, rather than a run that downloads a browser
    and a toolchain only to fail on a sign-in fifteen seconds later.
    """
    from config.constants.console import (
        NINJASRE_STAGING_CREDENTIAL_ENV,
        NINJASRE_STAGING_USERNAME_ENV,
    )

    monkeypatch.delenv(NINJASRE_STAGING_CREDENTIAL_ENV, raising=False)
    monkeypatch.setenv(NINJASRE_STAGING_USERNAME_ENV, "operator")

    def _must_not_run(*_args: object, **_kwargs: object) -> None:
        pytest.fail("a browser was provisioned before the credential was checked")

    monkeypatch.setattr(console_e2e, "resolve", _must_not_run)
    monkeypatch.setattr(console_e2e, "ensure_browsers", _must_not_run)

    with pytest.raises(console_e2e.HarnessError, match=NINJASRE_STAGING_CREDENTIAL_ENV):
        console_e2e.run_staging()


def test_the_staging_backing_refuses_without_a_username_and_never_provisions_anything(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The username is checked by the same rule, before a browser is touched."""
    from config.constants.console import (
        NINJASRE_STAGING_CREDENTIAL_ENV,
        NINJASRE_STAGING_USERNAME_ENV,
    )

    monkeypatch.delenv(NINJASRE_STAGING_USERNAME_ENV, raising=False)
    monkeypatch.setenv(NINJASRE_STAGING_CREDENTIAL_ENV, "does-not-matter")

    def _must_not_run(*_args: object, **_kwargs: object) -> None:
        pytest.fail("a browser was provisioned before the credential was checked")

    monkeypatch.setattr(console_e2e, "resolve", _must_not_run)
    monkeypatch.setattr(console_e2e, "ensure_browsers", _must_not_run)

    with pytest.raises(console_e2e.HarnessError, match=NINJASRE_STAGING_USERNAME_ENV):
        console_e2e.run_staging()


def test_the_staging_backing_starts_no_data_plane_no_local_console_and_builds_nothing() -> None:
    """`run_staging` never calls any of the three bring-up paths the other backings use.

    Asserted against the function's own source, the same way
    `test_the_compose_backing_builds_the_images_it_is_about_to_run` proves
    what a backing does without spending a real run on it: this backing's
    whole reason to exist is that it starts nothing, and a source that never
    names `mock_plane`, `compose_stack`, or the local `console` server proves
    that structurally rather than by hoping a live run happens to agree.
    """
    source = Path(console_e2e.__file__).read_text(encoding="utf-8")
    start = source.index("def run_staging(")
    end = source.index("\ndef ", start)
    body = source[start:end]

    for forbidden in ("mock_plane(", "compose_stack(", "console(toolchain"):
        assert forbidden not in body, (
            f"run_staging calls {forbidden!r}, which brings something up — "
            "the staging backing must point at what is already running"
        )


def test_the_staging_backing_always_selects_only_the_tests_marked_safe_for_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The safe-for-staging tag is applied to every staging run, never optional.

    The claim this proves — a test not marked safe does not run against this
    backing even when it is named explicitly — holds only if the grep filter
    is unconditional. Proved here against the constructed Playwright
    arguments, with `playwright()` itself replaced so no browser is actually
    launched.
    """
    from config.constants.console import (
        CONSOLE_STAGING_SAFE_TAG,
        NINJASRE_STAGING_CREDENTIAL_ENV,
        NINJASRE_STAGING_USERNAME_ENV,
    )

    monkeypatch.setenv(NINJASRE_STAGING_USERNAME_ENV, "operator")
    monkeypatch.setenv(NINJASRE_STAGING_CREDENTIAL_ENV, "does-not-matter")
    monkeypatch.setattr(console_e2e, "resolve", lambda *_a, **_k: object())
    monkeypatch.setattr(console_e2e, "ensure_browsers", lambda *_a, **_k: None)
    monkeypatch.setattr(console_e2e, "_staging_credential", lambda *_a, **_k: "tok-exchanged")

    captured: dict[str, object] = {}

    def _fake_playwright(
        _toolchain: object,
        _project: str,
        _base_url: str,
        *,
        credential: str | None = None,
        evidence_dir: Path | None = None,
        extra: Sequence[str] = (),
    ) -> int:
        captured["extra"] = tuple(extra)
        captured["credential"] = credential
        captured["evidence_dir"] = evidence_dir
        return 0

    monkeypatch.setattr(console_e2e, "playwright", _fake_playwright)

    # Named explicitly, the way a caller who wants "just this one" would ask —
    # the tag filter has to govern this just the same.
    status = console_e2e.run_staging(extra=["tests/e2e/some-other.spec.ts"])

    assert status == 0
    extra = captured["extra"]
    assert isinstance(extra, tuple)
    assert any(CONSOLE_STAGING_SAFE_TAG in part for part in extra), (
        f"no grep for {CONSOLE_STAGING_SAFE_TAG!r} in the constructed arguments: {extra!r}"
    )
    # The password never reaches this point: what `playwright()` was handed
    # is the exchanged token from the stubbed `_staging_credential`.
    assert captured["credential"] == "tok-exchanged"


# --- Regression: `--evidence-dir` has to reach the subprocess's own environment,
# not just the Playwright `--output` flag -----------------------------------
#
# `NINJASRE_STAGING_EVIDENCE_DIR` set directly in the environment produced ten
# captures; `--evidence-dir` on the command line produced zero, silently, exit
# 0 — the same failure shape any marker with two spellings has: it selects
# zero tests and reports success, which is the worst result available. Here
# it was zero captures reporting success. The cause: `run_staging` only ever
# threaded the resolved directory into `--output=`, which is Playwright's own
# artifact directory — unrelated to `process.env.NINJASRE_STAGING_EVIDENCE_DIR`,
# the one thing `transversal-rules.spec.ts`'s `afterEach` actually reads.


def test_playwright_puts_the_evidence_directory_in_the_subprocess_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`playwright(..., evidence_dir=...)` exports the same-named variable.

    Proved against the constructed ``subprocess.run`` call directly — the
    only place that decides what the Playwright process actually sees —
    rather than against a stub of ``playwright()`` itself, which is what let
    the gap between ``--output`` and the environment variable go unnoticed:
    every existing test stubbed `playwright()` and never looked inside it.
    """
    from config.constants.console import NINJASRE_STAGING_EVIDENCE_DIR_ENV

    captured: dict[str, object] = {}

    def _fake_run(
        _command: object,
        *,
        cwd: object = None,
        env: dict[str, str] | None = None,
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[bytes]:
        captured["env"] = dict(env) if env is not None else {}
        return subprocess.CompletedProcess(args=[], returncode=0)

    monkeypatch.setattr(subprocess, "run", _fake_run)
    toolchain = Toolchain(
        node=Path("/usr/bin/node"), npm=Path("/usr/bin/npm"), pnpm=Path("/usr/bin/pnpm")
    )

    console_e2e.playwright(
        toolchain,
        "behaviour",
        "https://stg.example",
        evidence_dir=Path("/tmp/evidence-example"),
    )

    env = captured["env"]
    assert isinstance(env, dict)
    assert env.get(NINJASRE_STAGING_EVIDENCE_DIR_ENV) == "/tmp/evidence-example", (
        f"{NINJASRE_STAGING_EVIDENCE_DIR_ENV} did not reach the subprocess environment: "
        f"{env.get(NINJASRE_STAGING_EVIDENCE_DIR_ENV)!r}"
    )


def test_run_staging_threads_the_resolved_evidence_directory_into_playwright(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The directory `run_staging` resolves is the one `playwright()` receives.

    Whether it came from the `evidence_dir` parameter (the CLI's
    `--evidence-dir`) or the environment fallback, `run_staging` must hand it
    to `playwright()` by the same keyword `playwright()` actually exports —
    not fold it into `extra` as a Playwright CLI flag, which is what reached
    `--output` and nothing else.
    """
    from config.constants.console import (
        NINJASRE_STAGING_CREDENTIAL_ENV,
        NINJASRE_STAGING_USERNAME_ENV,
    )

    monkeypatch.setenv(NINJASRE_STAGING_USERNAME_ENV, "operator")
    monkeypatch.setenv(NINJASRE_STAGING_CREDENTIAL_ENV, "does-not-matter")
    monkeypatch.setattr(console_e2e, "resolve", lambda *_a, **_k: object())
    monkeypatch.setattr(console_e2e, "ensure_browsers", lambda *_a, **_k: None)
    monkeypatch.setattr(console_e2e, "_staging_credential", lambda *_a, **_k: "tok-exchanged")

    captured: dict[str, object] = {}

    def _fake_playwright(
        _toolchain: object,
        _project: str,
        _base_url: str,
        *,
        credential: str | None = None,
        extra: Sequence[str] = (),
        evidence_dir: Path | None = None,
    ) -> int:
        captured["extra"] = tuple(extra)
        captured["evidence_dir"] = evidence_dir
        return 0

    monkeypatch.setattr(console_e2e, "playwright", _fake_playwright)

    status = console_e2e.run_staging(evidence_dir=Path("/tmp/evidence-example"))

    assert status == 0
    assert captured["evidence_dir"] == Path("/tmp/evidence-example")
    extra = captured["extra"]
    assert isinstance(extra, tuple)
    assert not any("--output" in part for part in extra), (
        f"--output does nothing for evidence capture and only disguises the "
        f"gap by depositing .last-run.json where a capture is expected: {extra!r}"
    )
