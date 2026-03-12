# TTN Integration Guide

## Overview

Your Flask application server has been successfully integrated with The Things Network (TTN) MQTT broker. The system now receives real-time uplink messages from your LoRa devices and can send downlink commands for image capture and location requests.

## Architecture

```
┌─────────────────┐
│  LoRa Devices   │
│  (ed-1, ed-2,   │
│   ed-3, ed-4)   │
└────────┬────────┘
         │ LoRaWAN
         ▼
┌─────────────────┐
│  The Things     │
│  Network (TTN)  │
│  MQTT Broker    │
└────────┬────────┘
         │ MQTT
         ▼
┌─────────────────┐      ┌──────────────────┐
│ ttn_integration │◄────►│ device_manager   │
│     .py         │      │      .py         │
└────────┬────────┘      └────────┬─────────┘
         │                        │
         └────────────┬───────────┘
                      ▼
              ┌───────────────┐
              │    app.py     │
              │ Flask Server  │
              └───────┬───────┘
                      │ HTTP
                      ▼
              ┌───────────────┐
              │   Dashboard   │
              │    (Browser)  │
              └───────────────┘
```

## Key Components

### 1. `ttn_integration.py`
Handles all MQTT communication with TTN:
- **Connects** to TTN MQTT broker
- **Receives** uplink messages from devices
- **Sends** downlink commands (image capture, location request, Wi-Fi hotspot control)
- **Parses** payload data (RSSI, images, health metrics)

### 2. `device_manager.py`
Manages real-time device data:
- **Stores** device state (location, RSSI readings, battery, health)
- **Processes** incoming uplink messages
- **Saves** received images to disk
- **Calculates** Wi-Fi relay paths for data hopping
- **Provides** data access for Flask API

### 3. `app.py` (Updated)
Flask web server with real TTN integration:
- **Serves** dashboard UI
- **Provides** REST API for device management
- **Triggers** downlink commands via TTN
- **Displays** real-time device data

## Device ID Mapping

Your TTN devices are mapped to patient information:

| TTN Device ID | Patient Name      | Room | Wi-Fi Capable |
|---------------|-------------------|------|---------------|
| `ed-1`        | Margaret Smith    | 101  | Yes           |
| `ed-2`        | John Anderson     | 102  | Yes           |
| `ed-3`        | Evelyn Roberts    | 103  | Yes           |
| `ed-4`        | Robert Chen       | 104  | Yes           |

