"""The vendor boundary: recorded responses in, a record of every call out.

This sits exactly where a real vendor sits — behind the capability, behind the
integration client, behind the credential proxy — and it is the only thing in a
scenario run that is not the production path. Mocking any higher would be
cheaper and would prove less: the client's parsing, its pagination, its error
mapping, and the proxy's injection are precisely the layers integration bugs
live in, and a suite that skipped them would go green while the real client was
broken.

Two decisions are load-bearing.

**An unmatched call answers empty-but-valid, never an error** (FR-008). An agent
exploring past the evidence a scenario planted should learn "there is nothing
there", which is a normal thing to learn and leaves the answer key intact. If it
learned "the tool is broken" instead it would change its behaviour — retry,
escalate, hedge the conclusion — in ways the answer key never anticipated, and
the scenario would be measuring the harness.

**Every call is recorded** (FR-010), matched or not. Trajectory scoring is about
what the agent actually did, and a call that returned nothing is still a call it
chose to make.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from platform.credentials.proxy.model import OutboundRequest, OutboundResponse
from tests.harness.loader import EvidenceFixture, RecordedResponse

#: What a vendor with nothing to report answers, for the majority of vendors
#: that speak JSON and whose clients read a document rather than a list.
GENERIC_EMPTY_BODY: Any = {}


def json_response(body: Any, *, status: int = 200) -> OutboundResponse:
    """Return ``body`` as a JSON vendor response."""
    return OutboundResponse(
        status, {"content-type": "application/json"}, json.dumps(body).encode("utf-8")
    )


def xml_response(document: str, *, status: int = 200) -> OutboundResponse:
    """Return ``document`` as an XML vendor response.

    The AWS query-protocol services predate JSON and have no JSON dialect to
    ask for, so their empty answers have to be the shape they really send.
    """
    return OutboundResponse(status, {"content-type": "text/xml"}, document.encode("utf-8"))


def text_response(body: str, *, status: int = 200) -> OutboundResponse:
    """Return ``body`` as a plain-text vendor response."""
    return OutboundResponse(status, {"content-type": "text/plain"}, body.encode("utf-8"))


#: The signature every backend's empty-response function has: it is handed the
#: request so a vendor whose empty document differs per endpoint — a log stream
#: is not a resource list — can answer per endpoint.
EmptyResponder = Callable[[OutboundRequest], OutboundResponse]


def generic_empty(request: OutboundRequest) -> OutboundResponse:
    """Return the empty JSON document, whatever was asked for."""
    return json_response(GENERIC_EMPTY_BODY)


@dataclass(frozen=True, slots=True)
class MockBackend:
    """One integration's vendor, as the harness stands in for it.

    A backend declares two things and nothing else: which integration it speaks
    for, and what that vendor answers when it has nothing to report. Everything
    else a scenario needs comes from its recorded fixtures — which is what makes
    contributing a scenario for an integration that already has a backend a
    matter of fixtures alone.
    """

    integration: str
    empty: EmptyResponder = generic_empty
    #: One line for the recording procedure: where these responses come from.
    recorded_from: str = ""

    def empty_for(self, request: OutboundRequest) -> OutboundResponse:
        """Return this vendor's empty-but-valid answer to ``request``."""
        return self.empty(request)


#: The backend used for a request no registered backend claims. Its empty
#: document is ``{}``, which every JSON client in this repository reads as
#: "nothing to report" rather than as a malformed answer.
GENERIC_BACKEND = MockBackend(integration="", empty=generic_empty)


@dataclass(frozen=True, slots=True)
class VendorCall:
    """One call the agent's stack made to a vendor, and what came back.

    Recorded whether or not a fixture matched. A call that returned nothing is
    still a call the agent chose to make, and a trajectory that shows it looked
    somewhere useless is a different trajectory from one that never looked.
    """

    integration: str
    method: str
    host: str
    path: str
    url: str
    status: int
    matched: bool
    fixture: str = ""


