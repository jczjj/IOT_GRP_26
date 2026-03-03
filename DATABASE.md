# Database Documentation

## Overview

The elderly monitoring system uses SQLite database (`elderly_monitoring.db`) as the single source of truth for all device data, RSSI readings, and system state.

**Database Location:** `/home/yztan120/Application Server/elderly_monitoring.db`

## Quick Start

### Initialize Database (First Time)
```bash
cd "/home/yztan120/Application Server"
venv/bin/python init_db.py
```

### Query Database
```bash
# Interactive menu
venv/bin/python query_db.py

# Command-line queries
venv/bin/python query_db.py devices    # Show all devices
venv/bin/python query_db.py nodes      # Show stationary nodes
venv/bin/python query_db.py rssi       # Show recent RSSI readings
venv/bin/python query_db.py summary    # Show latest RSSI per device
venv/bin/python query_db.py stats      # Show database statistics
venv/bin/python query_db.py all        # Show everything
```

### Direct SQL Access
```bash
sqlite3 elderly_monitoring.db

# Example queries
sqlite> SELECT * FROM devices;
sqlite> SELECT * FROM rssi_readings ORDER BY timestamp DESC LIMIT 10;
sqlite> .exit
```

## Schema Design

### Table: `devices`
Stores information about end devices (wearables worn by elderly residents).

| Column | Type | Description |
|--------|------|-------------|
| device_id | TEXT PRIMARY KEY | Unique device identifier (e.g., "ed-1") |
| patient_name | TEXT | Name of the resident wearing the device |
| room | TEXT | Room number/identifier |
| battery_level | INTEGER | Battery percentage (0-100) |
| status | TEXT | Device status: "active", "inactive", "battery_low", "offline" |
| last_uplink | TEXT | ISO 8601 timestamp of last message |
| last_rssi | INTEGER | Most recent RSSI reading (dBm) |
| last_location | TEXT | JSON string: `{"x": 5.2, "y": 3.1, "z": 1.5}` |
| location_updated_at | TEXT | ISO 8601 timestamp of last location update |
| heart_rate | INTEGER | Current heart rate (bpm), NULL if not available |
| temperature | REAL | Current body temperature (°C), NULL if not available |
| has_image | INTEGER | Boolean (0/1): whether device has captured image |
| last_image_path | TEXT | Path to most recent image |
| created_at | TEXT | Device registration timestamp |

**Indexes:**
- PRIMARY KEY on `device_id`

### Table: `rssi_readings`
Stores RSSI measurements from stationary nodes.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PRIMARY KEY AUTOINCREMENT | Auto-incrementing record ID |
| device_id | TEXT NOT NULL | Foreign key to devices.device_id |
| node_id | TEXT NOT NULL | Stationary node that measured RSSI (e.g., "sn-01") |
| rssi | INTEGER NOT NULL | Signal strength in dBm (typically -120 to 0) |
| timestamp | TEXT NOT NULL | ISO 8601 timestamp of measurement |

**Indexes:**
- PRIMARY KEY on `id`
- INDEX `idx_rssi_timestamp` on `timestamp` (for fast time-based queries)

**Foreign Keys:**
- `device_id` references `devices(device_id)`

### Table: `stationary_nodes`
Stores configuration for stationary LoRa nodes (fixed positions in the facility).

| Column | Type | Description |
|--------|------|-------------|
| node_id | TEXT PRIMARY KEY | Unique node identifier (e.g., "sn-01", "gateway") |
| name | TEXT | Human-readable name |
| type | TEXT | Node type: "stationary", "gateway" |
| location_x | REAL | X coordinate in meters |
| location_y | REAL | Y coordinate in meters |
| location_z | REAL | Z coordinate (height) in meters |
| status | TEXT | Node status: "active", "inactive" |

**Indexes:**
- PRIMARY KEY on `node_id`

