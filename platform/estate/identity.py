"""Where a resource's identity comes from, which is not its name.

A display name is the most likely thing about a virtual machine to change and
the least likely thing to be unique. So identity is the source integration plus
the identifier that source uses, hashed into a key that is stable across a
rename, a restart, and a re-discovery — and derivable by any replica without
consulting storage, which is what lets two replicas sweeping at once converge
rather than collide.

The hash is not a security boundary; it is a *shape*. It makes the key fixed
width and URL-safe whatever the provider's identifier looked like, and it keeps
a resource identifier out of the estate's URLs — which matters more than it
looks, because a screenshot of a console URL is the most casually shared
artefact in incident response.
"""

from __future__ import annotations

import hashlib
from typing import Final

from platform.estate.errors import NoStableIdentifier

#: Separates the source from the provider's identifier inside the hashed key. A
#: unit separator, because it cannot occur in an integration name and cannot
#: occur in any provider identifier we have seen — so ``a`` + ``b:c`` and
#: ``a:b`` + ``c`` cannot hash to the same thing.
KEY_SEPARATOR: Final = "\x1f"

#: Marks a string as one of ours in a log line or a URL, and keeps the key from
#: being mistaken for a provider's own identifier.
RESOURCE_ID_PREFIX: Final = "res-"

#: Hex characters kept from the digest. Thirty-two is 128 bits, which is past
#: the point where a collision across an estate is worth reasoning about, and
#: short enough that the whole key fits a console column.
RESOURCE_ID_DIGEST_CHARS: Final[int] = 32


def native_key(source: str, native_id: str) -> str:
    """Return the unhashed identity of a resource, for a caller that needs to compare.

    Exposed rather than kept private because reconciliation compares identities
    without wanting the hash, and a second spelling of the separator is the way
    two parts of this package come to disagree about what is the same resource.
    """
    return f"{source}{KEY_SEPARATOR}{native_id}"


def derive_resource_id(*, source: str, native_id: str) -> str:
    """Return the deployment-stable identity of what ``source`` calls ``native_id``.

    Raises ``NoStableIdentifier`` when either part is missing or blank, rather
    than generating one. A generated identifier would differ on every sweep, so
    every sweep would create the resource again and mark the previous one
    absent — an estate that grows without bound while reporting a
    decommissioning every interval.
    """
    trimmed_source = source.strip()
    trimmed_native = native_id.strip()
    if not trimmed_source:
        raise NoStableIdentifier(source=source, detail="the source integration was not named")
    if not trimmed_native:
        raise NoStableIdentifier(
            source=trimmed_source, detail="the provider-native identifier was empty"
        )

    digest = hashlib.sha256(native_key(trimmed_source, trimmed_native).encode("utf-8")).hexdigest()
    return f"{RESOURCE_ID_PREFIX}{digest[:RESOURCE_ID_DIGEST_CHARS]}"


__all__ = [
    "KEY_SEPARATOR",
    "RESOURCE_ID_DIGEST_CHARS",
    "RESOURCE_ID_PREFIX",
    "derive_resource_id",
    "native_key",
]
