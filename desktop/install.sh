#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
WIDGET="$SCRIPT_DIR/clawdmeter_desktop.py"
ICON_SRC="$PROJECT_DIR/assets/Claude Code Logo.png"
APP_ID="com.clawdmeter"

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

# ── 1. Dependencias ──────────────────────────────────────────────────────────
echo "[1/4] Verificando dependencias..."

MISSING=""
python3 -c "import gi" 2>/dev/null          || MISSING="$MISSING python3-gi"
python3 -c "import cairo" 2>/dev/null       || MISSING="$MISSING python3-gi-cairo"
command -v curl >/dev/null 2>&1             || MISSING="$MISSING curl"

if [ -n "$MISSING" ]; then
    info "Instalando:$MISSING"
    sudo apt install -y $MISSING
fi
ok "Dependencias listas"

# ── 2. Ícono ─────────────────────────────────────────────────────────────────
echo "[2/4] Instalando ícono..."

ICON_DIR="$HOME/.local/share/icons/hicolor/128x128/apps"
mkdir -p "$ICON_DIR"

if [ -f "$ICON_SRC" ]; then
    cp "$ICON_SRC" "$ICON_DIR/${APP_ID}.png"
    gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
    ok "Ícono instalado"
else
    info "Ícono no encontrado en assets/, se usará el ícono por defecto"
fi

# ── 3. Entrada en el launcher de aplicaciones ─────────────────────────────────
echo "[3/4] Registrando en el launcher de apps..."

mkdir -p "$HOME/.local/share/applications"
cat > "$HOME/.local/share/applications/${APP_ID}.desktop" << EOF
[Desktop Entry]
Name=Clawdmeter
GenericName=Claude Usage Monitor
Comment=Monitor de uso de Claude Code en el escritorio
Type=Application
Icon=${APP_ID}
Exec=python3 ${WIDGET}
StartupWMClass=${APP_ID}
Categories=Utility;Monitor;
Keywords=claude;ai;usage;monitor;clawdmeter;
NoDisplay=false
EOF

update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
ok "Disponible en el launcher (busca 'Clawdmeter')"

# ── 4. Autostart ──────────────────────────────────────────────────────────────
echo "[4/4] Configurando inicio automático..."

mkdir -p "$HOME/.config/autostart"
cat > "$HOME/.config/autostart/${APP_ID}.desktop" << EOF
[Desktop Entry]
Type=Application
Name=Clawdmeter
Exec=python3 ${WIDGET}
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
EOF

ok "Arrancará automáticamente al iniciar sesión"

# ── Listo ─────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}╔══════════════════════════════════════╗${NC}"
echo -e "${GREEN}║           ¡Instalación lista!        ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════╝${NC}"
echo ""
echo "  • Búscalo en tus apps como 'Clawdmeter'"
echo "  • Arranca solo al iniciar sesión"
echo "  • Para desinstalarlo: ./uninstall.sh"
echo ""

read -rp "  ¿Lanzar ahora? [Y/n] " answer
if [[ "$answer" != "n" && "$answer" != "N" ]]; then
    python3 "$WIDGET" &
    ok "¡Lanzado!"
fi

echo ""
