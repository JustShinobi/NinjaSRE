"""What a principal may do, resolved against the node they are asking about.

One tree, two uses. Configuration inherits downward — a value set at a division
applies to every team beneath it — and so does a grant. Making permissions
follow a *second* scoping model would give an operator two hierarchies to keep
straight, and the one they got wrong would be the security one.

**Inheritance is downward only.** A grant at ``payments`` covers ``payments``
and everything beneath it, and reaches neither the organisation above it nor
``platform`` beside it. That asymmetry is the whole security property: an
operator scoped to one team cannot widen their reach by asking about a node
nearer the root.

**An unknown node denies.** Resolving against a node that is not in the tree
does not fall back to the root, because a typo in a path parameter would then
become an organisation-wide check. A mistake here should fail closed.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace

from platform.config_service.errors import ConfigServiceError
from platform.config_service.hierarchy import Hierarchy
from platform.identity.errors import LastOwnerRemoval, PermissionDenied
from platform.identity.models import Grant
from platform.identity.permissions import Permission, Role, permissions_for
from platform.persistence.ports import UnitOfWork


@dataclass(frozen=True, slots=True)
class PermissionSet:
    """One principal's grants, resolvable at any node of one tenant's tree.

    ``hierarchy`` is optional because a caller that has not loaded the tree still
    needs an answer, and the answer it gets is the narrow one: exact-node grants
    and organisation-wide grants apply, inheritance does not. Denying more than
    it should is the safe direction for a missing input to fail in.
    """

    grants: tuple[Grant, ...] = field(default_factory=tuple)
    hierarchy: Hierarchy | None = None
    #: What a credential was scoped to, if it was scoped. ``None`` is "no
    #: ceiling" and is different from an empty set, which is "holds nothing" —
    #: a token issued with no permissions must not resolve to its owner's.
    ceiling: frozenset[Permission] | None = None

    def roles_at(self, node_id: str | None = None) -> frozenset[Role]:
        """Return every role that applies at ``node_id``."""
        reach = self._reach(node_id)
        if reach is None:
            return frozenset()
        return frozenset(
            grant.role for grant in self.grants if grant.node_id is None or grant.node_id in reach
        )

    def permissions_at(self, node_id: str | None = None) -> frozenset[Permission]:
        """Return the union of everything the applicable roles confer, capped."""
        applicable = self.roles_at(node_id)
        if not applicable:
            return frozenset()
        held: frozenset[Permission] = frozenset().union(
            *(permissions_for(role) for role in applicable)
        )
        return held if self.ceiling is None else held & self.ceiling

    def allows(self, permission: Permission, *, node_id: str | None = None) -> bool:
        """Return whether ``permission`` is held at ``node_id``."""
        return permission in self.permissions_at(node_id)

    def require(self, permission: Permission, *, node_id: str | None = None) -> None:
        """Raise ``PermissionDenied`` unless ``permission`` is held at ``node_id``."""
        if not self.allows(permission, node_id=node_id):
            principal = self.grants[0].principal_id if self.grants else None
            raise PermissionDenied(permission, node_id=node_id, principal_id=principal)

    def narrowed_to(self, permissions: Iterable[Permission]) -> PermissionSet:
        """Return this set capped by ``permissions``.

        What a scoped token gets: never more than its owner holds, and usually
        less. Expressed as a cap over the same grants rather than as an
        independent set, so a token can never outlive its owner's demotion by
        holding permissions of its own.

        Narrowing an already-narrowed set intersects rather than replaces. A
        narrowing that could widen would not be one.
        """
        wanted = frozenset(permissions)
        return replace(self, ceiling=wanted if self.ceiling is None else self.ceiling & wanted)

    def _reach(self, node_id: str | None) -> frozenset[str] | None:
        """Return the nodes a grant may sit at to cover ``node_id``.

        ``None`` means the node does not exist, which denies. An empty frozenset
        means "organisation-wide grants only", which is what asking about the
        tenant as a whole should get.
        """
        if node_id is None:
            return frozenset()
        if self.hierarchy is None:
            return frozenset({node_id})
        try:
            chain = self.hierarchy.chain(node_id)
        except ConfigServiceError:
            return None
        return frozenset(node.node_id for node in chain)


# --- Last owner protection ------------------------------------------


def owners_in(grants: Iterable[Grant]) -> frozenset[str]:
    """Return the principals holding ``owner`` over the organisation as a whole.

    Ownership is a property of the tenant, not of a node: an ``owner`` grant at
    one team does not make somebody the organisation's owner, and counting it
    would let the last real owner be removed while a team-scoped grant made the
    count look safe.
    """
    return frozenset(
        grant.principal_id for grant in grants if grant.role is Role.OWNER and grant.node_id is None
    )


def require_owner_retained(
    grants: Sequence[Grant],
    *,
    removing: Sequence[str] = (),
    adding: Sequence[Grant] = (),
) -> None:
    """Raise ``LastOwnerRemoval`` if the change would leave the org without an owner.

    Evaluated over the *whole* change rather than per removal, so handing
    ownership over in one operation is allowed and removing every owner in one
    operation is not. A per-removal check would get the first case wrong by
    refusing it and the second wrong by permitting it.
    """
    withdrawn = frozenset(removing)
    surviving = tuple(grant for grant in grants if grant.grant_id not in withdrawn)
    remaining = owners_in(surviving) | owners_in(adding)
    if remaining:
        return
    raise LastOwnerRemoval(sorted(owners_in(grants)))


# --- Loading (the one place this package reaches storage for grants) ---------


async def load_permissions(
    uow: UnitOfWork, principal_id: str, *, node_id: str | None = None
) -> PermissionSet:
    """Return what ``principal_id`` may do, resolvable around ``node_id``.

    Only the ancestry of the node in question is loaded, not the whole tree. A
    permission check needs to know which grants sit *above* the node being asked
    about, and that is one indexed read — materialising a tenant's entire
    hierarchy on every authenticated request would be the most expensive thing
    in the platform and would answer no additional question.
    """
    bindings = await uow.identity.role_bindings_for_user(principal_id)
    grants = tuple(Grant.of_binding(binding) for binding in bindings)
    return PermissionSet(grants=grants, hierarchy=await load_chain(uow, node_id))


async def load_chain(uow: UnitOfWork, node_id: str | None) -> Hierarchy | None:
    """Return the root-to-node path as a hierarchy, or ``None`` if there is none.

    A chain *is* a valid hierarchy — one root, every parent present — so the
    resolution code needs no second shape for the partial case.
    """
    if node_id is None:
        return None
    node = await uow.config.get(node_id)
    if node is None:
        return None
    ancestors = await uow.config.ancestors(node_id)
    return Hierarchy.of((*ancestors, node))


__all__ = [
    "PermissionSet",
    "load_chain",
    "load_permissions",
    "owners_in",
    "require_owner_retained",
]
