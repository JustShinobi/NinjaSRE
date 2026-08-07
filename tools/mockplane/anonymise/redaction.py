"""Removing what must not survive, and renaming what may.

Two different operations, deliberately not merged.

**Credential-shaped things are removed, not pseudonymised.** A pseudonymised
token is still a token-shaped string in a field called ``token``, and the next
person to read the fixture learns that this dataset carries credentials. Drop
the key and record that something was dropped.

**Identifying things are renamed.** Hostnames, guest and storage names,
addresses, domains, e-mail addresses, principals and teams get a stable
pseudonym so every reference between records survives.

Free text gets both. A hostname inside a log line is still a hostname, and the
field it is in has no name that says so — which is why the operator's list of
real values is applied to every string in the document, longest value first, and
why the pattern net runs over what is left.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any, Final

from tools.mockplane.anonymise.pseudonyms import Kind, PseudonymBook
from tools.mockplane.identifiers import IdentifierList

#: What a removed value is replaced by. A marker rather than an empty string, so
#: "this field held something and it was dropped" stays readable in the fixture.
REMOVED: Final = "[removed]"

#: Field names whose *string* value is removed outright, matched
#: case-insensitively anywhere in the key. Deliberately broad, because a false
#: positive costs one field of a development fixture and a false negative costs
#: a credential — but bounded by two rules that are not negotiable either way.
#:
#: Only a string is removed. A credential in a JSON payload is a scalar; a list
#: called ``tokens`` is a collection of records and an object called ``token``
#: is a record. Dropping those loses the dataset and protects nothing.
#:
#: A key ending in an identifier suffix is exempt. ``token_id`` names a token
#: and is not one, and a fixture with its identifiers removed is a fixture whose
#: every reference is broken.
CREDENTIAL_FIELD_FRAGMENTS: Final[tuple[str, ...]] = (
    "apikey",
    "api_key",
    "authorization",
    "certificate",
    "cipher",
    "client_secret",
    "cloudinit",
    "cloud-init",
    "credential",
    "passphrase",
    "password",
    "private_key",
    "privatekey",
    "secret",
    "session_key",
    "sshkey",
    "ssh_key",
    "sshkeys",
    "token",
)

#: Values that are credential-shaped whatever they are called. A capture will
#: put one in a field nobody expected; that is the case this exists for.
CREDENTIAL_VALUE_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"-----BEGIN CERTIFICATE-----"),
    re.compile(r"\bssh-(?:rsa|ed25519|dss)\s+[A-Za-z0-9+/]{40,}"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    re.compile(r"\b(?:Bearer|Basic)\s+[A-Za-z0-9+/._~-]{16,}"),
    re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s:@/]+:[^\s@/]+@"),
    re.compile(r"#cloud-config\b"),
    re.compile(r"\b(?:sk|pk|ghp|gho|xox[abpsr])[-_][A-Za-z0-9]{16,}"),
)

#: Field names whose value is a thing of a given kind, whatever the surrounding
#: document is. ``name`` is deliberately absent: it means twenty things, and
#: renaming a detector because it has a name would break the dataset.
_FIELD_KINDS: Final[Mapping[str, Kind]] = {
    "actor": Kind.PRINCIPAL,
    "actor_id": Kind.PRINCIPAL,
    "cluster": Kind.CLUSTER,
    "cluster_name": Kind.CLUSTER,
    "datastore": Kind.STORAGE,
    "domain": Kind.DOMAIN,
    "email": Kind.EMAIL,
    "fqdn": Kind.HOST,
    "host": Kind.HOST,
    "hostname": Kind.HOST,
    "mac": Kind.MAC,
    "node": Kind.NODE,
    "node_name": Kind.NODE,
    "nodename": Kind.NODE,
    "owner": Kind.PRINCIPAL,
    "pool": Kind.POOL,
    "pool_lv": Kind.POOL,
    "principal": Kind.PRINCIPAL,
    "principal_id": Kind.PRINCIPAL,
    "storage": Kind.STORAGE,
    "team": Kind.TEAM,
    "team_id": Kind.TEAM,
    # A principal is a principal whatever the field it is spelled in. The two
    # names for it have to map to one pseudonym or the grant stops naming
    # anybody — which is exactly the class of failure the referential check
    # exists to catch, and it caught this one.
    "user_id": Kind.PRINCIPAL,
    "vg_name": Kind.POOL,
    "volume_group": Kind.POOL,
}

#: A guest's own name is only a guest's name when it is beside a guest id. Any
#: other ``name`` is left alone.
_GUEST_MARKERS: Final = frozenset({"vmid", "guest_id"})

_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_IPV6 = re.compile(r"\b(?:[0-9a-fA-F]{1,4}:){2,7}[0-9a-fA-F]{0,4}\b")
_MAC = re.compile(r"\b(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}\b")
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_URL = re.compile(r"\b([a-z][a-z0-9+.-]*)://([^\s/?#\"']+)")

#: Suffixes that mark a private naming scheme. A domain under one of these is
#: somebody's estate by definition, and no pattern short of a full domain list
#: would otherwise catch it.
_PRIVATE_SUFFIXES: Final = (".lan", ".local", ".internal", ".home", ".corp", ".intranet")

#: Addresses that are already reserved for documentation, so replacing them
#: would churn the dataset for nothing.
_ALREADY_RESERVED: Final = ("198.51.100.", "203.0.113.", "192.0.2.", "2001:db8:")


#: Suffixes that make a key a name for a thing rather than the thing. Removing
#: ``token_id`` would break every reference to that token, which is a broken
#: dataset in exchange for no secrecy at all.
IDENTIFIER_SUFFIXES: Final[tuple[str, ...]] = (
    "_id",
    "_ids",
    "_at",
    "_by",
    "_count",
    "_kind",
    "_name",
    "_type",
    "_fields",
    "_scopes",
)


def is_credential_field(key: str) -> bool:
    """Return whether a field with this name holds something that must be dropped."""
    folded = key.lower().replace(" ", "")
    if folded.endswith(IDENTIFIER_SUFFIXES):
        return False
    return any(fragment in folded for fragment in CREDENTIAL_FIELD_FRAGMENTS)


def is_credential_value(value: str) -> bool:
    """Return whether ``value`` is credential-shaped whatever it is called."""
    return any(pattern.search(value) for pattern in CREDENTIAL_VALUE_PATTERNS)


def should_remove(key: str, value: Any) -> bool:
    """Return whether the field ``key`` holding ``value`` must be dropped.

    Both halves, because the name alone is not the decision. ``total_tokens``
    names tokens and is a count; ``tokens`` names tokens and is a list of
    records. A credential in a JSON payload is a string, and that is the line.
    """
    return isinstance(value, str) and is_credential_field(key)


def anonymise(
    document: Any,
    book: PseudonymBook,
    identifiers: IdentifierList,
) -> Any:
    """Return ``document`` with identity replaced and credentials removed.

    Structure, ordering, numbers and every other property are untouched: the
    count of each resource kind, the ratio between them, utilisation
    percentages, payload sizes and the skew between nodes are what the console
    is being designed against, and a pipeline that tidied them would defeat the
    point of capturing a real deployment.
    """
    return _walk(document, book, identifiers, key="", parent={})


def replace_in_text(text: str, book: PseudonymBook, identifiers: IdentifierList) -> str:
    """Return ``text`` with every identifying substring replaced by its pseudonym.

    The operator's known values go first, longest first, because one real value
    routinely contains another — a hostname inside its own fully-qualified name
    — and replacing the shorter first leaves a fragment behind that reads as a
    pseudonym and is not one.
    """
    if not text:
        return text
    replaced = text
    for entry in identifiers.longest_first():
        if entry.value and entry.value in replaced:
            replaced = replaced.replace(entry.value, book.of(entry.kind, entry.value))
    replaced = _EMAIL.sub(lambda found: book.of(Kind.EMAIL, found.group(0)), replaced)
    replaced = _MAC.sub(lambda found: book.of(Kind.MAC, found.group(0)), replaced)
    replaced = _IPV4.sub(_ipv4_replacement(book), replaced)
    replaced = _IPV6.sub(_ipv6_replacement(book), replaced)
    replaced = _URL.sub(_url_replacement(book), replaced)
    return _private_domains(replaced, book)


def _walk(
    value: Any,
    book: PseudonymBook,
    identifiers: IdentifierList,
    *,
    key: str,
    parent: Mapping[str, Any],
) -> Any:
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for name, item in value.items():
            if should_remove(str(name), item):
                result[str(name)] = REMOVED
                continue
            result[str(name)] = _walk(item, book, identifiers, key=str(name), parent=value)
        return result
    if isinstance(value, str):
        return _string(value, book, identifiers, key=key, parent=parent)
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return [_walk(item, book, identifiers, key=key, parent=parent) for item in value]
    return value


def _string(
    value: str,
    book: PseudonymBook,
    identifiers: IdentifierList,
    *,
    key: str,
    parent: Mapping[str, Any],
) -> str:
    if is_credential_value(value):
        return REMOVED
    kind = _kind_for(key, parent)
    if kind is not None:
        return book.of(kind, value)
    return replace_in_text(value, book, identifiers)


def _kind_for(key: str, parent: Mapping[str, Any]) -> Kind | None:
    folded = key.lower()
    if folded == "name" and _GUEST_MARKERS.intersection(parent):
        return Kind.GUEST
    return _FIELD_KINDS.get(folded)


def _ipv4_replacement(book: PseudonymBook) -> Any:
    def replace(found: re.Match[str]) -> str:
        address = found.group(0)
        octets = address.split(".")
        if any(not part.isdigit() or int(part) > 255 for part in octets):
            return address
        if address.startswith(_ALREADY_RESERVED) or address.startswith(("127.", "0.")):
            return address
        return book.of(Kind.IPV4, address)

    return replace


def _ipv6_replacement(book: PseudonymBook) -> Any:
    def replace(found: re.Match[str]) -> str:
        address = found.group(0)
        if address.lower().startswith(_ALREADY_RESERVED) or address in {"::", "::1"}:
            return address
        return book.of(Kind.IPV6, address)

    return replace


def _url_replacement(book: PseudonymBook) -> Any:
    def replace(found: re.Match[str]) -> str:
        scheme, authority = found.group(1), found.group(2)
        host, separator, port = authority.rpartition(":")
        if not separator or not port.isdigit():
            host, port = authority, ""
        if host in {"localhost", "127.0.0.1"}:
            return found.group(0)
        pseudonym = book.of(Kind.DOMAIN, host)
        return f"{scheme}://{pseudonym}" + (f":{port}" if port else "")

    return replace


def _private_domains(text: str, book: PseudonymBook) -> str:
    def replace(found: re.Match[str]) -> str:
        return book.of(Kind.DOMAIN, found.group(0))

    pattern = re.compile(
        r"\b[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?"
        r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)*"
        r"(?:" + "|".join(re.escape(suffix) for suffix in _PRIVATE_SUFFIXES) + r")\b"
    )
    return pattern.sub(replace, text)


def dropped_fields(document: Any, path: str = "") -> tuple[str, ...]:
    """Return the pointers of every field this pass removed, for the capture report."""
    found: list[str] = []
    if isinstance(document, Mapping):
        for name, value in document.items():
            here = f"{path}/{name}"
            if value == REMOVED:
                found.append(here)
            else:
                found.extend(dropped_fields(value, here))
    elif isinstance(document, Sequence) and not isinstance(document, str | bytes):
        for index, item in enumerate(document):
            found.extend(dropped_fields(item, f"{path}/{index}"))
    return tuple(found)


__all__ = [
    "CREDENTIAL_FIELD_FRAGMENTS",
    "CREDENTIAL_VALUE_PATTERNS",
    "REMOVED",
    "anonymise",
    "dropped_fields",
    "is_credential_field",
    "is_credential_value",
    "should_remove",
    "replace_in_text",
]
