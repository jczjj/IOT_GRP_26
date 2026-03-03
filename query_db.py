#!/usr/bin/env python3
"""
Database Query Tool
Simple command-line tool to view database contents
"""

import sys
sys.path.insert(0, '/home/yztan120/Application Server')

import sqlite3
from datetime import datetime
import os

DB_PATH = 'elderly_monitoring.db'

# Try to import tabulate, use fallback if not available
try:
    from tabulate import tabulate
except ImportError:
    # Simple fallback function
    def tabulate(data, headers, tablefmt='grid'):
        if not data:
            return "No data"
        
        # Calculate column widths
        col_widths = [len(str(h)) for h in headers]
        for row in data:
            for i, cell in enumerate(row):
                col_widths[i] = max(col_widths[i], len(str(cell)))
        
        # Build table
        result = []
        
        # Header separator
        sep_line = '+' + '+'.join(['-' * (w + 2) for w in col_widths]) + '+'
        result.append(sep_line)
        
        # Header row
        header_row = '|' + '|'.join([f" {str(headers[i]).ljust(col_widths[i])} " for i in range(len(headers))]) + '|'
        result.append(header_row)
        result.append(sep_line)
        
        # Data rows
        for row in data:
            data_row = '|' + '|'.join([f" {str(row[i]).ljust(col_widths[i])} " for i in range(len(row))]) + '|'
            result.append(data_row)
        
        result.append(sep_line)
        return '\n'.join(result)


def check_db_exists():
    """Check if database exists"""
    if not os.path.exists(DB_PATH):
        print(f"✗ Database not found: {DB_PATH}")
        print("  Run 'python init_db.py' to initialize the database")
        return False
    return True


def show_devices():
    """Show all devices"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT device_id, patient_name, room, battery_level, status, 
               last_uplink, heart_rate, temperature, has_image
        FROM devices
        ORDER BY device_id
    ''')
    
    rows = cursor.fetchall()
    
    if rows:
        print("\n📱 DEVICES")
        print("="*100)
        headers = ['Device ID', 'Patient', 'Room', 'Battery%', 'Status', 'Last Uplink', 'HR', 'Temp', 'Image']
        data = []
        for row in rows:
            data.append([
                row['device_id'],
                row['patient_name'],
                row['room'],
                f"{row['battery_level']}%",
                row['status'],
                row['last_uplink'] or 'Never',
                row['heart_rate'] or '-',
                row['temperature'] or '-',
                '✓' if row['has_image'] else '✗'
            ])
        print(tabulate(data, headers=headers, tablefmt='grid'))
    else:
        print(" No devices found")
    
    conn.close()


def show_rssi_readings():
    """Show recent RSSI readings"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT device_id, node_id, rssi, timestamp
        FROM rssi_readings
        ORDER BY timestamp DESC
        LIMIT 20
    ''')
    
    rows = cursor.fetchall()
    
    if rows:
        print("\n📡 RECENT RSSI READINGS (Last 20)")
        print("="*80)
        headers = ['Device ID', 'Node ID', 'RSSI (dBm)', 'Timestamp']
        data = [[row['device_id'], row['node_id'], row['rssi'], row['timestamp']] for row in rows]
        print(tabulate(data, headers=headers, tablefmt='grid'))
    else:
        print("  No RSSI readings found")
    
    conn.close()


def show_rssi_summary():
    """Show latest RSSI for each device"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('SELECT device_id FROM devices ORDER BY device_id')
    devices = [row['device_id'] for row in cursor.fetchall()]
    
    print("\n📊 LATEST RSSI SUMMARY")
    print("="*80)
    
    for device_id in devices:
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
            ORDER BY node_id
        ''', (device_id,))
        
        readings = cursor.fetchall()
        if readings:
            print(f"\n{device_id}:")
            for r in readings:
                print(f"  {r['node_id']:8s}: {r['rssi']:4d} dBm  (at {r['timestamp']})")
        else:
            print(f"\n{device_id}: No RSSI readings")
    
    conn.close()


