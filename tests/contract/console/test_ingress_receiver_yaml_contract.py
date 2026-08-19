"""The Alertmanager receiver block: paste-ready, and never a place a secret rides.

``GET /v1/ingress/sources`` is the sentence this deployment hands an operator
for "what do I paste into my alert router" (see that route's own module
docstring). For the Alertmanager source specifically it now carries the
``webhook_configs`` block verbatim — this deployment's own delivery URL, and
the authorization header naming the delivery token in use, never carrying a
value. A delivery token is never read back once it is issued (the store holds
a hash), so this route has no secret to leak even by mistake. This file makes
that structural rather than incidental, by pinning the generator's own
signature closed and reading its output the way an operator's alert router
would.
"""

from __future__ import annotations

import inspect

import yaml

from gateway.http.routes.ingress import IngressSourceView
from gateway.webhooks.sources.alertmanager import receiver_yaml

_URL = "http://192.168.68.74:8420/webhooks/alertmanager"
_TOKEN_NAME = "Alert delivery"


def test_ingress_source_view_declares_a_receiver_yaml_field() -> None:
    assert "receiver_yaml" in IngressSourceView.model_fields, (
        "IngressSourceView has no receiver_yaml field; a screen offering "
        "'Copy Alertmanager receiver YAML' has nothing to read it from"
    )


def test_the_generated_block_is_a_pasteable_webhook_configs_entry() -> None:
    block = receiver_yaml(url=_URL, token_name=_TOKEN_NAME)

    parsed = yaml.safe_load(block)
    assert isinstance(parsed, dict) and "webhook_configs" in parsed, (
        "the copied content is not a webhook_configs block"
    )
    entry = parsed["webhook_configs"][0]
    assert entry["url"] == _URL


def test_the_block_names_the_delivery_token_in_use() -> None:
    block = receiver_yaml(url=_URL, token_name=_TOKEN_NAME)
    assert _TOKEN_NAME in block, (
        "the receiver block does not name the delivery token in use; an operator pasting "
        "this has no way to find which Machine token authenticates it"
    )


def test_the_credential_field_is_an_explicit_marker_never_a_value() -> None:
    """FR-058: outside the issuance gesture, the value's place holds a marker,
    never a secret — and this route can never hold a secret to begin with."""
    block = receiver_yaml(url=_URL, token_name=_TOKEN_NAME)
    parsed = yaml.safe_load(block)
    credentials = parsed["webhook_configs"][0]["http_config"]["authorization"]["credentials"]

    assert isinstance(credentials, str)
    assert _TOKEN_NAME in credentials
    # A marker reads as a sentence an operator follows, not as a token shape a
    # real secret might have — the two must never be visually interchangeable.
    assert " " in credentials.strip()


def test_the_generator_s_signature_carries_no_parameter_a_secret_could_travel_through() -> None:
    """A token's raw value is never available to this route to begin with, but
    this closes the door structurally: nobody can pass one through even by
    accident, because there is no parameter for it to occupy.
    """
    parameters = set(inspect.signature(receiver_yaml).parameters)
    assert parameters == {"url", "token_name"}, (
        f"receiver_yaml declares {parameters}, not exactly {{'url', 'token_name'}}; a "
        f"receiver generator with anywhere to carry a raw credential value is exactly what "
        f"this test exists to catch"
    )
