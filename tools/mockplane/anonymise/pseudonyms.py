"""Stable pseudonyms: one real value, one replacement, everywhere it appears.

Three properties, and losing any one of them loses the dataset.

**Deterministic.** The same input yields the same pseudonym on every run, so two
runs of the pipeline are byte-identical and a visual-regression baseline
compares code against code rather than clock against clock.

**Consistent.** One real entity maps to one pseudonym across every file, so the
references between records survive. Random renaming would produce a dataset
where a run named resources that no longer existed.

**Not reversible.** The mapping is derived under a key the operator supplies and
never commits, and it is not derivable from the output. A committed map would
make the whole exercise theatre.

Addresses are drawn from the ranges the standards reserve for documentation, so
a pseudonym is not merely unlikely to be somebody's address — it cannot be.
"""

from __future__ import annotations

import hmac
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from hashlib import sha256
from typing import Final

from config.constants.fixtures import NINJASRE_PSEUDONYM_KEY_ENV


class MissingPseudonymKey(RuntimeError):
    """No key was supplied, so nothing can be pseudonymised."""


class Kind(StrEnum):
    """What sort of thing is being replaced, which decides what it is replaced with."""

    NODE = "node"
    HOST = "host"
    GUEST = "guest"
    STORAGE = "storage"
    POOL = "pool"
    CLUSTER = "cluster"
    PERSON = "person"
    PRINCIPAL = "principal"
    TEAM = "team"
    EMAIL = "email"
    DOMAIN = "domain"
    IPV4 = "ipv4"
    IPV6 = "ipv6"
    MAC = "mac"
    OPAQUE = "opaque"


#: Neutral words, none of them a product, a company or a place. Long enough that
#: an estate of ninety resources gets ninety distinct names before the numeric
#: suffix has to do any work.
_WORDS: Final[tuple[str, ...]] = (
    "alder",
    "amber",
    "anchor",
    "arbour",
    "aspen",
    "basalt",
    "beacon",
    "beryl",
    "birch",
    "bramble",
    "brook",
    "cairn",
    "cedar",
    "cinder",
    "cobalt",
    "copper",
    "coral",
    "cove",
    "crag",
    "cypress",
    "delta",
    "dune",
    "ember",
    "fathom",
    "fennel",
    "fjord",
    "flint",
    "garnet",
    "gable",
    "granite",
    "harbour",
    "hazel",
    "heather",
    "hollow",
    "indigo",
    "ivory",
    "jasper",
    "juniper",
    "kelp",
    "lagoon",
    "larch",
    "laurel",
    "ledger",
    "linen",
    "lumen",
    "maple",
    "marble",
    "meadow",
    "mesa",
    "mica",
    "mint",
    "moss",
    "nickel",
    "nimbus",
    "oakum",
    "obsidian",
    "onyx",
    "opal",
    "orchard",
    "osprey",
    "pebble",
    "pewter",
    "pine",
    "plateau",
    "poplar",
    "quarry",
    "quartz",
    "quill",
    "ridge",
    "rowan",
    "rushes",
    "saffron",
    "sable",
    "sandstone",
    "sequoia",
    "shale",
    "shingle",
    "silver",
    "slate",
    "sorrel",
    "spruce",
    "stellar",
    "stone",
    "sumac",
    "tamarisk",
    "teal",
    "thicket",
    "thistle",
    "timber",
    "topaz",
    "tundra",
    "umber",
    "vale",
    "verdant",
    "vellum",
    "walnut",
    "willow",
    "yarrow",
    "zephyr",
    "zinc",
    "zircon",
)

_FIRST_NAMES: Final[tuple[str, ...]] = (
    "Avery",
    "Blair",
    "Cameron",
    "Darcy",
    "Ellis",
    "Frankie",
    "Gale",
    "Harper",
    "Indigo",
    "Jordan",
    "Kai",
    "Lennox",
    "Morgan",
    "Noor",
    "Onyx",
    "Parker",
    "Quinn",
    "Reese",
    "Sage",
    "Tatum",
    "Umber",
    "Vale",
    "Wren",
    "Yael",
)

