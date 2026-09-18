"""Read and write single-level key/value tables in the plugin's own config.

Both the space icon picker and the agent mark resolver persist a flat
`key = "value"` table into the plugin's config directory, next to whatever the
user wrote by hand. That file is the user's, so a write must replace exactly
one table and leave every other line untouched.

No tomllib: Herdr runs plugin commands with a bare `python3`, and
/usr/bin/python3 is still 3.9 on macOS. A regex is enough because these tables
are flat, string-valued, and written by this plugin; hand edits round-trip as
long as they stay in that shape.

Stdlib only.
"""

from __future__ import annotations

import re
from pathlib import Path

import cobalt2_marks

#: Verdicts written by lib/cobalt2_resolve.py, keyed by the agent id Herdr
#: reports. Declared here, not in the resolver, so bin/agent-marks can read the
#: cache on its hook path without importing anything that talks to a network.
AGENT_MARKS_SECTION = "agent_marks"
AGENT_MARKS_HEADER = "# Written by the herdr-theme-cobalt2 agent mark resolver."
#: Cached value meaning "asked, and no mark applies". Keeps the plugin from
#: re-querying an id that names no coding agent at all.
NO_MARK = "none"

#: One `key = "value"` line. Bare and quoted keys both round-trip.
ENTRY_RE = re.compile(
    r'^\s*(?:"(?P<quoted>[^"]+)"|(?P<bare>[A-Za-z0-9_.-]+))\s*=\s*"(?P<value>[^"]*)"\s*$',
    re.MULTILINE,
)
#: TOML bare keys; anything else has to be quoted when written back.
BARE_KEY_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def config_path() -> Path:
    return cobalt2_marks.plugin_config_path()


def section_re(section: str) -> re.Pattern[str]:
    """Matches one `[section]` table up to the next table header."""
    return re.compile(rf"(?ms)^\[{re.escape(section)}\]\n.*?(?=^\[|\Z)")


def load_table(section: str, path: Path | None = None) -> dict[str, str]:
    """The table's entries, keys lowercased so lookups ignore case."""
    path = path or config_path()
    if not path.is_file():
        return {}
    found = section_re(section).search(path.read_text())
    if found is None:
        return {}
    table: dict[str, str] = {}
    for match in ENTRY_RE.finditer(found.group(0)):
        key = match.group("quoted") or match.group("bare")
        table[key.strip().lower()] = match.group("value")
    return table


def render_table(
    section: str, values: dict[str, str], header: str, first_key: str | None = None
) -> str:
    def key_of(key: str) -> str:
        return key if BARE_KEY_RE.match(key) else f'"{key}"'

    # `first_key` first, then alphabetical, so hand edits stay predictable.
    ordered = [first_key] if first_key and first_key in values else []
    ordered += sorted(key for key in values if key != first_key)
    lines = [f"[{section}]", header]
    lines += [f'{key_of(key)} = "{values[key]}"' for key in ordered]
    return "\n".join(lines) + "\n"


def save_table(
    section: str,
    values: dict[str, str],
    path: Path | None = None,
    header: str = "",
    first_key: str | None = None,
) -> Path:
    """Rewrite only this table, leaving every other key in the file alone."""
    path = path or config_path()
    pattern = section_re(section)
    original = path.read_text() if path.is_file() else ""
    if not values:
        updated = pattern.sub("", original).rstrip("\n")
        updated = f"{updated}\n" if updated else ""
    else:
        block = render_table(section, values, header, first_key)
        if pattern.search(original):
            # A function replacement: values may contain backslash escapes that
            # re.sub would otherwise read as template references.
            updated = pattern.sub(lambda _: block + "\n", original, count=1)
            updated = updated.rstrip("\n") + "\n"
        else:
            head = original.rstrip("\n")
            updated = (f"{head}\n\n" if head else "") + block
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(updated)
    tmp.replace(path)
    return path
