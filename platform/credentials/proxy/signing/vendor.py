"""Signing schemes that are not SigV4, kept beside it for the same reason.

Two more vendors construct a signature rather than attaching a token, and both
need the secret at construction time, so both belong on the proxy side.

**Azure shared key.** A canonicalised string over the verb, a fixed run of
standard headers, the ``x-ms-*`` headers, and the resource path, HMAC-SHA256 with
a base64 account key. Used by Azure Storage and by every service that copied it.

**Google service accounts.** Not a signature over the request at all: the
credential is exchanged for a short-lived access token which then rides in an
ordinary bearer header. The exchange is the part that needs the private key, so
it belongs to the refresher; what is left here is placing the token and the
quota project, which the vendor wants in a header of its own.

There is a general point in that difference. "Signing" is not one operation, and
the way to keep every integration from inventing its own is to make
each scheme a declared ``RequestSigner`` rather than a branch inside the engine.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Final
from urllib.parse import urlsplit

from config.constants.security import GOOGLE_QUOTA_PROJECT_HEADER
from platform.credentials.proxy.injection import AUTHORIZATION_HEADER
from platform.credentials.proxy.model import OutboundRequest

MS_DATE_HEADER: Final = "x-ms-date"
MS_VERSION_HEADER: Final = "x-ms-version"
MS_HEADER_PREFIX: Final = "x-ms-"

#: RFC 1123, which is what Azure's canonical string wants and what it rejects
#: anything else for.
HTTP_DATE_FORMAT: Final = "%a, %d %b %Y %H:%M:%S GMT"

#: The header names Azure's canonical string includes in a fixed order, whether
#: or not the request carries them. An absent one contributes an empty line, and
#: getting the count wrong shifts everything after it.
_CANONICAL_STANDARD_HEADERS: Final[tuple[str, ...]] = (
    "content-encoding",
    "content-language",
    "content-length",
    "content-md5",
    "content-type",
    "date",
    "if-modified-since",
    "if-match",
    "if-none-match",
    "if-unmodified-since",
    "range",
)


@dataclass(frozen=True, slots=True)
class AzureSharedKeySigner:
    """Azure's shared-key scheme, over the canonicalised request.

    ``api_version`` is declared by the integration rather than defaulted here.
    Azure's canonical string includes the version header, so a signer that
    guessed would produce signatures that stop verifying the day the account is
    configured for a different one.
    """

    api_version: str
    account_field: str = "account_name"
    key_field: str = "account_key"

    def fields(self) -> tuple[str, ...]:
        """Return the credential fields this scheme needs."""
        return (self.account_field, self.key_field)

    def sign(
        self,
        request: OutboundRequest,
        values: Mapping[str, str],
        *,
        now: datetime,
    ) -> OutboundRequest:
        """Return ``request`` carrying an ``Authorization: SharedKey`` header."""
        account = values[self.account_field]
        key = base64.b64decode(values[self.key_field])

        headers = dict(request.headers)
        headers[MS_DATE_HEADER] = now.strftime(HTTP_DATE_FORMAT)
        headers[MS_VERSION_HEADER] = self.api_version

        lowered = {name.lower(): value for name, value in headers.items()}
        standard = "\n".join(
            _azure_standard_value(lowered, name) for name in _CANONICAL_STANDARD_HEADERS
        )
        custom = "".join(
            f"{name}:{' '.join(value.split())}\n"
            for name, value in sorted(lowered.items())
            if name.startswith(MS_HEADER_PREFIX)
        )

        split = urlsplit(request.url)
        resource = f"/{account}{split.path}"
        if split.query:
            resource += "\n" + "\n".join(
                f"{name}:{value}"
                for name, _, value in sorted(part.partition("=") for part in split.query.split("&"))
            )

        to_sign = f"{request.method.upper()}\n{standard}\n{custom}{resource}"
        signature = base64.b64encode(
            hmac.new(key, to_sign.encode("utf-8"), hashlib.sha256).digest()
        ).decode("ascii")
        headers[AUTHORIZATION_HEADER] = f"SharedKey {account}:{signature}"
        return request.with_headers(headers)


@dataclass(frozen=True, slots=True)
class GoogleAccessTokenSigner:
    """Places a Google access token and, when configured, the quota project.

    The token itself comes from the refresher, which is what exchanges a service
    account's private key for one. Splitting it that way keeps the private key
    on the refresher's side of the proxy and means a token that expires
    mid-request is handled by the same single-retry path as every other
    short-lived credential.
    """

    token_field: str = "access_token"
    quota_project_field: str = "quota_project_id"

    def fields(self) -> tuple[str, ...]:
        """Return the credential fields this scheme needs."""
        return (self.token_field,)

    def sign(
        self,
        request: OutboundRequest,
        values: Mapping[str, str],
        *,
        now: datetime,
    ) -> OutboundRequest:
        """Return ``request`` carrying the bearer token and quota project."""
        headers = {AUTHORIZATION_HEADER: f"Bearer {values[self.token_field]}"}
        quota_project = values.get(self.quota_project_field, "")
        if quota_project:
            headers[GOOGLE_QUOTA_PROJECT_HEADER] = quota_project
        return request.with_headers(headers)


def _azure_standard_value(headers: Mapping[str, str], name: str) -> str:
    """Return the canonical value of one standard header.

    ``content-length`` of zero is written as an empty string. Azure changed that
    rule between API versions and signing a literal ``0`` fails on every current
    one, which is a two-hour debugging session that this line prevents.
    """
    value = headers.get(name, "")
    if name == "content-length" and value == "0":
        return ""
    return value


__all__ = [
    "HTTP_DATE_FORMAT",
    "MS_DATE_HEADER",
    "MS_VERSION_HEADER",
    "AzureSharedKeySigner",
    "GoogleAccessTokenSigner",
]
