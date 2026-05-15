#!/usr/bin/env python3
"""
Clawdmeter Desktop Widget — GTK4 / Hacker Edition
Ubuntu version of the ESP32 Claude usage monitor.

Usage:  python3 clawdmeter_desktop.py
Deps:   python3-gi  python3-gi-cairo  (sudo apt install python3-gi-cairo)
"""

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, Gdk, GLib

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
CONTAINER = "rgba(22, 20, 26, 0.70)"   # dark, very transparent — muestra el escritorio
TITLEBAR  = "rgba(38, 34, 46, 0.97)"   # casi sólido — legible
PANEL_C   = "rgba(32, 28, 40, 0.88)"   # panel interior semi-opaco
TEXT_C    = "#f2f2f2"                   # blanco suave Ubuntu
DIM_C     = "#a09aaa"                   # gris-lavanda
ACCENT_C  = "#E95420"                   # naranja Ubuntu — spinner/accent
GREEN_C   = "#26a269"                   # verde Yaru — uso bajo
AMBER_C   = "#e5a50a"                   # ámbar Yaru — uso medio
RED_C     = "#c01c28"                   # rojo Yaru — uso alto
BAR_BG_C  = "#1a1520"                   # pista de barra
BORDER_C  = "rgba(255, 255, 255, 0.08)" # borde sutil casi invisible

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
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def poll_sessions():
    """Lee ~/.claude/sessions/*.json y devuelve sesiones activas."""
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


