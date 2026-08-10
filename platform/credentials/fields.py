"""One field of a credential, as something that asks for it can render it.

``CredentialSchema`` next door is what the vault *validates* against: patterns,
lengths, alternatives, the rules that decide whether a write is accepted. This
is the other half of the same fact — what a person is asked, in what words, and
whether the prompt echoes. Two shapes rather than one because they are read by
different things: the vault never renders a form, and a form never enforces a
vendor's key format.

It lives here rather than in either surface because both need it. The CLI's
wizard prompts from it and the API's provider and integration routes serve it,
and those are two tier-1 packages that may not import each other. Below both is
the only place one copy can sit.

**There is no field here a value could occupy.** That is what makes a descriptor
safe to serve over HTTP without the route becoming a credential-reading path:
the absence is the guarantee, not a rule somebody has to remember when adding a
key. ``secret`` says whether the prompt echoes — get that wrong and a token is
on somebody's screen during a screen share.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class CredentialFieldSpec:
    """One field a credential needs, as a prompt or a form can ask for it.

    Carried out of the declaring package rather than hard-coded per vendor,
    which is what makes adding an integration a package rather than a change to
    every surface that sets one up.
    """

    name: str
    label: str = ""
    secret: bool = True
    required: bool = True
    help: str = ""

    @property
    def prompt(self) -> str:
        """Return the text shown when asking for this."""
        return self.label or self.name.replace("_", " ")

    def to_record(self) -> dict[str, Any]:
        """Return this field as a JSON-serialisable document."""
        return {
            "name": self.name,
            "label": self.prompt,
            "secret": self.secret,
            "required": self.required,
            "help": self.help,
        }


__all__ = ["CredentialFieldSpec"]
