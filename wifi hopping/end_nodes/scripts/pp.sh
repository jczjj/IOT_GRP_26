#!/bin/bash
# VERSION: 15.3 (Rebranded Receive)
MODE=$1; MY_ID=$2; TARGET_ID=$3; HOME_SSID=$4; HOME_PASS=$5; LOG=$6

RX_DIR="/home/sdn_service/poc/file_transfer/receive"
TARGET_SSID="pi0${TARGET_ID}pi0${TARGET_ID}"
TARGET_PASS="$TARGET_SSID"
TARGET_IP="10.42.${TARGET_ID}.1"
MY_SSID="pi0${MY_ID}pi0${MY_ID}"

[ "$TARGET_ID" == "0" ] && { TARGET_SSID="pi00pi00"; TARGET_PASS="pi00pi00"; }

purge_wifi() {
    for uuid in $(nmcli -g UUID,NAME con show | grep -E "pi0|LOQ" | cut -d: -f1); do
        sudo nmcli con delete uuid "$uuid" > /dev/null 2>&1
    done
}

if [ "$MODE" == "HOST" ]; then
    echo "[$(date)] 📥 RECEIVER | Hosting: $MY_SSID" >> "$LOG"
    purge_wifi
    sudo nmcli con add type wifi ifname wlan0 con-name "$MY_SSID" autoconnect yes ssid "$MY_SSID" mode ap ipv4.method shared ipv4.addresses 10.42.${MY_ID}.1/24 >> "$LOG" 2>&1
    sudo nmcli con modify "$MY_SSID" wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$MY_SSID" >> "$LOG" 2>&1
    sudo nmcli con up "$MY_SSID" >> "$LOG" 2>&1

elif [ "$MODE" == "PIVOT" ]; then
    echo "[$(date)] 🚀 SENDER | Hunting: $TARGET_SSID" >> "$LOG"
    
    CONNECTED=false
    for ((i=1; i<=5; i++)); do
        purge_wifi
        sudo nmcli con add type wifi ifname wlan0 con-name "$TARGET_SSID" ssid "$TARGET_SSID" >> "$LOG" 2>&1
        sudo nmcli con modify "$TARGET_SSID" wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$TARGET_PASS" >> "$LOG" 2>&1
        if sudo nmcli con up "$TARGET_SSID" >> "$LOG" 2>&1; then
            CONNECTED=true; break
        fi
        sleep 5
    done

    if [ "$CONNECTED" = true ]; then
        sleep 2
        for ((j=1; j<=3; j++)); do
            if ping -c 1 -W 2 "$TARGET_IP" > /dev/null; then
                if rsync -avz --timeout=15 "$RX_DIR/" sdn_service@"$TARGET_IP":"$RX_DIR/" >> "$LOG" 2>&1; then
                    echo "[$(date)] ✅ RSYNC SUCCESSFUL" >> "$LOG"
                    break
                fi
            fi
            sleep 3
        done
    fi
    
    # RECOVERY
    echo "[$(date)] 🏠 MISSION END: Returning to $HOME_SSID" >> "$LOG"
    sudo nmcli dev set wlan0 managed no && sleep 1 && sudo nmcli dev set wlan0 managed yes
    sudo nmcli con add type wifi ifname wlan0 con-name "$HOME_SSID" ssid "$HOME_SSID" >> "$LOG" 2>&1
    sudo nmcli con modify "$HOME_SSID" wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$HOME_PASS" >> "$LOG" 2>&1
    sudo nmcli con up "$HOME_SSID" >> "$LOG" 2>&1
fi
