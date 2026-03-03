# Elderly Home Monitoring System - Web Server

A Flask-based web application for monitoring elderly patients using RSSI-based localization and server-orchestrated Wi-Fi hopping.

## Features

### 1. **3D Topology Visualization**
- Interactive 3D representation of the facility
- Real-time display of stationary nodes (gateway + 3 anchors)
- Live tracking of patient device locations
- RSSI signal strength visualization with color-coded lines
- Intuitive controls for navigation and view manipulation

### 2. **Device Management Dashboard**
- Comprehensive list of all patient devices
- Real-time status monitoring (battery, health metrics, connectivity)
- Click-to-view detailed device information
- Auto-refresh capability for live monitoring

### 3. **Image Capture & Viewing**
- API-driven image capture request system
- Server-orchestrated Wi-Fi hopping visualization
- Relay path calculation and display
- Dedicated image viewer with metadata
- Store-and-forward fallback support

### 4. **Location Services**
- RSSI-based trilateration
- On-demand location updates
- Visual feedback of device positioning
- Distance calculation from multiple anchor points

---

## Quick Start

### Prerequisites
- Python 3.8 or higher
- pip (Python package manager)
- Modern web browser (Chrome, Firefox, Safari, Edge)

### Installation

1. **Clone or navigate to the project directory:**
```bash
cd "Application Server"
```

2. **Create a virtual environment (recommended):**
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies:**
```bash
pip install -r requirements.txt
```

4. **Run the application:**
```bash
python app.py
```

5. **Access the dashboard:**
Open your browser and navigate to:
```
http://localhost:5000
```

---

## Project Structure

```
Application Server/
├── app.py                      # Main Flask application
├── dummy_data.py               # Simulated data source (replace with real data)
├── requirements.txt            # Python dependencies
├── README.md                   # This file
├── templates/
│   ├── dashboard.html          # Main monitoring dashboard
│   └── view_image.html         # Image viewer page
├── static/
│   ├── css/
│   │   └── style.css           # Application styles
│   ├── js/
│   │   ├── topology3d.js       # 3D visualization logic
│   │   └── dashboard.js        # Dashboard UI controller
│   └── images/
│       └── captured/           # Directory for device images
│           ├── device_001_latest.jpg
│           ├── device_002_latest.jpg
│           └── device_004_latest.jpg
└── .gitignore
```

---

## API Endpoints

### Device Operations

#### Get All Devices
```http
GET /api/devices
```
Returns list of all end devices with current status and location.

**Response:**
```json
{
  "success": true,
  "devices": [
    {
      "id": "device_001",
      "patient_name": "Margaret Smith",
      "room": "101",
      "location": {"x": 8.5, "y": 12.0, "z": 1.2},
      "rssi_readings": {"gateway": -65, "sn1": -58, "sn2": -78, "sn3": -82},
      "battery_level": 87,
      "status": "active",
      "wifi_capable": true,
      "last_uplink": "2026-02-28T10:30:00",
      "heart_rate": 72,
      "temperature": 36.8,
      "has_image": true
    }
  ],
  "timestamp": "2026-02-28T10:35:00"
}
```

#### Get Stationary Nodes
```http
GET /api/stationary-nodes
```
Returns all anchor nodes with fixed coordinates.

#### Get Specific Device
```http
GET /api/device/{device_id}
```

#### Initiate Location Update
```http
POST /api/locate/{device_id}
```
Triggers RSSI trilateration process for a device.

#### Request Image Capture
```http
POST /api/request-image/{device_id}
```
Initiates Wi-Fi hopping process to capture and transfer image.

**Response:**
```json
{
  "success": true,
  "message": "Image request sent to device device_001",
  "device_id": "device_001",
  "relay_path": ["device_001", "device_002", "gateway"],
  "estimated_time": "9 seconds"
}
```

#### Get Device Image
```http
GET /api/device/{device_id}/image
```
Retrieves the latest captured image metadata.

### View Endpoints

