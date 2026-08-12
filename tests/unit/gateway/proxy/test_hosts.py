def test_the_bridge_endpoints_widen_the_allowlist_too() -> None:
    """The observability bridge names its metrics and log systems in the policy
    tree rather than in the active-integration list, so the proxy never saw
    them: a deployment pointed its logs at its own Loki and every read was
    refused for reaching a host the integration had not declared.

    The endpoint is an integration endpoint wherever it is written down. Reading
    only one of the two places is how an operator configures something correctly
    and is refused anyway.
    """
    from gateway.proxy.hosts import bridge_hosts

    class _Source:
        def __init__(self, name: str, endpoint: str, enabled: bool = True) -> None:
            self.name = name
            self.endpoint = endpoint
            self.enabled = enabled

    class _Bridge:
        metrics = _Source("prometheus", "https://prometheus.lan.example")
        logs = _Source("loki", "https://loki.lan.example")

    assert bridge_hosts(_Bridge()) == {
        "prometheus": ("prometheus.lan.example",),
        "loki": ("loki.lan.example",),
    }


def test_a_bridge_source_switched_off_opens_nothing() -> None:
    """Disabling has to close what it opened, or the reachable set outlives the
    configuration that justified it."""
    from gateway.proxy.hosts import bridge_hosts

    class _Off:
        def __init__(self) -> None:
            self.name = "loki"
            self.endpoint = "https://loki.lan.example"
            self.enabled = False

    class _Bridge:
        logs = _Off()

    assert bridge_hosts(_Bridge()) == {}


def test_a_bridge_source_naming_no_integration_opens_nothing() -> None:
    """An address with no integration behind it would register egress that no
    integration asked for."""
    from gateway.proxy.hosts import bridge_hosts

    class _Nameless:
        name = ""
        endpoint = "https://somewhere.example"
        enabled = True

    class _Bridge:
        logs = _Nameless()

    assert bridge_hosts(_Bridge()) == {}
