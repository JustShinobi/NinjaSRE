"""The six observability vendors, asked whether they are holding anything.

The framework's own tests prove that an empty window becomes its own state in a
report. What they cannot prove is that *this* vendor wrote a read that would
actually be empty when the store is — a probe pointed at a status endpoint
returns something forever, passes every framework test, and certifies a
Prometheus with no scrape targets as healthy.

So these run each signal source's real verifier through the real credential
proxy, with its own injection rule, against a vendor that answers on the path
the client actually calls. Nothing is mocked between the probe and the wire.

Two properties are asserted per vendor and they pull in opposite directions:

**A store that answered with records reports the count**, and — where the
vendor's read is genuinely time-bounded — the request carried the window's own
bounds rather than the client's defaults. A probe that asked for all of history
would be answered by data from last year.

**A store that answered with nothing reports ``EMPTY_WINDOW``**, and whether
that is a finding depends on the vendor. An alert router holding no alerts is
working; a metric store holding no series is not.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from config.constants.signals import (
    SOURCE_CLOCK_SKEW_TOLERANCE_SECONDS,
    VERIFY_WINDOW_MINUTES,
)
from integrations._base.transport import InProcessProxyTransport
from integrations._catalogue.discovery import catalogue
from integrations._verification.diagnostics import EmptyWindow, SkewState, WindowState
from integrations._verification.framework import (
    SignalSourceVerifier,
    VerificationReport,
    runner_for,
)
from platform.credentials.handles import CredentialHandle
from platform.credentials.proxy.app import create_proxy_app
from platform.credentials.proxy.audit import ResolutionAuditor
from platform.credentials.proxy.engine import ProxyEngine
from platform.credentials.proxy.injection import InjectionRuleRegistry
from platform.credentials.proxy.model import OutboundRequest, OutboundResponse
from platform.credentials.proxy.resolution import CredentialResolver
from platform.credentials.schemas import CredentialSchemaRegistry
from platform.credentials.vault import Vault
from platform.persistence.fakes import FakePersistence
from tests.contract.integrations.conftest import (
    CONTEXT,
    ENTRIES,
    ORG_ID,
    SCOPE,
    TEAM_ID,
    integration_ids,
    vault_values,
)

pytestmark = pytest.mark.contract

#: The instant the platform believes it is, everywhere in this module. Pinned:
#: the skew assertions are a subtraction against it, and a suite that read the
#: wall clock would assert against how long collection took.
NOW = datetime(2026, 8, 10, 12, 0, 0, tzinfo=UTC)

#: Wound back the window's own length, so the request bounds the probe sends are
#: values a test can name rather than values it has to recompute.
WINDOW_START = NOW - timedelta(minutes=VERIFY_WINDOW_MINUTES)

#: The six the specification names. Kept as a literal rather than derived from
#: "declares the protocol", because the point of the list is to fail when one of
#: the six *stops* declaring it.
SIGNAL_SOURCES: tuple[str, ...] = (
    "alertmanager",
    "grafana",
    "loki",
    "openobserve",
    "prometheus",
    "signoz",
)

#: What each vendor's windowed read answers with when it is holding two records,
#: keyed by the path the client calls it on. The shape is the vendor's own —
#: a renamed field fails here rather than at 03:00.
FULL_BODIES: dict[str, object] = {
    "/api/v1/query_range": {"data": {"result": [{"metric": {}}, {"metric": {}}]}},
    "/loki/api/v1/query_range": {"data": {"result": [{"stream": {}}, {"stream": {}}]}},
    "/api/default/_search": {"hits": [{"log": "one"}, {"log": "two"}]},
    "/api/v3/query_range": {"data": {"result": [{"trace": "a"}, {"trace": "b"}]}},
    "/api/v2/alerts": [{"fingerprint": "a"}, {"fingerprint": "b"}],
    "/api/search": [{"uid": "a"}, {"uid": "b"}],
}

#: The same reads, answering 200 with nothing in them. This is the failure the
#: probe family exists for and it is a different body per vendor, which is why
#: it is declared rather than inferred.
EMPTY_BODIES: dict[str, object] = {
    "/api/v1/query_range": {"data": {"result": []}},
    "/loki/api/v1/query_range": {"data": {"result": []}},
    "/api/default/_search": {"hits": []},
    "/api/v3/query_range": {"data": {"result": []}},
    "/api/v2/alerts": [],
    "/api/search": [],
}

#: Which of the six answer empty as a matter of ordinary operation.
EXPECTED_EMPTY: frozenset[str] = frozenset({"alertmanager", "signoz"})

#: Which of the six take a genuine time window on the read the probe makes.
#: Alertmanager answers "what is firing now" and Grafana answers "what dashboards
#: exist"; neither is time-ranged, and pretending otherwise in the assertions
#: would be the test asserting the docstring rather than the behaviour.
WINDOWED: frozenset[str] = frozenset({"loki", "openobserve", "prometheus", "signoz"})


@dataclass(slots=True)
class RoutingVendor:
    """The far side of the proxy, answering by path rather than by turn.

    A queue would work only if the exact number of permission probes each
    verifier makes were encoded here, which is a copy of each verifier that
    silently stops matching. Routing by path is what lets one helper serve six
    vendors with different probe counts.
    """

    body_for: Callable[[str], object]
    date_header: str = ""
    sent: list[OutboundRequest] = field(default_factory=list)

    async def send(self, request: OutboundRequest, *, timeout_seconds: float) -> OutboundResponse:
        """Record ``request`` and answer with whatever this vendor holds for its path."""
        self.sent.append(request)
        headers = {"content-type": "application/json"}
        if self.date_header:
            headers["date"] = self.date_header
        payload = self.body_for(_path_of(request))
        return OutboundResponse(200, headers, json.dumps(payload).encode("utf-8"))

    def request_to(self, path: str) -> OutboundRequest | None:
        """Return the last request that reached ``path``, or ``None``."""
        matched = [request for request in self.sent if _path_of(request) == path]
        return matched[-1] if matched else None


def _path_of(request: OutboundRequest) -> str:
    """Return the vendor path ``request`` was aimed at, without host or query."""
    url = str(request.url)
    without_scheme = url.split("://", 1)[-1]
    path = "/" + without_scheme.split("/", 1)[1] if "/" in without_scheme else "/"
    return path.split("?", 1)[0]


def _query_of(request: OutboundRequest) -> Mapping[str, str]:
    """Return the query parameters ``request`` carried."""
    url = str(request.url)
    if "?" not in url:
        return {}
    pairs = (pair.split("=", 1) for pair in url.split("?", 1)[1].split("&") if "=" in pair)
    return {key: _unquote(value) for key, value in pairs}


def _unquote(value: str) -> str:
    """Return ``value`` with the percent-encoding a query string arrives in undone."""
    from urllib.parse import unquote_plus

    return unquote_plus(value)


def _body_of(request: OutboundRequest) -> Mapping[str, object]:
    """Return the JSON body ``request`` carried, or an empty mapping."""
    if not request.body:
        return {}
    try:
        loaded = json.loads(request.body)
    except ValueError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


async def stand_up_routing(
    name: str,
    *,
    body_for: Callable[[str], object],
    date_header: str = "",
) -> tuple[InProcessProxyTransport, RoutingVendor]:
    """Return a transport onto a proxy holding ``name``'s credential.

    The real proxy, the real injection rules for the whole catalogue, and the
    real vault — only the far side is scripted. A probe that reached the vendor
    without the proxy would be refused here for the reason production would
    refuse it.
    """
    descriptors = [entry.descriptor for entry in catalogue()]
    gateway = FakePersistence()
    async with gateway.begin_system() as system:
        await system.orgs.create_organisation(ORG_ID, "Acme")

    # The vault's view of each schema: an address is configuration and is
    # stored in the configuration tree, so the vault never declares it.
    schemas = CredentialSchemaRegistry.from_schemas(
        *(stored for found in descriptors if (stored := found.schema.for_vault()) is not None)
    )
    vault = Vault(gateway=gateway, schemas=schemas)
    await vault.store(
        SCOPE, CredentialHandle(integration=name, team_id=TEAM_ID), vault_values(name)
    )

    vendor = RoutingVendor(body_for=body_for, date_header=date_header)
    engine = ProxyEngine(
        resolver=CredentialResolver(gateway=gateway, schemas=schemas),
        rules=InjectionRuleRegistry.from_rules(*(found.rule for found in descriptors)),
        sender=vendor,
        auditor=ResolutionAuditor(gateway=gateway),
        clock=lambda: NOW,
    )
    return InProcessProxyTransport(create_proxy_app(engine)), vendor


async def verify(
    name: str,
    *,
    bodies: dict[str, object],
    date_header: str = "",
) -> tuple[VerificationReport, RoutingVendor]:
    """Run ``name``'s real verifier against a vendor answering from ``bodies``."""

    def body_for(path: str) -> object:
        return bodies.get(path, {})

    transport, vendor = await stand_up_routing(name, body_for=body_for, date_header=date_header)
    runner = runner_for([ENTRIES[name].descriptor], clock=lambda: NOW)
    report = await runner.verify(name, transport=transport, context=CONTEXT)
    return report, vendor


