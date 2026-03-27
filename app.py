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
import time
import shutil
import uuid
import requests
from urllib.parse import quote
from anchor_layout import GATEWAY_NODE_ID
from localization import get_default_anchors
from ttn_integration import get_ttn_client, TTNClient
from device_manager import get_device_manager, DeviceManager
from database import init_database, get_connection, insert_device_image, get_device_last_updated, get_device_last_uplink, get_latest_rssi_with_timestamps


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

WIFI_HOPPING_ARCHIVE_DIR = os.environ.get(
    'WIFI_HOPPING_ARCHIVE_DIR',
    '/home/sdn_service/poc/file_transfer/archive'
)
IMAGE_WATCH_POLL_SECONDS = float(os.environ.get('IMAGE_WATCH_POLL_SECONDS', '2'))
WIFI_HOPPING_SERVER_BASE_URL = os.environ.get('WIFI_HOPPING_SERVER_BASE_URL', 'http://127.0.0.1:5000').rstrip('/')

# Shared state for image-bridge watcher and request polling.
IMAGE_BRIDGE_STATE = {
    'lock': threading.RLock(),
    'known_files': set(),
    'known_remote_files': set(),
    'pending_requests': [],
    'last_received_by_device': {}
}

# Initialize database
logger.info("Initializing database...")
init_database('elderly_monitoring.db')
logger.info("✓ Database initialized")

# Initialize device manager
device_manager: DeviceManager = get_device_manager(UPLOAD_FOLDER)

FACILITY_ANCHORS = get_default_anchors()

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


def _normalize_device_id(device_id: str) -> str:
    """Normalize IDs so route params like ed1 map to TTN/database style ed-1."""
    if not device_id:
        return device_id
    lowered = str(device_id).strip().lower()
    if lowered.startswith('ed') and not lowered.startswith('ed-'):
        suffix = lowered[2:]
        if suffix.isdigit():
            return f'ed-{suffix}'
    return lowered


def _register_pending_image_request(device_id: str) -> dict:
    """Track image requests so arriving files can be attributed to the right device."""
    req = {
        'request_id': str(uuid.uuid4()),
        'device_id': device_id,
        'requested_at': datetime.now().isoformat()
    }
    with IMAGE_BRIDGE_STATE['lock']:
        IMAGE_BRIDGE_STATE['pending_requests'].append(req)
    return req


def _pop_pending_request(device_id: str = None, request_id: str = None):
    """Pop a pending image request. If filters are provided, pop matching one."""
    with IMAGE_BRIDGE_STATE['lock']:
        pending = IMAGE_BRIDGE_STATE['pending_requests']
        if not pending:
            return None
        if not device_id and not request_id:
            return pending.pop(0)
        for i, req in enumerate(pending):
            if device_id and req.get('device_id') != device_id:
                continue
            if request_id and req.get('request_id') != request_id:
                continue
            return pending.pop(i)
    return None


def _get_pending_request(device_id: str = None, request_id: str = None):
    """Get a pending request without removing it."""
    with IMAGE_BRIDGE_STATE['lock']:
        for req in IMAGE_BRIDGE_STATE['pending_requests']:
            if device_id and req.get('device_id') != device_id:
                continue
            if request_id and req.get('request_id') != request_id:
                continue
            return dict(req)
    return None


def _extract_archive_timestamp(filename: str):
    """Parse timestamps from names like gatita_YYYYmmdd_HHMMSS.png."""
    base = os.path.basename(filename)
    stem = os.path.splitext(base)[0]
    if '_' not in stem:
        return None
    parts = stem.split('_')
    if len(parts) < 3:
        return None
    ts_raw = f"{parts[-2]}_{parts[-1]}"
    try:
        return datetime.strptime(ts_raw, '%Y%m%d_%H%M%S')
    except Exception:
        return None


