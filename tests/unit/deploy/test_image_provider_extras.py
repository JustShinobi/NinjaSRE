"""The application image ships the SDK its provider needs, or it ships nothing.

``pip install .`` installs the package with no extras, so no provider adapter is
importable. Every packaged deployment therefore came up healthy, accepted a
credential, and failed on its first investigation with a message about a missing
extra — which reads as a packaging mistake in the operator's environment and is
one in ours.

It went unnoticed because nothing fails until a model is actually invoked.
Health is green, the credential verifies, the console renders. The first thing
to notice is the first investigation, which is the worst possible moment.

**The application image carries every provider.** Which one an operator
configures is not knowable at build time, and an image that works for one
provider and not another is an image whose behaviour depends on a setting made
long after it was built.

**The proxy does not.** It injects credentials at the network edge and never
invokes a model, so an SDK in it is weight with no purpose.

**The console does**, and the reason is worth stating because the name misleads.
The image called ``console`` does not serve the Next.js console: its entry point
is the application's own, started on another port, and its own Dockerfile says
so — "the same wheel as the application, started at a different entry point".
It therefore imports what the application imports, model catalogue included,
and a bare install left it dying on import while the application beside it came
up fine. An image that runs the application needs what the application needs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

IMAGES = Path(__file__).resolve().parents[3] / "deploy" / "images"


def _install_lines(name: str) -> list[str]:
    text = (IMAGES / name).read_text(encoding="utf-8")
    return [line.strip() for line in text.splitlines() if "pip install" in line]


def test_the_application_image_installs_the_provider_extras() -> None:
    """Without them no provider adapter imports, and the failure surfaces at the
    first investigation rather than at build."""
    installs = _install_lines("app.Dockerfile")

    assert installs, "the application image installs nothing"
    assert any("[all-providers]" in line for line in installs)


def test_the_application_image_does_not_install_the_package_bare() -> None:
    """The defect, stated as the thing that must not come back: a bare install
    passes every check this repository has and produces an image that cannot
    run a model."""
    installs = _install_lines("app.Dockerfile")

    assert not any(
        line.endswith("pip install --no-cache-dir .") or line.endswith("pip install .")
        for line in installs
    )


def test_the_proxy_carries_no_model_sdk() -> None:
    """It injects credentials at the network edge and never invokes a model, so
    the extras would be weight with no purpose."""
    assert not any("all-providers" in line for line in _install_lines("proxy.Dockerfile"))


def test_the_console_image_carries_them_because_it_runs_the_application() -> None:
    """The image named ``console`` runs the application's entry point.

    Stated as its own test rather than as an exception to the one above,
    because it is not an exception: the rule is that an image installs what its
    entry point imports, and both of these follow it. Reading the console's
    entry point out of its Dockerfile is what keeps this honest — if the image
    ever becomes the Node application its name suggests, this test fails and
    asks to be reconsidered rather than quietly protecting dead weight.
    """
    dockerfile = (IMAGES / "console.Dockerfile").read_text(encoding="utf-8")

    assert "gateway.http.serve" in dockerfile, (
        "this test exists because the console image runs the application; if it no "
        "longer does, the extras it carries need a fresh argument"
    )
    assert any("[all-providers]" in line for line in _install_lines("console.Dockerfile"))
