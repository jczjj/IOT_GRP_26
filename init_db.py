#!/usr/bin/env python3
import argparse
import os
import sys
import logging
from pathlib import Path

from anchor_layout import get_stationary_nodes

# Ensure local imports work regardless of the current working directory.
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database import (
    init_database,
    insert_stationary_node,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = PROJECT_ROOT / 'elderly_monitoring.db'
STATIONARY_NODES = get_stationary_nodes()


def parse_args():
    parser = argparse.ArgumentParser(
        description='Initialize the SQLite database with the default stationary nodes.'
    )
    parser.add_argument(
        '--db-path',
        default=os.environ.get('IOT_DB_PATH', str(DEFAULT_DB_PATH)),
        help='SQLite database file path. Relative paths are resolved from this script folder.'
    )
    return parser.parse_args()


def resolve_db_path(raw_path: str) -> Path:
    db_path = Path(raw_path).expanduser()
    if not db_path.is_absolute():
        db_path = PROJECT_ROOT / db_path
    return db_path


def main():
    args = parse_args()
    db_path = resolve_db_path(args.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    print("="*60)
    print("Elderly Monitoring System - Database Initialization")
    print("="*60)
    
    print(f"\n[1/2] Creating database at: {db_path}")
    init_database(str(db_path))
    print("✓ Database schema created")
    
    # Step 2: Insert stationary nodes
    print("\n[2/2] Inserting infrastructure nodes at Z=0...")
    for node in STATIONARY_NODES:
        if insert_stationary_node(node):
            print(f"  ✓ Added {node['id']} at ({node['location']['x']}, {node['location']['y']})")
        else:
            print(f"  ✗ Failed to add {node['id']}")
    
    print("\n" + "="*60)
    print(f"✓ Initialization complete! Database saved at: {db_path}")
    print("="*60)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"Error during initialization: {e}", exc_info=True)
        sys.exit(1)