#### Dashboard
```http
GET /
```
Main monitoring interface with 3D topology.

#### Image Viewer
```http
GET /view-image/{device_id}
```
Dedicated page for viewing device images.

---

## Integration Guide: Replacing Dummy Data

The current implementation uses `dummy_data.py` to simulate real device data. When your LoRa network and RSSI system are operational, follow these steps to integrate real data:

### Step 1: Database Setup

Create a database schema to store device data:

```sql
-- PostgreSQL Example
CREATE TABLE stationary_nodes (
    id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100),
    type VARCHAR(20),
    location_x FLOAT,
    location_y FLOAT,
    location_z FLOAT,
    status VARCHAR(20),
    last_seen TIMESTAMP
);

CREATE TABLE end_devices (
    id VARCHAR(50) PRIMARY KEY,
    patient_name VARCHAR(100),
    room VARCHAR(20),
    location_x FLOAT,
    location_y FLOAT,
    location_z FLOAT,
    battery_level INTEGER,
    status VARCHAR(20),
    wifi_capable BOOLEAN,
    last_uplink TIMESTAMP,
    heart_rate INTEGER,
    temperature FLOAT,
    has_image BOOLEAN
);

CREATE TABLE rssi_readings (
    device_id VARCHAR(50),
    node_id VARCHAR(50),
    rssi INTEGER,
    timestamp TIMESTAMP,
    PRIMARY KEY (device_id, node_id, timestamp)
);

CREATE TABLE device_images (
    id SERIAL PRIMARY KEY,
    device_id VARCHAR(50),
    image_path VARCHAR(255),
    timestamp TIMESTAMP,
    size_bytes INTEGER,
    resolution VARCHAR(20)
);
```

### Step 2: Replace Dummy Data Functions

Modify `dummy_data.py` or create a new `data_provider.py`:

```python
import psycopg2
from datetime import datetime

# Database connection
def get_db_connection():
    return psycopg2.connect(
        host="your_database_host",
        database="monitoring_db",
        user="your_user",
        password="your_password"
    )

def get_all_devices():
    """Fetch real device data from database"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT d.id, d.patient_name, d.room,
               d.location_x, d.location_y, d.location_z,
               d.battery_level, d.status, d.wifi_capable,
               d.last_uplink, d.heart_rate, d.temperature,
               d.has_image
        FROM end_devices d
        WHERE d.status != 'inactive'
    ''')
    
    devices = []
    for row in cursor.fetchall():
        device_id = row[0]
        
        # Fetch RSSI readings for this device
        cursor.execute('''
            SELECT node_id, rssi
            FROM rssi_readings
            WHERE device_id = %s
            AND timestamp = (
                SELECT MAX(timestamp)
                FROM rssi_readings
                WHERE device_id = %s
            )
        ''', (device_id, device_id))
        
        rssi_readings = {node_id: rssi for node_id, rssi in cursor.fetchall()}
        
        device = {
            'id': device_id,
            'patient_name': row[1],
            'room': row[2],
            'location': {
                'x': row[3],
                'y': row[4],
                'z': row[5]
            },
            'rssi_readings': rssi_readings,
            'battery_level': row[6],
            'status': row[7],
            'wifi_capable': row[8],
            'last_uplink': row[9].isoformat() if row[9] else None,
            'heart_rate': row[10],
            'temperature': row[11],
            'has_image': row[12]
        }
        devices.append(device)
    
    cursor.close()
    conn.close()
    
    return devices
```

### Step 3: LoRa Network Server Integration

Connect to your LoRa Network Server API to trigger downlink commands:

