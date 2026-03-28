#!/usr/bin/env python3
"""
Database Module - SQLite database for device monitoring
Provides single source of truth for all device data
"""

import sqlite3
import threading
from datetime import datetime
from typing import Optional, List, Dict, Any
import json
import logging
import os

logger = logging.getLogger(__name__)

# Default database path
DB_PATH = 'elderly_monitoring.db'

# Thread-local storage for connections
_thread_local = threading.local()


def get_connection():
    """Get thread-local database connection"""
    if not hasattr(_thread_local, 'connection'):
        _thread_local.connection = sqlite3.connect(DB_PATH, check_same_thread=False)
        _thread_local.connection.row_factory = sqlite3.Row
    return _thread_local.connection


def init_database(db_path: str = DB_PATH):
    """
    Initialize database with schema
    Creates all necessary tables if they don't exist
    """
    global DB_PATH
    DB_PATH = db_path
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Devices table - stores end device information
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS devices (
            device_id TEXT PRIMARY KEY,
            patient_name TEXT NOT NULL,
            room TEXT,
            location_x REAL DEFAULT 0,
            location_y REAL DEFAULT 0,
            location_z REAL DEFAULT 0,
            battery_level INTEGER DEFAULT 0,
            status TEXT DEFAULT 'unknown',
            wifi_capable BOOLEAN DEFAULT 0,
            last_uplink TIMESTAMP,
            last_updated TIMESTAMP,
            heart_rate INTEGER,
            temperature REAL,
            has_image BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Devices table for pathalgo.py
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS devices_location (
            device_id INTEGER PRIMARY KEY,
            x REAL,
            y REAL,
            z REAL
        )
    ''')
    
    # RSSI readings table - stores signal strength measurements
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS rssi_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            node_id TEXT NOT NULL,
            rssi INTEGER NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (device_id) REFERENCES devices(device_id)
        )
    ''')
    
    # Create index for faster queries
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_rssi_device_time 
        ON rssi_readings(device_id, timestamp DESC)
    ''')
    
    # Stationary nodes table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stationary_nodes (
            node_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            location_x REAL NOT NULL,
            location_y REAL NOT NULL,
            location_z REAL NOT NULL,
            status TEXT DEFAULT 'online',
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Images table - stores captured images metadata
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS device_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            image_path TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            size_bytes INTEGER,
            resolution TEXT,
            FOREIGN KEY (device_id) REFERENCES devices(device_id)
        )
    ''')
    
    # System log table - for debugging and audit
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS system_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            level TEXT NOT NULL,
            message TEXT NOT NULL,
            device_id TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    
    logger.info(f"Database initialized at {DB_PATH}")

    # Ensure legacy databases get the new column
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(devices)")
        cols = [r[1] for r in cursor.fetchall()]
        if 'last_updated' not in cols:
            logger.info('Adding missing column "last_updated" to devices table')
            cursor.execute("ALTER TABLE devices ADD COLUMN last_updated TIMESTAMP")
            conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"Could not migrate devices table to add last_updated: {e}")


def insert_device(device_data: Dict[str, Any]) -> bool:
    """Insert or update a device"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO devices (
                device_id, patient_name, room, location_x, location_y, location_z,
                battery_level, status, wifi_capable, last_uplink, last_updated,
                heart_rate, temperature, has_image
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(device_id) DO UPDATE SET
                patient_name=excluded.patient_name,
                room=excluded.room,
                location_x=excluded.location_x,
                location_y=excluded.location_y,
                location_z=excluded.location_z,
                battery_level=excluded.battery_level,
                status=excluded.status,
                wifi_capable=excluded.wifi_capable,
                last_uplink=excluded.last_uplink,
                last_updated=excluded.last_updated,
                heart_rate=excluded.heart_rate,
                temperature=excluded.temperature,
                has_image=excluded.has_image,
                updated_at=CURRENT_TIMESTAMP
        ''', (
            device_data['id'],
            device_data['patient_name'],
            device_data['room'],
            device_data['location']['x'],
            device_data['location']['y'],
            device_data['location']['z'],
            device_data.get('battery_level', 0),
            device_data.get('status', 'unknown'),
            device_data.get('wifi_capable', False),
            device_data.get('last_uplink'),
            device_data.get('last_updated'),
            device_data.get('heart_rate'),
            device_data.get('temperature'),
            device_data.get('has_image', False)
        ))
        
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error inserting device: {e}")
        return False


def get_device(device_id: str) -> Optional[Dict[str, Any]]:
    """Get a specific device by ID"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM devices WHERE device_id = ?', (device_id,))
        row = cursor.fetchone()
        
        if not row:
            return None
        
        # Convert to dict and add RSSI readings
        device = dict(row)
        device['id'] = device['device_id']
        device['location'] = {
            'x': device['location_x'],
            'y': device['location_y'],
            'z': device['location_z']
        }
        
        # Get latest RSSI readings
        device['rssi_readings'] = get_latest_rssi_readings(device_id)
        
        # Clean up redundant fields
        for key in ['device_id', 'location_x', 'location_y', 'location_z', 'created_at', 'updated_at']:
            device.pop(key, None)
        
        return device
    except Exception as e:
        logger.error(f"Error getting device {device_id}: {e}")
        return None


