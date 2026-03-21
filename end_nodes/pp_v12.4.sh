#!/bin/bash
# VERSION: 12.4 (Universal Engine)
MODE=$1; MY_ID=$2; TARGET_ID=$3; PC_SSID=$4; PC_PASS=$5; RECOVERY=$6; RECEIVE_DIR=$7; LOG=$8

# Set lock
touch /tmp/sdn_busy

MY_SSID="pi0${MY_ID}pi0${MY_ID}"
TARGET_SSID="pi0${TARGET_ID}pi0${TARGET_ID}"
TARGET_PASS="$TARGET_SSID"
TARGET_IP="10.42.${TARGET_ID}.1"
[ "$TARGET_ID" == "0" ] && { TARGET_SSID="$PC_SSID"; TARGET_PASS="$PC_PASS"; }

purge_wifi() {
    echo "[$(date)] 🧹 Clearing old profiles..." >> "$LOG"
    for uuid in $(nmcli -g UUID,NAME con show | grep -E "pi0|LOQ" | cut -d: -f1); do 
        sudo nmcli con delete uuid "$uuid" >> "$LOG" 2>&1
    done
}

if [ "$MODE" == "HOST" ]; then
    echo "[$(date)] 📡 HOSTING: $MY_SSID" >> "$LOG"
    purge_wifi
    sudo nmcli con add type wifi ifname wlan0 con-name "$MY_SSID" autoconnect yes ssid "$MY_SSID" mode ap ipv4.method shared ipv4.addresses 10.42.${MY_ID}.1/24 >> "$LOG" 2>&1
    sudo nmcli con modify "$MY_SSID" wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$MY_SSID" >> "$LOG" 2>&1
    sudo nmcli con up "$MY_SSID" >> "$LOG" 2>&1
    # Lock is NOT released here; Agent handles it after file arrival.

elif [ "$MODE" == "PIVOT" ]; then
    echo "[$(date)] 🚀 PIVOTING: Hunting for $TARGET_SSID..." >> "$LOG"
    purge_wifi
    MAX_RETRIES=10; CONNECTED=false
    for ((i=1; i<=MAX_RETRIES; i++)); do
        sudo nmcli con add type wifi ifname wlan0 con-name "$TARGET_SSID" ssid "$TARGET_SSID" >> "$LOG" 2>&1
        sudo nmcli con modify "$TARGET_SSID" wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$TARGET_PASS" >> "$LOG" 2>&1
        sudo nmcli con up "$TARGET_SSID" >> "$LOG" 2>&1
        if [ $? -eq 0 ]; then CONNECTED=true; break; fi
        sudo nmcli con delete "$TARGET_SSID" >> "$LOG" 2>&1; sleep 8
    done

    if [ "$CONNECTED" = false ]; then
        rm -f /tmp/sdn_busy
        /bin/bash /home/sdn_service/poc/python_script/failsafe.sh; exit 1
    fi

    echo "[$(date)] 📦 RSYNC: Pushing to $TARGET_IP" >> "$LOG"
    rsync -e "ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 -o BatchMode=yes" -avz "${RECEIVE_DIR}/" sdn_service@"$TARGET_IP":"$RECEIVE_DIR" >> "$LOG" 2>&1

    if [ "$RECOVERY" == "true" ]; then
        echo "[$(date)] 🏠 FORCING HOME RECOVERY..." >> "$LOG"
        rm -f /tmp/sdn_busy
        sudo nmcli dev set wlan0 managed no && sleep 2 && sudo nmcli dev set wlan0 managed yes
        sudo nmcli con delete "$PC_SSID" >> "$LOG" 2>&1
        sudo nmcli con add type wifi ifname wlan0 con-name "$PC_SSID" ssid "$PC_SSID" >> "$LOG" 2>&1
        sudo nmcli con modify "$PC_SSID" wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$PC_PASS" >> "$LOG" 2>&1
        sudo nmcli con up "$PC_SSID" >> "$LOG" 2>&1
        exit 0
    fi
    rm -f /tmp/sdn_busy
fi