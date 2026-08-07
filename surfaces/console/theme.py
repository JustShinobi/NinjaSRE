"""Two themes, and the contrast arithmetic that decides whether either is usable.

The palette is not a matter of taste here. WCAG 2.1 AA states a number — 4.5:1
for body text, 3:1 for large text and for the boundary of a control — and a
palette either meets it or it does not. So the ratio is computed from the tokens
rather than eyeballed, and ``tests/unit/surfaces/console/test_theme.py`` asserts
every foreground-on-background pair the console actually uses.

That is also why the two themes are declared as the same token names with
different values. A screen written against ``--text`` and ``--surface`` works in
both by construction; one written against a colour works in whichever it was
written for, and the other is the one somebody is using at three in the morning.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

#: WCAG 2.1 AA, 1.4.3. Body text and anything below 18.66px bold / 24px regular.
MINIMUM_CONTRAST_BODY: Final = 4.5

#: WCAG 2.1 AA, 1.4.3 and 1.4.11. Large text, and the visual boundary of a
#: control — a button's border, an input's outline, a focus ring.
MINIMUM_CONTRAST_LARGE: Final = 3.0


@dataclass(frozen=True, slots=True)
class Palette:
    """One theme's colours, by role rather than by name.

    ``danger`` is the only role that carries meaning on its own, and it is never
    the *only* carrier: an approval that would be destructive says so in words
    as well, because eight per cent of men cannot tell it from ``accent``.
    """

    name: str
    surface: str
    surface_raised: str
    text: str
    text_muted: str
    accent: str
    accent_text: str
    border: str
    danger: str
    danger_text: str
    success: str
    warning: str

    def tokens(self) -> Mapping[str, str]:
        """Return the CSS custom properties this palette defines."""
        return {
            "surface": self.surface,
            "surface-raised": self.surface_raised,
            "text": self.text,
            "text-muted": self.text_muted,
            "accent": self.accent,
            "accent-text": self.accent_text,
            "border": self.border,
            "danger": self.danger,
            "danger-text": self.danger_text,
            "success": self.success,
            "warning": self.warning,
        }

    def body_pairs(self) -> tuple[tuple[str, str, str], ...]:
        """Return every ``(what, foreground, background)`` that must reach 4.5:1."""
        return (
            ("text on surface", self.text, self.surface),
            ("text on raised surface", self.text, self.surface_raised),
            ("muted text on surface", self.text_muted, self.surface),
            ("muted text on raised surface", self.text_muted, self.surface_raised),
            ("accent text on accent", self.accent_text, self.accent),
            ("danger text on danger", self.danger_text, self.danger),
        )

    def boundary_pairs(self) -> tuple[tuple[str, str, str], ...]:
        """Return every ``(what, foreground, background)`` that must reach 3:1."""
        return (
            ("border on surface", self.border, self.surface),
            ("accent on surface", self.accent, self.surface),
            ("danger on surface", self.danger, self.surface),
            ("success on surface", self.success, self.surface),
            ("warning on surface", self.warning, self.surface),
        )


#: The default. Chosen for a bright office and a laptop screen at full daylight.
LIGHT: Final[Palette] = Palette(
    name="light",
    surface="#ffffff",
    surface_raised="#f4f5f7",
    text="#16191d",
    text_muted="#585f69",
    accent="#0b5cab",
    accent_text="#ffffff",
    border="#6b7280",
    danger="#9b1c1c",
    danger_text="#ffffff",
    success="#146c43",
    warning="#8a5300",
)

#: What an on-call engineer has at three in the morning, which is when the
#: console is most used and when a bright page is least welcome.
DARK: Final[Palette] = Palette(
    name="dark",
    surface="#0f1216",
    surface_raised="#191d23",
    text="#eef1f5",
    text_muted="#a8b1bd",
    accent="#6aa9f0",
    accent_text="#0b1520",
    border="#8a93a0",
    danger="#f08d8d",
    danger_text="#2a0c0c",
    success="#6ede9d",
    warning="#e8b872",
)

PALETTES: Final[Mapping[str, Palette]] = {LIGHT.name: LIGHT, DARK.name: DARK}


def relative_luminance(colour: str) -> float:
    """Return the WCAG relative luminance of a ``#rrggbb`` colour, 0.0 to 1.0."""
    red, green, blue = (_linear(channel) for channel in _channels(colour))
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast_ratio(foreground: str, background: str) -> float:
    """Return the WCAG contrast ratio between two colours, 1.0 to 21.0."""
    first = relative_luminance(foreground)
    second = relative_luminance(background)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


def stylesheet() -> str:
    """Return the console's whole stylesheet, both themes included.

    One sheet with a media query rather than two sheets and a preference read on
    the server: the operating system already knows which the user wants, and a
    server that guessed would get it wrong for everybody who changed it after
    the page loaded.
    """
    light = _tokens_block(":root", LIGHT)
    dark = _tokens_block(":root", DARK)
    return (
        f"{light}\n"
        f"@media (prefers-color-scheme: dark) {{ {dark} }}\n"
        f'[data-theme="dark"] {{ {_declarations(DARK)} }}\n'
        f'[data-theme="light"] {{ {_declarations(LIGHT)} }}\n'
        f"{_LAYOUT}"
    )


