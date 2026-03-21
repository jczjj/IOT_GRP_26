# 🚀 Stable Asynchronous SDN (V12.4)
### *A Self-Healing, Multi-Hop Data Pipeline for Raspberry Pi*

## 📖 The Concept: "The Relay Race"
This project implements a **3 → 2 → 1 → 0** store-and-forward chain. Instead of all nodes connecting to a central router, each node performs a **"Pivot"** operation to bridge gaps in range or hardware limitations.

1. **Host:** A node creates a temporary WiFi hotspot.
2. **Handshake:** It waits for its neighbor to connect and upload data via `rsync`.
3. **Pivot:** Once the data is received, the node destroys its hotspot and "hunts" for the next node in the chain to pass the data forward.

---

## 🛠 Prerequisites
* **Hardware:** 4x Raspberry Pi (Zero 2W, Pi 4, or Pi 5).
* **OS:** Raspberry Pi OS (64-bit Lite preferred).
* **Software:** `python3`, `nmcli`, `rsync`, `flask`, `python-yaml`.
* **Network:** A local management WiFi (e.g., your laptop hotspot) for initial configuration and recovery.

---

## 📂 Project Structure
* `setup_env.sh`: Automates user creation, hardware permissions, and folder structures.
* `setup_ssh.sh`: Configures "Silent SSH" for passwordless node hopping.
* `sdn_config.yaml`: The master settings file (**User Input Required!**).
* `end_nodes/`: Contains the logic for the Source and Relay nodes (`agent_v12.4.py`, `pp_v12.4.sh`, `failsafe.sh`).
* `server/`: Contains the logic for the Node 0 Sink (`node0_anchor.sh`, `node0_monitor.py`, `node0_server.py`).

---

## 🚀 Step-by-Step Setup

### 1. Infrastructure Setup
Run this on **EVERY** Pi to create the `sdn_service` user and set hardware permissions (LoRa/Serial access):
```bash
sudo bash setup_env.sh
sudo su - sdn_service
```

### 2. Security & SSH
Run this on **EVERY** Pi to allow the nodes to talk to each other without passwords. Follow the prompts to exchange public keys:
```bash
bash setup_ssh.sh
```

### 3. Essential Configuration (USER ACTION REQUIRED) ⚠️
The system needs to know how to find your laptop for recovery. Edit `sdn_config.yaml` on every node:

```yaml
credentials:
  pc_ssid: "YOUR_LAPTOP_WIFI_NAME"  # <-- ENTER YOUR SSID
  pc_pass: "YOUR_WIFI_PASSWORD"     # <-- ENTER YOUR PASSWORD
...
```

### 4. Enable the Failsafe
Register the 15-minute watchdog to ensure you don't get locked out during testing:
```bash
(crontab -l 2>/dev/null; echo "*/2 * * * * /bin/bash /home/sdn_service/poc/python_script/failsafe.sh") | crontab -
```

---

## 🎮 Running a Test (3-2-1-0 Chain)

Start the nodes in order from **Destination** to **Source**:

### **Step 1: Node 0 (The Sink)**
This node hosts the final hotspot and the web dashboard.
```bash
sudo bash server/node0_anchor.sh & python3 server/node0_monitor.py & python3 server/node0_server.py & disown
```
*Connect your laptop to the `pi00pi00` hotspot and visit: `http://10.42.0.1:5000`*

### **Step 2: Nodes 1 & 2 (The Relays)**
Relays wipe their staging area and wait for data from the next node.
* **On Node 1:** `python3 end_nodes/agent_v12.4.py --sim 1 0`
* **On Node 2:** `python3 end_nodes/agent_v12.4.py --sim 2 0`

### **Step 3: Node 3 (The Source)**
This node triggers the entire chain.
```bash
# Prepare the payload
touch ~/poc/file_transfer/receive/gatita.png
touch ~/poc/file_transfer/receive/payload.lock

# Start the transmission
python3 end_nodes/agent_v12.4.py --sim 3 1
```

---

## 🛡️ Stability Features
* **Lock-Aware Execution:** Nodes use `/tmp/sdn_busy` to prevent the failsafe from interrupting active transfers.
* **Stale Lock Detection:** If a script crashes, the lock expires after 15 minutes, allowing the Pi to "come home" automatically.
* **Aggressive Recovery:** Fixes "Secrets Required" WiFi errors by automatically flushing and recreating corrupted network profiles.
* **Real-time Dashboard:** Node 0 automatically timestamps and archives received files, displaying them on a live-updating web gallery.

---

## 🔍 Monitoring
To watch the progress in real-time on any node:
```bash
tail -f /home/sdn_service/poc/python_script/production.log
```