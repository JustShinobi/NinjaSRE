"""What every credential field owes an operator, by its own type.

A schema declares three kinds of field — secret, public configuration, and the
address a self-hosted vendor answers at — and each kind owes the operator a
different amount of orientation. This module is that rule, written once so the
gate, the contract test, and the failure message all read the same thing rather
than three that could drift.

**A secret field must declare the minimum permission its value needs**, in the
vendor's own words. Guessing one from the field's name is worse than leaving it
blank: an operator who reads a plausible-looking scope pastes it into the
vendor's console and finds out it was wrong during an incident rather than
before one, and a scope that is too narrow fails silently while one that is too
wide is a standing risk nobody chose on purpose.

**An address field and a public configuration field must not declare one.**
Neither is a secret a vendor's permission model can be asked to constrain — a
hostname and a namespace name grant nothing — so a minimum permission on either
is not a stricter declaration, it is a wrong one, and the gate below reports it
exactly as loudly as a missing one.

**Every field, of every kind, must declare a guide** — an address for the
step-by-step that produces the value. An address field's guide is the vendor's
own documentation of where its API answers; nothing here is exempt because the
value it names happens not to be secret.

**Presence and form are checked here, never reachability.** A guide is a
website an operator might click days from now, at a moment nothing about a
build is watching. Opening a connection to it would make every run of this
check a network dependency, and would fail the build the day a vendor
reorganises its site — a failure that belongs to nobody who touched this
repository. A link that has gone stale is a real problem with a different
remedy: a periodic sweep outside the build, not a gate inside it.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

from platform.credentials.schemas import CredentialField, CredentialSchema

#: A secret field with nothing in ``min_scope``.
MIN_SCOPE_MISSING_RULE = "credential-field-min-scope-missing"
#: An address or public-configuration field carrying a ``min_scope`` it must
#: not have — see the module docstring for why this is a rule and not a detail.
MIN_SCOPE_FORBIDDEN_RULE = "credential-field-min-scope-forbidden"
#: Any field, of any kind, with nothing in ``guide_url``.
GUIDE_MISSING_RULE = "credential-field-guide-missing"
#: A declared ``guide_url`` that is neither a full vendor address nor an
#: absolute path on this deployment — see ``is_absolute_guide``.
GUIDE_NOT_ABSOLUTE_RULE = "credential-field-guide-not-absolute"


@dataclass(frozen=True, slots=True)
class GuidanceProblem:
    """One field that does not carry the orientation its own kind requires."""

    rule: str
    integration: str
    field: str
    message: str

    def __str__(self) -> str:
        return f"{self.rule}: {self.integration}.{self.field}: {self.message}"


def is_absolute_guide(url: str) -> bool:
    """Return whether ``url`` is a guide address this deployment accepts.

    Two shapes are accepted, and only two. The ordinary shape is a full vendor
    address — a scheme and a host, checked the same way an endpoint field's own
    value is (``http``/``https`` plus a hostname that is actually present).

    The other shape exists for a vendor with no public documentation of its
    own: its guide is this deployment's own served copy of its package
    documentation, and that page has no fixed host — every installation serves
    it from a different origin. An absolute *path*, starting with exactly one
    ``/``, is accepted for that case: a browser resolves it against whichever
    origin actually served the screen the same way it resolves any other
    same-origin link, which is the ordinary meaning of an absolute path in a
    URL reference and not a licence to invent a second one per vendor.
    """
    stripped = url.strip()
    if stripped.startswith("//"):
        # Protocol-relative — still names an external host, and the one form
        # this function does not try to disambiguate from a typo'd path.
        return False
    if stripped.startswith("/"):
        return True
    split = urlsplit(stripped)
    return split.scheme.lower() in {"http", "https"} and bool(split.hostname)


def guidance_problems(schema: CredentialSchema) -> list[GuidanceProblem]:
    """Return every field of ``schema`` missing the orientation its kind owes.

    Every problem is returned rather than the first one raised, so a caller
    collecting problems across a whole catalogue reports all of them in one
    failing build instead of one per run.
    """
    found: list[GuidanceProblem] = []
    for declared in schema.fields:
        found.extend(_min_scope_problems(schema.integration, declared))
        found.extend(_guide_problems(schema.integration, declared))
    return found


def _min_scope_problems(integration: str, declared: CredentialField) -> list[GuidanceProblem]:
    has_scope = declared.min_scope.strip() != ""
    if declared.is_secret and not has_scope:
        return [
            GuidanceProblem(
                rule=MIN_SCOPE_MISSING_RULE,
                integration=integration,
                field=declared.name,
                message=(
                    "is secret and declares no minimum permission, so an operator pasting a "
                    "value here has no way to know how much access it actually grants"
                ),
            )
        ]
    if not declared.is_secret and has_scope:
        return [
            GuidanceProblem(
                rule=MIN_SCOPE_FORBIDDEN_RULE,
                integration=integration,
                field=declared.name,
                message=(
                    "is not secret and declares a minimum permission, but an address or a "
                    "piece of public configuration grants no access a permission could name — "
                    "move it to the secret field it accompanies"
                ),
            )
        ]
    return []


def _guide_problems(integration: str, declared: CredentialField) -> list[GuidanceProblem]:
    guide = declared.guide_url.strip()
    if guide == "":
        return [
            GuidanceProblem(
                rule=GUIDE_MISSING_RULE,
                integration=integration,
                field=declared.name,
                message=(
                    "declares no guide, so an operator who does not already know this vendor "
                    "has nowhere to learn where this value comes from"
                ),
            )
        ]
    if not is_absolute_guide(guide):
        return [
            GuidanceProblem(
                rule=GUIDE_NOT_ABSOLUTE_RULE,
                integration=integration,
                field=declared.name,
                message=(
                    f"declares a guide of {guide!r}, which is neither a full vendor address "
                    f"nor an absolute path on this deployment, so nothing can resolve it"
                ),
            )
        ]
    return []


__all__ = [
    "GUIDE_MISSING_RULE",
    "GUIDE_NOT_ABSOLUTE_RULE",
    "MIN_SCOPE_FORBIDDEN_RULE",
    "MIN_SCOPE_MISSING_RULE",
    "GuidanceProblem",
    "guidance_problems",
    "is_absolute_guide",
]
