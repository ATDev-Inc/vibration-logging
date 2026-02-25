#!/bin/bash
# Wait for the interface to come up
sleep 10
# Set WiFi to 10dBm (approx 10mW) - reduces EMI and power ripple
iw dev wlan0 set txpower fixed 1000
# Disable power management to prevent 'ping spikes' during high-speed logging
iw dev wlan0 set power_save off
echo "[WiFi] Set to low-power mode (10dBm) and disabled power_save."
