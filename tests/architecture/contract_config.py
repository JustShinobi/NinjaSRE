"""Read the repository's declared import contracts.

Shared by the architecture tests so both read ``.importlinter`` the same way.
"""

from __future__ import annotations

import configparser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_CONFIG = REPO_ROOT / ".importlinter"

#: The root ``AGENTS.md`` holds the tier table the contracts enforce. It is the
#: source of truth because it ships with the repository: a contributor who clones
#: this and nothing else can still read the rule they are being held to.
ARCHITECTURE_DOC = REPO_ROOT / "AGENTS.md"

CONTRACT_SECTION_PREFIX = "importlinter:contract:"

# The ordering contract. It encodes the downward-only flow rather than one
# specific boundary, so it is broken by every violation of any other contract.
LAYERS_CONTRACT = "layers"


def declared_contracts() -> tuple[str, ...]:
    """Return the contract identifiers declared in ``.importlinter``, in order."""
    parser = configparser.ConfigParser()
    parser.read(CONTRACT_CONFIG, encoding="utf-8")
    return tuple(
        section.removeprefix(CONTRACT_SECTION_PREFIX)
        for section in parser.sections()
        if section.startswith(CONTRACT_SECTION_PREFIX)
    )