def signal_verifier(name: str) -> SignalSourceVerifier:
    """Return ``name``'s verifier as a signal source, or fail saying it is not one."""
    verifier = ENTRIES[name].descriptor.verifier
    assert isinstance(verifier, SignalSourceVerifier), (
        f"{name}: is a signal source and does not declare the probes, so its verification "
        f"proves a credential and says nothing about whether it holds any data"
    )
    return verifier


def rfc1123(when: datetime) -> str:
    """Return ``when`` as the ``Date`` header an HTTP server would send."""
    return when.astimezone(UTC).strftime("%a, %d %b %Y %H:%M:%S GMT")


# --- every one of the six declares both probes ---------------------------------


@pytest.mark.parametrize("name", SIGNAL_SOURCES)
def test_a_signal_source_declares_a_window_read_and_a_clock_reading(name: str) -> None:
    verifier = signal_verifier(name)

    assert verifier.data_window_probe() is not None
    assert verifier.clock_probe() is not None


@pytest.mark.parametrize("name", SIGNAL_SOURCES)
def test_the_window_probe_says_what_it_reads_and_what_to_do_when_it_is_empty(name: str) -> None:
    probe = signal_verifier(name).data_window_probe()
    assert probe is not None

    assert probe.description.strip(), f"{name}: an unnamed read produces an uninterpretable empty"
    assert probe.advice.strip(), f"{name}: no advice, so an empty window is a status and no more"
    assert (probe.empty_means is EmptyWindow.EXPECTED) == (name in EXPECTED_EMPTY), (
        f"{name}: disagrees with this suite about whether holding nothing is ordinary"
    )


