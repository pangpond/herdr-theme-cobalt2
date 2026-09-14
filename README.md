# Cobalt2 Theme for Herdr

Apply [Wes Bos Cobalt2](https://github.com/wesbos/cobalt2-iterm) colors to Herdr's UI chrome (sidebar, panels, accents) through `[theme.custom]`.

> **Credits:** Cobalt2 was created by [Wes Bos](https://wesbos.com/). This plugin adapts the palette from [`wesbos/cobalt2-iterm`](https://github.com/wesbos/cobalt2-iterm) for Herdr. Cobalt2 itself is not affiliated with Herdr.

## Install

```bash
herdr plugin install pangpond/herdr-theme-cobalt2
```

Then apply:

```bash
herdr plugin action invoke apply --plugin herdr-theme-cobalt2
```

Or press `prefix+shift+c` inside Herdr.

## What it does

- Writes a Cobalt2 `[theme]` / `[theme.custom]` block into `~/.config/herdr/config.toml`
- Backs up your previous theme block first (for restore)
- Runs `herdr config check`, then `herdr server reload-config`

It recolors **Herdr UI chrome** only. Terminal cell / ANSI colors still come from your terminal emulator (iTerm2, Ghostty, etc.). For the classic Cobalt2 terminal look, also install Wes Bos's iTerm preset from [`cobalt2-iterm`](https://github.com/wesbos/cobalt2-iterm).

## Actions

```bash
# Apply Cobalt2
herdr plugin action invoke apply --plugin herdr-theme-cobalt2

# Restore the theme backed up before the last apply
herdr plugin action invoke restore --plugin herdr-theme-cobalt2
```

## Local development

```bash
git clone https://github.com/pangpond/herdr-theme-cobalt2.git
cd herdr-theme-cobalt2
herdr plugin link "$PWD"
herdr server reload-config
herdr plugin action invoke apply --plugin herdr-theme-cobalt2
```

## Uninstall

```bash
herdr plugin uninstall herdr-theme-cobalt2
```

Uninstall does not remove `[theme.custom]` from `config.toml`. Use `restore` first, or edit the theme block by hand.

## Requirements

- Herdr 0.8.0+
- macOS or Linux
- Python 3

## License

MIT. Cobalt2 color scheme by Wes Bos — see [cobalt2-iterm](https://github.com/wesbos/cobalt2-iterm).