```python
import requests

def trigger_image_capture(device_id):
    """Send downlink command via LoRa Network Server"""
    
    # 1. Check if device exists and is capable
    device = get_device_by_id(device_id)
    if not device or not device['wifi_capable']:
        return {'success': False, 'error': 'Device not available'}
    
    # 2. Calculate relay path based on RSSI
    relay_path = calculate_relay_path(device)
    
    # 3. Send downlink command to LoRa Network Server
    lora_server_url = "http://your-lora-server:8080/api/v3/downlink"
    
    payload = {
        'device_id': device_id,
        'confirmed': True,
        'fPort': 2,
        'data': base64.b64encode(b'IMG_CAPTURE').decode()
    }
    
    try:
        response = requests.post(
            lora_server_url,
            json=payload,
            headers={'Authorization': 'Bearer YOUR_API_TOKEN'}
        )
        
        if response.status_code == 200:
            return {
                'success': True,
                'relay_path': relay_path,
                'estimated_time': f"{len(relay_path) * 3} seconds",
                'timestamp': datetime.now().isoformat()
            }
    except Exception as e:
        return {'success': False, 'error': str(e)}
```

### Step 4: RSSI Trilateration Integration

Implement real-time trilateration based on incoming RSSI data:

```python
import numpy as np
from scipy.optimize import least_squares

def calculate_position_from_rssi(rssi_readings, stationary_nodes):
    """
    Perform trilateration using RSSI measurements
    
    Args:
        rssi_readings: dict of {node_id: rssi_value}
        stationary_nodes: list of nodes with known coordinates
    
    Returns:
        Estimated (x, y, z) position
    """
    
    # Convert RSSI to distance estimates
    distances = {}
    for node_id, rssi in rssi_readings.items():
        distance = calculate_distance_from_rssi(rssi)
        distances[node_id] = distance
    
    # Prepare data for optimization
    node_positions = []
    distance_measurements = []
    
    for node in stationary_nodes:
        if node['id'] in distances:
            node_positions.append([
                node['location']['x'],
                node['location']['y'],
                node['location']['z']
            ])
            distance_measurements.append(distances[node['id']])
    
    node_positions = np.array(node_positions)
    distance_measurements = np.array(distance_measurements)
    
    # Optimization function
    def residuals(position):
        return np.linalg.norm(node_positions - position, axis=1) - distance_measurements
    
    # Initial guess (center of facility)
    x0 = np.mean(node_positions, axis=0)
    
    # Solve
    result = least_squares(residuals, x0)
    
    return {
        'x': result.x[0],
        'y': result.x[1],
        'z': result.x[2]
    }

def calculate_distance_from_rssi(rssi, tx_power=-59, n=2.7):
    """
    Convert RSSI to distance using path loss model
    
    Args:
        rssi: Received signal strength
        tx_power: Transmitter power at 1m (calibrate for your hardware)
        n: Path loss exponent (2.7-4.3 for indoor environments)
    """
    return 10 ** ((tx_power - rssi) / (10 * n))
```

### Step 5: Wi-Fi Hopping Path Calculation

Implement intelligent relay path selection:

```python
def calculate_relay_path(target_device):
    """
    Calculate optimal Wi-Fi relay path from device to gateway
    
    Uses RSSI data to determine which intermediate devices
    should activate their Wi-Fi hotspots
    """
    
    all_devices = get_all_devices()
    gateway_position = get_gateway_position()
    
    # Check if device is in direct range
    if target_device['rssi_readings']['gateway'] > -70:
        return [target_device['id'], 'gateway']
    
    # Find intermediate devices with good connectivity
    path = [target_device['id']]
    current_pos = target_device['location']
    
    while True:
        best_relay = None
        best_score = float('-inf')
        
        for device in all_devices:
            if device['id'] in path or not device['wifi_capable']:
                continue
            
            # Calculate distance to current position
            dist_to_current = calculate_distance(current_pos, device['location'])
            
            # Check signal strength to gateway
            gateway_rssi = device['rssi_readings'].get('gateway', -100)
            
            # Score based on position and signal
            score = gateway_rssi - (dist_to_current * 2)
            
            if score > best_score and dist_to_current < 15:  # Within range
                best_score = score
                best_relay = device
        
        if best_relay:
            path.append(best_relay['id'])
            current_pos = best_relay['location']
            
            # Check if we're close enough to gateway
            if best_relay['rssi_readings']['gateway'] > -70:
                path.append('gateway')
                break
        else:
            # No viable path found
            path.append('gateway')  # Direct attempt
            break
    
    return path
```

