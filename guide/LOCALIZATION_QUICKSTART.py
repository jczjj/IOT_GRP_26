#!/usr/bin/env python3
"""
QUICK START: RSSI Trilateration System
Usage guide for the RSSI-based device localization
"""

# ============================================================================
# 1. SETUP - Configure anchors and start the system
# ============================================================================

from ttn_integration import get_ttn_client, AnchorPoint

# Define your facility's anchor points (stationary nodes)
anchors = {
    'gateway': AnchorPoint('gateway', 'LoRaWAN Gateway', 15.0, 20.0, 2.5),
    'sn1': AnchorPoint('sn1', 'Anchor 1', 20.0, 20.0, 1.5),
    'sn2': AnchorPoint('sn2', 'Anchor 2', 12.5, 24.33, 1.5),
    'sn3': AnchorPoint('sn3', 'Anchor 3', 12.5, 15.67, 1.5)
}

# Create TTN client with auto-localization enabled
client = get_ttn_client(
    anchors=anchors,
    auto_localize=True  # Automatically calculate position from RSSI
)

# Start receiving messages from The Things Network
client.start()

# ============================================================================
# 2. AUTOMATIC LOCALIZATION
# ============================================================================

# When devices send RSSI readings via TTN, the system automatically:
# 1. Buffers RSSI values from multiple anchors
# 2. When >= 3 anchors have data, performs trilateration
# 3. Calculates device position (x, y, z)
# 4. Returns position to your application

# Example: A device sends location beacon with RSSI readings
# The system automatically localizes it within ~2-3 seconds

# ============================================================================
# 3. MANUAL LOCALIZATION
# ============================================================================

# Trigger manual localization for a specific device
device_id = 'ed-1'
location = client.localize_device(device_id)

if location:
    print(f"Device {device_id} position:")
    print(f"  X: {location['position']['x']:.2f}m")
    print(f"  Y: {location['position']['y']:.2f}m")
    print(f"  Z: {location['position']['z']:.2f}m")
    print(f"  Error: {location['residual_error']:.2f}m")
    print(f"  Confidence: {location['confidence']:.1%}")

# ============================================================================
# 4. CHECK LOCALIZATION STATUS
# ============================================================================

# Get current status for a device
status = client.get_localization_status(device_id)

print(f"Current status for {device_id}:")
print(f"  RSSI measurements available: {status['rssi_measurements']}")
print(f"  Ready for localization: {status['ready_for_localization']}")
print(f"  Last position: {status['last_position']}")
print(f"  RSSI values: {status['rssi_values']}")

# ============================================================================
# 5. RSSI VALUES - What they mean
# ============================================================================

# RSSI (signal strength) is measured in dBm (negative numbers)
# The values are automatically converted to distances using path loss model

# Typical RSSI values:
#   -30 dBm  Very close (< 1m) - strong signal
#   -50 dBm  Close (2-3m)
#   -70 dBm  Medium (10-15m)  
#   -90 dBm  Far (30-50m) - weak signal
#   -110 dBm Very far (> 50m) - unreliable

# ============================================================================
# 6. TUNING RSSI ACCURACY
# ============================================================================

# If positions are off, adjust these in ttn_integration.py:

# PATH_LOSS_EXPONENT - How quickly signal strength decreases with distance
#   2.0-2.5: Open space, line-of-sight
#   2.5-3.0: Indoor with some obstacles
#   3.0-4.0: Heavy walls, furniture (NLOS)

# TX_POWER - Reference transmit power at 1 meter
#   -40 dBm: Standard LoRa TX power (default)

# ============================================================================
# 7. API ENDPOINTS (Flask)
# ============================================================================

# GET /api/localize/<device_id>
#   Manually trigger localization
#   Query params: use_2d=true (optional, for 2D mode)
#   Returns: {position, residual_error, confidence, accuracy}

# POST /api/localize/<device_id>
#   Same as GET (alternative method)

# GET /api/devices
#   Get all devices with their locations (updated by trilateration)

# GET /api/stationary-nodes
#   Get anchor positions

# ============================================================================
# 8. DATABASE - RSSI Readings Storage
# ============================================================================

# RSSI readings are automatically stored in the database whenever:
# 1. Device sends RSSI reading directly
# 2. Stations forward RSSI readings from devices
# 3. Gateway receives signal from device

# Table: rssi_readings
#   device_id: which device
#   node_id: which anchor received the signal (gateway, sn1, sn2, sn3)
#   rssi: signal strength in dBm
#   timestamp: when measurement was taken

# ============================================================================
# 9. EXAMPLE: Full Workflow
# ============================================================================

# Step 1: Device broadcasts location beacon
# Step 2: All anchors receive it -> get RSSI values
# Step 3: Each anchor sends RSSI to gateway via LoRa/relay
# Step 4: Gateway delivers to TTN
# Step 5: TTN sends messages to application server
# Step 6: ttn_integration buffers RSSI from all nodes
# Step 7: System has >= 3 RSSI readings
# Step 8: Trilateration calculates position
# Step 9: Position saved to device location in database
# Step 10: Position available in dashboard visualization

# ============================================================================
# 10. EXPECTED ACCURACY
# ============================================================================

# With good RSSI readings and tuned path loss exponent:
#   Small room (10m x 10m): ±0.5-1.0m
#   Medium room (20m x 20m): ±1.0-2.0m
#   Large facility (30m x 40m): ±2.0-3.0m

# Accuracy decreases with:
#   - Fewer anchors (need at least 3-4)
#   - Heavy obstacles/walls
#   - NLOS (non-line-of-sight) conditions
#   - Moving people/interference

# Accuracy improves with:
#   - More anchors (4+ is ideal)
#   - Clear line-of-sight
#   - Consistent RSSI readings
#   - Time averaging/filtering
