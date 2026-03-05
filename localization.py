#!/usr/bin/env python3
"""
Localization Module - RSSI-Based Distance Calculation & Trilateration
Converts RSSI measurements to estimated distances and calculates device positions
"""

import math
import logging
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime, timedelta
import numpy as np
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class AnchorPoint:
    """Represents a stationary node (anchor) with known position"""
    node_id: str
    name: str
    x: float
    y: float
    z: float
    
    def position(self) -> np.ndarray:
        """Return position as numpy array"""
        return np.array([self.x, self.y, self.z])


@dataclass
class RSSIMeasurement:
    """Single RSSI measurement from an anchor"""
    node_id: str
    rssi: int  # dBm
    distance: float  # Calculated distance in meters
    timestamp: datetime
    confidence: float  # 0.0 to 1.0


class RSSIToDistance:
    """
    Converts RSSI (dBm) to estimated distance using Log-Distance Path Loss Model.
    
    Formula: distance = 10^((TX_POWER - RSSI - FADING) / (10 * n))
    Where:
    - TX_POWER: Transmit power at 1m reference (typical -40 dBm for BLE/Wi-Fi)
    - RSSI: Measured signal strength (dBm)
    - n: Path loss exponent (2-4 depending on environment)
    - FADING: Wall/furniture attenuation (0-10 dB)
    """
    
    # Environmental parameters - tune these based on your facility
    TX_POWER = -40          # dBm at 1m reference distance
    PATH_LOSS_EXPONENT = 2.5  # 2.0-2.5 for indoor LoS, 3.0-4.0 for NLOS
    WALL_FADING = 3.0        # dB per wall/major obstacle
    
    # Distance limits for filtering invalid measurements
    MIN_DISTANCE = 0.5   # meters
    MAX_DISTANCE = 50.0  # meters
    
    @staticmethod
    def rssi_to_distance(rssi: int, tx_power: int = TX_POWER, 
                        n: float = PATH_LOSS_EXPONENT, 
                        wall_factor: float = WALL_FADING) -> float:
        """
        Calculate distance from RSSI value.
        
        Args:
            rssi: RSSI value in dBm (typically -30 to -100)
            tx_power: Transmit power at 1m reference (dBm)
            n: Path loss exponent (2.0-4.0)
            wall_factor: Additional attenuation from obstacles (dB)
        
        Returns:
            Estimated distance in meters (clamped to MIN/MAX_DISTANCE)
        """
        if rssi >= 0:
            logger.warning(f"Invalid RSSI value: {rssi} dBm (should be negative)")
            return RSSIToDistance.MIN_DISTANCE
        
        # Log-distance path loss formula
        path_loss = (rssi - tx_power)
        distance = 10 ** (path_loss / (10 * n))
        
        # Clamp to valid range
        distance = max(RSSIToDistance.MIN_DISTANCE, min(distance, RSSIToDistance.MAX_DISTANCE))
        
        return distance
    
    @staticmethod
    def calculate_confidence(rssi: int, distance: float, num_measurements: int = 1) -> float:
        """
        Calculate measurement confidence (0.0-1.0).
        
        Higher RSSI (closer to 0) = more confident
        Longer distance = less confident
        More measurements = more confident
        
        Args:
            rssi: RSSI value in dBm
            distance: Calculated distance in meters
            num_measurements: Number of samples averaged
        
        Returns:
            Confidence score 0.0-1.0
        """
        # RSSI confidence: -30 dBm = 100%, -100 dBm = 10%
        rssi_conf = max(0.0, min(1.0, (rssi + 100) / 70))
        
        # Distance confidence: optimal range 2-15m
        if distance < 2:
            dist_conf = 0.9 + (distance / 2) * 0.1
        elif distance <= 15:
            dist_conf = 1.0
        else:
            dist_conf = max(0.5, 1.0 - (distance - 15) / 35)
        
        # Measurement count confidence
        count_conf = min(1.0, num_measurements / 3)  # Optimal at 3+ measurements
        
        # Combined confidence (weighted average)
        confidence = (rssi_conf * 0.5 + dist_conf * 0.3 + count_conf * 0.2)
        
        return confidence


