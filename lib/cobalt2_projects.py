"""Guess a space's icon from what is checked out in it.

Herdr's sidebar renders text, so a project's real favicon cannot be shown: the
graphics APIs are pane-scoped. The next best identifier is the Nerd Font
developer glyph for the stack the checkout uses, which is what this module
picks.

Detection reads manifest files rather than file extensions first, because a
manifest names the framework (`next`, `django`, `laravel`) while extensions
only name the language. Extensions are the fallback.

Every codepoint here was verified present in JetBrainsMono Nerd Font. All are
in the basic multilingual plane private use area, matching the constraint the
mark table documents: tooling around Herdr treats only BMP PUA as printable
width-1 symbols.

Stdlib only. Herdr runs plugin commands with a minimal PATH and no site
packages, and /usr/bin/python3 is still 3.9 on macOS, so no tomllib.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import NamedTuple


class Icon(NamedTuple):
    #: Short name printed beside the glyph, so a wrong guess is obvious.
    label: str
    codepoint: int

    @property
    def glyph(self) -> str:
        return chr(self.codepoint)


ICONS = {
    "next": Icon("Next.js", 0xE78D),
    "nuxt": Icon("Nuxt", 0xE6A0),
    "vue": Icon("Vue", 0xE6A0),
    "svelte": Icon("Svelte", 0xE697),
    "astro": Icon("Astro", 0xE6B3),
    "angular": Icon("Angular", 0xE753),
    "react": Icon("React", 0xE7BA),
    "vite": Icon("Vite", 0xF0A1),
    "node": Icon("Node", 0xE718),
    "typescript": Icon("TypeScript", 0xE628),
    "javascript": Icon("JavaScript", 0xE74E),
    "deno": Icon("Deno", 0xE28C),
    "bun": Icon("Bun", 0xE76F),
    "django": Icon("Django", 0xE71D),
    "python": Icon("Python", 0xE73C),
    "rust": Icon("Rust", 0xE7A8),
    "go": Icon("Go", 0xE626),
    "laravel": Icon("Laravel", 0xE73F),
    "php": Icon("PHP", 0xE73D),
    "rails": Icon("Rails", 0xE73B),
    "ruby": Icon("Ruby", 0xE739),
    "java": Icon("Java", 0xE738),
    "kotlin": Icon("Kotlin", 0xE634),
    "swift": Icon("Swift", 0xE755),
    "dotnet": Icon(".NET", 0xE77F),
    "elixir": Icon("Elixir", 0xE62D),
    "zig": Icon("Zig", 0xE6A9),
    "flutter": Icon("Flutter", 0xE28E),
    "docker": Icon("Docker", 0xE7B0),
    "terraform": Icon("Terraform", 0xE81D),
    "html": Icon("HTML", 0xE736),
    "markdown": Icon("Docs", 0xE73E),
    "git": Icon("Git", 0xE702),
    "folder": Icon("Folder", 0xF07B),
}

#: Dependency names in package.json, most specific first: a Next.js app also
#: depends on react, and reporting React for it would be the less useful guess.
NODE_DEPENDENCIES = (
    ("next", "next"),
    ("nuxt", "nuxt"),
    ("@angular/core", "angular"),
    ("svelte", "svelte"),
    ("astro", "astro"),
    ("vue", "vue"),
    ("vite", "vite"),
    ("react", "react"),
)

#: Manifest file to detector. Every root in range is scanned, and the most
#: specific hit wins, so a monorepo whose root carries a generic manifest
#: still reports the framework its apps use.
MANIFESTS: tuple[tuple[str, str], ...] = (
    ("package.json", "_node"),
    ("pyproject.toml", "_python"),
    ("requirements.txt", "_python"),
    ("manage.py", "_django"),
    ("Cargo.toml", "_rust"),
    ("go.mod", "_go"),
    ("composer.json", "_php"),
    ("artisan", "_laravel"),
    ("Gemfile", "_ruby"),
    ("pubspec.yaml", "_flutter"),
    ("deno.json", "_deno"),
    ("bun.lockb", "_bun"),
    ("mix.exs", "_elixir"),
    ("build.zig", "_zig"),
    ("pom.xml", "_java"),
    ("build.gradle.kts", "_kotlin"),
    ("Package.swift", "_swift"),
    ("Dockerfile", "_docker"),
)

#: How specific each icon is. A framework identifies a project better than the
#: language it is written in, which in turn beats the container it ships in.
RANKS = {
    "docker": 1,
    "terraform": 1,
    "git": 0,
    "folder": 0,
}
FRAMEWORKS = frozenset(
    {
        "next",
        "nuxt",
        "angular",
        "svelte",
        "astro",
        "vue",
        "vite",
        "react",
        "django",
        "laravel",
        "rails",
        "flutter",
    }
)


def rank(name: str) -> int:
    if name in FRAMEWORKS:
        return 3
    return RANKS.get(name, 2)


#: Extension to detector, used when no manifest matched.
EXTENSIONS = {
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".py": "python",
    ".rs": "rust",
    ".go": "go",
    ".php": "php",
    ".rb": "ruby",
    ".java": "java",
    ".kt": "kotlin",
    ".swift": "swift",
    ".cs": "dotnet",
    ".ex": "elixir",
    ".zig": "zig",
    ".tf": "terraform",
    ".html": "html",
    ".md": "markdown",
}


def _node(path: Path) -> str:
    try:
        manifest = json.loads((path / "package.json").read_text())
    except (OSError, ValueError):
        return "node"
    declared = {
        name.lower()
        for key in ("dependencies", "devDependencies", "peerDependencies")
        for name in (manifest.get(key) or {})
    }
    for dependency, detector in NODE_DEPENDENCIES:
        if dependency in declared:
            return detector
    return "node"


def _text_has(path: Path, names: tuple[str, ...], needle: str) -> bool:
    for name in names:
        try:
            if needle in (path / name).read_text().lower():
                return True
        except OSError:
            continue
    return False


def _python(path: Path) -> str:
    if _text_has(path, ("pyproject.toml", "requirements.txt"), "django"):
        return "django"
    return "python"


def _php(path: Path) -> str:
    return "laravel" if _text_has(path, ("composer.json",), "laravel") else "php"


def _ruby(path: Path) -> str:
    return "rails" if _text_has(path, ("Gemfile",), "rails") else "ruby"


_FIXED = {
    "_django": "django",
    "_laravel": "laravel",
    "_rust": "rust",
    "_go": "go",
    "_flutter": "flutter",
    "_deno": "deno",
    "_bun": "bun",
    "_elixir": "elixir",
    "_zig": "zig",
    "_java": "java",
    "_kotlin": "kotlin",
    "_swift": "swift",
    "_docker": "docker",
}
_DYNAMIC = {"_node": _node, "_python": _python, "_php": _php, "_ruby": _ruby}


def detect(path: Path, depth: int = 3) -> Icon:
    """The icon for a checkout, searching nested app directories too.

    Every root within `depth` is scanned and the most specific hit wins, not
    the first: a monorepo root often carries a generic `package.json` while the
    framework that actually identifies the project lives a level or two down.
    """
    best: tuple[int, str] | None = None
    for root in _roots(path, depth):
        for filename, detector in MANIFESTS:
            if not (root / filename).exists():
                continue
            resolver = _DYNAMIC.get(detector)
            name = resolver(root) if resolver else _FIXED[detector]
            score = rank(name)
            # Ties keep the shallower root, which is the project itself rather
            # than one of its packages.
            if best is None or score > best[0]:
                best = (score, name)
    if best is not None:
        return ICONS[best[1]]

    counts: dict[str, int] = {}
    for root in _roots(path, depth):
        for child in _iterdir(root):
            detector = EXTENSIONS.get(child.suffix.lower())
            if child.is_file() and detector:
                counts[detector] = counts.get(detector, 0) + 1
    if counts:
        # Ties break on the detector name, so the same tree always resolves to
        # the same icon.
        return ICONS[max(sorted(counts), key=lambda name: counts[name])]
    if (path / ".git").exists():
        return ICONS["git"]
    return ICONS["folder"]


#: Directories that never identify the project itself.
SKIPPED = re.compile(r"^(\.|node_modules$|venv$|target$|dist$|build$|vendor$)")


def _roots(path: Path, depth: int) -> list[Path]:
    roots = [path]
    frontier = [path]
    for _ in range(max(0, depth - 1)):
        nested: list[Path] = []
        for root in frontier:
            for child in _iterdir(root):
                if child.is_dir() and not SKIPPED.match(child.name):
                    nested.append(child)
        roots += nested
        frontier = nested
    return roots


def _iterdir(path: Path) -> list[Path]:
    try:
        return sorted(path.iterdir())
    except OSError:
        return []