### Table: `device_images`
Stores metadata for images captured by devices.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PRIMARY KEY AUTOINCREMENT | Auto-incrementing record ID |
| device_id | TEXT NOT NULL | Foreign key to devices.device_id |
| image_path | TEXT NOT NULL | Relative path from static/images/captured/ |
| timestamp | TEXT NOT NULL | ISO 8601 timestamp of capture |
| size_bytes | INTEGER | File size in bytes |
| resolution | TEXT | Image resolution (e.g., "640x480") |

**Indexes:**
- PRIMARY KEY on `id`

**Foreign Keys:**
- `device_id` references `devices(device_id)`

### Table: `system_log`
General-purpose logging table for system events.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PRIMARY KEY AUTOINCREMENT | Auto-incrementing record ID |
| timestamp | TEXT NOT NULL | ISO 8601 timestamp of event |
| level | TEXT | Log level: "INFO", "WARNING", "ERROR" |
| component | TEXT | System component (e.g., "ttn_client", "device_manager") |
| message | TEXT | Log message |

**Indexes:**
- PRIMARY KEY on `id`

## Data Flow

### Uplink Message Flow (TTN → Database)

```
1. TTN sends MQTT message
   ↓
2. TTNClient._on_message() callback receives message
   ↓
3. TTNClient._parse_payload() decodes binary payload
   ↓
4. DeviceManager.handle_uplink_message() processes data
   ↓
5. Database functions called:
   - insert_rssi_reading() for RSSI data
   - update_device_uplink() for device metadata
   - insert_device_image() for images
   ↓
6. Data persisted to elderly_monitoring.db
```

### API Request Flow (Frontend → Database)

```
1. Frontend makes HTTP request to Flask API
   ↓
2. Flask route handler (app.py) receives request
   ↓
3. DeviceManager method called (e.g., get_all_devices())
   ↓
4. Database query executed:
   - get_all_devices() → SELECT * FROM devices
   - get_latest_rssi_readings() → SELECT ... FROM rssi_readings
   ↓
5. JSON response returned to frontend
```

## Database Functions

All database operations are centralized in `database.py`. Use these functions instead of direct SQL queries.

### Device Management
- `insert_device(device_id, patient_name, room, ...)`: Create new device
- `get_device(device_id)`: Get device by ID
- `get_all_devices()`: Get all devices
- `update_device_uplink(device_id, rssi, battery_level, ...)`: Update device on uplink
- `update_device_location(device_id, x, y, z)`: Update calculated location
- `update_device_status(device_id, status)`: Update device status
- `update_device_battery(device_id, battery_level)`: Update battery level

### RSSI Management
- `insert_rssi_reading(device_id, node_id, rssi, timestamp)`: Store RSSI measurement
- `get_latest_rssi_readings(device_id)`: Get latest RSSI from each node for a device
- `get_rssi_history(device_id, minutes)`: Get RSSI history for time window

### Stationary Node Management
- `insert_stationary_node(node_id, name, type, x, y, z, status)`: Add node
- `get_stationary_node(node_id)`: Get node by ID
- `get_all_stationary_nodes()`: Get all nodes
- `get_active_stationary_nodes()`: Get only active nodes
- `update_stationary_node_status(node_id, status)`: Update node status

### Image Management
- `insert_device_image(device_id, image_path, size_bytes, resolution)`: Store image metadata
- `get_latest_image(device_id)`: Get most recent image for device

### Health Data
- `update_device_health(device_id, heart_rate, temperature)`: Update vital signs

## Common Queries

### Get Latest RSSI for All Devices
```python
from database import get_all_devices, get_latest_rssi_readings

devices = get_all_devices()
for device in devices:
    rssi_data = get_latest_rssi_readings(device['device_id'])
    print(f"{device['device_id']}: {rssi_data}")
```

### Get Device Location History
```python
from database import get_rssi_history

# Get last 10 minutes of RSSI data
rssi_history = get_rssi_history('ed-1', minutes=10)
```

