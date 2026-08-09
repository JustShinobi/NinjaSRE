"""Guest configuration, with the secrets in it removed before anything stores one.

A Proxmox guest's configuration is a small text file and it routinely contains
material nobody meant to publish: ``cipassword`` is a cloud-init password in
plain text, ``sshkeys`` is a key block, and a container's ``password`` is the
root password it was created with. All three end up in the estate the moment
discovery attaches a configuration to a resource, and from there in the console,
in a report, and in whatever the model is shown.

**The rules are the deployment's own, not a list invented here.** The guardrail
ruleset already knows what a private key block, a JSON web token and a labelled
secret look like, an operator can extend it, and a second list here would be a
second thing to keep in step — the one that drifted would be the one that missed.
What this module adds is the two things a generic scanner cannot know: which
Proxmox keys are secret *by name* regardless of what their value looks like, and
that the values are strings inside a mapping rather than one document.

**Redaction happens before storage, not at display.** A secret that reached the
estate has been written to a database, and removing it afterwards is a migration
rather than a redaction.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from platform.guardrails.engine import GuardrailEngine

#: Proxmox configuration keys whose value is a secret whatever it looks like. A
#: pattern-based scanner catches a key block and a long random string; it does
#: not catch ``cipassword: summer2024`` and there is no pattern that could.
SECRET_KEYS: frozenset[str] = frozenset(
    {
        "cipassword",
        "password",
        "sshkeys",
        "ssh-public-keys",
        "ssh_public_keys",
        "citoken",
        "smbios1",
    }
)

#: What replaces a value redacted by name. Different from the guardrail
#: engine's own placeholder on purpose: an operator reading a configuration
#: wants to know whether the value was removed because of what it *was* or
#: because of where it *sat*, and those have different fixes.
KEY_REDACTION: Final = "[redacted: Proxmox holds this field in plain text]"

_ENGINE = GuardrailEngine()


def masked_configuration(configuration: Mapping[str, Any]) -> dict[str, Any]:
    """Return ``configuration`` with every secret in it removed.

    Two passes, because they catch different things. Keys named in
    ``SECRET_KEYS`` are redacted whatever their value is; every remaining string
    value goes through the deployment's guardrail ruleset, which catches the key
    block pasted into a ``description`` field and the token somebody left in
    ``args``.

    Non-string values are left alone: a core count is not a secret and running a
    regular expression over eighty integers per guest is a cost with no benefit.
    """
    masked: dict[str, Any] = {}
    for key, value in configuration.items():
        if str(key).lower() in SECRET_KEYS:
            masked[key] = KEY_REDACTION
            continue
        masked[key] = _ENGINE.scan(value).text if isinstance(value, str) else value
    return masked


def masked_text(text: str) -> str:
    """Return ``text`` with anything the ruleset recognises removed.

    For the free-text readings — a task log, a cluster log message — where there
    are no keys to go by and the ruleset is all there is.
    """
    return _ENGINE.scan(text).text


def redacted_keys(configuration: Mapping[str, Any]) -> tuple[str, ...]:
    """Return which keys were redacted by name, for a report that has to say so.

    An operator investigating a guest needs to know that ``cipassword`` is *set*
    even though they cannot be shown it — "this guest has a cloud-init password"
    is a fact about its configuration and only the value is a secret.
    """
    return tuple(key for key in configuration if str(key).lower() in SECRET_KEYS)


__all__ = ["KEY_REDACTION", "SECRET_KEYS", "masked_configuration", "masked_text", "redacted_keys"]
