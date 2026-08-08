"""What the estate refuses, and the name it refuses under.

Each of these is a case where the wrong answer is worse than an error. A
resource stored under a generated identifier looks like an estate and is a
duplicate factory; a kind invented at write time looks like extensibility and is
a schemaless bag; a sweep that failed and was reported as one that found nothing
looks like a working deployment and is a false decommissioning of everything.
"""

from __future__ import annotations


class EstateError(Exception):
    """Anything the estate refuses."""


class UnknownResourceKind(EstateError):
    """A kind nobody declared.

    Raised at *registration* rather than at write wherever it can be: a
    declaration that names a parent kind which does not exist is wrong the
    moment it is made, and finding out on the first sweep means finding out in
    production.
    """

    def __init__(self, kind: str, *, declared_by: str = "") -> None:
        subject = f"{declared_by!r} declares " if declared_by else ""
        super().__init__(
            f"{subject}resource kind {kind!r}, which nothing has registered. "
            f"Register the kind before anything of that kind is declared or written."
        )
        self.kind = kind
        self.declared_by = declared_by


class KindAlreadyRegistered(EstateError):
    """Two declarations of one kind.

    Refused rather than merged. Two integrations that both believe they own
    ``virtual_machine`` disagree about its attributes, and whichever registered
    second would silently decide.
    """

    def __init__(self, kind: str) -> None:
        super().__init__(
            f"resource kind {kind!r} is already registered. A kind is declared once; "
            f"an integration that needs a different shape needs a different name."
        )
        self.kind = kind


class RegistrySealed(EstateError):
    """A kind registered after the deployment started serving.

    The registry is open while a deployment wires its integrations and closed
    afterwards. A kind that appeared halfway through a sweep would mean two
    sweeps of one integration disagreeing about what its resources are.
    """

    def __init__(self, kind: str) -> None:
        super().__init__(
            f"resource kind {kind!r} was registered after the registry was sealed. "
            f"Kinds are declared while the deployment is being composed, not while it runs."
        )
        self.kind = kind


class NoStableIdentifier(EstateError):
    """A source reported a resource it cannot name the same way twice.

    Generating an identifier here would be the worst available option: every
    sweep would generate a different one, so every sweep would create the
    resource again and mark the previous one absent. An estate that grows
    without bound and reports a decommissioning every fifteen minutes is harder
    to diagnose than a sweep that failed loudly.
    """

    def __init__(self, *, source: str, detail: str = "") -> None:
        because = f" ({detail})" if detail else ""
        super().__init__(
            f"{source or 'an unnamed source'} reported a resource with no stable "
            f"identifier{because}. It is not stored: an identifier we generated would "
            f"differ on every sweep, and every sweep would then create it again."
        )
        self.source = source


class SweepBoundExceeded(EstateError):
    """A sweep asked for more than its declared bound allows.

    Distinct from suspension, which is the normal outcome of reaching a bound.
    This is a declaration that could never fit — an interval below the floor, a
    call budget above the ceiling — and it is refused where it is declared.
    """

    def __init__(self, *, parameter: str, requested: int, limit: int, constant: str) -> None:
        super().__init__(
            f"{parameter} of {requested} exceeds {limit}, which is {constant}. "
            f"Bounds are raised deliberately, in the constant, not per integration."
        )
        self.parameter = parameter
        self.requested = requested
        self.limit = limit
        self.constant = constant


__all__ = [
    "EstateError",
    "KindAlreadyRegistered",
    "NoStableIdentifier",
    "RegistrySealed",
    "SweepBoundExceeded",
    "UnknownResourceKind",
]