def poll_context():
    """Lee el JSONL de sesión más reciente y devuelve uso de contexto real."""
    projects_dir = Path.home() / ".claude" / "projects"
    CTX_WINDOW = 200_000
    try:
        jsonl_files = sorted(
            projects_dir.rglob("*.jsonl"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )
        if not jsonl_files:
            return None

        lines = jsonl_files[0].read_text().strip().splitlines()

        # Buscar el último mensaje assistant con usage
        input_tokens = cache_read = cache_create = output_tokens = 0
        model = ""
        for line in reversed(lines):
            try:
                msg = json.loads(line)
                m = msg.get("message", {})
                if m.get("role") == "assistant" and m.get("usage"):
                    u = m["usage"]
                    input_tokens  = u.get("input_tokens", 0)
                    cache_read    = u.get("cache_read_input_tokens", 0)
                    cache_create  = u.get("cache_creation_input_tokens", 0)
                    output_tokens = u.get("output_tokens", 0)
                    model         = m.get("model", "")
                    break
            except Exception:
                pass

        # Contexto activo = lo que el modelo ve ahora
        ctx_used = input_tokens + cache_read + cache_create
        pct = round(ctx_used / CTX_WINDOW * 100) if CTX_WINDOW else 0

        return {
            "ctx_used":   ctx_used,
            "ctx_window": CTX_WINDOW,
            "ctx_pct":    min(pct, 100),
            "output":     output_tokens,
            "model":      _short_model(model),
            "file":       jsonl_files[0].stem[:8],
        }
    except Exception:
        return None


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
    for entry in json.loads(index_path.read_text()):
        path = ANIM_DIR / entry["filename"].replace(".html", ".json")
        if path.exists():
            anims.append(json.loads(path.read_text()))
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
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return r / 255, g / 255, b / 255, 1.0


# ── GTK4 Window ───────────────────────────────────────────────────────────────

class ClawdmeterWindow(Gtk.ApplicationWindow):

    def __init__(self, app):
        super().__init__(application=app, title="Clawdmeter")
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_icon_name(ICON_NAME)

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
        # Sesiones y contexto se leen localmente — más frecuente
        self._refresh_local()
        GLib.timeout_add(5_000, self._refresh_local)

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
            padding: 3px 8px 3px 10px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.07);
            border-radius: 14px 14px 0 0;
        }}
        .title-label {{
            color: rgba(242, 242, 242, 0.85);
            font-size: 10pt;
            font-weight: bold;
        }}
        .close-btn {{
            background-color: rgba(65, 58, 80, 0.85);
            color: rgba(242, 242, 242, 0.65);
            border-radius: 50%;
            min-width: 20px;
            min-height: 20px;
            padding: 0;
            font-size: 10pt;
        }}
        .close-btn:hover {{
            background-color: rgba(192, 57, 43, 0.85);
            color: rgba(255, 255, 255, 0.95);
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
        .status-dot {{
            color: {GREEN_C};
            font-size: 9pt;
            font-weight: bold;
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

        title = Gtk.Label(label="claude usage")
        title.add_css_class("title-label")
        title.set_hexpand(True)
        title.set_halign(Gtk.Align.START)
        tbar.append(title)

        self._status_dot = Gtk.Label(label="● on")
        self._status_dot.add_css_class("status-dot")
        self._status_dot.set_margin_end(8)
        tbar.append(self._status_dot)

        close = Gtk.Button()
        close.add_css_class("close-btn")
        close.set_has_frame(False)
        close.set_valign(Gtk.Align.CENTER)
        close.set_halign(Gtk.Align.CENTER)
        close_lbl = Gtk.Label(label="✕")
        close_lbl.set_halign(Gtk.Align.CENTER)
        close_lbl.set_valign(Gtk.Align.CENTER)
        close.set_child(close_lbl)
        close.connect("clicked", lambda _: self.close())
        tbar.append(close)

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

        wpanel.append(self._lbl("WEEKLY", "section-label"))

        self._w_pct = self._lbl("---%", "weekly-pct")
        wpanel.append(self._w_pct)

        self._w_bar = _ProgressBar(GREEN_C)
        wpanel.append(self._w_bar)

        self._w_reset = self._lbl("---", "reset-label")
        wpanel.append(self._w_reset)

        # ── Sesiones + Contexto ──
        spanel = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        spanel.add_css_class("sessions-panel")
        root.append(spanel)

        # Bloque sesiones
        sess_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        sess_box.set_hexpand(True)
        spanel.append(sess_box)
        sess_box.append(self._lbl("SESIONES", "sessions-title"))
        self._lbl_sessions = self._lbl("—", "sessions-value")
        sess_box.append(self._lbl_sessions)
        self._lbl_sess_detail = self._lbl("", "ctx-label")
        sess_box.append(self._lbl_sess_detail)

        # Separador visual
        sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        sep.set_margin_top(4)
        sep.set_margin_bottom(4)
        spanel.append(sep)

        # Bloque contexto
        ctx_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        ctx_box.set_hexpand(True)
        spanel.append(ctx_box)
        ctx_box.append(self._lbl("CONTEXTO", "sessions-title"))
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

    # ── Sesiones y contexto (locales, rápidos) ────────────────────────────────

    def _refresh_local(self):
        threading.Thread(target=self._bg_local, daemon=True).start()
        return True

    def _bg_local(self):
        sessions = poll_sessions()
        ctx      = poll_context()
        GLib.idle_add(self._apply_local, sessions, ctx)

    def _apply_local(self, sessions, ctx):
        n = len(sessions)
        busy  = sum(1 for s in sessions if s["status"] == "busy")
        idle  = n - busy

        self._lbl_sessions.set_markup(
            f'<span foreground="{TEXT_C}" font_weight="bold" font_size="15pt">{n}</span>'
        )
        if n == 0:
            self._lbl_sess_detail.set_label("sin sesiones")
        else:
            parts = []
            if busy: parts.append(f"{busy} activa{'s' if busy>1 else ''}")
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
            self._lbl_ctx_detail.set_label("sin sesión activa")
            self._ctx_bar.set_value(0, GREEN_C)

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
                f'<span foreground="{RED_C}" font_family="monospace" font_size="7pt">◆ ERR</span>'
            )
            return

        s, w = data["s"], data["w"]
        sc, wc = pct_color(s), pct_color(w)
        st = data.get("st", "allowed")

        dot_color = RED_C if st == "limited" else GREEN_C
        dot_text  = "◆ LMT" if st == "limited" else "◆ ON"
        self._status_dot.set_markup(
            f'<span foreground="{dot_color}" font_family="monospace" font_size="7pt">{dot_text}</span>'
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
        r, g, b, a = hex_to_rgba(BAR_BG_C)
        cr.set_source_rgba(r, g, b, 1.0)
        _rounded_rect(cr, 0, 0, width, height, height / 2)
        cr.fill()
        # Fill
        fill_w = int(width * self._value)
        if fill_w > 0:
            r, g, b, a = hex_to_rgba(self._color)
            cr.set_source_rgba(r, g, b, 0.85)
            _rounded_rect(cr, 0, 0, fill_w, height, height / 2)
            cr.fill()


def _rounded_rect(cr, x, y, w, h, r):
    """Draw a rounded rectangle path."""
    import math
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