def test_nothing_outside_the_six_quietly_became_a_signal_source() -> None:
    """A probe acquired by templating would report data nobody wrote a read for."""
    declaring = {
        name
        for name in integration_ids()
        if isinstance(ENTRIES[name].descriptor.verifier, SignalSourceVerifier)
    }

    assert declaring == set(SIGNAL_SOURCES)


# --- a source holding data -----------------------------------------------------


@pytest.mark.parametrize("name", SIGNAL_SOURCES)
async def test_a_source_holding_records_verifies_with_the_count(name: str) -> None:
    report, _ = await verify(name, bodies=FULL_BODIES, date_header=rfc1123(NOW))

    assert report.data_window is not None
    assert report.data_window.state is WindowState.RETURNED
    assert report.data_window.rows == 2
    assert report.ok
    assert not report.degraded


@pytest.mark.parametrize("name", sorted(WINDOWED))
async def test_a_windowed_read_asks_for_the_window_rather_than_all_of_history(name: str) -> None:
    """A probe that asked for everything is answered by data from last year."""
    _, vendor = await verify(name, bodies=FULL_BODIES)

    asked = "\n".join(
        f"{_path_of(request)} {_query_of(request)} {_body_of(request)}" for request in vendor.sent
    )
    for stamp in _window_spellings(name):
        assert stamp in asked, f"{name}: the read did not carry the window bound {stamp}"


