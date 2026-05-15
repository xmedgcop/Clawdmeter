#!/bin/bash

APP_ID="com.clawdmeter"
GREEN="\033[0;32m"
NC="\033[0m"
ok() { echo -e "  ${GREEN}✓${NC} $1"; }

echo ""
echo "Uninstalling Clawdmeter Desktop..."
echo ""

pkill -f clawdmeter_desktop.py 2>/dev/null && ok "Process stopped" || true

rm -f "$HOME/.local/share/applications/${APP_ID}.desktop"
ok "Launcher entry removed"

rm -f "$HOME/.config/autostart/${APP_ID}.desktop"
ok "Autostart removed"

rm -f "$HOME/.local/share/icons/hicolor/128x128/apps/${APP_ID}.png"
gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
ok "Icon removed"

update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true

echo ""
read -rp "  Also remove account config (~/.config/clawdmeter/)? [y/N] " answer
if [[ "$answer" == "y" || "$answer" == "Y" ]]; then
    rm -rf "$HOME/.config/clawdmeter"
    ok "Config removed"
fi

echo ""
echo "  Done. Project files were not touched."
echo ""
