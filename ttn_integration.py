#!/usr/bin/env python3
"""
The Things Network Integration Module
Handles MQTT communication with TTN for uplink/downlink messages
Includes RSSI-based trilateration for device localization
"""

import paho.mqtt.client as mqtt
import json
import base64
import requests
import threading
import time
from datetime import datetime
from typing import Callable, Optional, Dict, Any, List
import logging
import math
from collections import defaultdict

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

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

# ============================================================================
# LOCALIZATION MODULE - RSSI to Distance and Trilateration
# ============================================================================

class AnchorPoint:
    """Represents a stationary node (anchor) with known position"""
    def __init__(self, node_id: str, name: str, x: float, y: float, z: float):
        self.node_id = node_id
        self.name = name
        self.x = x
        self.y = y
        self.z = z
    
    def position(self):
        """Return position as tuple or numpy array"""
        if HAS_NUMPY:
            return np.array([self.x, self.y, self.z])
        else:
            return (self.x, self.y, self.z)


class RSSIToDistance:
    """
    Converts RSSI (dBm) to estimated distance using Log-Distance Path Loss Model.
    
    Formula: distance = 10^((TX_POWER - RSSI) / (10 * n))
    Where:
    - TX_POWER: Transmit power at 1m reference (-40 dBm for LoRa)
    - RSSI: Measured signal strength (dBm)
    - n: Path loss exponent (2.0-4.0)
    """
    
    TX_POWER = -40          # dBm at 1m reference distance
    PATH_LOSS_EXPONENT = 2.5  # Indoor LoS path loss exponent
    MIN_DISTANCE = 0.5      # Minimum distance in meters
    MAX_DISTANCE = 50.0     # Maximum distance in meters
    
    @staticmethod
    def rssi_to_distance(rssi: int) -> float:
        """Convert RSSI to distance in meters"""
        if rssi >= 0:
            logger.warning(f"Invalid RSSI: {rssi} dBm (should be negative)")
            return RSSIToDistance.MIN_DISTANCE
        
        # Log-distance path loss formula
        # RSSI closer to 0 = nearer, more negative = farther
        # d = 10^((TX_POWER - RSSI) / (10 * n))
        path_loss = RSSIToDistance.TX_POWER - rssi
        distance = 10 ** (path_loss / (10 * RSSIToDistance.PATH_LOSS_EXPONENT))
        
        # Clamp to valid range
        distance = max(RSSIToDistance.MIN_DISTANCE, min(distance, RSSIToDistance.MAX_DISTANCE))
        return distance
    
    @staticmethod
    def calculate_confidence(rssi: int, distance: float) -> float:
        """Calculate measurement confidence (0.0-1.0)"""
        # RSSI confidence: -30 dBm (close) = 100%, -100 dBm (far) = 10%
        rssi_conf = max(0.0, min(1.0, (rssi + 100) / 70))
        
        # Distance confidence: optimal range 2-15m
        if distance < 2:
            dist_conf = 0.9 + (distance / 2) * 0.1
        elif distance <= 15:
            dist_conf = 1.0
        else:
            dist_conf = max(0.5, 1.0 - (distance - 15) / 35)
        
        # Combined confidence
        return rssi_conf * 0.6 + dist_conf * 0.4


