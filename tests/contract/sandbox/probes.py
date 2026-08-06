"""The commands the contract suite runs *inside* a sandbox.

They are here rather than inline in the tests because all three profiles run the
same ones, and because each is a small program with a reason: one exhausts a
bound in a way that is observable across a poll interval, one probes for another
investigation's data, one tries to reach a host nobody declared. A test that
built these strings inline would eventually build three slightly different
versions and prove three slightly different things.

Every probe is written to be *stable* rather than fast. A capability that
allocates and immediately exits could finish between two samples and never be
seen; these allocate, hold, and sleep, which is also what a real capability that
downloaded a large log actually does.
"""

from __future__ import annotations

import sys

#: The interpreter a probe runs under. The sandbox's environment is built from
#: nothing, so the command has to be an absolute path — there is no ``PATH`` in
#: there to resolve ``python`` against, deliberately.
PYTHON = sys.executable


def python(source: str) -> tuple[str, ...]:
    """Return the command that runs ``source`` inside a sandbox."""
    return (PYTHON, "-I", "-c", source)


#: Prints to both streams and exits zero. The baseline every profile must pass.
HELLO = python("import sys; sys.stdout.write('out'); sys.stderr.write('err'); sys.stdout.flush()")

#: Exits non-zero without failing. A sandbox must report the status rather than
#: treat a failing capability as a broken sandbox.
EXIT_THREE = python("raise SystemExit(3)")

#: Emits many chunks with flushes between them, so a streaming implementation
#: that buffered everything until exit is visibly different from one that does not.
CHUNKED = python(
    "import sys, time\n"
    "for i in range(5):\n"
    "    sys.stdout.write(f'chunk{i}\\n'); sys.stdout.flush(); time.sleep(0.05)\n"
)

#: Sleeps far past any bound the suite sets. Used for wall clock and interruption.
SLEEP_FOREVER = python("import time; time.sleep(600)")

#: Burns CPU without allocating or sleeping.
BURN_CPU = python("x = 0\nwhile True:\n    x += 1\n")


#: Allocates well past the memory bound and *holds* it, so the resident set is
#: still there when the next sample is taken.
def allocate(megabytes: int) -> tuple[str, ...]:
    """Return a command that allocates ``megabytes`` and holds them."""
    return python(
        f"import time\n"
        f"block = bytearray({megabytes} * 1024 * 1024)\n"
        f"block[::4096] = b'x' * (len(block) // 4096 + (1 if len(block) % 4096 else 0))\n"
        f"time.sleep(600)\n"
    )


def fill_scratch(megabytes: int) -> tuple[str, ...]:
    """Return a command that writes ``megabytes`` into the scratch mount and waits."""
    return python(
        f"import time\n"
        f"with open('big.bin', 'wb') as handle:\n"
        f"    for _ in range({megabytes}):\n"
        f"        handle.write(b'\\0' * 1024 * 1024)\n"
        f"time.sleep(600)\n"
    )


def fork_children(count: int) -> tuple[str, ...]:
    """Return a command that starts ``count`` long-lived child processes.

    ``subprocess`` rather than ``os.fork`` so the same probe runs on Windows,
    and ``-I`` on the children so each one starts without reading a site
    directory it has no business reading.
    """
    return python(
        f"import subprocess, sys, time\n"
        f"children = [\n"
        f"    subprocess.Popen([sys.executable, '-I', '-c', 'import time; time.sleep(600)'])\n"
        f"    for _ in range({count})\n"
        f"]\n"
        f"time.sleep(600)\n"
    )


def write_file(name: str, content: str) -> tuple[str, ...]:
    """Return a command that writes ``content`` to ``name`` in the scratch mount."""
    return python(f"open({name!r}, 'w').write({content!r})")


def read_file(path: str) -> tuple[str, ...]:
    """Return a command that prints ``path`` or reports why it could not."""
    return python(
        f"import sys\n"
        f"try:\n"
        f"    sys.stdout.write(open({path!r}).read())\n"
        f"except OSError as error:\n"
        f"    sys.stdout.write(f'DENIED:{{type(error).__name__}}')\n"
    )


def overwrite_content(path: str) -> tuple[str, ...]:
    """Return a command that tries to rewrite delivered capability content.

    The immutability probe. Prints ``DENIED`` when the write is refused and ``WROTE``
    when it is not, so the assertion is on the outcome rather than on which
    exception a platform happens to raise.
    """
    return python(
        f"import sys\n"
        f"try:\n"
        f"    open({path!r}, 'w').write('tampered')\n"
        f"    sys.stdout.write('WROTE')\n"
        f"except OSError as error:\n"
        f"    sys.stdout.write(f'DENIED:{{type(error).__name__}}')\n"
    )


def connect(host: str, port: int) -> tuple[str, ...]:
    """Return a command that opens a TCP connection and reports what happened.

    Prints ``CONNECTED`` or ``REFUSED:<error>``. Used by the egress probe, where
    the assertion is that an undeclared host is never the first of those.
    """
    return python(
        f"import socket, sys\n"
        f"try:\n"
        f"    socket.create_connection(({host!r}, {port}), timeout=2).close()\n"
        f"    sys.stdout.write('CONNECTED')\n"
        f"except OSError as error:\n"
        f"    sys.stdout.write(f'REFUSED:{{type(error).__name__}}')\n"
    )


__all__ = [
    "BURN_CPU",
    "CHUNKED",
    "EXIT_THREE",
    "HELLO",
    "PYTHON",
    "SLEEP_FOREVER",
    "allocate",
    "connect",
    "fill_scratch",
    "fork_children",
    "overwrite_content",
    "python",
    "read_file",
    "write_file",
]