def _store_image_bytes_for_request(req: dict, source_name: str, image_bytes: bytes, ext: str):
    """Persist image bytes into dashboard storage and DB for a specific request."""
    device_id = req['device_id']
    request_id = req['request_id']
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    latest_filename = f"{device_id}_latest{ext}"
    ts_filename = f"{device_id}_{ts}{ext}"
    latest_path = os.path.join(app.config['UPLOAD_FOLDER'], latest_filename)
    ts_path = os.path.join(app.config['UPLOAD_FOLDER'], ts_filename)

    with open(ts_path, 'wb') as f:
        f.write(image_bytes)
    with open(latest_path, 'wb') as f:
        f.write(image_bytes)

    size_bytes = len(image_bytes)
    insert_device_image(device_id, latest_path, size_bytes, resolution='Unknown')

    with IMAGE_BRIDGE_STATE['lock']:
        IMAGE_BRIDGE_STATE['last_received_by_device'][device_id] = {
            'request_id': request_id,
            'received_at': datetime.now().isoformat(),
            'image_url': f"/static/images/captured/{latest_filename}",
            'source_file': source_name
        }

    logger.info(
        f"✓ Bridged Wi-Fi image to dashboard for {device_id}: {latest_filename} "
        f"(request {request_id}) source={source_name}"
    )


def _seed_archive_files_once():
    """Mark current archive files as known so only newly arrived files are processed."""
    if not os.path.isdir(WIFI_HOPPING_ARCHIVE_DIR):
        logger.warning(f"Archive directory not found: {WIFI_HOPPING_ARCHIVE_DIR}")
        return
    with IMAGE_BRIDGE_STATE['lock']:
        count = 0
        for name in os.listdir(WIFI_HOPPING_ARCHIVE_DIR):
            full = os.path.join(WIFI_HOPPING_ARCHIVE_DIR, name)
            if os.path.isfile(full):
                IMAGE_BRIDGE_STATE['known_files'].add(name)
                count += 1
    logger.info(f"Seeded {count} existing files as known in archive")


def _ingest_archive_image(filepath: str):
    """Copy newly arrived archive image into dashboard static folder and DB metadata."""
    _, ext = os.path.splitext(filepath)
    ext = ext.lower()
    if ext not in {'.jpg', '.jpeg', '.png', '.webp'}:
        logger.debug(f"Skipping non-image file: {filepath}")
        return

    with IMAGE_BRIDGE_STATE['lock']:
        pending_count = len(IMAGE_BRIDGE_STATE['pending_requests'])
    req = _pop_pending_request()

    if not req:
        logger.warning(f"Image arrived ({os.path.basename(filepath)}) but no pending request! Pending queue size: {pending_count}")
        return

    device_id = req['device_id']
    request_id = req['request_id']
    logger.debug(f"Ingesting image for device {device_id} (request {request_id}): {os.path.basename(filepath)}")

    try:
        with open(filepath, 'rb') as src:
            image_bytes = src.read()
        _store_image_bytes_for_request(req, os.path.basename(filepath), image_bytes, ext)
    except Exception as exc:
        logger.error(f"Failed to ingest archive image {filepath}: {exc}", exc_info=True)


def _pull_latest_archive_image_via_http(device_id: str, request_id: str = None) -> bool:
    """Fallback: fetch newest archive image from central server HTTP endpoints."""
    if not WIFI_HOPPING_SERVER_BASE_URL:
        return False

    req = _get_pending_request(device_id=device_id, request_id=request_id)
    if not req:
        return False

    try:
        list_url = f"{WIFI_HOPPING_SERVER_BASE_URL}/api/files"
        list_resp = requests.get(list_url, timeout=4)
        if list_resp.status_code != 200:
            return False
        names = list_resp.json()
        if not isinstance(names, list) or not names:
            return False
    except Exception as exc:
        logger.debug(f"HTTP fallback list failed: {exc}")
        return False

    requested_at = req.get('requested_at')
    requested_dt = None
    if requested_at:
        try:
            requested_dt = datetime.fromisoformat(requested_at)
        except Exception:
            requested_dt = None

    candidate = None
    with IMAGE_BRIDGE_STATE['lock']:
        known_remote = set(IMAGE_BRIDGE_STATE['known_remote_files'])

    for name in names:
        _, ext = os.path.splitext(name)
        ext = ext.lower()
        if ext not in {'.jpg', '.jpeg', '.png', '.webp'}:
            continue
        if name in known_remote:
            continue
        ts = _extract_archive_timestamp(name)
        if requested_dt and ts and ts < requested_dt:
            continue
        candidate = name
        break

    if not candidate:
        return False

    try:
        file_url = f"{WIFI_HOPPING_SERVER_BASE_URL}/files/{quote(candidate)}"
        file_resp = requests.get(file_url, timeout=8)
        if file_resp.status_code != 200 or not file_resp.content:
            return False

        matched_req = _pop_pending_request(device_id=device_id, request_id=request_id)
        if not matched_req:
            return False

        _, ext = os.path.splitext(candidate)
        _store_image_bytes_for_request(matched_req, f"http:{candidate}", file_resp.content, ext.lower())

        with IMAGE_BRIDGE_STATE['lock']:
            IMAGE_BRIDGE_STATE['known_remote_files'].add(candidate)

        return True
    except Exception as exc:
        logger.error(f"HTTP fallback ingest failed for {candidate}: {exc}", exc_info=True)
        return False


