#!/usr/bin/env python3
"""
Simple test script to verify connection to iobt-viz bridge.

Usage:
    python test_connection.py
"""

import json
import socket
import sys


def main():
    host = 'localhost'
    port = 9999

    print(f"Connecting to bridge at {host}:{port}...")

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, port))
        sock.settimeout(5.0)

        print("Connected! Waiting for welcome message...")

        # Read welcome message
        data = b""
        while b"\n" not in data:
            chunk = sock.recv(1024)
            if not chunk:
                break
            data += chunk

        if data:
            msg = json.loads(data.decode('utf-8').strip())
            print(f"Welcome: {json.dumps(msg, indent=2)}")

        # Send ping
        print("\nSending ping...")
        sock.sendall(b'{"type":"ping"}\n')

        # Wait for pong
        data = b""
        while b"\n" not in data:
            chunk = sock.recv(1024)
            if not chunk:
                break
            data += chunk

        if data:
            msg = json.loads(data.decode('utf-8').strip())
            print(f"Response: {json.dumps(msg, indent=2)}")

        # Request state
        print("\nRequesting state...")
        sock.sendall(b'{"type":"get_state"}\n')

        data = b""
        while b"\n" not in data:
            chunk = sock.recv(1024)
            if not chunk:
                break
            data += chunk

        if data:
            msg = json.loads(data.decode('utf-8').strip())
            print(f"State: {json.dumps(msg, indent=2)}")

        print("\nConnection test successful!")
        sock.close()
        return 0

    except socket.timeout:
        print("Timeout waiting for response")
        return 1
    except ConnectionRefusedError:
        print(f"Connection refused - is iobt-viz running with bridge enabled?")
        return 1
    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
