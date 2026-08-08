"""The three rules that make the estate a model rather than a bag.

A kind is declared before anything of that kind can be written, an identity
comes from the source rather than from the name, and an attribute a provider
invented does not become part of the schema by being sent.
"""

from __future__ import annotations

import pytest

from config.constants.estate import DEFAULT_FRESHNESS_SECONDS, MIN_FRESHNESS_SECONDS
from platform.estate.attributes import AttributeType, screened
from platform.estate.errors import (
    KindAlreadyRegistered,
    NoStableIdentifier,
    RegistrySealed,
    UnknownResourceKind,
)
from platform.estate.identity import derive_resource_id, native_key
from platform.estate.kinds import (
    CORE_KINDS,
    KIND_NODE,
    KIND_VIRTUAL_MACHINE,
    ResourceKind,
    core_registry,
)

pytestmark = pytest.mark.unit


# --- The registry --------------------------------------------------------------


def test_the_core_kinds_are_registered_and_readable() -> None:
    registry = core_registry()

    assert set(registry.names()) == {kind.name for kind in CORE_KINDS}
    assert registry.get(KIND_NODE).label
    assert registry.get(KIND_VIRTUAL_MACHINE).parent_kinds == (KIND_NODE,)


def test_an_integration_extends_the_registry_without_touching_the_core_model() -> None:
    registry = core_registry()
    registry.register(
        ResourceKind(
            name="proxmox_backup_job",
            label="Backup job",
            integration="proxmox",
            parent_kinds=(KIND_NODE,),
            attributes={"schedule": AttributeType.STRING, "enabled": AttributeType.BOOLEAN},
        )
    )

    assert "proxmox_backup_job" in registry.names()
    assert registry.get("proxmox_backup_job").integration == "proxmox"
    # The core kinds are untouched by the extension.
    assert registry.get(KIND_NODE).integration == ""


def test_an_unknown_parent_kind_is_rejected_at_registration_not_at_write() -> None:
    """A kind naming a parent nobody declared is refused when it is declared."""
    registry = core_registry()

    with pytest.raises(UnknownResourceKind) as refused:
        registry.register(ResourceKind(name="volume", label="Volume", parent_kinds=("datacentre",)))

    assert "datacentre" in str(refused.value)
    assert "volume" not in registry.names()


def test_registering_a_kind_twice_is_refused() -> None:
    registry = core_registry()

    with pytest.raises(KindAlreadyRegistered):
        registry.register(ResourceKind(name=KIND_NODE, label="Node, again"))


def test_a_sealed_registry_accepts_nothing_further() -> None:
    """FR-002's "closed at runtime": extension happens at wiring, not mid-sweep."""
    registry = core_registry()
    registry.seal()

    with pytest.raises(RegistrySealed):
        registry.register(ResourceKind(name="volume", label="Volume"))


def test_an_unknown_kind_cannot_be_read() -> None:
    with pytest.raises(UnknownResourceKind):
        core_registry().get("teapot")


def test_a_kind_may_declare_its_own_freshness_and_falls_back_to_the_default() -> None:
    registry = core_registry()
    registry.register(
        ResourceKind(name="tape_library", label="Tape library", freshness_seconds=86_400)
    )

    assert registry.freshness_for("tape_library") == 86_400
    assert registry.freshness_for(KIND_NODE) == registry.get(KIND_NODE).freshness_seconds
    assert registry.freshness_for("teapot") == DEFAULT_FRESHNESS_SECONDS


def test_a_freshness_below_the_floor_is_refused() -> None:
    with pytest.raises(ValueError, match="freshness"):
        ResourceKind(name="flapping", label="Flapping", freshness_seconds=MIN_FRESHNESS_SECONDS - 1)


# --- Identity ------------------------------------------------------------------


def test_identity_survives_a_rename_a_restart_and_a_re_discovery() -> None:
    """FR-003: the key is the source plus the native id, and nothing else."""
    first = derive_resource_id(source="proxmox", native_id="qemu/101")
    renamed = derive_resource_id(source="proxmox", native_id="qemu/101")

    assert first == renamed
    # A fresh process derives the same key: nothing here reads process state.
    assert first == derive_resource_id(source="proxmox", native_id="qemu/101")


def test_two_sources_naming_the_same_native_id_derive_different_identities() -> None:
    assert derive_resource_id(source="proxmox", native_id="101") != derive_resource_id(
        source="docker", native_id="101"
    )


def test_a_source_with_no_stable_identifier_is_rejected_by_name() -> None:
    """T-020's rule: rejected, never stored under something we generated."""
    with pytest.raises(NoStableIdentifier) as refused:
        derive_resource_id(source="proxmox", native_id="   ")

    assert "proxmox" in str(refused.value)

    with pytest.raises(NoStableIdentifier):
        derive_resource_id(source="", native_id="qemu/101")


def test_the_derived_identity_is_opaque_and_bounded() -> None:
    derived = derive_resource_id(source="proxmox", native_id="qemu/101")

    assert derived.startswith("res-")
    assert len(derived) <= 128
    # The native id is not recoverable from the key, so a key in a URL does not
    # leak the operator's naming.
    assert "qemu" not in derived


def test_the_native_key_separates_source_from_identifier_unambiguously() -> None:
    # A source id cannot contain the separator, so the split back is exact and
    # ``a`` + ``b:c`` cannot collide with ``a:b`` + ``c``.
    assert native_key("proxmox", "qemu/101") != native_key("proxmox:qemu", "101")


# --- Attributes ----------------------------------------------------------------


def test_an_undeclared_attribute_is_dropped_rather_than_stored() -> None:
    """FR-002's risk: a provider cannot invent the shape at runtime."""
    kind = ResourceKind(
        name="guest",
        label="Guest",
        attributes={"cores": AttributeType.INTEGER, "name": AttributeType.STRING},
    )

    result = kind.typed({"cores": 4, "name": "checkout", "invented": {"deep": "bag"}})

    assert result.values == {"cores": 4, "name": "checkout"}
    assert result.dropped == ("invented",)


def test_a_declared_attribute_of_the_wrong_type_is_reported_rather_than_coerced() -> None:
    kind = ResourceKind(name="guest", label="Guest", attributes={"cores": AttributeType.INTEGER})

    result = kind.typed({"cores": "many"})

    assert result.values == {}
    assert result.invalid == ("cores",)


def test_a_kind_declaring_no_attributes_accepts_none_of_them() -> None:
    kind = ResourceKind(name="opaque", label="Opaque")

    result = kind.typed({"anything": 1})

    assert result.values == {}
    assert result.dropped == ("anything",)


# --- Masking (NFR-005) ---------------------------------------------------------


def test_a_secret_shaped_attribute_is_redacted_before_storage() -> None:
    screenedvalues = screened({"cloud_init": "AWS_SECRET_ACCESS_KEY=" + "A" * 40})

    stored = str(screenedvalues.values["cloud_init"])
    assert "A" * 40 not in stored
    assert screenedvalues.screened == ("cloud_init",)


def test_a_personal_identifier_shaped_attribute_is_masked_before_storage() -> None:
    screenedvalues = screened({"last_client": "connected from 203.0.113.42"})

    stored = str(screenedvalues.values["last_client"])
    assert "203.0.113.42" not in stored
    assert screenedvalues.screened == ("last_client",)


def test_an_ordinary_attribute_passes_through_untouched() -> None:
    result = screened({"cores": 4, "boot_order": "scsi0"})

    assert result.values == {"cores": 4, "boot_order": "scsi0"}
    assert result.screened == ()
