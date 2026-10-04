#!/usr/bin/env bash
# Hub Pi becomes its own Wi-Fi hotspot: the escape hatch when the venue's
# network is dead, captive-portaled, or too crowded to join.
#
#   bash rig/hotspot.sh            # AP "HEIST-RIG" / password "crewcrew"
#   HOTSPOT_SSID=X HOTSPOT_PSK=Y bash rig/hotspot.sh
#
# Everything joins that SSID: laptop, wrist, rover all reach the hub at
# 10.42.0.1: dashboard http://10.42.0.1:5000, wrist/rover HUB_URL the same.
# Internet is gone in this mode, so vision falls back (Anthropic→offline) , 
# that's fine, the demo still runs. Flip it back with:
#   sudo nmcli connection down Hotspot
set -euo pipefail

SSID="${HOTSPOT_SSID:-HEIST-RIG}"
PSK="${HOTSPOT_PSK:-crewcrew}"

if ! command -v nmcli >/dev/null; then
    echo "nmcli missing, install NetworkManager or use the desktop hotspot toggle."
    exit 1
fi

echo "Bringing up hotspot '${SSID}' on wlan0..."
sudo nmcli device wifi hotspot ifname wlan0 ssid "${SSID}" password "${PSK}"

echo ""
echo "Hotspot up. Join '${SSID}' (password: ${PSK}) on every device."
echo "Hub is at:    http://10.42.0.1:5000"
echo "Rover .env:   HUB_URL=http://10.42.0.1:5000"
echo "Wrist sketch: #define HUB \"http://10.42.0.1:5000\""
echo "Tear down:    sudo nmcli connection down Hotspot"
