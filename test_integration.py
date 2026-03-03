#!/usr/bin/env python3
"""
Quick Test Script for TTN Integration
Tests the connection and basic functionality
"""

import sys
import time
from ttn_integration import get_ttn_client
from device_manager import get_device_manager

def main():
    print("="*60)
    print("TTN Integration Test")
    print("="*60)
    
    # Initialize device manager
    print("\n[1/4] Initializing Device Manager...")
    device_manager = get_device_manager()
    devices = device_manager.get_all_devices()
    print(f"✓ Device Manager initialized with {len(devices)} devices:")
    for device in devices:
        print(f"  - {device['id']}: {device['patient_name']} (Room {device['room']})")
    
    # Initialize TTN client
    print("\n[2/4] Connecting to The Things Network...")
    
    message_count = [0]  # Use list to allow modification in nested function
    
    def on_message(device_id, payload_data, metadata):
        message_count[0] += 1
        
        print(f"\n{'='*60}")
        print(f"📡 UPLINK #{message_count[0]}")
        print(f"{'='*60}")
        
        payload_type = payload_data.get('type')
        
        if payload_type == 'FORWARDED_RSSI':
            # Forwarded RSSI from stationary node
            print(f"Forwarding Device: {device_id}")
            print(f"Original Device:   {payload_data.get('original_device_id')}")
            print(f"Payload Type:      {payload_type}")
            print(f"RSSI (P2P):        {payload_data.get('rssi')} dBm")
            print(f"RSSI (gateway):    {metadata.get('gateway_rssi')} dBm")
        elif payload_type == 'RSSI':
            # Direct RSSI from end device
            print(f"Device:            {device_id}")
            print(f"Payload Type:      {payload_type}")
            print(f"RSSI Value:        {payload_data.get('rssi')} dBm")
            print(f"Gateway RSSI:      {metadata.get('gateway_rssi')} dBm")
            print(f"Gateway SNR:       {metadata.get('gateway_snr')} dB")
        elif payload_type == 'IMAGE':
            # Image data
            print(f"Device:            {device_id}")
            print(f"Payload Type:      {payload_type}")
            print(f"Image Size:        {len(payload_data.get('image_data', []))} bytes")
            print(f"Gateway RSSI:      {metadata.get('gateway_rssi')} dBm")
        elif payload_type == 'HEALTH':
            # Health metrics
            print(f"Device:            {device_id}")
            print(f"Payload Type:      {payload_type}")
            print(f"Heart Rate:        {payload_data.get('heart_rate')} bpm")
            print(f"Temperature:       {payload_data.get('temperature')} °C")
            print(f"Gateway RSSI:      {metadata.get('gateway_rssi')} dBm")
        else:
            # Unknown or other types
            print(f"Device:            {device_id}")
            print(f"Payload Type:      {payload_type}")
            print(f"Gateway RSSI:      {metadata.get('gateway_rssi')} dBm")
            if payload_type == 'UNKNOWN':
                print(f"Raw Payload (hex): {payload_data.get('raw_hex', 'N/A')}")
        
        print(f"Timestamp:         {metadata.get('timestamp')}")
        
        # Process the message
        device_manager.handle_uplink_message(device_id, payload_data, metadata)
        print(f"✓ Data updated in Device Manager")
        print(f"{'='*60}")
    
    ttn_client = get_ttn_client(on_message_callback=on_message)
    ttn_client.start()
    
    # Wait for connection
    time.sleep(2)
    
    if ttn_client.is_connected():
        print("✓ Connected to TTN MQTT broker")
    else:
        print("✗ Failed to connect to TTN")
        print("  Check your internet connection and TTN credentials")
        return
    
    # Test downlink
    print("\n[3/4] Testing Downlink Capability...")
    print("Choose a device to send a test command:")
    print("  1. ed-1 (Margaret Smith)")
    print("  2. ed-2 (John Anderson)")
    print("  3. ed-3 (Evelyn Roberts)")
    print("  4. ed-4 (Robert Chen)")
    print("  5. Skip test")
    
    try:
        choice = input("\nEnter choice (1-5): ").strip()
        
        device_map = {
            '1': 'ed-1',
            '2': 'ed-2',
            '3': 'ed-3',
            '4': 'ed-4'
        }
        
        if choice in device_map:
            device_id = device_map[choice]
            print(f"\nSending location request command to {device_id}...")
            success = ttn_client.send_location_request_command(device_id)
            
            if success:
                print(f"✓ Downlink sent successfully!")
                print(f"  Device {device_id} should now broadcast RSSI ping")
            else:
                print("✗ Failed to send downlink")
                print("  Check API key permissions in TTN Console")
        else:
            print("Skipping downlink test")
    
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        ttn_client.stop()
        return
    
    # Listen for messages
    print("\n[4/4] Listening for Uplink Messages...")
    print("Waiting for messages from devices...")
    print("(Press Ctrl+C to stop)\n")
    
    try:
        start_time = time.time()
        
        while True:
            time.sleep(1)
            
            # Show status every 30 seconds
            elapsed = int(time.time() - start_time)
            if elapsed > 0 and elapsed % 30 == 0:
                print(f"\n[Status] Listening... ({elapsed}s elapsed)")
                print(f"  Messages received: {message_count[0]}")
                print(f"  TTN Connected: {ttn_client.is_connected()}")
    
    except KeyboardInterrupt:
        print("\n\n" + "="*60)
        print("Test Complete")
        print("="*60)
        print(f"\nTotal messages received: {message_count[0]}")
        print("\nCurrent device status:")
        for device in device_manager.get_all_devices():
            rssi_summary = ", ".join([f"{k}:{v}" for k, v in device['rssi_readings'].items() if v is not None])
            print(f"  {device['id']}: Last uplink = {device['last_uplink'] or 'Never'}")
            if rssi_summary:
                print(f"    RSSI readings: {rssi_summary} dBm")
    
    finally:
        print("\nShutting down...")
        ttn_client.stop()
        print("✓ TTN client stopped")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
