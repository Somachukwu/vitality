#!/usr/bin/env python3
"""
Vita Server IP Auto-Patcher
============================
Run this script on the PC running the Vita backend BEFORE flashing the ESP32.
It detects your current local IP and automatically updates every SERVER_*_URL
define in both config.h files so you never have to edit them manually.

Usage (from any directory):
    python vita-esp32/find_server_ip.py
    -- or --
    Double-click  start_server.bat  in vita-backend/ (runs this first, then uvicorn)

Re-run whenever your machine changes WiFi networks.
"""

import os
import re
import socket
import sys

# ── Paths ─────────────────────────────────────────────────────────────────
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))

WEARABLE_CONFIG = os.path.join(SCRIPT_DIR, "vita_wearable", "config.h")
STATION_CONFIG  = os.path.join(SCRIPT_DIR, "vita_station",  "config.h")

# Defines whose IP portion will be replaced
URL_DEFINES = (
    "SERVER_INGEST_URL",
    "SERVER_HEALTH_URL",
    "SERVER_DEVICE_STATUS_URL",
)

# ── IP detection ──────────────────────────────────────────────────────────
def get_local_ip() -> str:
    """Return the LAN IP used for outbound traffic (not 127.0.0.1)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]

# ── Patch a single config.h ───────────────────────────────────────────────
def patch_config(path: str, ip: str) -> None:
    name = os.path.basename(os.path.dirname(path))

    if not os.path.exists(path):
        print(f"  [SKIP]  {name}/config.h — file not found")
        return

    with open(path, "r") as f:
        original = f.read()

    patched = original
    for define in URL_DEFINES:
        # Match:  #define SERVER_INGEST_URL  "http://<old-ip>:<port>/..."
        # Replace only the IP portion, keep everything else.
        patched = re.sub(
            rf'(#define\s+{define}\s+"http://)[\d.]+(:\d+/[^"]*")',
            rf'\g<1>{ip}\2',
            patched,
        )

    if patched == original:
        print(f"  [OK]    {name}/config.h — already up to date (or no URL defines present)")
    else:
        with open(path, "w") as f:
            f.write(patched)
        print(f"  [DONE]  {name}/config.h — server IP updated to {ip}")

# ── Main ──────────────────────────────────────────────────────────────────
def main():
    print()
    print("=" * 62)
    print("  VITA — Server IP Auto-Patcher")
    print("=" * 62)

    try:
        ip = get_local_ip()
    except Exception as e:
        print(f"\n  [ERROR] Could not detect local IP: {e}")
        print("  Make sure you are connected to WiFi.")
        sys.exit(1)

    hostname = socket.gethostname()
    print(f"\n  Hostname  : {hostname}")
    print(f"  Local IP  : {ip}   ← this will be written to config.h")
    print()
    print("  Patching config.h files:")
    patch_config(WEARABLE_CONFIG, ip)
    patch_config(STATION_CONFIG,  ip)

    print()
    print("  Done.  Next steps:")
    print("  1. Run start_server.bat (or: uvicorn app.main:app --host 0.0.0.0 --port 8000)")
    print("  2. Flash both ESP32 boards")
    print("  3. Watch the OLED for 'Server: ONLINE' then 'API key: VALID'")
    print()
    print("  If the OLED shows 'API key: NOT FOUND' — go to the Vita app,")
    print("  Profile > Add Device, paste the Chip UID, copy the api_key")
    print("  into config.h, and reflash.")
    print()
    print("  Re-run this script whenever the PC changes WiFi networks.")
    print("=" * 62)
    print()


if __name__ == "__main__":
    main()
