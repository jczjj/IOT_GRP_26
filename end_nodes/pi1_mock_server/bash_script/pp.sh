#!/bin/bash
# VERSION: 7.7 (SDN Relay - Aggressive Purge Edition)
AP_SSID="pi_01pi_01" 
AP_PASS="pi_01pi_01"
AP_IP="10.42.1.1/24"
LOG="test_evidence.log"

echo "[$(date)] --- PI 1 RELAY START (V7.7) ---" > $LOG
sudo iw dev wlan0 set power_save off

# 1. AGGRESSIVE PURGE: Delete any connection profile containing "pi_" or matching our SSID
echo "[$(date)] Purging all existing pi_ related network profiles..." >> $LOG
for uuid in $(nmcli -g UUID,NAME con show | grep -E "pi_|pi_01pi_01" | cut -d: -f1); do 
    sudo nmcli con delete uuid "$uuid" >> $LOG 2>&1
done
sudo iw dev ap0 del >> $LOG 2>&1

# 2. Create the Virtual Hotspot
sudo iw dev wlan0 interface add ap0 type __ap
sleep 2
sudo nmcli con add type wifi ifname ap0 mode ap con-name "$AP_SSID" ssid "$AP_SSID"
sudo nmcli con modify "$AP_SSID" 802-11-wireless-security.key-mgmt wpa-psk 802-11-wireless-security.psk "$AP_PASS"
sudo nmcli con modify "$AP_SSID" ipv4.method shared ipv4.addresses "$AP_IP"
sudo nmcli con up "$AP_SSID" >> $LOG 2>&1

echo "[$(date)] Relay SSID '$AP_SSID' is now LIVE at 10.42.1.1" >> $LOG

# 3. Mission Action: Prepare for incoming Gatita
mkdir -p ~/received_data
python3 -m http.server 8000 --directory ~/received_data/ &
