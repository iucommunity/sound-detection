#!/usr/bin/env python3
"""Simple test script to verify WebSocket server is working."""

import asyncio
import websockets
import json

async def test_websocket():
    """Test WebSocket connection."""
    # Try multiple ports
    ports = [22222, 22223, 22224, 22225, 22226, 22227]
    
    for port in ports:
        uri = f"ws://localhost:{port}"
        print(f"\nAttempting to connect to {uri}...")
        
        try:
            async with websockets.connect(uri, ping_interval=None) as websocket:
                print(f"✓ Connected successfully to port {port}!")
                
                # Wait for a message
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                    data = json.loads(message)
                    print(f"✓ Received message: {data}")
                    print(f"\n✓ Connection test successful on port {port}!")
                    return  # Success, exit
                except asyncio.TimeoutError:
                    print("⚠ No message received within 2 seconds (but connection is established)")
                    print(f"\n✓ Connection test successful on port {port}!")
                    return  # Connection works, exit
        except websockets.exceptions.InvalidStatusCode as e:
            print(f"✗ Connection failed with status code: {e.status_code}")
            if e.status_code == 404:
                print(f"  This means an HTTP server is running on port {port}, not a WebSocket server")
            continue  # Try next port
        except ConnectionRefusedError:
            print(f"✗ Connection refused - server is not running on port {port}")
            continue  # Try next port
        except Exception as e:
            print(f"✗ Connection failed: {e}")
            continue  # Try next port
    
    print(f"\n✗ Could not connect to WebSocket server on any port {ports}")
    print("  Make sure the WebSocket server is running")

if __name__ == "__main__":
    asyncio.run(test_websocket())

