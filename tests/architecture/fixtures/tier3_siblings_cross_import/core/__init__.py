"""Legal tier 3 cross-import: core imports its sibling platform.

``core`` and ``platform`` are siblings, so the dependency may run either way.
Every contract must hold on this tree — it is the counterweight to the six
violating fixtures.
"""

import platform