_LAST_NAMES: Final[tuple[str, ...]] = (
    "Ashford",
    "Bellamy",
    "Calloway",
    "Danforth",
    "Ellery",
    "Fairbourne",
    "Greenhalgh",
    "Halloway",
    "Ingram",
    "Jessop",
    "Kingsley",
    "Lockhart",
    "Merrick",
    "Northcote",
    "Ormsby",
    "Pemberton",
    "Quarrie",
    "Radcliffe",
    "Stannard",
    "Thorne",
    "Underhill",
    "Verity",
    "Westbrook",
    "Yarrow",
)

#: The domain the whole fictional deployment answers on. ``.invalid`` is
#: reserved by the standards and can never resolve, which is a stronger promise
#: than picking something that merely looks made up.
PSEUDONYM_DOMAIN: Final = "example.invalid"


#: What this module's own output looks like, per kind. Used only to recognise a
#: value that has already been through it — never to decide that something is
#: safe to publish.
_PSEUDONYM_SHAPES: Final[Mapping[Kind, re.Pattern[str]]] = {
    Kind.NODE: re.compile(r"^node\d{2}(-\d{3})?$"),
    Kind.HOST: re.compile(r"^[a-z]+-\d{3}$"),
    Kind.GUEST: re.compile(r"^(" + "|".join(_WORDS) + r")(-\d{3})?$"),
    Kind.STORAGE: re.compile(r"^store-[a-z]+(-\d{3})?$"),
    Kind.POOL: re.compile(r"^pool-[a-z]+(-\d{3})?$"),
    Kind.CLUSTER: re.compile(r"^cluster-[a-z]+(-\d{3})?$"),
    Kind.TEAM: re.compile(r"^team-[a-z]+(-\d{3})?$"),
    Kind.PRINCIPAL: re.compile(r"^user-[a-z]+(-\d{3})?$"),
    Kind.EMAIL: re.compile(r"^[^@\s]+@" + re.escape(PSEUDONYM_DOMAIN) + r"$"),
    Kind.DOMAIN: re.compile(r"^[a-z0-9.-]*" + re.escape(PSEUDONYM_DOMAIN) + r"$"),
    Kind.IPV4: re.compile(r"^198\.51\.100\.\d{1,3}$"),
    Kind.IPV6: re.compile(r"^2001:db8:"),
    Kind.MAC: re.compile(r"^02:"),
    Kind.PERSON: re.compile(
        r"^(" + "|".join(_FIRST_NAMES) + r") (" + "|".join(_LAST_NAMES) + r")(-\d{3})?$"
    ),
    Kind.OPAQUE: re.compile(r"^[a-z]+-[a-z]+-\d{3}$"),
}


def looks_pseudonymous(kind: Kind, value: str) -> bool:
    """Return whether ``value`` is already in the shape this module mints for ``kind``."""
    pattern = _PSEUDONYM_SHAPES.get(kind)
    return bool(pattern and pattern.match(value))


