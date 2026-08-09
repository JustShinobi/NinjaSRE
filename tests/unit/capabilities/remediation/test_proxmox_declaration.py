"""A hypervisor write that declared less than it has to cannot be built at all.

The requirement is that the failure happens at registration rather than at
runtime, and the strongest available form of that is a declaration that refuses
to construct: a capability missing a piece is an import error, so nothing
incomplete can reach the registry because nothing incomplete can exist.

The second half of the file is the agreement between the risk table and the
registry. The table is the document an operator reads; the registry is what the
system obeys. Two of them are only worth having if a test fails when they differ.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from capabilities.tools.remediation.proxmox import DECLARATIONS, risk
from capabilities.tools.remediation.proxmox.declaration import (
    ProxmoxRemediation,
    RegistrationRefused,
    RollbackDeclaration,
    WriteCategory,
    declarations_of,
)
from capabilities.tools.remediation.proxmox.preconditions import Precondition
from config.constants.closed_loop import MAX_SETTLE_SECONDS, MIN_SETTLE_SECONDS
from integrations.proxmox.privileges import RequiredPrivilege
from platform.remediation.declaration import (
    SignalDirection,
    VerificationDeclaration,
    VerificationSignal,
)
from platform.remediation.models import RemediationAction, StateSnapshot

pytestmark = pytest.mark.unit

#: A capability the table classifies, so that what a variant below is missing is
#: the only thing missing.
NAMED = "proxmox_start_guest"

_PRIVILEGE = RequiredPrivilege(privilege="VM.PowerMgmt", path="/vms", grants="start guests")

_VERIFIED = VerificationDeclaration(
    signals=(VerificationSignal(name="proxmox.guest.running", direction=SignalDirection.UP),),
    settle_seconds=120,
)

_ROLLBACK = RollbackDeclaration(
    summary="Shut {target} down again.",
    steps=("Shut it down.",),
)


def _intent(action: RemediationAction, before: StateSnapshot) -> Mapping[str, Any]:
    """Return a state to intend, so the variants differ only in what they omit."""
    del action, before
    return {"status": "running"}


def declaration(**overrides: Any) -> ProxmoxRemediation:
    """Return a complete declaration, with ``overrides`` applied."""
    fields: dict[str, Any] = {
        "capability": NAMED,
        "category": WriteCategory.GUEST_LIFECYCLE,
        "endpoint": "/nodes/{node}/{kind}/{vmid}/status/start",
        "method": "POST",
        "preconditions": (Precondition.TARGET_UNCHANGED,),
        "rollback": _ROLLBACK,
        "verification": _VERIFIED,
        "privileges": (_PRIVILEGE,),
        "fields": ("node", "status"),
        "identity_fields": ("node",),
        "intent_of": _intent,
        "writes_configuration": True,
    }
    return ProxmoxRemediation(**{**fields, **overrides})


def test_a_complete_declaration_is_buildable() -> None:
    """The control, so every refusal below is about the thing it names."""
    assert declaration().capability == NAMED


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"preconditions": ()}, "declares no preconditions"),
        ({"privileges": ()}, "names no Proxmox privilege"),
        ({"fields": (), "identity_fields": ()}, "names no state fields"),
        ({"identity_fields": ()}, "identity fields"),
        ({"endpoint": ""}, "endpoint and method"),
        ({"method": ""}, "endpoint and method"),
        ({"capability": "proxmox_not_classified"}, "risk table does not classify it"),
    ],
    ids=[
        "no preconditions",
        "no privileges",
        "no state fields",
        "no identity fields",
        "no endpoint",
        "no method",
        "unclassified",
    ],
)
def test_a_declaration_missing_a_piece_fails_registration(
    overrides: dict[str, Any], expected: str
) -> None:
    """Not at runtime. A gap discovered during an incident is a gap discovered late."""
    with pytest.raises(RegistrationRefused, match=expected):
        declaration(**overrides)


def test_a_rollback_that_says_neither_how_nor_why_cannot_be_written() -> None:
    """A capability with no undo and no reason for it is one nobody finished."""
    with pytest.raises(RegistrationRefused, match="rollback plan"):
        declaration(rollback=RollbackDeclaration())


def test_a_rollback_that_promises_an_undo_and_lists_no_steps_is_refused() -> None:
    """A summary with no steps is a plan nobody can run at three in the morning."""
    with pytest.raises(ValueError, match="steps"):
        RollbackDeclaration(summary="Put it back.")


def test_a_rollback_cannot_both_promise_an_undo_and_deny_having_one() -> None:
    """Saying both describes something that is not the case."""
    with pytest.raises(ValueError, match="not the case"):
        RollbackDeclaration(summary="Put it back.", steps=("x",), absent_because="it cannot be")


def test_declaring_no_rollback_requires_the_reason() -> None:
    """The reason is what makes it a decision rather than a field nobody filled in."""
    with pytest.raises(ValueError, match="has to say why"):
        RollbackDeclaration.none("   ")


def test_a_declaration_that_verifies_against_nothing_and_says_nothing_is_refused() -> None:
    """The declaration is required, including the declaration that there is none."""
    with pytest.raises(Exception, match="signals|reason"):
        declaration(verification=VerificationDeclaration())


def test_a_declaration_writing_a_prohibited_endpoint_cannot_be_registered() -> None:
    """The sweep is not only over what shipped; it is over what could be added."""
    with pytest.raises(RegistrationRefused, match="node_network"):
        declaration(endpoint="/nodes/{node}/network")


def test_two_declarations_with_one_name_are_refused() -> None:
    """Which one runs would otherwise depend on import order."""
    with pytest.raises(RegistrationRefused, match="two declarations"):
        declarations_of((declaration(), declaration()))


# --- The table and the registry ----------------------------------------------


def test_the_risk_table_and_the_registered_capabilities_agree_exactly() -> None:
    """The document an operator reads has to be the one the system obeys."""
    tabled = {row.capability for row in risk.RISK_TABLE}

    assert tabled == set(DECLARATIONS)


def test_every_declaration_takes_its_class_from_the_table_rather_than_declaring_one() -> None:
    """They cannot drift, because there is only one place the class is written."""
    for name, declared in DECLARATIONS.items():
        assert declared.risk_class is risk.class_of(name)


def test_every_registered_capability_declares_all_six_things() -> None:
    """Swept over the registry, so the fourteenth write is covered the day it lands."""
    for name, declared in DECLARATIONS.items():
        assert declared.preconditions, name
        assert declared.privileges, name
        assert declared.fields and declared.identity_fields, name
        assert declared.rollback.derivable or declared.rollback.absent_because.strip(), name
        assert declared.verification.verifiable or declared.verification.reason.strip(), name
        if declared.verification.verifiable:
            assert MIN_SETTLE_SECONDS <= declared.verification.settle_seconds <= MAX_SETTLE_SECONDS


def test_every_declaration_renders_a_paragraph_a_reviewer_can_read() -> None:
    """A declaration nobody can print is a declaration nobody reviews."""
    for name, declared in DECLARATIONS.items():
        described = declared.describe()

        assert name in described
        assert declared.risk_class.value in described
        assert "preconditions:" in described
        assert "rollback:" in described
        assert "privileges:" in described


def test_the_two_actions_with_no_undo_say_why_rather_than_inventing_one() -> None:
    """A deleted snapshot has no reversal, and pretending otherwise is worse than none."""
    without = {name for name, declared in DECLARATIONS.items() if not declared.rollback.derivable}

    assert without == {"proxmox_reclaim_storage", "proxmox_remove_orphaned_volume"}
    for name in without:
        assert DECLARATIONS[name].rollback.absent_because.strip(), name
