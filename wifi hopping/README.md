# 🛰️ SDN Store-and-Forward: End Node Setup Guide
### Project: IOT_GRP_26 - Energy-Aware Multi-Hop Networking (CSC 2106)

This repository contains the implementation of an energy-aware communication system for elderly monitoring. The system uses **LoRa** for low-power status updates and trilateration, while triggering high-power **WiFi** only when a data transfer (e.g., image payload) is required and feasible.

---

## 📂 Directory Structure
The system is designed to run under the `sdn_service` user on a Raspberry Pi. The directory structure must be strictly followed to ensure script paths and YAML configurations align:

```text
~/poc/
├── end_nodes/
│   ├── arduino/          # LoRa Shield source code (arduino.ino)
│   ├── file_transfer/
│   │   ├── image_src/    # Source images for transfer (e.g., gatita.png)
│   │   └── receive/      # Staging area for incoming/outgoing rsync
│   └── scripts/          # Core SDN logic and configuration
│       ├── agent.py      # Python Supervisor (LoRa Listener)
│       ├── pp.sh         # Network Engine (WiFi Switching/rsync)
│       ├── failsafe.sh   # Recovery Safety Net
│       ├── sdn_config.yaml
│       └── production.log
└── server/               # Gateway/Node 0 logic (Reference only)
    ├── node0_anchor.sh
    └── node0_monitor.py
```

---

## 🛠️ 1. Environment Preparation

### **User & Permissions**
Create a dedicated service user and grant access to the serial hardware (dialout group):
```bash
sudo adduser sdn_service
sudo usermod -aG sudo,dialout sdn_service
su - sdn_service
```

### **Dependencies**
Install the necessary networking and Python packages:
```bash
sudo apt update && sudo apt install -y python3-pip rsync network-manager
pip3 install pyserial pyyaml
```

### **Initialize Directories**
Clone the repository or manually create the following structure:
```bash
mkdir -p ~/poc/end_nodes/file_transfer/image_src
mkdir -p ~/poc/end_nodes/file_transfer/receive
mkdir -p ~/poc/end_nodes/scripts
```

---

## 🔑 2. SSH Key Handshake (Passwordless rsync)
The system requires passwordless SSH access to move files to the **Central Server (Node 0)** or between nodes.

1. **Generate the RSA Key:**
   ```bash
   ssh-keygen -t rsa -b 4096 -N "" -f ~/.ssh/id_rsa
   ```
2. **Distribute to Gateway/Target:**
   Assuming the Gateway (Node 0) is at `10.42.0.1`:
   ```bash
   ssh-copy-id sdn_service@10.42.0.1
   ```
   *Verify with `ssh sdn_service@10.42.0.1` to ensure no password prompt appears.*

---

## ⚙️ 3. Configuration (`sdn_config.yaml`)
Ensure your configuration file is located at `~/poc/end_nodes/scripts/sdn_config.yaml`. Update the `home_ssid` to your laptop/base station credentials.

```yaml
paths:
  engine_path: "/home/sdn_service/poc/end_nodes/scripts/pp.sh"
  receive_dir: "/home/sdn_service/poc/end_nodes/file_transfer/receive"
  source_dir: "/home/sdn_service/poc/end_nodes/file_transfer/image_src"
  payload_file: "gatita.png"
  lock_file: "sdn.lock"
  log_file: "/home/sdn_service/poc/end_nodes/scripts/production.log"

credentials:
  home_ssid: "YOUR_SSID_HERE"
  home_pass: "YOUR_PASSWORD_HERE"

timeouts:
  mission_max: 300   # 5-minute global mission limit
  command_max: 120   # 2-minute bash command limit
  hardware_wait: 60  # Startup delay for USB discovery
```

---

## 🚀 4. Deployment & Automation

### **Set Permissions**
All scripts must be executable for the system to function:
```bash
cd ~/poc/end_nodes/scripts/
chmod +x agent.py failsafe.sh pp.sh
```

### **Setup Crontab**
Automate the **Failsafe** recovery and the **Agent** startup. Run `crontab -e` and add:

```bash
# RECOVERY: Reconnect to laptop if system is lost/idle every minute
* * * * * /home/sdn_service/poc/end_nodes/scripts/failsafe.sh

# STARTUP: Launch Agent on boot with hardware patience
@reboot /usr/bin/python3 /home/sdn_service/poc/end_nodes/scripts/agent.py >> /home/sdn_service/poc/end_nodes/scripts/startup_debug.log 2>&1
```

---

## 📡 5. Hardware Interface (Arduino/LoRa)
1. The Arduino Uno + LoRa Shield acts as the communication trigger.
2. Flash the code found in `~/poc/end_nodes/arduino/arduino.ino`.
3. Connect the Arduino via USB. The `agent.py` script will automatically scan for `/dev/ttyUSB0` or `/dev/ttyACM0`.
4. Ensure the baud rate is set to **9600** in both the Arduino code and `agent.py`.

---

## 📊 Monitoring & Logs
To verify the system is running correctly, monitor the following logs:

```bash
# Watch the live SDN Agent mission logs
tail -f ~/poc/end_nodes/scripts/production.log

# Check for boot-time errors or hardware detection issues
cat ~/poc/end_nodes/scripts/startup_debug.log
```

## 🛡️ Failsafe & Retry Logic
- **Mission Timeout:** If a Relay node does not receive data within `mission_max` seconds, it releases the `/tmp/sdn_busy` lock and aborts.
- **Command Guard:** If `rsync` or `nmcli` hangs, the system kills the process after `command_max` seconds.
- **Failsafe:** The minute-by-minute cronjob detects if the node is "Idle" (no `/tmp/sdn_busy` file) and not connected to the "Home" WiFi. If both are true, it nukes mission profiles and forces a reconnection to the base station.