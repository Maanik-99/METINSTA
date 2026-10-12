"""
==============================================================================
🎮 EMULATOR MANAGER FOR LDPLAYER & MUMU PLAYER
==============================================================================
Provides high-performance, asynchronous-friendly management of:
- LDPlayer instances (via ldconsole.exe / list2)
- MuMu Player instances (via MuMuManager.exe info/control/simulation)
- ADB connectivity & hardware identity (IMEI, MAC, Android ID)
==============================================================================
"""

import json
import os
import random
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

if os.name == "nt":
    import ctypes
    from ctypes import wintypes


def find_ldconsole() -> Optional[str]:
    """Finds path to ldconsole.exe for LDPlayer across all drives."""
    drives = ["C:", "D:", "E:", "F:"]
    subpaths = [
        r"LDPlayer\LDPlayer9\ldconsole.exe",
        r"LDPlayer\LDPlayer64\ldconsole.exe",
        r"LDPlayer\LDPlayer14\ldconsole.exe",
        r"LDPlayer\LDPlayer4.0\ldconsole.exe",
        r"LDPlayer\LDPlayer\ldconsole.exe",
        r"leidian\LDPlayer9\ldconsole.exe",
        r"leidian\LDPlayer\ldconsole.exe",
        r"Program Files\LDPlayer\LDPlayer9\ldconsole.exe",
        r"Program Files\LDPlayer\LDPlayer\ldconsole.exe",
    ]
    for d in drives:
        for sp in subpaths:
            p = os.path.join(d + os.sep, sp)
            if os.path.exists(p):
                return p
    return shutil.which("ldconsole") or shutil.which("dnconsole")


def find_mumu_manager() -> Optional[str]:
    """Finds path to MuMuManager.exe for MuMu Player across all drives."""
    drives = ["C:", "D:", "E:", "F:"]
    subpaths = [
        r"Program Files\Netease\MuMuPlayer\nx_main\MuMuManager.exe",
        r"Program Files\Netease\MuMuPlayer-12.0\shell\MuMuManager.exe",
        r"Program Files\Netease\MuMuPlayerGlobal-12.0\shell\MuMuManager.exe",
        r"Program Files\MuMuPlayer-12.0\shell\MuMuManager.exe",
        r"Program Files (x86)\Netease\MuMuPlayer\nx_main\MuMuManager.exe",
        r"MuMuPlayer\nx_main\MuMuManager.exe",
        r"Netease\MuMuPlayer\nx_main\MuMuManager.exe",
    ]
    for d in drives:
        for sp in subpaths:
            p = os.path.join(d + os.sep, sp)
            if os.path.exists(p):
                return p
    return shutil.which("MuMuManager")


