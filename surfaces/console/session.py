"""Who is signed in, for how long, and what happens when that stops being true.

A console session holds one thing of value — the bearer token — and everything
here exists to bound where that thing can go.

**It is never rendered.** ``Session`` has no method that returns the token into
a page, and the sign-in form's own field is write-only in the same sense: the
value posted is exchanged for a session and is not echoed back. A token in the
HTML is a token in every browser cache and every screenshot pasted into a chat.

**Expiry is checked before the request, not after it.** A session that has
lapsed sends the user to sign in with the page they wanted remembered, rather
than making a call that will 401 and then handling the 401. The difference shows
up as whether "your session expired" arrives before or after a failed action.

**A 401 from anywhere ends the session.** Permissions can be revoked mid-session
(the spec's edge case), and the honest response to "this token no longer
resolves" is to stop presenting it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Final

from surfaces.console.permissions import Viewer

#: How long a signed-in session lasts without activity. Short enough that a
#: laptop left open in a shared office is not a standing grant; long enough that
#: an incident does not end with a re-authentication.
DEFAULT_SESSION_LIFETIME = timedelta(hours=8)

#: How long before expiry the console starts telling the user. Enough warning to
#: finish an approval rather than losing it at the moment of submission.
EXPIRY_WARNING = timedelta(minutes=10)

#: Where an unauthenticated visitor is sent, and the only page they may see.
SIGN_IN_PATH: Final = "/sign-in"


def _utc_now() -> datetime:
    """Return the current instant in UTC."""
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class Session:
    """One signed-in browser, and what it may present.

    ``token`` is here and nowhere else. No page builder receives a session; they
    receive a ``Viewer``, which carries identity and permissions and no
    credential — so there is no page that *could* render one by mistake.
    """

    token: str = ""
    viewer: Viewer = field(default_factory=Viewer)
    established_at: datetime | None = None
    expires_at: datetime | None = None
    #: Where the visitor was going when they were sent to sign in. Returned to
    #: afterwards, because an on-call engineer following a link from an alert
    #: should land on the run, not on a dashboard.
    intended_path: str = ""

    @property
    def is_authenticated(self) -> bool:
        """Return whether this session presents a credential at all."""
        return bool(self.token)

    def is_expired(self, *, now: datetime | None = None) -> bool:
        """Return whether this session has lapsed."""
        if self.expires_at is None:
            return not self.token
        return (now or _utc_now()) >= self.expires_at

    def is_expiring(self, *, now: datetime | None = None) -> bool:
        """Return whether this session is close enough to expiry to say so."""
        if self.expires_at is None or self.is_expired(now=now):
            return False
        return (now or _utc_now()) >= self.expires_at - EXPIRY_WARNING

    def is_usable(self, *, now: datetime | None = None) -> bool:
        """Return whether a request may be made with this session."""
        return self.is_authenticated and not self.is_expired(now=now)

    def renewed(
        self, *, now: datetime | None = None, lifetime: timedelta = DEFAULT_SESSION_LIFETIME
    ) -> Session:
        """Return this session with its expiry pushed out from ``now``."""
        moment = now or _utc_now()
        return replace(self, expires_at=moment + lifetime)

    def ended(self) -> Session:
        """Return an anonymous session, keeping nothing.

        The token is dropped rather than blanked in place: a session object that
        still carried a revoked secret would be one more place for it to be
        read out of.
        """
        return Session(intended_path=self.intended_path)

    def remembering(self, path: str) -> Session:
        """Return this session with ``path`` recorded as where the visitor was going."""
        return replace(self, intended_path=path if path != SIGN_IN_PATH else "")


def sign_in(
    token: str,
    principal: Mapping[str, object],
    *,
    now: datetime | None = None,
    lifetime: timedelta = DEFAULT_SESSION_LIFETIME,
    intended_path: str = "",
) -> Session:
    """Return the session a successful sign-in produces.

    ``principal`` is what ``GET /auth/me`` answered. Requiring it here rather
    than resolving it lazily is deliberate: a token that cannot describe its own
    principal is a token that does not work, and finding that out at sign-in is
    better than finding it out on the first page that needed a permission.
    """
    moment = now or _utc_now()
    return Session(
        token=token,
        viewer=Viewer.of_principal(principal),
        established_at=moment,
        expires_at=moment + lifetime,
        intended_path=intended_path,
    )


@dataclass(frozen=True, slots=True)
class SsoProvider:
    """Where a sign-in redirect goes, as the deployment configured it."""

    name: str
    authorize_url: str
    enabled: bool = True


__all__ = [
    "DEFAULT_SESSION_LIFETIME",
    "EXPIRY_WARNING",
    "SIGN_IN_PATH",
    "Session",
    "SsoProvider",
    "sign_in",
]
