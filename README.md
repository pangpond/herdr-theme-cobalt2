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

   - **Ghostty:** keep your primary family first, then add the fallback and
     codepoint map to `~/.config/ghostty/config`:

     ```conf
     font-family = "JetBrainsMono Nerd Font"
     font-family = "Herdr Harness Logos"
     font-codepoint-map = U+E1A0-U+E1A8="Herdr Harness Logos"
     ```

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
- Writes `[ui.sidebar.agents]` rows that show a per-harness mark, the pane title, and the [Agent Usage](https://github.com/moneycaringcoder/herdr-agent-usage) tokens when that plugin is installed
- Reports the `$cobalt2_logo` token for every pane, covering all 21 harnesses Herdr recognizes
- Backs up your previous `[theme]` and `[ui.sidebar.agents]` blocks before the first apply
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
by a blank cell. Pass `--width-cells` or `--height-fill` to make them smaller.

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
