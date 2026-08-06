"""SigV4, anchored to AWS's own published worked example.

The failure mode of a signing implementation is producing a *plausible*
signature that AWS rejects with a message blaming the key, so a test that only
checks the code agrees with itself is worth very little. The anchor is
``test_the_derived_key_matches_the_published_example``: AWS's documentation
prints the exact key bytes for one secret, date, region, and service, and the
four chained HMACs either produce them or the implementation is wrong.

The full ``get-vanilla`` signature from AWS's test suite is deliberately *not*
asserted, and the reason is worth stating rather than looking like an omission.
That case signs ``host;x-amz-date`` only, while this signer always includes
``x-amz-content-sha256`` — AWS accepts it everywhere and several services
require it, so signing without it would be the narrower and more surprising
choice. The signed-header list is asserted instead, which is the part that would
change if that decision were ever reversed by accident.

The rest of the file covers what is easy to get subtly wrong and impossible to
notice: an empty payload hashes to a constant, canonical headers are lowercased
and whitespace-collapsed, and query parameters are sorted after encoding.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest

from platform.credentials.proxy.model import OutboundRequest
from platform.credentials.proxy.signing.sigv4 import (
    ALGORITHM,
    AMZ_CONTENT_SHA256_HEADER,
    AMZ_DATE_HEADER,
    AMZ_SECURITY_TOKEN_HEADER,
    EMPTY_PAYLOAD_HASH,
    SigV4Signer,
    canonical_headers,
    canonical_query,
    canonical_uri,
    signing_key,
)
from platform.credentials.proxy.signing.vendor import (
    GOOGLE_QUOTA_PROJECT_HEADER,
    MS_DATE_HEADER,
    AzureSharedKeySigner,
    GoogleAccessTokenSigner,
)

pytestmark = pytest.mark.unit

#: The credentials and timestamp from AWS's published signing examples.
EXAMPLE_ACCESS_KEY = "AKIDEXAMPLE"
EXAMPLE_SECRET = "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY"
EXAMPLE_AT = datetime(2015, 8, 30, 12, 36, 0, tzinfo=UTC)
EXAMPLE_REGION = "us-east-1"
EXAMPLE_SERVICE = "service"

VALUES = {
    "access_key_id": EXAMPLE_ACCESS_KEY,
    "secret_access_key": EXAMPLE_SECRET,
    "region": EXAMPLE_REGION,
}


def test_the_derived_key_matches_the_published_example() -> None:
    """AWS's documentation prints these exact key bytes for these exact inputs.

    The anchor for everything else here. If the four chained HMACs are wrong in
    any way — order, encoding, the ``AWS4`` prefix — this is where it shows,
    rather than as a signature AWS rejects for reasons it will not explain.
    """
    derived = signing_key(EXAMPLE_SECRET, date_stamp="20120215", region="us-east-1", service="iam")

    assert derived.hex() == "f4780e2d9f65fa895f9c67b32ce1baf0b0d8a43505a000a1a9e090d414db404d"


def test_a_signed_request_carries_a_correctly_scoped_authorization_header() -> None:
    """AWS's ``get-vanilla`` request, with the scope and signed headers asserted.

    The signed-header list is the assertion that matters: it is what says the
    payload hash is covered, and it is what would change silently if somebody
    dropped ``x-amz-content-sha256`` to match the test suite's narrower case.
    """
    signer = SigV4Signer(service=EXAMPLE_SERVICE)
    request = OutboundRequest(method="GET", url="https://example.amazonaws.com/", headers={})

    signed = signer.sign(request, VALUES, now=EXAMPLE_AT)

    authorization = signed.headers["Authorization"]
    assert authorization.startswith(f"{ALGORITHM} ")
    assert (
        f"Credential={EXAMPLE_ACCESS_KEY}/20150830/{EXAMPLE_REGION}/{EXAMPLE_SERVICE}/aws4_request"
        in authorization
    )
    assert "SignedHeaders=host;x-amz-content-sha256;x-amz-date" in authorization
    assert "Signature=" in authorization


def test_the_signer_writes_the_date_rather_than_trusting_a_caller() -> None:
    """A caller date that disagrees with the scope produces an error blaming the key."""
    signed = SigV4Signer(service=EXAMPLE_SERVICE).sign(
        OutboundRequest(
            method="GET",
            url="https://example.amazonaws.com/",
            headers={AMZ_DATE_HEADER: "19990101T000000Z"},
        ),
        VALUES,
        now=EXAMPLE_AT,
    )

    assert signed.headers[AMZ_DATE_HEADER] == "20150830T123600Z"


def test_an_empty_payload_hashes_to_the_constant_aws_expects() -> None:
    signed = SigV4Signer(service=EXAMPLE_SERVICE).sign(
        OutboundRequest(method="GET", url="https://example.amazonaws.com/", headers={}),
        VALUES,
        now=EXAMPLE_AT,
    )

    assert signed.headers[AMZ_CONTENT_SHA256_HEADER] == EMPTY_PAYLOAD_HASH
    assert hashlib.sha256(b"").hexdigest() == EMPTY_PAYLOAD_HASH


def test_a_body_is_hashed_into_the_signature() -> None:
    body = b'{"limit": 1}'

    signed = SigV4Signer(service="logs").sign(
        OutboundRequest(
            method="POST", url="https://logs.us-east-1.amazonaws.com/", headers={}, body=body
        ),
        VALUES,
        now=EXAMPLE_AT,
    )

    assert signed.headers[AMZ_CONTENT_SHA256_HEADER] == hashlib.sha256(body).hexdigest()


def test_a_session_token_is_signed_and_sent() -> None:
    """Temporary credentials are three parts, and omitting the third fails opaquely."""
    signed = SigV4Signer(service=EXAMPLE_SERVICE).sign(
        OutboundRequest(method="GET", url="https://example.amazonaws.com/", headers={}),
        {**VALUES, "session_token": "the-session-token"},
        now=EXAMPLE_AT,
    )

    assert signed.headers[AMZ_SECURITY_TOKEN_HEADER] == "the-session-token"
    assert "x-amz-security-token" in signed.headers["Authorization"]


def test_two_signatures_over_the_same_request_agree() -> None:
    signer = SigV4Signer(service=EXAMPLE_SERVICE)
    request = OutboundRequest(method="GET", url="https://example.amazonaws.com/x", headers={})

    first = signer.sign(request, VALUES, now=EXAMPLE_AT)
    second = signer.sign(request, VALUES, now=EXAMPLE_AT)

    assert first.headers["Authorization"] == second.headers["Authorization"]


def test_a_different_body_produces_a_different_signature() -> None:
    signer = SigV4Signer(service=EXAMPLE_SERVICE)
    base = OutboundRequest(method="POST", url="https://example.amazonaws.com/", headers={})

    one = signer.sign(base.with_body(b"a"), VALUES, now=EXAMPLE_AT)
    two = signer.sign(base.with_body(b"b"), VALUES, now=EXAMPLE_AT)

    assert one.headers["Authorization"] != two.headers["Authorization"]


def test_signing_without_a_region_anywhere_is_refused() -> None:
    """AWS has no sane default region, so guessing one would be a silent wrong answer."""
    with pytest.raises(ValueError, match="needs a region"):
        SigV4Signer(service=EXAMPLE_SERVICE).sign(
            OutboundRequest(method="GET", url="https://example.amazonaws.com/", headers={}),
            {"access_key_id": EXAMPLE_ACCESS_KEY, "secret_access_key": EXAMPLE_SECRET},
            now=EXAMPLE_AT,
        )


def test_an_integration_may_declare_the_region_the_credential_omits() -> None:
    signed = SigV4Signer(service="logs", default_region="eu-west-1").sign(
        OutboundRequest(method="GET", url="https://logs.eu-west-1.amazonaws.com/", headers={}),
        {"access_key_id": EXAMPLE_ACCESS_KEY, "secret_access_key": EXAMPLE_SECRET},
        now=EXAMPLE_AT,
    )

    assert "/eu-west-1/logs/aws4_request" in signed.headers["Authorization"]


# -- the canonicalisation pieces ----------------------------------------------


def test_an_empty_path_canonicalises_to_a_slash() -> None:
    assert canonical_uri("") == "/"


def test_a_path_keeps_its_separators_when_encoded() -> None:
    """Encoding ``/`` would turn a path into one segment and sign the wrong resource."""
    assert canonical_uri("/a b/c") == "/a%20b/c"


def test_query_parameters_are_sorted_and_encoded() -> None:
    assert canonical_query("b=2&a=1") == "a=1&b=2"
    assert canonical_query("k=a b") == "k=a%20b"


def test_a_parameter_with_no_value_keeps_its_equals_sign() -> None:
    assert canonical_query("flag") == "flag="


def test_canonical_headers_are_lowercased_sorted_and_collapsed() -> None:
    block, signed = canonical_headers({"Host": "x", "X-Amz-Date": "  a   b  "})

    assert block == "host:x\nx-amz-date:a b\n"
    assert signed == "host;x-amz-date"


# -- the other vendor schemes -------------------------------------------------


def test_azure_shared_key_signs_with_the_account_key() -> None:
    signed = AzureSharedKeySigner(api_version="2021-08-06").sign(
        OutboundRequest(method="GET", url="https://acct.blob.core.windows.net/c/b", headers={}),
        {"account_name": "acct", "account_key": "c2VjcmV0LWtleS1ieXRlcw=="},
        now=datetime(2026, 8, 6, 12, 0, tzinfo=UTC),
    )

    assert signed.headers["Authorization"].startswith("SharedKey acct:")
    assert signed.headers[MS_DATE_HEADER] == "Thu, 06 Aug 2026 12:00:00 GMT"


def test_azure_signatures_differ_by_resource() -> None:
    signer = AzureSharedKeySigner(api_version="2021-08-06")
    values = {"account_name": "acct", "account_key": "c2VjcmV0LWtleS1ieXRlcw=="}
    at = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)

    one = signer.sign(
        OutboundRequest(method="GET", url="https://acct.blob.core.windows.net/a", headers={}),
        values,
        now=at,
    )
    two = signer.sign(
        OutboundRequest(method="GET", url="https://acct.blob.core.windows.net/b", headers={}),
        values,
        now=at,
    )

    assert one.headers["Authorization"] != two.headers["Authorization"]


def test_a_google_token_rides_in_an_ordinary_bearer_header() -> None:
    """The private key stays with the refresher; placing the token is all that is left."""
    signed = GoogleAccessTokenSigner().sign(
        OutboundRequest(method="GET", url="https://monitoring.googleapis.com/v3", headers={}),
        {"access_token": "ya29.the-token", "quota_project_id": "acme-prod"},
        now=datetime(2026, 8, 6, tzinfo=UTC),
    )

    assert signed.headers["Authorization"] == "Bearer ya29.the-token"
    assert signed.headers[GOOGLE_QUOTA_PROJECT_HEADER] == "acme-prod"


def test_the_quota_project_header_is_omitted_when_there_is_none() -> None:
    signed = GoogleAccessTokenSigner().sign(
        OutboundRequest(method="GET", url="https://monitoring.googleapis.com/v3", headers={}),
        {"access_token": "ya29.the-token"},
        now=datetime(2026, 8, 6, tzinfo=UTC),
    )

    assert GOOGLE_QUOTA_PROJECT_HEADER not in signed.headers
