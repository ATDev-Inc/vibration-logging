#!/bin/bash

# Exit on error
set -e

# Project root directory
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo "==========================================="
echo "   Vibration Logger Pro Installer"
echo "==========================================="

# 1. Ensure scripts are executable
chmod +x scripts/janitor.sh scripts/run_system.sh scripts/test_led.sh scripts/wifi_low_power.sh scripts/blink_led.sh

# 2. Build the C++ binary
echo "[1/5] Building project..."
cd firmware
mkdir -p build && cd build
cmake ..
make -j$(nproc)
cd "$PROJECT_DIR"

# 3. Configure Hardware Permissions
echo "[2/5] Adding $USER to spi and gpio groups..."
sudo usermod -aG spi,gpio $USER

# 4. Install WiFi Low-Power Service
echo "[3/5] Configuring WiFi Low-Power Mode..."
sudo cp scripts/wifi_low_power.sh /usr/local/bin/
cat <<EOF | sudo tee /etc/systemd/system/wifi-lowpower.service > /dev/null
[Unit]
Description=Set WiFi to Low Power Mode
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/wifi_low_power.sh

[Install]
WantedBy=multi-user.target
EOF

# 5. Install Vibration Logger Service (with CPU Pinning)
echo "[4/5] Configuring Vibration Logger Service (Real-Time)..."
SERVICE_FILE="vibration_logger.service"

# Dynamically update paths and ensure User=root
sed -e "s|User=.*|User=root|g" \
    -e "s|WorkingDirectory=.*|WorkingDirectory=$PROJECT_DIR|g" \
    -e "s|ExecStart=.*|ExecStart=$PROJECT_DIR/scripts/run_system.sh|g" \
    "$SERVICE_FILE" > /tmp/"$SERVICE_FILE"

sudo mv /tmp/"$SERVICE_FILE" /etc/systemd/system/

# 6. Enable everything
echo "[5/5] Enabling services..."
sudo systemctl daemon-reload
sudo systemctl enable wifi-lowpower.service
sudo systemctl enable vibration_logger.service

echo "-------------------------------------------"
echo "Pro Installation Successful!"
echo "-------------------------------------------"
echo "Optimizations applied:"
echo " - CPU Affinity: Core 3 (Isolated from OS/WiFi)"
echo " - Scheduling: SCHED_FIFO (Real-Time Priority)"
echo " - WiFi: 10dBm (Reduced EMI/Power Ripple)"
echo ""
echo "Please REBOOT now to apply group changes and start services."
echo "-------------------------------------------"
