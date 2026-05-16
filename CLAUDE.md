# Project context

Clawdmeter Desktop — a floating GTK4 widget for Ubuntu that shows Claude Code usage in real time. No hardware involved. Users do `git clone` + `./desktop/install.sh` and it works.

## Repo structure

```
desktop/
  clawdmeter_desktop.py   — the widget (GTK4, PyGObject)
  install.sh              — venv setup + autostart registration
  uninstall.sh            — cleanup
assets/
  Claude Code Logo.png    — app icon (128×128)
install.sh                — thin wrapper, calls desktop/install.sh
```

## Install / launch

```bash
./desktop/install.sh          # installs deps, creates venv, registers autostart
./desktop/uninstall.sh        # removes everything

# Manual launch (without reinstalling):
~/.local/share/clawdmeter/venv/bin/python desktop/clawdmeter_desktop.py
```

## Architecture

Single file: `desktop/clawdmeter_desktop.py`

- **GTK4 via PyGObject** — venv with `--system-site-packages` inherits system `python3-gi`; no pip-compiling PyGObject
- **Session detection** — reads `~/.claude/sessions/*.json` (main sessions, PID-verified) + `~/.claude/projects/<uuid>/subagents/agent-*.jsonl` (sub-agents: active if modified <90 s ago and last line ≠ `stop_reason: end_turn`)
- **Context %** — scans the active session's JSONL for the last assistant message with usage; formula: `(input_tokens + cache_read_input_tokens + cache_creation_input_tokens) / context_window * 100` — matches Claude Code's own display
- **Email auto-detect** — reads `~/.claude/.credentials.json` → Bearer token → GET `https://api.anthropic.com/api/oauth/claude_cli/roles` → parses `"organization_name": "email@domain's Organization"`
- **Animations** — pixel-art frames loaded from `tools/claudepix_data/*.json` (13 creatures, 20×20, 10-color palette)
- **Polling** — local data (sessions, context) every 5 s; Anthropic API usage every 60 s

## Always-on-top — critical gotchas

### Wayland (default Ubuntu 24+)
Uses `gtk4-layer-shell` (`gir1.2-gtk4layershell-1.0`). **Must call `init_for_window()` in `__init__` before `present()`** — calling it in the `realize` callback is too late and silently no-ops.

Use **`TOP` layer, not `OVERLAY`**. GNOME silently rejects OVERLAY for non-compositor apps.

```python
Gtk4LayerShell.init_for_window(self)
Gtk4LayerShell.set_layer(self, Gtk4LayerShell.Layer.TOP)
Gtk4LayerShell.set_exclusive_zone(self, -1)
Gtk4LayerShell.set_keyboard_mode(self, Gtk4LayerShell.KeyboardMode.NONE)
```

Gate on session type first — `init_for_window()` silently no-ops on X11 sessions even if the library is importable:
```python
on_wayland = bool(os.environ.get("WAYLAND_DISPLAY") or os.environ.get("XDG_SESSION_TYPE") == "wayland")
```

### X11
After realize + 800 ms delay, run `xdotool search --sync --name Clawdmeter windowstate --add ABOVE`. Always install xdotool as backup even on Wayland systems.

## install.sh key decisions

- **`--system-site-packages` venv** — inherits `python3-gi` from apt; avoids pip-compiling PyGObject (which fails due to `girepository-2.0` detection issues in both Ubuntu 24 and 26)
- **`--without-pip` + `get-pip.py` bootstrap** — avoids `python3.X-venv` apt 404s on Ubuntu 26
- **No compilation deps** — `libgirepository-dev`, `libcairo2-dev`, etc. not needed
- **Always install `xdotool wmctrl`** — needed as X11 fallback regardless of layer shell presence

## User profile / preferences

See `~/.claude/projects/.../memory/` for persistent context. User is a senior dev (not embedded-specialist), prefers iterative UI refinement, dislikes hand-authored art (use third-party assets). Terse communication preferred.
