"""What every vendor client is built from, so none of them builds it again.

``IntegrationClient`` is the only sanctioned path for an authenticated external
call (FR-015). A client inherits it and gets proxy routing, retry, timeouts,
rate-limit handling, bounded bodies, and structured errors; what it adds is the
vendor's own paths, payloads, and cursors.

There is no constructor argument here for a credential, and no attribute to hold
one. That is the point: a contributor writing the eighty-fifth integration does
not need to know the security model, because the shape of the base class makes
the wrong thing unspellable rather than discouraged.
"""

from __future__ import annotations

from integrations._base.client import ClientResponse, IntegrationClient
from integrations._base.errors import (
    ErrorCategory,
    IntegrationError,
    IntegrationErrorReason,
    categories,
    category_for,
    reason_for_status,
)
from integrations._base.pagination import (
    EndpointPagination,
    Page,
    Pages,
    PaginationStyle,
    Position,
    collect,
    iterate,
    page_of,
    supported_styles,
    walk,
)
from integrations._base.regions import Region, RegionMap, UnknownRegion
from integrations._base.retry import RetryPolicy, parse_retry_after
from integrations._base.schema import (
    VaultMapping,
    api_key_schema,
    basic_auth_schema,
    bearer_token_schema,
    credential_schema,
    key_pair_schema,
    public,
    secret,
    undeclared_fields,
)
from integrations._base.transport import (
    HttpProxyTransport,
    InProcessProxyTransport,
    ProxyTransport,
    RequestContext,
)

__all__ = [
    "ClientResponse",
    "EndpointPagination",
    "ErrorCategory",
    "HttpProxyTransport",
    "InProcessProxyTransport",
    "IntegrationClient",
    "IntegrationError",
    "IntegrationErrorReason",
    "Page",
    "PaginationStyle",
    "Pages",
    "Position",
    "ProxyTransport",
    "Region",
    "RegionMap",
    "RequestContext",
    "RetryPolicy",
    "UnknownRegion",
    "VaultMapping",
    "api_key_schema",
    "basic_auth_schema",
    "bearer_token_schema",
    "categories",
    "category_for",
    "collect",
    "credential_schema",
    "iterate",
    "key_pair_schema",
    "page_of",
    "parse_retry_after",
    "public",
    "reason_for_status",
    "secret",
    "supported_styles",
    "undeclared_fields",
    "walk",
]
