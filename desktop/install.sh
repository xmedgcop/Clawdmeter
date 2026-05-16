#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
WIDGET="$SCRIPT_DIR/clawdmeter_desktop.py"
ICON_SRC="$PROJECT_DIR/assets/Claude Code Logo.png"
APP_ID="com.clawdmeter"
VENV_DIR="$HOME/.local/share/clawdmeter/venv"
PYTHON_VERSION="${PYTHON_VERSION:-3.12}"

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

# ── 1. System build deps + typelibs ──────────────────────────────────────────
echo "[1/5] Installing system dependencies..."

MISSING=""
# Build deps for PyGObject / pycairo (compiled inside venv via pip)
# Ubuntu 26+ uses girepository-2.0; Ubuntu 24 uses 1.0
if ! dpkg -s libgirepository-2.0-dev &>/dev/null && ! dpkg -s libgirepository1.0-dev &>/dev/null; then
    if apt-cache show libgirepository-2.0-dev &>/dev/null 2>&1; then
        MISSING="$MISSING libgirepository-2.0-dev"
    else
        MISSING="$MISSING libgirepository1.0-dev"
    fi
fi
dpkg -s libcairo2-dev  &>/dev/null || MISSING="$MISSING libcairo2-dev"
dpkg -s libglib2.0-dev &>/dev/null || MISSING="$MISSING libglib2.0-dev"
dpkg -s python3-dev    &>/dev/null || MISSING="$MISSING python3-dev"
dpkg -s pkg-config     &>/dev/null || MISSING="$MISSING pkg-config"
# python3-venv is NOT added to apt — venv is always bootstrapped via get-pip.py
# to avoid broken/missing package URLs on Ubuntu 26+
# Runtime GIR typelibs (not pip-installable — must come from apt)
dpkg -s gir1.2-gtk-4.0 &>/dev/null || MISSING="$MISSING gir1.2-gtk-4.0"
command -v curl >/dev/null 2>&1    || MISSING="$MISSING curl"

if [ -n "$MISSING" ]; then
    info "Installing:$MISSING"
    sudo apt install -y $MISSING
fi

# gtk4-layer-shell: Wayland-native always-on-top (optional, best-effort)
if ! dpkg -s gir1.2-gtk4layershell-1.0 &>/dev/null; then
    if apt-cache show gir1.2-gtk4layershell-1.0 &>/dev/null 2>&1; then
        info "Installing gtk4-layer-shell (always-on-top on Wayland)..."
        sudo apt install -y gir1.2-gtk4layershell-1.0
    else
        info "gtk4-layer-shell not available in repos — installing xdotool fallback..."
        sudo apt install -y xdotool wmctrl 2>/dev/null || true
    fi
fi

ok "System dependencies ready"

# ── 2. Python (pyenv or system) ───────────────────────────────────────────────
echo "[2/5] Setting up Python..."

PYTHON_BIN=""

if command -v pyenv &>/dev/null; then
    info "pyenv found — ensuring Python $PYTHON_VERSION is installed..."
    pyenv install -s "$PYTHON_VERSION"
    PYENV_PYTHON="$(pyenv root)/versions/$PYTHON_VERSION/bin/python3"
    [ -f "$PYENV_PYTHON" ] && PYTHON_BIN="$PYENV_PYTHON"
fi

if [ -z "$PYTHON_BIN" ]; then
    PYTHON_BIN="$(command -v python3)"
    info "Using system Python: $PYTHON_BIN"
fi

PY_VER="$("$PYTHON_BIN" --version 2>&1)"
ok "Python: $PY_VER ($PYTHON_BIN)"

# ── 3. Virtual environment ────────────────────────────────────────────────────
echo "[3/5] Creating virtual environment..."

if [ -d "$VENV_DIR" ]; then
    info "Removing existing venv..."
    rm -rf "$VENV_DIR"
fi

# Always create venv without pip then bootstrap — avoids python3.X-venv apt issues
"$PYTHON_BIN" -m venv --without-pip "$VENV_DIR"
info "Bootstrapping pip..."
curl -s https://bootstrap.pypa.io/get-pip.py -o /tmp/clawdmeter-get-pip.py
"$VENV_DIR/bin/python" /tmp/clawdmeter-get-pip.py --quiet
rm -f /tmp/clawdmeter-get-pip.py

VENV_PYTHON="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"

info "Upgrading pip..."
"$VENV_PIP" install --quiet --upgrade pip

info "Installing PyGObject and pycairo..."
"$VENV_PIP" install --quiet PyGObject pycairo

# Verify GTK4 works inside the venv
if ! "$VENV_PYTHON" -c "import gi; gi.require_version('Gtk','4.0'); from gi.repository import Gtk" 2>/dev/null; then
    err "GTK4 not working in venv. Ensure gir1.2-gtk-4.0 and libgirepository-dev are installed."
fi

ok "Virtual environment ready ($VENV_DIR)"

# ── 4. Icon + app launcher ────────────────────────────────────────────────────
echo "[4/5] Installing icon and app launcher..."

ICON_DIR="$HOME/.local/share/icons/hicolor/128x128/apps"
mkdir -p "$ICON_DIR"
if [ -f "$ICON_SRC" ]; then
    cp "$ICON_SRC" "$ICON_DIR/${APP_ID}.png"
    gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
fi

mkdir -p "$HOME/.local/share/applications"
cat > "$HOME/.local/share/applications/${APP_ID}.desktop" << EOF
[Desktop Entry]
Name=Clawdmeter
GenericName=Claude Usage Monitor
Comment=Desktop monitor for Claude Code usage
Type=Application
Icon=${APP_ID}
Exec=${VENV_PYTHON} ${WIDGET}
StartupWMClass=${APP_ID}
Categories=Utility;Monitor;
Keywords=claude;ai;usage;monitor;clawdmeter;
NoDisplay=false
EOF

update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
ok "App launcher registered (search 'Clawdmeter')"

# ── 5. Autostart ──────────────────────────────────────────────────────────────
echo "[5/5] Configuring autostart..."

mkdir -p "$HOME/.config/autostart"
cat > "$HOME/.config/autostart/${APP_ID}.desktop" << EOF
[Desktop Entry]
Type=Application
Name=Clawdmeter
Icon=${APP_ID}
Exec=${VENV_PYTHON} ${WIDGET}
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
echo "  • Python env: $VENV_DIR"
echo ""

read -rp "  Launch now? [Y/n] " answer
if [[ "$answer" != "n" && "$answer" != "N" ]]; then
    "$VENV_PYTHON" "$WIDGET" &
    ok "Launched!"
fi

echo ""
