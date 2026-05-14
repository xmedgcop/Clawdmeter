#!/bin/bash

APP_ID="com.clawdmeter"
GREEN="\033[0;32m"
NC="\033[0m"
ok() { echo -e "  ${GREEN}✓${NC} $1"; }

echo ""
echo "Desinstalando Clawdmeter Desktop..."
echo ""

pkill -f clawdmeter_desktop.py 2>/dev/null && ok "Proceso detenido" || true

rm -f "$HOME/.local/share/applications/${APP_ID}.desktop"
ok "Entrada del launcher eliminada"

rm -f "$HOME/.config/autostart/${APP_ID}.desktop"
ok "Autostart eliminado"

rm -f "$HOME/.local/share/icons/hicolor/128x128/apps/${APP_ID}.png"
gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
ok "Ícono eliminado"

update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true

echo ""
echo "  Listo. Los archivos del proyecto no fueron tocados."
echo ""
