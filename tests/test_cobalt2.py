"""Tests for the Cobalt2 theme plugin.

Stdlib only, so this runs anywhere the plugin does:

    python3 -m unittest discover -s tests
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "lib"))

import cobalt2_marks  # noqa: E402

BMP_PUA = range(0xE000, 0xF900)
#: Stable assignments in this repository's bundled logo font.
HARNESS_RANGE = range(0xE1A0, 0xE1A9)


def load_script(name: str):
    """Import one of the extensionless bin/ scripts as a module."""
    path = PLUGIN_ROOT / "bin" / name
    spec = importlib.util.spec_from_loader(
        name.replace("-", "_"), importlib.machinery.SourceFileLoader(name.replace("-", "_"), str(path))
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


class MarkTableTest(unittest.TestCase):
    def test_every_mark_is_in_the_bmp_private_use_area(self):
        """Herdr and terminal tooling only treat BMP PUA marks as width-1 symbols."""
        for agent, mark in cobalt2_marks.MARKS.items():
            with self.subTest(agent=agent):
                self.assertIn(mark.codepoint, BMP_PUA)

    def test_vendored_marks_match_the_font_manifest(self):
        """The bundled font reserves one contiguous codepoint range."""
        vendored = cobalt2_marks.codepoints("harness")
        self.assertEqual(vendored, list(HARNESS_RANGE))

    def test_borrowed_marks_avoid_the_vendored_range(self):
        for codepoint in cobalt2_marks.codepoints("nerd"):
            with self.subTest(codepoint=hex(codepoint)):
                self.assertNotIn(codepoint, HARNESS_RANGE)

    def test_aliases_resolve_to_one_mark(self):
        for left, right in (
            ("opencode", "open_code"),
            ("omp", "pi"),
            ("copilot", "github_copilot"),
            ("qwen", "qwen-code"),
            ("qodercli", "qoder"),
        ):
            with self.subTest(alias=f"{left}/{right}"):
                self.assertEqual(cobalt2_marks.MARKS[left], cobalt2_marks.MARKS[right])

    def test_text_fallbacks_are_short_ascii(self):
        """The text variant has to fit the sidebar without wide characters."""
        for agent, mark in cobalt2_marks.MARKS.items():
            with self.subTest(agent=agent):
                self.assertTrue(mark.text.isascii(), mark.text)
                self.assertLessEqual(len(mark.text), 3)

    def test_covers_every_agent_herdr_can_report(self):
        """A missing agent renders an empty logo column, which is the bug this fixes."""
        expected = {
            "agy", "amp", "claude", "cline", "codex", "cursor", "devin", "droid",
            "gemini", "github_copilot", "grok", "hermes", "kilo", "kimi", "kiro",
            "maki", "mastracode", "muse", "open_code", "pi", "qodercli", "qwen",
        }
        self.assertEqual(expected - set(cobalt2_marks.MARKS), set())

    def test_styling_rules_stay_inside_the_budget(self):
        """Herdr rejects config with more than MAX_STYLE_RULES rules on a token."""
        budget = cobalt2_marks.MAX_STYLE_RULES - cobalt2_marks.RULE_HEADROOM
        self.assertLessEqual(len(cobalt2_marks.rule_specs()), budget)

    def test_accent_colored_marks_cost_no_rule(self):
        """That omission is what keeps the rule count under the ceiling."""
        rule_codepoints = {codepoint for codepoint, _ in cobalt2_marks.rule_specs()}
        accent_only = {
            mark.codepoint
            for mark in cobalt2_marks.MARKS.values()
            if mark.color == cobalt2_marks.ACCENT
        }
        self.assertEqual(rule_codepoints & accent_only, set())


class SidebarBlockTest(unittest.TestCase):
    def setUp(self):
        self.apply = load_script("apply-cobalt2")

    def test_block_is_valid_toml(self):
        parsed = tomllib.loads(self.apply.render_sidebar_block())
        self.assertIn("rows", parsed["ui"]["sidebar"]["agents"])

    def test_logo_token_carries_every_rule(self):
        parsed = tomllib.loads(self.apply.render_sidebar_block())
        token = parsed["ui"]["sidebar"]["agents"]["rows"][0][1]
        self.assertEqual(token["token"], "$cobalt2_logo")
        self.assertEqual(token["fg"], cobalt2_marks.ACCENT)
        self.assertEqual(
            [(ord(rule["equals"]), rule["fg"]) for rule in token["rules"]],
            cobalt2_marks.rule_specs(),
        )

    def test_token_name_is_not_the_agent_icons_token(self):
        """Sharing $harness_logo would make the two plugins race, last write wins."""
        self.assertNotIn("$harness_logo", self.apply.render_sidebar_block())

    def test_state_icon_stays_first(self):
        """Herdr's own colored lifecycle icon must keep its column."""
        parsed = tomllib.loads(self.apply.render_sidebar_block())
        self.assertEqual(parsed["ui"]["sidebar"]["agents"]["rows"][0][0], "state_icon")

    def test_theme_block_is_valid_toml(self):
        parsed = tomllib.loads(self.apply.render_theme_block())
        self.assertEqual(parsed["theme"]["custom"]["accent"], cobalt2_marks.ACCENT)

    def test_sidebar_regex_replaces_nested_rows_by_agent(self):
        """The old layout put per-agent overrides in a nested section."""
        config = (
            '[ui]\nmouse = true\n\n'
            '[ui.sidebar.agents]\nrows = [["agent"]]\n\n'
            '[ui.sidebar.agents.rows_by_agent]\nclaude = [["agent"]]\n\n'
            '[[keys.command]]\nkey = "prefix+x"\n'
        )
        result = self.apply.update_section(
            config, self.apply.SIDEBAR_SECTION_RE, self.apply.render_sidebar_block()
        )
        self.assertNotIn("rows_by_agent", result)
        self.assertIn("[[keys.command]]", result)
        self.assertIn("mouse = true", result)
        tomllib.loads(result)

    def test_update_section_survives_unicode_escapes(self):
        """re.sub would read \\uE1A0 in the replacement as a template escape."""
        result = self.apply.update_section(
            "[ui.sidebar.agents]\nrows = [[\"agent\"]]\n",
            self.apply.SIDEBAR_SECTION_RE,
            self.apply.render_sidebar_block(),
        )
        self.assertIn("\\uE1A0", result)