def get_all_devices() -> List[Dict[str, Any]]:
    """Get all devices"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM devices ORDER BY device_id')
        rows = cursor.fetchall()
        
        devices = []
        for row in rows:
            device = dict(row)
            device['id'] = device['device_id']
            device['location'] = {
                'x': device['location_x'],
                'y': device['location_y'],
                'z': device['location_z']
            }
            
            # Get latest RSSI readings
            device['rssi_readings'] = get_latest_rssi_readings(device['device_id'])
            
            # Clean up
            for key in ['device_id', 'location_x', 'location_y', 'location_z', 'created_at', 'updated_at']:
                device.pop(key, None)
            
            devices.append(device)
        
        return devices
    except Exception as e:
        logger.error(f"Error getting all devices: {e}")
        return []


def update_device_location(device_id: str, x: float, y: float, z: float) -> bool:
    """Update device location"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE devices 
            SET location_x = ?, location_y = ?, location_z = ?, last_updated = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE device_id = ?
        ''', (x, y, z, device_id))
        
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Error updating location for {device_id}: {e}")
        return False


def update_device_battery(device_id: str, battery_level: int) -> bool:
    """Update device battery level"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Determine status based on battery
        if battery_level < 20:
            status = 'low_battery'
        elif battery_level < 50:
            status = 'medium_battery'
        else:
            status = 'active'
        
        cursor.execute('''
            UPDATE devices 
            SET battery_level = ?, status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE device_id = ?
        ''', (battery_level, status, device_id))
        
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Error updating battery for {device_id}: {e}")
        return False


def update_device_uplink(device_id: str, timestamp: str) -> bool:
    """Update device last uplink time and set status to active"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE devices 
            SET last_uplink = ?, status = 'active', updated_at = CURRENT_TIMESTAMP
            WHERE device_id = ?
        ''', (timestamp, device_id))
        
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Error updating uplink for {device_id}: {e}")
        return False


def get_device_last_updated(device_id: str) -> Optional[str]:
    """Return the last_updated timestamp string for a device or None"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT last_updated FROM devices WHERE device_id = ?', (device_id,))
        row = cursor.fetchone()
        if row and row['last_updated']:
            return row['last_updated']
        return None
    except Exception as e:
        logger.error(f"Error fetching last_updated for {device_id}: {e}")
        return None


def get_device_last_uplink(device_id: str) -> Optional[str]:
    """Return the last_uplink timestamp string for a device or None"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT last_uplink FROM devices WHERE device_id = ?', (device_id,))
        row = cursor.fetchone()
        if row and row['last_uplink']:
            return row['last_uplink']
        return None
    except Exception as e:
        logger.error(f"Error fetching last_uplink for {device_id}: {e}")
        return None


def update_device_health(device_id: str, heart_rate: Optional[int], temperature: Optional[float]) -> bool:
    """Update device health metrics"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE devices 
            SET heart_rate = ?, temperature = ?, updated_at = CURRENT_TIMESTAMP
            WHERE device_id = ?
        ''', (heart_rate, temperature, device_id))
        
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Error updating health for {device_id}: {e}")
        return False


def insert_rssi_reading(device_id: str, node_id: str, rssi: int, timestamp: Optional[str] = None) -> bool:
    """Insert a new RSSI reading"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        if timestamp:
            cursor.execute('''
                INSERT INTO rssi_readings (device_id, node_id, rssi, timestamp)
                VALUES (?, ?, ?, ?)
            ''', (device_id, node_id, rssi, timestamp))
        else:
            cursor.execute('''
                INSERT INTO rssi_readings (device_id, node_id, rssi)
                VALUES (?, ?, ?)
            ''', (device_id, node_id, rssi))
        
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error inserting RSSI reading: {e}")
        return False


