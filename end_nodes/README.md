# 🛰️ SDN Stateless Node Orchestrator (V9.1)

A modular, event-driven orchestration layer for Raspberry Pi nodes in a **Store & Forward** Software-Defined Network (SDN). This system enables "True Statelessness"—nodes remain "blank slates" until they receive a LoRa-injected mission from the controller.

## 🚀 Key Features
* **True Statelessness:** Node identity, mission role (Origin/Relay), and network targets are defined at runtime via LoRa triggers.
* **Modular Architecture:** Clean separation between the **Python Brain** (logic), **Bash Tools** (OS actions), and **Arduino Firmwares** (radio bridge).
* **Algorithmic Networking:** Deterministic SSID/Password generation based on node hierarchy (Target = Node $n - 1$).
* **Atomic Networking:** Dedicated scripts for "Pivoting" to mission networks and "Recovering" to the management/laptop hotspot.
* **Unified Logging:** Chronological mission tracking across all sub-modules stored in a single `sdn_mission.log`.

---

## 📂 Directory Structure
```text
sdn_agent/
├── main_agent.py          # The Brain: Manages the State Machine
├── sdn_mission.log        # Unified Log (Generated)
├── modules/               # The Specialists
│   ├── __init__.py        # Python package marker
│   ├── lora_handler.py    # The Ear: Radio Parser (Hex/Binary Opcode)
│   ├── network_manager.py # The Hands: OS Networking Interface
│   └── transfer_tool.py   # The Mover: Data Logistics (rsync/http)
└── scripts/               # Atomic Bash Tools
    ├── wifi_pivot.sh      # Drops management Wi-Fi -> Joins Mission Network
    └── wifi_return.sh     # Wipes mission networks -> Returns Home (Laptop)