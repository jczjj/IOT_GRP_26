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
- `init_db.py` supports `IOT_DB_PATH`, but `app.py` currently initializes `elderly_monitoring.db` directly.

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
- `WIFI_HOPPING_ARCHIVE_DIR`: folder watched for incoming image files
- `IMAGE_WATCH_POLL_SECONDS`: image watcher interval in seconds (default `2`)

Used by initialization scripts:
- `IOT_DB_PATH`: custom SQLite database path for `init_db.py`

### Windows (PowerShell)

```powershell
$env:WIFI_HOPPING_ARCHIVE_DIR = "C:\path\to\archive"
$env:IMAGE_WATCH_POLL_SECONDS = "2"
python app.py
```

### macOS / Linux

```bash
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
# No automated tests are currently checked in this repository.
# If tests are added later, run:
# pytest
```

Job and image-bridge endpoints:

```bash
# Start multi-device localization job
curl -X POST http://localhost:8080/api/update-all-locations

# Check job status
curl http://localhost:8080/api/update-all-locations/jobs

# Single-device job-based localization
curl -X POST http://localhost:8080/api/locate-job/ed-1

# Image bridge diagnostics
curl http://localhost:8080/api/image-bridge-debug
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

## 11. Project File Guide

This section explains what each major file does and when you should edit it.

### Core backend files

- `app.py`
	- Main Flask application.
	- Defines HTTP routes (`/api/...`), starts the TTN client, and coordinates image and localization workflows.
	- Edit this when adding/changing API endpoints or request handling behavior.

- `device_manager.py`
	- Business logic layer used by `app.py`.
	- Handles device state updates, RSSI processing, localization triggers, and image metadata updates.
	- Edit this when changing how incoming data is interpreted or stored as device state.

- `ttn_integration.py`
	- TTN MQTT ingest and downlink helper logic.
	- Parses incoming TTN payloads and forwards structured data into the app callback.
	- Edit this when payload formats, TTN credentials, or MQTT behavior change.

- `database.py`
	- SQLite schema creation and CRUD/query helpers.
	- Single place for SQL table definitions and DB access functions.
	- Edit this when adding columns/tables or changing storage/query behavior.

- `init_db.py`
	- One-time DB initialization and anchor seeding utility.
	- Creates schema and inserts infrastructure/anchor defaults.
	- Run this on first setup (or when rebuilding the database).

### Localization and geometry files

- `anchor_layout.py`
	- Shared source of truth for anchor geometry and localization calibration constants.
	- Defines gateway/anchor IDs, coordinates, path loss parameters, and per-node RSSI offsets.
	- Used by `app.py`, `ttn_integration.py`, and `init_db.py` to keep localization setup consistent.

- `localization.py`
	- RSSI-to-distance math and trilateration utilities (2D/3D localization calculations).
	- Edit this when tuning localization algorithms or confidence/reliability logic.

### Frontend files

- `templates/dashboard.html`
	- Main dashboard page skeleton (server-rendered HTML).

- `templates/view_image.html`
	- Dedicated page for viewing device image history/latest image.

- `static/js/dashboard.js`
	- Frontend controller for API calls, polling, job status updates, and UI interactions.

- `static/js/topology3d.js`
	- 3D visualization logic for anchors/devices and live location display.

- `static/css/style.css`
	- Styling for dashboard, panels, modal, and responsive layout.

### Operational and config files

- `requirements.txt`
	- Python dependencies to install into your virtual environment.

- `run_server.sh`
	- Convenience script to activate `venv`, initialize DB if missing, then run `app.py`.

- `elderly_monitoring.db`
	- Runtime SQLite database file created/used by the application.

### Data flow at a glance

1. TTN uplink arrives in `ttn_integration.py`.
2. Parsed message is passed to callback in `app.py`.
3. `app.py` delegates state updates/localization work to `device_manager.py`.
4. `device_manager.py` reads/writes persistent data through `database.py`.
5. Frontend (`dashboard.js` + `topology3d.js`) polls API routes in `app.py` and renders updates.

## 12. Production Notes

- Flask debug server is for development only
- Keep secrets/credentials out of source files
- Deploy behind a production WSGI server and reverse proxy
- Restrict inbound ports to minimum required