# Arduino Codes

This folder contains the firmware for the **Sensor Nodes (SN)** and **End Devices (ED)** used in the LoRa-based localization system.

---

## Sensor Nodes (SN1, SN2, SN3)

**Hardware:** Arduino Uno + LoRa Shield (×3)

Sensor nodes act as **anchor nodes**. They listen for LoRa P2P wake-up signals from end devices, capture RSSI readings, and transmit the data back via LoRaWAN.

### Configuration

Each SN has a unique `DevEUI` and `AppKey` that must match the corresponding device registered on TTN (The Things Network).

| Node | DevEUI | AppKey |
|------|--------|--------|
| SN1 | `75 5D 07 D0 7E D5 B3 70` | `48 E3 C6 E4 30 90 3F AD B9 DA 4E 71 26 61 7F B8` |
| SN2 | `68 60 07 D0 7E D5 B3 70` | `32 5B 29 12 2D 82 18 AB DE 0C 13 30 3B FA A7 7B` |
| SN3 | `DF 61 07 D0 7E D5 B3 70` | `44 A0 1B 33 17 A8 6B 68 7B FD 53 3F A5 B7 23 15` |

### Setup

1. Open the corresponding `.ino` file (e.g. `SN1.ino`) in the Arduino IDE.
2. Verify the `DevEUI`, `AppKey`, and frequency settings match your TTN application.
3. Flash the sketch to the Arduino Uno.
4. Attach the LoRa Shield and power on the board.

---

## End Devices (ED1, ED2)

**Hardware:** Raspberry Pi 4 + Arduino Uno + LoRa Shield

End devices act as **trigger nodes**. They receive a LoRaWAN downlink command, switch to P2P mode to broadcast a wake-up signal (with their device ID), and then return to LoRaWAN mode.

### Configuration

Each ED has a unique `DevEUI`, `AppKey`, and `MY_DEVICE_ID`.

| Node | DevEUI | AppKey | Device ID |
|------|--------|--------|-----------|
| ED1 | `71 5D 07 D0 7E D5 B3 70` | `72 62 D1 80 02 75 D9 19 90 51 06 F9 28 3A B5 CE` | `0x01` |
| ED2 | `E0 61 07 D0 7E D5 B3 70` | `C6 48 A6 D4 BD 92 A5 1A 13 0A 43 64 95 FD CA 76` | `0x02` |

### Setup

1. Open the corresponding `.ino` file (e.g. `ED1.ino`) in the Arduino IDE.
2. Verify the `DevEUI`, `AppKey`, `MY_DEVICE_ID`, and frequency settings match your TTN application.
3. Flash the sketch to the Arduino Uno.
4. Attach the LoRa Shield, connect to the Raspberry Pi 4, and power on.

---

## Notes

- All devices operate on **915 MHz**.
- `AppEUI` is set to `00 00 00 00 00 00 00 00` for all devices.
- Ensure all devices are registered on TTN before powering on.
