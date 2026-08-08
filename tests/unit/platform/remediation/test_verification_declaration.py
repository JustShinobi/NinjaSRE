"""What a capability has to say about how anybody would know it worked.

Four properties, and each one is a way "we fixed it" becomes an assertion
nobody checked.

**A declaration is required, including the declaration that there is none.**
``RemediationComponents`` takes five things now, not four. A capability that
could omit this would be omitted by exactly the capabilities whose effects are
hardest to measure.

**An undeclared signal is refused at registration.** A capability naming a
signal no source produces would verify against nothing, forever, and report
``inconclusive`` every time — which is indistinguishable from a system that is
genuinely hard to measure.

**A move smaller than the noise floor is never success.** This is FR-005, and it
is the one simplification that would make every number this feature produces
worthless.

**The settle period is bounded at both ends.** Below the floor the verification
reads the sample the detector already fired on; above the ceiling nobody
connects the verdict to the action.
"""

from __future__ import annotations

import pytest

from config.constants.closed_loop import (
    DEFAULT_SETTLE_SECONDS,
    MAX_SETTLE_SECONDS,
    MIN_SETTLE_SECONDS,
)
from platform.persistence.ports.remediation_ledger import VerificationVerdict
from platform.remediation.declaration import (
    SignalDirection,
    VerificationDeclaration,
    VerificationSignal,
)
from platform.remediation.errors import UndeclaredVerification, UnknownVerificationSignal

pytestmark = pytest.mark.unit


def a_declaration(**overrides: object) -> VerificationDeclaration:
    """Return the declaration a filesystem-clearing capability would make."""
    fields: dict[str, object] = {
        "signals": (
            VerificationSignal(
                name="filesystem.used_percent",
                direction=SignalDirection.DOWN,
                clears_at=80.0,
            ),
        ),
        "settle_seconds": DEFAULT_SETTLE_SECONDS,
    }
    fields.update(overrides)
    return VerificationDeclaration(**fields)  # type: ignore[arg-type]


def test_a_capability_with_no_declared_signal_is_unverifiable_and_says_why() -> None:
    """FR-006: unverifiable is a declaration, not the absence of one."""
    declaration = VerificationDeclaration.unverifiable(
        "a feature flag's effect appears in whatever the flag guards, which is "
        "not a signal this capability can name"
    )

    assert not declaration.verifiable
    assert declaration.verdict_for(before={}, after={}) is VerificationVerdict.UNVERIFIABLE
    assert "feature flag" in declaration.reason


def test_an_unverifiable_declaration_must_say_why_it_cannot_be_verified() -> None:
    """An empty reason is the shape in which "nobody got round to it" hides."""
    with pytest.raises(UndeclaredVerification, match="a reason there are none"):
        VerificationDeclaration.unverifiable("   ")


def test_a_declaration_with_signals_and_no_settle_period_is_refused() -> None:
    """A signal read at the instant of the change reports the state it fixed."""
    with pytest.raises(ValueError, match="settle"):
        a_declaration(settle_seconds=MIN_SETTLE_SECONDS - 1)

    with pytest.raises(ValueError, match="settle"):
        a_declaration(settle_seconds=MAX_SETTLE_SECONDS + 1)


def test_a_signal_that_reached_the_clearing_value_is_effective() -> None:
    """SC-001: the condition cleared, which is the only thing that is success."""
    verdict = a_declaration().verdict_for(
        before={"filesystem.used_percent": 96.0},
        after={"filesystem.used_percent": 60.0},
    )

    assert verdict is VerificationVerdict.EFFECTIVE


def test_a_signal_that_did_not_reach_the_clearing_value_is_ineffective() -> None:
    """SC-002: it moved, measurably, and the condition still holds."""
    verdict = a_declaration().verdict_for(
        before={"filesystem.used_percent": 96.0},
        after={"filesystem.used_percent": 94.0},
    )

    assert verdict is VerificationVerdict.INEFFECTIVE


