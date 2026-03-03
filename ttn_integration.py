#!/usr/bin/env python3
"""
The Things Network Integration Module
Handles MQTT communication with TTN for uplink/downlink messages
"""

import paho.mqtt.client as mqtt
import json
import base64
import requests
import threading
import time
from datetime import datetime
from typing import Callable, Optional, Dict, Any
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# TTN Configuration
TTN_APP_ID = "iot-sit-group26-project-2026"
TTN_API_KEY = "NNSXS.HQ2B4OSKH4FH6TXYN22W4FVW7OKMNFBHFRTCP4Q.37CAHSZPPJNWJW4KZMCAELOQCSRRMVQZLR3MQYE3KWGDSRGWAOSQ"
TTN_REGION = "au1"
TTN_HOST = "au1.cloud.thethings.network"
TTN_PORT = 1883
TTN_USERNAME = "iot-sit-group26-project-2026@ttn"
TTN_PASSWORD = "NNSXS.HQ2B4OSKH4FH6TXYN22W4FVW7OKMNFBHFRTCP4Q.37CAHSZPPJNWJW4KZMCAELOQCSRRMVQZLR3MQYE3KWGDSRGWAOSQ"


class TTNClient:
    """The Things Network MQTT Client"""
    
    def __init__(self, on_message_callback: Optional[Callable] = None):
        """
        Initialize TTN Client
        
        Args:
            on_message_callback: Function to call when uplink message is received
                                 Signature: callback(device_id, payload_data, metadata)
        """
        self.client = mqtt.Client(client_id="raspberry-pi-web-server")
        self.client.username_pw_set(TTN_USERNAME, TTN_PASSWORD)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect
        
        self.on_message_callback = on_message_callback
        self.connected = False
        self.thread = None
        
    def _on_connect(self, client, userdata, flags, rc):
        """Callback when connected to TTN"""
        if rc == 0:
            self.connected = True
            logger.info("✓ Connected to The Things Network")
            topic = f"v3/{TTN_USERNAME}/devices/+/up"
            client.subscribe(topic)
            logger.info(f"✓ Subscribed to: {topic}")
        else:
            logger.error(f"✗ Connection failed with code {rc}")
            self.connected = False
    
    def _on_disconnect(self, client, userdata, rc):
        """Callback when disconnected from TTN"""
        self.connected = False
        if rc != 0:
            logger.warning(f"✗ Unexpected disconnection. Code: {rc}")
        else:
            logger.info("✗ Disconnected from TTN")
    
    def _on_message(self, client, userdata, msg):
        """Callback when uplink message is received"""
        try:
            payload = json.loads(msg.payload.decode())
            
            # Extract device ID from topic (v3/{app}@ttn/devices/{device_id}/up)
            topic_parts = msg.topic.split('/')
            device_id = topic_parts[3] if len(topic_parts) > 3 else "unknown"
            
            # Extract uplink data
            if 'uplink_message' in payload:
                uplink = payload['uplink_message']
                
                # Parse metadata
                metadata = {
                    'gateway_rssi': uplink.get('rx_metadata', [{}])[0].get('rssi', None),
                    'gateway_snr': uplink.get('rx_metadata', [{}])[0].get('snr', None),
                    'timestamp': datetime.now().isoformat(),
                    'raw_payload': payload
                }
                
                # Decode base64 payload
                if 'frm_payload' in uplink:
                    encoded_data = uplink['frm_payload']
                    raw_bytes = base64.b64decode(encoded_data)
                    
                    logger.info("="*50)
                    logger.info(f"📡 Message received from device: {device_id}")
                    
                    # Parse payload
                    payload_data = self._parse_payload(raw_bytes)
                    
                    logger.info(f"Payload type: {payload_data['type']}")
                    
                    if payload_data['type'] == 'RSSI':
                        logger.info(f"RSSI value: {payload_data['rssi']} dBm")
                    elif payload_data['type'] == 'FORWARDED_RSSI':
                        logger.info(f"Forwarding Device: {device_id}")
                        logger.info(f"Original Device:   {payload_data['original_device_id']}")
                        logger.info(f"RSSI (P2P):        {payload_data['rssi']} dBm")
                        logger.info(f"RSSI (gateway):    {metadata['gateway_rssi']} dBm")
                    elif payload_data['type'] == 'IMAGE':
                        logger.info(f"Image bytes received: {len(payload_data['image_data'])} bytes")
                    
                    if payload_data['type'] != 'FORWARDED_RSSI':
                        logger.info(f"Gateway RSSI: {metadata['gateway_rssi']} dBm")
                        logger.info(f"Gateway SNR: {metadata['gateway_snr']} dB")
                    logger.info("="*50)
                    
                    # Call external callback if provided
                    if self.on_message_callback:
                        self.on_message_callback(device_id, payload_data, metadata)
                        
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
    
    def _parse_payload(self, raw_bytes: bytes) -> Dict[str, Any]:
        """
        Parse the payload based on first byte (payload type)
        
        Payload Types:
            0x01 (3 bytes): RSSI reading - type + 2 bytes signed int
            0x01 (4 bytes): Forwarded RSSI - type + device_id_byte + 2 bytes signed int
            0x02: Image data (1 byte type + N bytes image)
            0x03: Health metrics (type + heart_rate + temperature)
            0x04: Forwarded RSSI with string device ID (type + length + device_id + rssi)
        """
        if len(raw_bytes) == 0:
            return {'type': 'EMPTY'}
        
        payload_type = raw_bytes[0]
        
        # RSSI payload with type 0x01
        if payload_type == 0x01:
            # Incomplete payload (only 2 bytes)
            if len(raw_bytes) == 2:
                logger.warning(f"Incomplete RSSI payload: only {len(raw_bytes)} bytes, expected 3 or 4")
                return {
                    'type': 'UNKNOWN',
                    'raw_hex': raw_bytes.hex(),
                    'error': 'Incomplete RSSI payload'
                }
            # Direct RSSI: 3 bytes (type + 2 bytes RSSI)
            elif len(raw_bytes) == 3:
                rssi = int.from_bytes(raw_bytes[1:3], byteorder='big', signed=True)
                return {
                    'type': 'RSSI',
                    'rssi': rssi
                }
            # Forwarded RSSI: 4 bytes (type + device_id_byte + 2 bytes RSSI)
            elif len(raw_bytes) == 4:
                device_id_byte = raw_bytes[1]
                rssi = int.from_bytes(raw_bytes[2:4], byteorder='big', signed=True)
                # Convert device byte to device ID string (0x01 -> "ed-1", 0x02 -> "ed-2", etc.)
                original_device_id = f"ed-{device_id_byte}"
                return {
                    'type': 'FORWARDED_RSSI',
                    'original_device_id': original_device_id,
                    'device_id_byte': device_id_byte,
                    'rssi': rssi
                }
            else:
                logger.warning(f"Unexpected RSSI payload length: {len(raw_bytes)} bytes")
                return {
                    'type': 'UNKNOWN',
                    'raw_hex': raw_bytes.hex(),
                    'error': f'Unexpected length for type 0x01: {len(raw_bytes)} bytes'
                }
        
        # Forwarded RSSI payload (alternative format with string device ID)
        # Format: 0x04 + device_id_length (1 byte) + device_id (N bytes) + rssi (2 bytes)
        elif payload_type == 0x04 and len(raw_bytes) >= 4:
            device_id_length = raw_bytes[1]
            if len(raw_bytes) >= 2 + device_id_length + 2:
                original_device_id = raw_bytes[2:2+device_id_length].decode('ascii', errors='ignore')
                rssi = int.from_bytes(
                    raw_bytes[2+device_id_length:2+device_id_length+2],
                    byteorder='big',
                    signed=True
                )
                return {
                    'type': 'FORWARDED_RSSI',
                    'original_device_id': original_device_id,
                    'rssi': rssi
                }
        
        # Image payload
        elif payload_type == 0x02 and len(raw_bytes) > 1:
            return {
                'type': 'IMAGE',
                'image_data': raw_bytes[1:]
            }
        
        # Health metrics payload (example: 0x03 + 1 byte heart_rate + 2 bytes temp*10)
        elif payload_type == 0x03 and len(raw_bytes) >= 4:
            heart_rate = raw_bytes[1]
            temp_raw = int.from_bytes(raw_bytes[2:4], byteorder='big', signed=False)
            temperature = temp_raw / 10.0
            return {
                'type': 'HEALTH',
                'heart_rate': heart_rate,
                'temperature': temperature
            }
        
        # Unknown payload
        else:
            return {
                'type': 'UNKNOWN',
                'raw_hex': raw_bytes.hex()
            }
    
    def send_downlink(self, device_id: str, payload_bytes: bytes, fport: int = 1) -> bool:
        """
        Send a downlink message to a specific device
        
        Args:
            device_id: TTN device ID (e.g., 'ed-1', 'ed-2')
            payload_bytes: Raw bytes to send
            fport: LoRaWAN port number (default: 1)
            
        Returns:
            True if successful, False otherwise
        """
        url = f"https://{TTN_REGION}.cloud.thethings.network/api/v3/as/applications/{TTN_APP_ID}/devices/{device_id}/down/push"
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
            resp = requests.post(url, headers=headers, json=data, timeout=10)
            if resp.status_code in [200, 202]:
                logger.info(f"✓ Downlink sent to {device_id}: {resp.status_code}")
                return True
            else:
                logger.error(f"✗ Downlink failed for {device_id}: {resp.status_code} {resp.text}")
                return False
        except Exception as e:
            logger.error(f"✗ Error sending downlink to {device_id}: {e}")
            return False
    
    def send_image_capture_command(self, device_id: str) -> bool:
        """
        Send command to device to capture and transmit image
        Payload: 0x01 (IMG_CAPTURE command)
        """
        logger.info(f"Sending image capture command to {device_id}")
        return self.send_downlink(device_id, b"\x01", fport=2)
    
    def send_location_request_command(self, device_id: str) -> bool:
        """
        Send command to device to broadcast RSSI ping to all stationary nodes
        Payload: 0x01 (LOCATION_REQUEST command)
        """
        logger.info(f"Sending location request command to {device_id}")
        return self.send_downlink(device_id, b"\x01", fport=1)
    
    def send_wifi_hotspot_command(self, device_id: str, enable: bool, static_ip: str = "") -> bool:
        """
        Send command to device to enable/disable Wi-Fi hotspot
        Payload: 0x03 (WIFI_HOTSPOT command) + 0x01/0x00 (enable/disable) + IP address bytes
        """
        payload = bytearray([0x03, 0x01 if enable else 0x00])
        
        if enable and static_ip:
            # Add static IP as 4 bytes (e.g., "192.168.1.50" -> [192, 168, 1, 50])
            ip_parts = [int(part) for part in static_ip.split('.')]
            payload.extend(ip_parts)
        
        logger.info(f"Sending Wi-Fi {'enable' if enable else 'disable'} command to {device_id}")
        return self.send_downlink(device_id, bytes(payload), fport=2)
    
    def start(self):
        """Start the MQTT client in a background thread"""
        if self.thread and self.thread.is_alive():
            logger.warning("TTN client already running")
            return
        
        def run():
            logger.info("Starting TTN MQTT client...")
            try:
                self.client.connect(TTN_HOST, TTN_PORT, 60)
                self.client.loop_forever()
            except Exception as e:
                logger.error(f"Error in TTN client: {e}")
                self.connected = False
        
        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()
        
        # Wait for connection
        timeout = 10
        start_time = time.time()
        while not self.connected and (time.time() - start_time) < timeout:
            time.sleep(0.5)
        
        if self.connected:
            logger.info("✓ TTN client started successfully")
        else:
            logger.error("✗ TTN client failed to connect within timeout")
    
    def stop(self):
        """Stop the MQTT client"""
        if self.client:
            self.client.disconnect()
            logger.info("TTN client stopped")
    
    def is_connected(self) -> bool:
        """Check if client is connected to TTN"""
        return self.connected


# Global singleton instance
_ttn_client_instance: Optional[TTNClient] = None


def get_ttn_client(on_message_callback: Optional[Callable] = None) -> TTNClient:
    """
    Get or create the global TTN client instance
    
    Args:
        on_message_callback: Optional callback for uplink messages
        
    Returns:
        TTNClient instance
    """
    global _ttn_client_instance
    
    if _ttn_client_instance is None:
        _ttn_client_instance = TTNClient(on_message_callback)
    
    return _ttn_client_instance


if __name__ == "__main__":
    # Test the TTN client standalone
    def test_callback(device_id, payload_data, metadata):
        print(f"\n[TEST] Received from {device_id}:")
        print(f"  Payload: {payload_data}")
        print(f"  Metadata: {metadata}")
    
    client = TTNClient(on_message_callback=test_callback)
    client.start()
    
    # Keep running
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
        client.stop()
