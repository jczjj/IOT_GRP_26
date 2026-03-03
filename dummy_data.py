"""
Dummy Data Module for Testing
This simulates the data that will come from the LoRa network and RSSI trilateration
"""

from datetime import datetime, timedelta
import random

# Simulated facility dimensions (in meters)
FACILITY_WIDTH = 30  # meters
FACILITY_LENGTH = 40  # meters
FACILITY_HEIGHT = 5  # meters

# Stationary nodes at fixed, known coordinates
STATIONARY_NODES = [
    {
        'id': 'gateway',
        'name': 'LoRaWAN Gateway',
        'type': 'gateway',
        'location': {
            'x': 15.0,  # Center of facility
            'y': 20.0,
            'z': 3.0   # Ceiling mounted
        },
        'status': 'online',
        'last_seen': datetime.now().isoformat()
    },
    {
        'id': 'sn1',
        'name': 'Stationary Node 1',
        'type': 'anchor',
        'location': {
            'x': 5.0,   # Corner 1
            'y': 5.0,
            'z': 2.5
        },
        'status': 'online',
        'last_seen': datetime.now().isoformat()
    },
    {
        'id': 'sn2',
        'name': 'Stationary Node 2',
        'type': 'anchor',
        'location': {
            'x': 25.0,  # Corner 2
            'y': 5.0,
            'z': 2.5
        },
        'status': 'online',
        'last_seen': datetime.now().isoformat()
    },
    {
        'id': 'sn3',
        'name': 'Stationary Node 3',
        'type': 'anchor',
        'location': {
            'x': 15.0,  # Back wall
            'y': 35.0,
            'z': 2.5
        },
        'status': 'online',
        'last_seen': datetime.now().isoformat()
    }
]

# Simulated end devices (patient wearables)
END_DEVICES = [
    {
        'id': 'device_001',
        'patient_name': 'Margaret Smith',
        'room': '101',
        'location': {
            'x': 8.5,
            'y': 12.0,
            'z': 1.2  # Wrist height
        },
        'rssi_readings': {
            'gateway': -65,
            'sn1': -58,
            'sn2': -78,
            'sn3': -82
        },
        'battery_level': 87,
        'status': 'active',
        'wifi_capable': True,
        'last_uplink': (datetime.now() - timedelta(seconds=30)).isoformat(),
        'heart_rate': 72,
        'temperature': 36.8,
        'has_image': True
    },
    {
        'id': 'device_002',
        'patient_name': 'John Anderson',
        'room': '102',
        'location': {
            'x': 22.0,
            'y': 18.5,
            'z': 1.3
        },
        'rssi_readings': {
            'gateway': -62,
            'sn1': -85,
            'sn2': -55,
            'sn3': -70
        },
        'battery_level': 64,
        'status': 'active',
        'wifi_capable': True,
        'last_uplink': (datetime.now() - timedelta(seconds=45)).isoformat(),
        'heart_rate': 68,
        'temperature': 37.1,
        'has_image': True
    },
    {
        'id': 'device_003',
        'patient_name': 'Evelyn Roberts',
        'room': '103',
        'location': {
            'x': 12.0,
            'y': 28.0,
            'z': 1.1
        },
        'rssi_readings': {
            'gateway': -68,
            'sn1': -88,
            'sn2': -82,
            'sn3': -60
        },
        'battery_level': 92,
        'status': 'active',
        'wifi_capable': True,
        'last_uplink': (datetime.now() - timedelta(seconds=15)).isoformat(),
        'heart_rate': 75,
        'temperature': 36.5,
        'has_image': False
    },
    {
        'id': 'device_004',
        'patient_name': 'Robert Chen',
        'room': '104',
        'location': {
            'x': 18.0,
            'y': 8.0,
            'z': 1.2
        },
        'rssi_readings': {
            'gateway': -70,
            'sn1': -72,
            'sn2': -68,
            'sn3': -90
        },
        'battery_level': 45,
        'status': 'low_battery',
        'wifi_capable': True,
        'last_uplink': (datetime.now() - timedelta(minutes=2)).isoformat(),
        'heart_rate': 80,
        'temperature': 36.9,
        'has_image': True
    }
]


