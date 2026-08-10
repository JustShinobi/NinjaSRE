"""A commit message is text somebody wrote in a hurry, and it reaches the model.

The leak this closes is the obvious one and the one that actually happens: a
credential pasted into a commit message, or a path naming a secrets file, read
out of a repository and put into an investigation's trace — where it is stored,
rendered in a console, and sent to whichever model the deployment configured.

Nothing new is invented for it. A change passes the same guardrail ruleset a
synced document passes, which is what keeps "what counts as a secret" one
decision rather than one per ingestion path. What is different is the response:
a document carrying a secret is refused, because the corpus is better off
without it, and a *change* carrying one is redacted and kept, because the change
is the evidence and dropping it would blind the investigation to the apply that
caused the outage.

The rule that fired travels with the change, so a reader can tell a message that
was redacted from one that happened to contain the word ``[REDACTED]``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from platform.changes.infra_apply import InfraApplySource
from platform.changes.models import Change, ChangeWindow
from platform.changes.screening import screen, screen_all

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 1, 15, 0, tzinfo=UTC)

#: A credential shape the shipped ruleset redacts, spelled the way one arrives:
#: in a message somebody wrote while rotating it. Not a real key.
LEAKED_KEY = "AKIAIOSFODNN7EXAMPLE"


def _change(*, message: str = "feat(monitoring): tidy up", paths: tuple[str, ...] = ()) -> Change:
    return Change(
        change_id="9f2c1ab",
        occurred_at=NOW,
        author="erik",
        message=message,
        paths=paths,
        source="infra_apply",
        component="monitoring",
    )


def test_a_message_carrying_a_credential_shape_comes_back_without_it() -> None:
    screened = screen(_change(message=f"fix(monitoring): rotate {LEAKED_KEY} out of the exporter"))

    assert LEAKED_KEY not in screened.message
    assert "rotate" in screened.message


def test_the_rule_that_fired_is_named_on_the_change() -> None:
    screened = screen(_change(message=f"fix(monitoring): rotate {LEAKED_KEY}"))

    assert screened.redactions == ("aws-access-key-id",)


def test_a_change_carrying_nothing_sensitive_is_returned_unchanged() -> None:
    original = _change(paths=("services/monitoring/stack/values.yaml",))

    screened = screen(original)

    assert screened is original
    assert screened.redactions == ()


def test_a_path_is_screened_too_because_a_path_is_text_from_the_same_place() -> None:
    screened = screen(_change(paths=(f"services/monitoring/{LEAKED_KEY}.tfvars",)))

    assert all(LEAKED_KEY not in path for path in screened.paths)
    assert screened.redactions == ("aws-access-key-id",)


def test_the_change_survives_its_own_redaction_rather_than_being_dropped() -> None:
    # The difference from document ingestion, and it is deliberate. A corpus is
    # better off without a document carrying a secret; an investigation is not
    # better off blind to the apply that caused the outage.
    screened = screen(_change(message=f"fix(monitoring): rotate {LEAKED_KEY}"))

    assert screened.change_id == "9f2c1ab"
    assert screened.author == "erik"
    assert screened.component == "monitoring"
    assert screened.occurred_at == NOW


def test_screening_a_set_keeps_its_order() -> None:
    first = _change(message="first")
    second = _change(message=f"second {LEAKED_KEY}")

    screened = screen_all([first, second])

    assert [entry.message.split()[0] for entry in screened] == ["first", "second"]


def test_screening_is_idempotent_so_a_second_pass_names_no_new_rule() -> None:
    once = screen(_change(message=f"fix(monitoring): rotate {LEAKED_KEY}"))
    twice = screen(once)

    assert twice.message == once.message
    assert twice.redactions == once.redactions


@pytest.mark.asyncio
async def test_the_source_screens_before_anything_can_read_the_change(tmp_path: Path) -> None:
    # The assertion that matters: screening is not something a caller has to
    # remember. A change that has left a source has already been through it.
    state = tmp_path / ".infra-state"
    state.mkdir()
    (state / "monitoring.json").write_text(
        '{"component": "monitoring", "applies": [{"revision": "9f2c1ab", '
        '"committed_at": "2026-08-01T14:00:00Z", "applied_at": "2026-08-01T14:05:00Z", '
        f'"author": "erik", "message": "fix(monitoring): rotate {LEAKED_KEY}"}}]}}',
        encoding="utf-8",
    )

    found = await InfraApplySource(root=tmp_path).changes_in(ChangeWindow.ending(NOW))

    assert len(found) == 1
    assert LEAKED_KEY not in found[0].message
    assert found[0].redactions == ("aws-access-key-id",)
