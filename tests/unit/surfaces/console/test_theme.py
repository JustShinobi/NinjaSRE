"""Both palettes, checked against the number WCAG 2.1 AA actually states.

A palette is not reviewed by looking at it. Every foreground-on-background pair
the console uses is computed here, in both themes, and a change that drops one
below its threshold fails rather than shipping — which is the only way a
contrast requirement survives the third redesign.
"""

from __future__ import annotations

import pytest

from surfaces.console.theme import (
    DARK,
    LIGHT,
    MINIMUM_CONTRAST_BODY,
    MINIMUM_CONTRAST_LARGE,
    PALETTES,
    Palette,
    contrast_ratio,
    relative_luminance,
    stylesheet,
)

_PALETTES = pytest.mark.parametrize("palette", [LIGHT, DARK], ids=["light", "dark"])


def test_the_luminance_of_the_two_extremes_is_the_two_extremes() -> None:
    assert relative_luminance("#000000") == pytest.approx(0.0)
    assert relative_luminance("#ffffff") == pytest.approx(1.0)


def test_black_on_white_is_the_maximum_ratio_the_scale_defines() -> None:
    assert contrast_ratio("#000000", "#ffffff") == pytest.approx(21.0, abs=0.01)


def test_a_colour_against_itself_is_the_minimum_ratio() -> None:
    assert contrast_ratio("#3366aa", "#3366aa") == pytest.approx(1.0)


def test_the_ratio_does_not_depend_on_which_colour_is_named_first() -> None:
    assert contrast_ratio("#16191d", "#ffffff") == contrast_ratio("#ffffff", "#16191d")


def test_a_colour_that_is_not_six_hex_digits_is_refused() -> None:
    with pytest.raises(ValueError, match="#rrggbb"):
        relative_luminance("#fff")


@_PALETTES
def test_every_body_text_pair_meets_the_four_and_a_half_to_one_rule(palette: Palette) -> None:
    failures = [
        f"{what}: {contrast_ratio(foreground, background):.2f}:1"
        for what, foreground, background in palette.body_pairs()
        if contrast_ratio(foreground, background) < MINIMUM_CONTRAST_BODY
    ]

    assert not failures, f"{palette.name} theme below {MINIMUM_CONTRAST_BODY}:1 — {failures}"


@_PALETTES
def test_every_control_boundary_meets_the_three_to_one_rule(palette: Palette) -> None:
    failures = [
        f"{what}: {contrast_ratio(foreground, background):.2f}:1"
        for what, foreground, background in palette.boundary_pairs()
        if contrast_ratio(foreground, background) < MINIMUM_CONTRAST_LARGE
    ]

    assert not failures, f"{palette.name} theme below {MINIMUM_CONTRAST_LARGE}:1 — {failures}"


def test_both_themes_define_exactly_the_same_token_names() -> None:
    assert set(LIGHT.tokens()) == set(DARK.tokens())


def test_a_screen_written_against_tokens_gets_both_themes_without_knowing() -> None:
    sheet = stylesheet()

    assert "prefers-color-scheme: dark" in sheet
    for name in LIGHT.tokens():
        assert f"--{name}:" in sheet


def test_the_stylesheet_carries_a_focus_ring_because_it_is_a_requirement_not_a_style() -> None:
    assert ":focus-visible" in stylesheet()


def test_the_stylesheet_carries_a_skip_link_that_is_hidden_until_focused() -> None:
    sheet = stylesheet()

    assert ".skip-link" in sheet
    assert ".skip-link:focus" in sheet


def test_both_palettes_are_reachable_by_name_because_a_preference_is_a_string() -> None:
    assert set(PALETTES) == {"light", "dark"}
