#!/usr/bin/env python3
"""
Device Manager Module
Manages real-time device data using database as single source of truth
"""

import os
import threading
from datetime import datetime
from typing import Dict, List, Optional, Any
import io
import logging

# Import database functions
from database import (
    get_device,
    get_all_devices as db_get_all_devices,
    get_all_stationary_nodes as db_get_stationary_nodes,
    get_latest_rssi_with_timestamps,
    insert_device,
    update_device_location,
    update_device_battery,
    update_device_uplink,
    update_device_health,
    insert_rssi_reading,
    insert_device_image,
    get_latest_device_image,
    log_system_event
)

# Import localization functions
from localization import (
    get_default_anchors,
    localize_device as run_localization,
)

# Make Pillow optional - only used for image resolution detection
try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    logger = logging.getLogger(__name__)
    logger.warning("Pillow not installed - image resolution detection disabled")

logger = logging.getLogger(__name__)

# Anchors can report with moderate delay; keep guard against very stale mixes
# but allow realistic stagger across gateway/sn nodes.
MAX_RSSI_TIMESTAMP_SKEW_SECONDS = 12

# Facility dimensions (in meters)
FACILITY_WIDTH = 30
FACILITY_LENGTH = 40
FACILITY_HEIGHT = 5


class DeviceManager:
    """Manages device state using database as single source of truth"""
    
    def __init__(self, image_storage_path: str = 'static/images/captured'):
        """
        Initialize Device Manager
        
        Args:
            image_storage_path: Directory to store captured images
        """
        self.image_storage_path = image_storage_path
        self.lock = threading.RLock()
        
        # Create image storage directory
        os.makedirs(image_storage_path, exist_ok=True)
        
        # Count devices from database
        device_count = len(db_get_all_devices())
        logger.info(f"Device Manager initialized with {device_count} devices from database")
    
    def handle_uplink_message(self, device_id: str, payload_data: Dict[str, Any], metadata: Dict[str, Any]):
        """
        Process uplink message from TTN and persist to database
        
        Args:
            device_id: Device ID from TTN (can be end device or stationary node)
            payload_data: Parsed payload data
            metadata: Message metadata (RSSI, SNR, timestamp)
        """
        with self.lock:
            # Handle forwarded RSSI from stationary nodes
            if payload_data.get('type') == 'FORWARDED_RSSI':
                original_device_id = payload_data.get('original_device_id')
                rssi_value = payload_data.get('rssi')
                
                if original_device_id and rssi_value:
                    # Auto-create original device if it doesn't exist
                    if not get_device(original_device_id):
                        logger.info(f"Creating new device from forwarded RSSI: {original_device_id}")
                        new_device = {
                            'id': original_device_id,
                            'patient_name': original_device_id,
                            'room': 'Unknown',
                            'location': {'x': 0, 'y': 0, 'z': 0},
                            'battery_level': 0,
                            'status': 'unknown',
                            'wifi_capable': False,
                            'last_uplink': None,
                            'heart_rate': None,
                            'temperature': None,
                            'has_image': False
                        }
                        insert_device(new_device)
                    
                    # Map stationary node device_id to node_id (handle both sn-1 and sn-01 formats)
                    node_mapping = {
                        'sn-01': 'sn1', 'sn-1': 'sn1',
                        'sn-02': 'sn2', 'sn-2': 'sn2',
                        'sn-03': 'sn3', 'sn-3': 'sn3',
                        'gateway': 'gateway'
                    }
                    node_id = node_mapping.get(device_id, device_id)
                    
                    logger.info(f"Processing forwarded RSSI: device_id={device_id} -> node_id={node_id}, original={original_device_id}, rssi={rssi_value}")
                    
                    # Store RSSI in database
                    if insert_rssi_reading(original_device_id, node_id, rssi_value, metadata['timestamp']):
                        logger.info(f"Updated RSSI for {original_device_id} -> {node_id}: {rssi_value} dBm (forwarded by {device_id})")
                    else:
                        logger.warning(f"Failed to update RSSI for {original_device_id}")
                return  # Don't process further for forwarded messages
            
            # Ensure device exists in database (auto-create from TTN data)
            device = get_device(device_id)
            if not device:
                # Auto-create device from first TTN message
                logger.info(f"Creating new device from TTN: {device_id}")
                new_device = {
                    'id': device_id,
                    'patient_name': device_id,  # Use device_id as default name
                    'room': 'Unknown',
                    'location': {'x': 0, 'y': 0, 'z': 0},  # 0 placeholder until RSSI trilateration
                    'battery_level': 0,
                    'status': 'unknown',
                    'wifi_capable': False,
                    'last_uplink': None,
                    'heart_rate': None,
                    'temperature': None,
                    'has_image': False
                }
                if insert_device(new_device):
                    logger.info(f"✓ Auto-created device {device_id} from TTN data")
                    device = get_device(device_id)
                else:
                    logger.error(f"Failed to auto-create device {device_id}")
                    return
            
            # Update last uplink time in database
            update_device_uplink(device_id, metadata['timestamp'])
            
            # Update gateway RSSI if available
            if metadata.get('gateway_rssi'):
                insert_rssi_reading(device_id, 'gateway', metadata['gateway_rssi'], metadata['timestamp'])
            
            # Process payload based on type
            payload_type = payload_data.get('type')
            
            if payload_type == 'RSSI':
                # RSSI reading from device
                rssi_value = payload_data.get('rssi')
                if rssi_value:
                    insert_rssi_reading(device_id, 'gateway', rssi_value, metadata['timestamp'])
                    logger.info(f"Updated RSSI for {device_id}: {rssi_value} dBm")
            
            elif payload_type == 'IMAGE':
                # Image data received
                image_data = payload_data.get('image_data')
                if image_data:
                    self._save_device_image(device_id, image_data)
            
            elif payload_type == 'HEALTH':
                # Health metrics received
                heart_rate = payload_data.get('heart_rate')
                temperature = payload_data.get('temperature')
                update_device_health(device_id, heart_rate, temperature)
                logger.info(f"Updated health metrics for {device_id}: HR={heart_rate}, Temp={temperature}")
    
    def _save_device_image(self, device_id: str, image_data: bytes):
        """
        Save received image data to disk
        
        Args:
            device_id: Device ID
            image_data: Raw image bytes (JPEG)
        """
        try:
            # Generate filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{device_id}_{timestamp}.jpg"
            latest_filename = f"{device_id}_latest.jpg"
            
            filepath = os.path.join(self.image_storage_path, filename)
            latest_filepath = os.path.join(self.image_storage_path, latest_filename)
            
            # Save image
            with open(filepath, 'wb') as f:
                f.write(image_data)
            
            # Also save as "latest" for quick access
            with open(latest_filepath, 'wb') as f:
                f.write(image_data)
            
            # Update database
            resolution = self._get_image_resolution(latest_filepath)
            insert_device_image(device_id, latest_filepath, len(image_data), resolution)
            
            logger.info(f"✓ Image saved for {device_id}: {filename} ({len(image_data)} bytes)")
            
        except Exception as e:
            logger.error(f"Error saving image for {device_id}: {e}", exc_info=True)
    
    def update_rssi_reading(self, device_id: str, node_id: str, rssi: int):
        """
        Update RSSI reading for a specific device-node pair
        
        Args:
            device_id: Device ID
            node_id: Stationary node ID (gateway, sn1, sn2, sn3)
            rssi: RSSI value in dBm
        """
        timestamp = datetime.now().isoformat()
        if insert_rssi_reading(device_id, node_id, rssi, timestamp):
            logger.debug(f"Updated RSSI for {device_id} -> {node_id}: {rssi} dBm")
    
    def update_device_location(self, device_id: str, x: float, y: float, z: float):
        """
        Update device location (after trilateration)
        
        Args:
            device_id: Device ID
            x, y, z: Coordinates in meters
        """
        if update_device_location(device_id, x, y, z):
            logger.info(f"Updated location for {device_id}: ({x:.2f}, {y:.2f}, {z:.2f})")
    
    def update_battery_level(self, device_id: str, battery_level: int):
        """
        Update device battery level
        
        Args:
            device_id: Device ID
            battery_level: Battery percentage (0-100)
        """
        update_device_battery(device_id, battery_level)
    
    def get_all_devices(self) -> List[Dict[str, Any]]:
        """Get all devices from database"""
        return db_get_all_devices()
    
    def get_device_by_id(self, device_id: str) -> Optional[Dict[str, Any]]:
        """Get specific device by ID from database"""
        return get_device(device_id)
    
    def get_stationary_nodes(self) -> List[Dict[str, Any]]:
        """Get all stationary nodes from database"""
        return db_get_stationary_nodes()
    
    def get_device_image(self, device_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the latest image info for a device from database
        
        Args:
            device_id: Device ID
            
        Returns:
            Dict with image info or None if not available
        """
        img_data = get_latest_device_image(device_id)
        if img_data:
            image_path = img_data.get('image_path') or ''
            filename = os.path.basename(image_path) if image_path else f'{device_id}_latest.jpg'
            return {
                'url': f'/static/images/captured/{filename}',
                'timestamp': img_data['timestamp'],
                'size': f"{img_data['size_bytes'] / 1024:.1f} KB",
                'resolution': img_data.get('resolution', 'Unknown')
            }
        return None
    
    def _get_image_resolution(self, filepath: str) -> str:
        """Get image resolution"""
        if not HAS_PIL:
            return "Unknown"
        try:
            with Image.open(filepath) as img:
                return f"{img.width}x{img.height}"
        except Exception:
            return "Unknown"
    
    def calculate_relay_path(self, device_id: str) -> List[str]:
        """
        Calculate Wi-Fi relay path from device to gateway
        
        Args:
            device_id: Target device ID
            
        Returns:
            List of device IDs in relay path (including target and gateway)
        """
        device = get_device(device_id)
        if not device:
            return []

        gateway_rssi = device['rssi_readings'].get('gateway')
        if gateway_rssi and gateway_rssi > -70:
            return [device_id, 'gateway']

        relay_candidates = []
        all_devices = db_get_all_devices()

        for other_device in all_devices:
            other_id = other_device['id']
            if other_id == device_id or not other_device.get('wifi_capable'):
                continue

            other_gateway_rssi = other_device['rssi_readings'].get('gateway')
            if other_gateway_rssi and other_gateway_rssi > -70:
                distance = self._calculate_distance(
                    device['location'],
                    other_device['location']
                )
                if distance < 15:
                    relay_candidates.append({
                        'id': other_id,
                        'gateway_rssi': other_gateway_rssi,
                        'distance_to_target': distance
                    })

        relay_candidates.sort(key=lambda candidate: (-candidate['gateway_rssi'], candidate['distance_to_target']))

        if relay_candidates:
            relay_id = relay_candidates[0]['id']
            return [device_id, relay_id, 'gateway']

        return [device_id, 'gateway']
    
    def localize_device(self, device_id: str, use_2d: bool = False) -> Optional[Dict[str, Any]]:
        """
        Calculate device location using RSSI trilateration.
        
        Retrieves latest RSSI readings for the device from all anchor nodes,
        converts RSSI to distances, and performs weighted least-squares trilateration.
        
        Args:
            device_id: Device to localize
            use_2d: If True, assumes device at fixed height (1.2m)
        
        Returns:
            Dict with localization result:
            {
                'position': {'x': float, 'y': float, 'z': float},
                'residual_error': float,  # Fitting error in meters
                'confidence': float,      # 0.0-1.0
                'accuracy': float,        # Estimated accuracy
                'num_measurements': int,
                'timestamp': str
            }
            Returns None if localization fails
        """
        with self.lock:
            try:
                records = get_latest_rssi_with_timestamps(device_id)

                # Build RSSI map and timestamp map from latest anchor records.
                rssi_by_node = {}
                ts_by_node = {}
                for node_id, rec in records.items():
                    rssi = rec.get('rssi') if isinstance(rec, dict) else None
                    ts_raw = rec.get('timestamp') if isinstance(rec, dict) else None
                    if rssi is None:
                        continue
                    rssi_by_node[node_id] = rssi

                    ts_dt = None
                    if ts_raw:
                        try:
                            ts_dt = datetime.fromisoformat(ts_raw)
                        except Exception:
                            try:
                                ts_dt = datetime.strptime(ts_raw, '%Y-%m-%d %H:%M:%S')
                            except Exception:
                                ts_dt = None
                    ts_by_node[node_id] = ts_dt

                if not rssi_by_node:
                    logger.warning(f"No RSSI measurements found for {device_id}")
                    return None

                required_nodes = {'gateway', 'sn1', 'sn2', 'sn3'}
                missing = required_nodes - rssi_by_node.keys()
                if missing:
                    logger.warning(f"Cannot localize {device_id}: missing RSSI from {sorted(missing)}")
                    return None

                # Guard against mixed-time measurements. Using stale and fresh
                # anchors together can shift solutions in physically invalid ways.
                anchor_times = [ts_by_node.get(n) for n in required_nodes]
                if any(t is None for t in anchor_times):
                    logger.warning(f"Cannot localize {device_id}: missing valid timestamps for one or more anchors")
                    return None
                min_ts = min(anchor_times)
                max_ts = max(anchor_times)
                skew_seconds = (max_ts - min_ts).total_seconds()
                if skew_seconds > MAX_RSSI_TIMESTAMP_SKEW_SECONDS:
                    logger.warning(
                        f"Cannot localize {device_id}: anchor RSSI timestamps skewed by {skew_seconds:.1f}s (max {MAX_RSSI_TIMESTAMP_SKEW_SECONDS}s)"
                    )
                    return None

                result = run_localization(
                    device_id=device_id,
                    rssi_readings=rssi_by_node,
                    anchors=get_default_anchors(),
                    use_2d=use_2d,
                    filter_outliers=True
                )
                
                if result and result.get('is_reliable', False):
                    # Update device location in database
                    pos = result['position']
                    update_device_location(device_id, pos['x'], pos['y'], pos['z'])
                    logger.info(f"Updated {device_id} location via trilateration: ({pos['x']:.2f}, {pos['y']:.2f}, {pos['z']:.2f})")
                    
                    return result
                elif result and not result.get('is_reliable', False):
                    logger.warning(
                        f"Localization for {device_id} marked unreliable; skipping DB location update. "
                        f"Residual={result.get('residual_error', 'n/a')}, confidence={result.get('confidence', 'n/a')}"
                    )
                    return result
                else:
                    logger.warning(f"Trilateration failed for {device_id}")
                    return None
                
            except Exception as e:
                logger.error(f"Error localizing device {device_id}: {e}", exc_info=True)
                return None
    
    def _calculate_distance(self, loc1: Dict[str, float], loc2: Dict[str, float]) -> float:
        """Calculate Euclidean distance between two locations"""
        import math
        dx = loc1['x'] - loc2['x']
        dy = loc1['y'] - loc2['y']
        dz = loc1['z'] - loc2['z']
        return math.sqrt(dx*dx + dy*dy + dz*dz)


# Global singleton instance
_device_manager_instance: Optional[DeviceManager] = None


def get_device_manager(image_storage_path: str = 'static/images/captured') -> DeviceManager:
    """
    Get or create the global device manager instance
    
    Args:
        image_storage_path: Directory to store captured images
        
    Returns:
        DeviceManager instance
    """
    global _device_manager_instance
    
    if _device_manager_instance is None:
        _device_manager_instance = DeviceManager(image_storage_path)
    
    return _device_manager_instance
