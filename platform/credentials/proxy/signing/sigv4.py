"""AWS Signature Version 4, computed on the proxy side of the boundary.

This module is why the credential proxy is worth building rather than mostly
building. Every other vendor takes a header, and a header can be attached by
something that holds the secret for a microsecond. SigV4 cannot: the signature
covers the method, the canonical URI, the query string, the headers, and a hash
of the body, and it is keyed by a chain derived from the secret access key. A
client that signs is a client that holds a key.

AWS is also the largest integration family an SRE platform has. Leaving SigV4 in
the client would make the most-used vendor the one exception to Article IV,
which is the same as not having Article IV — so the signing moved here, and the
client sends an unsigned request with a handle (SC-006).

The implementation is the specification, in order, with no shortcuts worth
taking:

**Canonical headers are lowercase, sorted, and whitespace-collapsed.** AWS
rejects a signature computed over headers in any other form, and the rejection
message says nothing useful, so the normalisation is done in one place and
tested against the specification's own worked example.

**The payload is always hashed.** Including when it is empty — the hash of the
empty string is a constant AWS expects, not a value that may be omitted.

**``x-amz-date`` is written by the signer.** A caller-supplied date that differs
from the one in the credential scope produces a signature that is internally
inconsistent, and the resulting error blames the key.
"""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Final
from urllib.parse import quote, urlsplit

from platform.credentials.proxy.model import OutboundRequest

ALGORITHM: Final = "AWS4-HMAC-SHA256"
REQUEST_TYPE: Final = "aws4_request"

DATE_FORMAT: Final = "%Y%m%dT%H%M%SZ"
SCOPE_DATE_FORMAT: Final = "%Y%m%d"

AMZ_DATE_HEADER: Final = "x-amz-date"
AMZ_SECURITY_TOKEN_HEADER: Final = "x-amz-security-token"
AMZ_CONTENT_SHA256_HEADER: Final = "x-amz-content-sha256"
AUTHORIZATION_HEADER: Final = "Authorization"

#: SHA-256 of the empty string. AWS expects it verbatim for a body-less request,
#: and computing it per call is the same constant plus a hash.
EMPTY_PAYLOAD_HASH: Final = hashlib.sha256(b"").hexdigest()


def canonical_uri(path: str) -> str:
    """Return the URI-encoded path AWS signs over.

    An empty path is ``/``. Each segment is percent-encoded once, with ``/``
    preserved — encoding it would turn a path into a single segment and the
    signature would cover a resource that does not exist.
    """
    if not path:
        return "/"
    return quote(path, safe="/-._~")


def canonical_query(query: str) -> str:
    """Return the query string in the sorted, encoded form AWS signs over.

    Parameters are sorted by name then by value, and both halves are encoded.
    Sorting by value matters for a repeated parameter, which several AWS APIs
    use for list arguments.
    """
    if not query:
        return ""
    encoded: list[tuple[str, str]] = []
    for part in query.split("&"):
        name, separator, value = part.partition("=")
        encoded.append((quote(name, safe="-._~"), quote(value if separator else "", safe="-._~")))
    return "&".join(f"{name}={value}" for name, value in sorted(encoded))


def canonical_headers(headers: Mapping[str, str]) -> tuple[str, str]:
    """Return the canonical header block and the signed-header list.

    Header names are lowercased and values have runs of whitespace collapsed,
    which is what the specification asks for and what a signature computed from
    the raw values would get wrong for any header a client pretty-printed.
    """
    normalised = {name.lower(): " ".join(value.split()) for name, value in headers.items()}
    names = sorted(normalised)
    block = "".join(f"{name}:{normalised[name]}\n" for name in names)
    return block, ";".join(names)


def _sign(key: bytes, message: str) -> bytes:
    """Return the HMAC-SHA256 of ``message`` under ``key``."""
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()


def signing_key(secret: str, *, date_stamp: str, region: str, service: str) -> bytes:
    """Return the derived key for one date, region, and service.

    Four chained HMACs, each narrowing the key. The point of the chain is that a
    key leaked from one day and one region signs nothing else, which is why it
    is worth doing rather than signing with the secret directly.
    """
    initial = f"AWS4{secret}".encode()
    return _sign(_sign(_sign(_sign(initial, date_stamp), region), service), REQUEST_TYPE)


@dataclass(frozen=True, slots=True)
class SigV4Signer:
    """Signs a request the way AWS expects, using credentials it is handed.

    The field names are configurable because a vendor speaking the S3 dialect —
    MinIO, Ceph, R2 — stores its credentials under its own names, and the
    signing is identical. The service and the region are what actually vary.
    """

    service: str
    region_field: str = "region"
    access_key_field: str = "access_key_id"
    secret_key_field: str = "secret_access_key"
    session_token_field: str = "session_token"
    #: Used when the credential carries no region of its own. AWS has no sane
    #: default region, so this is a declaration by the integration rather than a
    #: guess by the signer.
    default_region: str = ""

    def fields(self) -> tuple[str, ...]:
        """Return the credential fields this scheme needs."""
        return (self.access_key_field, self.secret_key_field)

    def sign(
        self,
        request: OutboundRequest,
        values: Mapping[str, str],
        *,
        now: datetime,
    ) -> OutboundRequest:
        """Return ``request`` carrying an ``Authorization`` header AWS will accept."""
        access_key = values[self.access_key_field]
        secret_key = values[self.secret_key_field]
        session_token = values.get(self.session_token_field, "")
        region = values.get(self.region_field) or self.default_region
        if not region:
            raise ValueError(
                f"signing for {self.service!r} needs a region, and neither the credential "
                f"nor the integration declared one"
            )

        split = urlsplit(request.url)
        body = request.body or b""
        payload_hash = hashlib.sha256(body).hexdigest() if body else EMPTY_PAYLOAD_HASH
        amz_date = now.strftime(DATE_FORMAT)
        date_stamp = now.strftime(SCOPE_DATE_FORMAT)

        headers = dict(request.headers)
        headers["host"] = split.netloc
        headers[AMZ_DATE_HEADER] = amz_date
        headers[AMZ_CONTENT_SHA256_HEADER] = payload_hash
        if session_token:
            headers[AMZ_SECURITY_TOKEN_HEADER] = session_token

        block, signed_headers = canonical_headers(headers)
        canonical_request = "\n".join(
            (
                request.method.upper(),
                canonical_uri(split.path),
                canonical_query(split.query),
                block,
                signed_headers,
                payload_hash,
            )
        )

        scope = f"{date_stamp}/{region}/{self.service}/{REQUEST_TYPE}"
        to_sign = "\n".join(
            (
                ALGORITHM,
                amz_date,
                scope,
                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            )
        )
        signature = hmac.new(
            signing_key(secret_key, date_stamp=date_stamp, region=region, service=self.service),
            to_sign.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        headers[AUTHORIZATION_HEADER] = (
            f"{ALGORITHM} Credential={access_key}/{scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )
        return request.with_headers(headers)


__all__ = [
    "ALGORITHM",
    "AMZ_CONTENT_SHA256_HEADER",
    "AMZ_DATE_HEADER",
    "AMZ_SECURITY_TOKEN_HEADER",
    "EMPTY_PAYLOAD_HASH",
    "REQUEST_TYPE",
    "SigV4Signer",
    "canonical_headers",
    "canonical_query",
    "canonical_uri",
    "signing_key",
]
