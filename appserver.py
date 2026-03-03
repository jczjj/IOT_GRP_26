#!/usr/bin/env python3
import paho.mqtt.client as mqtt
import json
import base64
import requests

# Downlink configuration
TTN_APP_ID = "iot-sit-group26-project-2026"  # <-- Set your TTN Application ID
TTN_TARGET_DEVICE_ID = "ed-1"  # <-- Set the device to receive downlink
TTN_API_KEY = "NNSXS.HQ2B4OSKH4FH6TXYN22W4FVW7OKMNFBHFRTCP4Q.37CAHSZPPJNWJW4KZMCAELOQCSRRMVQZLR3MQYE3KWGDSRGWAOSQ"  # <-- Set your TTN API key (with downlink rights)
TTN_REGION = "au1"  # Change to your region (e.g., eu1, nam1, au1)

def send_downlink(payload_bytes, fport=1):
    """Send a downlink to another device via TTN HTTP API."""
    url = f"https://{TTN_REGION}.cloud.thethings.network/api/v3/as/applications/{TTN_APP_ID}/devices/{TTN_TARGET_DEVICE_ID}/down/push"
    headers = {
        "Authorization": f"Bearer {TTN_API_KEY}",
        "Content-Type": "application/json"
    }
    # Encode payload as base64
    payload_b64 = base64.b64encode(payload_bytes).decode()
    data = {
        "downlinks": [
            {
                "f_port": fport,
                "frm_payload": payload_b64,
                "priority": "NORMAL"
            }
        ]
    }
    try:
        resp = requests.post(url, headers=headers, json=data)
        print(f"Downlink sent: {resp.status_code} {resp.text}")
    except Exception as e:
        print(f"Error sending downlink: {e}")

# TTN Configuration
TTN_HOST = "au1.cloud.thethings.network"
TTN_PORT = 1883
TTN_USERNAME = "iot-sit-group26-project-2026@ttn"
TTN_PASSWORD = "NNSXS.HQ2B4OSKH4FH6TXYN22W4FVW7OKMNFBHFRTCP4Q.37CAHSZPPJNWJW4KZMCAELOQCSRRMVQZLR3MQYE3KWGDSRGWAOSQ"
TTN_DEVICE_ID = "group26"

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("✓ Connected to The Things Network")
        topic = f"v3/{TTN_USERNAME}/devices/+/up"
        client.subscribe(topic)
        print(f"✓ Subscribed to: {topic}")
    else:
        print(f"✗ Connection failed with code {rc}")

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())

        # Extract uplink data
        if 'uplink_message' in payload:
            uplink = payload['uplink_message']

            # Decode base64 payload as raw bytes
            if 'frm_payload' in uplink:
                encoded_data = uplink['frm_payload']
                raw_bytes = base64.b64decode(encoded_data)

                print("\n" + "="*50)
                print(f"📡 Message received from device")
                if len(raw_bytes) > 0:
                    payload_type = raw_bytes[0]
                    if payload_type == 0x01 and len(raw_bytes) == 3:
                        # RSSI is 2 bytes signed integer
                        rssi = int.from_bytes(
                            raw_bytes[1:3],
                            byteorder='big',
                            signed=True
                        )

                        print(f"Payload type: RSSI")
                        print(f"RSSI value received: {rssi} dBm")
                    elif payload_type == 0x02 and len(raw_bytes) > 1:
                        # Image payload
                        img_hex = raw_bytes[1:].hex()
                        print(f"Payload type: IMAGE\nImage bytes (hex): {img_hex}")
                    else:
                        print(f"Unknown or malformed payload: {raw_bytes.hex()}")
                else:
                    print("Empty payload received.")
                print(f"RSSI (from gateway): {uplink.get('rx_metadata', [{}])[0].get('rssi', 'N/A')} dBm")
                print(f"SNR: {uplink.get('rx_metadata', [{}])[0].get('snr', 'N/A')} dB")
                print("="*50)
    except Exception as e:
        print(f"Error processing message: {e}")

def on_disconnect(client, userdata, rc):
    if rc != 0:
        print(f"✗ Unexpected disconnection. Code: {rc}")
    else:
        print("✗ Disconnected from TTN")

# Create MQTT client
client = mqtt.Client(client_id="raspberry-pi-subscriber")
client.username_pw_set(TTN_USERNAME, TTN_PASSWORD)
client.on_connect = on_connect
client.on_message = on_message
client.on_disconnect = on_disconnect


if __name__ == "__main__":
    # Send downlink with payload 0x01 (hex)
    send_downlink(b"\x01")
    print("Connecting to The Things Network...")
    try:
        client.connect(TTN_HOST, TTN_PORT, 60)
        client.loop_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        client.disconnect()
    except Exception as e:
        print(f"Error: {e}")