@dataclass(slots=True)
class PseudonymBook:
    """Every replacement made so far, and the key that decides them.

    Held rather than recomputed so a collision — two real values that would map
    to the same pseudonym — is detected and resolved, rather than silently
    merging two entities into one.
    """

    key: bytes
    #: Leave a value that is already in this book's own output shape alone.
    #:
    #: Only the committed dataset sets this, and it is what makes the pipeline a
    #: fixed point over its own output: the field map recognises ``node`` and
    #: does not recognise ``name``, so a second pass over an already-pseudonymous
    #: estate would rename a node under one key and not the other and leave the
    #: dataset disagreeing with itself.
    #:
    #: It is off for a capture, and must stay off, because a real deployment may
    #: genuinely have a node called ``node01`` — and passing that through would
    #: be a leak. The committed dataset's inputs never held a real value, which
    #: is the only reason this is safe there.
    already_pseudonymous: bool = False
    _forward: dict[tuple[Kind, str], str] = field(default_factory=dict)
    _taken: dict[Kind, set[str]] = field(default_factory=dict)

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> PseudonymBook:
        """Return a book keyed by the operator's key.

        Raises:
            MissingPseudonymKey: nothing supplied one. There is no default, on
                purpose: a default key is a published key.
        """
        source = dict(environ if environ is not None else os.environ)
        raw = source.get(NINJASRE_PSEUDONYM_KEY_ENV, "").strip()
        if not raw:
            raise MissingPseudonymKey(
                f"set {NINJASRE_PSEUDONYM_KEY_ENV} to the key this dataset is pseudonymised "
                f"under; it stays with you, and without it the output is not reversible"
            )
        return cls(key=raw.encode())

    def of(self, kind: Kind, value: str) -> str:
        """Return the stable pseudonym for ``value``, minting one if this is the first sight."""
        if not value:
            return value
        remembered = self._forward.get((kind, value))
        if remembered is not None:
            return remembered
        if self.already_pseudonymous and looks_pseudonymous(kind, value):
            return value
        taken = self._taken.setdefault(kind, set())
        for attempt in range(1024):
            candidate = self._mint(kind, value, attempt)
            if candidate not in taken:
                taken.add(candidate)
                self._forward[(kind, value)] = candidate
                return candidate
        raise RuntimeError(f"could not find a free pseudonym for a {kind.value} after 1024 tries")

    def known(self) -> Mapping[tuple[Kind, str], str]:
        """Return every replacement made, for a caller that has to invert one locally."""
        return dict(self._forward)

    def _digest(self, kind: Kind, value: str, attempt: int) -> bytes:
        message = f"{kind.value}\x00{value}\x00{attempt}".encode()
        return hmac.new(self.key, message, sha256).digest()

    def _mint(self, kind: Kind, value: str, attempt: int) -> str:
        digest = self._digest(kind, value, attempt)
        number = int.from_bytes(digest[:8], "big")
        word = _WORDS[number % len(_WORDS)]
        second = _WORDS[(number // len(_WORDS)) % len(_WORDS)]
        ordinal = (number // 65_536) % 900 + 100

        # A hundred words is a hundred names, and an estate of ninety guests all
        # but exhausts them. Once a word has been taken, later attempts qualify
        # it with a number rather than drawing again from the same hundred —
        # which is what stops a large estate running out of names entirely.
        suffix = "" if attempt == 0 else f"-{ordinal:03d}"

        match kind:
            case Kind.NODE:
                return f"node{ordinal % 90 + 1:02d}{suffix}"
            case Kind.HOST:
                return f"{word}-{ordinal:03d}"
            case Kind.GUEST:
                return f"{word}{suffix}"
            case Kind.STORAGE:
                return f"store-{word}{suffix}"
            case Kind.POOL:
                return f"pool-{word}{suffix}"
            case Kind.CLUSTER:
                return f"cluster-{word}{suffix}"
            case Kind.TEAM:
                return f"team-{word}{suffix}"
            case Kind.PERSON:
                first = _FIRST_NAMES[number % len(_FIRST_NAMES)]
                last = _LAST_NAMES[(number // len(_FIRST_NAMES)) % len(_LAST_NAMES)]
                return f"{first} {last}{suffix}"
            case Kind.PRINCIPAL:
                # An identifier, not an address. The two are separate kinds
                # because a fixture where a principal id is an e-mail address is
                # a fixture that teaches the console the wrong shape.
                return f"user-{word}{suffix}"
            case Kind.EMAIL:
                return f"{word}.{second}@{PSEUDONYM_DOMAIN}"
            case Kind.DOMAIN:
                return f"{word}.{PSEUDONYM_DOMAIN}"
            case Kind.IPV4:
                # RFC 5737 TEST-NET-2, reserved for documentation.
                return f"198.51.100.{number % 254 + 1}"
            case Kind.IPV6:
                # RFC 3849, reserved for documentation.
                return f"2001:db8::{number % 65535 + 1:x}"
            case Kind.MAC:
                # Locally administered, so it belongs to no manufacturer.
                tail = digest[:5]
                return "02:" + ":".join(f"{byte:02x}" for byte in tail)
            case Kind.OPAQUE:
                return f"{word}-{second}-{ordinal:03d}"


__all__ = [
    "PSEUDONYM_DOMAIN",
    "looks_pseudonymous",
    "Kind",
    "MissingPseudonymKey",
    "PseudonymBook",
]