def test_a_signal_that_moved_less_than_the_noise_floor_is_inconclusive() -> None:
    """FR-005 and T-011: not enough to tell is never success and never failure.

    Without a clearing value there is nothing to compare against but the size of
    the move, and a move of half a per cent on a live system is indistinguishable
    from an unrelated fluctuation.
    """
    declaration = a_declaration(
        signals=(VerificationSignal(name="workload.error_rate", direction=SignalDirection.DOWN),)
    )

    verdict = declaration.verdict_for(
        before={"workload.error_rate": 10.0},
        after={"workload.error_rate": 9.95},
    )

    assert verdict is VerificationVerdict.INCONCLUSIVE
    assert verdict is not VerificationVerdict.EFFECTIVE


def test_a_signal_that_moved_the_wrong_way_is_worsened() -> None:
    """SC-003: this is the only verdict that rolls anything back."""
    verdict = a_declaration().verdict_for(
        before={"filesystem.used_percent": 90.0},
        after={"filesystem.used_percent": 99.0},
    )

    assert verdict is VerificationVerdict.WORSENED


def test_a_signal_that_could_not_be_read_is_inconclusive() -> None:
    """FR-022: a resource that went away did not have its condition cleared."""
    verdict = a_declaration().verdict_for(
        before={"filesystem.used_percent": 96.0},
        after={},
    )

    assert verdict is VerificationVerdict.INCONCLUSIVE


def test_the_worst_of_several_signals_is_the_verdict() -> None:
    """One signal getting worse is not offset by another getting better."""
    declaration = a_declaration(
        signals=(
            VerificationSignal(name="filesystem.used_percent", clears_at=80.0),
            VerificationSignal(name="workload.error_rate", direction=SignalDirection.DOWN),
        )
    )

    verdict = declaration.verdict_for(
        before={"filesystem.used_percent": 96.0, "workload.error_rate": 1.0},
        after={"filesystem.used_percent": 60.0, "workload.error_rate": 8.0},
    )

    assert verdict is VerificationVerdict.WORSENED


def test_an_upward_signal_reads_the_opposite_way() -> None:
    """A scale is verified by replicas appearing, not by a number going down."""
    declaration = a_declaration(
        signals=(
            VerificationSignal(
                name="workload.ready_replicas",
                direction=SignalDirection.UP,
                clears_at=8.0,
            ),
        ),
    )

    assert (
        declaration.verdict_for(
            before={"workload.ready_replicas": 3.0},
            after={"workload.ready_replicas": 8.0},
        )
        is VerificationVerdict.EFFECTIVE
    )
    assert (
        declaration.verdict_for(
            before={"workload.ready_replicas": 3.0},
            after={"workload.ready_replicas": 1.0},
        )
        is VerificationVerdict.WORSENED
    )


def test_a_declaration_naming_a_signal_no_source_produces_is_refused() -> None:
    """T-002: the error names the signal and what the deployment does emit."""
    with pytest.raises(UnknownVerificationSignal) as refused:
        a_declaration().validate_against(("workload.error_rate", "node.load"))

    assert "filesystem.used_percent" in str(refused.value)
    assert "node.load" in str(refused.value)


def test_a_declaration_checked_against_a_catalogue_that_has_it_passes() -> None:
    """The check is a wiring check, so a correct wiring must be silent."""
    a_declaration().validate_against(("filesystem.used_percent",))


def test_an_unverifiable_declaration_needs_no_signal_catalogue() -> None:
    """It names no signal, so there is nothing for a catalogue to disagree with."""
    VerificationDeclaration.unverifiable("no signal maps to this").validate_against(())


def test_the_effect_may_be_visible_in_a_signal_other_than_the_one_that_fired() -> None:
    """T-033: the capability declares its own signals, not the detector's.

    A pod restarted because it was out of memory is verified by the restart
    count settling, not by memory — the two are different measurements and only
    one of them is about whether the action worked.
    """
    declaration = a_declaration(
        signals=(VerificationSignal(name="workload.restarts_per_hour", clears_at=1.0),)
    )

    assert declaration.names == ("workload.restarts_per_hour",)
    assert (
        declaration.verdict_for(
            before={"workload.restarts_per_hour": 12.0, "workload.memory_percent": 99.0},
            after={"workload.restarts_per_hour": 0.0, "workload.memory_percent": 99.0},
        )
        is VerificationVerdict.EFFECTIVE
    )
