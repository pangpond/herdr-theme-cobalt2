"""Tests for the Cobalt2 theme plugin.

Stdlib only, so this runs anywhere the plugin does:

    python3 -m unittest discover -s tests
"""

from __future__ import annotations

import http.server
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import tomllib
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "lib"))

import cobalt2_config  # noqa: E402
import cobalt2_marks  # noqa: E402
import cobalt2_resolve  # noqa: E402

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
        token = parsed["ui"]["sidebar"]["agents"]["rows"][1][1]
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
        self.assertEqual(parsed["ui"]["sidebar"]["agents"]["rows"][1][0], "state_icon")

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

    def test_spaces_block_renders_icon_and_branch_rows(self):
        parsed = tomllib.loads(self.apply.render_spaces_block())
        rows = parsed["ui"]["sidebar"]["spaces"]["rows"]
        self.assertEqual(rows[1][0]["token"], "$cobalt2_space")
        self.assertEqual(rows[1][1]["token"], "workspace")
        self.assertEqual([token["token"] for token in rows[2]], ["branch", "git_status"])

    def test_spaces_regex_replaces_only_its_own_section(self):
        config = (
            '[ui.sidebar.agents]\nrows = [["agent"]]\n\n'
            '[ui.sidebar.spaces]\nrows = [["workspace"]]\n\n'
            '[[keys.command]]\nkey = "prefix+x"\n'
        )
        result = self.apply.update_section(
            config, self.apply.SPACES_SECTION_RE, self.apply.render_spaces_block()
        )
        self.assertIn('rows = [["agent"]]', result)
        self.assertIn("$cobalt2_space", result)
        self.assertIn("[[keys.command]]", result)
        tomllib.loads(result)

    def test_agent_entry_is_two_content_rows_inside_padding(self):
        """Four terminal rows total: the smallest balanced entry the grid allows."""
        rows = tomllib.loads(self.apply.render_sidebar_block())["ui"]["sidebar"][
            "agents"
        ]["rows"]
        self.assertEqual(len(rows), 4)
        self.assertEqual(
            [token["token"] for token in rows[2]],
            ["state_text", "$limit", "$context"],
        )

    def test_blocks_wrap_entries_in_padding_rows(self):
        """Padding rows are what give the active-row highlight breathing room."""
        for block, section in (
            (self.apply.render_sidebar_block(), "agents"),
            (self.apply.render_spaces_block(), "spaces"),
        ):
            with self.subTest(section=section):
                rows = tomllib.loads(block)["ui"]["sidebar"][section]["rows"]
                self.assertEqual(
                    rows[0][0]["token"], f"${cobalt2_marks.PAD_TOKEN_ABOVE}"
                )
                self.assertEqual(
                    rows[-1][0]["token"], f"${cobalt2_marks.PAD_TOKEN_BELOW}"
                )


