#!/usr/bin/env python3
"""
Initialize Database with Default Data
Run this once to set up the database with stationary nodes and devices
"""

import sys
sys.path.insert(0, '/home/yztan120/Application Server')

from database import (
    init_database, 
    insert_device, 
    insert_stationary_node,
    log_system_event
)
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initial device data
INITIAL_DEVICES = [
    {
        'id': 'ed-1',
        'patient_name': 'Margaret Smith',
        'room': '101',
        'location': {'x': 15.0, 'y': 20.0, 'z': 1.2},
        'battery_level': 100,
        'status': 'unknown',
        'wifi_capable': True,
        'last_uplink': None,
        'heart_rate': None,
        'temperature': None,
        'has_image': False
    },
    {
        'id': 'ed-2',
        'patient_name': 'John Anderson',
        'room': '102',
        'location': {'x': 15.0, 'y': 20.0, 'z': 1.2},
        'battery_level': 100,
        'status': 'unknown',
        'wifi_capable': True,
        'last_uplink': None,
        'heart_rate': None,
        'temperature': None,
        'has_image': False
    },
    {
        'id': 'ed-3',
        'patient_name': 'Evelyn Roberts',
        'room': '103',
        'location': {'x': 15.0, 'y': 20.0, 'z': 1.2},
        'battery_level': 100,
        'status': 'unknown',
        'wifi_capable': True,
        'last_uplink': None,
        'heart_rate': None,
        'temperature': None,
        'has_image': False
    },
    {
        'id': 'ed-4',
        'patient_name': 'Robert Chen',
        'room': '104',
        'location': {'x': 15.0, 'y': 20.0, 'z': 1.2},
        'battery_level': 100,
        'status': 'unknown',
        'wifi_capable': True,
        'last_uplink': None,
        'heart_rate': None,
        'temperature': None,
        'has_image': False
    }
]

# Stationary nodes
# Gateway at facility center (15, 20), SNs form equilateral triangle 5m away, 1m lower
STATIONARY_NODES = [
    {
        'id': 'gateway',
        'name': 'LoRaWAN Gateway (Center)',
        'type': 'gateway',
        'location': {'x': 15.0, 'y': 20.0, 'z': 2.5},
        'status': 'online'
    },
    {
        'id': 'sn1',
        'name': 'Stationary Node 1 (East)',
        'type': 'anchor',
        'location': {'x': 20.0, 'y': 20.0, 'z': 1.5},
        'status': 'online'
    },
    {
        'id': 'sn2',
        'name': 'Stationary Node 2 (Northwest)',
        'type': 'anchor',
        'location': {'x': 12.5, 'y': 24.33, 'z': 1.5},
        'status': 'online'
    },
    {
        'id': 'sn3',
        'name': 'Stationary Node 3 (Southwest)',
        'type': 'anchor',
        'location': {'x': 12.5, 'y': 15.67, 'z': 1.5},
        'status': 'online'
    }
]


def main():
    print("="*60)
    print("Elderly Monitoring System - Database Initialization")
    print("="*60)
    
    # Step 1: Initialize database schema
    print("\n[1/3] Creating database schema...")
    init_database('elderly_monitoring.db')
    print("✓ Database schema created")
    
    # Step 2: Insert stationary nodes
    print("\n[2/3] Inserting stationary nodes...")
    for node in STATIONARY_NODES:
        if insert_stationary_node(node):
            print(f"  ✓ Added {node['id']}: {node['name']}")
        else:
            print(f"  ✗ Failed to add {node['id']}")
    
    # Step 3: Insert devices
    print("\n[3/3] Inserting end devices...")
    for device in INITIAL_DEVICES:
        if insert_device(device):
            print(f"  ✓ Added {device['id']}: {device['patient_name']} (Room {device['room']})")
        else:
            print(f"  ✗ Failed to add {device['id']}")
    
    # Log initialization
    log_system_event('INFO', 'Database initialized with default data')
    
    print("\n" + "="*60)
    print("✓ Database initialization complete!")
    print("="*60)
    print(f"\nDatabase file: elderly_monitoring.db")
    print(f"Devices added: {len(INITIAL_DEVICES)}")
    print(f"Stationary nodes added: {len(STATIONARY_NODES)}")
    print("\nYou can now start the application server with:")
    print("  ./run_server.sh")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"Error during initialization: {e}", exc_info=True)
        sys.exit(1)
