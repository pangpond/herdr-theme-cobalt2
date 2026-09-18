# Cobalt2 Theme for Herdr

Apply [Wes Bos Cobalt2](https://github.com/wesbos/cobalt2-iterm) colors to Herdr's UI chrome (sidebar, panels, accents) through `[theme.custom]`, and give every agent row a harness mark sized to match the text beside it.

> **Credits:** Cobalt2 was created by [Wes Bos](https://wesbos.com/). This plugin adapts the palette from [`wesbos/cobalt2-iterm`](https://github.com/wesbos/cobalt2-iterm) for Herdr. Cobalt2 itself is not affiliated with Herdr.

## Install

Requires Herdr 0.9.0+, macOS or Linux, and Python 3.

1. Install and apply the plugin:

   ```bash
   herdr plugin install pangpond/herdr-theme-cobalt2
   herdr plugin action invoke apply --plugin herdr-theme-cobalt2
   ```

   You can reapply it later with `prefix+shift+c` inside Herdr.

2. Build and install the bundled logo font for the current terminal:

   ```bash
   herdr plugin action invoke scale-fonts --plugin herdr-theme-cobalt2
   ```

   Ghostty and iTerm2 install the pinned `fontTools` dependency into the
   plugin's state directory on first run. Foot needs no Python dependency.

3. Activate the generated font:

   - **Ghostty:** the action updates `~/.config/ghostty/config` automatically,
     preserving the primary family and adding the `Herdr Harness Logos`
     fallback plus its U+E1A0–U+E1A8 codepoint map. Before the first change it
     saves the original as `ghostty-config.backup` in the plugin state
     directory. Use `bin/scale-agent-fonts --terminal ghostty --no-configure`
     when only the font file should be generated.

   - **iTerm2:** the action builds `MesloLGS NF Herdr` from the four pristine
     MesloLGS NF faces in `~/Library/Fonts`; select that generated family in
     the profile.

   - **Foot:** the action installs `Herdr Harness Logos` under
     `~/.local/share/fonts` and refreshes fontconfig. Add it after the primary
     family in `~/.config/foot/foot.ini`, using the same size:

     ```ini
     [main]
     font=JetBrainsMono Nerd Font:size=11, Herdr Harness Logos:size=11
     ```

Restart the terminal after changing its font configuration.

## What it does

- Writes a Cobalt2 `[theme]` / `[theme.custom]` block into `~/.config/herdr/config.toml`
- Writes `[ui.sidebar.agents]` rows that show a per-harness mark, the pane title, and one detail row with the lifecycle state plus the [Agent Usage](https://github.com/moneycaringcoder/herdr-agent-usage) tokens when that plugin is installed
- Writes `[ui.sidebar.spaces]` rows that show a per-space icon you pick, the space name, and its branch
- Reports `$cobalt2_logo` for every pane and `$cobalt2_space` for every space
- Resolves a mark for harnesses the table has no entry for, on request, and caches the verdict
- Backs up your previous `[theme]`, `[ui.sidebar.agents]`, and `[ui.sidebar.spaces]` blocks before the first apply
- Validates the rendered config with `herdr config check` **before** writing, then reloads Herdr

It recolors **Herdr UI chrome** only. Terminal cell and ANSI colors still come from your terminal emulator. For the classic Cobalt2 terminal look, also install Wes Bos's iTerm preset from [`cobalt2-iterm`](https://github.com/wesbos/cobalt2-iterm).

## Agent marks

Herdr's own state icon keeps its column; the mark is added beside it, colored per harness.

Nine dedicated logos at U+E1A0–U+E1A8 ship directly with this plugin in
`dist/HerdrHarnessLogos-Regular.ttf`; their vector sources, deterministic
builder, and license notices are also kept in this repository. The remaining
marks are borrowed from your primary Nerd Font: an X for Grok, the real Copilot
glyph, a spark for Gemini, and so on. See `lib/cobalt2_marks.py` for the full
table.

This plugin owns and reports `$cobalt2_logo`; it does not require or read from
the `agent-icons` plugin.

To use ASCII marks instead of glyphs, or none at all, put this in the plugin's config directory (`~/.config/herdr/plugins/config/herdr-theme-cobalt2/config.toml`):

```toml
marks = "text"  # or "none"
```

## Unrecognized harnesses

`lib/cobalt2_marks.py` matches agent ids exactly, so a harness it has never
heard of renders an empty logo column. Herdr learns about new harnesses faster
than this table does, and its ids drift (`github_copilot` vs `copilot`,
`open_code` vs `opencode`).

`--resolve-unknown` closes that gap by asking [TypeSafe](https://typesafe.ai)
which existing mark an unknown id should use:

```bash
export TYPESAFE_API_KEY=...
python3 bin/agent-marks --resolve-unknown
```

One request per unknown id asks two questions at once: a Choice over every mark
in the table plus a generic bucket and a "not an agent" option, and a Noul for
whether the id names a coding agent at all. `claude-code` resolves to the
Claude mark, `gh-copilot` to the Copilot glyph, `aider` to the generic agent
mark at U+EB08, and `vim` to no mark.

Answers below 0.6 confidence are refused and not cached, so an uncertain id
keeps the empty column rather than being pinned to a guess. Verdicts land in
the plugin's own config:

```toml
[agent_marks]
aider = "generic"
fish = "none"        # asked about, needs no mark
```

Editing that table by hand works identically, and an entry always beats
inference. Everything after the first resolve is a local lookup: the startup
and `pane.agent_detected` hooks never import the resolver, never open a socket,
and keep working with no API key at all.

## Row padding

Sidebar entries are padded so the active-row highlight is not flush against
the text. Herdr has no padding setting, and it drops whitespace-only metadata,
so the padding is a row holding a braille blank (U+2800) that renders nothing.
A terminal grid has no fraction of a row, so padding comes in whole rows:

```toml
row_padding = 2          # both panels: 2 above and below, 1 below only, 0 none
row_padding_agents = 2   # optional per-panel override (default 2)
row_padding_spaces = 1   # optional per-panel override (default 1)
row_gap = 0              # blank rows *between* entries, outside the highlight
```

Each agent entry is two content rows — the mark headline plus one detail row
with the lifecycle state, usage, and context — so level 2 makes a padded entry
four terminal rows, the smallest balanced entry the grid allows. Space entries
carry the same two rows but read heavier, which is why they default to one
padding row.

`row_padding*` takes effect on the next mark report:

```bash
herdr plugin action invoke refresh-marks --plugin herdr-theme-cobalt2
herdr plugin action invoke refresh-space-icons --plugin herdr-theme-cobalt2
```

`row_gap` is written into `config.toml`, so it needs `apply`. Because padding
and gap are both whole rows, the only way to make every row shorter is the
terminal: Ghostty takes `adjust-cell-height = -20%` in
`~/.config/ghostty/config`, and iTerm2 has Profile > Text > Line Spacing.

## Space icons

Each space row can carry its own icon. Herdr has no icon picker, and workspace
metadata only lives in the running server, so this plugin owns the choice and
re-reports it on startup and on `workspace.created` / `workspace.renamed`.

Pick one with `prefix+shift+i`, or:

```bash
herdr plugin action invoke space-icons --plugin herdr-theme-cobalt2
```

That opens a popup listing 24 icons; typing any other character uses it
instead, and `0` clears the space's icon. The choice is keyed by space label,
matched case-insensitively, and stored in the plugin's own config directory:

```toml
[space_icons]
default = "🗂"
herdr = "🚀"
"ramen-pipeline" = "🍜"
```

Editing that table by hand works the same way; `default` covers spaces with no
entry of their own. The same mapping is scriptable:

```bash
python3 bin/space-marks --set "herdr=🚀" --unset old-space
python3 bin/space-marks --list
```

Emoji occupy two cells. A Nerd Font glyph stays one cell wide if you want the
labels to line up exactly.

### Detecting icons from projects

A project's real favicon cannot be shown: Herdr's sidebar renders text, and its
graphics APIs are pane-scoped. The closest identifier is the Nerd Font glyph
for the stack a space has checked out, which this guesses:

```bash
herdr plugin action invoke detect-space-icons --plugin herdr-theme-cobalt2
python3 bin/space-marks --detect          # same thing, prints what it found
python3 bin/space-marks --detect --force  # also replace icons already chosen
```

It reads manifests (`package.json`, `composer.json`, `Cargo.toml`, `go.mod`,
`pyproject.toml`, …) up to three directories deep and keeps the most specific
hit, so a monorepo whose root carries a toolchain manifest still reports the
framework its apps use. File extensions are the fallback, then Git, then a
plain folder. Detected icons are written into `[space_icons]` as ordinary
entries, so editing or picking over them works as before, and `--detect`
without `--force` never overwrites a choice you made.

The glyphs are Nerd Font devicons verified present in JetBrainsMono Nerd Font.
A terminal without a Nerd Font shows tofu; pick emoji with the picker instead.

## Sizing the marks

The bundled font uses 1000 units/em. Each terminal handles that source
differently:

- **Ghostty** constrains these codepoints with `.fit`, whose scale factor is
  `min(1, …)`. It only scales down, so the build grows the outlines to the
  renderer's ceiling.
- **iTerm2** has no per-codepoint fallback map. The marks are merged into its
  2048 units/em primary family and scaled between the two coordinate systems.
- **Foot** resolves an explicit fontconfig fallback at the configured point
  size, so it only needs the bundled font installed.

The `scale-fonts` action detects Ghostty and iTerm2 from `TERM_PROGRAM`, and
Foot from `TERM`. Run `bin/scale-agent-fonts` directly with `--terminal
ghostty`, `--terminal iterm2`, or `--terminal foot` to override detection.
Re-run it after changing your primary font.

Ghostty marks are grown to fill the two-cell box granted to a symbol followed
by a blank cell. The action updates its fallback and codepoint map idempotently;
pass `--width-cells` or `--height-fill` to resize, or `--no-configure` to leave
the Ghostty config untouched.

iTerm2's generated family also receives Nerd Font marks missing from the
pristine MesloLGS NF faces; the donor is resolved from the primary Nerd Font.
Pass `--cap-fill` or `--width-fill` to tune their size.

The Ghostty and iTerm2 build paths need `fontTools`, which the action installs into a venv under the plugin's state directory on first run.

To rebuild the pristine bundled font from its SVG sources:

```bash
python3 -m pip install -r requirements-font.txt
python3 tools/build_logo_font.py
```

The generated TTF is byte-reproducible. Third-party mark origins, modifications,
trademark caveats, and complete license texts are in
`assets/THIRD_PARTY_NOTICES.md` and `assets/licenses/`.

## Actions

```bash
# Apply Cobalt2 theme and sidebar rows
herdr plugin action invoke apply --plugin herdr-theme-cobalt2

# Restore the blocks backed up before the first apply
herdr plugin action invoke restore --plugin herdr-theme-cobalt2

# Re-report marks for current panes
herdr plugin action invoke refresh-marks --plugin herdr-theme-cobalt2

# Re-report space icons for current spaces
herdr plugin action invoke refresh-space-icons --plugin herdr-theme-cobalt2

# Pick a space icon in a popup
herdr plugin action invoke space-icons --plugin herdr-theme-cobalt2

# Rebuild the logo font for this terminal
herdr plugin action invoke scale-fonts --plugin herdr-theme-cobalt2
```

## Local development

```bash
git clone https://github.com/pangpond/herdr-theme-cobalt2.git
cd herdr-theme-cobalt2
herdr plugin link "$PWD"
herdr server reload-config
herdr plugin action invoke apply --plugin herdr-theme-cobalt2
```

Run the tests with the standard library only:

```bash
python3 -m unittest discover -s tests
```

## Uninstall

```bash
herdr plugin uninstall herdr-theme-cobalt2
```

Uninstall does not revert `config.toml`. Run `restore` first, or edit the blocks by hand. Fonts installed by `scale-fonts` are yours to delete from `~/Library/Fonts` (macOS) or `~/.local/share/fonts` (Linux).

## Requirements

- Herdr 0.9.0+ (agent row styling rules)
- macOS or Linux
- Python 3
- `fontTools` 4.65.0 only when rebuilding or resizing fonts; `scale-fonts` installs it into plugin state automatically

## License

MIT. Cobalt2 color scheme by Wes Bos — see [cobalt2-iterm](https://github.com/wesbos/cobalt2-iterm).
