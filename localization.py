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
    """Solve 2D position from stationary anchors only (sn1/sn2/sn3)."""

    MIN_MEASUREMENTS = 3
    REQUIRED_ANCHORS = {'sn1', 'sn2', 'sn3'}
    MAX_GAUSS_NEWTON_ITERATIONS = 30
    GAUSS_NEWTON_TOLERANCE = 1e-4
    MAX_GAUSS_NEWTON_STEP = 2.5  # meters per iteration
    DAMPING_FACTOR = 0.7
    PAIRWISE_FEASIBILITY_TOLERANCE = 1.5  # meters; absorbs RSSI model noise
    POSITION_BOUND_MARGIN = 5.0  # extra meters around anchor geometry
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
        
        measurement_map = {m.node_id: m for m in measurements}
        # Pairwise feasibility: any real point P must satisfy
        # |d(P,A) - d(P,B)| <= d(A,B) <= d(P,A) + d(P,B), within tolerance.
        required_ids = sorted(Trilateration.REQUIRED_ANCHORS)
        for i in range(len(required_ids)):
            for j in range(i + 1, len(required_ids)):
                node_i = required_ids[i]
                node_j = required_ids[j]

                dist_i = measurement_map[node_i].distance
                dist_j = measurement_map[node_j].distance

                anchor_i = anchors[node_i]
                anchor_j = anchors[node_j]
                anchor_distance = math.sqrt(
                    ((anchor_i.x - anchor_j.x) ** 2)
                    + ((anchor_i.y - anchor_j.y) ** 2)
                    + ((anchor_i.z - anchor_j.z) ** 2)
                )

                tolerance = max(
                    Trilateration.PAIRWISE_FEASIBILITY_TOLERANCE,
                    0.15 * max(dist_i, dist_j),
                )
                lower_bound = abs(dist_i - dist_j)
                upper_bound = dist_i + dist_j

                if lower_bound > anchor_distance + tolerance:
                    return False, (
                        f"Inconsistent pair ({node_i}, {node_j}): |{dist_i:.2f} - {dist_j:.2f}| = "
                        f"{lower_bound:.2f}m exceeds anchor spacing {anchor_distance:.2f}m "
                        f"(tol {tolerance:.2f}m)."
                    )

                if upper_bound + tolerance < anchor_distance:
                    return False, (
                        f"Inconsistent pair ({node_i}, {node_j}): {dist_i:.2f} + {dist_j:.2f} = "
                        f"{upper_bound:.2f}m is below anchor spacing {anchor_distance:.2f}m "
                        f"(tol {tolerance:.2f}m)."
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

        required_ids = ['sn1', 'sn2', 'sn3']
        selected_measurements = [measurement_map[node_id] for node_id in required_ids]
        selected_anchors = [anchors[node_id] for node_id in required_ids]

        # Validate measurements for geometric feasibility
        is_valid, diagnostic_msg = Trilateration.validate_measurements(measurements, anchors)
        if not is_valid:
            logger.warning(
                'Measurement validation failed: %s. Using best-effort bounded localization.',
                diagnostic_msg,
            )
        measured_max_distance = max(m.distance for m in selected_measurements)

        # Initial guess from weighted anchor centroid (xy only).
        init_weights = []
        for m in selected_measurements:
            if use_weights:
                init_weights.append(Trilateration._measurement_weight(m))
            else:
                init_weights.append(1.0)
        init_weights_np = np.array(init_weights, dtype=float)
        if np.sum(init_weights_np) <= 0:
            init_weights_np = np.ones_like(init_weights_np)
        anchor_xy = np.array([[a.x, a.y] for a in selected_anchors], dtype=float)
        position_xy = np.average(anchor_xy, axis=0, weights=init_weights_np)
        anchor_centroid = np.mean(anchor_xy, axis=0)
        anchor_spread = float(np.max(np.linalg.norm(anchor_xy - anchor_centroid, axis=1)))
        max_solver_radius = measured_max_distance + anchor_spread + Trilateration.POSITION_BOUND_MARGIN

        def weighted_rmse(position: np.ndarray) -> float:
            errors: List[float] = []
            for anchor, measurement in zip(selected_anchors, selected_measurements):
                residual = float(np.linalg.norm(position - np.array([anchor.x, anchor.y], dtype=float))) - measurement.distance
                weight = Trilateration._measurement_weight(measurement) if use_weights else 1.0
                errors.append((residual ** 2) * weight)
            if not errors:
                return 0.0
            return float(np.sqrt(np.mean(errors)))

        for _ in range(Trilateration.MAX_GAUSS_NEWTON_ITERATIONS):
            jacobian_rows: List[List[float]] = []
            residuals: List[float] = []
            row_weights: List[float] = []

            for anchor, measurement in zip(selected_anchors, selected_measurements):
                delta = np.array([position_xy[0] - anchor.x, position_xy[1] - anchor.y], dtype=float)
                predicted_distance = float(np.linalg.norm(delta))
                if predicted_distance < 1e-6:
                    predicted_distance = 1e-6

                residual = predicted_distance - measurement.distance
                grad = delta / predicted_distance

                jacobian_rows.append([float(grad[0]), float(grad[1])])
                residuals.append(residual)
                if use_weights:
                    row_weights.append(Trilateration._measurement_weight(measurement))
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
                delta_xy, _, _, _ = np.linalg.lstsq(weighted_jacobian, -weighted_residual, rcond=None)
            except np.linalg.LinAlgError as exc:
                logger.error('2D weighted trilateration failed: %s', exc)
                return None

            delta_norm = float(np.linalg.norm(delta_xy))
            if delta_norm > Trilateration.MAX_GAUSS_NEWTON_STEP:
                delta_xy = delta_xy * (Trilateration.MAX_GAUSS_NEWTON_STEP / delta_norm)

            baseline_error = weighted_rmse(position_xy)
            best_position = position_xy
            best_error = baseline_error
            step_scale = Trilateration.DAMPING_FACTOR

            for _ in range(8):
                candidate_position = position_xy + (delta_xy * step_scale)
                offset = candidate_position - anchor_centroid
                offset_norm = float(np.linalg.norm(offset))
                if offset_norm > max_solver_radius:
                    candidate_position = anchor_centroid + (offset * (max_solver_radius / offset_norm))

                candidate_error = weighted_rmse(candidate_position)
                if candidate_error < best_error:
                    best_position = candidate_position
                    best_error = candidate_error

                if candidate_error <= baseline_error:
                    break

                step_scale *= 0.5

            position_xy = best_position

            if float(np.linalg.norm(delta_xy)) < Trilateration.GAUSS_NEWTON_TOLERANCE:
                break

        x = float(position_xy[0])
        y = float(position_xy[1])
        z = 0.0

        predicted_distances: Dict[str, float] = {}
        residual_components: List[float] = []
        for node_id in required_ids:
            measurement = measurement_map[node_id]
            anchor = anchors[node_id]
            predicted_distance = math.sqrt(
                ((x - anchor.x) ** 2)
                + ((y - anchor.y) ** 2)
                + ((z - anchor.z) ** 2)
            )
            predicted_distances[node_id] = predicted_distance
            residual_components.append(predicted_distance - measurement.distance)

        residual_error = float(np.sqrt(np.mean(np.square(residual_components)))) if residual_components else 0.0
        measurement_confidence = float(np.mean([measurement_map[node_id].confidence for node_id in required_ids]))
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
            'num_measurements': len(required_ids),
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

    for node_id in ('sn1', 'sn2', 'sn3'):
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