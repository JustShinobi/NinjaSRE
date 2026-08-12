"""Gemini's credential shape, host, and how its key enters a request.

A console could store a provider key and nothing could read it. The vault held
it, the vault's ``reveal`` is the credential proxy's to call and nobody else's,
and the proxy had no rule for any language-model provider — so the key went in
and stopped there, while the model client read an environment variable. That is
the one place Article IV says a credential must never be, and it is where the
most sensitive credential in the system was living.

So the provider is declared like every other integration. The key then works
because it was stored, rather than working because it was also exported.

**A header, not the query string.** Gemini accepts both. A query string reaches
access logs, proxy logs and referrer headers, and a key that has been written to
a log is a key that has to be rotated.
"""

from __future__ import annotations

from typing import Final

from integrations._base.regions import RegionMap
from integrations._base.schema import credential_schema, secret
from platform.credentials.proxy.injection import HeaderInjection, InjectionRule

#: The name a stored credential already carries. A rule under any other spelling
#: leaves the stored key unreadable, which is the defect this closes.
INTEGRATION: Final = "google_gemini"

#: Where the API is served. One host, exact: the allow-list is what stops a
#: compromised prompt sending the key somewhere else.
DEFAULT_HOST: Final = "generativelanguage.googleapis.com"

REGIONS: Final = RegionMap.single(INTEGRATION, host=DEFAULT_HOST, name="global")

#: The egress allow-list, which is the region map rather than a second tuple.
HOSTS: Final[tuple[str, ...]] = REGIONS.hosts()

SCHEMA: Final = credential_schema(
    INTEGRATION,
    secret(
        "api_key",
        "The API key from Google AI Studio. Sent as x-goog-api-key on every request.",
        min_length=8,
    ),
)

RULE: Final = InjectionRule(
    integration=INTEGRATION,
    hosts=HOSTS,
    injections=(HeaderInjection(header="x-goog-api-key", field="api_key"),),
)

__all__ = ["DEFAULT_HOST", "HOSTS", "INTEGRATION", "REGIONS", "RULE", "SCHEMA"]
