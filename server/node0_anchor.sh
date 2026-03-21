#!/bin/bash
# V12.4 Node 0 Anchor
SSID="pi00pi00"; PASS="pi00pi00"
if ! ip link show ap0 > /dev/null 2>&1; then sudo iw dev wlan0 interface add ap0 type __ap; fi
sudo ip link set ap0 up
for uuid in $(nmcli -g UUID,NAME con show | grep "pi0" | cut -d: -f1); do sudo nmcli con delete uuid "$uuid"; done
sudo nmcli con add type wifi ifname ap0 con-name "$SSID" autoconnect yes ssid "$SSID" mode ap ipv4.method shared ipv4.addresses 10.42.0.1/24
sudo nmcli con modify "$SSID" wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$PASS"
sudo nmcli con up "$SSID"