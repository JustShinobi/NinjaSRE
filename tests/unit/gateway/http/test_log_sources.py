"""Composing the log source, and binding the tool that reads it.

The defect this closes is the one the previous eighteen were: every piece
existed and nothing called the next. A ``LogSource`` port with no adapter, an
adapter with no composition, a composition with no caller in the lifespan — and
an investigation that reported "no log source configured" on a deployment whose
Loki was reachable the whole time.

So the test that matters here is the last one: the boot composes logs. A test of
``compose_log_sources`` alone would have passed for all eighteen.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from gateway.http.log_sources import ComposedLogAccess, selector_rules_from

pytestmark = pytest.mark.unit

AT = datetime(2026, 8, 12, 10, 0, tzinfo=UTC)


class _Settings:
    def __init__(self, declared: tuple[object, ...] = (), shipped: bool = True) -> None:
        self.log_selectors = declared
        self.use_shipped_log_selectors = shipped


class _Rule:
    rule_id = "operator-own"
    resource_kind = "container"
    template = '{job="proxmox-syslog"} |= "pve-container@{native:-1}"'
    description = "what this cluster's shipper actually labels streams with"


def test_a_deployment_that_declared_no_rule_gets_the_shipped_set() -> None:
    from platform.observation.bridge.catalogue import SHIPPED_LOG_SELECTORS

    assert len(selector_rules_from(_Settings())) == len(SHIPPED_LOG_SELECTORS)


def test_the_operators_own_rule_is_asked_before_the_shipped_one() -> None:
    """The point of being able to declare one: a shipper labelled some third way."""
    rules = selector_rules_from(_Settings(declared=(_Rule(),)))

    assert rules[0].rule_id == "operator-own"
    assert 'job="proxmox-syslog"' in rules[0].template


def test_a_deployment_can_switch_the_shipped_rules_off_entirely() -> None:
    assert selector_rules_from(_Settings(declared=(_Rule(),), shipped=False)) == (
        selector_rules_from(_Settings(declared=(_Rule(),)))[0],
    )


class _Resource:
    resource_id = "res-a"
    kind = "container"
    native_id = "cluster/pve01/100"
    display_name = "ct100"


class _Detail:
    class view:  # noqa: N801 — mirrors the estate's own attribute shape
        resource = _Resource()


class _Estate:
    def __init__(self, detail: object = None) -> None:
        self.detail_value = detail

    async def detail(self, scope: object, resource: str, *, now: datetime) -> object:
        del scope, resource, now
        return self.detail_value


class _Reader:
    def __init__(self) -> None:
        self.read_selector = ""

    async def read(self, selector: str, *, at: datetime) -> object:
        del at
        self.read_selector = selector
        return "an answer"


async def test_a_resource_the_estate_does_not_hold_reads_nothing() -> None:
    from platform.persistence.ports import TenantScope

    access = ComposedLogAccess(
        estate=_Estate(detail=None),  # type: ignore[arg-type]
        scope=TenantScope(org_id="acme"),
        reader=_Reader(),  # type: ignore[arg-type]
        rules=selector_rules_from(_Settings()),
    )

    assert await access.logs_for("res-nobody-watches", at=AT) is None


async def test_the_selector_is_built_from_the_resources_own_identity() -> None:
    from platform.persistence.ports import TenantScope

    reader = _Reader()
    access = ComposedLogAccess(
        estate=_Estate(detail=_Detail()),  # type: ignore[arg-type]
        scope=TenantScope(org_id="acme"),
        reader=reader,  # type: ignore[arg-type]
        rules=selector_rules_from(_Settings(declared=(_Rule(),))),
    )

    answer = await access.logs_for("res-a", at=AT)

    assert answer == "an answer"
    # The VMID off the end of the native identity, not the display name.
    assert reader.read_selector == '{job="proxmox-syslog"} |= "pve-container@100"'


async def test_a_kind_no_rule_covers_reads_nothing_rather_than_everything() -> None:
    """A half-filled template matches everything or nothing, and neither is about
    this resource."""
    from platform.persistence.ports import TenantScope

    class _Unknown(_Resource):
        kind = "storage-pool"

    class _UnknownDetail:
        class view:  # noqa: N801
            resource = _Unknown()

    access = ComposedLogAccess(
        estate=_Estate(detail=_UnknownDetail()),  # type: ignore[arg-type]
        scope=TenantScope(org_id="acme"),
        reader=_Reader(),  # type: ignore[arg-type]
        rules=selector_rules_from(_Settings()),
    )

    assert await access.logs_for("res-a", at=AT) is None


def test_the_boot_composes_the_log_source() -> None:
    """The joint. Eighteen defects this session were a capability nothing called,
    and a test of the composition alone would have passed for every one of them."""
    import inspect

    from gateway.http import lifespan

    assert "compose_log_sources" in inspect.getsource(lifespan)