def get_latest_rssi_readings(device_id: str) -> Dict[str, Optional[int]]:
    """Get the latest RSSI reading for each node for a device"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT node_id, rssi
            FROM rssi_readings r1
            WHERE device_id = ?
            AND timestamp = (
                SELECT MAX(timestamp)
                FROM rssi_readings r2
                WHERE r2.device_id = r1.device_id
                AND r2.node_id = r1.node_id
            )
        ''', (device_id,))
        
        readings = {}
        for row in cursor.fetchall():
            readings[row['node_id']] = row['rssi']
        
        # Ensure all nodes are present
        for node in ['gateway', 'sn1', 'sn2', 'sn3']:
            if node not in readings:
                readings[node] = None
        
        return readings
    except Exception as e:
        logger.error(f"Error getting RSSI readings for {device_id}: {e}")
        return {'gateway': None, 'sn1': None, 'sn2': None, 'sn3': None}


def get_latest_rssi_with_timestamps(device_id: str) -> Dict[str, Dict[str, Optional[str]]]:
    """Get the latest RSSI reading and timestamp for each node for a device.

    Returns a dict mapping node_id -> {'rssi': int|None, 'timestamp': str|None}
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT node_id, rssi, timestamp
            FROM rssi_readings r1
            WHERE device_id = ?
            AND timestamp = (
                SELECT MAX(timestamp)
                FROM rssi_readings r2
                WHERE r2.device_id = r1.device_id
                AND r2.node_id = r1.node_id
            )
        ''', (device_id,))

        records = { 'gateway': {'rssi': None, 'timestamp': None},
                    'sn1': {'rssi': None, 'timestamp': None},
                    'sn2': {'rssi': None, 'timestamp': None},
                    'sn3': {'rssi': None, 'timestamp': None} }

        for row in cursor.fetchall():
            records[row['node_id']] = {'rssi': row['rssi'], 'timestamp': row['timestamp']}

        return records
    except Exception as e:
        logger.error(f"Error getting RSSI records for {device_id}: {e}")
        return { 'gateway': {'rssi': None, 'timestamp': None},
                 'sn1': {'rssi': None, 'timestamp': None},
                 'sn2': {'rssi': None, 'timestamp': None},
                 'sn3': {'rssi': None, 'timestamp': None} }


def insert_stationary_node(node_data: Dict[str, Any]) -> bool:
    """Insert or update a stationary node"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO stationary_nodes (node_id, name, type, location_x, location_y, location_z, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(node_id) DO UPDATE SET
                name=excluded.name,
                type=excluded.type,
                location_x=excluded.location_x,
                location_y=excluded.location_y,
                location_z=excluded.location_z,
                status=excluded.status,
                last_seen=CURRENT_TIMESTAMP
        ''', (
            node_data['id'],
            node_data['name'],
            node_data['type'],
            node_data['location']['x'],
            node_data['location']['y'],
            node_data['location']['z'],
            node_data.get('status', 'online')
        ))
        
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error inserting stationary node: {e}")
        return False


def get_all_stationary_nodes() -> List[Dict[str, Any]]:
    """Get all stationary nodes"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM stationary_nodes')
        rows = cursor.fetchall()
        
        nodes = []
        for row in rows:
            node = dict(row)
            node['id'] = node['node_id']
            node['location'] = {
                'x': node['location_x'],
                'y': node['location_y'],
                'z': node['location_z']
            }
            
            # Clean up
            for key in ['node_id', 'location_x', 'location_y', 'location_z']:
                node.pop(key, None)
            
            # Convert last_seen to ISO format if present
            if node.get('last_seen'):
                node['last_seen'] = node['last_seen']
            
            nodes.append(node)
        
        return nodes
    except Exception as e:
        logger.error(f"Error getting stationary nodes: {e}")
        return []


def insert_device_image(device_id: str, image_path: str, size_bytes: int, resolution: str = None) -> bool:
    """Insert device image metadata"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO device_images (device_id, image_path, size_bytes, resolution)
            VALUES (?, ?, ?, ?)
        ''', (device_id, image_path, size_bytes, resolution))
        
        # Update device has_image flag
        cursor.execute('''
            UPDATE devices SET has_image = 1, updated_at = CURRENT_TIMESTAMP
            WHERE device_id = ?
        ''', (device_id,))
        
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error inserting image metadata: {e}")
        return False


def get_latest_device_image(device_id: str) -> Optional[Dict[str, Any]]:
    """Get the latest image for a device"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM device_images
            WHERE device_id = ?
            ORDER BY timestamp DESC
            LIMIT 1
        ''', (device_id,))
        
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None
    except Exception as e:
        logger.error(f"Error getting image for {device_id}: {e}")
        return None


def get_device_images(device_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Get recent image metadata for a device (newest first)."""
    try:
        safe_limit = max(1, min(int(limit), 200))
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT * FROM device_images
            WHERE device_id = ?
            ORDER BY timestamp DESC, id DESC
            LIMIT ?
        ''', (device_id, safe_limit))

        rows = cursor.fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"Error getting image history for {device_id}: {e}")
        return []


def log_system_event(level: str, message: str, device_id: Optional[str] = None) -> bool:
    """Log system event"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO system_log (level, message, device_id)
            VALUES (?, ?, ?)
        ''', (level, message, device_id))
        
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error logging system event: {e}")
        return False


if __name__ == "__main__":
    # Test database initialization
    init_database('test_monitoring.db')
    print("✓ Database initialized successfully")
