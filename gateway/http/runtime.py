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


__all__ = ["runtime_composed"]
