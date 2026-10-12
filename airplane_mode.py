import os
import sys
import time
import re
import shutil
import subprocess
import urllib.request
from datetime import datetime

# ============ কনফিগারেশন ============
DEFAULT_SERIAL = "RKG6ORMZPFXGAE8X"
FLIGHT_ON_SECONDS = 5
RECONNECT_WAIT = 6
RETRY_ON_SECONDS = 8
RETRY_WAIT = 15
# =====================================

def log(msg, log_fn=None):
    formatted = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    if log_fn and callable(log_fn):
        try:
            log_fn(formatted)
            return
        except Exception:
            pass
    print(formatted, flush=True)


def find_adb() -> str:
    """Finds adb binary in known paths or PATH"""
    explicit = r"C:\Users\_\Downloads\platform-tools-latest-windows\platform-tools\adb.exe"
    if os.path.exists(explicit):
        return explicit

    home = os.path.expanduser("~")
    candidates = [
        os.path.join(home, "Downloads", "platform-tools-latest-windows", "platform-tools", "adb.exe"),
        os.path.join(home, "AppData", "Local", "Android", "Sdk", "platform-tools", "adb.exe"),
        os.path.join(home, "Desktop", "scrcpy-win64-v4.0", "adb.exe"),
        os.path.join(home, "Desktop", "scrcpy-win64", "adb.exe"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c

    which_adb = shutil.which("adb")
    return which_adb if which_adb else "adb"


ADB_BIN = find_adb()


def run_adb(args: list, serial: str = None, capture: bool = True) -> str:
    """Runs an adb command targeting a specific device serial if available"""
    cmd = [ADB_BIN]
    if serial:
        cmd += ["-s", serial]
    cmd += args
    try:
        res = subprocess.run(cmd, capture_output=capture, text=True, timeout=30)
        return res.stdout.strip() if capture else ""
    except subprocess.TimeoutExpired:
        log("⚠ ADB command timed out!")
        return ""
    except FileNotFoundError:
        log("❌ ADB not found! Check ADB_BIN path.")
        return ""
    except Exception as e:
        log(f"⚠ ADB error: {e}")
        return ""


def get_connected_phone(target_serial: str = DEFAULT_SERIAL) -> tuple[bool, str | None]:
    """
    Checks if a physical mobile phone is connected via USB cable (ADB).
    Ignores emulators (e.g., emulator-5554, 127.0.0.1:16384).
    Returns (True, serial) if connected, or (False, None).
    """
    raw_devices = run_adb(["devices", "-l"])
    if not raw_devices:
        return False, None

    physical_devices = []
    lines = raw_devices.splitlines()
    for line in lines[1:]:  # skip 'List of devices attached'
        line = line.strip()
        if not line or line.startswith("*"):
            continue
        parts = line.split()
        if len(parts) >= 2:
            s = parts[0]
            state = parts[1]
            if state.lower() == "device":
                # Filter out emulators
                is_emu = (
                    s.lower().startswith("emulator-")
                    or "127.0.0.1:" in s
                    or "localhost:" in s
                    or ":5555" in s
                    or ":16384" in s
                )
                if not is_emu:
                    physical_devices.append(s)

    if not physical_devices:
        return False, None

    # If the configured serial is found among physical devices, prefer it
    if target_serial and target_serial in physical_devices:
        return True, target_serial

    # Otherwise return the first detected physical USB phone
    return True, physical_devices[0]


def is_usb_phone_connected(target_serial: str = DEFAULT_SERIAL) -> bool:
    """Convenience helper: returns True if USB phone is connected via ADB"""
    connected, _ = get_connected_phone(target_serial)
    return connected


def flight_mode(state: bool, serial: str = None) -> None:
    """Enables or disables airplane mode on the phone via ADB cmd connectivity"""
    action = "enable" if state else "disable"
    run_adb(["shell", "cmd", "connectivity", "airplane-mode", action], serial=serial)


def get_device_internal_ip(serial: str = None) -> str:
    """Fetches device cellular interface local/CGNAT IP"""
    for iface in ["ccmni0", "ccmni1", "rmnet_data0", "pdp0"]:
        out = run_adb(["shell", "ip", "-4", "addr", "show", iface], serial=serial)
        match = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", out)
        if match:
            return match.group(1)

    out = run_adb(["shell", "ip", "-4", "addr", "show"], serial=serial)
    for iface in ["ccmni", "rmnet", "pdp"]:
        match = re.search(
            rf"{iface}\w*.*?inet\s+(\d+\.\d+\.\d+\.\d+)",
            out, re.DOTALL
        )
        if match:
            return match.group(1)

    return "N/A"


def get_public_ip(retries: int = 5, delay: float = 2.0, timeout: float = 4.0) -> str:
    """Fetches real public IPv4 address with multiple services & retries"""
    services = [
        "https://api.ipify.org",
        "https://ipv4.icanhazip.com",
        "http://checkip.amazonaws.com",
        "https://ipinfo.io/ip",
        "https://ifconfig.me/ip",
    ]

    for attempt in range(retries):
        for url in services:
            try:
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "curl/7.84.0"}
                )
                with urllib.request.urlopen(req, timeout=timeout) as response:
                    ip = response.read().decode("utf-8").strip()
                    if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", ip):
                        return ip
            except Exception:
                continue

        if attempt < retries - 1:
            time.sleep(delay)

    return "N/A"