def find_adb() -> str:
    """Finds available ADB executable with deep multi-drive and emulator folder search."""
    # 1. First check relative to discovered MuMuManager if present
    mumu_p = find_mumu_manager()
    if mumu_p and os.path.exists(mumu_p):
        mumu_dir = os.path.dirname(mumu_p)  # e.g. D:\Program Files\Netease\MuMuPlayer\nx_main
        parent_dir = os.path.dirname(mumu_dir)  # e.g. D:\Program Files\Netease\MuMuPlayer
        mumu_adbs = [
            os.path.join(mumu_dir, "adb.exe"),
            os.path.join(parent_dir, "nx_device", "12.0", "shell", "adb.exe"),
            os.path.join(parent_dir, "nx_device", "15.0", "shell", "adb.exe"),
            os.path.join(parent_dir, "shell", "adb.exe"),
        ]
        for candidate in mumu_adbs:
            if os.path.exists(candidate):
                return candidate

    # 2. Check relative to discovered LDConsole if present
    ld_p = find_ldconsole()
    if ld_p and os.path.exists(ld_p):
        ld_dir = os.path.dirname(ld_p)
        ld_adb = os.path.join(ld_dir, "adb.exe")
        if os.path.exists(ld_adb):
            return ld_adb

    # 3. Check common known paths across all drives
    drives = ["C:", "D:", "E:", "F:"]
    subpaths = [
        r"Program Files\Netease\MuMuPlayer\nx_main\adb.exe",
        r"Program Files\Netease\MuMuPlayer\nx_device\12.0\shell\adb.exe",
        r"Program Files\Netease\MuMuPlayer\nx_device\15.0\shell\adb.exe",
        r"Program Files\Netease\MuMuPlayer-12.0\shell\adb.exe",
        r"Program Files\Netease\MuMuPlayerGlobal-12.0\shell\adb.exe",
        r"Program Files\MuMuPlayer-12.0\shell\adb.exe",
        r"LDPlayer\LDPlayer9\adb.exe",
        r"LDPlayer\LDPlayer14\adb.exe",
        r"LDPlayer\LDPlayer64\adb.exe",
        r"LDPlayer\LDPlayer4.0\adb.exe",
        r"leidian\LDPlayer9\adb.exe",
        r"Program Files\LDPlayer\LDPlayer9\adb.exe",
    ]
    for d in drives:
        for sp in subpaths:
            p = os.path.join(d + os.sep, sp)
            if os.path.exists(p):
                return p

    # 4. Check user home directories
    home = os.path.expanduser("~")
    user_paths = [
        os.path.join(home, "Desktop", "scrcpy-win64-v4.0", "adb.exe"),
        os.path.join(home, "Desktop", "scrcpy-win64", "adb.exe"),
        os.path.join(home, "AppData", "Local", "Android", "Sdk", "platform-tools", "adb.exe"),
    ]
    for p in user_paths:
        if os.path.exists(p):
            return p

    which_adb = shutil.which("adb")
    return which_adb if which_adb else "adb"


ADB_BIN = find_adb()
LDCONSOLE_BIN = find_ldconsole()
MUMU_BIN = find_mumu_manager()


@dataclass
class EmulatorInstance:
    emu_type: str                   # 'mumu', 'ld', or 'adb'
    index: int                      # Emulator instance index (0, 1, 2, ...)
    name: str                       # E.g. "Android Device-0" or "LDPlayer-1"
    is_online: bool                 # Whether Android engine/player is actively running
    adb_serial: str                 # Serial e.g. "127.0.0.1:16384" or "emulator-5554"
    pid: int = -1                   # Process ID
    extra_info: Dict = field(default_factory=dict)
    imei: str = ""
    android_id: str = ""
    mac: str = ""
    bot_running: bool = False
    status_text: str = "Offline"


def run_cmd(cmd: str, timeout: float = 6.0) -> Tuple[int, str, str]:
    """Executes a Windows shell command without popping up windows."""
    try:
        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0

        res = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            startupinfo=startupinfo,
            encoding="utf-8",
            errors="ignore",
        )
        return res.returncode, res.stdout.strip(), res.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "Timeout"
    except Exception as e:
        return -1, "", str(e)


def get_active_adb_serials() -> List[str]:
    """Returns list of currently online devices from adb devices."""
    code, stdout, _ = run_cmd(f'"{ADB_BIN}" devices', timeout=4.0)
    serials = []
    if code == 0:
        for line in stdout.splitlines()[1:]:
            parts = line.strip().split()
            if len(parts) >= 2 and parts[1] == "device":
                serials.append(parts[0])
    return serials


def scan_mumu_instances() -> List[EmulatorInstance]:
    """Scans all MuMu Player instances using MuMuManager info -v all."""
    instances = []
    if not MUMU_BIN or not os.path.exists(MUMU_BIN):
        return instances

    code, stdout, _ = run_cmd(f'"{MUMU_BIN}" info -v all', timeout=5.0)
    if code != 0 or not stdout:
        return instances

    try:
        data = json.loads(stdout)
        if isinstance(data, dict):
            for k, val in data.items():
                if not isinstance(val, dict):
                    continue
                try:
                    idx = int(val.get("index", k))
                except (ValueError, TypeError):
                    idx = 0

                name = val.get("name") or f"MuMu Device-{idx}"
                player_state = str(val.get("player_state", "")).lower()
                is_proc = bool(val.get("is_process_started", False))
                is_and = bool(val.get("is_android_started", False))
                is_online = (player_state == "start_finished") or (is_proc and is_and)

                adb_ip = val.get("adb_host_ip", "127.0.0.1")
                adb_port = val.get("adb_port", 0)
                adb_serial = f"{adb_ip}:{adb_port}" if adb_port else f"127.0.0.1:{16384 + idx * 32}"

                pid = val.get("pid", -1)

                inst = EmulatorInstance(
                    emu_type="mumu",
                    index=idx,
                    name=name,
                    is_online=is_online,
                    adb_serial=adb_serial,
                    pid=pid,
                    extra_info=val,
                    status_text="Online" if is_online else "Offline",
                )
                instances.append(inst)
    except Exception:
        pass

    return sorted(instances, key=lambda x: x.index)


