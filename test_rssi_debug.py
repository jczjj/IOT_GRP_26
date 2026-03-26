#!/usr/bin/env python3
"""Debug the trilateration with the user's RSSI data"""

from localization import calculate_coordinates_from_rssi, RSSIToDistance, get_default_anchors
from anchor_layout import REFERENCE_RSSI_AT_1_METER, PATH_LOSS_EXPONENT

# User's RSSI data
gateway_rssi = -17
sn1_rssi = -79
sn2_rssi = -16
sn3_rssi = -71

print("="*60)
print("RSSI to Distance Conversion")
print("="*60)
print(f"Reference RSSI: {REFERENCE_RSSI_AT_1_METER} dBm")
print(f"Path Loss Exponent: {PATH_LOSS_EXPONENT}")
print()

# Convert RSSI to distances
d_gateway = RSSIToDistance.rssi_to_distance(gateway_rssi)
d_sn1 = RSSIToDistance.rssi_to_distance(sn1_rssi)
d_sn2 = RSSIToDistance.rssi_to_distance(sn2_rssi)
d_sn3 = RSSIToDistance.rssi_to_distance(sn3_rssi)

print(f"GATEWAY ({gateway_rssi} dBm): {d_gateway:.2f}m")
print(f"SN1     ({sn1_rssi} dBm): {d_sn1:.2f}m")
print(f"SN2     ({sn2_rssi} dBm): {d_sn2:.2f}m")
print(f"SN3     ({sn3_rssi} dBm): {d_sn3:.2f}m")
print()

print("="*60)
print("Anchor Positions")
print("="*60)
anchors = get_default_anchors()
for node_id, anchor in anchors.items():
    print(f"{node_id:8s}: ({anchor.x:6.2f}, {anchor.y:6.2f}, {anchor.z:6.2f})")
print()

print("="*60)
print("Distance Analysis")
print("="*60)
print(f"Device closest to: SN2 ({d_sn2:.2f}m) and GATEWAY ({d_gateway:.2f}m)")
print(f"Calculated position would be near: SN2 at ({anchors['sn2'].x:.2f}, {anchors['sn2'].y:.2f})")
print()

# Calculate position
result = calculate_coordinates_from_rssi(gateway_rssi, sn1_rssi, sn2_rssi, sn3_rssi, use_2d=True)

if result:
    pos = result['position']
    print("="*60)
    print("Calculated Position (Trilateration)")
    print("="*60)
    print(f"X: {pos['x']:.3f} m")
    print(f"Y: {pos['y']:.3f} m")
    print(f"Z: {pos['z']:.3f} m")
    print()
    print("="*60)
    print("Predicted vs Measured Distances")
    print("="*60)
    for node_id, predicted_dist in result['predicted_distances'].items():
        actual_dist = {'gateway': d_gateway, 'sn1': d_sn1, 'sn2': d_sn2, 'sn3': d_sn3}[node_id]
        error = abs(predicted_dist - actual_dist)
        print(f"{node_id:8s}: Predicted={predicted_dist:.2f}m, Actual={actual_dist:.2f}m, Error={error:.2f}m")
    print()
    print(f"Residual Error: {result['residual_error']:.3f}")
    print(f"Confidence: {result['confidence']:.3f}")
else:
    print("ERROR: Localization failed")