def rotate_ip_via_airplane_mode(
    target_serial: str = DEFAULT_SERIAL,
    flight_on_seconds: int = FLIGHT_ON_SECONDS,
    reconnect_wait: int = RECONNECT_WAIT,
    verify_ip_change: bool = True,
    log_fn=None
) -> tuple[bool, str, str]:
    """
    Toggles Airplane Mode ON and OFF on the USB-connected phone to get a fresh cellular IP.
    Returns: (success: bool, old_ip: str, new_ip: str)
    """
    is_connected, serial = get_connected_phone(target_serial)
    if not is_connected or not serial:
        log("❌ USB Phone is not connected via ADB!", log_fn)
        return False, "", ""

    log(f"✈️ [Airplane Mode] USB phone connected ({serial}). Checking initial IP...", log_fn)
    old_ip = get_public_ip(retries=2, delay=1.0, timeout=3.0)
    log(f"✈️ Current Public IP: {old_ip}", log_fn)

    # 1. Turn Flight Mode ON
    flight_mode(True, serial=serial)
    log(f"✈️ Flight Mode ON on phone ({serial})! Waiting {flight_on_seconds}s...", log_fn)
    time.sleep(flight_on_seconds)

    # 2. Turn Flight Mode OFF
    flight_mode(False, serial=serial)
    log(f"✈️ Flight Mode OFF! Waiting {reconnect_wait}s for mobile network reconnect...", log_fn)
    time.sleep(reconnect_wait)

    new_ip = old_ip
    if verify_ip_change:
        for attempt in range(1, 4):
            new_ip = get_public_ip(retries=5, delay=2.0)
            internal_ip = get_device_internal_ip(serial=serial)
            log(f"✈️ Detected Public IP: {new_ip} (Internal CGNAT: {internal_ip})", log_fn)

            if new_ip != "N/A" and (old_ip == "N/A" or new_ip != old_ip):
                log(f"✅ SUCCESS! IP changed successfully: {old_ip} → {new_ip}", log_fn)
                return True, old_ip, new_ip

            if attempt < 3:
                log(f"⚠ Same IP detected on attempt {attempt}. Retoggling Flight Mode...", log_fn)
                flight_mode(True, serial=serial)
                time.sleep(RETRY_ON_SECONDS)
                flight_mode(False, serial=serial)
                time.sleep(RETRY_WAIT)

    return True, old_ip, new_ip


def rotate_ip_on_ninja_failure(
    reason: str = "Ninja mail create failed",
    target_serial: str = DEFAULT_SERIAL,
    flight_on_seconds: int = FLIGHT_ON_SECONDS,
    reconnect_wait: int = RECONNECT_WAIT,
    fallback_wifi: bool = False,
    log_fn=None
) -> bool:
    """
    High-level trigger called when Ninja mail creation fails:
    1. Checks if USB phone is connected.
    2. If connected, turns Airplane Mode ON, then OFF, rotating IP.
    3. If not connected and fallback_wifi is True, falls back to WiFi toggle.
    """
    is_connected, serial = get_connected_phone(target_serial)
    if is_connected and serial:
        log(f"\n[🔄 AUTO-IP-RESET] {reason}", log_fn)
        log(f"[📱 USB PHONE DETECTED] Triggering Airplane Mode ON/OFF to rotate IP...", log_fn)
        success, old_ip, new_ip = rotate_ip_via_airplane_mode(
            target_serial=serial,
            flight_on_seconds=flight_on_seconds,
            reconnect_wait=reconnect_wait,
            verify_ip_change=True,
            log_fn=log_fn
        )
        return success

    log(f"[ℹ️ AUTO-IP-RESET] USB phone not connected via ADB (reason: {reason}).", log_fn)
    if fallback_wifi:
        try:
            # Try WiFi fallback if available
            from NINJA import toggle_wifi
            log("[🔄 WIFI-FALLBACK] Falling back to WiFi reset to rotate IP...", log_fn)
            return toggle_wifi()
        except Exception as e:
            log(f"[-] WiFi fallback error: {e}", log_fn)

    return False