def show_stationary_nodes():
    """Show stationary nodes"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM stationary_nodes')
    rows = cursor.fetchall()
    
    if rows:
        print("\n🗼 STATIONARY NODES")
        print("="*80)
        headers = ['Node ID', 'Name', 'Type', 'Location (x,y,z)', 'Status']
        data = []
        for row in rows:
            loc = f"({row['location_x']}, {row['location_y']}, {row['location_z']})"
            data.append([row['node_id'], row['name'], row['type'], loc, row['status']])
        print(tabulate(data, headers=headers, tablefmt='grid'))
    else:
        print("  No stationary nodes found")
    
    conn.close()


def show_images():
    """Show device images"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT device_id, image_path, timestamp, size_bytes, resolution
        FROM device_images
        ORDER BY timestamp DESC
        LIMIT 10
    ''')
    
    rows = cursor.fetchall()
    
    if rows:
        print("\n📷 RECENT IMAGES (Last 10)")
        print("="*100)
        headers = ['Device ID', 'Path', 'Timestamp', 'Size', 'Resolution']
        data = []
        for row in rows:
            size_kb = f"{row['size_bytes'] / 1024:.1f} KB"
            data.append([
                row['device_id'],
                row['image_path'][-40:],  # Truncate path
                row['timestamp'],
                size_kb,
                row['resolution'] or 'Unknown'
            ])
        print(tabulate(data, headers=headers, tablefmt='grid'))
    else:
        print("  No images found")
    
    conn.close()


def show_stats():
    """Show database statistics"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Count records
    cursor.execute('SELECT COUNT(*) FROM devices')
    device_count = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM stationary_nodes')
    node_count = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM rssi_readings')
    rssi_count = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM device_images')
    image_count = cursor.fetchone()[0]
    
    # Get database size
    db_size = os.path.getsize(DB_PATH) / 1024  # KB
    
    print("\n📊 DATABASE STATISTICS")
    print("="*50)
    print(f"Database file:      {DB_PATH}")
    print(f"Database size:      {db_size:.1f} KB")
    print(f"Devices:            {device_count}")
    print(f"Stationary nodes:   {node_count}")
    print(f"RSSI readings:      {rssi_count}")
    print(f"Device images:      {image_count}")
    
    conn.close()


def interactive_menu():
    """Show interactive menu"""
    while True:
        print("\n" + "="*60)
        print("DATABASE QUERY TOOL")
        print("="*60)
        print("1. Show devices")
        print("2. Show stationary nodes")
        print("3. Show recent RSSI readings")
        print("4. Show RSSI summary (latest per device)")
        print("5. Show images")
        print("6. Show database statistics")
        print("7. Show all")
        print("0. Exit")
        print("="*60)
        
        try:
            choice = input("\nEnter choice: ").strip()
            
            if choice == '1':
                show_devices()
            elif choice == '2':
                show_stationary_nodes()
            elif choice == '3':
                show_rssi_readings()
            elif choice == '4':
                show_rssi_summary()
            elif choice == '5':
                show_images()
            elif choice == '6':
                show_stats()
            elif choice == '7':
                show_stats()
                show_devices()
                show_stationary_nodes()
                show_rssi_summary()
                show_images()
            elif choice == '0':
                print("\nGoodbye!")
                break
            else:
                print("\n✗ Invalid choice")
        
        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            print(f"\n✗ Error: {e}")


if __name__ == "__main__":
    if not check_db_exists():
        sys.exit(1)
    
    if len(sys.argv) > 1:
        # Command-line mode
        cmd = sys.argv[1]
        if cmd == 'devices':
            show_devices()
        elif cmd == 'nodes':
            show_stationary_nodes()
        elif cmd == 'rssi':
            show_rssi_readings()
        elif cmd == 'summary':
            show_rssi_summary()
        elif cmd == 'images':
            show_images()
        elif cmd == 'stats':
            show_stats()
        elif cmd == 'all':
            show_stats()
            show_devices()
            show_stationary_nodes()
            show_rssi_summary()
            show_images()
        else:
            print(f"Unknown command: {cmd}")
            print("Usage: python query_db.py [devices|nodes|rssi|summary|images|stats|all]")
    else:
        # Interactive mode
        interactive_menu()
