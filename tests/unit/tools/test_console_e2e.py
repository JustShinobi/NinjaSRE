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
from collections.abc import Iterator

import pytest

from config.constants.console import CONSOLE_E2E_MOCK_PORT, CONSOLE_E2E_PORT
from tools.console_e2e import ports

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
