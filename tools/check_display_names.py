"""Fail the build on a catalogue id with no display name.

An item of catalogue without a display name is a defect, not a fallback to
the raw id — the console must never be left titling a card, a list row or a
label with `azure_monitor` because nobody named it. Two catalogues declare a
`display_name` today, each in the vendor's or the provider's own module
rather than in a central map, so this cannot walk one list; it has to walk
two.

Both already hold the invariant at construction time —
`IntegrationProfile.__post_init__` and `ProviderOnboarding.__post_init__`
raise for a blank `display_name` before the offending profile exists to be
read. This is what makes the guard thin: it imports every declared vendor and
every declared provider, which is exactly the moment either invariant would
fire, and reports whichever one did rather than re-deriving the check.

Usage::

    python -m tools.check_display_names

Exits 0 when every declared catalogue entry names itself, 1 otherwise.
"""

from __future__ import annotations

import sys


def check() -> list[str]:
    """Return one message per catalogue that failed to declare a display name."""
    failures: list[str] = []

    try:
        from integrations._catalogue.discovery import profiles

        for name, profile in profiles().items():
            if not profile.display_name.strip():
                failures.append(f"integrations.{name}: PROFILE has a blank display_name")
    except (LookupError, TypeError, ValueError) as error:
        failures.append(f"the integration catalogue would not load: {error}")

    try:
        from core.llm.onboarding import all_onboardings

        for onboarding in all_onboardings():
            if not onboarding.display_name.strip():
                failures.append(
                    f"core.llm.onboarding.{onboarding.provider_id}: ONBOARDING has a blank "
                    f"display_name"
                )
    except (LookupError, TypeError, ValueError) as error:
        failures.append(f"the provider onboarding catalogue would not load: {error}")

    return failures


def main() -> int:
    """Print every failure found, and return the process exit code."""
    failures = check()
    if not failures:
        return 0
    print(f"{len(failures)} catalogue item(s) with no display name:", file=sys.stderr)
    for failure in failures:
        print(f"  {failure}", file=sys.stderr)
    print(
        "\nA display name is declared beside the item it names — IntegrationProfile in the "
        "vendor's own package, ProviderOnboarding in the provider's own module — never in a "
        "central map.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
