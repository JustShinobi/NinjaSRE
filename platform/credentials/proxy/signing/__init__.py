"""Request-signing schemes, all of them on the proxy side of the boundary.

A signature covers the request and is keyed by the secret, so signing cannot
happen anywhere the secret is not — which is why these live here rather than in
the vendor clients that would otherwise own them. AWS is the case that forces
the issue and the one the whole proxy is worth building for (SC-006).

Each scheme is a ``RequestSigner`` an integration declares in its injection
rule, so adding a vendor with a novel scheme is a class here plus a line there,
and the engine never learns another branch.
"""

from __future__ import annotations

from platform.credentials.proxy.signing.sigv4 import SigV4Signer
from platform.credentials.proxy.signing.vendor import (
    AzureSharedKeySigner,
    GoogleAccessTokenSigner,
)

__all__ = [
    "AzureSharedKeySigner",
    "GoogleAccessTokenSigner",
    "SigV4Signer",
]
