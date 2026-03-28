#!/usr/bin/env python3
"""Shared anchor geometry and RSSI calibration settings."""

from __future__ import annotations

import copy
import math
from typing import Any, Dict, List

GATEWAY_NODE_ID = 'gateway'
ANCHOR_NODE_IDS = ('sn1', 'sn2', 'sn3')
ALL_ANCHOR_IDS = (GATEWAY_NODE_ID, *ANCHOR_NODE_IDS)

ANCHOR_RADIUS_METERS = 5.0
REFERENCE_RSSI_AT_1_METER = -49
PATH_LOSS_EXPONENT = 3.1      # Fitted from measured points: -59@2m, -62@3m, -71@5m (rounded)
FIXED_DEVICE_HEIGHT_METERS = 0.0  # Devices are at the same level as the gateway in the test room
# Per-node RSSI calibration offsets (added to the raw RSSI before distance conversion).
# Add an entry here only when you have a measured reference distance for that node.
# Positive  = node reads weaker than the model expects; boost to compensate.
# Negative  = node reads stronger than expected; attenuate.
NODE_RSSI_CALIBRATION: Dict[str, int] = {}  # cleared: base model now calibrated for this room


def get_rssi_offset(node_id: str) -> int:
    return NODE_RSSI_CALIBRATION.get(node_id, 0)


def calibrate_rssi(node_id: str, rssi: int) -> int:
    return rssi + get_rssi_offset(node_id)


def get_anchor_layout() -> Dict[str, Dict[str, Any]]:
    triangle_height = ANCHOR_RADIUS_METERS * math.sqrt(3) / 2
    return {
        GATEWAY_NODE_ID: {
            'id': GATEWAY_NODE_ID,
            'name': 'LoRaWAN Gateway (Origin)',
            'type': 'gateway',
            'location': {'x': 0.0, 'y': 0.0, 'z': 0.0},
            'status': 'online',
        },
        'sn1': {
            'id': 'sn1',
            'name': 'Stationary Node 1 (East)',
            'type': 'anchor',
            'location': {'x': ANCHOR_RADIUS_METERS, 'y': 0.0, 'z': 0.0},
            'status': 'online',
        },
        'sn2': {
            'id': 'sn2',
            'name': 'Stationary Node 2 (Northwest)',
            'type': 'anchor',
            'location': {'x': -ANCHOR_RADIUS_METERS / 2, 'y': triangle_height, 'z': 0.0},
            'status': 'online',
        },
        'sn3': {
            'id': 'sn3',
            'name': 'Stationary Node 3 (Southwest)',
            'type': 'anchor',
            'location': {'x': -ANCHOR_RADIUS_METERS / 2, 'y': -triangle_height, 'z': 0.0},
            'status': 'online',
        },
    }


def get_stationary_nodes() -> List[Dict[str, Any]]:
    return [copy.deepcopy(node) for node in get_anchor_layout().values()]