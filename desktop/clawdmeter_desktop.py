#!/usr/bin/env python3
"""
Clawdmeter Desktop Widget — GTK4
Ubuntu floating widget for the Claude Code usage monitor.

Usage:  python3 clawdmeter_desktop.py
Deps:   python3-gi  python3-gi-cairo  (sudo apt install python3-gi-cairo)
"""

import math
import os

# Probe for gtk4-layer-shell BEFORE locking the GDK backend.
# Layer shell is the only reliable always-on-top mechanism on GNOME Wayland —
# _NET_WM_STATE_ABOVE via XWayland is intentionally ignored by the compositor.
def _layer_shell_available():
    try:
        import gi as _gi
        _gi.require_version("Gtk4LayerShell", "1.0")
        from gi.repository import Gtk4LayerShell  # noqa: F401
        return True
    except Exception:
        return False

_HAVE_LAYER_SHELL = _layer_shell_available()
if not _HAVE_LAYER_SHELL:
    os.environ.setdefault("GDK_BACKEND", "x11")  # XWayland fallback

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, Gdk, GLib, Pango

import threading
import json
import re
import subprocess
import time
import random
import queue
import shutil
from pathlib import Path

ASSETS_DIR = Path(__file__).parent.parent / "assets"
ICON_NAME  = "com.clawdmeter"

def _install_icon():
    src = ASSETS_DIR / "Claude Code Logo.png"
    dst = Path.home() / ".local/share/icons/hicolor/128x128/apps" / f"{ICON_NAME}.png"
    if not dst.exists() and src.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, dst)
        subprocess.run(
            ["gtk-update-icon-cache", "-f", "-t",
             str(Path.home() / ".local/share/icons/hicolor")],
            check=False, capture_output=True,
        )

_install_icon()

# ── Paths ─────────────────────────────────────────────────────────────────────
ANIM_DIR = Path(__file__).parent.parent / "tools" / "claudepix_data"

# ── Ubuntu Yaru-dark palette ──────────────────────────────────────────────────
BG        = "transparent"
CONTAINER = "rgba(22, 20, 26, 0.70)"   # dark, very transparent — shows desktop
TITLEBAR  = "rgba(38, 34, 46, 0.97)"   # nearly solid — readable
PANEL_C   = "rgba(32, 28, 40, 0.88)"   # semi-opaque inner panel
TEXT_C    = "#f2f2f2"                   # Ubuntu soft white
DIM_C     = "#a09aaa"                   # grey-lavender dim text
ACCENT_C  = "#E95420"                   # Ubuntu orange — spinner/accent
GREEN_C   = "#26a269"                   # Yaru green — low usage
AMBER_C   = "#e5a50a"                   # Yaru amber — mid usage
RED_C     = "#c01c28"                   # Yaru red — high usage
BAR_BG_C  = "#1a1520"                   # bar track
BORDER_C  = "rgba(255, 255, 255, 0.08)" # subtle near-invisible border

# ── Spinner ───────────────────────────────────────────────────────────────────
SPINNER_FRAMES = ["·", "✻", "✽", "✶", "✳", "✢"]
SPINNER_MS     = [260, 130, 130, 130, 130, 260]
MESSAGES = [
    "Accomplishing", "Elucidating", "Perusing", "Actioning", "Enchanting",
    "Philosophising", "Actualizing", "Envisioning", "Pondering", "Baking",
    "Finagling", "Pontificating", "Booping", "Flibbertigibbeting", "Processing",
    "Brewing", "Forging", "Puttering", "Calculating", "Forming", "Puzzling",
    "Cerebrating", "Frolicking", "Reticulating", "Channelling", "Generating",
    "Ruminating", "Churning", "Germinating", "Scheming", "Clauding", "Hatching",
    "Schlepping", "Coalescing", "Herding", "Shimmying", "Cogitating", "Honking",
    "Shucking", "Combobulating", "Hustling", "Simmering", "Computing", "Ideating",
    "Smooshing", "Concocting", "Imagining", "Spelunking", "Conjuring", "Incubating",
    "Spinning", "Considering", "Inferring", "Stewing", "Contemplating", "Jiving",
    "Sussing", "Cooking", "Manifesting", "Synthesizing", "Crafting", "Marinating",
    "Thinking", "Creating", "Meandering", "Tinkering", "Crunching", "Moseying",
    "Transmuting", "Deciphering", "Mulling", "Unfurling", "Deliberating",
    "Mustering", "Unravelling", "Determining", "Musing", "Vibing",
    "Discombobulating", "Noodling", "Wandering", "Divining", "Percolating",
    "Whirring", "Doing", "Wibbling", "Effecting", "Wizarding", "Working", "Wrangling",
]