@dataclass(slots=True)
class MockVendorBoundary:
    """The far side of the credential proxy for one scenario run.

    Satisfies the proxy's ``OutboundSender`` port structurally, which is what
    puts it exactly where a real network send would be.
    """

    fixtures: tuple[EvidenceFixture, ...] = ()
    backends: Mapping[str, MockBackend] = field(default_factory=dict)
    #: Vendor host to integration name, so an unmatched call still knows whose
    #: empty document to answer with.
    hosts: Mapping[str, str] = field(default_factory=dict)
    calls: list[VendorCall] = field(default_factory=list)

    async def send(self, request: OutboundRequest, *, timeout_seconds: float) -> OutboundResponse:
        """Return the recorded answer to ``request``, or this vendor's empty one."""
        integration = self.integration_for(request.host)
        matched, fixture = self._best_match(request, integration)

        if matched is None:
            answer = self.backends.get(integration, GENERIC_BACKEND).empty_for(request)
            self._record(request, integration, answer.status_code, matched=False)
            return answer

        self._record(request, integration, matched.status, matched=True, fixture=fixture)
        return OutboundResponse(
            matched.status, {"content-type": matched.content_type}, matched.payload()
        )

    def integration_for(self, host: str) -> str:
        """Return the integration that declared ``host``, or the empty string."""
        return self.hosts.get(host.lower(), "")

    def _best_match(
        self, request: OutboundRequest, integration: str
    ) -> tuple[RecordedResponse | None, str]:
        """Return the narrowest recorded response answering ``request``.

        Narrowest rather than first, so a scenario can record a broad answer for
        a whole endpoint family and a precise one for the single call the
        incident turns on, in either file order.
        """
        best: RecordedResponse | None = None
        best_fixture = ""
        for fixture in self.fixtures:
            if integration and fixture.integration != integration:
                continue
            for recorded in fixture.responses:
                if not recorded.match.matches(
                    method=request.method, url=request.url, body=request.body
                ):
                    continue
                if best is None or recorded.match.specificity > best.match.specificity:
                    best, best_fixture = recorded, fixture.filename
        return best, best_fixture

    def _record(
        self,
        request: OutboundRequest,
        integration: str,
        status: int,
        *,
        matched: bool,
        fixture: str = "",
    ) -> None:
        """Add one call to the trajectory record."""
        self.calls.append(
            VendorCall(
                integration=integration,
                method=request.method,
                host=request.host,
                path=request.path,
                url=request.url,
                status=status,
                matched=matched,
                fixture=fixture,
            )
        )

    # -- what trajectory scoring reads ---------------------------------------

    @property
    def reached_hosts(self) -> frozenset[str]:
        """Return every vendor host this run actually reached."""
        return frozenset(call.host for call in self.calls)

    @property
    def reached_integrations(self) -> frozenset[str]:
        """Return every integration this run actually called."""
        return frozenset(call.integration for call in self.calls if call.integration)

    @property
    def unmatched(self) -> tuple[VendorCall, ...]:
        """Return the calls no fixture answered, in the order they were made."""
        return tuple(call for call in self.calls if not call.matched)

    @property
    def matched(self) -> tuple[VendorCall, ...]:
        """Return the calls a recorded fixture answered."""
        return tuple(call for call in self.calls if call.matched)


# --- Standing the real client path up ----------------------------------------


#: What a public credential field is filled with when its name says what it is.
#: Only fields whose *value* is load-bearing appear here: a region selects an
#: endpoint and signs a request, so a placeholder would produce a host no
#: integration declared. Everything else is an opaque identifier and a generated
#: one is as good as a real one.
_KNOWN_PUBLIC_VALUES: Mapping[str, str] = {"region": "us-east-1"}


def _from_character_class(entries: Sequence[Any]) -> str:
    """Return one character satisfying a parsed regular-expression class."""
    for opcode, argument in entries:
        name = str(opcode)
        if name == "LITERAL":
            return chr(argument)
        if name == "RANGE":
            return chr(argument[0])
        if name == "CATEGORY":
            return {"CATEGORY_DIGIT": "0", "CATEGORY_SPACE": " "}.get(str(argument), "a")
    return "a"


def _from_pattern(parsed: Any) -> str:
    """Return one string satisfying a parsed regular expression.

    Deliberately minimal: it covers literals, character classes, bounded
    repeats, branches, and groups, which is every construct a credential format
    in this repository uses. Anything it cannot satisfy is reported rather than
    guessed at, because a credential that silently failed its schema would fail
    at the vault with a message about the *schema* rather than about the
    generator.
    """
    produced: list[str] = []
    for opcode, argument in parsed:
        name = str(opcode)
        if name == "LITERAL":
            produced.append(chr(argument))
        elif name == "NOT_LITERAL":
            produced.append("a" if chr(argument) != "a" else "b")
        elif name == "ANY":
            produced.append("a")
        elif name == "IN":
            produced.append(_from_character_class(argument))
        elif name in {"MAX_REPEAT", "MIN_REPEAT"}:
            low, high, sub = argument
            count = low if low else min(1, high if isinstance(high, int) else 1)
            produced.append(_from_pattern(sub) * count)
        elif name == "BRANCH":
            produced.append(_from_pattern(argument[1][0]))
        elif name == "SUBPATTERN":
            produced.append(_from_pattern(argument[3]))
        elif name in {"AT", "ASSERT", "ASSERT_NOT"}:
            continue
        else:
            raise ValueError(f"cannot generate a value for the {name} construct")
    return "".join(produced)


