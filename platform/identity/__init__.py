"""Who is acting, what they may do, and the record of what they did.

The package is split by question rather than by layer, because the questions are
what a reader arrives with.

===================  =========================================================
``permissions``      the atomic catalogue and the five roles built from it
``authorisation``    node-scoped resolution, and the last-owner refusal
``models``           principal, grant, issued token, session
``tokens``           issue, verify, revoke — immediately — expire, warn
``sessions``         signed sessions with an idle and an absolute bound
``oidc``             authorisation code with PKCE, claims, group mapping
``sso_config``       provider settings, and testing one before it goes live
``impersonation``    an admin in a team's context, time-limited
``break_glass``      the way in when the identity provider is not
``audit``            writing the record, sealing it, exporting it
===================  =========================================================

Nothing here reaches storage directly: everything goes through
``IdentityRepository`` and ``AuditRepository``, which is what lets the whole
package be exercised without a database.
"""

from __future__ import annotations

from platform.identity.authorisation import PermissionSet, owners_in, require_owner_retained
from platform.identity.errors import IdentityError, LastOwnerRemoval, PermissionDenied
from platform.identity.models import Grant, IssuedToken, Principal, Session
from platform.identity.permissions import Permission, Role, permissions_for

__all__ = [
    "Grant",
    "IdentityError",
    "IssuedToken",
    "LastOwnerRemoval",
    "Permission",
    "PermissionDenied",
    "PermissionSet",
    "Principal",
    "Role",
    "Session",
    "owners_in",
    "permissions_for",
    "require_owner_retained",
]