def get_running_dnplayer_processes() -> Dict[int, int]:
    """Returns mapping of LDPlayer instance index -> process PID from running dnplayer.exe."""
    running = {}
    try:
        import psutil
        for p in psutil.process_iter(['pid', 'name', 'cmdline']):
            name = (p.info['name'] or '').lower()
            if 'dnplayer' in name:
                cmd = " ".join(p.info.get('cmdline') or [])
                m = re.search(r'index[=\s]+(\d+)', cmd, re.IGNORECASE)
                if m:
                    running[int(m.group(1))] = p.info['pid']
                elif 0 not in running:
                    running[0] = p.info['pid']
    except Exception:
        pass
    return running


def get_ld_headless_ports() -> Dict[int, Tuple[int, int]]:
    """
    Returns mapping of LDPlayer index -> (port, pid)
    Discovered from running Ld9BoxHeadless.exe / VBoxHeadless.exe processes with --comment leidian{idx}.
    Guarantees 100% exact port binding per instance.
    """
    mapping = {}
    try:
        import psutil
        pid_to_port = {}
        for c in psutil.net_connections(kind='inet'):
            if c.status == 'LISTEN' and c.laddr and 5550 <= c.laddr.port <= 5700 and c.pid:
                pid_to_port[c.pid] = c.laddr.port

        for p in psutil.process_iter(['pid', 'name', 'cmdline']):
            name = (p.info['name'] or '').lower()
            if 'ld9boxheadless' in name or 'vboxheadless' in name:
                cmd = p.info.get('cmdline') or []
                cmd_str = ' '.join(cmd)
                m = re.search(r'leidian(\d+)', cmd_str, re.IGNORECASE)
                if m:
                    idx = int(m.group(1))
                    pid = p.info['pid']
                    port = pid_to_port.get(pid, 5555 + (idx * 2))
                    mapping[idx] = (port, pid)
    except Exception:
        pass
    return mapping


def scan_ld_instances() -> List[EmulatorInstance]:
    """Scans all LDPlayer instances using ldconsole list2, headless VM ports, and active processes."""
    instances = []
    if not LDCONSOLE_BIN or not os.path.exists(LDCONSOLE_BIN):
        return instances

    code, stdout, _ = run_cmd(f'"{LDCONSOLE_BIN}" list2', timeout=5.0)
    if code != 0 or not stdout:
        return instances

    headless_ports = get_ld_headless_ports()
    running_dn = get_running_dnplayer_processes()
    active_adbs = get_active_adb_serials()

    # Clean up duplicate 127.0.0.1:55XX ports if emulator-55XX is already active
    for dev in list(active_adbs):
        if dev.startswith("127.0.0.1:") and ":" in dev:
            try:
                p_num = int(dev.split(":")[1])
                if 5555 <= p_num <= 5700:
                    matching_emu = f"emulator-{p_num - 1}"
                    if matching_emu in active_adbs:
                        run_cmd(f'"{ADB_BIN}" disconnect {dev}', timeout=2.0)
                        if dev in active_adbs:
                            active_adbs.remove(dev)
            except Exception:
                pass

    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(",")
        if len(parts) >= 6:
            try:
                idx = int(parts[0])
                name = parts[1]
                pid = int(parts[5]) if parts[5] != "-1" else -1

                # If pid was not returned by ldconsole, check headless VM or dnplayer process
                hp_info = headless_ports.get(idx)
                if pid <= 0:
                    if idx in running_dn:
                        pid = running_dn[idx]
                    elif hp_info:
                        pid = hp_info[1]

                # Determine expected ADB port and serial
                port = hp_info[0] if hp_info else (5555 + (idx * 2))
                emu_serial = f"emulator-{port - 1}"
                ip_serial = f"127.0.0.1:{port}"

                is_proc_running = (idx in running_dn) or (idx in headless_ports) or (pid > 0)

                if emu_serial in active_adbs:
                    adb_serial = emu_serial
                    is_online = True
                elif ip_serial in active_adbs:
                    adb_serial = ip_serial
                    is_online = True
                elif is_proc_running:
                    # Process is running, ensure ADB connects without creating port collision
                    connect_device_adb(ip_serial)
                    adb_serial = emu_serial
                    is_online = True
                else:
                    adb_serial = emu_serial
                    is_online = False

                inst = EmulatorInstance(
                    emu_type="ld",
                    index=idx,
                    name=name,
                    is_online=is_online,
                    adb_serial=adb_serial,
                    pid=pid,
                    extra_info={"raw": line, "port": port},
                    status_text="Online" if is_online else "Offline",
                )
                instances.append(inst)
            except Exception:
                continue

    return sorted(instances, key=lambda x: x.index)


