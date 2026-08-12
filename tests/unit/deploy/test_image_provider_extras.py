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

**The proxy and console do not.** The proxy injects credentials at the network
edge and never invokes a model; the console is a Node application. Shipping SDKs
into either is weight with no purpose.
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


@pytest.mark.parametrize("image", ["proxy.Dockerfile", "console.Dockerfile"])
def test_the_other_images_carry_no_model_sdk(image: str) -> None:
    """The proxy injects credentials and never invokes a model; the console is a
    Node application. An SDK in either is weight with no purpose."""
    assert not any("all-providers" in line for line in _install_lines(image))
