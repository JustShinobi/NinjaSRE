"""Deliberate boundary violation: tier 4 config imports core.

This module exists to be rejected. ``config-is-a-leaf`` must report it, and no other
forbidden or independence contract may fire on this fixture tree.
"""

import core
