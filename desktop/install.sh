#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
WIDGET="$SCRIPT_DIR/clawdmeter_desktop.py"
ICON_SRC="$PROJECT_DIR/assets/Claude Code Logo.png"
APP_ID="com.clawdmeter"
CONFIG_DIR="$HOME/.config/clawdmeter"

GREEN="\033[0;32m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
NC="\033[0m"

ok()   { echo -e "  ${GREEN}✓${NC} $1"; }
info() { echo -e "  ${YELLOW}→${NC} $1"; }
err()  { echo -e "  ${RED}✗${NC} $1"; exit 1; }

echo ""
echo "╔══════════════════════════════════════╗"
echo "║     Clawdmeter Desktop — Install     ║"
echo "╚══════════════════════════════════════╝"
echo ""

# ── 1. Dependencies ───────────────────────────────────────────────────────────
echo "[1/4] Checking dependencies..."

MISSING=""
dpkg -s python3-gi        &>/dev/null || MISSING="$MISSING python3-gi"
dpkg -s python3-gi-cairo  &>/dev/null || MISSING="$MISSING python3-gi-cairo"
dpkg -s gir1.2-gtk-4.0   &>/dev/null || MISSING="$MISSING gir1.2-gtk-4.0"
command -v curl   >/dev/null 2>&1     || MISSING="$MISSING curl"

if [ -n "$MISSING" ]; then
    info "Installing:$MISSING"
    sudo apt install -y $MISSING
fi

# Always-on-top: prefer gtk4-layer-shell (Wayland-native), fall back to xdotool/wmctrl
ABOVE_MISSING=""
dpkg -s gir1.2-gtk4layershell-1.0 &>/dev/null || ABOVE_MISSING="$ABOVE_MISSING gir1.2-gtk4layershell-1.0"
if [ -n "$ABOVE_MISSING" ]; then
    # Try layer shell first; if not in repos fall back to xdotool+wmctrl
    if apt-cache show gir1.2-gtk4layershell-1.0 &>/dev/null 2>&1; then
        info "Installing always-on-top support (gtk4-layer-shell)..."
        sudo apt install -y gir1.2-gtk4layershell-1.0
    else
        info "gtk4-layer-shell not available, installing xdotool+wmctrl fallback..."
        sudo apt install -y xdotool wmctrl 2>/dev/null || true
    fi
else
    ok "gtk4-layer-shell already installed"
fi

# Verify GTK4 actually works after install
if ! python3 -c "import gi; gi.require_version('Gtk','4.0'); from gi.repository import Gtk" 2>/dev/null; then
    err "GTK4 Python bindings not working. Try: sudo apt install --reinstall python3-gi gir1.2-gtk-4.0"
fi
ok "Dependencies ready"

# ── 2. Icon ───────────────────────────────────────────────────────────────────
echo "[2/4] Installing icon..."

ICON_DIR="$HOME/.local/share/icons/hicolor/128x128/apps"
mkdir -p "$ICON_DIR"

if [ -f "$ICON_SRC" ]; then
    cp "$ICON_SRC" "$ICON_DIR/${APP_ID}.png"
    gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
    ok "Icon installed"
else
    info "Icon not found in assets/ — default icon will be used"
fi

# ── 3. App launcher entry ─────────────────────────────────────────────────────
echo "[3/4] Registering in app launcher..."

mkdir -p "$HOME/.local/share/applications"
cat > "$HOME/.local/share/applications/${APP_ID}.desktop" << EOF
[Desktop Entry]
Name=Clawdmeter
GenericName=Claude Usage Monitor
Comment=Desktop monitor for Claude Code usage
Type=Application
Icon=${APP_ID}
Exec=env GDK_BACKEND=x11 python3 ${WIDGET}
StartupWMClass=${APP_ID}
Categories=Utility;Monitor;
Keywords=claude;ai;usage;monitor;clawdmeter;
NoDisplay=false
EOF

update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
ok "Available in launcher (search 'Clawdmeter')"

# ── 4. Autostart ──────────────────────────────────────────────────────────────
echo "[4/4] Configuring autostart..."

mkdir -p "$HOME/.config/autostart"
cat > "$HOME/.config/autostart/${APP_ID}.desktop" << EOF
[Desktop Entry]
Type=Application
Name=Clawdmeter
Icon=${APP_ID}
Exec=env GDK_BACKEND=x11 python3 ${WIDGET}
Terminal=false
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
EOF

ok "Will start automatically on login"

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}╔══════════════════════════════════════╗${NC}"
echo -e "${GREEN}║        Installation complete!        ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════╝${NC}"
echo ""
echo "  • Find it in your apps as 'Clawdmeter'"
echo "  • Starts automatically on login"
echo "  • To uninstall: ./uninstall.sh"
echo ""

read -rp "  Launch now? [Y/n] " answer
if [[ "$answer" != "n" && "$answer" != "N" ]]; then
    python3 "$WIDGET" &
    ok "Launched!"
fi

echo ""
