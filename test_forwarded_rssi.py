#!/usr/bin/env python3
"""
Test script to demonstrate forwarded RSSI payload format
"""

import sys
sys.path.insert(0, '/home/yztan120/Application Server')

from ttn_integration import TTNClient

# Example payload from stationary node sn-02 forwarding RSSI from ed-01
def test_forwarded_rssi_parsing():
    print("Testing Forwarded RSSI Payload Parsing")
    print("="*60)
    
    client = TTNClient()
    
    # Test Case 1: Forwarded RSSI from sn-02 for ed-01 with RSSI -39 dBm
    # Format: 0x04 + length(5) + "ed-01" + RSSI(-39 as signed 16-bit big-endian)
    device_id = "ed-01"
    device_id_bytes = device_id.encode('ascii')
    rssi_value = -39
    rssi_bytes = rssi_value.to_bytes(2, byteorder='big', signed=True)
    
    payload = bytes([0x04]) + bytes([len(device_id_bytes)]) + device_id_bytes + rssi_bytes
    
    print(f"\nTest Payload (hex): {payload.hex()}")
    print(f"Breakdown:")
    print(f"  Byte 0:     0x{payload[0]:02x} (type: FORWARDED_RSSI)")
    print(f"  Byte 1:     0x{payload[1]:02x} (device_id length: {payload[1]})")
    print(f"  Bytes 2-6:  {payload[2:2+payload[1]].decode('ascii')} (original device ID)")
    print(f"  Bytes 7-8:  0x{payload[7]:02x}{payload[8]:02x} (RSSI: {rssi_value} dBm)")
    
    # Parse the payload
    result = client._parse_payload(payload)
    
    print(f"\nParsed Result:")
    print(f"  Type:                {result['type']}")
    print(f"  Original Device ID:  {result.get('original_device_id', 'N/A')}")
    print(f"  RSSI (P2P):          {result.get('rssi', 'N/A')} dBm")
    
    print("\n" + "="*60)
    print("✓ Test Complete")
    print("\nYour Arduino should send this format from stationary nodes:")
    print("  byte payload[] = {")
    print("    0x04,                    // Type: Forwarded RSSI")
    print("    0x05,                    // Device ID length")
    print("    'e', 'd', '-', '0', '1', // Original device ID")
    print("    rssi_high_byte,          // RSSI high byte")
    print("    rssi_low_byte            // RSSI low byte")
    print("  };")
    print("\nExample Arduino code:")
    print("  int16_t rssi = -39;")
    print("  payload[5] = (rssi >> 8) & 0xFF;  // High byte")
    print("  payload[6] = rssi & 0xFF;         // Low byte")


if __name__ == "__main__":
    test_forwarded_rssi_parsing()
