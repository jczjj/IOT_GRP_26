#!/usr/bin/env python3
"""
Test Downlink Command
Tests sending location request command to a device
"""

import sys
sys.path.insert(0, '/home/yztan120/Application Server')

from ttn_integration import TTNClient
import logging

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def test_location_request():
    """Test sending location request command"""
    print("="*60)
    print("Testing Location Request Command")
    print("="*60)
    
    # Create TTN client (don't connect to MQTT, just use for downlink)
    client = TTNClient()
    
    # Test device
    device_id = "ed-1"
    
    print(f"\n📡 Testing downlink to device: {device_id}")
    print(f"   Payload: 0x01 (LOCATION_REQUEST)")
    print(f"   FPort: 1")
    
    # Send location request
    success = client.send_location_request_command(device_id)
    
    if success:
        print("\n✓ Location request command sent successfully!")
    else:
        print("\n✗ Failed to send location request command")
        print("   Check the error logs above for details")
    
    print("="*60)
    return success


if __name__ == "__main__":
    try:
        success = test_location_request()
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"Test failed with exception: {e}", exc_info=True)
        sys.exit(1)
