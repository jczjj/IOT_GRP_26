#!/usr/bin/env python3
import sys
import logging

# Assuming your database.py is in this path
sys.path.insert(0, '/home/yztan120/Application Server')

from database import (
    init_database, 
    insert_stationary_node,
    log_system_event
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Coordinates calculated for an equilateral triangle with radius (r) = 5m
# Gateway is at (0, 0, 0)
# SN1: (r, 0, 0) -> East
# SN2: (-r/2, r*sqrt(3)/2, 0) -> Northwest
# SN3: (-r/2, -r*sqrt(3)/2, 0) -> Southwest

STATIONARY_NODES = [
    {
        'id': 'gateway',
        'name': 'LoRaWAN Gateway (Origin)',
        'type': 'gateway',
        'location': {'x': 0.0, 'y': 0.0, 'z': 0.0},
        'status': 'online'
    },
    {
        'id': 'sn1',
        'name': 'Stationary Node 1 (East)',
        'type': 'anchor',
        'location': {'x': 5.0, 'y': 0.0, 'z': 0.0}, # Radius = 5m
        'status': 'online'
    },
    {
        'id': 'sn2',
        'name': 'Stationary Node 2 (Northwest)',
        'type': 'anchor',
        'location': {'x': -2.5, 'y': 4.33, 'z': 0.0}, # -5/2, 5*sqrt(3)/2
        'status': 'online'
    },
    {
        'id': 'sn3',
        'name': 'Stationary Node 3 (Southwest)',
        'type': 'anchor',
        'location': {'x': -2.5, 'y': -4.33, 'z': 0.0}, # -5/2, -5*sqrt(3)/2
        'status': 'online'
    }
]

def main():
    print("="*60)
    print("Elderly Monitoring System - In-Memory DB Initialization")
    print("="*60)
    
    # Step 1: Initialize database in RAM
    # NOTE: Your 'database.py' functions must support passing this string to sqlite3.connect()
    print("\n[1/2] Creating In-Memory database...")
    db_path = ':memory:' 
    init_database(db_path)
    print("✓ Volatile database schema created in RAM")
    
    # Step 2: Insert stationary nodes
    print("\n[2/2] Inserting infrastructure nodes at Z=0...")
    for node in STATIONARY_NODES:
        if insert_stationary_node(node):
            print(f"  ✓ Added {node['id']} at ({node['location']['x']}, {node['location']['y']})")
        else:
            print(f"  ✗ Failed to add {node['id']}")
    
    print("\n" + "="*60)
    print("✓ Initialization complete! (Data will be lost on exit)")
    print("="*60)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"Error during initialization: {e}", exc_info=True)
        sys.exit(1)