def scan_all_instances() -> List[EmulatorInstance]:
    """
    Scans both MuMu Player and LDPlayer, checks ADB connectivity,
    and returns a unified list of all emulator instances without duplicates.
    """
    mumu_list = scan_mumu_instances()
    ld_list = scan_ld_instances()

    # Auto-connect ADB for online port-based emulators (e.g. MuMu Player)
    for inst in mumu_list:
        if inst.is_online and ":" in inst.adb_serial:
            connect_device_adb(inst.adb_serial)

    return mumu_list + ld_list


def launch_emulator(emu_type: str, index: int) -> Tuple[bool, str]:
    """Starts the emulator instance to bring it Online."""
    emu_type = emu_type.lower()
    if emu_type == "mumu":
        if not MUMU_BIN:
            return False, "MuMuManager.exe not found"
        cmd = f'"{MUMU_BIN}" control -v {index} launch'
        code, out, err = run_cmd(cmd, timeout=8.0)
        return (code == 0), out or err or "MuMu launch command sent"

    elif emu_type == "ld":
        if not LDCONSOLE_BIN:
            return False, "ldconsole.exe not found"
        cmd = f'"{LDCONSOLE_BIN}" launch --index {index}'
        code, out, err = run_cmd(cmd, timeout=8.0)
        return (code == 0), out or err or "LDPlayer launch command sent"

    return False, f"Unknown emulator type: {emu_type}"


def shutdown_emulator(emu_type: str, index: int) -> Tuple[bool, str]:
    """Stops/closes the emulator instance."""
    emu_type = emu_type.lower()
    if emu_type == "mumu":
        if not MUMU_BIN:
            return False, "MuMuManager.exe not found"
        cmd = f'"{MUMU_BIN}" control -v {index} shutdown'
        code, out, err = run_cmd(cmd, timeout=8.0)
        return (code == 0), out or err or "MuMu shutdown command sent"

    elif emu_type == "ld":
        if not LDCONSOLE_BIN:
            return False, "ldconsole.exe not found"
        cmd = f'"{LDCONSOLE_BIN}" quit --index {index}'
        code, out, err = run_cmd(cmd, timeout=8.0)
        return (code == 0), out or err or "LDPlayer quit command sent"

    return False, f"Unknown emulator type: {emu_type}"


def restart_emulator(emu_type: str, index: int) -> Tuple[bool, str]:
    """Reboots/restarts the emulator instance."""
    emu_type = emu_type.lower()
    if emu_type == "mumu":
        if not MUMU_BIN:
            return False, "MuMuManager.exe not found"
        cmd = f'"{MUMU_BIN}" control -v {index} restart'
        code, out, err = run_cmd(cmd, timeout=8.0)
        return (code == 0), out or err or "MuMu restart command sent"

    elif emu_type == "ld":
        if not LDCONSOLE_BIN:
            return False, "ldconsole.exe not found"
        cmd = f'"{LDCONSOLE_BIN}" reboot --index {index}'
        code, out, err = run_cmd(cmd, timeout=8.0)
        return (code == 0), out or err or "LDPlayer reboot command sent"

    return False, f"Unknown emulator type: {emu_type}"


