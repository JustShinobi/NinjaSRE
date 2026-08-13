"""In-memory implementations of all eighteen ports, and the gateway over them.

Not a test double. These are what let features 007–017 be built and unit-tested
before a database exists, which means they are load-bearing: a fake that
diverged from the real store would be a fiction those features were written
against, and the divergence would surface as production behaviour nobody had
ever seen.

That is why they run the same contract suite the Postgres backend does
(SC-005). A fake-only pass is not accepted as green — it means the suite ran
against one backend, and the suite exists to check two.

They also have real transactions. ``FakePersistence.begin`` snapshots, hands the
copy to a unit of work, and commits by swapping it in, so a block that raises
rolls back across all sixteen repositories. Without that, SC-001 would pass here
for the wrong reason.
"""

from __future__ import annotations

from platform.persistence.fakes.gateway import (
    FakePersistence,
    FakeSystemUnitOfWork,
    FakeUnitOfWork,
)

__all__ = [
    "FakePersistence",
    "FakeSystemUnitOfWork",
    "FakeUnitOfWork",
]
