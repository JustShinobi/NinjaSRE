"""The staging smoke test must ask each service for the health path it serves.

This ran for the first time tonight and failed on its third call: it asks the
credential proxy for `/health`, and the proxy serves `/internal/health` — the
path `config/constants/security.py` declares and the proxy's own router is built
from. A 404, from a service that was up and answering.

It had been wrong since it was written and nobody knew, because the step before
it in the delivery pipeline failed first and the smoke contract was skipped
every time. Fixing that step is what made this visible.

Asserted against the constant rather than against a copy of the string, so a
path that moves takes this with it. The two health paths that are correct are
covered too — a test that only pinned the one that broke would let the next one
drift the same way.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from config.constants.security import PROXY_HEALTH_PATH

pytestmark = pytest.mark.contract

SMOKE = Path(__file__).resolve().parents[3] / "scripts" / "ci" / "smoke-stg"

#: What each component answers a liveness check on. The proxy's differs, which
#: is the whole reason this file exists: it is behind `/internal` because it is
#: the one surface an operator never browses to.
_HEALTH_PATHS = {
    "APP": "/health/live",
    "CONSOLE": "/health/live",
    "PROXY": PROXY_HEALTH_PATH,
}


def _default_url(component: str) -> str:
    """Return the URL the script falls back to for ``component``."""
    text = SMOKE.read_text(encoding="utf-8")
    found = re.search(rf"NINJASRE_SMOKE_{component}_URL:-(?P<url>[^}}]+)\}}", text)
    assert found, f"the smoke script names no default URL for {component}"
    return found.group("url")


def test_the_script_is_there_and_runnable() -> None:
    """The pipeline runs `test -x` on it before calling it, so a mode change is
    a failure at deploy time rather than at review time."""
    assert SMOKE.is_file()
    assert SMOKE.stat().st_mode & 0o111, f"{SMOKE} is not executable"


@pytest.mark.parametrize(("component", "path"), sorted(_HEALTH_PATHS.items()))
def test_each_component_is_asked_for_the_path_it_serves(component: str, path: str) -> None:
    url = _default_url(component)

    assert url.endswith(path), f"the smoke test asks {component} for {url!r}, not {path!r}"


def test_the_proxy_path_is_taken_from_the_constant_that_declares_it() -> None:
    """Not a second copy of the string. The proxy's router is built from this
    constant, so a smoke test holding its own spelling is one rename away from
    reporting a healthy deployment unreachable — or an unreachable one healthy."""
    assert PROXY_HEALTH_PATH in SMOKE.read_text(encoding="utf-8")
