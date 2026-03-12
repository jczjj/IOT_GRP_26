#!/usr/bin/env python3
"""
RSSI Trilateration Test Script
Demonstrates and tests the localization system with simulated and real data
"""

import math
import logging
from datetime import datetime
import numpy as np
from anchor_layout import FIXED_DEVICE_HEIGHT_METERS, REFERENCE_RSSI_AT_1_METER, get_rssi_offset

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Only run if localization module is available
try:
    from localization import RSSIToDistance, calculate_coordinates_from_rssi, get_default_anchors, localize_device
except ImportError as e:
    logger.error(f"Failed to import localization module: {e}")
    raise


ANCHORS = get_default_anchors()


def distance_to_rssi(distance: float, node_id: str | None = None) -> int:
    modeled_rssi = REFERENCE_RSSI_AT_1_METER - 10 * RSSIToDistance.PATH_LOSS_EXPONENT * math.log10(max(distance, 0.25))
    return int(round(modeled_rssi - get_rssi_offset(node_id or '')))


def test_rssi_to_distance():
    """Test RSSI to distance conversion"""
    print("\n" + "="*60)
    print("TEST 1: RSSI to Distance Conversion")
    print("="*60)
    
    test_cases = [
        (-50, "1m reference"),
        (-57, "About 2m away"),
        (-65, "About 5m away"),
        (-72, "About 10m away"),
        (-85, "Very far (~100m)"),
    ]
    
    for rssi, description in test_cases:
        distance = RSSIToDistance.rssi_to_distance(rssi)
        confidence = RSSIToDistance.calculate_confidence(rssi, distance)
        print(f"  RSSI {rssi:4d} dBm → {distance:6.2f}m ({description:25s}) confidence={confidence:.2%}")
    
    print("\n✓ RSSI conversion working correctly")


def test_with_simulated_data():
    """Test trilateration with simulated RSSI data"""
    print("\n" + "="*60)
    print("TEST 2: Trilateration with Simulated Data")
    print("="*60)
    
    # Test cases with known true positions
    test_positions = [
        {
            'name': 'Near Gateway',
            'true_pos': np.array([0.0, 0.0, FIXED_DEVICE_HEIGHT_METERS]),
            'description': 'Device directly above the gateway'
        },
        {
            'name': 'Between SN1 and SN2',
            'true_pos': np.array([1.2, 2.0, 0.8]),
            'description': 'Device inside the triangle'
        },
        {
            'name': 'Toward SN1',
            'true_pos': np.array([3.6, 0.4, 1.4]),
            'description': 'Device moving east toward sn1'
        },
        {
            'name': 'Toward SN3',
            'true_pos': np.array([-1.4, -2.5, 0.6]),
            'description': 'Device moving southwest toward sn3'
        }
    ]
    
    for test_case in test_positions:
        name = test_case['name']
        true_pos = test_case['true_pos']
        
        print(f"\n  Scenario: {test_case['description']}")
        print(f"  True position: ({true_pos[0]:.1f}, {true_pos[1]:.1f}, {true_pos[2]:.1f})")
        
        # Calculate expected RSSI from each anchor
        rssi_readings = {}
        print(f"  {'Anchor':<12} {'Distance':<12} {'RSSI (ideal)':<15} {'RSSI (with noise)':<15}")
        print(f"  {'-'*12} {'-'*12} {'-'*15} {'-'*15}")
        
        for node_id, anchor in ANCHORS.items():
            distance = float(np.linalg.norm(true_pos - anchor.position()))
            rssi_ideal = distance_to_rssi(distance, node_id)
            
            # Add some noise (typical measurement error)
            noise = np.random.normal(0, 0.5)
            rssi_noisy = int(rssi_ideal + noise)
            
            rssi_readings[node_id] = rssi_noisy
            
            print(f"  {node_id:<12} {distance:>10.2f}m {rssi_ideal:>13.1f} dBm {rssi_noisy:>13d} dBm")
        
        # Run trilateration
        result = localize_device(
            device_id=f'test-{name}',
            rssi_readings=rssi_readings,
            anchors=ANCHORS,
            use_2d=False,
            filter_outliers=False
        )
        
        if result:
            pos = result['position']
            estimated = np.array([pos['x'], pos['y'], pos['z']])
            error = np.linalg.norm(estimated - true_pos)
            
            print(f"\n  Estimated position: ({pos['x']:.2f}, {pos['y']:.2f}, {pos['z']:.2f})")
            print(f"  Position error: {error:.2f}m")
            print(f"  Residual error: {result['residual_error']:.2f}m")
            print(f"  Confidence: {result['confidence']:.2%}")
            print(f"  Accuracy: {result['accuracy']:.2%}")
            print(f"  Measurements used: {result['num_measurements']}")
            
            if error > 1.25:
                print(f"  ⚠ WARNING: Large error (>{error:.2f}m) - check RSSI generation")
            else:
                print(f"  ✓ Position error acceptable")
        else:
            print(f"  ✗ FAILED: Trilateration failed")