class RowPaddingTest(unittest.TestCase):
    """A padding row only renders when its token is reported, so the level is
    chosen by the reporters rather than by the config block."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.config = self.tmp / "config.toml"

    def test_defaults_to_symmetric_padding_when_unset(self):
        """Symmetric padding is the point; level 1 is an opt-in half height."""
        self.assertEqual(cobalt2_marks.DEFAULT_PAD_LEVEL, 2)
        self.assertEqual(cobalt2_marks.configured_padding(self.config), 2)
        self.config.write_text('marks = "font"\n')
        self.assertEqual(cobalt2_marks.configured_padding(self.config), 2)

    def test_reads_each_level(self):
        for level in cobalt2_marks.PAD_LEVELS:
            with self.subTest(level=level):
                self.config.write_text(f"row_padding = {level}\n")
                self.assertEqual(cobalt2_marks.configured_padding(self.config), level)

    def test_rejects_an_out_of_range_level(self):
        self.config.write_text("row_padding = 3\n")
        with self.assertRaises(ValueError):
            cobalt2_marks.configured_padding(self.config)

    def test_level_selects_which_tokens_are_reported(self):
        below = f"{cobalt2_marks.PAD_TOKEN_BELOW}={cobalt2_marks.PAD_GLYPH}"
        above = f"{cobalt2_marks.PAD_TOKEN_ABOVE}={cobalt2_marks.PAD_GLYPH}"
        self.assertEqual(
            cobalt2_marks.pad_token_args(0),
            [
                "--clear-token",
                cobalt2_marks.PAD_TOKEN_BELOW,
                "--clear-token",
                cobalt2_marks.PAD_TOKEN_ABOVE,
            ],
        )
        self.assertEqual(
            cobalt2_marks.pad_token_args(1),
            ["--token", below, "--clear-token", cobalt2_marks.PAD_TOKEN_ABOVE],
        )
        self.assertEqual(
            cobalt2_marks.pad_token_args(2), ["--token", below, "--token", above]
        )

    def test_pad_glyph_is_not_whitespace(self):
        """Herdr drops whitespace-only metadata, which is why this is U+2800."""
        self.assertFalse(cobalt2_marks.PAD_GLYPH.isspace())
        self.assertEqual(len(cobalt2_marks.PAD_GLYPH), 1)


class SpaceIconStoreTest(unittest.TestCase):
    """The user's own choices live in the plugin config directory."""

    def setUp(self):
        self.marks = load_script("space-marks")
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.config = self.tmp / "config.toml"

    def test_round_trips_labels_that_need_quoting(self):
        self.marks.save_icons({"default": "🗂", "ramen-pipeline": "🍜", "av japan": "🎮"}, self.config)
        tomllib.loads(self.config.read_text())
        self.assertEqual(
            self.marks.load_icons(self.config),
            {"default": "🗂", "ramen-pipeline": "🍜", "av japan": "🎮"},
        )

    def test_writing_icons_keeps_unrelated_config(self):
        """The same file holds the marks variant users may already have set."""
        self.config.write_text('marks = "text"\n')
        self.marks.save_icons({"herdr": "🚀"}, self.config)
        parsed = tomllib.loads(self.config.read_text())
        self.assertEqual(parsed["marks"], "text")
        self.assertEqual(parsed["space_icons"]["herdr"], "🚀")

    def test_rewriting_replaces_rather_than_appends(self):
        self.marks.save_icons({"herdr": "🚀"}, self.config)
        self.marks.save_icons({"herdr": "🎯"}, self.config)
        self.assertEqual(self.config.read_text().count("[space_icons]"), 1)
        self.assertEqual(self.marks.load_icons(self.config), {"herdr": "🎯"})

    def test_clearing_every_icon_drops_the_table(self):
        self.config.write_text('marks = "text"\n')
        self.marks.save_icons({"herdr": "🚀"}, self.config)
        self.marks.save_icons({}, self.config)
        self.assertNotIn("space_icons", self.config.read_text())
        self.assertEqual(tomllib.loads(self.config.read_text())["marks"], "text")

    def test_label_lookup_ignores_case_and_falls_back(self):
        icons = {"herdr": "🚀", "default": "🗂"}
        self.assertEqual(self.marks.icon_for("Herdr", icons), "🚀")
        self.assertEqual(self.marks.icon_for("unknown", icons), "🗂")
        self.assertIsNone(self.marks.icon_for("unknown", {"herdr": "🚀"}))


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
        # Point the plugin config at a scratch directory. Unsetting it would
        # fall back to ~/.config, making every assertion depend on whatever the
        # developer running the suite has configured.
        config_dir = self.tmp / "config"
        config_dir.mkdir(exist_ok=True)
        env = {
            **os.environ,
            "PATH": f"{self.tmp}{os.pathsep}{os.environ['PATH']}",
            "HERDR_BIN_PATH": str(self.tmp / "herdr"),
            "HERDR_PLUGIN_CONFIG_DIR": str(config_dir),
        }
        # Never let the suite reach TypeSafe: resolution is covered by
        # ResolveRequestTest against a local stub.
        env.pop("TYPESAFE_API_KEY", None)
        env.pop("HERDR_PLUGIN_EVENT_JSON", None)
        result = subprocess.run(
            [sys.executable, str(PLUGIN_ROOT / "bin" / "agent-marks"), *args],
            capture_output=True,
            text=True,
            env=env,
        )
        return result, fake

    @staticmethod
    def logo_arg(call: list[str]) -> str | None:
        """The $cobalt2_logo argument, ignoring the padding tokens beside it."""
        for index, item in enumerate(call):
            if item in ("--token", "--clear-token") and call[index + 1].startswith(
                "cobalt2_logo"
            ):
                return call[index + 1] if item == "--token" else "cleared"
        return None

    def test_reports_a_mark_for_each_known_agent(self):
        panes = [
            {"pane_id": "w1:p1", "agent": "claude"},
            {"pane_id": "w1:p2", "agent": "grok"},
        ]
        result, fake = self.run_marks(panes)
        self.assertEqual(result.returncode, 0, result.stderr)
        tokens = {
            call[2]: self.logo_arg(call)
            for call in fake.calls()
            if call[:2] == ["pane", "report-metadata"]
        }
        self.assertEqual(tokens["w1:p1"], f"cobalt2_logo={chr(0xE1A0)}")
        self.assertEqual(tokens["w1:p2"], f"cobalt2_logo={chr(0xF467)}")

    def test_clears_the_token_for_an_agent_with_no_mark(self):
        """A stale mark from a previous agent would otherwise stick around."""
        result, fake = self.run_marks([{"pane_id": "w1:p1", "agent": "aider"}])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.logo_arg(fake.calls()[-1]), "cleared")

    def test_tolerates_a_pane_with_no_agent(self):
        """Indexing pane['agent'] here would raise KeyError on an idle pane."""
        result, fake = self.run_marks([{"pane_id": "w1:p1"}])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.logo_arg(fake.calls()[-1]), "cleared")

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
        self.assertEqual(self.logo_arg(fake.calls()[-1]), "cobalt2_logo=C")

    def test_none_variant_reports_no_mark(self):
        result, fake = self.run_marks(
            [{"pane_id": "w1:p1", "agent": "claude"}], "--variant", "none"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.logo_arg(fake.calls()[-1]), "cleared")

    def test_reports_the_padding_token_beside_the_mark(self):
        """The padding row only renders when this token is reported."""
        result, fake = self.run_marks([{"pane_id": "w1:p1", "agent": "claude"}])
        self.assertEqual(result.returncode, 0, result.stderr)
        call = fake.calls()[-1]
        self.assertIn(
            f"{cobalt2_marks.PAD_TOKEN_BELOW}={cobalt2_marks.PAD_GLYPH}", call
        )

    def test_a_cached_verdict_paints_without_network_or_api_key(self):
        """Resolution happens once; the hooks must stay offline forever after."""
        config = self.tmp / "config"
        config.mkdir(exist_ok=True)
        (config / "config.toml").write_text(
            f"[{cobalt2_config.AGENT_MARKS_SECTION}]\n"
            f'aider = "{cobalt2_marks.GENERIC}"\n'
        )
        result, fake = self.run_marks([{"pane_id": "w1:p1", "agent": "aider"}])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.logo_arg(fake.calls()[-1]),
            f"cobalt2_logo={cobalt2_marks.glyph(cobalt2_marks.GENERIC)}",
        )

    def test_a_cached_no_mark_leaves_the_column_empty(self):
        """`none` records that the id was asked about and needs no mark."""
        config = self.tmp / "config"
        config.mkdir(exist_ok=True)
        (config / "config.toml").write_text(
            f"[{cobalt2_config.AGENT_MARKS_SECTION}]\n"
            f'fish = "{cobalt2_config.NO_MARK}"\n'
        )
        result, fake = self.run_marks([{"pane_id": "w1:p1", "agent": "fish"}])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.logo_arg(fake.calls()[-1]), "cleared")