def _window_spellings(name: str) -> tuple[str, ...]:
    """Return how ``name``'s API spells the window's two ends."""
    if name == "prometheus":
        return ("2026-08-10T11:45:00Z", "2026-08-10T12:00:00Z")
    if name == "loki":
        nanoseconds = int(WINDOW_START.timestamp() * 1_000_000_000)
        return (str(nanoseconds), str(int(NOW.timestamp() * 1_000_000_000)))
    if name == "openobserve":
        microseconds = int(WINDOW_START.timestamp() * 1_000_000)
        return (str(microseconds), str(int(NOW.timestamp() * 1_000_000)))
    milliseconds = int(WINDOW_START.timestamp() * 1_000)
    return (str(milliseconds), str(int(NOW.timestamp() * 1_000)))


# --- a source holding nothing --------------------------------------------------


@pytest.mark.parametrize("name", SIGNAL_SOURCES)
async def test_a_source_answering_200_with_nothing_reports_an_empty_window(name: str) -> None:
    report, _ = await verify(name, bodies=EMPTY_BODIES, date_header=rfc1123(NOW))

    assert report.data_window is not None
    assert report.data_window.state is WindowState.EMPTY_WINDOW
    assert report.data_window.rows == 0


@pytest.mark.parametrize("name", sorted(set(SIGNAL_SOURCES) - EXPECTED_EMPTY))
async def test_a_store_that_should_hold_something_and_does_not_fails_verification(
    name: str,
) -> None:
    report, _ = await verify(name, bodies=EMPTY_BODIES, date_header=rfc1123(NOW))

    assert not report.ok, f"{name}: reported healthy while holding nothing"
    assert report.degraded
    assert any("holds nothing" in reason for reason in report.degradations)


@pytest.mark.parametrize("name", sorted(EXPECTED_EMPTY))
async def test_a_source_whose_ordinary_state_is_empty_is_not_reported_as_broken(name: str) -> None:
    report, _ = await verify(name, bodies=EMPTY_BODIES, date_header=rfc1123(NOW))

    assert report.ok
    assert not report.degraded


# --- the clock -----------------------------------------------------------------


@pytest.mark.parametrize("name", SIGNAL_SOURCES)
async def test_a_source_whose_clock_agrees_measures_the_offset(name: str) -> None:
    report, _ = await verify(
        name, bodies=FULL_BODIES, date_header=rfc1123(NOW + timedelta(seconds=1))
    )

    assert report.clock is not None
    assert report.clock.state is SkewState.IN_TOLERANCE
    assert report.clock.offset_seconds == pytest.approx(1.0)


@pytest.mark.parametrize("name", SIGNAL_SOURCES)
async def test_a_skewed_source_is_degraded_with_the_measured_offset(name: str) -> None:
    drift = timedelta(seconds=SOURCE_CLOCK_SKEW_TOLERANCE_SECONDS + 60)
    report, _ = await verify(name, bodies=FULL_BODIES, date_header=rfc1123(NOW + drift))

    assert report.clock is not None
    assert report.clock.state is SkewState.OUT_OF_TOLERANCE
    assert report.clock.offset_seconds == pytest.approx(drift.total_seconds())
    assert report.degraded
    assert report.ok, "a skewed source still answers; its timestamps are what cannot be trusted"


@pytest.mark.parametrize("name", SIGNAL_SOURCES)
async def test_a_source_that_sends_no_date_header_is_unmeasured_rather_than_agreeing(
    name: str,
) -> None:
    report, _ = await verify(name, bodies=FULL_BODIES, date_header="")

    assert report.clock is not None
    assert report.clock.state is SkewState.UNREPORTED
    assert report.clock.offset_seconds is None
    assert not report.degraded


@pytest.mark.parametrize("name", SIGNAL_SOURCES)
async def test_the_record_a_console_renders_carries_both_measurements(name: str) -> None:
    report, _ = await verify(name, bodies=FULL_BODIES, date_header=rfc1123(NOW))
    record = report.to_record()

    window = record["data_window"]
    assert isinstance(window, dict)
    assert window["rows"] == 2
    assert window["window_minutes"] == VERIFY_WINDOW_MINUTES

    clock = record["clock"]
    assert isinstance(clock, dict)
    assert clock["tolerance_seconds"] == SOURCE_CLOCK_SKEW_TOLERANCE_SECONDS
