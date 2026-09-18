"""Agent mark table shared by the sidebar reporter, the font tool, and the
theme writer.

Herdr recognizes more harnesses than have dedicated brand artwork, so this
table combines two glyph sources:

- "harness": U+E1A0-U+E1A8 from the "Herdr Harness Logos" font bundled in
  this repository. The corresponding vector sources and license notices live
  under assets/.
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

import os
import re
from pathlib import Path
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
    #: "harness" for the bundled logo font, "nerd" for the primary Nerd Font.
    source: str


def _harness(codepoint: int, text: str, color: str) -> Mark:
    return Mark(codepoint, text, color, "harness")


def _nerd(codepoint: int, text: str, color: str) -> Mark:
    return Mark(codepoint, text, color, "nerd")


#: Key of the fallback mark used when no branded mark applies.
GENERIC = "generic"


# Keyed by the agent id Herdr reports. Herdr's canonical ids and its runtime
# names disagree in a few places (github_copilot vs copilot, open_code vs
# opencode), so both spellings are present and resolve to the same mark.
MARKS: dict[str, Mark] = {
    # Brand marks from the font bundled in dist/.
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
    # Fallback for a harness the table has no artwork for, assigned by
    # lib/cobalt2_resolve.py. Not an id Herdr reports: it is a bucket. Kept on
    # the accent so it costs no styling rule, which matters because
    # rule_specs() is already at its budget.
    GENERIC: _nerd(0xEB08, "AGT", ACCENT),  # cod-hubot, a generic robot
}

#: Herdr rejects config with more than 16 rules on a single token.
MAX_STYLE_RULES = 16
#: Rules left unused, so the user can add their own without hitting the wall.
RULE_HEADROOM = 2

#: Braille blank, reported as the value of a padding token. Herdr drops
#: whitespace-only metadata (a plain space and U+00A0 both vanish), so a blank
#: row needs a glyph that is printable but draws nothing.
PAD_GLYPH = "\u2800"
#: Padding rows are separate tokens above and below an entry, so the level can
#: choose one or both. A terminal grid has no fraction of a row: one row is the
#: smallest step, which makes level 1 (below only) the half-height option and
#: level 2 the smallest symmetric one.
PAD_TOKEN_BELOW = "cobalt2_pad"
PAD_TOKEN_ABOVE = "cobalt2_pad_top"
#: Plugin config key selecting the level: 0 none, 1 below only, 2 both.
PAD_CONFIG_KEY = "row_padding"
#: Per-section overrides. The agent and space panels render different numbers
#: of content rows, so one shared level makes one of them look heavier.
PAD_CONFIG_KEY_AGENTS = "row_padding_agents"
PAD_CONFIG_KEY_SPACES = "row_padding_spaces"
PAD_LEVELS = (0, 1, 2)
#: Shipped defaults, tuned against a real sidebar: the agent entry carries two
#: content rows and looks balanced with padding above and below, while the
#: space entry reads as heavier at the same level and takes one row.
DEFAULT_PAD_LEVEL = 2
DEFAULT_PAD_LEVEL_SPACES = 1
#: Plugin config key for the blank rows Herdr puts *between* entries. Those
#: rows sit outside the active-row highlight, so a gap separates entries
#: without making the highlight itself taller.
GAP_CONFIG_KEY = "row_gap"
DEFAULT_ROW_GAP = 0


def plugin_config_path() -> Path:
    configured = os.environ.get("HERDR_PLUGIN_CONFIG_DIR")
    root = (
        Path(configured)
        if configured
        else Path.home() / ".config/herdr/plugins/config/herdr-theme-cobalt2"
    )
    return root / "config.toml"


def _config_int(key: str, default: int, path: Path | None) -> int:
    """One integer key from the plugin config.

    Read with a regex rather than tomllib, which is absent from the Python 3.9
    that /usr/bin/python3 still is on macOS.
    """
    path = path or plugin_config_path()
    if not path.is_file():
        return default
    match = re.search(rf"^\s*{key}\s*=\s*(\d+)\s*$", path.read_text(), re.MULTILINE)
    return default if match is None else int(match.group(1))


def configured_padding(section: str | None = None, path: Path | None = None) -> int:
    """Padding rows per entry: 0, 1 (below), or 2 (above and below).

    `section` is "agents" or "spaces". Its own key wins over the shared
    `row_padding`, which in turn wins over the section's shipped default.
    """
    sections = {
        "agents": (PAD_CONFIG_KEY_AGENTS, DEFAULT_PAD_LEVEL),
        "spaces": (PAD_CONFIG_KEY_SPACES, DEFAULT_PAD_LEVEL_SPACES),
    }
    key, default = sections.get(section or "", (PAD_CONFIG_KEY, DEFAULT_PAD_LEVEL))
    shared = _config_int(PAD_CONFIG_KEY, default, path)
    level = shared if key == PAD_CONFIG_KEY else _config_int(key, shared, path)
    if level not in PAD_LEVELS:
        raise ValueError(
            f"invalid {key} {level} in {path or plugin_config_path()}; "
            f"expected 0, 1, or 2"
        )
    return level


def configured_row_gap(path: Path | None = None) -> int:
    """Blank rows Herdr leaves between sidebar entries, outside the highlight."""
    return _config_int(GAP_CONFIG_KEY, DEFAULT_ROW_GAP, path)


def pad_token_args(level: int) -> list[str]:
    """`herdr report-metadata` arguments for the padding tokens.

    Tokens the level excludes are cleared rather than skipped, so lowering the
    level removes rows that were already reported.
    """
    args: list[str] = []
    for token, needed in ((PAD_TOKEN_BELOW, level >= 1), (PAD_TOKEN_ABOVE, level >= 2)):
        args += ["--token", f"{token}={PAD_GLYPH}"] if needed else ["--clear-token", token]
    return args


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
