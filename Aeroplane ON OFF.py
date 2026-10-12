import subprocess
import time
import re
import urllib.request
from datetime import datetime
from airplane_mode import (
    ADB_BIN as ADB,
    DEFAULT_SERIAL as SERIAL,
    get_connected_phone,
    is_usb_phone_connected,
    flight_mode,
    get_device_internal_ip,
    get_public_ip,
    rotate_ip_via_airplane_mode,
    rotate_ip_on_ninja_failure,
    FLIGHT_ON_SECONDS,
    RECONNECT_WAIT,
    RETRY_ON_SECONDS,
    RETRY_WAIT
)

# ============ কনফিগারেশন ============
WAIT_MINUTES = 1
# =====================================


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def run_adb(args, capture=True):
    from airplane_mode import run_adb as _run_adb
    return _run_adb(args, serial=SERIAL, capture=capture)


def check_device():
    return is_usb_phone_connected(SERIAL)


def get_ip():
    """রিয়েল পাবলিক IPv4 রিটার্ন করবে"""
    return get_public_ip()


def change_ip_once():
    flight_mode(True, serial=SERIAL)
    log(f"Flight Mode ON (waiting {FLIGHT_ON_SECONDS}s)")
    time.sleep(FLIGHT_ON_SECONDS)

    flight_mode(False, serial=SERIAL)
    log(f"Flight Mode OFF (waiting {RECONNECT_WAIT}s for reconnect)")
    time.sleep(RECONNECT_WAIT)


def ensure_ip_changed(old_ip):
    attempts = 0
    while True:
        attempts += 1
        new_ip = get_public_ip(retries=6, delay=2)
        internal_ip = get_device_internal_ip(serial=SERIAL)
        log(f"New Real Public IP: {new_ip} (Internal CGNAT: {internal_ip})")

        if new_ip != "N/A" and new_ip != old_ip:
            log(f"✅ SUCCESS! Public IP changed: {old_ip} → {new_ip}")
            return new_ip

        log(f"⚠ Same IP ({attempts} attempt). Toggling Flight Mode again...")
        flight_mode(True, serial=SERIAL)
        time.sleep(RETRY_ON_SECONDS)
        flight_mode(False, serial=SERIAL)
        log(f"Flight Mode OFF (waiting {RETRY_WAIT}s)")
        time.sleep(RETRY_WAIT)


def main():
    print("=" * 50)
    print("  Flight Mode Auto Toggle with Real Public IP Check")
    print("=" * 50)
    print()

    if not check_device():
        log("❌ Device not connected! Check USB cable.")
        return

    log(f"✅ Device connected: {SERIAL}")

    flight_mode(False, serial=SERIAL)
    time.sleep(3)

    old_ip = get_public_ip(retries=5, delay=2)
    internal_ip = get_device_internal_ip(serial=SERIAL)
    log(f"Initial Real Public IP: {old_ip} (Internal CGNAT: {internal_ip})")

    if old_ip == "N/A":
        log("⚠ Could not fetch Public IP! Check internet connection.")
    print()

    try:
        while True:
            log(f"Waiting {WAIT_MINUTES} minutes...")
            time.sleep(WAIT_MINUTES * 60)

            change_ip_once()
            old_ip = ensure_ip_changed(old_ip)
            print()

    except KeyboardInterrupt:
        log("⏹ Stopped. Turning Flight Mode OFF...")
        flight_mode(False, serial=SERIAL)
        log("Done.")


if __name__ == "__main__":
    main()