class Trilateration:
    """
    Calculates device position from multiple RSSI measurements using trilateration.
    Uses weighted least-squares fitting for robustness.
    """
    
    MIN_ANCHORS = 3  # Need at least 3 anchors for 2D, 4 for 3D
    
    @staticmethod
    def calculate_position(measurements: List[RSSIMeasurement], 
                          anchors: Dict[str, AnchorPoint],
                          use_weights: bool = True,
                          prefer_2d: bool = False) -> Optional[Dict[str, Any]]:
        """
        Calculate device position using weighted least-squares trilateration.
        
        Args:
            measurements: List of RSSI measurements from different anchors
            anchors: Dict of anchor points {node_id: AnchorPoint}
            use_weights: If True, use confidence as weights; if False, equal weights
            prefer_2d: If True, assume device is at Z=1.2m (typical height)
        
        Returns:
            Dict with 'position' (x,y,z), 'residual', 'confidence' or None if failed
        """
        
        # Validate inputs
        if not measurements or len(measurements) < Trilateration.MIN_ANCHORS:
            logger.warning(f"Insufficient measurements: {len(measurements)} (need {Trilateration.MIN_ANCHORS})")
            return None
        
        # Prepare data for least-squares solving
        # Build matrices for: (x-xi)^2 + (y-yi)^2 + (z-zi)^2 = ri^2
        
        A = []  # Coefficient matrix
        b = []  # Right-hand side
        weights = []  # Optional weights
        
        valid_measurements = []
        
        for measurement in measurements:
            if measurement.node_id not in anchors:
                logger.warning(f"Unknown anchor: {measurement.node_id}")
                continue
            
            anchor = anchors[measurement.node_id]
            
            # Each measurement gives us a constraint
            # 2(xi*x + yi*y + zi*z) - (x + y + z) = ri^2 - xi^2 - yi^2 - zi^2
            # Rearranged for least squares
            
            valid_measurements.append(measurement)
            
            # Row of A: [2*xi, 2*yi, 2*zi]
            A.append([2 * anchor.x, 2 * anchor.y, 2 * anchor.z])
            
            # Right side: ri^2 - xi^2 - yi^2 - zi^2
            ri_sq = measurement.distance ** 2
            anchor_dist_sq = anchor.x**2 + anchor.y**2 + anchor.z**2
            b.append(ri_sq - anchor_dist_sq)
            
            # Weight by confidence
            if use_weights:
                weights.append(measurement.confidence)
            else:
                weights.append(1.0)
        
        if len(valid_measurements) < Trilateration.MIN_ANCHORS:
            logger.warning(f"Not enough valid measurements after filtering: {len(valid_measurements)}")
            return None
        
        try:
            # Convert to numpy arrays
            A = np.array(A, dtype=float)
            b = np.array(b, dtype=float)
            weights = np.array(weights, dtype=float)
            
            # Normalize weights to sum to 1
            weights = weights / np.sum(weights)
            
            # Weighted least-squares: minimize ||W^(1/2) * (A*x - b)||^2
            # Equivalent to: (A^T * W * A)^(-1) * A^T * W * b
            
            W = np.diag(weights)  # Weight matrix
            
            # Solve: (A^T * W * A) * x = A^T * W * b
            ATA = A.T @ W @ A
            ATb = A.T @ W @ b
            
            try:
                position = np.linalg.solve(ATA, ATb)
            except np.linalg.LinAlgError:
                # Matrix singular, use least-squares instead
                position, residuals, rank, s = np.linalg.lstsq(A, b, rcond=None)
                logger.debug(f"Used numpy.linalg.lstsq fallback (rank={rank})")
            
            x, y, z = float(position[0]), float(position[1]), float(position[2])
            
            # If prefer_2D, lock z to expected height
            if prefer_2d:
                z = 1.2  # Typical wrist-worn device height
            
            # Calculate residual (fitting error)
            predicted_b = A @ position
            residuals = predicted_b - b
            rms_error = float(np.sqrt(np.mean(residuals ** 2)))
            
            # Overall confidence
            avg_confidence = float(np.mean(weights))
            
            # Estimate accuracy from residual and confidence
            accuracy = max(0.3, avg_confidence * (1.0 - min(1.0, rms_error / 10)))
            
            return {
                'position': {'x': x, 'y': y, 'z': z},
                'residual_error': rms_error,
                'confidence': avg_confidence,
                'accuracy': accuracy,
                'num_measurements': len(valid_measurements),
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Trilateration failed: {e}", exc_info=True)
            return None
    
    @staticmethod
    def kalman_filter(current_position: Optional[Dict[str, float]],
                     new_measurement: Dict[str, Any],
                     process_noise: float = 0.1,
                     measurement_noise: float = 1.0) -> Dict[str, float]:
        """
        Simple 3D Kalman filter for smoothing position estimates.
        
        Args:
            current_position: Previous estimated position {x, y, z} or None for first measurement
            new_measurement: New trilateration result with 'position' and 'accuracy'
            process_noise: Q - process noise covariance (higher = trust motion more)
            measurement_noise: R - measurement noise covariance (higher = trust new measurement less)
        
        Returns:
            Filtered position {x, y, z}
        """
        
        if current_position is None:
            # First measurement - just return it
            new_pos = new_measurement['position']
            return {'x': new_pos['x'], 'y': new_pos['y'], 'z': new_pos['z']}
        
        # Simple complementary filter instead of full Kalman
        # Use confidence as weighting factor
        accuracy = new_measurement.get('accuracy', 0.5)
        alpha = 0.3 + (accuracy * 0.4)  # 30-70% weight on new measurement
        
        new_pos = new_measurement['position']
        
        filtered = {
            'x': current_position['x'] * (1 - alpha) + new_pos['x'] * alpha,
            'y': current_position['y'] * (1 - alpha) + new_pos['y'] * alpha,
            'z': current_position['z'] * (1 - alpha) + new_pos['z'] * alpha
        }
        
        return filtered


def localize_device(device_id: str, 
                   rssi_readings: Dict[str, int],
                   anchors: Dict[str, AnchorPoint],
                   use_2d: bool = False,
                   filter_outliers: bool = True) -> Optional[Dict[str, Any]]:
    """
    Complete localization pipeline: RSSI → distance → position
    
    Args:
        device_id: Device to localize
        rssi_readings: Dict {node_id: rssi_dBm} from fresh measurements
        anchors: Dict {node_id: AnchorPoint}
        use_2d: If True, assume device at fixed height
        filter_outliers: If True, remove RSSI values that seem invalid
    
    Returns:
        Localization result or None
    """
    
    # Step 1: Convert RSSI to distances
    measurements = []
    
    for node_id, rssi in rssi_readings.items():
        if node_id not in anchors:
            logger.warning(f"RSSI from unknown node: {node_id}")
            continue
        
        # Filter outliers
        if filter_outliers:
            if rssi > -20 or rssi < -120:  # Sanity check
                logger.debug(f"Filtering outlier RSSI: {node_id}={rssi} dBm")
                continue
        
        distance = RSSIToDistance.rssi_to_distance(rssi)
        confidence = RSSIToDistance.calculate_confidence(rssi, distance)
        
        measurement = RSSIMeasurement(
            node_id=node_id,
            rssi=rssi,
            distance=distance,
            timestamp=datetime.now(),
            confidence=confidence
        )
        measurements.append(measurement)
        
        logger.debug(f"{device_id}: {node_id} RSSI={rssi} dBm → distance={distance:.2f}m (conf={confidence:.2f})")
    
    if not measurements:
        logger.warning(f"No valid RSSI measurements for {device_id}")
        return None
    
    # Step 2: Trilateration
    result = Trilateration.calculate_position(
        measurements=measurements,
        anchors=anchors,
        use_weights=True,
        prefer_2d=use_2d
    )
    
    if result:
        logger.info(f"{device_id} localized: ({result['position']['x']:.2f}, {result['position']['y']:.2f}, {result['position']['z']:.2f}) "
                   f"error={result['residual_error']:.2f}m conf={result['confidence']:.2f}")
    
    return result


# Example usage and testing
if __name__ == '__main__':
    import logging
    logging.basicConfig(level=logging.DEBUG)
    
    # Define test anchors (30m × 40m facility)
    # Gateway at center, 3 SNs forming equilateral triangle 5m away, 1m lower
    anchors = {
        'gateway': AnchorPoint('gateway', 'Gateway (Center)', 15.0, 20.0, 2.5),
        'sn1': AnchorPoint('sn1', 'Anchor 1 (East)', 20.0, 20.0, 1.5),
        'sn2': AnchorPoint('sn2', 'Anchor 2 (NW)', 12.5, 24.33, 1.5),
        'sn3': AnchorPoint('sn3', 'Anchor 3 (SW)', 12.5, 15.67, 1.5)
    }
    
    # Test case: device at (15, 20, 1.2) - facility center
    # Calculate expected RSSI from each anchor
    test_position = np.array([15, 20, 1.2])
    rssi_readings = {}
    
    for node_id, anchor in anchors.items():
        distance = float(np.linalg.norm(test_position - anchor.position()))
        rssi = RSSIToDistance.TX_POWER + 10 * RSSIToDistance.PATH_LOSS_EXPONENT * math.log10(distance) + \
               np.random.normal(0, 2)  # Add small noise
        rssi_readings[node_id] = int(rssi)
        print(f"Simulated {node_id}: distance={distance:.2f}m → RSSI={rssi:.1f} dBm")
    
    print("\n--- Running Trilateration ---")
    result = localize_device('test-device', rssi_readings, anchors, use_2d=False)
    
    if result:
        print(f"\nResult: {result['position']}")
        print(f"Error: {result['residual_error']:.2f}m")
        print(f"Confidence: {result['confidence']:.2%}")