PIXEL_SCALE = 8   # 20×20 → 160×160


# ── Data fetching ─────────────────────────────────────────────────────────────

def read_token():
    creds = Path.home() / ".claude" / ".credentials.json"
    try:
        m = re.search(r'"accessToken":"([^"]+)"', creds.read_text())
        return m.group(1) if m else None
    except Exception:
        return None


def read_account_info():
    """Auto-detect email from Anthropic OAuth API; fallback to config file."""
    try:
        creds_path = Path.home() / ".claude" / ".credentials.json"
        token = json.loads(creds_path.read_text())["claudeAiOauth"]["accessToken"]
        result = subprocess.run(
            ["curl", "-s",
             "-H", f"Authorization: Bearer {token}",
             "-H", "anthropic-version: 2023-06-01",
             "https://api.anthropic.com/api/oauth/claude_cli/roles"],
            capture_output=True, text=True, timeout=5,
        )
        org = json.loads(result.stdout).get("organization_name", "")
        m = re.match(r"^(.+?)'s Organization$", org)
        if m:
            return m.group(1)
        if org:
            return org
    except Exception:
        pass
    # Fallback: manual config override
    try:
        cfg = json.loads((Path.home() / ".config" / "clawdmeter" / "config.json").read_text())
        email = cfg.get("email", "")
        if email:
            return email
    except Exception:
        pass
    try:
        d = json.loads((Path.home() / ".claude" / ".credentials.json").read_text())
        sub = d.get("claudeAiOauth", {}).get("subscriptionType", "")
        if sub:
            return f"claude {sub}"
    except Exception:
        pass
    return ""


