"""Agent mark table shared by the sidebar reporter, the font tool, and the
theme writer.

Herdr recognizes far more harnesses than the agent-icons plugin ships marks
for, so rows for the rest render with no logo at all. This table fills every
gap, using two glyph sources:

- "harness": U+E1A0-U+E1A8 from the agent-icons font, "Herdr Harness Logos".
  These are real vendored brand marks. The codepoints are that plugin's
  permanent assignments, so they are mirrored here rather than reassigned.
- "nerd": a glyph borrowed from the terminal's primary Nerd Font. Some are the
  actual brand mark (Copilot), others are mnemonics (an X for xAI's Grok).

Borrowed codepoints are restricted to the basic multilingual plane private use
area, U+E000-U+F8FF. Glyphs in the supplementary PUA (many Material Design
icons, for instance) are excluded on purpose: tooling around Herdr commonly
treats only the BMP range as printable width-1 symbols.

Stdlib only. Herdr runs plugin commands with a minimal PATH and no site
packages, so this module must stay importable from that environment.
"""

from __future__ import annotations

from typing import NamedTuple

HARNESS_FONT_FAMILY = "Herdr Harness Logos"

# Cobalt2 palette, mirrored from bin/apply-cobalt2's [theme.custom] block.
ACCENT = "#ffc600"
_PEACH = "#ff9d00"
_TEAL = "#80fcff"
_STONE = "#82a7bd"
_MAUVE = "#fb94ff"
_GREEN = "#3ad900"
_RED = "#ff628c"
_BLUE = "#0088ff"
_TEXT = "#d6deeb"
_WHITE = "#ffffff"


class Mark(NamedTuple):
    """One agent's sidebar mark."""

    codepoint: int
    #: Printable ASCII shown when the glyph font is unavailable.
    text: str
    #: Sidebar foreground. ACCENT costs no styling rule, see rule_specs().
    color: str
    #: "harness" for the agent-icons font, "nerd" for the primary Nerd Font.
    source: str


def _harness(codepoint: int, text: str, color: str) -> Mark:
    return Mark(codepoint, text, color, "harness")


def _nerd(codepoint: int, text: str, color: str) -> Mark:
    return Mark(codepoint, text, color, "nerd")


# Keyed by the agent id Herdr reports. Herdr's canonical ids and its runtime
# names disagree in a few places (github_copilot vs copilot, open_code vs
# opencode), so both spellings are present and resolve to the same mark.
MARKS: dict[str, Mark] = {
    # Vendored marks, from the agent-icons font.
    "claude": _harness(0xE1A0, "C", _PEACH),
    "codex": _harness(0xE1A1, "AI", _TEAL),
    "opencode": _harness(0xE1A2, "OC", _STONE),
    "open_code": _harness(0xE1A2, "OC", _STONE),
    "omp": _harness(0xE1A3, "OMP", ACCENT),
    "pi": _harness(0xE1A3, "OMP", ACCENT),
    "cline": _harness(0xE1A4, "CL", _GREEN),
    "mastracode": _harness(0xE1A5, "MC", ACCENT),
    "kimi": _harness(0xE1A6, "KIM", _MAUVE),
    "kilo": _harness(0xE1A7, "KIL", _RED),
    "maki": _harness(0xE1A8, "MAK", ACCENT),
    # Borrowed Nerd Font glyphs. Comments name the glyph and why it was picked.
    "cursor": _nerd(0xF1B2, "CUR", _BLUE),  # fa-cube
    "grok": _nerd(0xF467, "GRK", _WHITE),  # oct-x, for xAI's X brand
    "copilot": _nerd(0xEC1E, "GHC", _TEXT),  # cod-copilot, the real brand mark
    "github_copilot": _nerd(0xEC1E, "GHC", _TEXT),
    "gemini": _nerd(0xEC10, "GEM", _GREEN),  # cod-sparkle, echoes the spark logo
    "kiro": _nerd(0xE71F, "KIR", _MAUVE),  # dev-ghost, for the ghost mascot
    "droid": _nerd(0xE70E, "DRD", _GREEN),  # dev-android
    # fa-feather, for winged Hermes. Left on the accent because the obvious
    # alternative, cyan, is too close to the teal used for Codex to tell apart.
    "hermes": _nerd(0xEDF7, "HRM", ACCENT),
    "agy": _nerd(0xEB44, "AGY", ACCENT),  # cod-rocket, for Antigravity
    "muse": _nerd(0xEC1B, "MUS", ACCENT),  # cod-music
    "amp": _nerd(0xF0E7, "AMP", ACCENT),  # fa-flash
    "devin": _nerd(0xE28C, "DVN", _BLUE),  # fae-brain
    "qwen": _nerd(0xE27F, "QWN", _BLUE),  # fae-atom
    "qwen-code": _nerd(0xE27F, "QWN", _BLUE),
    "qodercli": _nerd(0xEC19, "QOD", ACCENT),  # cod-chip
    "qoder": _nerd(0xEC19, "QOD", ACCENT),
}

#: Herdr rejects config with more than 16 rules on a single token.
MAX_STYLE_RULES = 16
#: Rules left unused, so the user can add their own without hitting the wall.
RULE_HEADROOM = 2


def glyph(agent: str) -> str | None:
    mark = MARKS.get(agent)
    return chr(mark.codepoint) if mark else None


def text_fallback(agent: str) -> str | None:
    mark = MARKS.get(agent)
    return mark.text if mark else None


def codepoints(source: str | None = None) -> list[int]:
    """Distinct codepoints, optionally filtered to one glyph source."""
    return sorted({mark.codepoint for mark in MARKS.values() if source in (None, mark.source)})


def rule_specs() -> list[tuple[int, str]]:
    """(codepoint, color) pairs that need an explicit sidebar styling rule.

    Marks colored with ACCENT are omitted, because the token's base style
    already paints them that color. That keeps the generated config inside
    Herdr's per-token rule ceiling with room to spare.
    """
    by_codepoint = {
        mark.codepoint: mark.color for mark in MARKS.values() if mark.color != ACCENT
    }
    return sorted(by_codepoint.items())
