"""The certificate trust reaching the process that opens the socket.

A declaration nothing composes is a field an operator fills in and a behaviour
that never changes. So these tests are about the wire: the engine the
composition root builds holds a registry, the sender it holds is the same
object, the configuration read produces declarations beside the hosts in one
read, and the cycle rebuilds rather than accumulating.
"""

from __future__ import annotations

import ast
import inspect

import pytest

from gateway.proxy.hosts import refresh_configured_trust, trust_from_configuration
from platform.credentials.proxy.trust import CertificateTrust, TrustAnchor, TrustRegistry

pytestmark = pytest.mark.unit

COLONS = "00:01:02:03:04:05:06:07:08:09:0A:0B:0C:0D:0E:0F:10:11:12:13:14:15:16:17:18:19:1A:1B:1C:1D:1E:1F"
ADDRESS = "https://pve01.acme.example:8006"
PEM = "-----BEGIN CERTIFICATE-----\nMIIBogIBADANBgkq\n-----END CERTIFICATE-----\n"


def entry(**over: object) -> dict[str, object]:
    """Return one active integration entry as the proxy's reader sees it."""
    return {"name": "proxmox", "enabled": True, "base_url": ADDRESS, **over}


# -- the composition root hands it over ------------------------------------------


def test_the_composed_engine_holds_a_trust_registry() -> None:
    """Cut this and every address falls back to the system store for ever."""
    from gateway.proxy.composition import build_proxy_engine
    from platform.persistence.fakes import FakePersistence

    engine = build_proxy_engine(FakePersistence())

    assert isinstance(engine.trust, TrustRegistry), (
        "the composed engine has no trust registry, so a declaration an operator wrote "
        "reaches nothing and every address is verified against the system store."
    )


def test_the_sender_reads_the_same_registry_the_engine_does() -> None:
    """One object, two readers. Two registries would be two answers."""
    from gateway.proxy.composition import build_proxy_engine
    from platform.persistence.fakes import FakePersistence

    engine = build_proxy_engine(FakePersistence())
    sender = engine._sender  # noqa: SLF001 — the point of the test

    assert sender._trust is engine.trust  # noqa: SLF001 — the point of the test


def test_the_sender_is_given_the_registry_rather_than_finding_one() -> None:
    """Composition is the only way in, so there is no second place trust is decided."""
    from gateway.proxy import composition

    tree = ast.parse(inspect.getsource(composition))
    constructed = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "HttpOutboundSender"
    ]

    assert constructed, "nothing constructs the sender in the composition root"
    assert all(any(keyword.arg == "trust" for keyword in call.keywords) for call in constructed), (
        "the sender is constructed without a trust registry, so it builds its own view"
    )


# -- the configuration read ---------------------------------------------------------


def test_a_declared_fingerprint_comes_out_of_the_configuration() -> None:
    declared = trust_from_configuration([entry(trust={"fingerprints": [COLONS]})])

    assert len(declared) == 1
    assert declared[0].anchor is TrustAnchor.PINNED_FINGERPRINT
    assert declared[0].addresses == ("pve01.acme.example",)


def test_a_declared_certificate_comes_out_of_the_configuration() -> None:
    declared = trust_from_configuration([entry(trust={"certificate_pem": PEM})])

    assert declared[0].anchor is TrustAnchor.SUPPLIED_CERTIFICATE


def test_an_entry_that_declared_nothing_contributes_no_declaration() -> None:
    """The default costs nothing and is reached by the registry's own fallback."""
    assert trust_from_configuration([entry()]) == ()


def test_an_entry_switched_off_contributes_nothing() -> None:
    assert trust_from_configuration([entry(enabled=False, trust={"fingerprints": [COLONS]})]) == ()


def test_an_entry_with_no_address_contributes_nothing() -> None:
    """A declaration that names no address authorises no address."""
    assert trust_from_configuration([entry(base_url="", trust={"fingerprints": [COLONS]})]) == ()


def test_a_declaration_that_does_not_parse_is_ignored_and_does_not_stop_the_rest() -> None:
    """One bad entry must not cost every other integration its declaration."""
    declared = trust_from_configuration(
        [
            entry(name="broken", trust={"fingerprints": ["probably-a-password"]}),
            entry(trust={"fingerprints": [COLONS]}),
        ]
    )

    assert len(declared) == 1
    assert declared[0].addresses == ("pve01.acme.example",)


# -- the cycle rebuilds rather than accumulating ------------------------------------


def test_a_removed_declaration_stops_applying_on_the_next_cycle() -> None:
    """A permission that outlived the decision to grant it is the failure here."""
    registry = TrustRegistry()
    refresh_configured_trust(
        registry, trust_from_configuration([entry(trust={"fingerprints": [COLONS]})])
    )
    assert registry.for_host("pve01.acme.example").anchor is TrustAnchor.PINNED_FINGERPRINT

    refresh_configured_trust(registry, trust_from_configuration([entry()]))

    assert registry.for_host("pve01.acme.example").anchor is TrustAnchor.SYSTEM_TRUST_STORE


def test_the_rebuilt_registry_reaches_a_sender_that_had_already_cached_a_context() -> None:
    """A cached context outliving its declaration is the same failure, one layer down."""
    from gateway.proxy.sender import HttpOutboundSender

    registry = TrustRegistry([CertificateTrust.pinned(COLONS).for_addresses(ADDRESS)])
    sender = HttpOutboundSender(trust=registry)
    first = sender._egress_for("pve01.acme.example")  # noqa: SLF001 — the point of the test
    assert first.trust.anchor is TrustAnchor.PINNED_FINGERPRINT

    registry.replace_all(())

    second = sender._egress_for("pve01.acme.example")  # noqa: SLF001 — the point of the test
    assert second.trust.anchor is TrustAnchor.SYSTEM_TRUST_STORE


# -- one cycle, one read ------------------------------------------------------------


def test_the_process_rebuilds_the_hosts_and_the_trust_in_the_same_cycle() -> None:
    """Two truths derived from one document by two cycles is how they disagree."""
    from gateway.proxy import __main__ as process

    watcher = inspect.getsource(process._watch_configured_hosts)  # noqa: SLF001

    assert "refresh_configured_hosts" in watcher
    assert "refresh_configured_trust" in watcher, (
        "the periodic cycle rebuilds the allow-list and not the trust, so a declaration "
        "an operator wrote takes a pod restart to apply — a restart for a reason nothing "
        "on the screen explains."
    )


def test_the_startup_path_applies_the_trust_too() -> None:
    """Otherwise the first minute of every process verifies against the wrong anchor."""
    from gateway.proxy import __main__ as process

    served = inspect.getsource(process._serve)  # noqa: SLF001

    assert "refresh_configured_trust" in served


def test_an_unreadable_configuration_leaves_what_is_in_force_in_force() -> None:
    """A database blip must not become an outage of every integration."""
    from gateway.proxy import __main__ as process

    tree = ast.parse(inspect.getsource(process))
    watcher = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_watch_configured_hosts"
    )
    handlers = [node for node in ast.walk(watcher) if isinstance(node, ast.ExceptHandler)]

    assert handlers, "the cycle does not survive a configuration it cannot read"
    # `continue` rather than `break` or a raise: the current rules stay in force
    # and the next tick tries again.
    assert any(
        any(isinstance(inner, ast.Continue) for inner in ast.walk(handler)) for handler in handlers
    )
