# Clawdmeter

A floating desktop widget for Ubuntu that shows your Claude Code usage at a glance — active sessions, context window %, current project, and weekly token spend.

Clawdmeter reads everything locally from `~/.claude/` — no BLE, no extra daemon, no hardware required.

## Install

```bash
git clone https://github.com/xmedgcop/Clawdmeter.git
cd Clawdmeter
./desktop/install.sh
```

The installer will:
- Install system dependencies (`python3-gi`, `gir1.2-gtk-4.0`, `gtk4-layer-shell` if available)
- Create an isolated Python venv at `~/.local/share/clawdmeter/venv`
- Register the app launcher (searchable as "Clawdmeter" in your apps)
- Set it to start automatically on login
- Offer to launch it immediately

## What it shows

| Field | Source |
|---|---|
| Sessions | `~/.claude/sessions/*.json` (live PIDs) + sub-agents |
| Context % | Last assistant message usage in the active session JSONL |
| Project / branch | Current working directory and git branch from the JSONL |
| Weekly usage | Anthropic API (polled every 60 s) |
| Account | Auto-detected from `~/.claude/.credentials.json` |

## Requirements

- Ubuntu 22.04 or later (24.04+ recommended)
- Python 3.10+
- Claude Code installed and logged in (`~/.claude/.credentials.json` must exist)

## Uninstall

```bash
./desktop/uninstall.sh
```

This removes the venv, launcher, autostart entry, and icon. Your Claude config is untouched.

## Troubleshooting

**Widget doesn't stay on top**
- Wayland session: requires `gir1.2-gtk4layershell-1.0` (installed automatically on Ubuntu 24+)
- X11 session: requires `xdotool` (installed automatically by the installer)
- Re-run `./desktop/install.sh` to ensure dependencies are present

**"No module named gi" on launch**
- Always launch via the venv: `~/.local/share/clawdmeter/venv/bin/python desktop/clawdmeter_desktop.py`
- Or re-run `./desktop/install.sh` to rebuild the venv

**Session count is 0 while Claude Code is running**
- Check that `~/.claude/sessions/` contains `.json` files while Claude Code is active
- The widget refreshes every 5 seconds

## Licensing note

This project uses Anthropic brand assets (Clawd sprites via [claudepix.vercel.app](https://claudepix.vercel.app)) and fonts. The code is source-available but not open-licensed due to these third-party assets.
