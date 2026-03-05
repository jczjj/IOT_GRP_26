#!/usr/bin/env python3
"""
Initialize Database Schema Only
Run this once to set up the database with schema and stationary nodes (infrastructure)

Note: End devices are created dynamically when they send their first message via TTN
No dummy/hard-coded device data is used
"""

import sys
sys.path.insert(0, '/home/yztan120/Application Server')

from database import (
    init_database, 
    insert_stationary_node,
    log_system_event
)
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Stationary nodes (infrastructure - these are physical hardware that must be configured)
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
    print("\n[1/2] Creating database schema...")
    init_database('elderly_monitoring.db')
    print("✓ Database schema created")
    print("  - devices table (empty - devices added dynamically from TTN)")
    print("  - rssi_readings table")
    print("  - stationary_nodes table")
    print("  - device_images table")
    
    # Step 2: Insert stationary nodes (infrastructure)
    print("\n[2/2] Inserting infrastructure nodes...")
    for node in STATIONARY_NODES:
        if insert_stationary_node(node):
            print(f"  ✓ Added {node['id']}: {node['name']}")
        else:
            print(f"  ✗ Failed to add {node['id']}")
    
    # Log initialization
    log_system_event('INFO', 'Database initialized - schema only, no dummy devices')
    
    print("\n" + "="*60)
    print("✓ Database initialization complete!")
    print("="*60)
    print(f"\nDatabase file: elderly_monitoring.db")
    print(f"Stationary nodes configured: {len(STATIONARY_NODES)}")
    print(f"End devices: 0 (will be created dynamically from TTN)")
    print("\nDATASET PRINCIPLE:")
    print("• Single source of truth: TTN API responses")
    print("• End devices created on first RSSI message from TTN")
    print("• Positions calculated from RSSI trilateration (not hard-coded)")
    print("• No dummy data used - only real measurements")
    print("\nYou can now start the application server with:")
    print("  python app.py")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"Error during initialization: {e}", exc_info=True)
        sys.exit(1)
