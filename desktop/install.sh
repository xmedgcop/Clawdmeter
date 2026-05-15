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
echo "[1/5] Checking dependencies..."

# Remove conflicting pip 'gi' stub that shadows the system python3-gi package
if pip3 show gi &>/dev/null 2>&1; then
    info "Removing conflicting pip 'gi' package..."
    pip3 uninstall -y gi 2>/dev/null || true
fi

MISSING=""
# Check python3-gi via dpkg (not import) to avoid pip stub false-positive
dpkg -s python3-gi &>/dev/null 2>&1     || MISSING="$MISSING python3-gi"
python3 -c "import cairo" 2>/dev/null    || MISSING="$MISSING python3-gi-cairo"
command -v curl    >/dev/null 2>&1       || MISSING="$MISSING curl"
command -v wmctrl  >/dev/null 2>&1       || MISSING="$MISSING wmctrl"

if [ -n "$MISSING" ]; then
    info "Installing:$MISSING"
    sudo apt install -y $MISSING
fi
ok "Dependencies ready"

# ── 2. Account config ─────────────────────────────────────────────────────────
echo "[2/5] Configuring account..."

mkdir -p "$CONFIG_DIR"
if [ ! -f "$CONFIG_DIR/config.json" ]; then
    read -rp "  Enter your Claude account email (leave blank to skip): " email
    if [ -n "$email" ]; then
        python3 -c "import json,sys; print(json.dumps({'email': sys.argv[1]}))" "$email" \
            > "$CONFIG_DIR/config.json"
        ok "Email saved to $CONFIG_DIR/config.json"
    else
        printf '{"email": ""}\n' > "$CONFIG_DIR/config.json"
        info "No email set — you can edit $CONFIG_DIR/config.json later"
    fi
else
    ok "Config already exists ($CONFIG_DIR/config.json)"
fi

# ── 3. Icon ───────────────────────────────────────────────────────────────────
echo "[3/5] Installing icon..."

ICON_DIR="$HOME/.local/share/icons/hicolor/128x128/apps"
mkdir -p "$ICON_DIR"

if [ -f "$ICON_SRC" ]; then
    cp "$ICON_SRC" "$ICON_DIR/${APP_ID}.png"
    gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
    ok "Icon installed"
else
    info "Icon not found in assets/ — default icon will be used"
fi

# ── 4. App launcher entry ─────────────────────────────────────────────────────
echo "[4/5] Registering in app launcher..."

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

# ── 5. Autostart ──────────────────────────────────────────────────────────────
echo "[5/5] Configuring autostart..."

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