def synthesise_credential(schema: Any) -> dict[str, str]:
    """Return a schema-valid credential for a scenario run.

    Every value here is invented, and the vault will not accept an invented
    value that does not satisfy the schema — so this generates from the
    declaration rather than from a table. That is what makes SC-005 true for
    credentials as well as for fixtures: contributing a scenario for a new
    integration means writing no credential, because the integration already
    declared what one looks like.

    Raises:
        ValueError: a field's declared format is one the generator cannot
            satisfy, named so the integration's schema can say so instead.
    """
    import re as regular_expressions

    values: dict[str, str] = {}
    for declared in schema.fields:
        if declared.pattern is not None:
            try:
                value = _from_pattern(regular_expressions._parser.parse(declared.pattern))
            except (ValueError, AttributeError) as error:  # pragma: no cover - defensive
                raise ValueError(
                    f"{schema.integration}.{declared.name}: the harness cannot generate a "
                    f"value matching this field's declared format: {error}"
                ) from error
            if regular_expressions.fullmatch(declared.pattern, value) is None:
                raise ValueError(
                    f"{schema.integration}.{declared.name}: the generated value does not "
                    f"satisfy this field's declared format"
                )
        elif declared.name in _KNOWN_PUBLIC_VALUES:
            value = _KNOWN_PUBLIC_VALUES[declared.name]
        else:
            stem = f"scenario-{schema.integration}-{declared.name}".replace("_", "-")
            value = stem.ljust(max(declared.min_length, len(stem)), "x")
        values[declared.name] = value
    return values


@dataclass(frozen=True, slots=True)
class VendorStack:
    """The real client path for one scenario, with recorded vendors at the end.

    Everything between a capability and this object is production code: the
    integration client, the transport, the credential proxy, and each vendor's
    own injection rule. That is the point of mocking at the boundary rather than
    at the capability, and it is why ``transport`` is what gets bound rather
    than a set of stubbed tools.
    """

    transport: Any
    boundary: MockVendorBoundary
    integrations: tuple[str, ...]
    credentials: Mapping[str, Mapping[str, str]]


async def stand_up(
    integrations: Sequence[str],
    fixtures: Sequence[EvidenceFixture] = (),
    *,
    org_id: str,
    team_id: str,
    at: Any,
) -> VendorStack:
    """Return the credential proxy for ``integrations``, answering from ``fixtures``.

    Raises:
        KeyError: an integration name nothing in the catalogue declares.
    """
    from integrations._base.transport import InProcessProxyTransport
    from integrations._catalogue.discovery import catalogue as integration_catalogue
    from platform.credentials.handles import CredentialHandle
    from platform.credentials.proxy.app import create_proxy_app
    from platform.credentials.proxy.audit import ResolutionAuditor
    from platform.credentials.proxy.engine import ProxyEngine
    from platform.credentials.proxy.injection import InjectionRuleRegistry
    from platform.credentials.proxy.resolution import CredentialResolver
    from platform.credentials.schemas import CredentialSchemaRegistry
    from platform.credentials.vault import Vault
    from platform.persistence.fakes import FakePersistence
    from platform.persistence.ports import TenantScope
    from tests.harness.backends import backend_for

    entries = {entry.name: entry for entry in integration_catalogue()}
    descriptors = [entries[name].descriptor for name in integrations]

    gateway = FakePersistence()
    async with gateway.begin_system() as system:
        await system.orgs.create_organisation(org_id, org_id.title())

    scope = TenantScope(org_id=org_id, team_node_id=team_id)
    schemas = CredentialSchemaRegistry.from_schemas(*(found.schema for found in descriptors))
    vault = Vault(gateway=gateway, schemas=schemas)

    credentials: dict[str, dict[str, str]] = {}
    for descriptor in descriptors:
        values = synthesise_credential(descriptor.schema)
        credentials[descriptor.name] = values
        await vault.store(
            scope, CredentialHandle(integration=descriptor.name, team_id=team_id), values
        )

    boundary = MockVendorBoundary(
        fixtures=tuple(fixtures),
        backends={name: backend_for(name) for name in integrations},
        hosts=host_map([found.rule for found in descriptors]),
    )
    engine = ProxyEngine(
        resolver=CredentialResolver(gateway=gateway, schemas=schemas),
        rules=InjectionRuleRegistry.from_rules(*(found.rule for found in descriptors)),
        sender=boundary,
        auditor=ResolutionAuditor(gateway=gateway),
        clock=lambda: at,
    )
    return VendorStack(
        transport=InProcessProxyTransport(create_proxy_app(engine)),
        boundary=boundary,
        integrations=tuple(integrations),
        credentials=credentials,
    )


def host_map(rules: Sequence[Any]) -> dict[str, str]:
    """Return vendor host to integration name for ``rules``.

    Takes injection rules rather than integration names because the hosts are
    declared on the rule, and the rule is the egress allow-list the proxy
    enforces — so the map the boundary answers on is the same list the proxy
    permits, by construction rather than by agreement.
    """
    return {host.lower(): rule.integration for rule in rules for host in getattr(rule, "hosts", ())}


__all__ = [
    "GENERIC_BACKEND",
    "GENERIC_EMPTY_BODY",
    "EmptyResponder",
    "MockBackend",
    "MockVendorBoundary",
    "VendorCall",
    "VendorStack",
    "generic_empty",
    "host_map",
    "json_response",
    "stand_up",
    "synthesise_credential",
    "text_response",
    "xml_response",
]