### Step 6: Image Storage and Retrieval

Handle real image data from devices:

```python
import os
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = 'static/images/captured'
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png'}

def save_device_image(device_id, image_data):
    """
    Save image received from device
    
    Args:
        device_id: Device identifier
        image_data: Binary image data
    """
    
    filename = f"{device_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    
    with open(filepath, 'wb') as f:
        f.write(image_data)
    
    # Update database
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO device_images (device_id, image_path, timestamp, size_bytes)
        VALUES (%s, %s, %s, %s)
    ''', (device_id, filepath, datetime.now(), len(image_data)))
    conn.commit()
    cursor.close()
    conn.close()
    
    # Update device has_image flag
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE end_devices SET has_image = TRUE WHERE id = %s
    ''', (device_id,))
    conn.commit()
    cursor.close()
    conn.close()
    
    return filename

def get_device_image(device_id):
    """Retrieve latest image for a device"""
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT image_path, timestamp, size_bytes, resolution
        FROM device_images
        WHERE device_id = %s
        ORDER BY timestamp DESC
        LIMIT 1
    ''', (device_id,))
    
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if not row:
        return None
    
    return {
        'url': f'/{row[0]}',
        'timestamp': row[1].isoformat(),
        'size': f'{row[2] / (1024 * 1024):.2f} MB',
        'resolution': row[3] or 'N/A'
    }
```

### Step 7: Update Flask App

Modify `app.py` imports:

```python
# Replace this:
from dummy_data import (...)

# With this:
from data_provider import (
    get_all_devices,
    get_device_by_id,
    get_stationary_nodes,
    trigger_image_capture,
    get_device_image
)
```

---

## 🧪 Testing with Dummy Data

The application comes pre-configured with realistic dummy data:

- **4 Patient Devices** with varying battery levels, health metrics, and locations
- **3 Stationary Nodes + 1 Gateway** positioned throughout a 30m x 40m facility
- **RSSI readings** for trilateration demonstration
- **Sample images** for devices with `has_image: true`

This allows you to:
- Test the UI/UX before hardware is ready
- Demonstrate the system to stakeholders
- Develop and debug frontend features independently
- Validate API contracts

---

## Calibration Guide

### RSSI-to-Distance Calibration

For accurate localization, calibrate the path loss model for your environment:

1. **Collect Reference Measurements:**
   - Place a device at known distances from a stationary node (1m, 2m, 5m, 10m, 15m)
   - Record RSSI values at each distance
   - Repeat in different areas of your facility

2. **Calculate Path Loss Exponent (n):**
   ```python
   # Use linear regression on your measurements
   import numpy as np
   from scipy.stats import linregress
   
   distances = np.array([1, 2, 5, 10, 15])  # meters
   rssi_values = np.array([-55, -62, -71, -78, -83])  # your measurements
   
   # Convert to log scale
   log_distances = np.log10(distances)
   
   # Regression
   slope, intercept, r_value, p_value, std_err = linregress(log_distances, rssi_values)
   
   n = -slope / 10
   tx_power = intercept
   
   print(f"Path Loss Exponent (n): {n}")
   print(f"TX Power at 1m: {tx_power}")
   ```

3. **Update Configuration:**
   ```python
   # In data_provider.py or dummy_data.py
   CALIBRATION = {
       'tx_power': -59,  # Your calibrated value
       'path_loss_exponent': 2.7  # Your calibrated value
   }
   ```

---

## Security Considerations

When deploying in production:

1. **Change the secret key** in `app.py`
2. **Use environment variables** for sensitive configuration
3. **Implement authentication** (e.g., Flask-Login)
4. **Enable HTTPS** behind a reverse proxy (nginx)
5. **Validate all inputs** server-side
6. **Rate limit API endpoints**
7. **Sanitize database queries** (use parameterized queries)

