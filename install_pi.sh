#!/usr/bin/env bash
# Install script for Raspberry Pi 4 OS (64-bit)
# Run with: bash install_pi.sh

set -euo pipefail

echo "==> Updating apt repositories..."
sudo apt-get update -y

echo "==> Installing required system packages..."
sudo apt-get install -y \
    python3-pip \
    python3-dev \
    python3-opencv \
    python3-numpy \
    python3-pil \
    i2c-tools \
    espeak \
    libespeak1 \
    portaudio19-dev \
    libatlas-base-dev \
    v4l-utils \
    curl

echo "==> Enabling I2C interface..."
sudo raspi-config nonint do_i2c 0

echo "==> Installing Python dependencies..."
# requirements-pi.txt covers both Pis (hub and rover run the same package).
# Pip install without breaking system packages on modern Debian
pip3 install --break-system-packages -r requirements-pi.txt || pip3 install -r requirements-pi.txt

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CURRENT_USER="$(whoami)"

UNIT="heist.service"
KIOSK=0
for arg in "$@"; do
    case "$arg" in
        --rover) UNIT="rover.service"
                 echo "==> Rover mode: ${UNIT} runs 'python3 -m rig.rover' instead of the hub app." ;;
        --kiosk) KIOSK=1
                 echo "==> Kiosk mode: local monitor shows the dashboard, no laptop needed." ;;
    esac
done

if [[ "${KIOSK}" == "1" ]]; then
    echo "==> Installing kiosk display stack (cage + chromium)..."
    sudo apt-get install -y cage chromium-browser 2>/dev/null \
        || sudo apt-get install -y cage chromium
fi

echo "==> Configuring systemd service for ${CURRENT_USER} in ${PROJECT_DIR}..."
SERVICE_FILE="/etc/systemd/system/${UNIT}"
sudo cp "${PROJECT_DIR}/${UNIT}" "${SERVICE_FILE}"
sudo sed -i "s|User=pi|User=${CURRENT_USER}|g" "${SERVICE_FILE}"
sudo sed -i "s|/home/pi/rowdyhack26-precode|${PROJECT_DIR}|g" "${SERVICE_FILE}"

sudo systemctl daemon-reload
sudo systemctl enable "${UNIT}"

if [[ "${KIOSK}" == "1" ]]; then
    KIOSK_FILE="/etc/systemd/system/kiosk.service"
    sudo cp "${PROJECT_DIR}/kiosk.service" "${KIOSK_FILE}"
    sudo sed -i "s|User=pi|User=${CURRENT_USER}|g" "${KIOSK_FILE}"
    # The binary is chromium on Bookworm, chromium-browser on Bullseye , 
    # point the unit at whichever landed.
    CHROMIUM_BIN="$(command -v chromium || command -v chromium-browser || true)"
    if [[ -n "${CHROMIUM_BIN}" ]]; then
        sudo sed -i "s|/usr/bin/chromium |${CHROMIUM_BIN} |" "${KIOSK_FILE}"
    else
        echo "WARN: no chromium binary found; kiosk.service will fail to start."
    fi
    sudo systemctl enable kiosk.service
    echo "==> Kiosk enabled: the HDMI monitor shows the dashboard on boot."
fi

echo ""
echo "Installation complete (${UNIT})."
echo "To start the service now:   sudo systemctl start ${UNIT%.service}"
echo "To view live logs:          journalctl -u ${UNIT%.service} -f"
echo "To stop the service:        sudo systemctl stop ${UNIT%.service}"