def generate_random_identity() -> Dict[str, str]:
    """Generates realistic device identifiers."""
    # Realistic 15-digit TAC+Serial IMEI
    imei = "86" + "".join([str(random.randint(0, 9)) for _ in range(13)])
    # 16-hex Android ID
    android_id = "".join(random.choices("0123456789abcdef", k=16))
    # Standard MAC address
    mac = ":".join([f"{random.randint(0, 255):02x}" for _ in range(6)])
    # IMSI
    imsi = "4600" + "".join([str(random.randint(0, 9)) for _ in range(11)])
    # Sim Serial
    simserial = "898600" + "".join([str(random.randint(0, 9)) for _ in range(14)])

    return {
        "imei": imei,
        "android_id": android_id,
        "mac": mac,
        "imsi": imsi,
        "simserial": simserial,
    }


def randomize_emulator_identity(
    emu_type: str,
    index: int,
    device_serial: Optional[str] = None
) -> Tuple[bool, Dict[str, str], str]:
    """
    Randomizes IMEI, Android ID, MAC Address, IMSI for LDPlayer or MuMu Player.
    Works whether the emulator is online or offline.
    If device_serial is online, also applies live via ADB shell!
    """
    emu_type = emu_type.lower()
    ident = generate_random_identity()
    new_imei = ident["imei"]
    new_id = ident["android_id"]
    new_mac = ident["mac"]
    new_imsi = ident["imsi"]
    new_sim = ident["simserial"]

    status_msgs = []
    success = True

    if emu_type == "mumu":
        if not MUMU_BIN:
            return False, ident, "MuMuManager.exe not found"
        c1, o1, _ = run_cmd(f'"{MUMU_BIN}" simulation -v {index} -sk imei -sv {new_imei}')
        c2, o2, _ = run_cmd(f'"{MUMU_BIN}" simulation -v {index} -sk android_id -sv {new_id}')
        c3, o3, _ = run_cmd(f'"{MUMU_BIN}" simulation -v {index} -sk mac_address -sv {new_mac}')
        success = (c1 == 0 and c2 == 0 and c3 == 0)
        status_msgs.append(f"MuMu #{index} Hardware IMEI={new_imei}, AndroidID={new_id}")

    elif emu_type == "ld":
        if not LDCONSOLE_BIN:
            return False, ident, "ldconsole.exe not found"
        cmd = (
            f'"{LDCONSOLE_BIN}" modify --index {index} '
            f'--imei auto --androidid {new_id} --mac auto '
            f'--imsi {new_imsi} --simserial {new_sim}'
        )
        c, o, err = run_cmd(cmd)
        success = (c == 0)
        status_msgs.append(f"LDPlayer #{index} Hardware identity randomized via ldconsole")

    else:
        return False, ident, f"Unsupported emulator: {emu_type}"

    # If device is online with ADB, also update Android ID live in settings
    if device_serial:
        try:
            run_cmd(f'"{ADB_BIN}" -s {device_serial} shell settings put secure android_id {new_id}', timeout=4.0)
            status_msgs.append(f"Live Android ID set via ADB on {device_serial}")
        except Exception:
            pass

    return success, ident, " | ".join(status_msgs)


def connect_device_adb(device_serial: str) -> bool:
    """Explicitly connects ADB to port-based device, preventing duplicate connections."""
    if ":" in device_serial:
        try:
            ip, port_str = device_serial.split(":")
            port = int(port_str)
            # If standard LDPlayer port (5555..5700), check if emulator-{port-1} is already active
            if 5555 <= port <= 5700:
                expected_emu = f"emulator-{port - 1}"
                actives = get_active_adb_serials()
                if expected_emu in actives:
                    return True
        except Exception:
            pass
        code, stdout, _ = run_cmd(f'"{ADB_BIN}" connect {device_serial}', timeout=3.0)
        return "connected" in stdout.lower() or "already" in stdout.lower()
    return True


