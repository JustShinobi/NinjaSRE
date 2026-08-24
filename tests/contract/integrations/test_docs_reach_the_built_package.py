"""Every vendor's docs.md, proven to survive packaging rather than assumed to.

The documentation route reads a file that lives inside a vendor's Python
package. If the built wheel did not carry it, the route would answer with a
read failure in every real deployment and pass in every local checkout —
exactly the shape of failure a check that only ever runs against a checkout
cannot catch. This builds the actual wheel `pip install .` would install and
opens it, rather than trusting the packaging configuration by reading it.
"""

from __future__ import annotations

import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

from integrations._catalogue.discovery import repository_root, vendor_packages

pytestmark = pytest.mark.contract

#: ``uv`` is a standalone binary, not a module this interpreter can run with
#: ``-m`` — the same toolchain the rest of this repository's build already
#: depends on, resolved from ``PATH`` rather than assumed to be at a fixed
#: location.
_UV = shutil.which("uv")


@pytest.mark.skipif(_UV is None, reason="uv is not on PATH; this environment cannot build a wheel")
def test_every_vendors_docs_md_is_inside_the_built_wheel(tmp_path: Path) -> None:
    root = repository_root()
    assert _UV is not None  # narrows for mypy; the skipif above already guards this
    built = subprocess.run(
        [_UV, "build", "--wheel", "-o", str(tmp_path)],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert built.returncode == 0, built.stderr

    wheels = sorted(tmp_path.glob("*.whl"))
    assert len(wheels) == 1, f"expected exactly one built wheel, found {wheels}"

    with zipfile.ZipFile(wheels[0]) as archive:
        names = set(archive.namelist())

    missing = sorted(
        vendor for vendor in vendor_packages() if f"integrations/{vendor}/docs.md" not in names
    )
    assert missing == [], (
        f"{missing} shipped no docs.md in the built wheel — the documentation route "
        f"would answer a read failure for these in any deployment built from it, "
        f"while every local checkout keeps passing every other check"
    )
