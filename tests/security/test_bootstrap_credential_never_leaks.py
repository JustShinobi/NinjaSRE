"""SC-003. The bootstrap credential is in the file, in the terminal, and nowhere else.

A credential printed once and then forgotten is only forgotten if nothing wrote
it down on the way past. Three places do the writing in this platform — the
structured log, the audit trail, and an exception's own message — so the sweep
covers all three, over the whole of the credential's life: issued, reused,
presented, refused, spent.

The sweep looks for the secret itself rather than for a pattern. A test that
asserted "no string matching ``nsr_``" would pass against a log line that
carried the credential base64-encoded, and that is not the property FR-004
describes.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path

import pytest

from config.constants.first_run import DEFAULT_ORGANISATION_ID, NINJASRE_STATE_DIR_ENV
from platform.identity.errors import TokenRejected
from platform.identity.tokens import TokenService
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports.transaction import TenantScope
from platform.startup.bootstrap import (
    announcement,
    bring_up,
    credential_path,
    establish_durable_credential,
)

pytestmark = pytest.mark.security


@pytest.fixture
def environ(tmp_path: Path) -> dict[str, str]:
    return {NINJASRE_STATE_DIR_ENV: str(tmp_path / "state")}


@pytest.fixture
def captured_logs(caplog: pytest.LogCaptureFixture) -> Iterator[pytest.LogCaptureFixture]:
    """Capture everything every logger emits, at every level.

    At ``NOTSET`` on the root, so a debug line added later is swept too. A sweep
    that only read ``INFO`` would pass the day somebody logged the credential
    while debugging why it did not work.
    """
    with caplog.at_level(logging.NOTSET):
        yield caplog


def _log_text(caplog: pytest.LogCaptureFixture) -> str:
    """Return everything that was logged, message and structured payload alike."""
    parts: list[str] = [caplog.text]
    for record in caplog.records:
        parts.append(str(record.getMessage()))
        parts.append(repr(getattr(record, "__dict__", {})))
    return "\n".join(parts)


async def _audit_text(store: FakePersistence) -> str:
    """Return every audit event in the store, as the export would render it."""
    async with store.begin(TenantScope(org_id=DEFAULT_ORGANISATION_ID)) as uow:
        events = await uow.audit.query()
    return json.dumps(
        [
            {
                "action": event.action,
                "actor_id": event.actor_id,
                "resource_id": event.resource_id,
                "detail": dict(event.detail),
            }
            for event in events
        ],
        default=str,
    )


async def test_issuing_the_credential_writes_it_to_no_log_and_no_audit_event(
    environ: dict[str, str], captured_logs: pytest.LogCaptureFixture
) -> None:
    store = FakePersistence()
    tokens = TokenService(gateway=store)

    result = await bring_up(store, tokens, environ=environ)
    secret = result.credential.secret

    assert secret not in _log_text(captured_logs)
    assert secret not in await _audit_text(store)


async def test_a_second_bring_up_that_reuses_the_credential_does_not_log_it(
    environ: dict[str, str], captured_logs: pytest.LogCaptureFixture
) -> None:
    store = FakePersistence()
    tokens = TokenService(gateway=store)
    result = await bring_up(store, tokens, environ=environ)
    captured_logs.clear()

    again = await bring_up(store, tokens, environ=environ)

    assert again.issued is False
    assert result.credential.secret not in _log_text(captured_logs)


async def test_spending_the_credential_writes_neither_it_nor_its_replacement(
    environ: dict[str, str], captured_logs: pytest.LogCaptureFixture
) -> None:
    store = FakePersistence()
    tokens = TokenService(gateway=store)
    result = await bring_up(store, tokens, environ=environ)

    durable = await establish_durable_credential(
        store,
        tokens,
        bootstrap=result.credential,
        user_id="ada",
        email="ada@example.test",
        display_name="Ada",
        environ=environ,
    )

    text = _log_text(captured_logs) + await _audit_text(store)
    assert result.credential.secret not in text
    assert durable.secret not in text


async def test_a_refusal_names_no_credential(
    environ: dict[str, str], captured_logs: pytest.LogCaptureFixture
) -> None:
    """FR-004's third place. An exception's message is read by whoever is
    debugging, pasted into an issue, and rendered by a surface."""
    store = FakePersistence()
    tokens = TokenService(gateway=store)
    result = await bring_up(store, tokens, environ=environ)
    await establish_durable_credential(
        store,
        tokens,
        bootstrap=result.credential,
        user_id="ada",
        email="ada@example.test",
        display_name="Ada",
        environ=environ,
    )

    with pytest.raises(TokenRejected) as refusal:
        await tokens.authenticate(result.credential.secret)

    assert result.credential.secret not in str(refusal.value)
    assert result.credential.secret not in repr(refusal.value)
    assert result.credential.secret not in _log_text(captured_logs)


async def test_the_two_places_it_does_appear_are_the_file_and_the_printed_block(
    environ: dict[str, str],
) -> None:
    """Stated as an assertion rather than left implied: a sweep that found the
    credential nowhere at all would also pass against a bring-up that never
    produced one."""
    store = FakePersistence()
    tokens = TokenService(gateway=store)

    result = await bring_up(store, tokens, environ=environ)

    on_disk = credential_path(environ).read_text(encoding="utf-8")
    printed = announcement(result.credential, path=credential_path(environ))
    assert result.credential.secret in on_disk
    assert result.credential.secret in printed