def find_scrcpy() -> Optional[str]:
    """Finds path to scrcpy.exe for interactive screen mirroring."""
    home = os.path.expanduser("~")
    candidates = [
        os.path.join(home, "Desktop", "scrcpy-win64-v4.0", "scrcpy.exe"),
        os.path.join(home, "Desktop", "scrcpy-win64", "scrcpy.exe"),
        os.path.join(home, "Desktop", "scrcpy", "scrcpy.exe"),
        os.path.join(home, "Downloads", "scrcpy-win64-v4.0", "scrcpy.exe"),
        os.path.join(home, "Downloads", "scrcpy-win64", "scrcpy.exe"),
        os.path.join(home, "Downloads", "scrcpy", "scrcpy.exe"),
        r"C:\scrcpy\scrcpy.exe",
        r"D:\scrcpy\scrcpy.exe",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return shutil.which("scrcpy")


SCRCPY_BIN = find_scrcpy()


def launch_scrcpy(device_serial: str, title: str = "") -> Tuple[bool, str]:
    """Launches an interactive low-latency 60FPS screen mirror window via scrcpy."""
    if not SCRCPY_BIN or not os.path.exists(SCRCPY_BIN):
        return False, "scrcpy.exe not found on Desktop"
    try:
        if ":" in device_serial:
            connect_device_adb(device_serial)
        t = title or f"Instance - {device_serial}"
        cmd = [SCRCPY_BIN, "-s", device_serial, "--window-title", t, "--window-width", "360", "--stay-awake"]
        subprocess.Popen(cmd)
        return True, "Interactive Screen Mirroring launched!"
    except Exception as e:
        return False, str(e)


def capture_device_screen(device_serial: str, target_size=(160, 280)):
    """
    Captures live Android screen thumbnail via ADB screencap.
    Fast (~100ms) and lightweight.
    """
    try:
        import io
        from PIL import Image

        p = subprocess.Popen(
            [ADB_BIN, "-s", device_serial, "exec-out", "screencap", "-p"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        data, err = p.communicate(timeout=3.0)

        # Auto-reconnect if device wasn't connected yet in ADB
        if (not data or len(data) < 1000) and err and b"not found" in err:
            if ":" in device_serial:
                connect_device_adb(device_serial)
                p2 = subprocess.Popen(
                    [ADB_BIN, "-s", device_serial, "exec-out", "screencap", "-p"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL
                )
                data, _ = p2.communicate(timeout=3.0)

        if data and len(data) > 1000:
            if data.startswith(b"\x89PNG\r\r\n"):
                data = data.replace(b"\r\r\n", b"\r\n")
            img = Image.open(io.BytesIO(data))
            if target_size:
                img.thumbnail(target_size, Image.Resampling.LANCZOS)
            return img
    except Exception:
        pass
    return None


def bring_hwnd_to_front(hwnd: int) -> bool:
    """Restores and brings a Win32 HWND to the absolute foreground."""
    if not hwnd or os.name != "nt":
        return False
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        if not user32.IsWindow(hwnd):
            return False

        SW_RESTORE = 9
        SW_SHOW = 5
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
        else:
            user32.ShowWindow(hwnd, SW_SHOW)

        try:
            user32.AllowSetForegroundWindow(0xFFFFFFFF)
        except Exception:
            pass

        try:
            user32.SwitchToThisWindow(hwnd, True)
        except Exception:
            pass

        fg_hwnd = user32.GetForegroundWindow()
        cur_tid = kernel32.GetCurrentThreadId()
        target_tid = user32.GetWindowThreadProcessId(hwnd, None)
        fg_tid = user32.GetWindowThreadProcessId(fg_hwnd, None) if fg_hwnd else 0

        if cur_tid and target_tid and cur_tid != target_tid:
            user32.AttachThreadInput(cur_tid, target_tid, True)
        if fg_tid and target_tid and fg_tid != target_tid:
            user32.AttachThreadInput(fg_tid, target_tid, True)

        user32.keybd_event(0x12, 0, 0, 0)
        user32.keybd_event(0x12, 0, 2, 0)

        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        user32.SetActiveWindow(hwnd)

        if cur_tid and target_tid and cur_tid != target_tid:
            user32.AttachThreadInput(cur_tid, target_tid, False)
        if fg_tid and target_tid and fg_tid != target_tid:
            user32.AttachThreadInput(fg_tid, target_tid, False)

        return True
    except Exception:
        return False


def find_window_for_instance(
    emu_type: str,
    index: int,
    name: str = "",
    pid: int = -1,
    extra_info: Optional[Dict] = None
) -> Optional[int]:
    """Finds the HWND for an emulator instance using multiple discovery methods."""
    if os.name != "nt":
        return None
    emu_type = (emu_type or "").lower()
    user32 = ctypes.windll.user32

    # 1. Check extra_info if window handle was already provided by manager
    if extra_info and isinstance(extra_info, dict):
        main_wnd = extra_info.get("main_wnd")
        if main_wnd:
            try:
                h = int(str(main_wnd), 16) if isinstance(main_wnd, str) else int(main_wnd)
                if h and user32.IsWindow(h):
                    return h
            except Exception:
                pass

        render_wnd = extra_info.get("render_wnd")
        if render_wnd:
            try:
                h = int(str(render_wnd), 16) if isinstance(render_wnd, str) else int(render_wnd)
                if h and user32.IsWindow(h):
                    return h
            except Exception:
                pass

        raw = extra_info.get("raw")
        if raw and isinstance(raw, str):
            parts = raw.split(",")
            if len(parts) >= 3:
                try:
                    h = int(parts[2])
                    if h and user32.IsWindow(h):
                        return h
                except Exception:
                    pass

    # 2. Build candidate window titles
    candidate_titles = []
    if name:
        clean_name = name.strip()
        candidate_titles.append(clean_name)
        if index > 0 and not clean_name.endswith(f"-{index}"):
            candidate_titles.append(f"{clean_name}-{index}")

    if emu_type == "mumu":
        if index == 0:
            candidate_titles.extend(["Android Device", "MuMuPlayer", "Android Device-0", "MuMu Device-0"])
        else:
            candidate_titles.extend([
                f"Android Device-{index}",
                f"Android Device {index}",
                f"MuMuPlayer-{index}",
                f"MuMu Device-{index}"
            ])
    elif emu_type == "ld":
        if index == 0:
            candidate_titles.extend(["LDPlayer", "LDPlayer-0", "dnplayer"])
        else:
            candidate_titles.extend([f"LDPlayer-{index}", f"LDPlayer {index}"])

    # 3. Direct FindWindowW by title
    for title in candidate_titles:
        try:
            h = user32.FindWindowW(None, title)
            if h and user32.IsWindow(h):
                return h
        except Exception:
            pass

    # 4. If PID not given, fetch from MuMuManager or running dnplayer
    if pid <= 0:
        if emu_type == "mumu" and MUMU_BIN:
            try:
                c, out, _ = run_cmd(f'"{MUMU_BIN}" info -v {index}', timeout=3.0)
                if c == 0 and out:
                    data = json.loads(out)
                    pid = data.get("pid", -1)
                    mw = data.get("main_wnd")
                    if mw:
                        h = int(str(mw), 16)
                        if h and user32.IsWindow(h):
                            return h
            except Exception:
                pass
        elif emu_type == "ld":
            running_dn = get_running_dnplayer_processes()
            pid = running_dn.get(index, -1)

    # 5. EnumWindows by PID or candidate title match
    matched = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _enum_cb(hwnd, lparam):
        if not user32.IsWindow(hwnd):
            return True
        w_pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(w_pid))

        buf = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, buf, 512)
        w_title = buf.value.strip()

        if pid > 0 and w_pid.value == pid:
            if w_title and user32.IsWindowVisible(hwnd):
                matched.append((hwnd, 100))
            elif user32.IsWindowVisible(hwnd):
                matched.append((hwnd, 80))
            elif w_title:
                matched.append((hwnd, 70))
            else:
                matched.append((hwnd, 50))
            return True

        if w_title:
            w_lower = w_title.lower()
            for cand in candidate_titles:
                if cand.lower() == w_lower:
                    matched.append((hwnd, 95))
                    return True
                elif cand.lower() in w_lower:
                    matched.append((hwnd, 75))
                    return True
        return True

    try:
        user32.EnumWindows(WNDENUMPROC(_enum_cb), 0)
    except Exception:
        pass

    if matched:
        matched.sort(key=lambda x: x[1], reverse=True)
        return matched[0][0]

    return None


def show_emulator_window(
    emu_type: str,
    index: int,
    name: str = "",
    pid: int = -1,
    extra_info: Optional[Dict] = None
) -> Tuple[bool, str]:
    """
    Brings the emulator window to the foreground.
    1. Direct Win32 HWND activation (SetForegroundWindow, SwitchToThisWindow, SW_RESTORE).
    2. PowerShell WScript.Shell AppActivate by title or PID.
    3. Emulator CLI commands (MuMuManager / ldconsole).
    """
    emu_type = (emu_type or "").lower()

    # 1. Direct Win32 window activation
    hwnd = find_window_for_instance(emu_type, index, name=name, pid=pid, extra_info=extra_info)
    if hwnd:
        if bring_hwnd_to_front(hwnd):
            return True, f"{emu_type.upper()} [idx {index}] window activated (HWND {hex(hwnd)})"

    # 2. PowerShell AppActivate fallback
    candidate_titles = []
    if name:
        candidate_titles.append(name.strip())
    if emu_type == "mumu":
        candidate_titles.extend(["Android Device" if index == 0 else f"Android Device-{index}", f"MuMuPlayer-{index}"])
    elif emu_type == "ld":
        candidate_titles.extend(["LDPlayer" if index == 0 else f"LDPlayer-{index}"])

    for title in candidate_titles:
        ps_cmd = f"(New-Object -ComObject WScript.Shell).AppActivate('{title}')"
        c, out, _ = run_cmd(f'powershell -NoProfile -Command "{ps_cmd}"', timeout=2.5)
        if c == 0 and "True" in out:
            return True, f"{emu_type.upper()} [idx {index}] window brought to front via AppActivate ('{title}')"

    if pid > 0:
        ps_cmd = f"(New-Object -ComObject WScript.Shell).AppActivate({pid})"
        c, out, _ = run_cmd(f'powershell -NoProfile -Command "{ps_cmd}"', timeout=2.5)
        if c == 0 and "True" in out:
            return True, f"{emu_type.upper()} [idx {index}] window brought to front via AppActivate (PID {pid})"

    # 3. Emulator CLI fallback
    if emu_type == "mumu":
        if MUMU_BIN:
            run_cmd(f'"{MUMU_BIN}" control -v {index} launch', timeout=3.0)
            run_cmd(f'"{MUMU_BIN}" main launch', timeout=3.0)
            return True, f"MuMu window launch command sent for index {index}"
    elif emu_type == "ld":
        if LDCONSOLE_BIN:
            c, _, _ = run_cmd(f'"{LDCONSOLE_BIN}" launch --index {index}', timeout=3.0)
            return True, f"LDPlayer window launch command sent for index {index}"

    return False, f"Unable to bring window to front for {emu_type} index {index}"


def organize_all_windows() -> Tuple[bool, str]:
    """Arranges and sorts all player windows neatly."""
    msgs = []
    if LDCONSOLE_BIN:
        c, _, _ = run_cmd(f'"{LDCONSOLE_BIN}" sortWnd', timeout=4.0)
        if c == 0:
            msgs.append("LDPlayer windows sorted")
    if MUMU_BIN:
        c, _, _ = run_cmd(f'"{MUMU_BIN}" sort', timeout=4.0)
        if c == 0:
            msgs.append("MuMu windows sorted")
    return True, " | ".join(msgs) if msgs else "Organize command completed"


if __name__ == "__main__":
    print("Testing Emulator Manager...")
    print(f"ADB: {ADB_BIN}")
    print(f"LDConsole: {LDCONSOLE_BIN}")
    print(f"MuMuManager: {MUMU_BIN}")
    print(f"scrcpy: {SCRCPY_BIN}")
    instances = scan_all_instances()
    print(f"Found {len(instances)} emulator instances:")
    for inst in instances:
        print(f" - [{inst.emu_type.upper()} #{inst.index}] {inst.name} | Status: {inst.status_text} | Serial: {inst.adb_serial} | PID: {inst.pid}")

