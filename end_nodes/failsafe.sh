#!/bin/bash
# VERSION: 12.4 (Smart & Calm Watchdog)
LOCK="/tmp/sdn_busy"
SSID="LOQ15_7071"
PASS="section4"
LOG="/home/sdn_service/poc/python_script/production.log"
MAX_AGE_MINUTES=15

# HOME CHECK
CURRENT_SSID=$(nmcli -t -f ACTIVE,SSID dev wifi | grep '^yes' | cut -d: -f2)
if [ "$CURRENT_SSID" == "$SSID" ]; then exit 0; fi

# BUSY CHECK
if [ -f "$LOCK" ]; then
    FILE_TIME=$(stat -c %Y "$LOCK")
    CURR_TIME=$(date +%s)
    AGE_MIN=$(( (CURR_TIME - FILE_TIME) / 60 ))
    if [ "$AGE_MIN" -lt "$MAX_AGE_MINUTES" ]; then
        echo "[$(date)] ⏳ FAILSAFE: System Busy ($AGE_MIN min). Skipping." >> "$LOG"
        exit 0
    else
        echo "[$(date)] ⚠️ FAILSAFE: Stale lock detected. Overriding." >> "$LOG"
        rm -f "$LOCK"
    fi
fi

# RECOVERY
echo "[$(date)] 🚑 FAILSAFE: Lost & Idle. Recovering..." >> "$LOG"
sudo nmcli dev set wlan0 managed no && sleep 2 && sudo nmcli dev set wlan0 managed yes
for uuid in $(nmcli -g UUID con show | grep -v "loopback"); do sudo nmcli con delete uuid "$uuid" >> "$LOG" 2>&1; done
sudo nmcli con add type wifi ifname wlan0 con-name "$SSID" ssid "$SSID"
sudo nmcli con modify "$SSID" wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$PASS"
sudo nmcli con up "$SSID" >> "$LOG" 2>&1