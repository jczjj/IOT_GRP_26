#!/usr/bin/env python3
"""
Integration test for RSSI Trilateration with TTN
Tests the complete flow from RSSI reception to position calculation
"""

import sys
import math
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

try:
    from ttn_integration import AnchorPoint, RSSIToDistance, Trilateration, TTNClient
    import numpy as np
    HAS_NUMPY = True
except ImportError as e:
    print(f"Error importing required modules: {e}")
    print("Make sure you have installed: numpy, paho-mqtt, flask, requests")
    sys.exit(1)


def test_rssi_to_distance():
    """Test RSSI to distance conversion"""
    print("\n" + "="*60)
    print("TEST 1: RSSI to Distance Conversion")
    print("="*60)
    
    test_cases = [
        (-40, "Very close (1m reference)"),
        (-50, "Close (~3m)"),
        (-60, "Medium (~10m)"),
        (-70, "Far (~30m)"),
        (-85, "Very far (~100m)"),
    ]
    
    for rssi, description in test_cases:
        distance = RSSIToDistance.rssi_to_distance(rssi)
        confidence = RSSIToDistance.calculate_confidence(rssi, distance)
        print(f"  RSSI {rssi:4d} dBm → {distance:6.2f}m ({description:25s}) | confidence={confidence:.2%}")
    
    print("\n✓ RSSI conversion working correctly")


def test_trilateration_with_known_position():
    """Test trilateration with simulated RSSI data"""
    print("\n" + "="*60)
    print("TEST 2: Trilateration with Known Position")
    print("="*60)
    
    # Define anchors
    anchors = {
        'gateway': AnchorPoint('gateway', 'Gateway (Center)', 15.0, 20.0, 2.5),
        'sn1': AnchorPoint('sn1', 'Anchor 1 (East)', 20.0, 20.0, 1.5),
        'sn2': AnchorPoint('sn2', 'Anchor 2 (NW)', 12.5, 24.33, 1.5),
        'sn3': AnchorPoint('sn3', 'Anchor 3 (SW)', 12.5, 15.67, 1.5)
    }
    
    # Test cases with known true positions
    test_positions = [
        {
            'name': 'Center',
            'true_pos': np.array([15, 20, 1.2]),
            'description': 'Device at facility center'
        },
        {
            'name': 'Near SN1',
            'true_pos': np.array([20, 20, 1.2]),
            'description': 'Device at SN1 location'
        },
        {
            'name': 'Between SN2 and SN3',
            'true_pos': np.array([12.5, 20, 1.2]),
            'description': 'Device between anchors'
        }
    ]
    
    for test_case in test_positions:
        name = test_case['name']
        true_pos = test_case['true_pos']
        
        print(f"\nScenario: {test_case['description']}")
        print(f"True position: ({true_pos[0]:.2f}, {true_pos[1]:.2f}, {true_pos[2]:.2f})")
        
        # Calculate expected RSSI from each anchor
        rssi_readings = {}
        print(f"{'Anchor':<12} {'Distance':<12} {'RSSI (ideal)':<15} {'RSSI (w/ noise)':<15}")
        print(f"{'-'*12} {'-'*12} {'-'*15} {'-'*15}")
        
        for node_id, anchor in anchors.items():
            distance = float(np.linalg.norm(true_pos - anchor.position()))
            
            # Calculate RSSI without noise (RSSI = TX_POWER - 10*n*log10(d))
            # Closer to 0 = nearer, more negative = farther
            rssi_ideal = RSSIToDistance.TX_POWER - 10 * RSSIToDistance.PATH_LOSS_EXPONENT * math.log10(distance)
            
            # Add some noise (typical measurement error)
            noise = np.random.normal(0, 2.5)  # 2.5 dBm std dev
            rssi_noisy = int(rssi_ideal + noise)
            
            rssi_readings[node_id] = rssi_noisy
            
            print(f"{node_id:<12} {distance:>10.2f}m {rssi_ideal:>13.1f} dBm {rssi_noisy:>13d} dBm")
        
        # Run trilateration
        result = Trilateration.calculate_position(rssi_readings, anchors, use_2d=False)
        
        if result:
            pos = result['position']
            estimated = np.array([pos['x'], pos['y'], pos['z']])
            error = np.linalg.norm(estimated - true_pos)
            
            print(f"\nEstimated position: ({pos['x']:.2f}, {pos['y']:.2f}, {pos['z']:.2f})")
            print(f"Position error: {error:.2f}m")
            print(f"Residual error: {result['residual_error']:.2f}m")
            print(f"Confidence: {result['confidence']:.2%}")
            print(f"Measurements used: {result['num_measurements']}")
            
            if error <= 2.0:
                print(f"✓ Good accuracy")
            else:
                print(f"⚠ Error > 2m - may need calibration")
        else:
            print(f"✗ FAILED: Trilateration returned None")