def _image_bridge_watcher():
    """Background watcher that detects newly arrived files from Wi-Fi hopping server."""
    _seed_archive_files_once()
    logger.info(f"Image bridge watcher started on {WIFI_HOPPING_ARCHIVE_DIR}")
    logger.info(f"Archive poll interval: {IMAGE_WATCH_POLL_SECONDS}s")
    while True:
        try:
            if os.path.isdir(WIFI_HOPPING_ARCHIVE_DIR):
                names = sorted(os.listdir(WIFI_HOPPING_ARCHIVE_DIR))
                with IMAGE_BRIDGE_STATE['lock']:
                    known_count = len(IMAGE_BRIDGE_STATE['known_files'])
                    pending_count = len(IMAGE_BRIDGE_STATE['pending_requests'])
                new_count = 0
                for name in names:
                    full = os.path.join(WIFI_HOPPING_ARCHIVE_DIR, name)
                    if not os.path.isfile(full):
                        continue
                    with IMAGE_BRIDGE_STATE['lock']:
                        if name in IMAGE_BRIDGE_STATE['known_files']:
                            continue
                        IMAGE_BRIDGE_STATE['known_files'].add(name)
                        new_count += 1
                    _ingest_archive_image(full)
                if new_count > 0:
                    logger.debug(f"Archive scan: {len(names)} total files, {known_count} known, {new_count} new ingested. Pending requests: {pending_count}")
            else:
                logger.warning(f"Archive directory unavailable: {WIFI_HOPPING_ARCHIVE_DIR}")
            time.sleep(IMAGE_WATCH_POLL_SECONDS)
        except Exception as exc:
            logger.error(f"Image bridge watcher error: {exc}", exc_info=True)
            time.sleep(IMAGE_WATCH_POLL_SECONDS)


threading.Thread(target=_image_bridge_watcher, daemon=True).start()


# Best Path algorithm constants
MAX_DISTANCE = 0.5  # Maximum distance in meters for direct communication
TARGET_NODE = ''  # We want to reach the gateway

