"""
Flask Application Server for Elderly Home Monitoring System
RSSI-Based Localization with Server-Orchestrated Wi-Fi Hopping
"""

from flask import Flask, render_template, jsonify, request, send_from_directory
from datetime import datetime
import json
import os
import logging
import math  # Added for distance calculation
import threading
import uuid
from ttn_integration import get_ttn_client, TTNClient, AnchorPoint
from device_manager import get_device_manager, DeviceManager
from database import init_database, get_device_last_updated, get_device_last_uplink, get_latest_rssi_with_timestamps

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-in-production'

# Configure upload folder for images
UPLOAD_FOLDER = 'static/images/captured'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Initialize database
logger.info("Initializing database...")
init_database('elderly_monitoring.db')
logger.info("✓ Database initialized")

# Initialize device manager
device_manager: DeviceManager = get_device_manager(UPLOAD_FOLDER)

# Configure anchor points for RSSI trilateration (30m × 40m facility)
# Gateway at center, 3 SNs forming equilateral triangle 5m away, 1m lower
FACILITY_ANCHORS = {
    'gateway': AnchorPoint('gateway', 'LoRaWAN Gateway (Center)', 15.0, 20.0, 2.5),
    'sn1': AnchorPoint('sn1', 'Stationary Node 1 (East)', 20.0, 20.0, 1.5),
    'sn2': AnchorPoint('sn2', 'Stationary Node 2 (Northwest)', 12.5, 24.33, 1.5),
    'sn3': AnchorPoint('sn3', 'Stationary Node 3 (Southwest)', 12.5, 15.67, 1.5)
}

# Initialize TTN client with callback
def on_ttn_message(device_id: str, payload_data: dict, metadata: dict):
    """Callback for TTN uplink messages"""
    device_manager.handle_uplink_message(device_id, payload_data, metadata)

ttn_client: TTNClient = get_ttn_client(
    on_message_callback=on_ttn_message,
    anchors=FACILITY_ANCHORS,
    auto_localize=True
)

# Start TTN client
logger.info("Starting TTN MQTT client...")
ttn_client.start()

if ttn_client.is_connected():
    logger.info("✓ Application Server ready - TTN connected")
else:
    logger.warning("⚠ Application Server started but TTN connection pending")


@app.route('/')
def index():
    """Main dashboard with 3D topology visualization"""
    return render_template('dashboard.html')


