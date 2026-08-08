"""The single datastore, behind ports that no other module may bypass.

Constitution Article XI: one PostgreSQL instance holds relational records,
vector embeddings, and the topology graph. One thing to back up, one to upgrade,
one to monitor — and an investigation that writes its trace, its episode, its
embedding, and its topology edges in a single transaction, because they are all
in the same database.

**No SQL and no Cypher leaves this package.** ``tools/check_raw_sql.py`` fails
the build on a query written anywhere else, naming the module. Everything above
tier 3 imports from ``platform.persistence.ports`` and holds a
``PersistenceGateway``.

What is where:

``ports/``
    The thirteen repository protocols, the unit of work, and the records they
    exchange. This is the public surface; read ``ports/transaction.py`` first.
``fakes/``
    In-memory implementations of all thirteen, passing the same contract suite as
    any real backend. Not a test double: they are what lets features 007–017 be
    built and unit-tested without a database, and a fake that diverged from the
    real store would be a fiction those features were written against.
``errors.py``
    What storage raises. No message carries secret material or another tenant's
    data.
``health.py``
    The judgement half of the health check — a pure function from what a probe
    observed to whether the deployment should take work.
"""

from __future__ import annotations

from platform.persistence.errors import PersistenceError
from platform.persistence.ports import PersistenceGateway, TenantScope, UnitOfWork

__all__ = [
    "PersistenceError",
    "PersistenceGateway",
    "TenantScope",
    "UnitOfWork",
]
