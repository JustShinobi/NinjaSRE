"""Whether this process holds something that can actually drive an investigation.

One question, asked in three places — the checklist, the self-check, and the
route that starts an investigation — and it is here rather than repeated because
the three have to agree. A checklist that said yes while the route said no would
be the same defect as before in a more confusing shape.

The question is worth asking at all because it is the one thing about a
deployment that leaves no trace anywhere else. An account, a provider key, a
resource in the estate: all of them are visible from the console. A process with
no investigation runtime composed looks exactly like one that has, right up to
the moment somebody presses Investigate and the run fails before it starts —
which is what made the guided first run's last step a promise the product could
not keep.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from gateway.http.state import GatewayState


def runtime_composed(state: GatewayState) -> bool:
    """Return whether this deployment can start an investigation.

    Asked of the stand-in rather than of a setting, and that indirection is the
    point: what decides the answer is what the composition root actually built,
    and a check that read the environment variable instead would say yes for a
    variable naming a factory that failed to import.

    The import is local because ``asgi`` is the composition root and imports the
    route table on the way up; at module scope this would close the circle.
    """
    from gateway.http.asgi import UnconfiguredInvestigator

    return not isinstance(state.investigator, UnconfiguredInvestigator)


def recompose_investigator(state: Any, *, environ: Mapping[str, str] | None = None) -> None:
    """Rebuild the runner now that the configuration it depends on has been read.

    ``build_deployment`` composes the investigator from the environment alone,
    which is the only thing a synchronous composition root has. The operator's
    model choice is published afterwards, and the vault's provider keys later
    still — and ``get_llm`` caches the client it built in between, so a runner
    composed first keeps calling whatever the manifest named however the console
    is configured.

    Called once, after both are true. A deployment that names no factory keeps
    its stand-in: "nothing is composed" is a state the checklist and the start
    route both read, and a rebuild that quietly produced something in its place
    would answer their question wrongly.

    The import is local for the reason ``runtime_composed`` gives above: ``asgi``
    is the composition root and imports the route table on the way up.
    """
    from gateway.http.asgi import UnconfiguredInvestigator, investigator_of

    if isinstance(state.investigator, UnconfiguredInvestigator):
        return
    state.investigator = investigator_of(dict(environ if environ is not None else os.environ))


__all__ = ["recompose_investigator", "runtime_composed"]