Example using environment variables:

```python
import os

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or 'dev-key-change-in-production'
DATABASE_URL = os.environ.get('DATABASE_URL')
LORA_SERVER_URL = os.environ.get('LORA_SERVER_URL')
LORA_API_TOKEN = os.environ.get('LORA_API_TOKEN')
```

---

## Production Deployment

### Using Gunicorn (Recommended)

1. **Install Gunicorn:**
```bash
pip install gunicorn
```

2. **Run with Gunicorn:**
```bash
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

### Using Docker

Create `Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app"]
```

Build and run:
```bash
docker build -t elderly-monitoring .
docker run -p 5000:5000 elderly-monitoring
```

### Using Systemd (Linux)

Create `/etc/systemd/system/elderly-monitoring.service`:

```ini
[Unit]
Description=Elderly Monitoring Web Server
After=network.target

[Service]
User=www-data
WorkingDirectory=/path/to/Application Server
Environment="PATH=/path/to/venv/bin"
ExecStart=/path/to/venv/bin/gunicorn -w 4 -b 127.0.0.1:5000 app:app

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable elderly-monitoring
sudo systemctl start elderly-monitoring
```

---

## Troubleshooting

### 3D Visualization Not Loading

**Issue:** Canvas appears black or empty

**Solutions:**
- Check browser console for JavaScript errors
- Ensure Three.js CDN is accessible
- Try a different browser (Chrome recommended)
- Check if WebGL is enabled in browser settings

### API Returns 404 Errors

**Issue:** Endpoints return "Not Found"

**Solutions:**
- Verify Flask app is running
- Check endpoint URL spelling
- Ensure app.py has all route decorators
- Look for Python syntax errors in terminal

### Images Not Displaying

**Issue:** Image viewer shows "No image available"

**Solutions:**
- Check if dummy images exist in `static/images/captured/`
- Verify file permissions
- Check device `has_image` flag in dummy_data.py
- Look at browser Network tab for 404 errors

### Slow Performance

**Issue:** Dashboard is laggy

**Solutions:**
- Reduce auto-refresh interval (line 22 in dashboard.js)
- Limit number of devices in dummy_data.py
- Check browser hardware acceleration settings
- Use Chrome/Edge for better WebGL performance

---

## Customization

### Changing Facility Dimensions

Edit `dummy_data.py`:

```python
FACILITY_WIDTH = 50  # Change from 30
FACILITY_LENGTH = 60  # Change from 40
FACILITY_HEIGHT = 8   # Change from 5
```

Also update `topology3d.js`:

```javascript
// In createFacility() method
const floorGeometry = new THREE.PlaneGeometry(50, 60);
```

### Adding More Devices

Edit `dummy_data.py` and add to `END_DEVICES` list:

```python
{
    'id': 'device_005',
    'patient_name': 'New Patient',
    'room': '105',
    'location': {'x': 10.0, 'y': 15.0, 'z': 1.2},
    # ... other fields
}
```

### Changing Color Scheme

Edit `static/css/style.css` `:root` variables:

```css
:root {
    --primary-color: #your-color;
    --secondary-color: #your-color;
    /* etc. */
}
```

---

## Additional Resources

- [Flask Documentation](https://flask.palletsprojects.com/)
- [Three.js Documentation](https://threejs.org/docs/)
- [LoRaWAN Specification](https://lora-alliance.org/resource_hub/lorawan-specification-v1-1/)
- [RSSI-Based Localization Paper](https://ieeexplore.ieee.org/)

---

## Support

For issues related to:
- **Web Application:** Check this README and troubleshooting section
- **LoRa Network:** Consult your network server documentation
- **Hardware Integration:** Refer to device manufacturer documentation

---

## License

This project is part of the CSC2106 IoT Protocols and Networks course at the University of Glasgow.

---

**Last Updated:** February 28, 2026