def test_with_manual_rssi():
    """Test with manually entered RSSI values"""
    print("\n" + "="*60)
    print("TEST 3: Manual RSSI Input")
    print("="*60)
    
    # Example: Device somewhere in facility
    print("\n  Enter RSSI readings from each anchor (in dBm):")
    print("  Example values: -50 to -80 (closer is stronger, less negative)")
    print("  Or use default test values (press Enter)\n")
    
    rssi_readings = {}
    defaults = {'gateway': -52, 'sn1': -62, 'sn2': -66, 'sn3': -64}
    
    for node_id in ['gateway', 'sn1', 'sn2', 'sn3']:
        prompt = f"  RSSI from {node_id:<8} [{defaults[node_id]:4d}]: "
        try:
            user_input = input(prompt).strip()
            if user_input:
                rssi_readings[node_id] = int(user_input)
            else:
                rssi_readings[node_id] = defaults[node_id]
        except ValueError:
            print(f"    Invalid input, using default {defaults[node_id]}")
            rssi_readings[node_id] = defaults[node_id]
    
    print(f"\n  RSSI readings:")
    for node_id, rssi in rssi_readings.items():
        distance = RSSIToDistance.rssi_to_distance(rssi, node_id=node_id)
        print(f"    {node_id:<8} {rssi:4d} dBm → {distance:.2f}m")
    
    # Perform localization
    result = localize_device(
        device_id='manual-test',
        rssi_readings=rssi_readings,
        anchors=ANCHORS,
        use_2d=False
    )
    
    if result:
        print(f"\n  Calculated position:")
        print(f"    X: {result['position']['x']:.2f}m")
        print(f"    Y: {result['position']['y']:.2f}m")
        print(f"    Z: {result['position']['z']:.2f}m")
        print(f"\n  Quality metrics:")
        print(f"    Residual error: {result['residual_error']:.2f}m")
        print(f"    Confidence:     {result['confidence']:.1%}")
        print(f"    Accuracy:       {result['accuracy']:.1%}")
        print(f"    Measurements:   {result['num_measurements']}")
    else:
        print(f"\n  ✗ Localization failed - check RSSI values")