class ResolvePolicyTest(unittest.TestCase):
    """The risk policy applied to a raw TypeSafe answer, no network involved."""

    def test_brands_describe_every_mark(self):
        """An undescribed mark can never be chosen, so it must not exist."""
        described = {
            cobalt2_marks.MARKS[key].codepoint
            for key in set(cobalt2_resolve.BRANDS) | {cobalt2_marks.GENERIC}
        }
        self.assertEqual(set(cobalt2_marks.codepoints()) - described, set())

    def test_confidence_and_agency_gate_the_answer(self):
        cases = (
            ("a confident brand match is used", "claude", 0.99, 0.90, "claude"),
            ("the same match below the floor is refused", "claude", 0.40, 0.90, None),
            ("a non-agent gets no mark", cobalt2_resolve.NOT_AN_AGENT, 0.95, 0.20, None),
            ("an unrecognized agent gets the generic mark", "generic", 0.90, 0.96, "generic"),
            ("generic needs the id to be an agent", "generic", 0.90, 0.30, None),
            ("an option outside the table is refused", "made_up", 0.99, 0.90, None),
        )
        for name, choice, confidence, is_agent, expected in cases:
            with self.subTest(name):
                self.assertEqual(
                    cobalt2_resolve._mark_for(choice, confidence, is_agent), expected
                )

    def test_a_non_agent_is_cached_so_it_is_asked_about_once(self):
        verdict = cobalt2_resolve.Verdict(
            mark=None, choice=cobalt2_resolve.NOT_AN_AGENT, confidence=0.95, is_agent=0.1
        )
        self.assertEqual(verdict.cacheable, cobalt2_config.NO_MARK)

    def test_an_uncertain_answer_is_not_cached(self):
        """Pinning a guess would stop a better answer from ever being asked for."""
        verdict = cobalt2_resolve.Verdict(
            mark=None, choice="claude", confidence=0.31, is_agent=0.9
        )
        self.assertIsNone(verdict.cacheable)


