"""Every shipped remediation capability says how anybody would know it worked.

T-004. Parameterised over the registry rather than over a list written here, so
an eighth capability landing without a declaration fails this file rather than
being discovered as a run of ``inconclusive`` verdicts nobody could explain.

Two of the seven are worth their own assertions.

``toggle_feature_flag`` declares itself *unverifiable*, with a reason: a flag's
effect appears in whatever the flag guards, which is not something the
capability can name. It is in the shipped set for the same reason
``clear_cache`` is the one with no derivable rollback — the unverifiable path is
exercised by the catalogue rather than being a branch nobody has run.

``clear_cache`` declares a clearing value, which is what makes ``ineffective``
distinguishable from ``inconclusive`` for it. Without one, a cache clear that
freed two per cent of a full disk would be reported as "cannot tell" rather than
as "did not work".
"""

from __future__ import annotations

import pytest

from capabilities.tools.remediation import COMPONENTS, registry
from config.constants.closed_loop import MAX_SETTLE_SECONDS, MIN_SETTLE_SECONDS
from platform.remediation.components import RemediationComponents
from platform.remediation.declaration import signals_of

pytestmark = pytest.mark.contract

CAPABILITIES = [(bundle.capability, bundle) for bundle in COMPONENTS]


@pytest.mark.parametrize(("name", "bundle"), CAPABILITIES, ids=[name for name, _ in CAPABILITIES])
def test_every_capability_declares_how_its_effect_is_verified(
    name: str,
    bundle: RemediationComponents,
) -> None:
    """A declaration, or a stated reason there can be none. Never neither."""
    declaration = bundle.verification

    assert declaration.verifiable or declaration.reason.strip(), (
        f"{name} declares neither a verification signal nor a reason it has none"
    )


@pytest.mark.parametrize(("name", "bundle"), CAPABILITIES, ids=[name for name, _ in CAPABILITIES])
def test_every_verifiable_capability_declares_a_settle_period_inside_the_bounds(
    name: str,
    bundle: RemediationComponents,
) -> None:
    """Below the floor it reads the sample the detector fired on; above it, nobody looks."""
    declaration = bundle.verification
    if not declaration.verifiable:
        return

    assert MIN_SETTLE_SECONDS <= declaration.settle_seconds <= MAX_SETTLE_SECONDS, name


def test_the_shipped_set_exercises_the_unverifiable_path() -> None:
    """FR-006 is a branch, and a branch nothing shipped takes is one nobody runs."""
    unverifiable = [
        bundle.capability for bundle in COMPONENTS if not bundle.verification.verifiable
    ]

    assert "toggle_feature_flag" in unverifiable


def test_the_shipped_set_names_the_signals_a_deployment_has_to_produce() -> None:
    """An operator wiring observation needs one list, not seven packages to read."""
    named = signals_of([bundle.verification for bundle in COMPONENTS])

    assert named
    assert "filesystem.used_percent" in named
    assert all(name == name.strip() and " " not in name for name in named)


def test_registering_against_a_catalogue_that_lacks_a_signal_is_refused() -> None:
    """T-002: the wiring mistake is caught where it is made."""
    from platform.remediation.errors import UnknownVerificationSignal

    with pytest.raises(UnknownVerificationSignal):
        registry(known_signals=("nothing.at.all",))


def test_registering_against_the_signals_the_set_declares_is_silent() -> None:
    """A correct wiring must not be noisy, or operators learn to pass nothing."""
    built = registry(known_signals=signals_of([bundle.verification for bundle in COMPONENTS]))

    assert len(built) == len(COMPONENTS)