def test_2d_vs_3d():
    """Compare 2D and 3D localization"""
    print("\n" + "="*60)
    print("TEST 4: 2D vs 3D Localization")
    print("="*60)
    
    # True position
    true_pos = np.array([0.0, 0.0, FIXED_DEVICE_HEIGHT_METERS])
    
    # Simulate RSSI
    rssi_readings = {}
    for node_id, anchor in ANCHORS.items():
        distance = float(np.linalg.norm(true_pos - anchor.position()))
        rssi = distance_to_rssi(distance, node_id)
        rssi_readings[node_id] = rssi
    
    print(f"\n  True position: ({true_pos[0]:.1f}, {true_pos[1]:.1f}, {true_pos[2]:.1f})")
    print(f"  RSSI readings: {rssi_readings}\n")
    
    # 3D localization
    print("  3D Localization (full x, y, z):")
    result_3d = localize_device(
        device_id='test-3d',
        rssi_readings=rssi_readings,
        anchors=ANCHORS,
        use_2d=False
    )
    
    if result_3d:
        pos_3d = np.array([result_3d['position']['x'], result_3d['position']['y'], result_3d['position']['z']])
        error_3d = np.linalg.norm(pos_3d - true_pos)
        print(f"    Position: ({result_3d['position']['x']:.2f}, {result_3d['position']['y']:.2f}, {result_3d['position']['z']:.2f})")
        print(f"    Error: {error_3d:.2f}m")
        print(f"    Confidence: {result_3d['confidence']:.1%}")
    
    # 2D localization
    print("\n  2D Localization (x, y only, z fixed at 1.2m):")
    result_2d = localize_device(
        device_id='test-2d',
        rssi_readings=rssi_readings,
        anchors=ANCHORS,
        use_2d=True
    )

    if result_2d:
        pos_2d = np.array([result_2d['position']['x'], result_2d['position']['y'], result_2d['position']['z']])
        error_2d = np.linalg.norm(pos_2d - true_pos)
        print(f"    Position: ({result_2d['position']['x']:.2f}, {result_2d['position']['y']:.2f}, {result_2d['position']['z']:.2f})")
        print(f"    Error: {error_2d:.2f}m")
        print(f"    Confidence: {result_2d['confidence']:.1%}")

    print(f"\n  Note: 2D mode is more stable when device height is fixed")


def test_direct_coordinate_calculation():
    """Test direct gateway/sn1/sn2/sn3 RSSI to x/y/z calculation."""
    print("\n" + "="*60)
    print("TEST 5: Direct Coordinate Calculation")
    print("="*60)

    true_pos = np.array([1.4, -1.1, 0.9])
    rssi_values = {}
    for node_id, anchor in ANCHORS.items():
        distance = float(np.linalg.norm(true_pos - anchor.position()))
        rssi_values[node_id] = distance_to_rssi(distance, node_id)

    result = calculate_coordinates_from_rssi(
        gateway_rssi=rssi_values['gateway'],
        sn1_rssi=rssi_values['sn1'],
        sn2_rssi=rssi_values['sn2'],
        sn3_rssi=rssi_values['sn3'],
    )

    if not result:
        raise RuntimeError('Direct coordinate calculation failed')

    estimated = np.array([
        result['position']['x'],
        result['position']['y'],
        result['position']['z'],
    ])
    error = float(np.linalg.norm(estimated - true_pos))

    print(f"  Input RSSI values: {rssi_values}")
    print(f"  Estimated position: ({estimated[0]:.2f}, {estimated[1]:.2f}, {estimated[2]:.2f})")
    print(f"  Position error: {error:.3f}m")


def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("RSSI TRILATERATION TEST SUITE")
    print("="*60)
    print(f"Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # Run tests
        test_rssi_to_distance()
        test_with_simulated_data()
        
        # Ask user if they want to enter manual data
        print("\n" + "="*60)
        response = input("Run manual RSSI input test? (y/n) [n]: ").strip().lower()
        if response == 'y':
            test_with_manual_rssi()
        
        # Run comparison test
        test_2d_vs_3d()
        test_direct_coordinate_calculation()
        
        print("\n" + "="*60)
        print("✓ ALL TESTS COMPLETED")
        print("="*60)
        print("\nNext steps:")
        print("1. Deploy the system with real devices")
        print("2. Collect RSSI readings from your facility")
        print("3. Tune PATH_LOSS_EXPONENT in localization.py based on results")
        print("4. Integrate with /api/localize/ endpoint")
        print("5. Use positions in 3D visualization")
        
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        raise


if __name__ == '__main__':
    main()