class Trilateration:
    """Calculate device position from RSSI measurements using least-squares fitting"""
    
    MIN_ANCHORS = 3  # Need at least 3 anchors for 2D, 4 for accurate 3D
    
    @staticmethod
    def calculate_position(rssi_dict: Dict[str, int], 
                          anchors: Dict[str, AnchorPoint],
                          use_2d: bool = False) -> Optional[Dict[str, Any]]:
        """
        Calculate device position using weighted least-squares trilateration.
        
        Args:
            rssi_dict: Dict of {node_id: rssi_dBm}
            anchors: Dict of {node_id: AnchorPoint}
            use_2d: If True, assume device at fixed height (1.2m)
        
        Returns:
            Dict with position and metrics, or None if failed
        """
        if not HAS_NUMPY:
            logger.error("NumPy required for trilateration. Install: pip install numpy")
            return None
        
        # Filter valid measurements
        measurements = {}
        for node_id, rssi in rssi_dict.items():
            if node_id not in anchors:
                continue
            if rssi > -20 or rssi < -120:  # Valid RSSI range: -120 to -20 dBm
                continue
            
            distance = RSSIToDistance.rssi_to_distance(rssi)
            confidence = RSSIToDistance.calculate_confidence(rssi, distance)
            measurements[node_id] = {
                'distance': distance,
                'confidence': confidence,
                'rssi': rssi
            }
        
        if len(measurements) < Trilateration.MIN_ANCHORS:
            logger.warning(f"Insufficient measurements: {len(measurements)} (need {Trilateration.MIN_ANCHORS})")
            return None
        
        # Linearized trilateration by subtracting reference equation
        # Sphere eq: (x-xi)^2 + (y-yi)^2 + (z-zi)^2 = di^2
        # Subtracting eq_0 from eq_i eliminates the unknown x^2+y^2+z^2 term
        items = list(measurements.items())
        ref_node_id, ref_data = items[0]
        ref_anchor = anchors[ref_node_id]
        ref_dist_sq = ref_data['distance'] ** 2
        ref_anchor_sq = ref_anchor.x**2 + ref_anchor.y**2 + ref_anchor.z**2
        
        A = []
        b = []
        weights = []
        
        for node_id, data in items[1:]:
            anchor = anchors[node_id]
            di_sq = data['distance'] ** 2
            anchor_i_sq = anchor.x**2 + anchor.y**2 + anchor.z**2
            
            A.append([
                2 * (anchor.x - ref_anchor.x),
                2 * (anchor.y - ref_anchor.y),
                2 * (anchor.z - ref_anchor.z)
            ])
            b.append(di_sq - ref_dist_sq + ref_anchor_sq - anchor_i_sq)
            weights.append(data['confidence'])
        
        try:
            A = np.array(A, dtype=float)
            b = np.array(b, dtype=float)
            weights = np.array(weights, dtype=float)
            
            # Normalize weights
            weights = weights / np.sum(weights)
            W = np.diag(weights)
            
            # Solve weighted least-squares
            ATA = A.T @ W @ A
            ATb = A.T @ W @ b
            
            try:
                position = np.linalg.solve(ATA, ATb)
            except np.linalg.LinAlgError:
                position, _, _, _ = np.linalg.lstsq(A, b, rcond=None)
            
            x, y, z = float(position[0]), float(position[1]), float(position[2])
            
            # Lock z if 2D mode
            if use_2d:
                z = 1.2
            
            # Calculate residual error
            predicted_b = A @ position
            residuals = predicted_b - b
            rms_error = float(np.sqrt(np.mean(residuals ** 2)))
            
            # Confidence and accuracy
            avg_confidence = float(np.mean(weights))
            accuracy = max(0.3, avg_confidence * (1.0 - min(1.0, rms_error / 10)))
            
            return {
                'position': {'x': x, 'y': y, 'z': z},
                'residual_error': rms_error,
                'confidence': avg_confidence,
                'accuracy': accuracy,
                'num_measurements': len(measurements),
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Trilateration error: {e}")
            return None


# ============================================================================
# TTN MQTT CLIENT
# ============================================================================


class TTNClient:
    """The Things Network MQTT Client with integrated RSSI trilateration"""
    
    def __init__(self, on_message_callback: Optional[Callable] = None, 
                 anchors: Optional[Dict[str, AnchorPoint]] = None,
                 auto_localize: bool = True):
        """
        Initialize TTN Client
        
        Args:
            on_message_callback: Function to call when uplink message is received
            anchors: Dict of anchor points for trilateration
            auto_localize: If True, automatically calculate position when RSSI data is available
        """
        self.client = mqtt.Client(client_id="raspberry-pi-web-server")
        self.client.username_pw_set(TTN_USERNAME, TTN_PASSWORD)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect
        
        self.on_message_callback = on_message_callback
        self.connected = False
        self.thread = None
        self.lock = threading.RLock()
        
        # Localization setup
        self.anchors = anchors or self._get_default_anchors()
        self.auto_localize = auto_localize
        
        # Buffer to collect RSSI readings from multiple nodes
        # Format: {device_id: {node_id: rssi_value}}
        self.rssi_buffer = defaultdict(dict)
        self.rssi_timestamps = defaultdict(dict)
        
        # Localization results cache
        self.last_position = {}  # {device_id: {x, y, z}}
        
    def _get_default_anchors(self) -> Dict[str, AnchorPoint]:
        """Get default anchor positions for the facility"""
        return {
            'gateway': AnchorPoint('gateway', 'LoRaWAN Gateway (Center)', 15.0, 20.0, 2.5),
            'sn1': AnchorPoint('sn1', 'Stationary Node 1 (East)', 20.0, 20.0, 1.5),
            'sn2': AnchorPoint('sn2', 'Stationary Node 2 (Northwest)', 12.5, 24.33, 1.5),
            'sn3': AnchorPoint('sn3', 'Stationary Node 3 (Southwest)', 12.5, 15.67, 1.5)
        }
        
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
                        # Buffer RSSI from gateway
                        self._buffer_rssi(device_id, 'gateway', metadata['gateway_rssi'])
                        
                    elif payload_data['type'] == 'FORWARDED_RSSI':
                        logger.info(f"Forwarding Device: {device_id}")
                        logger.info(f"Original Device:   {payload_data['original_device_id']}")
                        logger.info(f"RSSI (P2P):        {payload_data['rssi']} dBm")
                        logger.info(f"RSSI (gateway):    {metadata['gateway_rssi']} dBm")
                        
                        # Buffer P2P RSSI from the forwarding node (sender)
                        original_device = payload_data['original_device_id']
                        self._buffer_rssi(original_device, device_id, payload_data['rssi'])
                        self._buffer_rssi(original_device, 'gateway', metadata['gateway_rssi'])
                        
                    elif payload_data['type'] == 'IMAGE':
                        logger.info(f"Image bytes received: {len(payload_data['image_data'])} bytes")
                    
                    if payload_data['type'] != 'FORWARDED_RSSI':
                        logger.info(f"Gateway RSSI: {metadata['gateway_rssi']} dBm")
                        logger.info(f"Gateway SNR: {metadata['gateway_snr']} dB")
                    logger.info("="*50)
                    
                    # Attempt localization if we have enough measurements
                    if self.auto_localize and payload_data['type'] in ['RSSI', 'FORWARDED_RSSI']:
                        target_device = payload_data.get('original_device_id', device_id) if payload_data['type'] == 'FORWARDED_RSSI' else device_id
                        location = self.localize_if_ready(target_device)
                        if location:
                            payload_data['calculated_position'] = location['position']
                    
                    # Call external callback if provided
                    if self.on_message_callback:
                        self.on_message_callback(device_id, payload_data, metadata)
                        
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
    
    def _buffer_rssi(self, device_id: str, node_id: str, rssi: int):
        """Buffer RSSI reading from a node"""
        if rssi is None or rssi <= -120 or rssi > 0:
            return
        
        with self.lock:
            self.rssi_buffer[device_id][node_id] = rssi
            self.rssi_timestamps[device_id][node_id] = datetime.now()
    
    def localize_if_ready(self, device_id: str, min_anchors: int = 3) -> Optional[Dict[str, Any]]:
        """
        Attempt trilateration if we have enough RSSI measurements
        
        Args:
            device_id: Device to localize
            min_anchors: Minimum anchors needed (3 for 2D, 4 for 3D)
        
        Returns:
            Localization result or None
        """
        with self.lock:
            rssi_data = self.rssi_buffer.get(device_id, {})
            
            if len(rssi_data) < min_anchors:
                return None
            
            # Perform trilateration
            result = Trilateration.calculate_position(rssi_data, self.anchors, use_2d=False)
            
            if result:
                self.last_position[device_id] = result['position']
                
                # Log result
                pos = result['position']
                logger.info(f"✓ LOCALIZED {device_id}: ({pos['x']:.2f}m, {pos['y']:.2f}m, {pos['z']:.2f}m) "
                           f"| Error: {result['residual_error']:.2f}m | Confidence: {result['confidence']:.1%}")
                
                # Clear old RSSI data
                self.rssi_buffer[device_id].clear()
                self.rssi_timestamps[device_id].clear()
                
                return result
            
            return None
    
    def get_last_position(self, device_id: str) -> Optional[Dict[str, float]]:
        """Get last calculated position for device"""
        with self.lock:
            return self.last_position.get(device_id)
    
    def get_rssi_buffer(self, device_id: str) -> Dict[str, int]:
        """Get current RSSI buffer for device"""
        with self.lock:
            return dict(self.rssi_buffer.get(device_id, {}))
    
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
    
    def set_anchors(self, anchors: Dict[str, AnchorPoint]):
        """Update anchor positions for trilateration"""
        with self.lock:
            self.anchors = anchors
            logger.info(f"Updated {len(anchors)} anchor positions for trilateration")
    
    def localize_device(self, device_id: str) -> Optional[Dict[str, Any]]:
        """
        Manually trigger localization for a device
        
        Returns:
            Localization result with position and metrics, or None if failed
        """
        return self.localize_if_ready(device_id, min_anchors=3)
    
    def get_localization_status(self, device_id: str) -> Dict[str, Any]:
        """Get current localization status for device"""
        with self.lock:
            rssi_count = len(self.rssi_buffer.get(device_id, {}))
            position = self.last_position.get(device_id)
            
            return {
                'device_id': device_id,
                'rssi_measurements': rssi_count,
                'ready_for_localization': rssi_count >= 3,
                'last_position': position,
                'rssi_values': dict(self.rssi_buffer.get(device_id, {}))
            }
    
    
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


def get_ttn_client(on_message_callback: Optional[Callable] = None,
                  anchors: Optional[Dict[str, AnchorPoint]] = None,
                  auto_localize: bool = True) -> TTNClient:
    """
    Get or create the global TTN client instance
    
    Args:
        on_message_callback: Optional callback for uplink messages
        anchors: Optional custom anchor points for trilateration
        auto_localize: If True, automatically localize when RSSI data available
        
    Returns:
        TTNClient instance
    """
    global _ttn_client_instance
    
    if _ttn_client_instance is None:
        _ttn_client_instance = TTNClient(
            on_message_callback=on_message_callback,
            anchors=anchors,
            auto_localize=auto_localize
        )
    
    return _ttn_client_instance


if __name__ == "__main__":
    # Test the TTN client with localization
    def test_callback(device_id, payload_data, metadata):
        print(f"\n[TEST] Received from {device_id}:")
        print(f"  Payload: {payload_data}")
        if 'calculated_position' in payload_data:
            pos = payload_data['calculated_position']
            print(f"  Position: ({pos['x']:.2f}m, {pos['y']:.2f}m, {pos['z']:.2f}m)")
        print(f"  Metadata: {metadata}")
    
    # Create client with localization enabled
    anchors = {
        'gateway': AnchorPoint('gateway', 'LoRaWAN Gateway', 15.0, 20.0, 2.5),
        'sn1': AnchorPoint('sn1', 'Anchor 1 (East)', 20.0, 20.0, 1.5),
        'sn2': AnchorPoint('sn2', 'Anchor 2 (NW)', 12.5, 24.33, 1.5),
        'sn3': AnchorPoint('sn3', 'Anchor 3 (SW)', 12.5, 15.67, 1.5)
    }
    
    client = TTNClient(on_message_callback=test_callback, anchors=anchors, auto_localize=True)
    client.start()
    
    print("TTN Client started with RSSI trilateration enabled")
    print(f"Anchors configured: {list(anchors.keys())}")
    
    # Keep running
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
        client.stop()
