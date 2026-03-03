# TTN Integration - Quick Start

## ✅ Integration Complete!

Your Flask application server has been successfully integrated with The Things Network (TTN).

## 📁 New Files Created

1. **`ttn_integration.py`** - Handles MQTT communication with TTN
2. **`device_manager.py`** - Manages device state and real-time data
3. **`INTEGRATION_GUIDE.md`** - Comprehensive integration documentation
4. **`test_integration.py`** - Test script for verifying the integration

## 🔧 Files Modified

1. **`app.py`** - Updated to use TTN integration instead of dummy data
2. **`requirements.txt`** - Added new dependencies (paho-mqtt, Pillow, requests)

## 🚀 Quick Start

### 1. Virtual Environment Setup (First Time Only)
```bash
cd "/home/yztan120/Application Server"
python3 -m venv venv
venv/bin/pip install Flask Werkzeug Jinja2 paho-mqtt requests
```

### 2. Initialize Database (First Time Only)
```bash
venv/bin/python init_db.py
```

This creates `elderly_monitoring.db` with:
- Device table (ed-1, ed-2, ed-3, ed-4)
- Stationary nodes (gateway, sn1, sn2, sn3)
- RSSI readings table
- Images metadata table

### 3. Test the Integration
```bash
cd "/home/yztan120/Application Server"
venv/bin/python test_integration.py
```

This will:
- Connect to TTN
- Show connected devices  
- Test sending a downlink command
- Listen for uplink messages

### 4. Run the Web Server

**Option A: Using the helper script (auto-initializes DB)**
```bash
./run_server.sh
```

**Option B: Manually**
```bash
cd "/home/yztan120/Application Server"
venv/bin/python app.py
```

Access the dashboard at: **http://localhost:8080**

## 📊 Device Mapping

Your TTN devices are automatically mapped:

| Device ID | Patient Name      | Room |
|-----------|-------------------|------|
| ed-1      | Margaret Smith    | 101  |
| ed-2      | John Anderson     | 102  |
| ed-3      | Evelyn Roberts    | 103  |
| ed-4      | Robert Chen       | 104  |

## 🔄 How It Works

```
LoRa Devices → TTN → MQTT → ttn_integration.py 
                                    ↓
                              device_manager.py
                                    ↓
                                 app.py ← Dashboard (Browser)
```

## 📡 Supported Operations

### From Dashboard:
1. **Request Image** - Sends downlink command `0x01` to device
2. **Locate Device** - Sends downlink command `0x02` for RSSI ping
3. **View Images** - Displays captured images from devices
4. **Monitor Status** - Real-time device location, battery, health metrics

### Uplink Messages Handled:
1. **RSSI Data** (0x01) - Updates signal strength readings
2. **Images** (0x02) - Saves captured images to disk
3. **Health Metrics** (0x03) - Updates heart rate and temperature

## 🔍 API Endpoints

All original endpoints work, plus new ones:

- `GET /api/ttn-status` - Check TTN connection
- `POST /api/update-rssi/<device_id>/<node_id>/<rssi>` - Manual RSSI update
- `POST /api/update-battery/<device_id>/<level>` - Manual battery update

## 📝 Next Steps

1. **Power on your LoRa devices** (ed-1, ed-2, ed-3, ed-4)
2. **Monitor TTN Console** to verify devices are transmitting
3. **Run test_integration.py** to verify connectivity
4. **Start the web server** with `python app.py`
5. **Access the dashboard** at http://localhost:8080

## 🐛 Troubleshooting

### Connection Issues
```bash
# Check TTN connectivity
ping au1.cloud.thethings.network

# Test MQTT port
telnet au1.cloud.thethings.network 1883
```

### View Logs
When running the app, you'll see detailed logs:
```
INFO - ✓ Connected to The Things Network
INFO - ✓ Subscribed to: v3/iot-sit-group26-project-2026@ttn/devices/+/up
INFO - 📡 Message received from device: ed-1
```

### Common Issues
- **"TTN connection pending"** → Check internet & credentials
- **"No uplink messages"** → Verify devices are powered and joined
- **"Downlink failed"** → Check API key permissions in TTN Console

## �️ Database Management

### View Database Contents
```bash
# Interactive menu
venv/bin/python query_db.py

# Quick queries
venv/bin/python query_db.py devices    # Show all devices
venv/bin/python query_db.py nodes      # Show stationary nodes
venv/bin/python query_db.py rssi       # Recent RSSI readings
venv/bin/python query_db.py summary    # Latest RSSI per device
venv/bin/python query_db.py stats      # Database statistics
venv/bin/python query_db.py all        # Show everything
```

### Backup Database
```bash
# Create timestamped backup
./backup_db.sh

# Backups are stored in backups/ directory
# Automatic cleanup: keeps backups for 7 days
```

### Direct SQL Access
```bash
sqlite3 elderly_monitoring.db

# Example queries
sqlite> SELECT * FROM devices;
sqlite> SELECT * FROM rssi_readings ORDER BY timestamp DESC LIMIT 10;
sqlite> .schema devices
sqlite> .exit
```

### Re-initialize Database (Caution: Deletes All Data)
```bash
rm elderly_monitoring.db
venv/bin/python init_db.py
```

**Documentation:** See [DATABASE.md](DATABASE.md) for complete schema and usage.

## �📚 Documentation

- **Full Guide:** [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md)
- **Original README:** [README.md](README.md)
- **Test Script:** `python test_integration.py`

## 🔐 Security Note

Your TTN API key is currently hardcoded. For production, use environment variables:

```bash
export TTN_APP_ID="iot-sit-group26-project-2026"
export TTN_API_KEY="your-api-key"
export TTN_REGION="au1"
```

---

**Ready to test?** Run `python test_integration.py` to verify everything works!
