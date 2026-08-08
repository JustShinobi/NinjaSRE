"""What the incident lifecycle refuses, and the name it refuses under.

Both of these are cases where doing the thing would quietly lose information an
operator needs. Reopening a closed incident writes a new occurrence into last
week's history, so the *when* of the recurrence disappears; acting on an
incident nobody raised means a caller is holding an identifier it invented, and
storing something under it would create the incident it thought it had.
"""

from __future__ import annotations


class IncidentError(Exception):
    """Anything the incident lifecycle refuses."""


class UnknownIncident(IncidentError):
    """An operation naming an incident nothing raised."""

    def __init__(self, incident_id: str) -> None:
        super().__init__(
            f"no incident is stored as {incident_id!r}. An incident is raised through the "
            f"lifecycle; an identifier that resolves to nothing is a caller holding one it "
            f"made up."
        )
        self.incident_id = incident_id


class IncidentClosed(IncidentError):
    """A transition on an incident that has already ended.

    Refused rather than reopening. The condition recurring is a new incident,
    and writing the recurrence into the closed one's history would lose when it
    recurred — which is the first thing anybody asks about a repeat.
    """

    def __init__(self, incident_id: str, *, state: str) -> None:
        super().__init__(
            f"incident {incident_id!r} is {state} and cannot be moved. A condition that "
            f"has recurred opens a new incident; writing it into this one would lose when "
            f"it recurred."
        )
        self.incident_id = incident_id
        self.state = state


__all__ = ["IncidentClosed", "IncidentError", "UnknownIncident"]