class FakeHerdr:
    """A stand-in `herdr` on PATH that records the calls made to it."""

    def __init__(self, root: Path, panes: list[dict]):
        self.root = root
        self.log = root / "calls.jsonl"
        binary = root / "herdr"
        binary.write_text(
            "#!/usr/bin/env python3\n"
            "import json, sys, os\n"
            f"log = {str(self.log)!r}\n"
            f"panes = {json.dumps(panes)}\n"
            "with open(log, 'a') as handle:\n"
            "    handle.write(json.dumps(sys.argv[1:]) + '\\n')\n"
            "if sys.argv[1:3] == ['pane', 'list']:\n"
            "    print(json.dumps({'result': {'panes': panes}}))\n"
        )
        binary.chmod(0o755)

    def calls(self) -> list[list[str]]:
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines()]


class AgentMarksTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def run_marks(self, panes: list[dict], *args: str) -> tuple[subprocess.CompletedProcess, FakeHerdr]:
        fake = FakeHerdr(self.tmp, panes)
        env = {
            **os.environ,
            "PATH": f"{self.tmp}{os.pathsep}{os.environ['PATH']}",
            "HERDR_BIN_PATH": str(self.tmp / "herdr"),
        }
        env.pop("HERDR_PLUGIN_EVENT_JSON", None)
        env.pop("HERDR_PLUGIN_CONFIG_DIR", None)
        result = subprocess.run(
            [sys.executable, str(PLUGIN_ROOT / "bin" / "agent-marks"), *args],
            capture_output=True,
            text=True,
            env=env,
        )
        return result, fake

    def test_reports_a_mark_for_each_known_agent(self):
        panes = [
            {"pane_id": "w1:p1", "agent": "claude"},
            {"pane_id": "w1:p2", "agent": "grok"},
        ]
        result, fake = self.run_marks(panes)
        self.assertEqual(result.returncode, 0, result.stderr)
        tokens = {
            call[2]: call[-1]
            for call in fake.calls()
            if call[:2] == ["pane", "report-metadata"]
        }
        self.assertEqual(tokens["w1:p1"], f"cobalt2_logo={chr(0xE1A0)}")
        self.assertEqual(tokens["w1:p2"], f"cobalt2_logo={chr(0xF467)}")

    def test_clears_the_token_for_an_agent_with_no_mark(self):
        """A stale mark from a previous agent would otherwise stick around."""
        result, fake = self.run_marks([{"pane_id": "w1:p1", "agent": "aider"}])
        self.assertEqual(result.returncode, 0, result.stderr)
        call = fake.calls()[-1]
        self.assertIn("--clear-token", call)
        self.assertEqual(call[-1], "cobalt2_logo")

    def test_tolerates_a_pane_with_no_agent(self):
        """Indexing pane['agent'] here would raise KeyError on an idle pane."""
        result, fake = self.run_marks([{"pane_id": "w1:p1"}])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--clear-token", fake.calls()[-1])

    def test_never_touches_herdr_state_reporting(self):
        """Herdr owns the state icon and lifecycle labels; this only adds a token."""
        result, fake = self.run_marks([{"pane_id": "w1:p1", "agent": "claude"}])
        self.assertEqual(result.returncode, 0, result.stderr)
        flat = " ".join(" ".join(call) for call in fake.calls())
        for forbidden in ("report-agent", "--display-agent", "--state-label", "--title"):
            self.assertNotIn(forbidden, flat)

    def test_text_variant_reports_ascii(self):
        result, fake = self.run_marks(
            [{"pane_id": "w1:p1", "agent": "claude"}], "--variant", "text"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(fake.calls()[-1][-1], "cobalt2_logo=C")

    def test_none_variant_reports_no_mark(self):
        result, fake = self.run_marks(
            [{"pane_id": "w1:p1", "agent": "claude"}], "--variant", "none"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--clear-token", fake.calls()[-1])



class BundledFontTest(unittest.TestCase):
    def setUp(self):
        if importlib.util.find_spec("fontTools") is None:
            self.skipTest("fontTools is only required for font build checks")

    def test_font_contains_every_bundled_mark(self):
        from fontTools.ttLib import TTFont

        font = TTFont(PLUGIN_ROOT / "dist" / "HerdrHarnessLogos-Regular.ttf")
        self.assertEqual(
            set(cobalt2_marks.codepoints("harness")),
            set(font.getBestCmap()),
        )

    def test_source_build_is_byte_reproducible(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "rebuilt.ttf"
            result = subprocess.run(
                [
                    sys.executable,
                    str(PLUGIN_ROOT / "tools" / "build_logo_font.py"),
                    "--output",
                    str(output),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                output.read_bytes(),
                (PLUGIN_ROOT / "dist" / "HerdrHarnessLogos-Regular.ttf").read_bytes(),
            )

    def test_scaler_uses_bundled_font_without_plugin_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "scaled.ttf"
            env = {
                **os.environ,
                "HOME": str(root),
                "HERDR_PLUGIN_STATE_DIR": str(root / "state"),
            }
            result = subprocess.run(
                [
                    sys.executable,
                    str(PLUGIN_ROOT / "bin" / "scale-agent-fonts"),
                    "--terminal",
                    "ghostty",
                    "--primary",
                    str(PLUGIN_ROOT / "dist" / "HerdrHarnessLogos-Regular.ttf"),
                    "--out",
                    str(output),
                ],
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(output.is_file())


if __name__ == "__main__":
    unittest.main()