def poll_api():
    token = read_token()
    if not token:
        return {"ok": False, "error": "no token"}
    try:
        result = subprocess.run(
            ["curl", "-s", "-D", "-", "-o", "/dev/null",
             "https://api.anthropic.com/v1/messages",
             "-H", f"Authorization: Bearer {token}",
             "-H", "anthropic-version: 2023-06-01",
             "-H", "anthropic-beta: oauth-2025-04-20",
             "-H", "Content-Type: application/json",
             "-H", "User-Agent: claude-code/2.1.5",
             "-d", '{"model":"claude-haiku-4-5-20251001","max_tokens":1,'
                   '"messages":[{"role":"user","content":"hi"}]}'],
            capture_output=True, text=True, timeout=30,
        )
        hdrs = result.stdout

        def hdr(name):
            m = re.search(rf"{re.escape(name)}:\s*(\S+)", hdrs, re.IGNORECASE)
            return m.group(1) if m else None

        s5h_util  = float(hdr("anthropic-ratelimit-unified-5h-utilization") or 0)
        s5h_reset = int(hdr("anthropic-ratelimit-unified-5h-reset") or 0)
        s7d_util  = float(hdr("anthropic-ratelimit-unified-7d-utilization") or 0)
        s7d_reset = int(hdr("anthropic-ratelimit-unified-7d-reset") or 0)
        status    = hdr("anthropic-ratelimit-unified-5h-status") or "unknown"
        now = int(time.time())

        return {
            "s":  round(s5h_util * 100),
            "sr": max(0, (s5h_reset - now) // 60),
            "w":  round(s7d_util * 100),
            "wr": max(0, (s7d_reset - now) // 60),
            "st": status,
            "ok": True,
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "API timeout"}
    except Exception:
        return {"ok": False, "error": "poll failed"}


def poll_sessions():
    """Reads ~/.claude/sessions/*.json and returns active sessions."""
    sessions_dir = Path.home() / ".claude" / "sessions"
    active = []
    try:
        for f in sessions_dir.glob("*.json"):
            try:
                d = json.loads(f.read_text())
                # Verificar que el proceso sigue vivo
                pid = d.get("pid")
                if pid and Path(f"/proc/{pid}").exists():
                    active.append({
                        "pid":    pid,
                        "status": d.get("status", "?"),
                        "cwd":    Path(d.get("cwd", "?")).name,
                    })
            except Exception:
                pass
    except Exception:
        pass
    return active


def _active_session_uuids():
    """Return sessionIds of sessions whose process is still alive."""
    sessions_dir = Path.home() / ".claude" / "sessions"
    uuids = []
    try:
        for f in sessions_dir.glob("*.json"):
            try:
                d = json.loads(f.read_text())
                pid = d.get("pid")
                sid = d.get("sessionId", "")
                if pid and sid and Path(f"/proc/{pid}").exists():
                    uuids.append(sid)
            except Exception:
                pass
    except Exception:
        pass
    return uuids


def poll_local_data():
    """Single pass — returns (ctx_dict, proj_dict) for the current active session."""
    projects_dir = Path.home() / ".claude" / "projects"
    CTX_WINDOW = 200_000

    # Prefer the JSONL that belongs to an active session (live PID)
    target = None
    for uuid in _active_session_uuids():
        matches = list(projects_dir.rglob(f"{uuid}.jsonl"))
        if matches:
            target = max(matches, key=lambda f: f.stat().st_mtime)
            break

    # Fall back to most recently modified JSONL if no active session found
    if target is None:
        try:
            all_files = sorted(
                projects_dir.rglob("*.jsonl"),
                key=lambda f: f.stat().st_mtime,
                reverse=True,
            )
            if all_files:
                target = all_files[0]
        except Exception:
            return None, None

    if target is None:
        return None, None

    try:
        lines = target.read_text().strip().splitlines()
    except OSError:
        return None, None

    try:
        input_tokens = cache_read = cache_create = output_tokens = 0
        model = project_name = git_branch = ""

        for line in reversed(lines):
            try:
                msg = json.loads(line)
                if not model:
                    m = msg.get("message", {})
                    if m.get("role") == "assistant" and m.get("usage"):
                        u = m["usage"]
                        input_tokens  = u.get("input_tokens", 0)
                        cache_read    = u.get("cache_read_input_tokens", 0)
                        cache_create  = u.get("cache_creation_input_tokens", 0)
                        output_tokens = u.get("output_tokens", 0)
                        model         = m.get("model", "")
                if not project_name:
                    cwd = msg.get("cwd", "")
                    if cwd:
                        project_name = Path(cwd).name
                if not git_branch:
                    git_branch = msg.get("gitBranch", "")
                if model and project_name and git_branch:
                    break
            except Exception:
                pass

        ctx_used = input_tokens + cache_read + cache_create
        pct = round(ctx_used / CTX_WINDOW * 100) if CTX_WINDOW else 0

        ctx = {
            "ctx_used":   ctx_used,
            "ctx_window": CTX_WINDOW,
            "ctx_pct":    min(pct, 100),
            "output":     output_tokens,
            "model":      _short_model(model),
        }
        proj = {"project": project_name, "branch": git_branch}
        return ctx, proj
    except Exception:
        return None, None


def _short_model(model: str) -> str:
    if "opus" in model:   return "Opus"
    if "sonnet" in model: return "Sonnet"
    if "haiku" in model:  return "Haiku"
    return model.split("-")[0].capitalize() if model else "?"


def load_animations():
    index_path = ANIM_DIR / "_index.json"
    if not index_path.exists():
        return []
    anims = []
    try:
        entries = json.loads(index_path.read_text())
    except Exception:
        return []
    for entry in entries:
        path = ANIM_DIR / entry["filename"].replace(".html", ".json")
        if path.exists():
            try:
                anims.append(json.loads(path.read_text()))
            except Exception:
                pass  # skip malformed animation files
    return anims


def format_reset(mins):
    if mins < 0:    return "---"
    if mins < 60:   return f"{mins}m"
    if mins < 1440:
        h, m = divmod(mins, 60)
        return f"{h}h {m}m"
    d, rem = divmod(mins, 1440)
    return f"{d}d {rem // 60}h"


def pct_color(pct):
    return RED_C if pct >= 80 else (AMBER_C if pct >= 50 else GREEN_C)


def hex_to_rgba(hex_color):
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = h[0]*2 + h[1]*2 + h[2]*2   # expand #rgb → #rrggbb
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return r / 255, g / 255, b / 255, 1.0


# ── GTK4 Window ───────────────────────────────────────────────────────────────

class ClawdmeterWindow(Gtk.ApplicationWindow):

    def __init__(self, app):
        super().__init__(application=app, title="Clawdmeter")
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_icon_name(ICON_NAME)

        # Layer shell must be initialised BEFORE the window is realized/shown.
        # Connecting to "realize" is too late — init_for_window() would no-op.
        if _HAVE_LAYER_SHELL:
            self._init_layer_shell()
        else:
            self.connect("realize", lambda *_: GLib.timeout_add(800, self._apply_keep_above_x11))

        self.animations  = load_animations()
        self._anim_idx   = 0
        self._frame_idx  = 0
        self._spin_phase = 0
        self._msg_idx    = random.randrange(max(1, len(MESSAGES)))
        self._poll_q     = queue.Queue()

        self._build_css()
        self._build_ui()

        self._do_poll()
        GLib.timeout_add(60_000, self._do_poll)
        self._schedule_anim_tick()
        self._schedule_spinner_tick()
        GLib.timeout_add(500, self._drain_queue)
        # Sessions and context are read locally — faster refresh
        self._refresh_local()
        GLib.timeout_add(5_000, self._refresh_local)

    def _init_layer_shell(self):
        try:
            from gi.repository import Gtk4LayerShell
            Gtk4LayerShell.init_for_window(self)
            Gtk4LayerShell.set_layer(self, Gtk4LayerShell.Layer.OVERLAY)
            Gtk4LayerShell.set_keyboard_mode(self, Gtk4LayerShell.KeyboardMode.NONE)
        except Exception:
            self.connect("realize", lambda *_: GLib.timeout_add(800, self._apply_keep_above_x11))

    def _apply_keep_above_x11(self):
        title = "Clawdmeter"
        if shutil.which("xdotool"):
            try:
                subprocess.Popen(
                    ["xdotool", "search", "--sync", "--name", title,
                     "windowstate", "--add", "ABOVE"],
                    stderr=subprocess.DEVNULL,
                )
                return False
            except OSError:
                pass
        if shutil.which("wmctrl"):
            try:
                subprocess.Popen(
                    ["wmctrl", "-r", title, "-b", "add,above"],
                    stderr=subprocess.DEVNULL,
                )
            except OSError:
                pass
        return False

    # ── CSS ───────────────────────────────────────────────────────────────────

    def _build_css(self):
        css = f"""
        window {{
            background-color: transparent;
        }}
        .root-box {{
            background-color: {CONTAINER};
            border-radius: 14px;
            border: 1px solid {BORDER_C};
            margin: 5px;
        }}
        .titlebar {{
            background-color: {TITLEBAR};
            padding: 5px 8px 5px 10px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.07);
            border-radius: 14px 14px 0 0;
        }}
        .title-label {{
            color: rgba(242, 242, 242, 0.85);
            font-size: 10pt;
            font-weight: bold;
        }}
        .status-sub {{
            color: {DIM_C};
            font-size: 7pt;
            font-family: monospace;
        }}
        .win-btn {{
            background-color: rgba(72, 64, 90, 0.70);
            border-radius: 50%;
            min-width: 22px;
            min-height: 22px;
            padding: 3px;
            border: 1px solid rgba(255, 255, 255, 0.12);
            color: rgba(242, 242, 242, 0.80);
        }}
        .win-btn:hover {{
            background-color: rgba(110, 96, 140, 1.0);
            color: rgba(255, 255, 255, 1.0);
            border-color: rgba(255, 255, 255, 0.25);
        }}
        .win-btn-close:hover {{
            background-color: {RED_C};
            color: rgba(255, 255, 255, 1.0);
            border-color: rgba(255, 255, 255, 0.25);
        }}
        .section-label {{
            color: {DIM_C};
            font-size: 7pt;
            letter-spacing: 1px;
        }}
        .pct-label {{
            color: {TEXT_C};
            font-weight: bold;
            font-size: 24pt;
        }}
        .reset-label {{
            color: {DIM_C};
            font-size: 7.5pt;
        }}
        .weekly-panel {{
            background-color: {PANEL_C};
            border-radius: 10px;
            border: 1px solid rgba(255, 255, 255, 0.06);
            padding: 8px 12px;
            margin: 6px 8px 0 8px;
        }}
        .weekly-pct {{
            color: {TEXT_C};
            font-weight: bold;
            font-size: 18pt;
        }}
        .spinner-label {{
            color: {ACCENT_C};
            font-size: 7.5pt;
            margin: 4px 10px 8px 10px;
        }}
        .sessions-panel {{
            background-color: {PANEL_C};
            border-radius: 10px;
            border: 1px solid rgba(255, 255, 255, 0.06);
            padding: 8px 12px;
            margin: 6px 8px 0 8px;
        }}
        .sessions-title {{
            color: {DIM_C};
            font-size: 7pt;
            letter-spacing: 1px;
        }}
        .sessions-value {{
            color: {TEXT_C};
            font-weight: bold;
            font-size: 15pt;
        }}
        .ctx-label {{
            color: {DIM_C};
            font-size: 7.5pt;
        }}
        .project-info {{
            color: {DIM_C};
            font-size: 7pt;
            font-family: monospace;
        }}
        """
        provider = Gtk.CssProvider()
        provider.load_from_string(css)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    # ── UI layout ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Outer container (transparent — needed so border-radius works)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_child(outer)

        # Main card with rounded corners + semi-transparent bg
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.add_css_class("root-box")
        outer.append(root)

        # ── Title bar (WindowHandle = draggable via WM) ──
        handle = Gtk.WindowHandle()
        tbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        tbar.add_css_class("titlebar")

        # Left: title + status sub-label stacked
        title_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        title_col.set_hexpand(True)
        title_col.set_halign(Gtk.Align.START)
        title_col.set_valign(Gtk.Align.CENTER)

        title = Gtk.Label(label="claude usage")
        title.add_css_class("title-label")
        title.set_halign(Gtk.Align.START)
        title_col.append(title)

        self._status_dot = Gtk.Label(label="◆ connecting…")
        self._status_dot.add_css_class("status-sub")
        self._status_dot.set_halign(Gtk.Align.START)
        title_col.append(self._status_dot)

        tbar.append(title_col)

        # Right: window buttons
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_box.set_valign(Gtk.Align.CENTER)
        tbar.append(btn_box)

        minimize = self._win_btn("window-minimize-symbolic", close=False)
        minimize.connect("clicked", lambda _: self.minimize())
        btn_box.append(minimize)

        close = self._win_btn("window-close-symbolic", close=True)
        close.connect("clicked", lambda _: self.close())
        btn_box.append(close)

        handle.set_child(tbar)
        root.append(handle)

        # ── Top row: animation + session ──
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        top.set_margin_top(8)
        top.set_margin_start(10)
        top.set_margin_end(10)
        root.append(top)

        # Clawd pixel-art canvas
        canvas_wrap = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        canvas_wrap.set_valign(Gtk.Align.CENTER)
        self._canvas = Gtk.DrawingArea()
        self._canvas.set_size_request(PIXEL_SCALE * 20, PIXEL_SCALE * 20)
        self._canvas.set_draw_func(self._draw_frame_cb)
        canvas_wrap.append(self._canvas)
        top.append(canvas_wrap)

        # Session info
        sess = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        sess.set_hexpand(True)
        sess.set_valign(Gtk.Align.CENTER)
        top.append(sess)

        sess.append(self._lbl("SESSION", "section-label"))

        self._s_pct = self._lbl("---%", "pct-label")
        sess.append(self._s_pct)

        self._s_bar = _ProgressBar(GREEN_C)
        sess.append(self._s_bar)

        self._s_reset = self._lbl("---", "reset-label")
        sess.append(self._s_reset)

        # ── Weekly panel ──
        wpanel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        wpanel.add_css_class("weekly-panel")
        root.append(wpanel)

        # Two columns: left = WEEKLY + %, right = project/branch/email
        w_top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        wpanel.append(w_top)

        w_left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        w_left.set_halign(Gtk.Align.START)
        w_left.set_hexpand(True)
        w_top.append(w_left)

        w_left.append(self._lbl("WEEKLY", "section-label"))
        self._w_pct = self._lbl("---%", "weekly-pct")
        w_left.append(self._w_pct)

        w_meta = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        w_meta.set_halign(Gtk.Align.END)
        w_meta.set_valign(Gtk.Align.START)
        w_top.append(w_meta)

        self._w_project = self._elbl("project-info", align=Gtk.Align.END)
        self._w_branch  = self._elbl("project-info", align=Gtk.Align.END)
        self._w_account = self._elbl("project-info", align=Gtk.Align.END)
        w_meta.append(self._w_project)
        w_meta.append(self._w_branch)
        w_meta.append(self._w_account)

        self._w_bar = _ProgressBar(GREEN_C)
        wpanel.append(self._w_bar)

        self._w_reset = self._lbl("---", "reset-label")
        wpanel.append(self._w_reset)

        # ── Sesiones + Contexto ──
        spanel = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        spanel.add_css_class("sessions-panel")
        root.append(spanel)

        # Sessions block
        sess_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        sess_box.set_hexpand(True)
        spanel.append(sess_box)
        sess_box.append(self._lbl("SESSIONS", "sessions-title"))
        self._lbl_sessions = self._lbl("—", "sessions-value")
        sess_box.append(self._lbl_sessions)
        self._lbl_sess_detail = self._lbl("", "ctx-label")
        sess_box.append(self._lbl_sess_detail)

        # Divider
        sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        sep.set_margin_top(4)
        sep.set_margin_bottom(4)
        spanel.append(sep)

        # Context block
        ctx_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        ctx_box.set_hexpand(True)
        spanel.append(ctx_box)
        ctx_box.append(self._lbl("CONTEXT", "sessions-title"))
        self._lbl_ctx_pct = self._lbl("—", "sessions-value")
        ctx_box.append(self._lbl_ctx_pct)
        self._lbl_ctx_detail = self._lbl("", "ctx-label")
        ctx_box.append(self._lbl_ctx_detail)
        self._ctx_bar = _ProgressBar(GREEN_C)
        ctx_box.append(self._ctx_bar)

        # ── Spinner ──
        self._spinner_lbl = self._lbl("", "spinner-label")
        self._spinner_lbl.set_halign(Gtk.Align.START)
        root.append(self._spinner_lbl)

    @staticmethod
    def _lbl(text, css_class):
        lbl = Gtk.Label(label=text)
        lbl.add_css_class(css_class)
        lbl.set_halign(Gtk.Align.START)
        lbl.set_xalign(0)
        return lbl

    @staticmethod
    def _win_btn(icon_name, close=False):
        btn = Gtk.Button()
        btn.set_has_frame(False)
        btn.add_css_class("win-btn")
        if close:
            btn.add_css_class("win-btn-close")
        btn.set_valign(Gtk.Align.CENTER)
        btn.set_halign(Gtk.Align.CENTER)
        img = Gtk.Image.new_from_icon_name(icon_name)
        img.set_pixel_size(12)
        btn.set_child(img)
        return btn

    @staticmethod
    def _elbl(css_class, max_chars=10, align=Gtk.Align.START):
        """Label with end-ellipsis and tooltip for full text on hover."""
        lbl = Gtk.Label(label="")
        lbl.add_css_class(css_class)
        lbl.set_halign(align)
        lbl.set_xalign(1.0 if align == Gtk.Align.END else 0.0)
        lbl.set_ellipsize(Pango.EllipsizeMode.END)
        lbl.set_max_width_chars(max_chars)
        return lbl


    # ── Sessions and context (local, fast refresh) ───────────────────────────

    def _refresh_local(self):
        threading.Thread(target=self._bg_local, daemon=True).start()
        return True

    def _bg_local(self):
        sessions    = poll_sessions()
        ctx, proj   = poll_local_data()
        email       = read_account_info()
        GLib.idle_add(self._apply_local, sessions, ctx, proj, email)

    def _apply_local(self, sessions, ctx, proj=None, email=""):
        n = len(sessions)
        busy  = sum(1 for s in sessions if s["status"] == "busy")
        idle  = n - busy

        self._lbl_sessions.set_markup(
            f'<span foreground="{TEXT_C}" font_weight="bold" font_size="15pt">{n}</span>'
        )
        if n == 0:
            self._lbl_sess_detail.set_label("no sessions")
        else:
            parts = []
            if busy: parts.append(f"{busy} active")
            if idle: parts.append(f"{idle} idle")
            self._lbl_sess_detail.set_label(" · ".join(parts))

        if ctx:
            pct = ctx["ctx_pct"]
            color = pct_color(pct)
            self._lbl_ctx_pct.set_markup(
                f'<span foreground="{color}" font_weight="bold" font_size="15pt">{pct}%</span>'
            )
            used_k = ctx["ctx_used"] // 1000
            self._lbl_ctx_detail.set_label(f"{used_k}k / 200k  {ctx['model']}")
            self._ctx_bar.set_value(pct / 100, color)
        else:
            self._lbl_ctx_pct.set_label("—")
            self._lbl_ctx_detail.set_label("no active session")
            self._ctx_bar.set_value(0, GREEN_C)

        # Project + branch + account
        p = proj.get("project", "") if proj else ""
        b = proj.get("branch",  "") if proj else ""
        full_tip = "\n".join(x for x in [p, b, email] if x)
        self._w_project.set_label(p)
        self._w_branch.set_label(b)
        self._w_account.set_label(email)
        for lbl in (self._w_project, self._w_branch, self._w_account):
            lbl.set_tooltip_text(full_tip or None)

    # ── Polling API ───────────────────────────────────────────────────────────

    def _do_poll(self):
        threading.Thread(target=lambda: self._poll_q.put(poll_api()),
                         daemon=True).start()
        return True

    def _drain_queue(self):
        try:
            while True:
                data = self._poll_q.get_nowait()
                self._apply_data(data)
        except queue.Empty:
            pass
        return True

    def _apply_data(self, data):
        if not data.get("ok"):
            self._spinner_lbl.set_label(f"⚠ {data.get('error', 'poll failed')}")
            self._status_dot.set_markup(
                f'<span foreground="{RED_C}">◆ error</span>'
            )
            return

        s, w = data["s"], data["w"]
        sc, wc = pct_color(s), pct_color(w)
        st = data.get("st", "allowed")

        dot_color = RED_C if st == "limited" else GREEN_C
        dot_text  = "◆ rate limited" if st == "limited" else "◆ online"
        self._status_dot.set_markup(
            f'<span foreground="{dot_color}">{dot_text}</span>'
        )

        self._s_pct.set_markup(
            f'<span foreground="{sc}" font_family="monospace" font_weight="bold" font_size="24pt">{s}%</span>'
        )
        self._s_reset.set_label(format_reset(data["sr"]))
        self._s_bar.set_value(s / 100, sc)

        self._w_pct.set_markup(
            f'<span foreground="{wc}" font_family="monospace" font_weight="bold" font_size="18pt">{w}%</span>'
        )
        self._w_reset.set_label(format_reset(data["wr"]))
        self._w_bar.set_value(w / 100, wc)

    # ── Clawd pixel-art animation ─────────────────────────────────────────────

    def _draw_frame_cb(self, area, cr, width, height):
        # Transparent canvas background
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()

        if not self.animations:
            return

        anim    = self.animations[self._anim_idx]
        frame   = anim["frames"][self._frame_idx]
        palette = anim["palette"]

        for row_i, row in enumerate(frame["grid"]):
            for col_i, ci in enumerate(row):
                color = palette[ci] if ci < len(palette) else "transparent"
                if not color or color == "transparent":
                    continue
                r, g, b, a = hex_to_rgba(color)
                cr.set_source_rgba(r, g, b, a)
                cr.rectangle(
                    col_i * PIXEL_SCALE, row_i * PIXEL_SCALE,
                    PIXEL_SCALE, PIXEL_SCALE,
                )
                cr.fill()

    def _schedule_anim_tick(self):
        if not self.animations:
            GLib.timeout_add(500, self._anim_tick)
            return
        hold = self.animations[self._anim_idx]["frames"][self._frame_idx].get("hold", 150)
        GLib.timeout_add(hold, self._anim_tick)

    def _anim_tick(self):
        if not self.animations:
            GLib.timeout_add(500, self._anim_tick)
            return False
        self._frame_idx = (self._frame_idx + 1) % len(self.animations[self._anim_idx]["frames"])
        if self._frame_idx == 0 and random.random() < 0.2:
            self._anim_idx = random.randrange(len(self.animations))
        self._canvas.queue_draw()
        self._schedule_anim_tick()
        return False

    # ── Spinner ───────────────────────────────────────────────────────────────

    def _schedule_spinner_tick(self):
        n      = len(SPINNER_FRAMES)
        phases = 2 * (n - 1)
        phase  = self._spin_phase % phases
        idx    = phase if phase < n else phases - phase
        GLib.timeout_add(SPINNER_MS[idx], self._spinner_tick)

    def _spinner_tick(self):
        n      = len(SPINNER_FRAMES)
        phases = 2 * (n - 1)
        phase  = self._spin_phase % phases
        idx    = phase if phase < n else phases - phase
        self._spin_phase = (self._spin_phase + 1) % phases
        if self._spin_phase == 0:
            self._msg_idx = (self._msg_idx + 1) % len(MESSAGES)
        self._spinner_lbl.set_label(f"{SPINNER_FRAMES[idx]} {MESSAGES[self._msg_idx]}…")
        self._schedule_spinner_tick()
        return False


# ── Progress bar (Cairo-drawn) ────────────────────────────────────────────────

class _ProgressBar(Gtk.DrawingArea):
    H = 5

    def __init__(self, color):
        super().__init__()
        self._value = 0.0
        self._color = color
        self.set_size_request(-1, self.H)
        self.set_vexpand(False)
        self.set_draw_func(self._draw)

    def set_value(self, fraction, color):
        self._value = max(0.0, min(1.0, fraction))
        self._color = color
        self.queue_draw()

    def _draw(self, area, cr, width, height):
        # Track
        r, g, b, _ = hex_to_rgba(BAR_BG_C)
        cr.set_source_rgba(r, g, b, 1.0)
        _rounded_rect(cr, 0, 0, width, height, height / 2)
        cr.fill()
        # Fill
        fill_w = int(width * self._value)
        if fill_w > 0:
            r, g, b, _ = hex_to_rgba(self._color)
            cr.set_source_rgba(r, g, b, 0.85)
            _rounded_rect(cr, 0, 0, fill_w, height, height / 2)
            cr.fill()


def _rounded_rect(cr, x, y, w, h, r):
    cr.new_sub_path()
    cr.arc(x + w - r, y + r,     r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0,             math.pi / 2)
    cr.arc(x + r,     y + h - r, r, math.pi / 2,   math.pi)
    cr.arc(x + r,     y + r,     r, math.pi,        3 * math.pi / 2)
    cr.close_path()


# ── App entry ─────────────────────────────────────────────────────────────────

class ClawdmeterApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="com.clawdmeter")

    def do_activate(self):
        win = ClawdmeterWindow(self)
        win.present()


def main():
    app = ClawdmeterApp()
    app.run()


if __name__ == "__main__":
    main()
