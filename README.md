# IOT_GRP_26

Elderly home monitoring dashboard with:
- Flask web server
- TTN MQTT integration for LoRa uplinks/downlinks
- RSSI-based localization
- SQLite persistence
- Web UI for live device status and captured images

## Features

- Live dashboard for end devices with battery, health metrics, and latest uplink timestamps
- Automatic TTN MQTT ingest for uplinks with callback processing into persistent storage
- RSSI collection from gateway and anchors, with API-triggered localization
- 2D/3D localization support with confidence, residual error, and accuracy metrics
- Device image pipeline with request/response tracking and archive bridge endpoints
- Job-based multi-device update workflow for coordinated location refresh
- SQLite-backed persistence for devices, RSSI history, and image metadata
- REST endpoints for operations, diagnostics, and health checks

This guide is designed so you can run the project on Windows, macOS, Linux, or Raspberry Pi with the same flow.

## 1. Requirements

- Python 3.9+ (3.10 or 3.11 recommended)
- pip
- Git
- Network access (if using live TTN integration)

Optional:
- sqlite3 CLI for manual database checks

## 2. Clone Repository

```bash
git clone <your-repo-url>
cd IOT_GRP_26
```

## 3. Set Up Virtual Environment

### Windows (PowerShell)

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If PowerShell blocks script execution:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1
```

### Windows (Command Prompt)

```bat
python -m venv venv
venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### macOS / Linux / Raspberry Pi

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 4. Initialize Database (Recommended on First Run)

```bash
python init_db.py
```

Notes:
- The default database file is `elderly_monitoring.db` in the project root.
- Override with `IOT_DB_PATH` if needed.

## 5. Start the Application

```bash
python app.py
```

Default server endpoint:
- http://localhost:8080

The app binds to `0.0.0.0`, which allows access from other devices on the same network.

## 6. Access from Any Device on Your LAN

If the server machine IP is `192.168.1.20`, open this on another laptop/phone/tablet:

- http://192.168.1.20:8080

If remote devices cannot connect, verify:
- Both devices are on the same LAN/subnet
- Firewall allows inbound TCP 8080 on the server machine
- VPN or guest network isolation is not blocking local traffic

## 7. Environment Variables

Variables used by the app:
- `IOT_DB_PATH`: custom SQLite database path
- `WIFI_HOPPING_ARCHIVE_DIR`: folder watched for incoming image files
- `IMAGE_WATCH_POLL_SECONDS`: image watcher interval in seconds (default `2`)

### Windows (PowerShell)

```powershell
$env:IOT_DB_PATH = "C:\path\to\elderly_monitoring.db"
$env:WIFI_HOPPING_ARCHIVE_DIR = "C:\path\to\archive"
$env:IMAGE_WATCH_POLL_SECONDS = "2"
python app.py
```

### macOS / Linux

```bash
export IOT_DB_PATH="/path/to/elderly_monitoring.db"
export WIFI_HOPPING_ARCHIVE_DIR="/path/to/archive"
export IMAGE_WATCH_POLL_SECONDS="2"
python app.py
```

## 8. TTN Integration Notes

- TTN MQTT client starts automatically when `app.py` starts.
- Credentials are currently configured in `ttn_integration.py`.
- For your own deployment, update TTN credentials/region values before production use.

If TTN is unreachable, the web app can still start. Connection status appears in server logs.

## 9. Useful Commands

Run tests:

```bash
pytest
```

Health check endpoint:

```bash
curl http://localhost:8080/health
```

Inspect latest device records in SQLite:

```bash
sqlite3 elderly_monitoring.db "SELECT device_id, status, battery_level, last_uplink FROM devices ORDER BY device_id;"
```

## 10. Troubleshooting

### Import errors

- Make sure the virtual environment is activated
- Reinstall dependencies:

```bash
pip install -r requirements.txt
```

### Port 8080 already in use

- Stop the process currently using port 8080, then start again
- Or change the port in the `app.run(... port=8080 ...)` call in `app.py`

### Raspberry Pi install issues (numpy/pillow)

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Cannot open from another device

- Use host LAN IP, not `localhost`
- Confirm firewall rule for TCP 8080
- Confirm same network/subnet

## 11. Key Files

- `app.py`: Flask entrypoint and API routes
- `ttn_integration.py`: TTN MQTT client and payload parsing
- `device_manager.py`: runtime device state and processing
- `database.py`: SQLite data access layer
- `init_db.py`: DB initialization script
- `templates/`: HTML templates
- `static/`: CSS, JS, captured images
- `guide/`: additional quickstart/integration guides

## 12. Production Notes

- Flask debug server is for development only
- Keep secrets/credentials out of source files
- Deploy behind a production WSGI server and reverse proxy
- Restrict inbound ports to minimum required