def get_all_devices():
    """Get all end devices"""
    return END_DEVICES


def get_device_by_id(device_id):
    """Get specific device by ID"""
    for device in END_DEVICES:
        if device['id'] == device_id:
            return device
    return None


def get_stationary_nodes():
    """Get all stationary nodes (anchors + gateway)"""
    return STATIONARY_NODES


def trigger_image_capture(device_id):
    """
    Simulate triggering image capture from a device
    In production, this would:
    1. Wait for device uplink
    2. Send downlink command
    3. Compute Wi-Fi relay path if needed
    4. Orchestrate Wi-Fi hopping
    5. Receive image data
    """
    device = get_device_by_id(device_id)
    
    if not device:
        return {
            'success': False,
            'error': 'Device not found'
        }
    
    if not device.get('wifi_capable', False):
        return {
            'success': False,
            'error': 'Device does not support Wi-Fi connectivity'
        }
    
    # Simulate relay path calculation
    # In production, this would be based on RSSI and device proximity
    relay_path = []
    
    # Check if device is in direct Wi-Fi range (RSSI > -70 to gateway)
    if device['rssi_readings']['gateway'] > -70:
        relay_path = [device_id, 'gateway']
    else:
        # Need to use relay devices
        # Find intermediate devices with better signal
        relay_path = [device_id, 'device_002', 'gateway']
    
    return {
        'success': True,
        'relay_path': relay_path,
        'estimated_time': f"{len(relay_path) * 3} seconds",
        'timestamp': datetime.now().isoformat()
    }


def get_device_image(device_id):
    """
    Get the latest image from a device
    In production, this would retrieve the actual image from storage
    """
    device = get_device_by_id(device_id)
    
    if not device or not device.get('has_image', False):
        return None
    
    # Return dummy image data
    # In production, this would be the actual image path/URL
    return {
        'url': f'/static/images/captured/{device_id}_latest.jpg',
        'timestamp': datetime.now().isoformat(),
        'size': '2.4 MB',
        'resolution': '640x480'
    }


def calculate_distance_from_rssi(rssi, tx_power=-59, n=2.0):
    """
    Calculate approximate distance from RSSI value
    Formula: d = 10^((TxPower - RSSI) / (10 * n))
    
    Parameters:
    - rssi: Received Signal Strength Indicator
    - tx_power: Transmitter power at 1 meter (calibration value)
    - n: Path loss exponent (2.0 for free space, 2.7-4.3 for indoor)
    """
    return 10 ** ((tx_power - rssi) / (10 * n))


# For integration guide - example of how real data should be structured
REAL_DATA_EXAMPLE = """
# Real Data Integration Example

When integrating with actual LoRa network and RSSI system, replace the dummy_data.py
functions with calls to your actual data sources:

## Example: Fetching real device data

```python
def get_all_devices():
    # Connect to your database or LoRa network server
    import psycopg2  # or your database driver
    
    conn = psycopg2.connect(
        host="your_database_host",
        database="monitoring_db",
        user="your_user",
        password="your_password"
    )
    
    cursor = conn.cursor()
    cursor.execute('''
        SELECT device_id, patient_name, room, 
               location_x, location_y, location_z,
               battery_level, status, last_uplink,
               heart_rate, temperature
        FROM end_devices
        WHERE status = 'active'
    ''')
    
    devices = []
    for row in cursor.fetchall():
        device = {
            'id': row[0],
            'patient_name': row[1],
            'room': row[2],
            'location': {
                'x': row[3],
                'y': row[4],
                'z': row[5]
            },
            'battery_level': row[6],
            'status': row[7],
            'last_uplink': row[8].isoformat(),
            'heart_rate': row[9],
            'temperature': row[10]
        }
        devices.append(device)
    
    cursor.close()
    conn.close()
    
    return devices

## Example: Triggering real image capture

```python
def trigger_image_capture(device_id):
    import requests
    
    # Call your LoRa network server API
    response = requests.post(
        'http://lora-server:8080/api/downlink',
        json={
            'device_id': device_id,
            'command': 'START_IMAGE_CAPTURE',
            'port': 2
        }
    )
    
    if response.status_code == 200:
        return response.json()
    
    return {'success': False, 'error': 'Failed to send command'}
```
"""