class ResolveRequestTest(unittest.TestCase):
    """The HTTP contract, served by a stub so the suite never leaves the host."""

    def serve(self, status: int, body: dict | str):
        received: dict = {}

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("Content-Length", 0))
                received["body"] = json.loads(self.rfile.read(length))
                received["auth"] = self.headers.get("Authorization")
                payload = json.dumps(body) if isinstance(body, dict) else body
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(payload.encode())

            def log_message(self, *_):
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        # LIFO, so shutdown runs before the socket is closed.
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        host, port = server.server_address[:2]
        return received, {
            "TYPESAFE_API_KEY": "test-key",
            "TYPESAFE_ENDPOINT": f"http://{host}:{port}/v1/systemone",
        }

    def test_sends_the_agent_id_as_state_and_parses_the_answer(self):
        received, env = self.serve(
            200,
            {
                "model": "jev-latest",
                "answers": {
                    "mark": {
                        "type": "choice",
                        "choice": "copilot",
                        "probabilities": {"copilot": 0.97},
                        "confidence": 0.97,
                    },
                    "is_coding_agent": {"type": "noul", "noul": 0.93},
                },
            },
        )
        verdict = cobalt2_resolve.resolve("gh-copilot", env=env)
        self.assertEqual(verdict.mark, "copilot")
        self.assertEqual(received["auth"], "Bearer test-key")
        self.assertEqual(received["body"]["state"], {"agent": {"id": "gh-copilot"}})
        self.assertIn("mark", received["body"]["questions"])

    def test_an_http_failure_is_recoverable(self):
        _, env = self.serve(429, {"error": "slow down"})
        with self.assertRaises(cobalt2_resolve.ResolveError):
            cobalt2_resolve.resolve("aider", env=env)

    def test_malformed_json_is_recoverable(self):
        _, env = self.serve(200, "not json at all")
        with self.assertRaises(cobalt2_resolve.ResolveError):
            cobalt2_resolve.resolve("aider", env=env)

    def test_a_missing_api_key_is_reported_not_raised_as_a_keyerror(self):
        with self.assertRaises(cobalt2_resolve.ResolveError):
            cobalt2_resolve.resolve("aider", env={})


class GhosttyConfigTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.scaler = load_script("scale-agent-fonts")
        self.config = self.tmp / "ghostty" / "config"
        self.backup = self.tmp / "state" / "ghostty-config.backup"

    def test_configuration_is_idempotent_and_preserves_one_backup(self):
        original = (
            'font-family = "JetBrainsMono Nerd Font"\n'
            'font-family = "Herdr Harness Logos"\n'
            'font-family = "Herdr Harness Logos"\n'
            'font-codepoint-map = U+E1A0-U+E1A8="Wrong Family"\n'
            "background = #173448\n"
        )
        self.config.parent.mkdir(parents=True)
        self.config.write_text(original)

        self.scaler.configure_ghostty(
            "JetBrainsMono Nerd Font", self.config, self.backup
        )
        configured = self.config.read_text()
        self.assertEqual(
            configured.count('font-family = "Herdr Harness Logos"'), 1
        )
        self.assertEqual(
            configured.count(
                'font-codepoint-map = U+E1A0-U+E1A8="Herdr Harness Logos"'
            ),
            1,
        )
        self.assertIn("background = #173448", configured)
        self.assertEqual(self.backup.read_text(), original)

        self.scaler.configure_ghostty(
            "JetBrainsMono Nerd Font", self.config, self.backup
        )
        self.assertEqual(self.config.read_text(), configured)
        self.assertEqual(self.backup.read_text(), original)

    def test_missing_config_gets_primary_and_fallback(self):
        self.scaler.configure_ghostty("Iosevka", self.config, self.backup)
        configured = self.config.read_text()
        self.assertIn('font-family = "Iosevka"', configured)
        self.assertIn('font-family = "Herdr Harness Logos"', configured)
        self.assertFalse(self.backup.exists())


class FootFontTest(unittest.TestCase):
    def test_auto_detects_foot_and_installs_bundled_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "HerdrHarnessLogos-Regular.ttf"
            env = {
                **os.environ,
                "HOME": str(root),
                "HERDR_PLUGIN_STATE_DIR": str(root / "state"),
                "TERM": "foot",
                "TERM_PROGRAM": "",
            }
            result = subprocess.run(
                [
                    sys.executable,
                    str(PLUGIN_ROOT / "bin" / "scale-agent-fonts"),
                    "--out",
                    str(output),
                ],
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                output.read_bytes(),
                (PLUGIN_ROOT / "dist" / "HerdrHarnessLogos-Regular.ttf").read_bytes(),
            )
            self.assertIn("foot.ini", result.stdout)
            self.assertFalse((root / "state").exists())


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

    def test_ghostty_scaler_configures_default_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "config" / "ghostty" / "config"
            original = 'font-family = "Test Primary"\nbackground = #173448\n'
            config.parent.mkdir(parents=True)
            config.write_text(original)
            env = {
                **os.environ,
                "HOME": str(root),
                "XDG_CONFIG_HOME": str(root / "config"),
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
                ],
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            configured = config.read_text()
            self.assertIn('font-family = "Herdr Harness Logos"', configured)
            self.assertIn("font-codepoint-map = U+E1A0-U+E1A8", configured)
            self.assertEqual(
                (root / "state" / "ghostty-config.backup").read_text(),
                original,
            )



if __name__ == "__main__":
    unittest.main()