**Note:** Update the `DEVICE_INFO_MAP` in [device_manager.py](device_manager.py#L29) to add more devices.

## Payload Protocol

### Uplink Payloads (Device → Server)

#### 1. RSSI Reading
```
Byte 0: 0x01 (Payload type: RSSI)
Byte 1-2: RSSI value (signed 16-bit integer, big-endian)
```
Example: `0x01 FF B8` = RSSI of -72 dBm

#### 2. Image Data
```
Byte 0: 0x02 (Payload type: Image)
Byte 1-N: JPEG image bytes
```

#### 3. Health Metrics
```
Byte 0: 0x03 (Payload type: Health)
Byte 1: Heart rate (unsigned 8-bit)
Byte 2-3: Temperature × 10 (unsigned 16-bit, big-endian)
```
Example: `0x03 48 01 6C` = HR 72 bpm, Temp 36.8°C

### Downlink Payloads (Server → Device)

#### 1. Image Capture Command
```
FPort: 2
Payload: 0x01
```
Triggers device to capture and transmit image via Wi-Fi hopping.

#### 2. Location Request Command
```
FPort: 2
Payload: 0x02
```
Triggers device to broadcast RSSI ping to all stationary nodes.

#### 3. Wi-Fi Hotspot Control
```
FPort: 2
Payload: 0x03 [enable/disable] [IP bytes]

enable/disable: 0x01 = Enable, 0x00 = Disable
IP bytes: 4 bytes (e.g., 192.168.1.50 → 0xC0 0xA8 0x01 0x32)
```
Example: `0x03 01 C0 A8 01 32` = Enable hotspot with IP 192.168.1.50

## Setup Instructions

### 1. Install Dependencies

```bash
cd "/home/yztan120/Application Server"
pip install -r requirements.txt
```

### 2. Configure TTN Credentials

The TTN credentials are already configured in [ttn_integration.py](ttn_integration.py#L14):

```python
TTN_APP_ID = "iot-sit-group26-project-2026"
TTN_API_KEY = "NNSXS.HQ2B..."  # Your API key
TTN_REGION = "au1"
```

**⚠️ Security Note:** For production, move these to environment variables:

```bash
export TTN_APP_ID="iot-sit-group26-project-2026"
export TTN_API_KEY="your-api-key-here"
export TTN_REGION="au1"
```

Then update `ttn_integration.py`:
```python
import os
TTN_APP_ID = os.environ.get('TTN_APP_ID')
TTN_API_KEY = os.environ.get('TTN_API_KEY')
TTN_REGION = os.environ.get('TTN_REGION', 'au1')
```

### 3. Run the Application

```bash
python app.py
```

You should see:
```
INFO - Starting TTN MQTT client...
INFO - ✓ Connected to The Things Network
INFO - ✓ Subscribed to: v3/iot-sit-group26-project-2026@ttn/devices/+/up
INFO - ✓ Application Server ready - TTN connected
INFO - Starting Flask web server on 0.0.0.0:8080
```

### 4. Access the Dashboard

Open your browser: `http://localhost:8080`

## API Endpoints

All existing endpoints from the original README still work. New endpoints:

### Check TTN Connection Status
```http
GET /api/ttn-status
```
Response:
```json
{
  "connected": true,
  "timestamp": "2026-03-03T10:30:00"
}
```

### Update RSSI Reading (Manual)
```http
POST /api/update-rssi/<device_id>/<node_id>/<rssi>
```
Example: `POST /api/update-rssi/ed-1/sn1/-65`

### Update Battery Level (Manual)
```http
POST /api/update-battery/<device_id>/<battery_level>
```
Example: `POST /api/update-battery/ed-1/85`

## Testing the Integration

### 1. Test TTN Connection

Create a test script `test_ttn.py`:

```python
from ttn_integration import TTNClient
import time

def on_message(device_id, payload_data, metadata):
    print(f"\n✓ Received from {device_id}")
    print(f"  Payload: {payload_data}")
    print(f"  RSSI: {metadata.get('gateway_rssi')} dBm")

client = TTNClient(on_message_callback=on_message)
client.start()

print("Waiting for messages... (Press Ctrl+C to stop)")
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nStopping...")
    client.stop()
```

Run: `python test_ttn.py`

### 2. Send a Test Downlink

```python
from ttn_integration import get_ttn_client

ttn = get_ttn_client()
ttn.start()

# Send image capture command to ed-1
success = ttn.send_image_capture_command('ed-1')
print(f"Downlink sent: {success}")

ttn.stop()
```

### 3. Monitor the Dashboard

1. Open `http://localhost:8080`
2. Click "Refresh Data" to see connected devices
3. Click "Request Image" on a device
4. Monitor the console for downlink confirmations

## Workflow Examples

### Example 1: Request Image from Device

**Step 1:** Nurse clicks "Request Image" on dashboard for device `ed-1`

**Step 2:** Flask server calls:
```python
POST /api/request-image/ed-1
```

**Step 3:** Server logic:
- Checks if `ed-1` is Wi-Fi capable ✓
- Calculates relay path: `['ed-1', 'gateway']` (direct)
- Sends downlink via TTN: `0x01` on FPort 2

**Step 4:** Device receives downlink:
- Captures image
- Connects to gateway Wi-Fi
- Uploads image

**Step 5:** Server receives image uplink:
- Saves as `/static/images/captured/ed-1_latest.jpg`
- Updates device `has_image` flag

**Step 6:** Dashboard auto-refreshes and shows new image available

### Example 2: Locate Device with RSSI Relay

**Step 1:** Nurse clicks "Locate Device" for `ed-3`

**Step 2:** Server sends location request:
```python
POST /api/locate/ed-3
```

**Step 3:** Device `ed-3` receives downlink `0x02`:
- Broadcasts "hello" packet via LoRa

**Step 4:** Stationary nodes (gateway, sn1, sn2, sn3) receive packet:
- Each measures RSSI
- Each sends uplink with RSSI value

**Step 5:** Server receives 4 RSSI readings:
- gateway: -68 dBm
- sn1: -88 dBm
- sn2: -82 dBm
- sn3: -60 dBm

**Step 6:** Server performs trilateration:
- Calculates (x, y, z) position
- Updates device location in `device_manager`

**Step 7:** Dashboard shows updated location on 3D map

## Troubleshooting

### Issue: "TTN connection pending"

**Cause:** Cannot connect to TTN MQTT broker

**Solutions:**
1. Check internet connection
2. Verify TTN credentials in `ttn_integration.py`
3. Check TTN Application status at https://console.cloud.thethings.network/
4. Ensure port 1883 is not blocked by firewall:
   ```bash
   telnet au1.cloud.thethings.network 1883
   ```

### Issue: No uplink messages received

**Cause:** Devices not transmitting or wrong topic subscription

**Solutions:**
1. Check if devices are powered on and registered in TTN
2. Monitor TTN Console "Live Data" to see if messages arrive at TTN
3. Verify subscription topic in logs:
   ```
   ✓ Subscribed to: v3/iot-sit-group26-project-2026@ttn/devices/+/up
   ```
4. Check device OTAA/ABP join status

### Issue: Downlink not sent

**Cause:** API key lacks downlink permissions or device ID mismatch

**Solutions:**
1. Verify API key has "Write downlink application traffic" permission in TTN Console
2. Check device ID matches exactly (case-sensitive): `ed-1` not `ED-1`
3. Check API response in logs:
   ```
   ✗ Downlink failed for ed-1: 403 {"message": "insufficient rights"}
   ```
4. Regenerate API key with correct permissions

### Issue: Images not saving

**Cause:** Permission issues or invalid image data

**Solutions:**
1. Check directory permissions:
   ```bash
   ls -la "static/images/captured"
   ```
2. Ensure directory is writable:
   ```bash
   chmod 755 "static/images/captured"
   ```
3. Check logs for save errors:
   ```
   ERROR - Error saving image for ed-1: [Errno 13] Permission denied
   ```

### Issue: Device location not updating

**Cause:** Insufficient RSSI readings for trilateration

**Solutions:**
1. Ensure at least 3 stationary nodes receive the RSSI ping
2. Check RSSI values are not None in device_manager
3. Verify stationary node coordinates are correct in `STATIONARY_NODES`
4. Implement trilateration algorithm (currently placeholder)

## Advanced Configuration

### Adding More Devices

Edit [device_manager.py](device_manager.py#L29):

```python
DEVICE_INFO_MAP = {
    'ed-1': {'patient_name': 'Margaret Smith', 'room': '101', 'wifi_capable': True},
    'ed-2': {'patient_name': 'John Anderson', 'room': '102', 'wifi_capable': True},
    'ed-3': {'patient_name': 'Evelyn Roberts', 'room': '103', 'wifi_capable': True},
    'ed-4': {'patient_name': 'Robert Chen', 'room': '104', 'wifi_capable': True},
    'ed-5': {'patient_name': 'New Patient', 'room': '105', 'wifi_capable': True},  # Add this
}
```

### Adjusting Facility Layout

Edit stationary node positions in [device_manager.py](device_manager.py#L15):

```python
STATIONARY_NODES = [
    {
        'id': 'gateway',
        'location': {'x': 20.0, 'y': 25.0, 'z': 3.0},  # Adjust coordinates
        # ...
    },
    # ... adjust other nodes
]
```

Also update `FACILITY_WIDTH`, `FACILITY_LENGTH`, `FACILITY_HEIGHT` to match your facility.

### Implementing RSSI Trilateration

The system currently stores RSSI readings but doesn't perform actual trilateration. To implement:

1. Install scipy: `pip install scipy`

2. Add to [device_manager.py](device_manager.py):

```python
import numpy as np
from scipy.optimize import least_squares

def trilaterate_position(rssi_readings, stationary_nodes):
    """Calculate position from RSSI readings"""
    
    # Convert RSSI to distances (path loss model)
    def rssi_to_distance(rssi, tx_power=-59, n=2.7):
        return 10 ** ((tx_power - rssi) / (10 * n))
    
    # Prepare node positions and distances
    positions = []
    distances = []
    
    for node in stationary_nodes:
        node_id = node['id']
        if node_id in rssi_readings and rssi_readings[node_id] is not None:
            positions.append([
                node['location']['x'],
                node['location']['y'],
                node['location']['z']
            ])
            distances.append(rssi_to_distance(rssi_readings[node_id]))
    
    if len(positions) < 3:
        return None  # Need at least 3 nodes
    
    positions = np.array(positions)
    distances = np.array(distances)
    
    # Optimization function
    def residuals(position):
        return np.linalg.norm(positions - position, axis=1) - distances
    
    # Initial guess (center of nodes)
    x0 = np.mean(positions, axis=0)
    
    # Solve
    result = least_squares(residuals, x0)
    
    if result.success:
        return {
            'x': float(result.x[0]),
            'y': float(result.x[1]),
            'z': float(result.x[2])
        }
    
    return None
```

3. Call this function when RSSI readings are complete:

```python
# In DeviceManager.handle_uplink_message()
if all(device['rssi_readings'][node] is not None 
       for node in ['gateway', 'sn1', 'sn2', 'sn3']):
    # All RSSI readings available
    new_location = trilaterate_position(
        device['rssi_readings'],
        STATIONARY_NODES
    )
    if new_location:
        self.update_device_location(
            device_id,
            new_location['x'],
            new_location['y'],
            new_location['z']
        )
```

### Running as a System Service

For production deployment on Raspberry Pi:

1. Create `/etc/systemd/system/elderly-monitoring.service`:

```ini
[Unit]
Description=Elderly Monitoring Application Server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/yztan120/Application Server
Environment="PATH=/home/yztan120/Application Server/venv/bin"
ExecStart=/home/yztan120/Application Server/venv/bin/python app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

2. Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable elderly-monitoring
sudo systemctl start elderly-monitoring
```

3. Check status:
```bash
sudo systemctl status elderly-monitoring
```

4. View logs:
```bash
sudo journalctl -u elderly-monitoring -f
```

## Next Steps

1. **Test with Real Devices:** Power on your LoRa devices and verify uplink messages appear
2. **Calibrate RSSI:** Follow the calibration guide in [README.md](README.md) to adjust path loss parameters
3. **Implement Trilateration:** Add the RSSI-to-position calculation algorithm
4. **Test Wi-Fi Hopping:** Verify relay path selection and image transmission
5. **Add Authentication:** Secure the dashboard with login credentials
6. **Deploy to Production:** Use systemd service for auto-start on boot

## Support & Resources

- **TTN Documentation:** https://www.thethingsindustries.com/docs/
- **paho-mqtt Documentation:** https://www.eclipse.org/paho/index.php?page=clients/python/docs/index.php
- **Flask Documentation:** https://flask.palletsprojects.com/
- **Project README:** [README.md](README.md)

---

**Integration completed successfully!** Your web server is now connected to The Things Network and ready to monitor your LoRa devices in real-time.