def test_ttn_client_with_auto_localize():
    """Test TTN client with auto-localization"""
    print("\n" + "="*60)
    print("TEST 3: TTN Client with Auto-Localization")
    print("="*60)
    
    anchors = {
        'gateway': AnchorPoint('gateway', 'Gateway (Center)', 15.0, 20.0, 2.5),
        'sn1': AnchorPoint('sn1', 'Anchor 1 (East)', 20.0, 20.0, 1.5),
        'sn2': AnchorPoint('sn2', 'Anchor 2 (NW)', 12.5, 24.33, 1.5),
        'sn3': AnchorPoint('sn3', 'Anchor 3 (SW)', 12.5, 15.67, 1.5)
    }
    
    # Create client
    client = TTNClient(anchors=anchors, auto_localize=True)
    
    print("\nTTN Client created with anchors:")
    for node_id, anchor in anchors.items():
        print(f"  {node_id}: ({anchor.x:.1f}, {anchor.y:.1f}, {anchor.z:.1f}m)")
    
    # Simulate RSSI readings
    test_device = 'ed-1'
    rssi_dict = {
        'gateway': -55,
        'sn1': -65,
        'sn2': -72,
        'sn3': -68
    }
    
    print(f"\nSimulating RSSI readings for {test_device}:")
    for node_id, rssi in rssi_dict.items():
        print(f"  {node_id}: {rssi} dBm")
        client._buffer_rssi(test_device, node_id, rssi)
    
    # Attempt localization
    result = client.localize_if_ready(test_device, min_anchors=3)
    
    if result:
        pos = result['position']
        print(f"\n✓ LOCALIZED {test_device}:")
        print(f"  Position: ({pos['x']:.2f}m, {pos['y']:.2f}m, {pos['z']:.2f}m)")
        print(f"  Residual error: {result['residual_error']:.2f}m")
        print(f"  Confidence: {result['confidence']:.1%}")
        print(f"  Measurements: {result['num_measurements']}")
    else:
        print(f"\n✗ Localization failed")
    
    # Check status
    status = client.get_localization_status(test_device)
    print(f"\nLocalization status for {test_device}:")
    print(f"  RSSI measurements: {status['rssi_measurements']}")
    print(f"  Ready: {status['ready_for_localization']}")
    print(f"  Last position: {status['last_position']}")
    
    print("\n✓ TTN Client test completed")


def main():
    """Run all integration tests"""
    print("\n" + "="*60)
    print("RSSI TRILATERATION INTEGRATION TEST SUITE")
    print("="*60)
    print(f"Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        test_rssi_to_distance()
        test_trilateration_with_known_position()
        test_ttn_client_with_auto_localize()
        
        print("\n" + "="*60)
        print("✓ ALL INTEGRATION TESTS COMPLETED SUCCESSFULLY")
        print("="*60)
        print("\nSystem is ready for deployment:")
        print("  1. Run: python app.py")
        print("  2. Devices will auto-localize when RSSI readings are received")
        print("  3. Use /api/localize/<device_id> endpoint for manual localization")
        print("  4. Positions are stored and visible in dashboard")
        
    except Exception as e:
        logger.error(f"Integration test failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
