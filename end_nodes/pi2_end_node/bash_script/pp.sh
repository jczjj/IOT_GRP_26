#!/bin/bash
# VERSION: 8.1 (Node - Guaranteed Reconnect)
PC_SSID="LOQ15_7071"
PC_PASS="section4"
TARGET_SSID="pi_01pi_01"
TARGET_PASS="pi_01pi_01"
LOG="/home/lly_pi2/poc/python_script/test_evidence.log"
FILE_PATH="/home/lly_pi2/gatita.png"

echo "[$(date)] --- PI 2 NODE START (V8.1) ---" > "$LOG"

# --- STAGE 1: THE PIVOT (Away from PC) ---
echo "[$(date)] Purging profiles and joining Pi 1..." >> "$LOG"
for uuid in $(nmcli -g UUID,NAME con show | grep -E "pi_|$PC_SSID" | cut -d: -f1); do 
    sudo nmcli con delete uuid "$uuid" >> "$LOG" 2>&1
done

sudo nmcli con add type wifi ifname wlan0 con-name "$TARGET_SSID" ssid "$TARGET_SSID" >> "$LOG" 2>&1
sudo nmcli con modify "$TARGET_SSID" wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$TARGET_PASS" 802-11-wireless-security.psk-flags 0 >> "$LOG" 2>&1
sudo nmcli con up "$TARGET_SSID" >> "$LOG" 2>&1

# --- STAGE 2: THE MISSION (File Push) ---
if [ $? -eq 0 ]; then
    sleep 5
    if [ -f "$FILE_PATH" ]; then
        echo "[$(date)] Pushing file..." >> "$LOG"
        sshpass -p "lly_pi" rsync -avz "$FILE_PATH" lly_pi@10.42.1.1:~/received_data/ >> "$LOG" 2>&1
    else
        echo "[$(date)] ERROR: File missing" >> "$LOG"
    fi
else
    echo "[$(date)] ERROR: Failed to connect to Pi 1" >> "$LOG"
fi

# --- STAGE 3: THE RETURN (Guaranteed) ---
# This part now runs NO MATTER WHAT happened above.
echo "[$(date)] Returning to PC Hotspot ($PC_SSID)..." >> "$LOG"

# Clean up the Pi 1 profile so it doesn't conflict later
sudo nmcli con delete "$TARGET_SSID" >> "$LOG" 2>&1

# Re-add and Up the PC connection
sudo nmcli con add type wifi ifname wlan0 con-name "$PC_SSID" ssid "$PC_SSID" >> "$LOG" 2>&1
sudo nmcli con modify "$PC_SSID" wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$PC_PASS" >> "$LOG" 2>&1
sudo nmcli con up "$PC_SSID" >> "$LOG" 2>&1

if [ $? -eq 0 ]; then
    echo "[$(date)] BACK ONLINE: Connected to Laptop." >> "$LOG"
else
    echo "[$(date)] CRITICAL: Failed to return to Laptop!" >> "$LOG"
fi
