#!/bin/bash
# V12.0 Node 0 Anchor
SSID="pi00pi00"
PASS="pi00pi00"
LOG="/home/sdn_service/poc/python_script/production.log"

echo "[$(date)] ⚓ ANCHOR: Initializing Node 0..." >> "$LOG"

# 1. Create virtual interface ap0 to preserve wlan0 connection
if ! ip link show ap0 > /dev/null 2>&1; then
    sudo iw dev wlan0 interface add ap0 type __ap
fi
sudo ip link set ap0 up

# 2. Purge old profiles
for uuid in $(nmcli -g UUID,NAME con show | grep "pi0" | cut -d: -f1); do
    sudo nmcli con delete uuid "$uuid" >> "$LOG" 2>&1
done

# 3. Host Hotspot
sudo nmcli con add type wifi ifname ap0 con-name "$SSID" autoconnect yes ssid "$SSID" mode ap ipv4.method shared ipv4.addresses 10.42.0.1/24 >> "$LOG" 2>&1
sudo nmcli con modify "$SSID" wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$PASS" >> "$LOG" 2>&1
sudo nmcli con up "$SSID" >> "$LOG" 2>&1
