"""One declaration per vendor, and the thing the catalogue-wide test walks.

An integration has to answer four questions before it can make an authenticated
call: what its credential is made of, which hosts it may reach, how the secret
enters the request, and how to check that the credential actually works. A
descriptor is those four answers in one object, declared beside the vendor it
describes.

Bundling them is what makes SC-002 assertable. "Every integration routes through
the proxy" is not a property anybody can inspect across eighty-five packages; it
is a property a test can check by walking the tree and finding a descriptor,
with a client that sits on the base class, in each one. An integration that
forgot fails the day it lands rather than the day somebody audits.

``sdk_strategy`` records FR-018's decision per vendor. The table has four rows
and three of them are fine; the fourth is not a row, it is the absence of one.
There is no in-process-credential exception, so a vendor SDK that cannot be
routed through the proxy gets replaced by a direct client on
``integrations/_base/client.py`` rather than an argument about how this one is
different.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

from platform.credentials.proxy.injection import InjectionRule
from platform.credentials.schemas import CredentialSchema


class SdkStrategy(StrEnum):
    """Which row of FR-018's table this vendor's client sits on.

    ``NO_EXCEPTION_GRANTED`` is not a strategy an integration may declare; it is
    the fourth row of the table written down so the absence is explicit. A
    vendor SDK that insists on holding the key in-process is not accepted, and
    the honest way to record that is a name for the thing nobody may choose.
    """

    #: The SDK accepts a custom transport or base URL, so it is pointed at the
    #: proxy and keeps working. Preferred, because the vendor keeps maintaining
    #: the dialect.
    ROUTED_SDK = "routed_sdk"
    #: The SDK signs internally with an in-process key. The client sends an
    #: unsigned request and the proxy signs it (AWS, Azure, Google).
    PROXY_SIGNED = "proxy_signed"
    #: The SDK was thin over REST and buys less than the base client already
    #: provides, so there is no SDK.
    DIRECT_CLIENT = "direct_client"
    #: Written down to be refused. See the class docstring.
    NO_EXCEPTION_GRANTED = "no_exception_granted"


@runtime_checkable
class IntegrationVerifier(Protocol):
    """Checks that a stored credential actually works, end to end (FR-021).

    An operator whose integration is failing wants to know whether the
    credential is wrong, and the only honest way to answer is to use it. The
    verifier makes one cheap, read-only call through the proxy and reports what
    the vendor said — which is what an operator actually needs, as opposed to
    being shown the key and asked to eyeball it.
    """

    @property
    def integration(self) -> str:
        """Return the integration this verifier checks."""


@dataclass(frozen=True, slots=True)
class IntegrationDescriptor:
    """Everything the platform needs to know about one vendor's credentials.

    Declared in the vendor's own package and collected by walking the tree, so
    adding an integration is one package and no edit anywhere else. That is the
    property that has to hold for a catalogue of eighty-five to be addable one
    at a time, and it is why there is no registry module to remember to update.
    """

    name: str
    schema: CredentialSchema
    rule: InjectionRule
    verifier: IntegrationVerifier
    client_class: type
    sdk_strategy: SdkStrategy
    strategy_note: str

    def __post_init__(self) -> None:
        if self.schema.integration != self.name:
            raise ValueError(
                f"the descriptor for {self.name!r} carries a credential schema for "
                f"{self.schema.integration!r}"
            )
        if self.rule.integration != self.name:
            raise ValueError(
                f"the descriptor for {self.name!r} carries an injection rule for "
                f"{self.rule.integration!r}"
            )
        if self.sdk_strategy is SdkStrategy.NO_EXCEPTION_GRANTED:
            raise ValueError(
                f"{self.name!r} declares the strategy that exists to be refused. There is "
                f"no in-process-credential exception; route the SDK through the proxy, "
                f"sign proxy-side, or write a direct client."
            )
        if not self.strategy_note.strip():
            raise ValueError(
                f"{self.name!r} declares an SDK strategy with no rationale, which is a "
                f"decision nobody can review"
            )

    def undeclared_injection_fields(self) -> tuple[str, ...]:
        """Return injection fields the credential schema does not declare.

        Empty is correct. A non-empty answer means the schema and the rule have
        drifted — almost always a field rename on one side — and the symptom
        would otherwise be an unauthenticated request and a 401 nobody can
        explain.
        """
        declared = set(self.schema.field_names)
        return tuple(sorted(set(self.rule.required_fields()) - declared))


__all__ = [
    "IntegrationDescriptor",
    "IntegrationVerifier",
    "SdkStrategy",
]
