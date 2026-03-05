"""
Flask Application Server for Elderly Home Monitoring System
RSSI-Based Localization with Server-Orchestrated Wi-Fi Hopping
"""

from flask import Flask, render_template, jsonify, request, send_from_directory
from datetime import datetime
import json
import os
import logging
from ttn_integration import get_ttn_client, TTNClient
from device_manager import get_device_manager, DeviceManager
from database import init_database

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

# Initialize TTN client with callback
def on_ttn_message(device_id: str, payload_data: dict, metadata: dict):
    """Callback for TTN uplink messages"""
    device_manager.handle_uplink_message(device_id, payload_data, metadata)

ttn_client: TTNClient = get_ttn_client(on_message_callback=on_ttn_message)

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
    
    Retrieves latest RSSI readings from all anchor nodes and performs
    weighted least-squares trilateration to estimate device position.
    
    Query params:
        - use_2d: If 'true', assumes device at fixed height (1.2m)
    
    Returns:
        {
            'success': bool,
            'position': {'x': float, 'y': float, 'z': float},
            'residual_error': float,     # Fitting error in meters
            'confidence': float,         # 0.0-1.0
            'accuracy': float,           # Estimated accuracy
            'num_measurements': int,
            'timestamp': str,
            'message': str
        }
    """
    use_2d = request.args.get('use_2d', 'false').lower() == 'true'
    
    result = device_manager.localize_device(device_id, use_2d=use_2d)
    
    if result:
        return jsonify({
            'success': True,
            'position': result['position'],
            'residual_error': result['residual_error'],
            'confidence': result['confidence'],
            'accuracy': result['accuracy'],
            'num_measurements': result['num_measurements'],
            'timestamp': result['timestamp'],
            'message': f"Device {device_id} localized successfully"
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
