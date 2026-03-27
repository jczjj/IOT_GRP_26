#!/usr/bin/env python3
"""
Localization Module
Converts gateway/sn1/sn2/sn3 RSSI readings into x, y, z coordinates.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np

from anchor_layout import (
    ALL_ANCHOR_IDS,
    FIXED_DEVICE_HEIGHT_METERS,
    GATEWAY_NODE_ID,
    PATH_LOSS_EXPONENT,
    REFERENCE_RSSI_AT_1_METER,
    calibrate_rssi,
    get_anchor_layout,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AnchorPoint:
    node_id: str
    name: str
    x: float
    y: float
    z: float

    def position(self) -> np.ndarray:
        return np.array([self.x, self.y, self.z], dtype=float)


@dataclass(frozen=True)
class RSSIMeasurement:
    node_id: str
    rssi: int
    distance: float
    timestamp: datetime
    confidence: float


def get_default_anchors() -> Dict[str, AnchorPoint]:
    anchors: Dict[str, AnchorPoint] = {}
    for node_id, node in get_anchor_layout().items():
        location = node['location']
        anchors[node_id] = AnchorPoint(
            node_id=node_id,
            name=node['name'],
            x=float(location['x']),
            y=float(location['y']),
            z=float(location['z']),
        )
    return anchors


class RSSIToDistance:
    """Convert RSSI to distance using a calibrated log-distance model."""

    REFERENCE_RSSI_AT_1_METER = REFERENCE_RSSI_AT_1_METER
    PATH_LOSS_EXPONENT = PATH_LOSS_EXPONENT
    MIN_DISTANCE = 0.25
    MAX_DISTANCE = 21.0   # diagonal of 15 m × 15 m test room ≈ 21.2 m

    @staticmethod
    def rssi_to_distance(
        rssi: int,
        reference_rssi: int = REFERENCE_RSSI_AT_1_METER,
        path_loss_exponent: float = PATH_LOSS_EXPONENT,
        node_id: Optional[str] = None,
    ) -> float:
        if node_id is not None:
            rssi = calibrate_rssi(node_id, rssi)

        if rssi >= 0:
            logger.warning('Invalid RSSI value %s dBm; expected a negative number.', rssi)
            return RSSIToDistance.MIN_DISTANCE

        distance = 10 ** ((reference_rssi - rssi) / (10 * path_loss_exponent))
        return max(RSSIToDistance.MIN_DISTANCE, min(distance, RSSIToDistance.MAX_DISTANCE))

    @staticmethod
    def calculate_confidence(
        rssi: int,
        distance: float,
        num_measurements: int = 1,
        node_id: Optional[str] = None,
    ) -> float:
        if node_id is not None:
            rssi = calibrate_rssi(node_id, rssi)

        rssi_confidence = max(0.05, min(1.0, (abs(rssi) - 20) / 90))
        rssi_confidence = 1.05 - rssi_confidence

        if distance <= 5:
            distance_confidence = 1.0
        elif distance <= 15:
            distance_confidence = 0.9
        else:
            distance_confidence = max(0.4, 1.0 - ((distance - 15) / 35))

        measurement_confidence = min(1.0, 0.5 + (num_measurements * 0.15))
        return max(0.05, min(1.0, (rssi_confidence * 0.5) + (distance_confidence * 0.35) + (measurement_confidence * 0.15)))


class Trilateration:
    """Solve x/y from anchor geometry, then recover z from gateway distance."""

    MIN_MEASUREMENTS = 4
    REQUIRED_ANCHORS = set(ALL_ANCHOR_IDS)
    MAX_GAUSS_NEWTON_ITERATIONS = 30
    GAUSS_NEWTON_TOLERANCE = 1e-4
    GATEWAY_WEIGHT_FACTOR = 0.45
    GATEWAY_DISTANCE_TOLERANCE_METERS = 0.75
    MAX_RESIDUAL_ERROR = 2.0  # Meters - flag unreliable solutions
    MIN_CONFIDENCE_THRESHOLD = 0.5  # Minimum acceptable confidence

    @staticmethod
    def _measurement_weight(measurement: RSSIMeasurement, is_gateway: bool = False) -> float:
        """Compute a fine-grained reliability weight for weighted least squares.

        RSSI is in dBm, so a 1-2 dB change should still adjust weights.
        Use linearized power scale to preserve that sensitivity.
        """
        power_scale = 10 ** (float(measurement.rssi) / 20.0)
        signal_weight = max(0.08, min(3.5, power_scale * 350.0))
        weight = max(0.02, measurement.confidence * signal_weight)
        if is_gateway:
            weight *= Trilateration.GATEWAY_WEIGHT_FACTOR
        return weight

    @staticmethod
    def validate_measurements(
        measurements: List[RSSIMeasurement],
        anchors: Dict[str, AnchorPoint],
    ) -> tuple[bool, str]:
        """
        Validate that RSSI measurements are geometrically feasible.
        
        Returns: (is_valid, diagnostic_message)
        """
        if len(measurements) < Trilateration.MIN_MEASUREMENTS:
            return False, f"Insufficient measurements: {len(measurements)} < {Trilateration.MIN_MEASUREMENTS}"

        measured_anchor_ids = {m.node_id for m in measurements}
        missing_required = sorted(Trilateration.REQUIRED_ANCHORS - measured_anchor_ids)
        if missing_required:
            return False, f"Missing required anchors for 3D trilateration: {', '.join(missing_required)}"
        
        # Pairwise geometric consistency check using triangle inequality.
        # For any two anchors i, j with separation L, feasible distances must satisfy:
        # |d_i - d_j| <= L and d_i + d_j >= L (with margin for RSSI noise).
        measurement_map = {m.node_id: m for m in measurements}
        node_ids = [node_id for node_id in ALL_ANCHOR_IDS if node_id in measurement_map and node_id in anchors]
        margin = Trilateration.PAIRWISE_DISTANCE_MARGIN_METERS

        for i in range(len(node_ids)):
            for j in range(i + 1, len(node_ids)):
                node_i = node_ids[i]
                node_j = node_ids[j]
                measurement_i = measurement_map[node_i]
                measurement_j = measurement_map[node_j]
                anchor_i = anchors[node_i]
                anchor_j = anchors[node_j]

                anchor_distance = math.sqrt(
                    ((anchor_i.x - anchor_j.x) ** 2)
                    + ((anchor_i.y - anchor_j.y) ** 2)
                    + ((anchor_i.z - anchor_j.z) ** 2)
                )

                distance_diff = abs(measurement_i.distance - measurement_j.distance)
                distance_sum = measurement_i.distance + measurement_j.distance

                violates_diff = distance_diff > (anchor_distance + margin)
                violates_sum = distance_sum < (anchor_distance - margin)

                if violates_diff or violates_sum:
                    return False, (
                        f"Pairwise geometric inconsistency between {node_i} and {node_j}: "
                        f"d_i={measurement_i.distance:.2f}m, d_j={measurement_j.distance:.2f}m, "
                        f"anchor_separation={anchor_distance:.2f}m, "
                        f"|d_i-d_j|={distance_diff:.2f}, d_i+d_j={distance_sum:.2f}."
                    )
        
        return True, "Measurements are geometrically feasible"

    @staticmethod
    def calculate_position(
        measurements: List[RSSIMeasurement],
        anchors: Dict[str, AnchorPoint],
        use_weights: bool = True,
        prefer_2d: bool = False,
    ) -> Optional[Dict[str, Any]]:
        measurement_map = {
            measurement.node_id: measurement
            for measurement in measurements
            if measurement.node_id in anchors
        }

        if len(measurement_map) < Trilateration.MIN_MEASUREMENTS:
            logger.warning('Insufficient measurements: %s', len(measurement_map))
            return None

        missing_required = sorted(Trilateration.REQUIRED_ANCHORS - set(measurement_map.keys()))
        if missing_required:
            logger.warning('Missing required anchors for 3D trilateration: %s', ', '.join(missing_required))
            return None

        # Validate measurements for geometric feasibility
        is_valid, diagnostic_msg = Trilateration.validate_measurements(measurements, anchors)
        if not is_valid:
            logger.warning('Measurement validation failed: %s', diagnostic_msg)
            return None

        gateway_measurement = measurement_map.get(GATEWAY_NODE_ID)
        if gateway_measurement is None:
            logger.warning('Gateway RSSI is required to recover z from trilateration.')
            return None

        required_ids = [GATEWAY_NODE_ID, 'sn1', 'sn2', 'sn3']
        selected_measurements = [measurement_map[node_id] for node_id in required_ids]
        selected_anchors = [anchors[node_id] for node_id in required_ids]

        # Initial guess from weighted anchor centroid.
        init_weights = []
        for m in selected_measurements:
            if use_weights:
                init_weights.append(Trilateration._measurement_weight(m, is_gateway=(m.node_id == GATEWAY_NODE_ID)))
            else:
                init_weights.append(1.0)
        init_weights_np = np.array(init_weights, dtype=float)
        if np.sum(init_weights_np) <= 0:
            init_weights_np = np.ones_like(init_weights_np)
        anchor_positions = np.array([a.position() for a in selected_anchors], dtype=float)
        position = np.average(anchor_positions, axis=0, weights=init_weights_np)
        if prefer_2d:
            position[2] = FIXED_DEVICE_HEIGHT_METERS

        for _ in range(Trilateration.MAX_GAUSS_NEWTON_ITERATIONS):
            jacobian_rows: List[List[float]] = []
            residuals: List[float] = []
            row_weights: List[float] = []

            for anchor, measurement in zip(selected_anchors, selected_measurements):
                delta = position - anchor.position()
                predicted_distance = float(np.linalg.norm(delta))
                if predicted_distance < 1e-6:
                    predicted_distance = 1e-6

                residual = predicted_distance - measurement.distance
                grad = delta / predicted_distance
                if prefer_2d:
                    grad[2] = 0.0

                jacobian_rows.append([float(grad[0]), float(grad[1]), float(grad[2])])
                residuals.append(residual)
                if use_weights:
                    row_weights.append(Trilateration._measurement_weight(
                        measurement,
                        is_gateway=(measurement.node_id == GATEWAY_NODE_ID)
                    ))
                else:
                    row_weights.append(1.0)

            jacobian = np.array(jacobian_rows, dtype=float)
            residual_vector = np.array(residuals, dtype=float)
            weight_vector = np.array(row_weights, dtype=float)

            if np.any(weight_vector <= 0):
                weight_vector = np.ones_like(weight_vector)

            weighted_jacobian = np.diag(np.sqrt(weight_vector)) @ jacobian
            weighted_residual = np.diag(np.sqrt(weight_vector)) @ residual_vector

            try:
                delta_position, _, _, _ = np.linalg.lstsq(weighted_jacobian, -weighted_residual, rcond=None)
            except np.linalg.LinAlgError as exc:
                logger.error('3D weighted trilateration failed: %s', exc)
                return None

            position = position + delta_position
            if prefer_2d:
                position[2] = FIXED_DEVICE_HEIGHT_METERS

            if float(np.linalg.norm(delta_position)) < Trilateration.GAUSS_NEWTON_TOLERANCE:
                break

        x = float(position[0])
        y = float(position[1])
        z = float(position[2])

        predicted_distances: Dict[str, float] = {}
        residual_components: List[float] = []
        for node_id, measurement in measurement_map.items():
            anchor = anchors[node_id]
            predicted_distance = math.sqrt(
                ((x - anchor.x) ** 2)
                + ((y - anchor.y) ** 2)
                + ((z - anchor.z) ** 2)
            )
            predicted_distances[node_id] = predicted_distance
            residual_components.append(predicted_distance - measurement.distance)

        residual_error = float(np.sqrt(np.mean(np.square(residual_components)))) if residual_components else 0.0
        measurement_confidence = float(np.mean([measurement.confidence for measurement in measurement_map.values()]))
        geometry_score = max(0.0, 1.0 - min(1.0, residual_error / 5.0))
        confidence = max(0.05, min(1.0, (measurement_confidence * 0.7) + (geometry_score * 0.3)))
        accuracy = max(0.05, min(1.0, confidence * geometry_score))

        # Check if solution quality is acceptable
        is_reliable = residual_error < Trilateration.MAX_RESIDUAL_ERROR and confidence > Trilateration.MIN_CONFIDENCE_THRESHOLD
        if not is_reliable:
            if residual_error >= Trilateration.MAX_RESIDUAL_ERROR:
                logger.warning(
                    'High residual error (%.2f m): Measurements may be inconsistent or RSSI data may be stale. '
                    'Verify all RSSI readings are from the same measurement cycle.',
                    residual_error
                )
            if confidence <= Trilateration.MIN_CONFIDENCE_THRESHOLD:
                logger.warning(
                    'Low confidence (%.2f): Solution quality is poor. '
                    'Consider re-measuring or checking RSSI data consistency.',
                    confidence
                )

        return {
            'position': {'x': x, 'y': y, 'z': z},
            'residual_error': residual_error,
            'confidence': confidence,
            'accuracy': accuracy,
            'is_reliable': is_reliable,
            'num_measurements': len(measurement_map),
            'predicted_distances': predicted_distances,
            'measurement_validation': diagnostic_msg if not is_valid else 'OK',
            'timestamp': datetime.now().isoformat(),
        }


def localize_device(
    device_id: str,
    rssi_readings: Dict[str, int],
    anchors: Optional[Dict[str, AnchorPoint]] = None,
    use_2d: bool = True,
    filter_outliers: bool = True,
) -> Optional[Dict[str, Any]]:
    anchors = anchors or get_default_anchors()
    measurements: List[RSSIMeasurement] = []

    for node_id in ALL_ANCHOR_IDS:
        if node_id not in rssi_readings or node_id not in anchors:
            continue

        rssi = rssi_readings[node_id]
        calibrated_rssi = calibrate_rssi(node_id, rssi)
        if filter_outliers and (calibrated_rssi > -20 or calibrated_rssi < -120):
            logger.debug('Skipping outlier RSSI for %s: raw=%s dBm calibrated=%s dBm', node_id, rssi, calibrated_rssi)
            continue

        distance = RSSIToDistance.rssi_to_distance(rssi, node_id=node_id)
        confidence = RSSIToDistance.calculate_confidence(rssi, distance, len(rssi_readings), node_id=node_id)
        measurements.append(
            RSSIMeasurement(
                node_id=node_id,
                rssi=calibrated_rssi,
                distance=distance,
                timestamp=datetime.now(),
                confidence=confidence,
            )
        )

    if len(measurements) < Trilateration.MIN_MEASUREMENTS:
        logger.warning('%s has only %s valid RSSI measurements.', device_id, len(measurements))
        return None

    result = Trilateration.calculate_position(
        measurements=measurements,
        anchors=anchors,
        use_weights=True,
        prefer_2d=use_2d,
    )
    if result is None:
        return None

    result['device_id'] = device_id
    result['rssi_readings'] = {node_id: rssi_readings[node_id] for node_id in rssi_readings if node_id in anchors}
    result['distances'] = {
        measurement.node_id: measurement.distance
        for measurement in measurements
    }
    return result


def calculate_coordinates_from_rssi(
    gateway_rssi: int,
    sn1_rssi: int,
    sn2_rssi: int,
    sn3_rssi: int,
    use_2d: bool = True,
) -> Optional[Dict[str, Any]]:
    return localize_device(
        device_id='manual-rssi-calculation',
        rssi_readings={
            'gateway': gateway_rssi,
            'sn1': sn1_rssi,
            'sn2': sn2_rssi,
            'sn3': sn3_rssi,
        },
        anchors=get_default_anchors(),
        use_2d=use_2d,
    )