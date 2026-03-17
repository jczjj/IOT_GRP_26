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

    MIN_MEASUREMENTS = 3
    GATEWAY_DISTANCE_TOLERANCE_METERS = 0.75

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

        gateway_measurement = measurement_map.get(GATEWAY_NODE_ID)
        if gateway_measurement is None:
            logger.warning('Gateway RSSI is required to recover z from trilateration.')
            return None

        gateway_anchor = anchors[GATEWAY_NODE_ID]
        non_gateway_ids = [node_id for node_id in measurement_map if node_id != GATEWAY_NODE_ID]
        if len(non_gateway_ids) < 2:
            logger.warning('Need gateway plus at least two stationary nodes for localization.')
            return None

        rows: List[List[float]] = []
        targets: List[float] = []
        weights: List[float] = []

        for node_id in non_gateway_ids:
            anchor = anchors[node_id]
            measurement = measurement_map[node_id]
            rows.append([
                2 * (gateway_anchor.x - anchor.x),
                2 * (gateway_anchor.y - anchor.y),
            ])
            targets.append(
                (measurement.distance ** 2)
                - (gateway_measurement.distance ** 2)
                - (anchor.x ** 2 + anchor.y ** 2)
                + (gateway_anchor.x ** 2 + gateway_anchor.y ** 2)
            )
            if use_weights:
                # Give stronger RSSI (less negative dBm) more influence in the
                # weighted least-squares fit while preserving confidence scaling.
                # Example: -55 dBm -> larger multiplier, -90 dBm -> smaller.
                signal_strength_weight = max(
                    0.25,
                    min(3.0, 1.0 + ((70.0 - abs(float(measurement.rssi))) / 20.0))
                )
                weights.append(measurement.confidence * signal_strength_weight)
            else:
                weights.append(1.0)

        matrix = np.array(rows, dtype=float)
        vector = np.array(targets, dtype=float)
        weight_vector = np.array(weights, dtype=float)

        if np.any(weight_vector <= 0):
            weight_vector = np.ones_like(weight_vector)

        weight_matrix = np.diag(np.sqrt(weight_vector))
        weighted_matrix = weight_matrix @ matrix
        weighted_vector = weight_matrix @ vector

        try:
            planar_position, _, _, _ = np.linalg.lstsq(weighted_matrix, weighted_vector, rcond=None)
        except np.linalg.LinAlgError as exc:
            logger.error('Planar trilateration failed: %s', exc)
            return None

        x = float(planar_position[0])
        y = float(planar_position[1])

        if prefer_2d:
            z = FIXED_DEVICE_HEIGHT_METERS
        else:
            horizontal_distance_sq = ((x - gateway_anchor.x) ** 2) + ((y - gateway_anchor.y) ** 2)
            horizontal_distance = math.sqrt(max(horizontal_distance_sq, 0.0))
            z_squared = (gateway_measurement.distance ** 2) - horizontal_distance_sq
            if (horizontal_distance - gateway_measurement.distance) > Trilateration.GATEWAY_DISTANCE_TOLERANCE_METERS:
                logger.warning(
                    'Gateway RSSI is inconsistent with solved x/y coordinates: horizontal=%.3f, gateway_distance=%.3f',
                    horizontal_distance,
                    gateway_measurement.distance,
                )
                return None
            z = gateway_anchor.z + math.sqrt(max(0.0, z_squared))

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

        return {
            'position': {'x': x, 'y': y, 'z': z},
            'residual_error': residual_error,
            'confidence': confidence,
            'accuracy': accuracy,
            'num_measurements': len(measurement_map),
            'predicted_distances': predicted_distances,
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