def find_best_path(database, target_node):
	# Fetch all devices
	cursor = database.cursor()
	cursor.execute("SELECT device_id, location_x, location_y, location_z FROM devices")
	devices = cursor.fetchall()
	# Build device map
	device_map = {dev[0]: (dev[1], dev[2], dev[3]) for dev in devices}
	device_map['origin'] = (0, 0, 0)
	
	# Build graph with penalty for hops over MAX_DISTANCE
	PENALTY_FACTOR = 10.0
	graph = {}
	for id1, coord1 in device_map.items():
		graph[id1] = {}
		for id2, coord2 in device_map.items():
			if id1 != id2:
				dist = math.sqrt(sum((a-b)**2 for a,b in zip(coord1, coord2)))
				if dist <= MAX_DISTANCE:
					graph[id1][id2] = dist
				else:
					graph[id1][id2] = dist * PENALTY_FACTOR

	import heapq
	start = target_node
	end = 'origin'
	queue = [(0, start, [start])]
	visited = set()
	while queue:
		cost, node, path = heapq.heappop(queue)
		if node in visited:
			continue
		visited.add(node)
		# Always hop directly to origin if within MAX_DISTANCE
		dist_to_origin = math.sqrt(sum((a-b)**2 for a,b in zip(device_map[node], device_map['origin'])))
		if dist_to_origin <= MAX_DISTANCE and node != 'origin':
			return (path[::-1])
		
		if node == end:
			return path[::-1]
		for neighbor, weight in graph[node].items():
			if neighbor not in visited:
				heapq.heappush(queue, (cost + weight, neighbor, [neighbor] + path))
	return []


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
    Trigger image capture from a specific device.
    Runs find_best_path to determine the relay chain, then sends a
    structured downlink to each device in the path.

    Payload format per device (3 bytes):
      Byte 0: 0x02  (always)
      Byte 1: number of remaining hops from this device (len(path) - index)
      Byte 2: 0x00 for the first device (hotspot off / target),
              0x01 for all subsequent relay devices (hotspot on)
    """
    normalized_device_id = _normalize_device_id(device_id)
    effective_device_id = normalized_device_id

    # Check if device exists
    device = device_manager.get_device_by_id(effective_device_id)
    if not device and normalized_device_id != device_id:
        effective_device_id = device_id
        device = device_manager.get_device_by_id(effective_device_id)
    if not device:
        return jsonify({
            'success': False,
            'error': 'Device not found'
        }), 404

    # Run find_best_path using the devices table in the database
    conn = get_connection()
    path = find_best_path(conn, effective_device_id)
    logger.info(f"Best path for {effective_device_id}: {path}")

    if not path:
        return jsonify({
            'success': False,
            'error': 'Could not find a valid path to the gateway'
        }), 500

    # Send a downlink to every device in the path with the correct payload
    results = []
    total = len(path)
    for i, target_dev in enumerate(path):
        hotspot_byte = 0x00 if i == 0 else 0x01
        hop_count_byte = total - i
        payload = bytes([0x02, hop_count_byte, hotspot_byte])
        success = ttn_client.send_downlink(target_dev, payload, fport=2)
        results.append({
            'device_id': target_dev,
            'payload_hex': payload.hex(),
            'success': success
        })
        logger.info(
            f"Downlink to {target_dev}: payload={payload.hex()} success={success}"
        )

    all_ok = all(r['success'] for r in results)
    req = _register_pending_image_request(effective_device_id) if all_ok else None

    if req:
        logger.info(f"📸 Registered pending image request for {effective_device_id} (request_id: {req['request_id']}, path: {path})")
    else:
        logger.warning(f"Failed to register pending request for {effective_device_id} - TTN downlinks failed")

    return jsonify({
        'success': all_ok,
        'message': f'Image request sent along path for device {effective_device_id}',
        'device_id': effective_device_id,
        'path': path,
        'downlinks': results,
        'estimated_time': f'{total * 3} seconds',
        'request_id': req['request_id'] if req else None,
        'requested_at': req['requested_at'] if req else None
    }), 200 if all_ok else 500


@app.route('/api/device/<device_id>/image')
def get_image(device_id):
    """Get the latest captured image from a device"""
    normalized_device_id = _normalize_device_id(device_id)
    effective_device_id = normalized_device_id
    image_data = device_manager.get_device_image(effective_device_id)
    if not image_data and normalized_device_id != device_id:
        effective_device_id = device_id
        image_data = device_manager.get_device_image(effective_device_id)
    
    if image_data:
        return jsonify({
            'success': True,
            'image_url': image_data['url'],
            'timestamp': image_data['timestamp'],
            'size': image_data.get('size'),
            'resolution': image_data.get('resolution'),
            'device_id': effective_device_id
        })
    
    return jsonify({
        'success': False,
        'error': 'No image available for this device'
    }), 404


@app.route('/api/request-image-status/<device_id>')
def request_image_status(device_id):
    """Poll readiness for a just-requested image and return URL immediately when available."""
    normalized_device_id = _normalize_device_id(device_id)
    effective_device_id = normalized_device_id
    request_id = request.args.get('request_id')

    with IMAGE_BRIDGE_STATE['lock']:
        last = IMAGE_BRIDGE_STATE['last_received_by_device'].get(effective_device_id)
        if not last and normalized_device_id != device_id:
            effective_device_id = device_id
            last = IMAGE_BRIDGE_STATE['last_received_by_device'].get(effective_device_id)

    if not last:
        # Fallback: pull from central server HTTP archive if local watcher missed file events.
        pulled = _pull_latest_archive_image_via_http(effective_device_id, request_id=request_id)
        if pulled:
            with IMAGE_BRIDGE_STATE['lock']:
                last = IMAGE_BRIDGE_STATE['last_received_by_device'].get(effective_device_id)
        if not last:
            return jsonify({'success': True, 'ready': False})

    if request_id and last.get('request_id') != request_id:
        return jsonify({'success': True, 'ready': False})

    image_data = device_manager.get_device_image(effective_device_id)
    if not image_data:
        return jsonify({'success': True, 'ready': False})

    return jsonify({
        'success': True,
        'ready': True,
        'device_id': effective_device_id,
        'request_id': last.get('request_id'),
        'received_at': last.get('received_at'),
        'source_file': last.get('source_file'),
        'image_url': image_data['url'],
        'timestamp': image_data.get('timestamp'),
        'size': image_data.get('size'),
        'resolution': image_data.get('resolution')
    })


@app.route('/api/image-bridge-debug')
def image_bridge_debug():
    """Debug endpoint to see image bridge watcher state"""
    with IMAGE_BRIDGE_STATE['lock']:
        pending = []
        for req in IMAGE_BRIDGE_STATE['pending_requests']:
            pending.append({
                'request_id': req['request_id'][:8] + '...',
                'device_id': req['device_id'],
                'requested_at': req['requested_at']
            })
        received_by_device = {}
        for dev_id, info in IMAGE_BRIDGE_STATE['last_received_by_device'].items():
            received_by_device[dev_id] = {
                'request_id': info['request_id'][:8] + '...',
                'received_at': info['received_at'],
                'source_file': info['source_file']
            }

    return jsonify({
        'success': True,
        'archive_dir': WIFI_HOPPING_ARCHIVE_DIR,
        'http_fallback_base_url': WIFI_HOPPING_SERVER_BASE_URL,
        'archive_dir_exists': os.path.isdir(WIFI_HOPPING_ARCHIVE_DIR),
        'poll_interval_seconds': IMAGE_WATCH_POLL_SECONDS,
        'known_files_count': len(IMAGE_BRIDGE_STATE['known_files']),
        'known_files_sample': sorted(list(IMAGE_BRIDGE_STATE['known_files']))[-5:],
        'known_remote_files_count': len(IMAGE_BRIDGE_STATE['known_remote_files']),
        'pending_requests': pending,
        'last_received_by_device': received_by_device,
        'archive_contents': sorted(os.listdir(WIFI_HOPPING_ARCHIVE_DIR))[:20] if os.path.isdir(WIFI_HOPPING_ARCHIVE_DIR) else []
    })


@app.route('/api/image-bridge/push', methods=['POST'])
@app.route('/api/image-bridge/push/', methods=['POST'])
def image_bridge_push():
    """Receive archived image bytes from node0_monitor and ingest immediately."""
    if 'image' not in request.files:
        return jsonify({'success': False, 'error': 'Missing multipart field: image'}), 400

    file_obj = request.files['image']
    if not file_obj or not file_obj.filename:
        return jsonify({'success': False, 'error': 'Empty uploaded file'}), 400

    filename = file_obj.filename
    _, ext = os.path.splitext(filename)
    ext = ext.lower()
    if ext not in {'.jpg', '.jpeg', '.png', '.webp'}:
        return jsonify({'success': False, 'error': 'Unsupported image extension'}), 400

    device_id = request.form.get('device_id')
    request_id = request.form.get('request_id')
    normalized_device_id = _normalize_device_id(device_id) if device_id else None

    req = _pop_pending_request(device_id=normalized_device_id, request_id=request_id)
    if not req:
        with IMAGE_BRIDGE_STATE['lock']:
            pending_count = len(IMAGE_BRIDGE_STATE['pending_requests'])
        return jsonify({
            'success': False,
            'error': 'No pending request available for image ingestion',
            'pending_requests': pending_count
        }), 409

    try:
        image_bytes = file_obj.read()
        if not image_bytes:
            return jsonify({'success': False, 'error': 'Uploaded file has no content'}), 400

        source_name = request.form.get('source_file') or filename
        _store_image_bytes_for_request(req, f"push:{source_name}", image_bytes, ext)
        return jsonify({
            'success': True,
            'device_id': req['device_id'],
            'request_id': req['request_id'],
            'source_file': source_name
        })
    except Exception as exc:
        logger.error(f"Failed to ingest pushed image {filename}: {exc}", exc_info=True)
        return jsonify({'success': False, 'error': str(exc)}), 500


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
            'is_reliable': bool,             # Whether solution meets quality thresholds
            'measurement_validation': str,   # Diagnostic message about RSSI measurements
            'num_measurements': int,
            'timestamp': str,
            'message': str
        }
    """
    use_2d = request.args.get('use_2d', 'true').lower() == 'true'
    
    result = device_manager.localize_device(device_id, use_2d=use_2d)
    
    if result:
        # Extract the device's newly estimated position
        pos = result['position']
        
        # Get the Gateway's exact coordinates from your config
        gateway = FACILITY_ANCHORS[GATEWAY_NODE_ID]
        
        # Calculate 3D Euclidean distance from Gateway
        distance_from_gateway = math.sqrt(
            (pos['x'] - gateway.x)**2 + 
            (pos['y'] - gateway.y)**2 + 
            (pos['z'] - gateway.z)**2
        )
        
        is_reliable = result.get('is_reliable', True)
        reliability_status = "RELIABLE" if is_reliable else "⚠️ UNRELIABLE"
        
        return jsonify({
            'success': True,
            'position': pos,
            'distance_from_gateway': round(distance_from_gateway, 2),
            'residual_error': result['residual_error'],
            'confidence': result['confidence'],
            'accuracy': result['accuracy'],
            'is_reliable': is_reliable,
            'measurement_validation': result.get('measurement_validation', 'OK'),
            'num_measurements': result['num_measurements'],
            'timestamp': result['timestamp'],
            'message': f"Device {device_id} localized ({reliability_status}). Distance from gateway: {round(distance_from_gateway, 2)}m. Residual error: {round(result['residual_error'], 2)}m"
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
    timeout = 120
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
                    job.setdefault('logs', []).append(f"Waiting up to {per_device_timeout}s for RSSI from all 4 anchors (gateway + 3 SNs) for {did} (requested at {req_time.isoformat()})")
                except Exception:
                    logger.exception(f"Failed sending location request to {did}")
                    dev.setdefault('logs', []).append('Request failed to send')
                    dev['status'] = 'request_failed'
                    job['devices'][did] = dev
                    # continue to next device in this round
                    continue

                # Wait up to per_device_timeout for SN readings
                device_deadline = req_time + timedelta(seconds=per_device_timeout)
                got_all_rssi = False
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

                    anchor_ts = []
                    for anchor in ['gateway', 'sn1', 'sn2', 'sn3']:
                        rec = records.get(anchor) or {}
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

                        # Log when this anchor first returns a fresh timestamp after the request
                        if ts_dt and ts_dt > req_time and anchor not in seen_sn:
                            dev.setdefault('logs', []).append(f"{anchor} reported RSSI at {ts_dt.isoformat()}")
                            seen_sn.add(anchor)

                        anchor_ts.append(ts_dt)

                    if all((t is not None and t > req_time) for t in anchor_ts):
                        got_all_rssi = True
                        latest_ts = max(t for t in anchor_ts if t is not None)
                        dev['last_updated'] = latest_ts.isoformat()
                        dev.setdefault('logs', []).append(f"RSSI from all 4 anchors received at {latest_ts.isoformat()}")

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
                                # Add a diagnostic reason to logs for easier tuning.
                                diag = 'Localization returned no result'
                                try:
                                    latest_records = get_latest_rssi_with_timestamps(did)
                                    ts_vals = []
                                    for anchor in ['gateway', 'sn1', 'sn2', 'sn3']:
                                        ts = (latest_records.get(anchor) or {}).get('timestamp')
                                        if not ts:
                                            continue
                                        try:
                                            ts_vals.append(datetime.fromisoformat(ts))
                                        except Exception:
                                            try:
                                                ts_vals.append(datetime.strptime(ts, '%Y-%m-%d %H:%M:%S'))
                                            except Exception:
                                                pass
                                    if len(ts_vals) >= 2:
                                        skew = (max(ts_vals) - min(ts_vals)).total_seconds()
                                        diag = f'Localization returned no result (anchor timestamp skew {skew:.1f}s)'
                                except Exception:
                                    pass
                                dev.setdefault('logs', []).append(diag)
                                dev['status'] = 'localization_failed'
                        except Exception:
                            logger.exception(f"Localization failed for {did}")
                            dev.setdefault('logs', []).append('Localization exception')
                            dev['status'] = 'localization_failed'

                        break

                    time.sleep(1)

                # exited wait loop; log reason
                if got_all_rssi:
                    job.setdefault('logs', []).append(f"Device {did} reported all 4 anchors by {datetime.now().isoformat()}")
                else:
                    job.setdefault('logs', []).append(f"Device {did} did NOT report all 4 anchors within {per_device_timeout}s (now {datetime.now().isoformat()})")

                if not got_all_rssi:
                    # this attempt timed out for the device; mark and either retry or abandon
                    dev.setdefault('logs', []).append(f"No full 4-anchor RSSI within {per_device_timeout}s; attempt #{dev.get('attempts',0)}")
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

    # Prevent creating a new locate job if there's already an active job
    # that includes this device (queued or in_progress)
    for jid, j in JOBS.items():
        if device_id in j.get('device_ids', []):
            if j.get('status') in ('queued', 'in_progress'):
                return jsonify({'success': False, 'error': 'Localization in progress, please try again later'}), 409

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