def _tokens_block(selector: str, palette: Palette) -> str:
    """Return one selector's custom-property block."""
    return f"{selector} {{ {_declarations(palette)} }}"


def _declarations(palette: Palette) -> str:
    """Return the custom-property declarations for ``palette``."""
    return " ".join(f"--{name}: {value};" for name, value in palette.tokens().items())


def _channels(colour: str) -> tuple[int, int, int]:
    """Return the three 8-bit channels of a ``#rrggbb`` colour."""
    value = colour.lstrip("#")
    if len(value) != 6:
        raise ValueError(f"{colour!r} is not a #rrggbb colour")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def _linear(channel: int) -> float:
    """Return one 8-bit channel converted to linear light, per WCAG 2.1."""
    proportion = channel / 255.0
    if proportion <= 0.04045:
        return proportion / 12.92
    return float(((proportion + 0.055) / 1.055) ** 2.4)


#: Layout, spacing, and the two behaviours that are accessibility requirements
#: rather than styling: a focus ring that is always visible (2.4.7), and a
#: skip link that is off-screen until focused (2.4.1).
_LAYOUT: Final = """
*, *::before, *::after { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--surface);
  color: var(--text);
  font: 16px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif;
}
a { color: var(--accent); }
:focus-visible { outline: 3px solid var(--accent); outline-offset: 2px; }
.skip-link {
  position: absolute; left: -9999px;
  background: var(--surface-raised); color: var(--text); padding: .75rem 1rem;
}
.skip-link:focus { left: .5rem; top: .5rem; z-index: 10; }
.shell { display: flex; flex-direction: column; min-height: 100vh; }
.shell__nav ul { display: flex; flex-wrap: wrap; gap: .25rem; list-style: none; margin: 0; padding: .5rem; }
.shell__nav a { display: block; padding: .5rem .75rem; border-radius: .375rem; text-decoration: none; }
.shell__nav a[aria-current="page"] { background: var(--accent); color: var(--accent-text); }
main { padding: 1rem; flex: 1; width: 100%; max-width: 80rem; margin: 0 auto; }
h1 { margin-top: 0; }
/* Every control the console renders comes from ``shell.form_field``, which wraps
   the label and the input in a ``.field``. Without a rule here the two sit flush
   against each other — "API token[input]" — on every form on every page. */
.field { display: flex; flex-direction: column; gap: .25rem; margin-bottom: .75rem; }
.field:has(> input[type="checkbox"]), .field:has(> input[type="radio"]) {
  flex-direction: row-reverse; align-items: center; justify-content: flex-end; gap: .5rem;
}
.field > label { font-weight: 600; }
.field > p { margin: 0; font-size: .875rem; }
input, select, textarea {
  font: inherit; padding: .5rem; max-width: 32rem;
  border: 1px solid var(--border); border-radius: .375rem;
  background: var(--surface); color: var(--text);
}
input[type="checkbox"], input[type="radio"] { width: auto; padding: 0; }
textarea { min-height: 4.5rem; }
fieldset { border: 1px solid var(--border); border-radius: .375rem; padding: .75rem 1rem; margin: 0 0 1rem; }
legend { font-weight: 600; padding: 0 .25rem; }
form > button, form > .button { margin-top: .25rem; }
.banner--impersonation {
  background: var(--warning); color: var(--surface);
  padding: .75rem 1rem; font-weight: 700;
  border-bottom: 4px solid var(--danger);
}
.card { background: var(--surface-raised); border: 1px solid var(--border);
        border-radius: .5rem; padding: 1rem; margin-bottom: 1rem; }
.card--danger { border-left: 6px solid var(--danger); }
table { border-collapse: collapse; width: 100%; }
th, td { border-bottom: 1px solid var(--border); padding: .5rem; text-align: left; }
.transcript { list-style: none; margin: 0; padding: 0; }
.transcript__event { border-bottom: 1px solid var(--border); padding: .5rem 0; }
.muted { color: var(--text-muted); }
.tree ul { list-style: none; padding-left: 1rem; border-left: 1px solid var(--border); }
button, .button {
  font: inherit; padding: .5rem .875rem; border-radius: .375rem;
  border: 1px solid var(--border); background: var(--surface-raised); color: var(--text);
}
button.primary { background: var(--accent); color: var(--accent-text); border-color: var(--accent); }
button.danger { background: var(--danger); color: var(--danger-text); border-color: var(--danger); }
@media (max-width: 40rem) {
  main { padding: .5rem; }
  table, thead, tbody, th, td, tr { display: block; }
  thead { position: absolute; left: -9999px; }
  td { border: none; padding: .25rem .5rem; }
  tr { border-bottom: 1px solid var(--border); padding: .5rem 0; }
  td::before { content: attr(data-label) ": "; font-weight: 700; }
}
"""


__all__ = [
    "DARK",
    "LIGHT",
    "MINIMUM_CONTRAST_BODY",
    "MINIMUM_CONTRAST_LARGE",
    "PALETTES",
    "Palette",
    "contrast_ratio",
    "relative_luminance",
    "stylesheet",
]