@app.route('/api/devices')
def get_devices():
    """Get all end devices with their current status and location"""
    devices = device_manager.get_all_devices()
    return jsonify({
        'success': True,
        'devices': devices,
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/stationary-nodes')
def get_nodes():
    """Get all stationary nodes (anchors) with fixed coordinates"""
    nodes = device_manager.get_stationary_nodes()
    return jsonify({
        'success': True,
        'nodes': nodes,
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/device/<device_id>')
def get_device(device_id):
    """Get specific device information"""
    device = device_manager.get_device_by_id(device_id)
    if device:
        return jsonify({
            'success': True,
            'device': device
        })
    return jsonify({
        'success': False,
        'error': 'Device not found'
    }), 404


@app.route('/api/request-image/<device_id>', methods=['POST'])
def request_image(device_id):
    """
    Trigger image capture from a specific device
    This initiates the server-orchestrated Wi-Fi hopping process
    """
    # Check if device exists
    device = device_manager.get_device_by_id(device_id)
    if not device:
        return jsonify({
            'success': False,
            'error': 'Device not found'
        }), 404
    
    if not device.get('wifi_capable', False):
        return jsonify({
            'success': False,
            'error': 'Device does not support Wi-Fi connectivity'
        }), 400
    
    # Calculate relay path
    relay_path = device_manager.calculate_relay_path(device_id)
    
    # Send downlink command via TTN
    success = ttn_client.send_image_capture_command(device_id)
    
    if success:
        # If relay is needed, send Wi-Fi hotspot commands
        if len(relay_path) > 2:  # More than just [device, gateway]
            for relay_device_id in relay_path[1:-1]:  # Exclude first and last
                ttn_client.send_wifi_hotspot_command(relay_device_id, enable=True)
        
        return jsonify({
            'success': True,
            'message': f'Image request sent to device {device_id}',
            'device_id': device_id,
            'relay_path': relay_path,
            'estimated_time': f'{len(relay_path) * 3} seconds'
        })
    
    return jsonify({
        'success': False,
        'error': 'Failed to send downlink command to device'
    }), 500


@app.route('/api/device/<device_id>/image')
def get_image(device_id):
    """Get the latest captured image from a device"""
    image_data = device_manager.get_device_image(device_id)
    
    if image_data:
        return jsonify({
            'success': True,
            'image_url': image_data['url'],
            'timestamp': image_data['timestamp'],
            'device_id': device_id
        })
    
    return jsonify({
        'success': False,
        'error': 'No image available for this device'
    }), 404


@app.route('/view-image/<device_id>')
def view_image(device_id):
    """Render page to view device image"""
    device = device_manager.get_device_by_id(device_id)
    if not device:
        return "Device not found", 404
    
    return render_template('view_image.html', device=device)


@app.route('/api/locate/<device_id>', methods=['POST'])
def locate_device(device_id):
    """
    Initiate location request for a specific device
    This triggers RSSI trilateration process
    """
    device = device_manager.get_device_by_id(device_id)
    
    if not device:
        return jsonify({
            'success': False,
            'error': 'Device not found'
        }), 404
    
    # Send downlink command to device to broadcast RSSI ping
    success = ttn_client.send_location_request_command(device_id)
    
    if success:
        return jsonify({
            'success': True,
            'message': f'Location request sent to device {device_id}',
            'status': 'waiting_for_rssi_data',
            'current_location': device.get('location', {})
        })
    
    return jsonify({
        'success': False,
        'error': 'Failed to send location request command'
    }), 500


@app.route('/health')
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/ttn-status')
def ttn_status():
    """Get TTN connection status"""
    return jsonify({
        'connected': ttn_client.is_connected(),
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/update-rssi/<device_id>/<node_id>/<int:rssi>', methods=['POST'])
def update_rssi(device_id, node_id, rssi):
    """
    Manual endpoint to update RSSI readings
    (Can be used by stationary nodes to report RSSI)
    """
    device_manager.update_rssi_reading(device_id, node_id, rssi)
    return jsonify({
        'success': True,
        'message': f'RSSI updated for {device_id} -> {node_id}: {rssi} dBm'
    })


@app.route('/api/localize/<device_id>', methods=['POST'])
def localize(device_id):
    """
    Calculate device location using RSSI-based trilateration.
    Calculates 3D Euclidean distance from the Gateway using the localized coordinates.
    
    Retrieves latest RSSI readings from all anchor nodes and performs
    weighted least-squares trilateration to estimate device position.
    
    Query params:
        - use_2d: If 'true', assumes device at fixed height (1.2m)
    
    Returns:
        {
            'success': bool,
            'position': {'x': float, 'y': float, 'z': float},
            'distance_from_gateway': float,  # Distance in meters
            'residual_error': float,         # Fitting error in meters
            'confidence': float,             # 0.0-1.0
            'accuracy': float,               # Estimated accuracy
            'num_measurements': int,
            'timestamp': str,
            'message': str
        }
    """
    use_2d = request.args.get('use_2d', 'false').lower() == 'true'
    
    result = device_manager.localize_device(device_id, use_2d=use_2d)
    
    if result:
        # Extract the device's newly estimated position
        pos = result['position']
        
        # Get the Gateway's exact coordinates from your config
        gateway = FACILITY_ANCHORS['gateway']
        
        # Calculate 3D Euclidean distance from Gateway
        distance_from_gateway = math.sqrt(
            (pos['x'] - gateway.x)**2 + 
            (pos['y'] - gateway.y)**2 + 
            (pos['z'] - gateway.z)**2
        )
        
        return jsonify({
            'success': True,
            'position': pos,
            'distance_from_gateway': round(distance_from_gateway, 2),
            'residual_error': result['residual_error'],
            'confidence': result['confidence'],
            'accuracy': result['accuracy'],
            'num_measurements': result['num_measurements'],
            'timestamp': result['timestamp'],
            'message': f"Device {device_id} localized successfully. Distance from gateway: {round(distance_from_gateway, 2)}m"
        })
    else:
        return jsonify({
            'success': False,
            'error': f'Failed to localize device {device_id}. Ensure RSSI readings exist from at least 3 anchor nodes.'
        }), 400


@app.route('/api/update-battery/<device_id>/<int:battery_level>', methods=['POST'])
def update_battery(device_id, battery_level):
    """Manual endpoint to update battery level"""
    device_manager.update_battery_level(device_id, battery_level)
    return jsonify({
        'success': True,
        'message': f'Battery level updated for {device_id}: {battery_level}%'
    })


@app.route('/api/update-all-locations', methods=['POST'])
def update_all_locations():
    """Start a background job to update locations for all devices.

    Returns immediately with a `job_id`. Use `/api/update-all-locations/status/<job_id>`
    to poll for progress and final results.
    """
    timeout = 60
    if request.is_json:
        timeout = int(request.json.get('timeout', timeout))
    else:
        try:
            timeout = int(request.args.get('timeout', timeout))
        except Exception:
            pass

    devices = device_manager.get_all_devices()
    device_ids = [d['id'] for d in devices]

    if not device_ids:
        return jsonify({'success': True, 'message': 'No devices registered', 'devices': []})

    # Create job
    job_id = str(uuid.uuid4())
    # devices map stores per-device verbose info
    devices_map = {d: {'status': 'queued', 'logs': []} for d in device_ids}

    JOBS[job_id] = {
        'status': 'queued',
        'requested_at': datetime.now().isoformat(),
        'timeout_seconds': timeout,
        'device_ids': device_ids,
        'devices': devices_map,
        'updated_devices': [],
        'pending_devices': device_ids[:],
        'localization': {},
        'logs': [],
        'error': None
    }

    # Start worker thread
    thread = threading.Thread(target=_run_update_all_job, args=(job_id,), daemon=True)
    thread.start()

    # Ensure job shows as in-progress immediately and record startup log
    JOBS[job_id]['status'] = 'in_progress'
    JOBS[job_id].setdefault('logs', []).append(f"Worker thread started at {datetime.now().isoformat()}")
    JOBS[job_id]['thread_info'] = {'daemon': thread.daemon}

    return jsonify({'success': True, 'job_id': job_id})


# In-memory job store: job_id -> job info
JOBS = {}


def _run_update_all_job(job_id: str):
    """Worker to perform update-all-locations job and update JOBS dict."""
    job = JOBS.get(job_id)
    if not job:
        return

    # record that worker has begun execution (helps diagnose missing thread runs)
    try:
        job.setdefault('logs', []).append(f"Worker executing function _run_update_all_job at {datetime.now().isoformat()}")
    except Exception:
        logger.exception('Failed to append starting log for job')

    job['status'] = 'in_progress'
    start_time = datetime.fromisoformat(job['requested_at'])
    timeout = job.get('timeout_seconds', 60)

    # Sequential per-device processing: send request to one device,
    # wait up to per-device timeout for an uplink, then localize and continue.
    import time
    from datetime import timedelta

    per_device_timeout = 60  # seconds per device (increased to allow downlink + RSSI)
    updated = []
    remaining = []

    try:
        # Round-robin retry loop: keep trying timed-out devices until
        # either all devices succeed or overall job timeout is reached.
        pending = job['device_ids'][:]
        job['pending_devices'] = pending[:]
        delay_between_devices = 1  # seconds between starting each device (short to avoid long blocking)

        # Ensure overall deadline allows sequential per-device waits and retries.
        # If the caller provided a small overall timeout, extend it to at least
        # accommodate one pass over devices with per-device timeouts and max attempts.
        max_attempts = 3
        estimated_needed = per_device_timeout * len(pending) * max_attempts
        effective_timeout = max(timeout, estimated_needed + 10)
        job.setdefault('logs', []).append(f"Effective overall timeout set to {effective_timeout}s (requested {timeout}s, estimated needed {estimated_needed}s)")
        deadline = start_time + timedelta(seconds=effective_timeout)

        max_attempts = 3

        # Sequential multi-pass processing:
        # For each attempt round, iterate devices one-by-one, send downlink,
        # wait up to per_device_timeout for RSSI, then move to next device.
        # After finishing a full pass, retry timed-out devices up to max_attempts.
        for attempt_round in range(1, max_attempts + 1):
            if not pending or datetime.now() >= deadline:
                break

            logger.info(f"Job {job_id}: starting attempt round {attempt_round} for {len(pending)} devices")

            # iterate a copy to allow modifying pending within loop
            for did in list(pending):
                if datetime.now() >= deadline:
                    break

                dev = job['devices'].setdefault(did, {'status': 'queued', 'logs': []})
                if dev.get('status') == 'localized' or dev.get('status') == 'abandoned':
                    if did in pending:
                        pending.remove(did)
                    continue

                # Start the attempt for this device
                req_time = datetime.now()
                dev['status'] = 'requested'
                dev['requested_at'] = req_time.isoformat()
                dev.setdefault('attempts', 0)
                dev['attempts'] += 1
                dev.setdefault('logs', []).append(f"Attempt #{dev['attempts']} start at {req_time.isoformat()}")

                # Send downlink (block while sending only)
                try:
                    logger.info(f"Job {job_id}: sending location request to {did} (attempt {dev['attempts']})")
                    ttn_client.send_location_request_command(did)
                    job.setdefault('logs', []).append(f"Sent location request to {did} at {req_time.isoformat()}")
                    # record that we're now waiting for RSSI from SNs for this device
                    job.setdefault('logs', []).append(f"Waiting up to {per_device_timeout}s for RSSI from 3 SNs for {did} (requested at {req_time.isoformat()})")
                except Exception:
                    logger.exception(f"Failed sending location request to {did}")
                    dev.setdefault('logs', []).append('Request failed to send')
                    dev['status'] = 'request_failed'
                    job['devices'][did] = dev
                    # continue to next device in this round
                    continue

                # Wait up to per_device_timeout for SN readings
                device_deadline = req_time + timedelta(seconds=per_device_timeout)
                got_3sn = False
                seen_sn = set()
                last_heartbeat = datetime.now()
                while datetime.now() < device_deadline and datetime.now() < deadline:
                    try:
                        records = get_latest_rssi_with_timestamps(did)
                    except Exception as db_ex:
                        logger.exception(f"DB error while polling RSSI for {did}: {db_ex}")
                        job.setdefault('logs', []).append(f"DB error polling RSSI for {did}: {db_ex}")
                        # short sleep and continue; don't let DB issues block the loop permanently
                        time.sleep(1)
                        continue

                    # periodic heartbeat to show progress during long waits
                    if (datetime.now() - last_heartbeat).total_seconds() >= 10:
                        hb = f"Waiting for RSSI for {did}: still pending at {datetime.now().isoformat()}"
                        dev.setdefault('logs', []).append(hb)
                        job.setdefault('logs', []).append(hb)
                        last_heartbeat = datetime.now()

                    sn_ts = []
                    for sn in ['sn1', 'sn2', 'sn3']:
                        rec = records.get(sn) or {}
                        ts = rec.get('timestamp')
                        if ts:
                            try:
                                ts_dt = datetime.fromisoformat(ts)
                            except Exception:
                                try:
                                    ts_dt = datetime.strptime(ts, '%Y-%m-%d %H:%M:%S')
                                except Exception:
                                    ts_dt = None
                        else:
                            ts_dt = None

                        # Log when this SN first returns a timestamp after the request
                        if ts_dt and ts_dt > req_time and sn not in seen_sn:
                            dev.setdefault('logs', []).append(f"{sn} reported RSSI at {ts_dt.isoformat()}")
                            seen_sn.add(sn)

                        sn_ts.append(ts_dt)

                    if all((t is not None and t > req_time) for t in sn_ts):
                        got_3sn = True
                        latest_ts = max(t for t in sn_ts if t is not None)
                        dev['last_updated'] = latest_ts.isoformat()
                        dev.setdefault('logs', []).append(f"RSSI from 3 SNs received at {latest_ts.isoformat()}")

                        # attempt localization
                        try:
                            res = device_manager.localize_device(did)
                            job['localization'].setdefault(did, res)
                            if res:
                                dev.setdefault('logs', []).append('Localization succeeded')
                                dev['status'] = 'localized'
                                updated.append(did)
                                if did in pending:
                                    pending.remove(did)
                            else:
                                dev.setdefault('logs', []).append('Localization returned no result')
                                dev['status'] = 'localization_failed'
                        except Exception:
                            logger.exception(f"Localization failed for {did}")
                            dev.setdefault('logs', []).append('Localization exception')
                            dev['status'] = 'localization_failed'

                        break

                    time.sleep(1)

                # exited wait loop; log reason
                if got_3sn:
                    job.setdefault('logs', []).append(f"Device {did} reported 3 SNs by {datetime.now().isoformat()}")
                else:
                    job.setdefault('logs', []).append(f"Device {did} did NOT report 3 SNs within {per_device_timeout}s (now {datetime.now().isoformat()})")

                if not got_3sn:
                    # this attempt timed out for the device; mark and either retry or abandon
                    dev.setdefault('logs', []).append(f"No 3-SN uplink within {per_device_timeout}s; attempt #{dev.get('attempts',0)}")
                    job.setdefault('logs', []).append(f"Job {job_id}: device {did} attempt #{dev.get('attempts',0)} timed out at {datetime.now().isoformat()}")
                    if dev.get('attempts', 0) >= max_attempts:
                        dev.setdefault('logs', []).append('Max attempts reached; marking as abandoned')
                        dev['status'] = 'abandoned'
                        if did in pending:
                            pending.remove(did)
                    else:
                        dev['status'] = 'timed_out'
                    # persist device and immediately continue to next device
                    job['devices'][did] = dev
                    continue

                # record attempt end
                dev.setdefault('logs', []).append(f"Attempt #{dev.get('attempts')} end at {datetime.now().isoformat()}")
                job['devices'][did] = dev

                # small delay between devices to avoid TTN rate limits
                sleep_until = datetime.now() + timedelta(seconds=delay_between_devices)
                while datetime.now() < sleep_until and datetime.now() < deadline:
                    time.sleep(0.5)

            # End of attempt_round; update job-level lists and prepare next round
            job['updated_devices'] = updated[:]
            job['pending_devices'] = pending[:]

        # Finished attempts (either pending empty or overall deadline expired)

        # Finished attempts (either pending empty or overall deadline expired)
        job['localization'] = job.get('localization', {})
        if pending:
            job['status'] = 'partial_complete'
            job['error'] = f"Timed out for {len(pending)} devices"
        else:
            job['status'] = 'done'
        job['completed_at'] = datetime.now().isoformat()

    except Exception as e:
        logger.exception('Error running update-all job')
        job['status'] = 'failed'
        job['error'] = str(e)
        job['completed_at'] = datetime.now().isoformat()


@app.route('/api/update-all-locations/status/<job_id>')
def get_update_all_status(job_id):
    job = JOBS.get(job_id)
    if not job:
        return jsonify({'success': False, 'error': 'Job not found'}), 404
    return jsonify({'success': True, 'job': job})


@app.route('/api/update-all-locations/jobs')
def list_update_all_jobs():
    """Return a summary list of recent update-all jobs."""
    summaries = []
    for jid, job in JOBS.items():
        summaries.append({
            'job_id': jid,
            'status': job.get('status'),
            'requested_at': job.get('requested_at'),
            'timeout_seconds': job.get('timeout_seconds'),
            'num_devices': len(job.get('device_ids', [])),
            'updated_count': len(job.get('updated_devices', [])),
            'completed_at': job.get('completed_at')
        })
    return jsonify({'success': True, 'jobs': summaries})


@app.route('/api/device-job-status/<device_id>')
def device_job_status(device_id):
    """Return job statuses that involve the given device_id."""
    results = []
    for jid, job in JOBS.items():
        if device_id in job.get('device_ids', []):
            dev_info = job.get('devices', {}).get(device_id, {})
            results.append({
                'job_id': jid,
                'job_status': job.get('status'),
                'device_status': dev_info.get('status'),
                'device_logs': dev_info.get('logs', []),
                'requested_at': job.get('requested_at'),
                'completed_at': job.get('completed_at')
            })
    # sort by requested_at desc
    results.sort(key=lambda x: x.get('requested_at') or '', reverse=True)
    return jsonify({'success': True, 'device_jobs': results})


@app.route('/api/locate-job/<device_id>', methods=['POST'])
def locate_job(device_id):
    """Create a short-lived job to request location from a single device.

    Returns job_id immediately. The worker will send a location request and
    wait for an uplink (RSSI) or timeout, then attempt localization (best-effort).
    """
    timeout = 30
    if request.is_json:
        timeout = int(request.json.get('timeout', timeout))
    else:
        try:
            timeout = int(request.args.get('timeout', timeout))
        except Exception:
            pass

    # ensure device exists
    device = device_manager.get_device_by_id(device_id)
    if not device:
        return jsonify({'success': False, 'error': 'Device not found'}), 404

    # Create job struct similar to update-all
    job_id = str(uuid.uuid4())
    devices_map = {device_id: {'status': 'queued', 'logs': []}}
    JOBS[job_id] = {
        'status': 'queued',
        'requested_at': datetime.now().isoformat(),
        'timeout_seconds': timeout,
        'device_ids': [device_id],
        'devices': devices_map,
        'updated_devices': [],
        'pending_devices': [device_id],
        'localization': {},
        'logs': [],
        'error': None
    }

    thread = threading.Thread(target=_run_update_all_job, args=(job_id,), daemon=True)
    thread.start()

    return jsonify({'success': True, 'job_id': job_id})


if __name__ == '__main__':
    try:
        # Run in debug mode for development
        # In production, use a proper WSGI server like Gunicorn
        logger.info("Starting Flask web server on 0.0.0.0:8080")
        app.run(host='0.0.0.0', port=8080, debug=True)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        # Cleanup
        ttn_client.stop()
        logger.info("Application stopped")