### Check Device Status
```python
from database import get_device

device = get_device('ed-1')
print(f"Status: {device['status']}")
print(f"Battery: {device['battery_level']}%")
print(f"Last seen: {device['last_uplink']}")
```

### Find Low Battery Devices
```sql
SELECT device_id, patient_name, battery_level 
FROM devices 
WHERE battery_level < 20 
ORDER BY battery_level ASC;
```

### Get RSSI Trend
```sql
SELECT 
    device_id,
    node_id,
    AVG(rssi) as avg_rssi,
    COUNT(*) as reading_count
FROM rssi_readings
WHERE timestamp > datetime('now', '-1 hour')
GROUP BY device_id, node_id;
```

## Maintenance

### Backup Database
```bash
# Create timestamped backup
cp elderly_monitoring.db "elderly_monitoring_backup_$(date +%Y%m%d_%H%M%S).db"

# Or use SQLite backup command
sqlite3 elderly_monitoring.db ".backup elderly_monitoring_backup.db"
```

### Vacuum Database (Optimize)
```bash
sqlite3 elderly_monitoring.db "VACUUM;"
```

### Prune Old RSSI Data
```sql
-- Delete RSSI readings older than 7 days
DELETE FROM rssi_readings 
WHERE timestamp < datetime('now', '-7 days');
```

### Check Database Integrity
```bash
sqlite3 elderly_monitoring.db "PRAGMA integrity_check;"
```

## Troubleshooting

### Database Locked Error
**Symptom:** `sqlite3.OperationalError: database is locked`

**Cause:** Multiple processes accessing database simultaneously

**Solution:** The database module uses thread-local connections. Ensure:
- Only one Flask server instance is running
- TTN client and Flask app share the same process
- Use `timeout` parameter when opening connections

### Missing Data
**Symptom:** No RSSI readings showing up

**Check:**
1. Is database initialized? `ls -lh elderly_monitoring.db`
2. Are devices registered? `python query_db.py devices`
3. Is TTN connected? Check `test_integration.py` output
4. Are uplink messages being received? Check Flask logs

### Slow Queries
**Solution:** Ensure indexes exist:
```sql
CREATE INDEX IF NOT EXISTS idx_rssi_timestamp 
ON rssi_readings(timestamp);

CREATE INDEX IF NOT EXISTS idx_rssi_device 
ON rssi_readings(device_id);
```

## Migration from In-Memory Storage

**Previous Architecture:**
- DeviceManager used Python dicts: `self.devices = {}`
- Data lost on server restart
- No historical RSSI data

**Current Architecture:**
- SQLite database with persistent storage
- Full RSSI history with timestamps
- Automatic backups possible via cron

**Breaking Changes:**
- Device data format unchanged (dict → database row conversion is seamless)
- API responses remain identical
- Frontend code requires no changes

## Performance Notes

- **Database Size:** ~10 KB base + ~40 bytes per RSSI reading
- **Expected Growth:** With 4 devices × 4 nodes × 1 reading/minute = 960 readings/hour = 37 KB/hour
- **Recommended Retention:** 7 days (~6 MB) or implement rolling deletion
- **Query Performance:** Indexed timestamps allow sub-millisecond queries on 100K+ records

## Security Considerations

- **File Permissions:** Database file should be readable only by server user
  ```bash
  chmod 640 elderly_monitoring.db
  chown www-data:www-data elderly_monitoring.db
  ```
  
- **SQL Injection:** All database functions use parameterized queries (safe)
- **Backup Encryption:** Consider encrypting backups if they contain PHI (patient health information)

## Related Files

- `database.py` - Database module with all CRUD operations
- `init_db.py` - Database initialization script
- `query_db.py` - Command-line query tool
- `device_manager.py` - Business logic layer (uses database.py)
- `app.py` - Flask API (uses device_manager.py)
- `ttn_integration.py` - TTN MQTT client (feeds data to device_manager.py)
