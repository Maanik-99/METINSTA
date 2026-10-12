"""
==============================================================================
🚀 AUTOMETAINSTABOT - ULTIMATE MULTI-EMULATOR CONTROLLER & GUI DASHBOARD
==============================================================================
Features:
- 100% Lag-Free Architecture (All I/O, Subprocesses & Bot Pipelines in Background)
- Side-by-Side Live View Layout (Screen Preview on LEFT, Log Box on RIGHT)
- Compact Vertical Height to fit multiple emulator cards on screen
- Auto-Trimming Log Buffer (Max 50 lines to prevent memory bloat and lag)
- Exact Monotonic Submission & Approval Counters (100% Fix for Double Counting)
- Full Online & Offline Emulator Instance Detection (LDPlayer & MuMu Player)
- Turn Offline Instances Online (One-click Launch)
- Turn Online Instances Offline (One-click Shutdown)
- One-Click Device / IMEI / Android ID / MAC Randomization for LD & MuMu
- Per-Instance Target Bot Selector (@PayGoeasy_bot vs @Taskl1_bot)
- Interactive 60FPS Screen Mirroring via scrcpy (One-click touch/mouse control)
- One-Click Window Organizer & Auto-Tile (Neatly arranges all emulator windows)
- Run / Stop / Restart AutoMetaInstaBot Pipeline per Instance
- Global Master Controls (Start All, Stop All, Launch All, Randomize All, Tile Windows)
==============================================================================
"""

import asyncio
import json
import os
import queue
import re
import sys
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if os.getcwd() != BASE_DIR:
    try:
        os.chdir(BASE_DIR)
    except Exception:
        pass
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import customtkinter as ctk
from PIL import Image

# Import Core Bot Engine & Config
import autometainstabot
from emulator_manager import (
    EmulatorInstance,
    scan_all_instances,
    launch_emulator,
    shutdown_emulator,
    restart_emulator,
    randomize_emulator_identity,
    connect_device_adb,
    capture_device_screen,
    launch_scrcpy,
    show_emulator_window,
    organize_all_windows,
    ADB_BIN,
    LDCONSOLE_BIN,
    MUMU_BIN,
    SCRCPY_BIN,
)

# CustomTkinter styling
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# Thread-safe log queue for GUI
GUI_LOG_QUEUE = queue.Queue()

# Thread-safe dispatch queue to safely run UI updates from background threads in Tkinter
GUI_DISPATCH_QUEUE = queue.Queue()


def dispatch_to_main(fn, *args, **kwargs):
    """Safely enqueues a callback to execute on Tkinter's main thread (100% thread-safe)."""
    GUI_DISPATCH_QUEUE.put((fn, args, kwargs))


# Persistent Emulator Instance -> Dedicated Individual Telegram Account Mapping
INSTANCE_ACCOUNTS_FILE = os.path.join(BASE_DIR, "instance_accounts.json")


def load_instance_accounts() -> Dict[str, str]:
    if os.path.exists(INSTANCE_ACCOUNTS_FILE):
        try:
            with open(INSTANCE_ACCOUNTS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_instance_accounts(mapping: Dict[str, str]):
    try:
        with open(INSTANCE_ACCOUNTS_FILE, "w", encoding="utf-8") as f:
            json.dump(mapping, f, indent=2)
    except Exception:
        pass


def simplify_log_message(tag: str, raw_msg: str) -> Optional[str]:
    """Transforms verbose logs into clean, emoji-rich, readable status updates."""
    tag_clean = tag.upper().strip()
    msg_clean = raw_msg.strip()

    # Filter out noisy internal debug dumps
    if any(k in tag_clean for k in ["XML", "HIERARCHY", "DUMP", "PAGE-DUMP", "COORD", "REL-COORD", "DEV-SCAN"]):
        return None
    if any(k in msg_clean.lower() for k in ["xml hierarchy", "empty ui dump", "getting screen hierarchy"]):
        return None

    # Highlight key milestones
    if "CYCLE-START" in tag_clean or "Starting Taskly" in msg_clean:
        m = re.search(r"Cycle #?(\d+)", msg_clean, re.IGNORECASE)
        c_num = m.group(1) if m else "1"
        return f"🚀 Starting Cycle #{c_num}..."

    elif "STEP-1" in tag_clean or "Initializing task menu" in msg_clean:
        return "📋 Requesting task from Telegram Bot..."

    elif "BOT CREDENTIALS ACQUIRED" in msg_clean or "Credentials Received" in msg_clean:
        m_user = re.search(r"Target User\s*:\s*([^\r\n]+)", msg_clean)
        u_name = m_user.group(1).strip() if m_user else "Account"
        return f"👤 Got Task from Bot: Username '{u_name}'"

    elif "STEP-2" in tag_clean and "Meta AI" in msg_clean:
        m_name = re.search(r"for:\s*([^\r\n|]+)", msg_clean)
        n_str = m_name.group(1).strip() if m_name else "User"
        return f"🌐 Meta AI: Registering account ({n_str})..."

    elif "STEP-6" in tag_clean or ("Waiting for" in msg_clean and "OTP" in msg_clean):
        return "✉️ Waiting for Meta AI OTP email code..."

    elif "OTP-SUCCESS" in tag_clean or "Found OTP" in msg_clean or "Found Meta OTP" in msg_clean:
        m_otp = re.search(r":\s*(\d{6,8})", msg_clean)
        otp = m_otp.group(1) if m_otp else "Code"
        return f"🔑 Meta OTP Code Received: {otp}"

    elif "STEP-3" in tag_clean or "Running Instagram 2FA" in msg_clean:
        return "📱 Emulator: Starting Instagram & 2FA Setup..."

    elif "2FA-CAPTURED" in tag_clean or "Secret Key:" in msg_clean:
        m_key = re.search(r"Secret Key:\s*'([^']+)'", msg_clean)
        key = m_key.group(1) if m_key else "Key"
        return f"🔐 2FA Secret Key Captured: {key}"

    elif "2FA-OTP" in tag_clean or "Generated 6-Digit OTP" in msg_clean:
        m_totp = re.search(r"pyotp:\s*'(\d{6})'", msg_clean)
        totp = m_totp.group(1) if m_totp else "OTP"
        return f"📲 2FA Authenticator TOTP: {totp}"

    elif "EMAIL-CODE" in tag_clean or "Fetching 8-digit security code" in msg_clean:
        return "📬 Fetching 8-digit Instagram security code from inbox..."

    elif "Found 8-digit 2FA Security Code" in msg_clean:
        m_code = re.search(r":\s*(\d{8})", msg_clean)
        code = m_code.group(1) if m_code else ""
        return f"🔑 8-digit Security Code Received: {code}"

    elif "TG-SUBMITTED" in tag_clean or "report has been received" in msg_clean.lower() or "report received" in msg_clean.lower():
        m_s = re.search(r"(?:Total(?:\s+Submitted)?|Submitted):\s*(\d+)", msg_clean, re.IGNORECASE)
        s_str = f" [Total: {m_s.group(1)}]" if m_s else ""
        return f"📥 ✅ Report Received & Submitted to Bot!{s_str}"

    elif "TG-BALANCE" in tag_clean or "your balance:" in msg_clean.lower() or "current balance:" in msg_clean.lower() or ("balance:" in msg_clean.lower() and "$" in msg_clean):
        m_b = re.search(r"(\$[\d\.]+|\d+\.\d{2,4})", msg_clean)
        b_str = m_b.group(1) if m_b else msg_clean
        if not b_str.startswith("$") and re.match(r"^\d", b_str):
            b_str = f"${b_str}"
        return f"💰 Current Balance: {b_str}"

    elif "TG-APPROVED" in tag_clean or "report approved" in msg_clean.lower() or "+$0.03" in msg_clean:
        m_a = re.search(r"(?:Total(?:\s+Approved)?|Approved):\s*(\d+)", msg_clean, re.IGNORECASE)
        a_str = f" [Total: {m_a.group(1)}]" if m_a else ""
        return f"💰 ✅ Report Approved (+$0.03)!{a_str}"

    elif "Report confirmed and accepted" in msg_clean:
        return "✅ Bot confirmed task report & credited reward!"

    elif "ONLY-META" in tag_clean or "ONLY_META" in tag_clean or "TG-SUBMITTED" in tag_clean:
        return msg_clean

    elif "IMEI-CHANGE" in tag_clean:
        return f"🎲 {msg_clean}"

    elif "FOLLOW" in tag_clean or "CONFIG" in tag_clean:
        return msg_clean if any(msg_clean.startswith(e) for e in ["👥", "👉", "✨"]) else f"👥 {msg_clean}"

    elif "SUCCESS" in tag_clean:
        return f"✅ {msg_clean}"

    elif "ERR" in tag_clean or "FAILED" in tag_clean:
        return f"❌ {msg_clean}"

    elif "WARN" in tag_clean or "CYCLE-ABORT" in tag_clean:
        return f"⚠️ {msg_clean}"

    if len(msg_clean) < 140 and not ("{" in msg_clean and "}" in msg_clean):
        return msg_clean

    return None


def custom_gui_log_callback(tag: str, message: str, instance_name: str = ""):
    """Intercepts autometainstabot logs and pushes to thread-safe GUI queue."""
    simple_msg = simplify_log_message(tag, message)
    if simple_msg:
        t_now = datetime.now().strftime("%H:%M:%S")
        GUI_LOG_QUEUE.put({
            "instance": instance_name or "MAIN",
            "tag": tag,
            "time": t_now,
            "text": simple_msg,
            "raw": message
        })


# Bind autometainstabot logging
autometainstabot.set_log_callback(custom_gui_log_callback)


def ensure_session_wal_mode(sess_path: str):
    """Configures SQLite session database with WAL mode and 60s busy timeout to prevent 'database is locked' errors."""
    import sqlite3
    db_file = sess_path if sess_path.endswith('.session') else f"{sess_path}.session"
    if os.path.exists(db_file):
        try:
            conn = sqlite3.connect(db_file, timeout=15.0)
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA busy_timeout=60000;")
            conn.commit()
            conn.close()
        except Exception:
            pass


class BotRunnerThread(threading.Thread):
    """
    Dedicated background thread per instance for running autometainstabot.TasklyWorker.
    Owns an isolated asyncio loop and TelegramClient session.
    """
    def __init__(self, instance_key: str, account_cfg: dict, device_serial: str, target_bot: str, on_state_change=None, on_account_switched=None, available_bots=None, task_mode: str = "2fa", auto_shift: bool = False, shift_task_mode: str = ""):
        super().__init__(daemon=True)
        self.instance_key = instance_key
        self.account_cfg = account_cfg
        self.device_serial = device_serial
        self.target_bot = target_bot
        self.on_state_change = on_state_change
        self.on_account_switched = on_account_switched
        self.available_bots = available_bots or ["Taskl1_bot", "PayGoeasy_bot", "RealEarningBangladesh_Bot"]
        self.task_mode = task_mode
        self.auto_shift = auto_shift
        self.shift_task_mode = shift_task_mode

        self.worker: Optional[autometainstabot.TasklyWorker] = None
        self.tg_client = None
        self.loop = None
        self._is_stopped = False

    def _on_worker_account_switched(self, instance_name: str, new_phone: str, new_bot: str):
        if self.on_account_switched:
            self.on_account_switched(self.instance_key, new_phone, new_bot)

    def run(self):
        self._is_stopped = False
        mode_icon = "⚡" if "meta" in self.task_mode else ("🎲" if "random" in self.task_mode else ("🍪" if self.task_mode == "cookies" else ("🔐" if "2fa_cookies" in self.task_mode else "🔑")))
        shift_info = f" [Shift: {self.shift_task_mode.upper()}]" if self.auto_shift and self.shift_task_mode else (" [Auto-Shift ON]" if self.auto_shift else "")
        if self.on_state_change:
            self.on_state_change(self.instance_key, f"Running ({mode_icon} @{self.target_bot}){shift_info}", "running")

        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        try:
            self.loop.run_until_complete(self._async_run())
        except (asyncio.CancelledError, KeyboardInterrupt):
            pass
        except Exception as e:
            if not self._is_stopped:
                custom_gui_log_callback("ERR", f"Worker failed: {e}", self.instance_key)
                if self.on_state_change:
                    self.on_state_change(self.instance_key, "Error", "error")
        finally:
            self._cleanup()

    async def _async_run(self):
        from telethon import TelegramClient

        acc = dict(self.account_cfg)
        clean_phone = re.sub(r'[^0-9]', '', str(acc.get('phone', '')))
        sess_name = acc.get('session_name') or f"Taskl1_session_{clean_phone}"
        sess_path = os.path.join(BASE_DIR, sess_name) if not os.path.isabs(sess_name) else sess_name
        if not os.path.exists(sess_path + ".session") and not os.path.exists(sess_path):
            for alt in [f"Taskl1_session_{clean_phone}", f"taskly_session_{clean_phone}"]:
                alt_p = os.path.join(BASE_DIR, alt)
                if os.path.exists(alt_p + ".session"):
                    sess_path = alt_p
                    break

        target_bot = self.target_bot or "Taskl1_bot"
        acc["target_bot"] = target_bot
        acc["target_bots"] = self.available_bots

        shift_str = f" | Auto-Shift: {'ON (' + (self.shift_task_mode.upper() if self.shift_task_mode else 'SAME') + ')' if self.auto_shift else 'OFF'}"
        custom_gui_log_callback("INIT", f"Connecting Telegram for {acc.get('phone')} (Bot: @{target_bot}, Mode: {self.task_mode.upper()}{shift_str})...", self.instance_key)
        ensure_session_wal_mode(sess_path)
        self.tg_client = TelegramClient(sess_path, acc['api_id'], acc['api_hash'])
        for attempt in range(1, 6):
            try:
                await self.tg_client.start(phone=clean_phone)  # type: ignore
                break
            except Exception as conn_err:
                err_str = str(conn_err).lower()
                if ("database is locked" in err_str or "locked" in err_str or "busy" in err_str) and attempt < 5:
                    custom_gui_log_callback("WARN", f"Session database is busy/locked. Waiting for lock release (attempt {attempt}/5)...", self.instance_key)
                    await asyncio.sleep(attempt * 1.5)
                else:
                    raise conn_err

        custom_gui_log_callback("INIT", f"Telegram connected! Launching {self.task_mode.upper()} pipeline targeting @{target_bot}...", self.instance_key)

        self.worker = autometainstabot.TasklyWorker(
            account_cfg=acc,
            device_serial=self.device_serial,
            instance_name=self.instance_key,
            target_bot=target_bot,
            client=self.tg_client,
            on_account_switched_callback=self._on_worker_account_switched,
            available_bots=self.available_bots,
            task_mode=self.task_mode,
            on_state_change=self.on_state_change,
            auto_shift=self.auto_shift,
            shift_task_mode=self.shift_task_mode
        )

        # Initial balance update from bot (skip for Only Meta)
        if self.task_mode not in ["only_meta", "only meta", "only mete"] and "realearning" not in (target_bot or "").lower():
            try:
                await self.worker.fetch_bot_balance()
            except Exception:
                pass

        # Pure-API Meta Pipeline (Fast, lightweight, 100% direct API)
        await self.worker.run()

    def _cleanup(self):
        # 1. Cleanly disconnect tg_client on loop if connected
        if self.tg_client and self.loop and not self.loop.is_closed():
            try:
                if self.tg_client.is_connected():
                    self.loop.run_until_complete(asyncio.wait_for(self.tg_client.disconnect(), timeout=4.0))
            except Exception:
                pass

        # 2. Release account from global pool
        if self.worker and hasattr(self.worker, 'account_cfg') and self.worker.account_cfg.get('phone'):
            autometainstabot.TelegramAccountPool.release_active(self.worker.account_cfg.get('phone'))
        elif self.account_cfg and self.account_cfg.get('phone'):
            autometainstabot.TelegramAccountPool.release_active(self.account_cfg.get('phone'))

        # 3. Cancel any pending tasks
        try:
            pending = [t for t in asyncio.all_tasks(self.loop) if not t.done()]
            if pending:
                for t in pending:
                    t.cancel()
                self.loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        except Exception:
            pass

        try:
            self.loop.run_until_complete(self.loop.shutdown_asyncgens())
        except Exception:
            pass

        try:
            self.loop.close()
        except Exception:
            pass

        # 4. Explicitly close SQLite session connection handles
        if self.tg_client:
            try:
                if hasattr(self.tg_client, 'session') and hasattr(self.tg_client.session, '_conn') and self.tg_client.session._conn:
                    self.tg_client.session._conn.close()
            except Exception:
                pass
            try:
                if hasattr(self.tg_client, 'session') and hasattr(self.tg_client.session, 'close'):
                    self.tg_client.session.close()
            except Exception:
                pass
            self.tg_client = None

        self._is_stopped = True
        if self.on_state_change:
            self.on_state_change(self.instance_key, "Stopped", "stopped")

    def stop(self):
        self._is_stopped = True
        if self.worker:
            self.worker.is_stopped = True
        if self.loop and self.loop.is_running():
            def _cancel():
                for t in asyncio.all_tasks(self.loop):
                    t.cancel()
            self.loop.call_soon_threadsafe(_cancel)


class EmulatorCard(ctk.CTkFrame):
    """
    Rich, compact, interactive card displaying an emulator instance (Online or Offline).
    Layout:
    - Header Row: Brand badge, Name, Status Pill
    - Specs Bar: ADB Serial, PID, Quick Mirror, Quick Show
    - Acc & Bot Row: Telegram Account Dropdown & Target Bot Dropdown
    - Stats Bar: Bal, Cycles, Sub, App (Monotonic, Exact Counters)
    - Body Frame (Horizontal Split):
      - Left Frame: Live Screen Preview (Compact, width 130px, height 195px)
      - Right Frame: Log Box (Autotrimmed to max 50 lines to prevent lag)
    - Action Buttons Bar: Turn Online/Shutdown, Random IMEI, Live View toggle, Run/Stop Bot, Clear
    """
    def __init__(
        self,
        master,
        instance_data: EmulatorInstance,
        accounts: List[dict],
        available_bots: List[str],
        dashboard,
    ):
        super().__init__(master, corner_radius=12, fg_color="#181b22", border_width=1, border_color="#282e3d")
        self.data = instance_data
        self.accounts = accounts
        self.available_bots = available_bots if available_bots else ["Taskl1_bot", "PayGoeasy_bot", "RealEarningBangladesh_Bot"]
        self.dashboard = dashboard
        self.cfg = getattr(dashboard, 'cfg', {}) if dashboard else autometainstabot._CFG
        self.instance_key = f"{self.data.emu_type.upper()}-{self.data.index}"

        # Current metrics (exact monotonic values)
        self.meta_created_count = 0
        self.submitted_count = 0
        self.approved_count = 0
        self.cycle_count = 0
        self.balance = "$0.00"
        self.is_bot_running = False
        self._meta_counted_in_cycle = False

        if self.dashboard and hasattr(self.dashboard, 'get_account_for_instance'):
            self.selected_account = self.dashboard.get_account_for_instance(self.instance_key, self.data.index)
        else:
            self.selected_account = accounts[self.data.index % len(accounts)] if accounts else {}
        self.selected_bot = self.available_bots[0]
        self.auto_shift_var = ctk.BooleanVar(value=False)
        self.selected_shift_mode = "cookies"

        # Live Screen Preview state
        self.preview_active = False
        self.preview_thread: Optional[threading.Thread] = None

        self._build_ui()

    def _build_ui(self):
        # 1. Header Frame
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(10, 3))

        # Brand / Index badge
        type_color = "#3b82f6" if self.data.emu_type == "mumu" else "#f97316"
        badge_text = f"MuMu #{self.data.index}" if self.data.emu_type == "mumu" else f"LDPlayer #{self.data.index}"
        
        self.badge_lbl = ctk.CTkLabel(
            header,
            text=badge_text,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#ffffff",
            fg_color=type_color,
            corner_radius=6,
            padx=8,
            pady=2,
        )
        self.badge_lbl.pack(side="left")

        # Name
        self.name_lbl = ctk.CTkLabel(
            header,
            text=f"  {self.data.name}",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#f1f5f9"
        )
        self.name_lbl.pack(side="left")

        # Status Pill
        self.status_pill = ctk.CTkLabel(
            header,
            text="● Offline" if not self.data.is_online else "● Online",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#ef4444" if not self.data.is_online else "#22c55e",
            fg_color="#2d1519" if not self.data.is_online else "#142d1e",
            corner_radius=8,
            padx=10,
            pady=3,
        )
        self.status_pill.pack(side="right")

        # 2. Specs & Device Info Bar
        info_bar = ctk.CTkFrame(self, fg_color="#11141a", corner_radius=8)
        info_bar.pack(fill="x", padx=12, pady=3)

        serial_text = self.data.adb_serial if self.data.is_online else "Disconnected"
        self.info_lbl = ctk.CTkLabel(
            info_bar,
            text=f"ADB: {serial_text}  |  PID: {self.data.pid if self.data.pid > 0 else 'N/A'}",
            font=ctk.CTkFont(size=11),
            text_color="#94a3b8"
        )
        self.info_lbl.pack(side="left", padx=10, pady=3)

        # Quick Mirror & Show Window shortcuts
        self.btn_quick_show = ctk.CTkButton(
            info_bar,
            text="👁️ Show",
            font=ctk.CTkFont(size=10),
            width=48,
            height=20,
            fg_color="#1e293b",
            hover_color="#334155",
            command=self._on_show_window
        )
        self.btn_quick_show.pack(side="right", padx=(2, 6), pady=2)

        self.btn_quick_mirror = ctk.CTkButton(
            info_bar,
            text="🔍 Mirror",
            font=ctk.CTkFont(size=10, weight="bold"),
            width=56,
            height=20,
            fg_color="#0284c7",
            hover_color="#0369a1",
            command=self._on_launch_mirror
        )
        self.btn_quick_mirror.pack(side="right", padx=2, pady=2)
        if not self.data.is_online:
            self.btn_quick_mirror.configure(state="disabled", fg_color="#334155")
            self.btn_quick_show.configure(state="disabled", fg_color="#334155")

        # 3. Telegram Account & Target Bot Configuration Row
        config_frame = ctk.CTkFrame(self, fg_color="transparent")
        config_frame.pack(fill="x", padx=12, pady=2)

        # Account Selector
        ctk.CTkLabel(
            config_frame,
            text="📱 Acc:",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#cbd5e1"
        ).pack(side="left")

        account_options = [f"{a.get('phone')}" for a in self.accounts]
        if not account_options:
            account_options = ["Not Configured"]

        default_acc_str = f"{self.selected_account.get('phone')}" if self.selected_account and self.selected_account.get('phone') else (account_options[0] if account_options else "Default")
        self.acc_combo = ctk.CTkComboBox(
            config_frame,
            values=account_options,
            command=self._on_account_selected,
            font=ctk.CTkFont(size=11),
            width=145,
            height=24,
            fg_color="#1e2430",
            border_color="#334155"
        )
        self.acc_combo.set(default_acc_str)
        self.acc_combo.pack(side="left", padx=(4, 10))

        # Target Bot Selector (User requirement: Choose between bots from GUI)
        ctk.CTkLabel(
            config_frame,
            text="🤖 Bot:",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#cbd5e1"
        ).pack(side="left")

        clean_bots = [b.lstrip("@") for b in self.available_bots]
        self.bot_combo = ctk.CTkComboBox(
            config_frame,
            values=clean_bots,
            command=self._on_bot_selected,
            font=ctk.CTkFont(size=11),
            width=135,
            height=24,
            fg_color="#1e2430",
            border_color="#334155"
        )
        if self.dashboard and hasattr(self.dashboard, 'selected_global_bot') and self.dashboard.selected_global_bot:
            default_bot = self.dashboard.selected_global_bot
        elif clean_bots:
            default_bot = clean_bots[0]
        else:
            default_bot = "Taskl1_bot"
        self.selected_bot = default_bot
        self.bot_combo.set(default_bot)
        self.bot_combo.pack(side="left", padx=4)

        # Mode Selector (Cookies vs 2FA)
        ctk.CTkLabel(
            config_frame,
            text="📋 Mode:",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#cbd5e1"
        ).pack(side="left", padx=(6, 2))

        if self.dashboard and hasattr(self.dashboard, 'cfg') and self.dashboard.cfg.get("task_mode"):
            cfg_mode = str(self.dashboard.cfg.get("task_mode")).lower()
        else:
            cfg_mode = self.cfg.get("task_mode", "2fa").lower()
        if "meta" in cfg_mode:
            default_mode_str = "⚡ Only Meta"
            self.selected_mode = "only_meta"
        elif "random" in cfg_mode:
            default_mode_str = "🎲 Random 2FA + Cookies"
            self.selected_mode = "random_2fa_cookies"
        elif "2fa" in cfg_mode and "cookie" in cfg_mode:
            default_mode_str = "🔐 2FA + Cookies"
            self.selected_mode = "2fa_cookies"
        elif "cookies" in cfg_mode:
            default_mode_str = "🍪 Cookies"
            self.selected_mode = "cookies"
        else:
            default_mode_str = "🔑 2FA"
            self.selected_mode = "2fa"

        self.mode_combo = ctk.CTkComboBox(
            config_frame,
            values=["🔑 2FA", "🍪 Cookies", "🔐 2FA + Cookies", "🎲 Random 2FA + Cookies", "⚡ Only Meta"],
            command=self._on_mode_selected,
            font=ctk.CTkFont(size=11),
            width=165,
            height=24,
            fg_color="#1e2430",
            border_color="#334155"
        )
        self.mode_combo.set(default_mode_str)
        self.mode_combo.pack(side="left", padx=4)

        # 3.5 Auto-Shift Controls Row (Toggle auto-shift & select task mode on shifted bot)
        shift_frame = ctk.CTkFrame(self, fg_color="transparent")
        shift_frame.pack(fill="x", padx=12, pady=(2, 4))

        self.chk_auto_shift = ctk.CTkCheckBox(
            shift_frame,
            text="🔄 Auto-Shift on Limit",
            variable=self.auto_shift_var,
            command=self._on_auto_shift_toggled,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#f59e0b",
            checkmark_color="#0f172a",
            fg_color="#f59e0b",
            hover_color="#d97706",
            width=160,
            height=22
        )
        self.chk_auto_shift.pack(side="left")

        ctk.CTkLabel(
            shift_frame,
            text="➡️ Shift Task:",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#cbd5e1"
        ).pack(side="left", padx=(10, 4))

        self.shift_task_combo = ctk.CTkComboBox(
            shift_frame,
            values=["🍪 Cookies", "🔑 2FA", "🔐 2FA + Cookies", "🎲 Random 2FA + Cookies", "⚡ Only Meta", "🔄 Same Mode"],
            command=self._on_shift_mode_selected,
            font=ctk.CTkFont(size=11),
            width=165,
            height=24,
            fg_color="#1e2430",
            border_color="#334155"
        )
        self.shift_task_combo.set("🍪 Cookies")
        self.shift_task_combo.pack(side="left", padx=2)

        # 4. Stats Bar
        stats_frame = ctk.CTkFrame(self, fg_color="#131722", corner_radius=6)
        stats_frame.pack(fill="x", padx=12, pady=3)

        self.stats_lbl = ctk.CTkLabel(
            stats_frame,
            text="💰 Bal: $0.00  |  🌐 Meta: 0  |  📥 Sub: 0  |  📈 Success: 0.0%",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#38bdf8"
        )
        self.stats_lbl.pack(padx=8, pady=2)

        # 5. BODY FRAME: Horizontal Split (Left = Live Screen Preview, Right = Log Box)
        # This keeps the card compact and displays logs on the right side of the screen!
        self.body_frame = ctk.CTkFrame(self, fg_color="transparent", height=195)
        self.body_frame.pack(fill="x", expand=False, padx=12, pady=4)
        self.body_frame.pack_propagate(False)

        # Left: Live Preview Frame (Compact Phone ratio 125x190)
        self.preview_frame = ctk.CTkFrame(
            self.body_frame,
            width=130,
            height=195,
            fg_color="#0a0d13",
            corner_radius=8,
            border_width=1,
            border_color="#1f293d"
        )
        self.preview_frame.pack_propagate(False)

        self.preview_lbl = ctk.CTkLabel(
            self.preview_frame,
            text="📱 Loading...",
            font=ctk.CTkFont(size=10),
            text_color="#64748b"
        )
        self.preview_lbl.pack(expand=True, fill="both", padx=2, pady=2)

        # Right: Log Box (Auto-trimmed to max 50 lines to prevent lag)
        self.log_box = ctk.CTkTextbox(
            self.body_frame,
            font=ctk.CTkFont(family="Consolas", size=10),
            fg_color="#0b0e14",
            text_color="#e2e8f0",
            corner_radius=8,
            border_width=1,
            border_color="#1e2533",
            wrap="word",
            height=195
        )
        # Initially, log box takes full width
        self.log_box.pack(side="left", fill="both", expand=True)
        self.log_box.configure(state="disabled")

        # 6. Action Buttons Bar
        btn_bar = ctk.CTkFrame(self, fg_color="transparent")
        btn_bar.pack(fill="x", padx=12, pady=(2, 8))

        # Online/Offline toggle
        self.btn_online_toggle = ctk.CTkButton(
            btn_bar,
            text="🚀 Turn Online" if not self.data.is_online else "⏹ Shutdown",
            font=ctk.CTkFont(size=11, weight="bold"),
            width=88,
            height=26,
            fg_color="#059669" if not self.data.is_online else "#b91c1c",
            hover_color="#047857" if not self.data.is_online else "#991b1b",
            command=self._on_toggle_online
        )
        self.btn_online_toggle.pack(side="left", padx=(0, 4))

        # Randomize Device / IMEI
        self.btn_randomize = ctk.CTkButton(
            btn_bar,
            text="🎲 Random IMEI",
            font=ctk.CTkFont(size=11, weight="bold"),
            width=92,
            height=26,
            fg_color="#7c3aed",
            hover_color="#6d28d9",
            command=self._on_randomize_imei
        )
        self.btn_randomize.pack(side="left", padx=4)

        # In-GUI Live Screen Toggle
        self.btn_live_view = ctk.CTkButton(
            btn_bar,
            text="📱 Live View",
            font=ctk.CTkFont(size=11, weight="bold"),
            width=82,
            height=26,
            fg_color="#0284c7",
            hover_color="#0369a1",
            command=self._on_toggle_live_view
        )
        self.btn_live_view.pack(side="left", padx=4)
        if not self.data.is_online:
            self.btn_live_view.configure(state="disabled", fg_color="#334155")

        # Run / Stop Bot Button
        self.btn_run_bot = ctk.CTkButton(
            btn_bar,
            text="▶ Run Bot",
            font=ctk.CTkFont(size=11, weight="bold"),
            width=76,
            height=26,
            fg_color="#16a34a",
            hover_color="#15803d",
            command=self._on_toggle_bot
        )
        self.btn_run_bot.pack(side="left", padx=4)
        if not self.data.is_online:
            self.btn_run_bot.configure(state="disabled", fg_color="#334155")

        # Clear Logs
        self.btn_clear = ctk.CTkButton(
            btn_bar,
            text="🗑 Clear",
            font=ctk.CTkFont(size=11),
            width=50,
            height=26,
            fg_color="#334155",
            hover_color="#475569",
            command=self.clear_logs
        )
        self.btn_clear.pack(side="right")

    def _on_account_selected(self, choice: str):
        for acc in self.accounts:
            if acc.get("phone") and str(acc.get("phone")) in choice:
                # Check if another emulator already has this account selected
                conflict_name = None
                if self.dashboard:
                    for other_key, other_card in self.dashboard.cards.items():
                        if other_key != self.instance_key:
                            if other_card.selected_account and str(other_card.selected_account.get("phone")) == str(acc.get("phone")):
                                conflict_name = other_card.data.name
                                break

                self.selected_account = acc
                if self.dashboard:
                    self.dashboard.instance_account_map[self.instance_key] = acc.get("phone", "")
                    save_instance_accounts(self.dashboard.instance_account_map)
                    autometainstabot.TelegramAccountPool.set_assigned_accounts(self.dashboard.instance_account_map)

                if conflict_name:
                    self.append_log(datetime.now().strftime("%H:%M:%S"), f"⚠️ Notice: Account {acc.get('phone')} is also assigned to {conflict_name}. To avoid interference, each emulator should use a distinct account.")
                else:
                    self.append_log(datetime.now().strftime("%H:%M:%S"), f"✅ Assigned dedicated individual account: {acc.get('phone')}")
                break

    def _on_bot_selected(self, choice: str):
        self.selected_bot = choice.strip().lstrip("@")
        self.append_log(datetime.now().strftime("%H:%M:%S"), f"Target bot set to: @{self.selected_bot}")

    def _on_mode_selected(self, choice: str):
        choice_lower = choice.lower()
        if "meta" in choice_lower:
            self.selected_mode = "only_meta"
        elif "random" in choice_lower:
            self.selected_mode = "random_2fa_cookies"
        elif "2fa" in choice_lower and "cookie" in choice_lower:
            self.selected_mode = "2fa_cookies"
        elif "cookies" in choice_lower:
            self.selected_mode = "cookies"
        else:
            self.selected_mode = "2fa"
        self.append_log(datetime.now().strftime("%H:%M:%S"), f"Task mode set to: {self.selected_mode.upper()}")

    def _on_auto_shift_toggled(self):
        is_on = self.auto_shift_var.get()
        state_str = "ENABLED (will auto-shift on limit/cooldown)" if is_on else "DISABLED (will stay on current bot)"
        self.append_log(datetime.now().strftime("%H:%M:%S"), f"Auto-Shift is now {state_str}")
        if self.dashboard and self.instance_key in self.dashboard.worker_threads:
            runner = self.dashboard.worker_threads[self.instance_key]
            if runner:
                runner.auto_shift = is_on
                if runner.worker:
                    runner.worker.auto_shift = is_on

    def _on_shift_mode_selected(self, choice: str):
        choice_lower = choice.lower()
        if "same" in choice_lower:
            self.selected_shift_mode = ""
        elif "meta" in choice_lower:
            self.selected_shift_mode = "only_meta"
        elif "random" in choice_lower:
            self.selected_shift_mode = "random_2fa_cookies"
        elif "2fa" in choice_lower and "cookie" in choice_lower:
            self.selected_shift_mode = "2fa_cookies"
        elif "cookies" in choice_lower or "cookie" in choice_lower:
            self.selected_shift_mode = "cookies"
        else:
            self.selected_shift_mode = "2fa"
        self.append_log(datetime.now().strftime("%H:%M:%S"), f"Shift target task mode set to: {choice}")
        if self.dashboard and self.instance_key in self.dashboard.worker_threads:
            runner = self.dashboard.worker_threads[self.instance_key]
            if runner:
                runner.shift_task_mode = self.selected_shift_mode
                if runner.worker:
                    runner.worker.shift_task_mode = self.selected_shift_mode

    def update_instance_state(self, new_data: EmulatorInstance):
        old_on = self.data.is_online
        old_serial = self.data.adb_serial
        old_pid = self.data.pid

        self.data = new_data
        is_on = new_data.is_online

        # If online state, serial, and PID have not changed, skip widget reconfiguration!
        if old_on == is_on and old_serial == new_data.adb_serial and old_pid == new_data.pid:
            self.sync_worker_counts()
            return

        if is_on:
            # Keep running worker device_serial synchronized with verified serial
            runner = self.dashboard.worker_threads.get(self.instance_key)
            if runner and runner.worker and new_data.adb_serial:
                runner.worker.device_serial = new_data.adb_serial
                runner.device_serial = new_data.adb_serial

            if not self.is_bot_running:
                self.set_status("Online", "online")
                self.btn_run_bot.configure(state="normal", fg_color="#16a34a", text="▶ Run Bot")
            self.btn_online_toggle.configure(text="⏹ Shutdown", fg_color="#b91c1c", hover_color="#991b1b")
            self.info_lbl.configure(text=f"ADB: {self.data.adb_serial}  |  PID: {self.data.pid}")
            self.btn_live_view.configure(state="normal", fg_color="#0284c7")
            self.btn_quick_mirror.configure(state="normal", fg_color="#0284c7")
            self.btn_quick_show.configure(state="normal", fg_color="#1e293b")
        else:
            if self.is_bot_running:
                self.stop_bot()
            if self.preview_active:
                self._stop_live_preview()
            self.set_status("Offline", "offline")
            self.btn_run_bot.configure(state="disabled", fg_color="#334155", text="▶ Run Bot")
            self.btn_online_toggle.configure(text="🚀 Turn Online", fg_color="#059669", hover_color="#047857")
            self.info_lbl.configure(text="ADB: Disconnected  |  PID: N/A")
            self.btn_live_view.configure(state="disabled", fg_color="#334155")
            self.btn_quick_mirror.configure(state="disabled", fg_color="#334155")
            self.btn_quick_show.configure(state="disabled", fg_color="#334155")

        # Sync authoritative worker counts
        self.sync_worker_counts()

    def sync_worker_counts(self):
        """Pulls authoritative monotonic counter directly from TasklyWorker instance."""
        if threading.current_thread() != threading.main_thread():
            dispatch_to_main(self.sync_worker_counts)
            return
        runner = self.dashboard.worker_threads.get(self.instance_key)
        if runner and runner.worker:
            w = runner.worker
            changed = False
            w_sub = getattr(w, 'submitted_count', 0)
            if w_sub > self.submitted_count:
                self.submitted_count = w_sub
                changed = True
            w_app = getattr(w, 'approved_count', 0)
            if w_app > self.approved_count:
                self.approved_count = w_app
                changed = True
            if hasattr(w, 'current_balance') and w.current_balance:
                self.balance = w.current_balance
                changed = True
            if changed:
                self.update_stats()
                self.dashboard.update_global_summary()

    def _on_toggle_online(self):
        if not self.data.is_online:
            self.append_log(datetime.now().strftime("%H:%M:%S"), f"🚀 Sending launch command to {self.data.name}...")
            self.set_status("Booting...", "working")
            self.btn_online_toggle.configure(state="disabled")

            def _launch():
                ok, msg = launch_emulator(self.data.emu_type, self.data.index)
                self.append_log(datetime.now().strftime("%H:%M:%S"), f"Launch response: {msg}")
                time.sleep(4.0)
                dispatch_to_main(self.dashboard.refresh_instances_now)
                dispatch_to_main(lambda: self.btn_online_toggle.configure(state="normal"))

            threading.Thread(target=_launch, daemon=True).start()
        else:
            self.append_log(datetime.now().strftime("%H:%M:%S"), f"⏹ Shutting down {self.data.name}...")
            self.set_status("Closing...", "waiting")
            if self.is_bot_running:
                self.stop_bot()
            if self.preview_active:
                self._stop_live_preview()

            def _shutdown():
                ok, msg = shutdown_emulator(self.data.emu_type, self.data.index)
                self.append_log(datetime.now().strftime("%H:%M:%S"), f"Shutdown response: {msg}")
                time.sleep(2.0)
                dispatch_to_main(self.dashboard.refresh_instances_now)

            threading.Thread(target=_shutdown, daemon=True).start()

    def _on_randomize_imei(self):
        self.append_log(datetime.now().strftime("%H:%M:%S"), f"🎲 Randomizing hardware identity & IMEI...")
        self.btn_randomize.configure(state="disabled")

        def _do_rand():
            ok, ident, msg = randomize_emulator_identity(
                self.data.emu_type,
                self.data.index,
                device_serial=self.data.adb_serial if self.data.is_online else None
            )
            time_now = datetime.now().strftime("%H:%M:%S")
            if ok:
                self.append_log(time_now, f"✨ Identity Randomized!")
                self.append_log(time_now, f"   IMEI: {ident['imei']} | Android ID: {ident['android_id']}")
                self.append_log(time_now, f"   MAC:  {ident['mac']}")
            else:
                self.append_log(time_now, f"❌ Randomize Failed: {msg}")

            dispatch_to_main(lambda: self.btn_randomize.configure(state="normal"))

        threading.Thread(target=_do_rand, daemon=True).start()

    def _on_show_window(self):
        time_start = datetime.now().strftime("%H:%M:%S")
        self.append_log(time_start, f"Bringing emulator window to foreground...")
        def _do_show():
            ok, msg = show_emulator_window(
                self.data.emu_type,
                self.data.index,
                name=self.data.name,
                pid=self.data.pid,
                extra_info=self.data.extra_info
            )
            time_res = datetime.now().strftime("%H:%M:%S")
            if ok:
                self.append_log(time_res, f"✅ {msg}")
            else:
                self.append_log(time_res, f"⚠️ {msg}")
        threading.Thread(target=_do_show, daemon=True).start()

    def _on_launch_mirror(self):
        if not self.data.is_online:
            return
        self.append_log(datetime.now().strftime("%H:%M:%S"), f"🔍 Launching interactive screen mirror via scrcpy...")
        threading.Thread(target=lambda: launch_scrcpy(self.data.adb_serial, title=f"Mirror - {self.data.name}"), daemon=True).start()

    def _on_toggle_live_view(self):
        if not self.preview_active:
            self._start_live_preview()
        else:
            self._stop_live_preview()

    def _start_live_preview(self):
        if not self.data.is_online:
            return
        self.preview_active = True
        self.btn_live_view.configure(text="📱 Hide View", fg_color="#f59e0b", hover_color="#d97706")
        
        # Split layout horizontally: Screen on LEFT, Log Box on RIGHT!
        self.log_box.pack_forget()
        self.preview_frame.pack(side="left", padx=(0, 6), fill="y")
        self.log_box.pack(side="left", fill="both", expand=True)
        self.preview_lbl.configure(image=None, text="📱 Loading...")

        self.append_log(datetime.now().strftime("%H:%M:%S"), "📱 Live Screen Stream started (Left-docked).")

        def _stream():
            if ":" in self.data.adb_serial:
                connect_device_adb(self.data.adb_serial)
            while self.preview_active and self.data.is_online:
                try:
                    img = capture_device_screen(self.data.adb_serial, target_size=(124, 190))
                    if img and self.preview_active:
                        ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
                        dispatch_to_main(self._update_preview_label, ctk_img)
                except Exception:
                    pass
                time.sleep(1.2)  # Lightweight 1.2s interval to ensure ZERO lag

        self.preview_thread = threading.Thread(target=_stream, daemon=True)
        self.preview_thread.start()

    def _stop_live_preview(self):
        self.preview_active = False
        self.btn_live_view.configure(text="📱 Live View", fg_color="#0284c7", hover_color="#0369a1")
        self.preview_frame.pack_forget()
        self.preview_lbl.configure(image=None, text="📱 Loading...")
        self.append_log(datetime.now().strftime("%H:%M:%S"), "📱 Live Screen Stream closed.")

    def _update_preview_label(self, ctk_img):
        if self.preview_active and self.preview_lbl:
            self.preview_lbl.configure(image=ctk_img, text="")

    def _on_toggle_bot(self):
        if not self.is_bot_running:
            self.start_bot()
        else:
            self.stop_bot()

    def start_bot(self):
        if not self.data.is_online:
            self.append_log(datetime.now().strftime("%H:%M:%S"), "❌ Cannot run bot: Emulator is OFFLINE! Click 'Turn Online' first.")
            return

        if not self.selected_account:
            self.append_log(datetime.now().strftime("%H:%M:%S"), "❌ No Telegram account assigned to this instance!")
            return

        # Strict Individual Account Isolation: Prevent duplicate sessions on same account
        acc_phone = re.sub(r'[^0-9]', '', str(self.selected_account.get("phone", "")))
        is_busy, busy_by = autometainstabot.TelegramAccountPool.is_account_busy(acc_phone, self.instance_key)
        if is_busy:
            self.append_log(datetime.now().strftime("%H:%M:%S"), f"❌ CONFLICT: Account {self.selected_account.get('phone')} is already running on {busy_by}! Each emulator must use an individual account.")
            self.set_status("Account Conflict", "error")
            return

        if self.dashboard:
            for other_key, other_card in self.dashboard.cards.items():
                if other_key != self.instance_key and other_card.is_bot_running:
                    other_phone = re.sub(r'[^0-9]', '', str(other_card.selected_account.get("phone", "")))
                    if other_phone and other_phone == acc_phone:
                        self.append_log(datetime.now().strftime("%H:%M:%S"), f"❌ CONFLICT: Account {self.selected_account.get('phone')} is already running on {other_card.data.name} ({other_key})!")
                        self.set_status("Account Conflict", "error")
                        return

        chosen_bot = self.selected_bot.strip().lstrip("@")
        acc_copy = dict(self.selected_account)
        acc_copy["target_bot"] = chosen_bot
        acc_copy["target_bots"] = [chosen_bot] + [b.strip().lstrip("@") for b in self.available_bots if b.strip().lstrip("@") != chosen_bot]

        mode_str = self.selected_mode.upper()
        self.append_log(datetime.now().strftime("%H:%M:%S"), f"🚀 Starting bot on {self.data.adb_serial} with Acc {self.selected_account.get('phone')} targeting @{chosen_bot} (Mode: {mode_str})...")
        mode_icon = "🍪" if self.selected_mode == "cookies" else ("🔐" if "2fa_cookies" in self.selected_mode else "🔑")
        self.set_status(f"Running ({mode_icon} @{chosen_bot})", "running")
        self.is_bot_running = True
        self.btn_run_bot.configure(text="⏹ Stop Bot", fg_color="#dc2626", hover_color="#b91c1c")

        self.dashboard.start_worker_for_instance(
            instance_key=self.instance_key,
            account_cfg=acc_copy,
            device_serial=self.data.adb_serial,
            target_bot=chosen_bot,
            on_state_change=self._on_worker_state_change,
            on_account_switched=self._on_worker_account_switched,
            available_bots=self.available_bots,
            task_mode=self.selected_mode,
            auto_shift=self.auto_shift_var.get(),
            shift_task_mode=self.selected_shift_mode
        )


    def _on_worker_account_switched(self, key: str, new_phone: str, new_bot: str):
        def _apply():
            if new_phone:
                self.acc_combo.set(str(new_phone))
                for a in self.accounts:
                    if a.get("phone") and str(a.get("phone")) in str(new_phone):
                        self.selected_account = a
                        break
            if new_bot:
                clean_b = str(new_bot).lstrip("@")
                self.selected_bot = clean_b
                self.bot_combo.set(clean_b)
                self.set_status(f"Running (@{clean_b})", "running")
            self.append_log(datetime.now().strftime("%H:%M:%S"), f"🔀 Switched to Acc: {new_phone} | Bot: @{new_bot}")
        dispatch_to_main(_apply)

    def stop_bot(self):
        self.append_log(datetime.now().strftime("%H:%M:%S"), "⏹ Stopping bot pipeline...")
        self.set_status("Stopping...", "waiting")
        self.dashboard.stop_worker_for_instance(self.instance_key)
        self.is_bot_running = False
        self.btn_run_bot.configure(text="▶ Run Bot", fg_color="#16a34a", hover_color="#15803d")

    def _on_worker_state_change(self, key: str, status: str, color_type: str):
        def _apply():
            self.set_status(status, color_type)
            if status == "Stopped":
                self.is_bot_running = False
                self.btn_run_bot.configure(text="▶ Run Bot", fg_color="#16a34a", hover_color="#15803d")
            self.sync_worker_counts()
        dispatch_to_main(_apply)

    def append_log(self, time_str: str, text: str):
        if threading.current_thread() != threading.main_thread():
            dispatch_to_main(self.append_log, time_str, text)
            return
        # 1. Insert into textbox with auto-trimming to max 50 lines (Prevents lag/memory load)
        line = f"[{time_str}] {text}\n"
        self.log_box.configure(state="normal")
        self.log_box.insert("end", line)

        try:
            line_count = int(self.log_box.index("end-1c").split(".")[0])
            if line_count > 50:
                # Trim oldest lines to keep at 45
                self.log_box.delete("1.0", f"{line_count - 45}.0")
        except Exception:
            pass

        self.log_box.see("end")
        self.log_box.configure(state="disabled")

        # 2. Extract EXACT Monotonic Counters (Fixes Double Counting!)
        m_b = re.search(r"(\$[\d\.]+|\d+\.\d{2,4})", text)
        if m_b and ("Balance:" in text or "TG-BALANCE" in text or "Your balance:" in text or "Bal:" in text):
            val = m_b.group(1)
            self.balance = val if val.startswith("$") else f"${val}"
            self.update_stats()
            self.dashboard.update_global_summary()

        # Track Meta account creation
        if any(k in text for k in ["META-SUCCESS", "Meta Account Created", "Running Instagram 2FA on emulator"]):
            if not getattr(self, '_meta_counted_in_cycle', False):
                self.meta_created_count += 1
                self._meta_counted_in_cycle = True
                self.update_stats()
                self.dashboard.update_global_summary()

        # Parse exact count from log (Submitted and Approved are tracked independently)
        m_sub = re.search(r"(?:Total\s+Submitted|\[SUBMITTED\].*?Total|Submitted|Sub):\s*(\d+)", text, re.IGNORECASE)
        if m_sub:
            val = int(m_sub.group(1))
            if val > self.submitted_count:
                self.submitted_count = val
                self.update_stats()
                self.dashboard.update_global_summary()

        m_app = re.search(r"(?:Total\s+Approved|\[APPROVED\].*?Total|Approved|App):\s*(\d+)", text, re.IGNORECASE)
        if m_app:
            val = int(m_app.group(1))
            if val > self.approved_count:
                self.approved_count = val
                self.update_stats()
                self.dashboard.update_global_summary()

        m_cyc = re.search(r"Cycle #?(\d+)", text, re.IGNORECASE)
        if m_cyc:
            val = int(m_cyc.group(1))
            if val > self.cycle_count:
                self.cycle_count = val
                self._meta_counted_in_cycle = False
                self.update_stats()
                self.dashboard.update_global_summary()
        elif "Starting Cycle" in text:
            self.cycle_count += 1
            self._meta_counted_in_cycle = False
            self.update_stats()
            self.dashboard.update_global_summary()

    def update_stats(self):
        if threading.current_thread() != threading.main_thread():
            dispatch_to_main(self.update_stats)
            return
        ratio = (self.submitted_count / self.meta_created_count * 100.0) if self.meta_created_count > 0 else 0.0
        ratio_str = f"{min(ratio, 100.0):.1f}%"
        new_text = f"💰 Bal: {self.balance}  |  🌐 Meta: {self.meta_created_count}  |  📥 Sub: {self.submitted_count}  |  💵 App: {self.approved_count}  |  📈 {ratio_str}"
        if self.stats_lbl.cget("text") != new_text:
            self.stats_lbl.configure(text=new_text)
        if self.dashboard and hasattr(self.dashboard, 'sync_balance_to_tab') and self.selected_account:
            self.dashboard.sync_balance_to_tab(self.selected_account.get("phone", ""), self.balance)

    def clear_logs(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    def set_status(self, status: str, color_type: str = "running"):
        if threading.current_thread() != threading.main_thread():
            dispatch_to_main(self.set_status, status, color_type)
            return
        colors = {
            "online": ("● Online", "#22c55e", "#142d1e"),
            "offline": ("● Offline", "#ef4444", "#2d1519"),
            "running": (f"● {status}", "#38bdf8", "#11263c"),
            "working": (f"● {status}", "#38bdf8", "#11263c"),
            "waiting": (f"● {status}", "#fbbf24", "#302611"),
            "stopped": ("● Stopped", "#94a3b8", "#1e293b"),
            "error": ("● Error", "#f87171", "#331818"),
        }
        text, fg, bg = colors.get(color_type, (f"● {status}", "#94a3b8", "#1e293b"))
        if self.status_pill.cget("text") != text:
            self.status_pill.configure(text=text, text_color=fg, fg_color=bg)


def parse_balance_text(text: str) -> Optional[float]:
    """Extracts balance float value from Telegram bot response text."""
    if not text:
        return None
    m = re.search(r"(?:balance|баланс)[^\d\n]*?((?:\d*\.\d+|\d+))", text, re.IGNORECASE)
    if m:
        try:
            return float(m.group(1))
        except Exception:
            pass
    m2 = re.search(r"\$\s*((?:\d*\.\d+|\d+))", text)
    if m2:
        try:
            return float(m2.group(1))
        except Exception:
            pass
    m3 = re.search(r"((?:\d*\.\d+|\d+))\s*(?:USDT|USD)", text, re.IGNORECASE)
    if m3:
        try:
            return float(m3.group(1))
        except Exception:
            pass
    return None


def check_single_account_balance_sync(account_info: dict, target_bot: str = "Taskl1_bot", status_cb=None, timeout: float = 10.0) -> Tuple[Optional[float], Optional[str]]:
    """
    Executes an isolated, single-purpose Telegram balance check:
    1. Connects to TelegramClient for the account session
    2. Sends '/start' to the bot
    3. Clicks '💰 Balance' / 'Balance' button (or sends '💰 Balance' text)
    4. Waits for the bot's reply and extracts balance amount
    5. Cleanly disconnects and returns (balance_float, None) or (None, error_msg)
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_async_check_balance_task(account_info, target_bot, status_cb, timeout, loop))
    finally:
        try:
            loop.close()
        except Exception:
            pass


async def _async_check_balance_task(account_info: dict, target_bot: str, status_cb, timeout: float, loop):
    from telethon import TelegramClient, errors

    phone = account_info.get("phone", "")
    clean_phone = re.sub(r'[^0-9]', '', str(phone))
    sess_name = account_info.get("session_name") or f"Taskl1_session_{clean_phone}"
    sess_path = os.path.join(BASE_DIR, sess_name) if not os.path.isabs(sess_name) else sess_name
    if not os.path.exists(sess_path + ".session") and not os.path.exists(sess_path):
        for alt in [f"Taskl1_session_{clean_phone}", f"taskly_session_{clean_phone}"]:
            alt_p = os.path.join(BASE_DIR, alt)
            if os.path.exists(alt_p + ".session"):
                sess_path = alt_p
                break

    api_id = account_info.get("api_id")
    api_hash = account_info.get("api_hash")
    clean_bot = target_bot.strip().lstrip("@") if target_bot else "Taskl1_bot"

    if not api_id or not api_hash:
        return None, "Missing API ID/Hash"

    if status_cb:
        status_cb("Connecting...", "waiting")

    ensure_session_wal_mode(sess_path)
    client = TelegramClient(sess_path, api_id, api_hash, loop=loop)
    try:
        await client.connect()
        if not await client.is_user_authorized():
            return None, "Not logged in"

        if status_cb:
            status_cb(f"Sending /start to @{clean_bot}...", "waiting")

        await client.send_message(clean_bot, "/start")
        await asyncio.sleep(1.2)

        if status_cb:
            status_cb("Checking Balance...", "waiting")

        clicked = False
        try:
            recent_msgs = await client.get_messages(clean_bot, limit=5)
            for msg in recent_msgs:
                if msg.buttons:
                    for row in msg.buttons:
                        for btn in row:
                            if re.search(r"Balance|💰|Баланс", btn.text or "", re.IGNORECASE):
                                await btn.click()
                                clicked = True
                                break
                        if clicked:
                            break
                if clicked:
                    break
        except Exception:
            pass

        if not clicked:
            await client.send_message(clean_bot, "💰 Balance")

        start_t = time.time()
        captured_bal = None
        while (time.time() - start_t) < timeout:
            await asyncio.sleep(0.4)
            recent = await client.get_messages(clean_bot, limit=4)
            for msg in recent:
                t = msg.text or ""
                b_val = parse_balance_text(t)
                if b_val is not None:
                    captured_bal = b_val
                    break
            if captured_bal is not None:
                break

        if captured_bal is not None:
            return captured_bal, None
        else:
            return None, "No reply from bot"

    except errors.FloodWaitError as fw:
        return None, f"FloodWait ({fw.seconds}s)"
    except Exception as e:
        err = str(e)
        if "database is locked" in err.lower() or "locked" in err.lower():
            return None, "Busy (Worker active)"
        return None, err[:30]
    finally:
        try:
            if client.is_connected():
                await client.disconnect()
        except Exception:
            pass
        try:
            if hasattr(client, 'session') and hasattr(client.session, '_conn') and client.session._conn:
                client.session._conn.close()
        except Exception:
            pass
        try:
            if hasattr(client, 'session') and hasattr(client.session, 'close'):
                client.session.close()
        except Exception:
            pass


class AccountBalanceRow(ctk.CTkFrame):
    """
    Dedicated row in Balance Checker tab representing one Telegram account.
    """
    def __init__(self, master, acc_index: int, account_info: dict, available_bots: List[str], on_check_balance, dashboard):
        super().__init__(master, fg_color="#181b22", corner_radius=10, border_width=1, border_color="#282e3d")
        self.acc_index = acc_index
        self.account_info = account_info
        self.available_bots = [b.lstrip("@") for b in (available_bots or ["Taskl1_bot", "PayGoeasy_bot", "RealEarningBangladesh_Bot"])]
        self.on_check_balance = on_check_balance
        self.dashboard = dashboard

        self.phone = str(account_info.get("phone", f"Acc #{acc_index+1}"))
        self.balance = 0.0
        self.balance_str = "$0.0000"
        self.last_checked_time = "Never"
        self.is_checking = False

        # Selected bot for this account
        raw_b = account_info.get("target_bot") or (self.available_bots[0] if self.available_bots else "Taskl1_bot")
        self.selected_bot = str(raw_b).lstrip("@")

        self._build_ui()

    def _build_ui(self):
        # Left: Index & Phone
        ctk.CTkLabel(
            self,
            text=f"#{self.acc_index+1}",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#94a3b8",
            width=32
        ).pack(side="left", padx=(10, 4), pady=8)

        self.phone_lbl = ctk.CTkLabel(
            self,
            text=f"📱 {self.phone}",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#f1f5f9",
            width=150,
            anchor="w"
        )
        self.phone_lbl.pack(side="left", padx=6, pady=8)

        # Bot selector
        ctk.CTkLabel(
            self,
            text="🤖",
            font=ctk.CTkFont(size=12)
        ).pack(side="left", padx=(6, 2))

        self.bot_combo = ctk.CTkOptionMenu(
            self,
            values=self.available_bots,
            command=self._on_bot_changed,
            font=ctk.CTkFont(size=11, weight="bold"),
            width=125,
            height=26,
            fg_color="#1e293b",
            button_color="#334155",
            button_hover_color="#475569"
        )
        self.bot_combo.set(self.selected_bot)
        self.bot_combo.pack(side="left", padx=4, pady=8)

        # Balance Badge
        self.balance_badge = ctk.CTkLabel(
            self,
            text="💵 $0.0000",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#10b981",
            fg_color="#064e3b",
            corner_radius=6,
            padx=12,
            pady=4,
            width=110
        )
        self.balance_badge.pack(side="left", padx=10, pady=8)

        # Last checked timestamp
        self.last_checked_lbl = ctk.CTkLabel(
            self,
            text="🕒 Never",
            font=ctk.CTkFont(size=11),
            text_color="#64748b",
            width=90
        )
        self.last_checked_lbl.pack(side="left", padx=8, pady=8)

        # Status pill
        self.status_pill = ctk.CTkLabel(
            self,
            text="● Idle",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#94a3b8",
            fg_color="#1e293b",
            corner_radius=8,
            padx=10,
            pady=3,
            width=140
        )
        self.status_pill.pack(side="left", padx=8, pady=8)

        # Action Button: Check Balance
        self.btn_check = ctk.CTkButton(
            self,
            text="🔍 Check Balance",
            font=ctk.CTkFont(size=11, weight="bold"),
            width=120,
            height=28,
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            command=self._on_check_clicked
        )
        self.btn_check.pack(side="right", padx=(6, 12), pady=8)

    def _on_bot_changed(self, choice: str):
        self.selected_bot = choice.strip().lstrip("@")

    def _on_check_clicked(self):
        if self.on_check_balance:
            self.on_check_balance(self.acc_index)

    def set_checking_state(self, is_checking: bool):
        self.is_checking = is_checking
        if is_checking:
            self.btn_check.configure(state="disabled", text="⏳ Checking...", fg_color="#334155")
        else:
            self.btn_check.configure(state="normal", text="🔍 Check Balance", fg_color="#2563eb")

    def set_balance(self, bal: float, time_str: str):
        self.balance = bal
        self.balance_str = f"${bal:.4f}"
        self.balance_badge.configure(text=f"💵 {self.balance_str}")
        self.last_checked_time = time_str
        self.last_checked_lbl.configure(text=f"🕒 {time_str}")

    def set_status(self, status: str, color_type: str = "idle"):
        colors = {
            "idle": (f"● {status}", "#94a3b8", "#1e293b"),
            "waiting": (f"● {status}", "#fbbf24", "#302611"),
            "success": ("● Success", "#22c55e", "#142d1e"),
            "busy": (f"● {status}", "#f59e0b", "#33220a"),
            "error": (f"● {status}", "#ef4444", "#2d1519"),
        }
        text, fg, bg = colors.get(color_type, (f"● {status}", "#94a3b8", "#1e293b"))
        self.status_pill.configure(text=text, text_color=fg, fg_color=bg)


class AutoMetaInstaGUI(ctk.CTk):
    """
    Main Application Window.
    Super-responsive, lagless dashboard with Dual-Tab Interface:
    1. 🚀 Emulators & Controller
    2. 💰 Balance Checker
    """
    def __init__(self):
        super().__init__()

        self.title("🚀 AutoMetaInstaBot — Multi-Emulator Master & Controller")
        self.geometry("1260, 880")
        self.minsize(980, 700)
        self.configure(fg_color="#0e1117")

        # Load accounts & target bots from config.json
        self.cfg = autometainstabot.load_config()
        self.accounts = self.cfg.get("telegram", {}).get("accounts", [])
        
        raw_bots = self.cfg.get("telegram", {}).get("target_bot") or ["Taskl1_bot", "PayGoeasy_bot"]
        if isinstance(raw_bots, str):
            self.available_bots = [b.strip().lstrip("@") for b in raw_bots.split(",") if b.strip()]
        elif isinstance(raw_bots, list):
            self.available_bots = [str(b).strip().lstrip("@") for b in raw_bots if str(b).strip()]
        else:
            self.available_bots = ["Taskl1_bot", "PayGoeasy_bot"]

        # Ensure known bots are present as options
        for b in ["Taskl1_bot", "PayGoeasy_bot", "RealEarningBangladesh_Bot"]:
            if b not in self.available_bots:
                self.available_bots.append(b)

        # Initialize global Telegram Account Pool
        autometainstabot.TelegramAccountPool.initialize(self.accounts)

        # Dedicated 1-to-1 Emulator Instance -> Account Mapping
        self.instance_account_map: Dict[str, str] = load_instance_accounts()
        autometainstabot.TelegramAccountPool.set_assigned_accounts(self.instance_account_map)

        # Active state
        self.instances: List[EmulatorInstance] = []
        self.cards: Dict[str, EmulatorCard] = {}
        self.balance_rows: Dict[int, AccountBalanceRow] = {}
        self.worker_threads: Dict[str, BotRunnerThread] = {}
        self.current_filter: str = "all"
        self._is_refreshing: bool = False
        self._is_checking_all: bool = False
        self._cancel_check_all: bool = False
        clean_bots = [b.strip().lstrip("@") for b in self.available_bots]
        self.selected_global_bot: str = clean_bots[0] if clean_bots else "Taskl1_bot"

        self.only_meta_submitted_count: int = 0
        self.only_meta_cycle_count: int = 0
        self.is_only_meta_running: bool = False

        self._build_header()
        
        # Triple-Tab Interface: Emulators Dashboard vs Only Meta vs Dedicated Balance Checker
        self.tabview = ctk.CTkTabview(
            self,
            fg_color="transparent",
            segmented_button_fg_color="#161b24",
            segmented_button_selected_color="#2563eb",
            segmented_button_selected_hover_color="#1d4ed8",
            segmented_button_unselected_color="#1e2430",
            segmented_button_unselected_hover_color="#334155"
        )
        self.tabview.pack(fill="both", expand=True, padx=16, pady=(0, 10))

        self.tab_dashboard = self.tabview.add("🚀 Emulators & Controller")
        self.tab_only_meta = self.tabview.add("⚡ Only Meta (No Emulator)")
        self.tab_balance = self.tabview.add("💰 Balance Checker")

        self._build_filter_bar(self.tab_dashboard)
        self._build_instances_container(self.tab_dashboard)
        self._build_only_meta_tab(self.tab_only_meta)
        self._build_balance_tab(self.tab_balance)

        self._start_dispatch_consumer()
        self._start_log_consumer()

        # Non-blocking initial emulator scan
        self.refresh_instances_now()

        # Periodic non-blocking background heartbeat to refresh statuses
        self._schedule_heartbeat()
        self._schedule_counts_sync()

    def _build_header(self):
        header_frame = ctk.CTkFrame(self, fg_color="#161b24", corner_radius=12, border_width=1, border_color="#232b3b")
        header_frame.pack(fill="x", padx=16, pady=(14, 8))

        # Title & Summary Text
        title_box = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_box.pack(side="left", padx=16, pady=12)

        title_lbl = ctk.CTkLabel(
            title_box,
            text="🚀 AutoMetaInstaBot Controller",
            font=ctk.CTkFont(size=19, weight="bold"),
            text_color="#f8fafc"
        )
        title_lbl.pack(anchor="w")

        self.summary_lbl = ctk.CTkLabel(
            title_box,
            text="Scanning emulator instances (LDPlayer & MuMu Player)...",
            font=ctk.CTkFont(size=12),
            text_color="#94a3b8"
        )
        self.summary_lbl.pack(anchor="w", pady=(2, 0))

        self.global_stats_lbl = ctk.CTkLabel(
            title_box,
            text="🏆 Submitted: 0  |  💰 Approved: 0  |  💵 Balance: $0.00",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#38bdf8"
        )
        self.global_stats_lbl.pack(anchor="w", pady=(2, 0))

        # Action Buttons
        btn_box = ctk.CTkFrame(header_frame, fg_color="transparent")
        btn_box.pack(side="right", padx=8, pady=8)

        self.btn_start_all = ctk.CTkButton(
            btn_box,
            text="▶ Start All",
            font=ctk.CTkFont(size=11, weight="bold"),
            width=88,
            height=30,
            fg_color="#16a34a",
            hover_color="#15803d",
            command=self.start_all_online_bots
        )
        self.btn_start_all.pack(side="left", padx=2)

        self.btn_stop_all = ctk.CTkButton(
            btn_box,
            text="⏹ Stop All",
            font=ctk.CTkFont(size=11, weight="bold"),
            width=76,
            height=30,
            fg_color="#dc2626",
            hover_color="#b91c1c",
            command=self.stop_all_bots
        )
        self.btn_stop_all.pack(side="left", padx=2)

        self.btn_launch_all = ctk.CTkButton(
            btn_box,
            text="🚀 Launch",
            font=ctk.CTkFont(size=11, weight="bold"),
            width=80,
            height=30,
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            command=self.launch_all_offline
        )
        self.btn_launch_all.pack(side="left", padx=2)

        self.btn_tile_all = ctk.CTkButton(
            btn_box,
            text="📐 Tile",
            font=ctk.CTkFont(size=11, weight="bold"),
            width=64,
            height=30,
            fg_color="#0891b2",
            hover_color="#0e7490",
            command=self.organize_windows_now
        )
        self.btn_tile_all.pack(side="left", padx=2)

        self.btn_rand_all = ctk.CTkButton(
            btn_box,
            text="🎲 Rand All",
            font=ctk.CTkFont(size=11, weight="bold"),
            width=84,
            height=30,
            fg_color="#7c3aed",
            hover_color="#6d28d9",
            command=self.randomize_all_identities
        )
        self.btn_rand_all.pack(side="left", padx=2)

        # Auto 5 Subscribe Toggle Button
        auto_sub_init = bool(self.cfg.get("auto_follow_suggested", True))
        self.auto_subscribe_enabled = auto_sub_init
        autometainstabot.set_auto_follow_suggested(auto_sub_init)

        self.btn_auto_subscribe = ctk.CTkButton(
            btn_box,
            text="👥 5 Sub: ON" if self.auto_subscribe_enabled else "👥 5 Sub: OFF",
            font=ctk.CTkFont(size=11, weight="bold"),
            width=88,
            height=30,
            fg_color="#16a34a" if self.auto_subscribe_enabled else "#475569",
            hover_color="#15803d" if self.auto_subscribe_enabled else "#64748b",
            command=self.toggle_auto_subscribe
        )
        self.btn_auto_subscribe.pack(side="left", padx=2)

        headless_init = bool(self.cfg.get("headless", False))
        self.headless_enabled = headless_init
        autometainstabot.set_headless(headless_init)

        self.btn_headless = ctk.CTkButton(
            btn_box,
            text="🖥️ Headless: ON" if self.headless_enabled else "🖥️ Headless: OFF",
            font=ctk.CTkFont(size=11, weight="bold"),
            width=96,
            height=30,
            fg_color="#16a34a" if self.headless_enabled else "#475569",
            hover_color="#15803d" if self.headless_enabled else "#64748b",
            command=self.toggle_headless
        )
        self.btn_headless.pack(side="left", padx=2)

        # Captcha Solve vs No Captcha (Skip) Toggle Button
        captcha_init = bool(self.cfg.get("skip_captcha", False))
        self.skip_captcha_enabled = captcha_init
        autometainstabot.set_skip_captcha(captcha_init)

        self.btn_captcha_mode = ctk.CTkButton(
            btn_box,
            text="⚡ No Captcha" if self.skip_captcha_enabled else "🧩 Captcha: ON",
            font=ctk.CTkFont(size=11, weight="bold"),
            width=98,
            height=30,
            fg_color="#f59e0b" if self.skip_captcha_enabled else "#16a34a",
            hover_color="#d97706" if self.skip_captcha_enabled else "#15803d",
            command=self.toggle_captcha_mode
        )
        self.btn_captcha_mode.pack(side="left", padx=2)

        self.btn_refresh = ctk.CTkButton(
            btn_box,
            text="🔄 Refresh",
            font=ctk.CTkFont(size=11),
            width=70,
            height=30,
            fg_color="#334155",
            hover_color="#475569",
            command=self.refresh_instances_now
        )
        self.btn_refresh.pack(side="left", padx=(2, 0))

    def _build_filter_bar(self, parent):
        filter_frame = ctk.CTkFrame(parent, fg_color="transparent")
        filter_frame.pack(fill="x", padx=4, pady=(2, 3))

        # Tabs for filtering
        self.filter_buttons = {}
        tab_names = [
            ("all", "All Instances"),
            ("online", "🟢 Online Only"),
            ("offline", "🔴 Offline Only"),
            ("running", "⚡ Running Bots"),
            ("mumu", "MuMu Player"),
            ("ld", "LDPlayer"),
        ]

        for code, label in tab_names:
            btn = ctk.CTkButton(
                filter_frame,
                text=label,
                font=ctk.CTkFont(size=11, weight="bold" if code == "all" else "normal"),
                height=26,
                fg_color="#2563eb" if code == "all" else "#1e2430",
                hover_color="#3b82f6",
                command=lambda c=code: self.set_filter(c)
            )
            btn.pack(side="left", padx=3)
            self.filter_buttons[code] = btn

        # Global Controls Frame (Dedicated row for full visibility on any screen width)
        global_ctrl_frame = ctk.CTkFrame(
            parent,
            fg_color="#161b24",
            corner_radius=8,
            border_width=1,
            border_color="#232b3b"
        )
        global_ctrl_frame.pack(fill="x", padx=4, pady=(2, 6))

        # Global Bot Selector
        ctk.CTkLabel(
            global_ctrl_frame,
            text="🤖 Global Bot:",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#a78bfa"
        ).pack(side="left", padx=(8, 4), pady=2)

        clean_bots = [b.strip().lstrip("@") for b in self.available_bots]
        default_global_bot = self.selected_global_bot or (clean_bots[0] if clean_bots else "Taskl1_bot")

        self.global_bot_combo = ctk.CTkOptionMenu(
            global_ctrl_frame,
            values=clean_bots,
            command=self._on_global_bot_changed,
            font=ctk.CTkFont(size=11, weight="bold"),
            width=135,
            height=26,
            fg_color="#1e293b",
            button_color="#334155",
            button_hover_color="#475569"
        )
        self.global_bot_combo.set(default_global_bot)
        self.global_bot_combo.pack(side="left", padx=(0, 10), pady=2)

        # Global Mode Selector
        ctk.CTkLabel(
            global_ctrl_frame,
            text="🌐 Global Mode:",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#38bdf8"
        ).pack(side="left", padx=(4, 4), pady=2)

        cfg_mode = self.cfg.get("task_mode", "2fa").lower()
        if "meta" in cfg_mode:
            default_global_mode = "⚡ Only Meta"
        elif "random" in cfg_mode:
            default_global_mode = "🎲 Random 2FA + Cookies"
        elif "2fa" in cfg_mode and "cookie" in cfg_mode:
            default_global_mode = "🔐 2FA + Cookies"
        elif "cookies" in cfg_mode:
            default_global_mode = "🍪 Cookies"
        else:
            default_global_mode = "🔑 2FA"

        self.global_mode_combo = ctk.CTkOptionMenu(
            global_ctrl_frame,
            values=["🔑 2FA", "🍪 Cookies", "🔐 2FA + Cookies", "🎲 Random 2FA + Cookies", "⚡ Only Meta"],
            command=self._on_global_mode_changed,
            font=ctk.CTkFont(size=11, weight="bold"),
            width=165,
            height=26,
            fg_color="#1e293b",
            button_color="#334155",
            button_hover_color="#475569"
        )
        self.global_mode_combo.set(default_global_mode)
        self.global_mode_combo.pack(side="left", padx=(0, 6), pady=2)

        # Global Auto-Shift checkbox
        self.global_auto_shift_var = ctk.BooleanVar(value=False)
        self.global_auto_shift_chk = ctk.CTkCheckBox(
            global_ctrl_frame,
            text="🔄 Auto-Shift",
            variable=self.global_auto_shift_var,
            command=self._on_global_auto_shift_toggled,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#f59e0b",
            checkmark_color="#0f172a",
            fg_color="#f59e0b",
            hover_color="#d97706",
            width=96,
            height=22
        )
        self.global_auto_shift_chk.pack(side="left", padx=(6, 4), pady=2)

        # Global Shift Task Selector
        ctk.CTkLabel(
            global_ctrl_frame,
            text="➡️ Shift Task:",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#cbd5e1"
        ).pack(side="left", padx=(4, 2), pady=2)

        self.global_shift_task_combo = ctk.CTkOptionMenu(
            global_ctrl_frame,
            values=["🍪 Cookies", "🔑 2FA", "🔐 2FA + Cookies", "🎲 Random 2FA + Cookies", "⚡ Only Meta", "🔄 Same Mode"],
            command=self._on_global_shift_task_changed,
            font=ctk.CTkFont(size=11, weight="bold"),
            width=165,
            height=26,
            fg_color="#1e293b",
            button_color="#334155",
            button_hover_color="#475569"
        )
        self.global_shift_task_combo.set("🍪 Cookies")
        self.global_shift_task_combo.pack(side="left", padx=(0, 6), pady=2)

        # Global Auto 5 Subscribe Toggle Button
        self.global_auto_sub_btn = ctk.CTkButton(
            global_ctrl_frame,
            text="👥 5 Sub: ON" if self.auto_subscribe_enabled else "👥 5 Sub: OFF",
            font=ctk.CTkFont(size=11, weight="bold"),
            width=100,
            height=26,
            fg_color="#16a34a" if self.auto_subscribe_enabled else "#475569",
            hover_color="#15803d" if self.auto_subscribe_enabled else "#64748b",
            command=self.toggle_auto_subscribe
        )
        self.global_auto_sub_btn.pack(side="left", padx=(4, 4), pady=2)

        self.global_headless_btn = ctk.CTkButton(
            global_ctrl_frame,
            text="🖥️ Headless: ON" if self.headless_enabled else "🖥️ Headless: OFF",
            font=ctk.CTkFont(size=11, weight="bold"),
            width=110,
            height=26,
            fg_color="#16a34a" if self.headless_enabled else "#475569",
            hover_color="#15803d" if self.headless_enabled else "#64748b",
            command=self.toggle_headless
        )
        self.global_headless_btn.pack(side="left", padx=(2, 6), pady=2)

    def _on_global_bot_changed(self, choice: str):
        chosen_bot = choice.strip().lstrip("@")
        self.selected_global_bot = chosen_bot

        # Update in-memory app config and persist to config.json
        if "telegram" in self.cfg:
            current_bots = self.cfg["telegram"].get("target_bot")
            if isinstance(current_bots, list):
                if chosen_bot in current_bots:
                    current_bots.remove(chosen_bot)
                current_bots.insert(0, chosen_bot)
                self.cfg["telegram"]["target_bot"] = current_bots
            elif isinstance(current_bots, str):
                self.cfg["telegram"]["target_bot"] = chosen_bot

            try:
                autometainstabot.save_config(self.cfg)
            except Exception as e:
                print(f"Error persisting global target_bot to config.json: {e}")

        # Update all active emulator cards
        for card in self.cards.values():
            card.selected_bot = chosen_bot
            card.bot_combo.set(chosen_bot)
            card.append_log(
                datetime.now().strftime("%H:%M:%S"),
                f"🤖 Global bot applied: @{chosen_bot}"
            )

    def _on_global_mode_changed(self, choice: str):
        choice_lower = choice.lower()
        if "meta" in choice_lower:
            new_mode = "only_meta"
            display_str = "⚡ Only Meta"
        elif "random" in choice_lower:
            new_mode = "random_2fa_cookies"
            display_str = "🎲 Random 2FA + Cookies"
        elif "2fa" in choice_lower and "cookie" in choice_lower:
            new_mode = "2fa_cookies"
            display_str = "🔐 2FA + Cookies"
        elif "cookies" in choice_lower:
            new_mode = "cookies"
            display_str = "🍪 Cookies"
        else:
            new_mode = "2fa"
            display_str = "🔑 2FA"

        # Update in-memory app configuration
        self.cfg["task_mode"] = new_mode

        # Persist to config.json
        try:
            autometainstabot.save_config(self.cfg)
        except Exception as e:
            print(f"Error persisting global task_mode to config.json: {e}")

        # Update all active emulator cards
        for card in self.cards.values():
            card.cfg["task_mode"] = new_mode
            card.selected_mode = new_mode
            card.mode_combo.set(display_str)
            card.append_log(
                datetime.now().strftime("%H:%M:%S"),
                f"🌐 Global mode applied: {display_str}"
            )

    def _on_global_auto_shift_toggled(self):
        val = self.global_auto_shift_var.get()
        state_str = "ENABLED" if val else "DISABLED"
        for card in self.cards.values():
            card.auto_shift_var.set(val)
            card._on_auto_shift_toggled()
        self.summary_lbl.configure(text=f"Global Auto-Shift {state_str} for all instances")

    def _on_global_shift_task_changed(self, choice: str):
        for card in self.cards.values():
            card.shift_task_combo.set(choice)
            card._on_shift_mode_selected(choice)
        self.summary_lbl.configure(text=f"Global Shift Task set to: {choice}")

    def toggle_auto_subscribe(self):
        self.auto_subscribe_enabled = not self.auto_subscribe_enabled
        new_val = self.auto_subscribe_enabled
        autometainstabot.set_auto_follow_suggested(new_val)
        self.cfg["auto_follow_suggested"] = new_val
        try:
            autometainstabot.save_config(self.cfg)
        except Exception as e:
            print(f"Error persisting auto_follow_suggested to config.json: {e}")

        text_str = "👥 5 Sub: ON" if new_val else "👥 5 Sub: OFF"
        fg_col = "#16a34a" if new_val else "#475569"
        hov_col = "#15803d" if new_val else "#64748b"

        if hasattr(self, 'btn_auto_subscribe') and self.btn_auto_subscribe:
            self.btn_auto_subscribe.configure(
                text=text_str,
                fg_color=fg_col,
                hover_color=hov_col
            )

        if hasattr(self, 'global_auto_sub_btn') and self.global_auto_sub_btn:
            self.global_auto_sub_btn.configure(
                text=text_str,
                fg_color=fg_col,
                hover_color=hov_col
            )

        status_msg = "ENABLED (will auto-follow 5 accounts on registration)" if new_val else "DISABLED (skipping suggested accounts)"
        custom_gui_log_callback("CONFIG", f"Auto 5 Subscribe set to {status_msg}", "MAIN")
        for card in self.cards.values():
            card.append_log(
                datetime.now().strftime("%H:%M:%S"),
                f"👥 Auto 5 Subscribe {status_msg}"
            )
        self.summary_lbl.configure(text=f"Auto 5 Subscribe {'ENABLED' if new_val else 'DISABLED'}")

    def toggle_headless(self):
        self.headless_enabled = not self.headless_enabled
        new_val = self.headless_enabled
        autometainstabot.set_headless(new_val)
        self.cfg["headless"] = new_val
        try:
            autometainstabot.save_config(self.cfg)
        except Exception as e:
            print(f"Error persisting headless to config.json: {e}")

        text_str = "🖥️ Headless: ON" if new_val else "🖥️ Headless: OFF"
        fg_col = "#16a34a" if new_val else "#475569"
        hov_col = "#15803d" if new_val else "#64748b"

        if hasattr(self, 'btn_headless') and self.btn_headless:
            self.btn_headless.configure(
                text=text_str,
                fg_color=fg_col,
                hover_color=hov_col
            )

        if hasattr(self, 'global_headless_btn') and self.global_headless_btn:
            self.global_headless_btn.configure(
                text=text_str,
                fg_color=fg_col,
                hover_color=hov_col
            )

    def toggle_captcha_mode(self):
        self.skip_captcha_enabled = not self.skip_captcha_enabled
        new_val = self.skip_captcha_enabled
        autometainstabot.set_skip_captcha(new_val)
        self.cfg["skip_captcha"] = new_val
        try:
            autometainstabot.save_config(self.cfg)
        except Exception as e:
            print(f"Error persisting skip_captcha to config.json: {e}")

        text_str = "⚡ No Captcha" if new_val else "🧩 Captcha: ON"
        fg_col = "#f59e0b" if new_val else "#16a34a"
        hov_col = "#d97706" if new_val else "#15803d"

        if hasattr(self, 'btn_captcha_mode') and self.btn_captcha_mode:
            self.btn_captcha_mode.configure(
                text=text_str,
                fg_color=fg_col,
                hover_color=hov_col
            )

        status_msg = "ENABLED (Only clean no-captcha accounts; skip & rotate IP if checkpoint detected)" if new_val else "DISABLED (2Captcha will solve checkpoints)"
        custom_gui_log_callback("CONFIG", f"No Captcha Mode {status_msg}", "MAIN")
        self.summary_lbl.configure(text=f"No Captcha Mode {'ON' if new_val else 'OFF'}")

        status_msg = "ENABLED (browser runs in background)" if new_val else "DISABLED (browser window will show)"
        custom_gui_log_callback("CONFIG", f"Headless mode set to {status_msg}", "MAIN")
        for card in self.cards.values():
            card.append_log(
                datetime.now().strftime("%H:%M:%S"),
                f"🖥️ Headless mode {status_msg}"
            )
        self.summary_lbl.configure(text=f"Headless mode {'ENABLED' if new_val else 'DISABLED'}")

    def _build_instances_container(self, parent):
        self.scroll_frame = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        self.scroll_frame.pack(fill="both", expand=True, padx=4, pady=(0, 8))

        # 2-column grid
        self.scroll_frame.grid_columnconfigure(0, weight=1)
        self.scroll_frame.grid_columnconfigure(1, weight=1)

    # =========================================================================
    # ⚡ DEDICATED ONLY META TAB (100% PURE API - ZERO EMULATOR REQUIRED)
    # =========================================================================
    def _build_only_meta_tab(self, parent):
        """Constructs dedicated Only Meta tab layout for pure API account creation and submission."""
        header = ctk.CTkFrame(parent, fg_color="#161b24", corner_radius=12, border_width=1, border_color="#232b3b")
        header.pack(fill="x", padx=4, pady=(4, 8))

        # Title Row
        title_row = ctk.CTkFrame(header, fg_color="transparent")
        title_row.pack(fill="x", padx=14, pady=(12, 6))

        t_lbl = ctk.CTkLabel(
            title_row,
            text="⚡ Pure-API Only Meta Mode",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#38bdf8"
        )
        t_lbl.pack(side="left")

        sub_lbl = ctk.CTkLabel(
            title_row,
            text="• 100% Direct API (Zero Emulator Required • Zero ADB • Fast turnaround)",
            font=ctk.CTkFont(size=11),
            text_color="#94a3b8"
        )
        sub_lbl.pack(side="left", padx=(8, 0))

        self.only_meta_status_pill = ctk.CTkLabel(
            title_row,
            text="● Idle",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#334155",
            text_color="#94a3b8",
            corner_radius=12,
            padx=12,
            pady=3
        )
        self.only_meta_status_pill.pack(side="right")

        # Controls Row
        ctrl_row = ctk.CTkFrame(header, fg_color="transparent")
        ctrl_row.pack(fill="x", padx=14, pady=(4, 10))

        # Account Selector
        ctk.CTkLabel(
            ctrl_row,
            text="📱 Account:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#a78bfa"
        ).pack(side="left", padx=(0, 4))

        acc_choices = [f"{a.get('phone', f'Account {i+1}')}" for i, a in enumerate(self.accounts)]
        if not acc_choices:
            acc_choices = ["No Accounts Found"]
        self.only_meta_acc_combo = ctk.CTkOptionMenu(
            ctrl_row,
            values=acc_choices,
            font=ctk.CTkFont(size=11, weight="bold"),
            width=165,
            height=30,
            fg_color="#1e293b",
            button_color="#334155",
            button_hover_color="#475569"
        )
        self.only_meta_acc_combo.set(acc_choices[0])
        self.only_meta_acc_combo.pack(side="left", padx=(0, 10))

        # Target Bot Selector
        ctk.CTkLabel(
            ctrl_row,
            text="🤖 Bot:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#38bdf8"
        ).pack(side="left", padx=(0, 4))

        meta_bot_choices = ["RealEarningBangladesh_Bot", "Taskl1_bot", "PayGoeasy_bot"]
        for b in self.available_bots:
            clean_b = b.lstrip("@")
            if clean_b not in meta_bot_choices:
                meta_bot_choices.append(clean_b)

        self.only_meta_bot_combo = ctk.CTkOptionMenu(
            ctrl_row,
            values=meta_bot_choices,
            font=ctk.CTkFont(size=11, weight="bold"),
            width=210,
            height=30,
            fg_color="#1e293b",
            button_color="#334155",
            button_hover_color="#475569"
        )
        self.only_meta_bot_combo.set("RealEarningBangladesh_Bot")
        self.only_meta_bot_combo.pack(side="left", padx=(0, 10))

        # Password Entry & Save Button
        ctk.CTkLabel(
            ctrl_row,
            text="🔑 Password:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#fbbf24"
        ).pack(side="left", padx=(0, 4))

        cur_pwd = autometainstabot.get_only_meta_password()
        self.only_meta_pwd_entry = ctk.CTkEntry(
            ctrl_row,
            font=ctk.CTkFont(size=11),
            width=110,
            height=30,
            fg_color="#0e1117",
            border_color="#334155"
        )
        self.only_meta_pwd_entry.insert(0, cur_pwd)
        self.only_meta_pwd_entry.pack(side="left", padx=(0, 4))

        self.btn_save_only_meta_pwd = ctk.CTkButton(
            ctrl_row,
            text="💾 Save",
            width=58,
            height=30,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#d97706",
            hover_color="#b45309",
            command=self._save_only_meta_pwd
        )
        self.btn_save_only_meta_pwd.pack(side="left", padx=(0, 12))

        # Start / Stop Buttons
        self.btn_start_only_meta = ctk.CTkButton(
            ctrl_row,
            text="▶ Start Only Meta",
            width=135,
            height=30,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#16a34a",
            hover_color="#15803d",
            command=self._start_only_meta
        )
        self.btn_start_only_meta.pack(side="left", padx=4)

        self.btn_stop_only_meta = ctk.CTkButton(
            ctrl_row,
            text="⏹ Stop",
            width=80,
            height=30,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#dc2626",
            hover_color="#b91c1c",
            state="disabled",
            command=self._stop_only_meta
        )
        self.btn_stop_only_meta.pack(side="left", padx=4)

        self.btn_clear_only_meta_logs = ctk.CTkButton(
            ctrl_row,
            text="🗑 Clear Logs",
            width=85,
            height=30,
            font=ctk.CTkFont(size=11),
            fg_color="#334155",
            hover_color="#475569",
            command=self._clear_only_meta_logs
        )
        self.btn_clear_only_meta_logs.pack(side="right", padx=(4, 0))

        # Stats Card row
        stats_frame = ctk.CTkFrame(header, fg_color="#0e1117", corner_radius=8, border_width=1, border_color="#1e2533")
        stats_frame.pack(fill="x", padx=14, pady=(0, 10))

        self.only_meta_submitted_lbl = ctk.CTkLabel(
            stats_frame,
            text="📥 Submitted: 0",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#10b981",
            fg_color="#064e3b",
            corner_radius=6,
            padx=12,
            pady=4
        )
        self.only_meta_submitted_lbl.pack(side="left", padx=(8, 6), pady=4)

        self.only_meta_cycle_lbl = ctk.CTkLabel(
            stats_frame,
            text="🔄 Cycle: #0",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#38bdf8",
            fg_color="#0c4a6e",
            corner_radius=6,
            padx=10,
            pady=4
        )
        self.only_meta_cycle_lbl.pack(side="left", padx=6, pady=4)

        self.only_meta_pwd_badge = ctk.CTkLabel(
            stats_frame,
            text=f"🔑 Config Pwd: {cur_pwd}",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#fbbf24",
            fg_color="#302611",
            corner_radius=6,
            padx=10,
            pady=4
        )
        self.only_meta_pwd_badge.pack(side="left", padx=6, pady=4)

        info_lbl = ctk.CTkLabel(
            stats_frame,
            text="⚡ No LDPlayer or MuMu required • Pure Socket & GraphQL API",
            font=ctk.CTkFont(size=11),
            text_color="#64748b"
        )
        info_lbl.pack(side="right", padx=(6, 10))

        # Terminal Log Console Frame
        log_frame = ctk.CTkFrame(parent, fg_color="#111622", corner_radius=10, border_width=1, border_color="#1e2533")
        log_frame.pack(fill="both", expand=True, padx=4, pady=(0, 4))

        log_top = ctk.CTkFrame(log_frame, fg_color="transparent")
        log_top.pack(fill="x", padx=12, pady=(8, 4))

        ctk.CTkLabel(
            log_top,
            text="💻 Live Terminal Console (Only Meta):",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#94a3b8"
        ).pack(side="left")

        self.only_meta_log_box = ctk.CTkTextbox(
            log_frame,
            fg_color="#090d16",
            text_color="#e2e8f0",
            font=ctk.CTkFont(family="Consolas", size=11),
            corner_radius=8,
            wrap="word",
            border_width=1,
            border_color="#1e2533"
        )
        self.only_meta_log_box.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.only_meta_log_box.insert("end", "[INIT] Only Meta panel ready. No emulator required. Click '▶ Start Only Meta' to begin.\n")
        self.only_meta_log_box.configure(state="disabled")

    def _save_only_meta_pwd(self):
        new_pwd = re.sub(r"[`'\"*]", "", self.only_meta_pwd_entry.get().strip()).strip()
        if not new_pwd:
            new_pwd = "saikat50968"
        self.cfg["only_meta_password"] = new_pwd
        if "telegram" not in self.cfg:
            self.cfg["telegram"] = {}
        self.cfg["telegram"]["only_meta_password"] = new_pwd
        try:
            autometainstabot.save_config(self.cfg)
            self.only_meta_pwd_badge.configure(text=f"🔑 Config Pwd: {new_pwd}")
            self._append_only_meta_log(datetime.now().strftime("%H:%M:%S"), f"💾 Saved Only Meta password '{new_pwd}' to config.json!")
        except Exception as e:
            self._append_only_meta_log(datetime.now().strftime("%H:%M:%S"), f"❌ Error saving password: {e}")

    def _start_only_meta(self):
        if getattr(self, 'is_only_meta_running', False):
            return

        # 1. Selected Account
        chosen_acc_str = self.only_meta_acc_combo.get()
        chosen_acc = None
        for a in self.accounts:
            if a.get("phone") and str(a.get("phone")) in chosen_acc_str:
                chosen_acc = a
                break
        if not chosen_acc and self.accounts:
            chosen_acc = self.accounts[0]
        if not chosen_acc:
            self._append_only_meta_log(datetime.now().strftime("%H:%M:%S"), "❌ No Telegram accounts found in config.json!")
            return

        # 2. Target Bot
        chosen_bot = self.only_meta_bot_combo.get().strip().lstrip("@")
        if not chosen_bot:
            chosen_bot = "RealEarningBangladesh_Bot"

        # 3. Save password if user changed it in entry
        self._save_only_meta_pwd()

        self.is_only_meta_running = True
        self.btn_start_only_meta.configure(state="disabled")
        self.btn_stop_only_meta.configure(state="normal")
        self.only_meta_status_pill.configure(text=f"● Running (@{chosen_bot})", fg_color="#16a34a", text_color="#ffffff")

        self._append_only_meta_log(datetime.now().strftime("%H:%M:%S"), f"🚀 Starting pure-API Only Meta worker for {chosen_acc.get('phone')} targeting @{chosen_bot} (Zero emulator)...")

        self.start_worker_for_instance(
            instance_key="ONLY_META",
            account_cfg=chosen_acc,
            device_serial="pure_api_only_meta",
            target_bot=chosen_bot,
            on_state_change=self._on_only_meta_state_change,
            available_bots=[chosen_bot, "RealEarningBangladesh_Bot", "Taskl1_bot", "PayGoeasy_bot"],
            task_mode="only_meta"
        )

    def _stop_only_meta(self):
        self.stop_worker_for_instance("ONLY_META")
        self.is_only_meta_running = False
        self.btn_start_only_meta.configure(state="normal")
        self.btn_stop_only_meta.configure(state="disabled")
        self.only_meta_status_pill.configure(text="● Idle", fg_color="#334155", text_color="#94a3b8")
        self._append_only_meta_log(datetime.now().strftime("%H:%M:%S"), "⏹ Only Meta worker stopped.")

    def _on_only_meta_state_change(self, instance_key: str, state_text: str, state_type: str):
        def _apply():
            if state_type == "running":
                self.only_meta_status_pill.configure(text=f"● {state_text}", fg_color="#16a34a", text_color="#ffffff")
            elif state_type == "error":
                self.only_meta_status_pill.configure(text="● Error", fg_color="#dc2626", text_color="#ffffff")
                self.btn_start_only_meta.configure(state="normal")
                self.btn_stop_only_meta.configure(state="disabled")
                self.is_only_meta_running = False
            elif state_type == "stopped":
                self.only_meta_status_pill.configure(text="● Idle", fg_color="#334155", text_color="#94a3b8")
                self.btn_start_only_meta.configure(state="normal")
                self.btn_stop_only_meta.configure(state="disabled")
                self.is_only_meta_running = False
        dispatch_to_main(_apply)

    def _append_only_meta_log(self, time_str: str, text: str):
        if threading.current_thread() != threading.main_thread():
            dispatch_to_main(self._append_only_meta_log, time_str, text)
            return

        if not hasattr(self, 'only_meta_log_box'):
            return

        line = f"[{time_str}] {text}\n"
        self.only_meta_log_box.configure(state="normal")
        self.only_meta_log_box.insert("end", line)

        try:
            line_count = int(self.only_meta_log_box.index("end-1c").split(".")[0])
            if line_count > 200:
                self.only_meta_log_box.delete("1.0", f"{line_count - 180}.0")
        except Exception:
            pass

        self.only_meta_log_box.see("end")
        self.only_meta_log_box.configure(state="disabled")

        # Update stats counters
        if "Cycle #" in text or "CYCLE-START" in text:
            m_c = re.search(r"Cycle #?(\d+)", text)
            if m_c:
                c_num = m_c.group(1)
                self.only_meta_cycle_count = int(c_num)
                self.only_meta_cycle_lbl.configure(text=f"🔄 Cycle: #{c_num}")

        if "TG-SUBMITTED" in text or "Request ID:" in text:
            m_s = re.search(r"Total:\s*(\d+)", text)
            if m_s:
                cnt = int(m_s.group(1))
                self.only_meta_submitted_count = cnt
            else:
                self.only_meta_submitted_count += 1
            self.only_meta_submitted_lbl.configure(text=f"📥 Submitted: {self.only_meta_submitted_count}")

    def _clear_only_meta_logs(self):
        self.only_meta_log_box.configure(state="normal")
        self.only_meta_log_box.delete("1.0", "end")
        self.only_meta_log_box.configure(state="disabled")

    # =========================================================================
    # 💰 DEDICATED BALANCE CHECKER TAB METHODS
    # =========================================================================

    def _build_balance_tab(self, parent):
        """Constructs dedicated Balance Checker Tab layout"""
        bal_header = ctk.CTkFrame(parent, fg_color="#161b24", corner_radius=12, border_width=1, border_color="#232b3b")
        bal_header.pack(fill="x", padx=4, pady=(4, 8))

        ctrl_row = ctk.CTkFrame(bal_header, fg_color="transparent")
        ctrl_row.pack(fill="x", padx=12, pady=(10, 4))

        # Switch bot for all accounts
        ctk.CTkLabel(
            ctrl_row,
            text="🤖 Switch Bot:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#a78bfa"
        ).pack(side="left", padx=(0, 4))

        clean_bots = [b.lstrip("@") for b in self.available_bots]
        self.bal_global_bot_combo = ctk.CTkOptionMenu(
            ctrl_row,
            values=clean_bots,
            command=self._on_switch_all_balance_bots,
            font=ctk.CTkFont(size=11, weight="bold"),
            width=135,
            height=30,
            fg_color="#1e293b",
            button_color="#334155",
            button_hover_color="#475569"
        )
        self.bal_global_bot_combo.set(clean_bots[0] if clean_bots else "Taskl1_bot")
        self.bal_global_bot_combo.pack(side="left", padx=(0, 10))

        self.btn_check_all_bal = ctk.CTkButton(
            ctrl_row,
            text="💰 Check All Balances",
            width=160,
            height=30,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#16a34a",
            hover_color="#15803d",
            command=self.check_all_balances
        )
        self.btn_check_all_bal.pack(side="left", padx=4)

        self.btn_stop_bal_check = ctk.CTkButton(
            ctrl_row,
            text="⏹ Stop Checking",
            width=120,
            height=30,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#dc2626",
            hover_color="#b91c1c",
            state="disabled",
            command=self.stop_balance_check
        )
        self.btn_stop_bal_check.pack(side="left", padx=4)

        self.btn_refresh_bal_accounts = ctk.CTkButton(
            ctrl_row,
            text="🔄 Refresh List",
            width=110,
            height=30,
            font=ctk.CTkFont(size=12),
            fg_color="#334155",
            hover_color="#475569",
            command=self.refresh_balance_accounts
        )
        self.btn_refresh_bal_accounts.pack(side="left", padx=4)

        self.bal_progress_lbl = ctk.CTkLabel(
            ctrl_row,
            text=f"Ready • {len(self.accounts)} Accounts loaded",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#38bdf8"
        )
        self.bal_progress_lbl.pack(side="left", padx=12)

        tip_lbl = ctk.CTkLabel(
            ctrl_row,
            text="⚡ Sends /start ➔ 💰 Balance (Pure Telegram check, no emulators)",
            font=ctk.CTkFont(size=11),
            text_color="#64748b"
        )
        tip_lbl.pack(side="right", padx=(6, 2))

        # Stats Card row
        bal_stats_frame = ctk.CTkFrame(bal_header, fg_color="#0e1117", corner_radius=8, border_width=1, border_color="#1e2533")
        bal_stats_frame.pack(fill="x", padx=12, pady=(4, 10))

        self.bal_grand_total_badge = ctk.CTkLabel(
            bal_stats_frame,
            text="💵 Grand Total: $0.0000",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#10b981",
            fg_color="#064e3b",
            corner_radius=6,
            padx=14,
            pady=4
        )
        self.bal_grand_total_badge.pack(side="left", padx=(8, 6), pady=4)

        self.bal_total_acc_badge = ctk.CTkLabel(
            bal_stats_frame,
            text=f"👥 Accounts: {len(self.accounts)}",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#93c5fd",
            fg_color="#1e3a8a",
            corner_radius=6,
            padx=10,
            pady=4
        )
        self.bal_total_acc_badge.pack(side="left", padx=6, pady=4)

        self.bal_checked_count_badge = ctk.CTkLabel(
            bal_stats_frame,
            text=f"✅ Checked: 0 / {len(self.accounts)}",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#fbbf24",
            fg_color="#302611",
            corner_radius=6,
            padx=10,
            pady=4
        )
        self.bal_checked_count_badge.pack(side="left", padx=6, pady=4)

        # Scrollable list for account rows
        self.bal_scroll_container = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        self.bal_scroll_container.pack(fill="both", expand=True, padx=4, pady=(0, 4))

        self._populate_balance_rows()

    def _populate_balance_rows(self):
        """Populates account rows inside Balance tab scrollable list"""
        for child in self.bal_scroll_container.winfo_children():
            child.destroy()
        self.balance_rows.clear()

        for i, acc in enumerate(self.accounts):
            row = AccountBalanceRow(
                self.bal_scroll_container,
                acc_index=i,
                account_info=acc,
                available_bots=self.available_bots,
                on_check_balance=self.check_single_account_balance_async,
                dashboard=self
            )
            row.pack(fill="x", padx=4, pady=4)
            self.balance_rows[i] = row

        self.update_balance_tab_totals()

    def _on_switch_all_balance_bots(self, choice: str):
        """Switches target bot for all accounts in the Balance tab"""
        clean_bot = choice.strip().lstrip("@")
        for row in self.balance_rows.values():
            row.selected_bot = clean_bot
            row.bot_combo.set(clean_bot)

    def update_balance_tab_totals(self):
        """Updates Grand Total balance and checked count in the Balance Tab"""
        total_bal = sum(r.balance for r in self.balance_rows.values())
        checked_cnt = sum(1 for r in self.balance_rows.values() if r.last_checked_time != "Never")
        total_cnt = len(self.balance_rows)

        self.bal_grand_total_badge.configure(text=f"💵 Grand Total: ${total_bal:.4f}")
        self.bal_total_acc_badge.configure(text=f"👥 Accounts: {total_cnt}")
        self.bal_checked_count_badge.configure(text=f"✅ Checked: {checked_cnt} / {total_cnt}")

    def check_single_account_balance_async(self, acc_index: int):
        """Asynchronously checks balance for a single account without blocking GUI"""
        threading.Thread(target=self._run_single_account_check, args=(acc_index,), daemon=True).start()

    def _run_single_account_check(self, acc_index: int):
        row = self.balance_rows.get(acc_index)
        if not row:
            return

        phone_clean = re.sub(r'[^0-9]', '', str(row.phone))
        # Check if worker running with this phone
        is_worker_running = False
        for runner in self.worker_threads.values():
            if runner and runner.is_alive():
                r_phone = re.sub(r'[^0-9]', '', str(runner.account_cfg.get('phone', '')))
                if r_phone == phone_clean:
                    is_worker_running = True
                    break

        if is_worker_running:
            self.after(0, lambda: row.set_status("Busy (Worker running)", "busy"))
            return

        self.after(0, lambda: row.set_checking_state(True))

        def status_cb(txt, col_type):
            self.after(0, lambda: row.set_status(txt, col_type))

        target_b = row.selected_bot or "Taskl1_bot"
        bal, err = check_single_account_balance_sync(row.account_info, target_bot=target_b, status_cb=status_cb)
        t_now = datetime.now().strftime("%H:%M:%S")

        def _finish_ui():
            row.set_checking_state(False)
            if bal is not None:
                row.set_balance(bal, t_now)
                row.set_status("Success", "success")
                self.update_balance_tab_totals()
            else:
                err_msg = err or "Failed"
                color = "busy" if "busy" in err_msg.lower() else "error"
                row.set_status(err_msg, color)

        self.after(0, _finish_ui)

    def check_all_balances(self):
        """Initiates batch check across all accounts sequentially"""
        if self._is_checking_all:
            return
        self._is_checking_all = True
        self._cancel_check_all = False

        self.btn_check_all_bal.configure(state="disabled")
        self.btn_stop_bal_check.configure(state="normal")
        self.bal_progress_lbl.configure(text="Starting batch balance check...")

        threading.Thread(target=self._run_check_all_thread, daemon=True).start()

    def stop_balance_check(self):
        """Cancels an in-progress batch balance check"""
        if self._is_checking_all:
            self._cancel_check_all = True
            self.bal_progress_lbl.configure(text="Stopping after current account...")

    def _run_check_all_thread(self):
        total_cnt = len(self.balance_rows)
        for idx, (acc_idx, row) in enumerate(list(self.balance_rows.items())):
            if self._cancel_check_all:
                break

            phone_clean = re.sub(r'[^0-9]', '', str(row.phone))
            is_worker_running = False
            for runner in self.worker_threads.values():
                if runner and runner.is_alive():
                    r_phone = re.sub(r'[^0-9]', '', str(runner.account_cfg.get('phone', '')))
                    if r_phone == phone_clean:
                        is_worker_running = True
                        break

            if is_worker_running:
                dispatch_to_main(lambda r=row: r.set_status("Busy (Worker running)", "busy"))
                continue

            dispatch_to_main(lambda i=idx, p=row.phone: self.bal_progress_lbl.configure(
                text=f"Checking [{i+1}/{total_cnt}] {p}..."
            ))

            dispatch_to_main(lambda r=row: r.set_checking_state(True))

            def status_cb(txt, col_type, r=row):
                dispatch_to_main(lambda: r.set_status(txt, col_type))

            target_b = row.selected_bot or "Taskl1_bot"
            bal, err = check_single_account_balance_sync(row.account_info, target_bot=target_b, status_cb=status_cb)
            t_now = datetime.now().strftime("%H:%M:%S")

            def _update_row(r=row, b=bal, e=err):
                r.set_checking_state(False)
                if b is not None:
                    r.set_balance(b, t_now)
                    r.set_status("Success", "success")
                    self.update_balance_tab_totals()
                else:
                    err_msg = e or "Failed"
                    color = "busy" if "busy" in err_msg.lower() else "error"
                    r.set_status(err_msg, color)

            dispatch_to_main(_update_row)

            for _ in range(12):
                if self._cancel_check_all:
                    break
                time.sleep(0.1)

        def _cleanup():
            self._is_checking_all = False
            self.btn_check_all_bal.configure(state="normal")
            self.btn_stop_bal_check.configure(state="disabled")
            if self._cancel_check_all:
                self.bal_progress_lbl.configure(text="⏹ Stopped by user.")
            else:
                self.bal_progress_lbl.configure(text=f"✅ Completed checking all {total_cnt} accounts!")
            self.update_balance_tab_totals()

        dispatch_to_main(_cleanup)

    def refresh_balance_accounts(self):
        """Reloads accounts from config.json and updates Balance tab"""
        self.cfg = autometainstabot.load_config()
        self.accounts = self.cfg.get("telegram", {}).get("accounts", [])
        self._populate_balance_rows()
        self.bal_progress_lbl.configure(text=f"Refreshed • {len(self.accounts)} Accounts loaded")

    def sync_balance_to_tab(self, phone: str, balance_str: str):
        """Synchronizes balance update from active automation worker to Balance tab"""
        if threading.current_thread() != threading.main_thread():
            dispatch_to_main(self.sync_balance_to_tab, phone, balance_str)
            return
        if not phone:
            return
        phone_clean = re.sub(r'[^0-9]', '', str(phone))
        for row in self.balance_rows.values():
            row_phone_clean = re.sub(r'[^0-9]', '', str(row.phone))
            if row_phone_clean == phone_clean:
                try:
                    b_val = float(re.sub(r'[^\d\.]', '', balance_str))
                    t_now = datetime.now().strftime("%H:%M:%S")
                    row.set_balance(b_val, t_now)
                    row.set_status("Success", "success")
                    self.update_balance_tab_totals()
                except Exception:
                    pass
                break

    def set_filter(self, code: str):
        self.current_filter = code
        for c, btn in self.filter_buttons.items():
            if c == code:
                btn.configure(fg_color="#2563eb", font=ctk.CTkFont(size=11, weight="bold"))
            else:
                btn.configure(fg_color="#1e2430", font=ctk.CTkFont(size=11, weight="normal"))
        self._apply_filter()

    def _apply_filter(self, force: bool = False):
        new_layout = []
        row = 0
        col = 0
        for key, card in self.cards.items():
            inst = card.data
            show = True

            if self.current_filter == "online" and not inst.is_online:
                show = False
            elif self.current_filter == "offline" and inst.is_online:
                show = False
            elif self.current_filter == "running" and not card.is_bot_running:
                show = False
            elif self.current_filter == "mumu" and inst.emu_type != "mumu":
                show = False
            elif self.current_filter == "ld" and inst.emu_type != "ld":
                show = False

            if show:
                new_layout.append((key, row, col))
                col += 1
                if col > 1:
                    col = 0
                    row += 1

        # Prevent layout recalculation if nothing changed
        if not force and hasattr(self, '_current_grid_layout') and self._current_grid_layout == new_layout:
            return

        self._current_grid_layout = new_layout
        visible_keys = {item[0] for item in new_layout}

        for key, card in self.cards.items():
            if key not in visible_keys:
                card.grid_forget()

        for key, r, c in new_layout:
            self.cards[key].grid(row=r, column=c, padx=6, pady=6, sticky="nsew")

    def refresh_instances_now(self, is_manual: bool = True):
        if self._is_refreshing:
            return
        self._is_refreshing = True
        if is_manual:
            self.summary_lbl.configure(text="Scanning emulator instances & ADB devices...")

        def _scan():
            instances = scan_all_instances()
            dispatch_to_main(self._on_instances_scanned, instances, is_manual)

        threading.Thread(target=_scan, daemon=True).start()

    def _on_instances_scanned(self, instances: List[EmulatorInstance], is_manual: bool = False):
        self._is_refreshing = False
        self.instances = instances

        online_count = sum(1 for i in instances if i.is_online)
        offline_count = len(instances) - online_count

        new_summary = f"Total: {len(instances)} Instances | 🟢 Online: {online_count} | 🔴 Offline: {offline_count} | Bots: {', '.join(self.available_bots)}"
        if self.summary_lbl.cget("text") != new_summary:
            self.summary_lbl.configure(text=new_summary)

        new_cards_added = False
        for inst in instances:
            key = f"{inst.emu_type.upper()}-{inst.index}"
            if key in self.cards:
                self.cards[key].update_instance_state(inst)
            else:
                card = EmulatorCard(
                    self.scroll_frame,
                    instance_data=inst,
                    accounts=self.accounts,
                    available_bots=self.available_bots,
                    dashboard=self
                )
                self.cards[key] = card
                new_cards_added = True

        self._apply_filter(force=new_cards_added)
        self.update_global_summary()

    def _schedule_heartbeat(self):
        """Heartbeat to poll background updates smoothly and without screen shaking."""
        def _check():
            try:
                self.refresh_instances_now(is_manual=False)
            except Exception:
                pass
            finally:
                self.after(10000, _check)

        self.after(10000, _check)

    def _schedule_counts_sync(self):
        """Fast, lightweight counter synchronization (every 2.5s) without subprocess or layout lag."""
        def _sync():
            try:
                for card in list(self.cards.values()):
                    card.sync_worker_counts()
            except Exception:
                pass
            finally:
                self.after(2500, _sync)

        self.after(2500, _sync)

    def get_account_for_instance(self, instance_key: str, instance_index: int) -> dict:
        """Returns dedicated individual account for an emulator instance, avoiding duplicates."""
        saved_phone = self.instance_account_map.get(instance_key)
        if saved_phone:
            for acc in self.accounts:
                if str(acc.get("phone", "")).strip() == str(saved_phone).strip():
                    return acc

        # If not saved, assign an individual account that isn't already assigned to another instance
        assigned_phones = {str(p).strip() for k, p in self.instance_account_map.items() if k != instance_key}
        for acc in self.accounts:
            phone = str(acc.get("phone", "")).strip()
            if phone and phone not in assigned_phones:
                self.instance_account_map[instance_key] = phone
                save_instance_accounts(self.instance_account_map)
                autometainstabot.TelegramAccountPool.set_assigned_accounts(self.instance_account_map)
                return acc

        # Fallback if there are more emulators than accounts: assign by index modulo
        if self.accounts:
            acc = self.accounts[instance_index % len(self.accounts)]
            self.instance_account_map[instance_key] = acc.get("phone", "")
            save_instance_accounts(self.instance_account_map)
            autometainstabot.TelegramAccountPool.set_assigned_accounts(self.instance_account_map)
            return acc
        return {}

    def start_worker_for_instance(self, instance_key: str, account_cfg: dict, device_serial: str, target_bot: str, on_state_change, on_account_switched=None, available_bots=None, task_mode: str = "2fa", auto_shift: bool = False, shift_task_mode: str = ""):
        # Stop any existing runner for this key and wait for clean release of session files
        old_runner = self.worker_threads.get(instance_key)
        if old_runner and old_runner.is_alive():
            old_runner.stop()
            try:
                old_runner.join(timeout=3.5)
            except Exception:
                pass

        # Register account as actively occupied by this emulator instance
        phone = account_cfg.get("phone", "")
        if phone:
            autometainstabot.TelegramAccountPool.register_active(phone, instance_key)

        runner = BotRunnerThread(
            instance_key=instance_key,
            account_cfg=account_cfg,
            device_serial=device_serial,
            target_bot=target_bot,
            on_state_change=on_state_change,
            on_account_switched=on_account_switched,
            available_bots=available_bots or self.available_bots,
            task_mode=task_mode,
            auto_shift=auto_shift,
            shift_task_mode=shift_task_mode
        )
        self.worker_threads[instance_key] = runner
        runner.start()
        self.update_global_summary()

    def stop_worker_for_instance(self, instance_key: str):
        runner = self.worker_threads.get(instance_key)
        if runner:
            if runner.account_cfg and runner.account_cfg.get("phone"):
                autometainstabot.TelegramAccountPool.release_active(runner.account_cfg.get("phone", ""))
            if runner.is_alive():
                runner.stop()
        self.update_global_summary()

    def start_all_online_bots(self):
        for idx, (key, card) in enumerate(self.cards.items()):
            if card.data.is_online and not card.is_bot_running:
                delay = idx * 3000
                self.after(delay, card.start_bot)

    def stop_all_bots(self):
        for card in self.cards.values():
            if card.is_bot_running:
                card.stop_bot()

    def launch_all_offline(self):
        for card in self.cards.values():
            if not card.data.is_online:
                card._on_toggle_online()

    def randomize_all_identities(self):
        for card in self.cards.values():
            card._on_randomize_imei()

    def organize_windows_now(self):
        self.summary_lbl.configure(text="Organizing and auto-tiling all emulator windows...")
        def _tile():
            ok, msg = organize_all_windows()
            time.sleep(1.0)
            dispatch_to_main(self.refresh_instances_now)
        threading.Thread(target=_tile, daemon=True).start()

    def update_global_summary(self):
        if threading.current_thread() != threading.main_thread():
            dispatch_to_main(self.update_global_summary)
            return
        total_meta = sum(c.meta_created_count for c in list(self.cards.values()))
        total_sub = sum(c.submitted_count for c in list(self.cards.values()))
        total_app = sum(c.approved_count for c in list(self.cards.values()))
        active_bots = sum(1 for c in list(self.cards.values()) if c.is_bot_running)

        global_ratio = (total_sub / total_meta * 100.0) if total_meta > 0 else 0.0
        ratio_str = f"{min(global_ratio, 100.0):.1f}%"

        total_bal = 0.0
        for c in list(self.cards.values()):
            try:
                b_clean = re.sub(r'[^\d\.]', '', c.balance)
                if b_clean:
                    total_bal += float(b_clean)
            except Exception:
                pass

        bal_str = f"${total_bal:.2f}"
        new_stats = f"⚡ Active: {active_bots}  |  🌐 Meta: {total_meta}  |  📥 Submitted: {total_sub}  |  💰 Approved: {total_app}  |  📈 {ratio_str}  |  💵 Bal: {bal_str}"
        if self.global_stats_lbl.cget("text") != new_stats:
            self.global_stats_lbl.configure(text=new_stats)

    def _start_dispatch_consumer(self):
        """Processes functions dispatched from background threads strictly on the Tkinter main thread."""
        def _poll():
            try:
                while not GUI_DISPATCH_QUEUE.empty():
                    fn, args, kwargs = GUI_DISPATCH_QUEUE.get_nowait()
                    try:
                        fn(*args, **kwargs)
                    except Exception:
                        pass
            except Exception:
                pass
            finally:
                self.after(30, _poll)

        self.after(30, _poll)

    def _start_log_consumer(self):
        """Consumes queue messages and routes to appropriate cards."""
        def poll_queue():
            try:
                while not GUI_LOG_QUEUE.empty():
                    item = GUI_LOG_QUEUE.get_nowait()
                    inst_name = item.get("instance", "MAIN").upper()
                    time_str = item.get("time", "")
                    text = item.get("text", "")

                    matched = False
                    if "ONLY_META" in inst_name or (getattr(self, 'is_only_meta_running', False) and ("ONLY-META" in text or "TG-SUBMITTED" in text or "RealEarning" in text)):
                        self._append_only_meta_log(time_str, text)
                        matched = True

                    if not matched:
                        for key, card in list(self.cards.items()):
                            if key in inst_name or inst_name in key:
                                card.append_log(time_str, text)
                                matched = True
                                break

                    if not matched:
                        for card in list(self.cards.values()):
                            if card.is_bot_running:
                                card.append_log(time_str, text)
            except Exception:
                pass
            finally:
                self.after(150, poll_queue)

        self.after(150, poll_queue)


def main():
    # Global exception handler to log any unexpected crash
    def _on_crash(exc_type, exc_val, exc_tb):
        import traceback
        err_msg = "".join(traceback.format_exception(exc_type, exc_val, exc_tb))
        print("CRITICAL GUI EXCEPTION:\n", err_msg)
        try:
            with open(os.path.join(BASE_DIR, "gui_crash.log"), "a", encoding="utf-8") as f:
                f.write(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] UNCAUGHT EXCEPTION:\n{err_msg}\n")
        except Exception:
            pass

    sys.excepthook = _on_crash
    if hasattr(threading, 'excepthook'):
        def _thread_crash(args):
            import traceback
            err_msg = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
            print(f"CRITICAL THREAD EXCEPTION in {getattr(args.thread, 'name', 'unknown')}:\n", err_msg)
            try:
                with open(os.path.join(BASE_DIR, "gui_crash.log"), "a", encoding="utf-8") as f:
                    f.write(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] THREAD EXCEPTION in {getattr(args.thread, 'name', 'unknown')}:\n{err_msg}\n")
            except Exception:
                pass
        threading.excepthook = _thread_crash

    # Initialize all session files with WAL mode and 60s busy timeout
    try:
        import glob
        for s in glob.glob(os.path.join(BASE_DIR, "*.session")):
            ensure_session_wal_mode(s)
    except Exception:
        pass

    try:
        app = AutoMetaInstaGUI()
        app.mainloop()
    except Exception as e:
        import traceback
        err_msg = traceback.format_exc()
        print("CRITICAL MAINLOOP EXCEPTION:\n", err_msg)
        try:
            with open(os.path.join(BASE_DIR, "gui_crash.log"), "a", encoding="utf-8") as f:
                f.write(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] MAINLOOP CRASH:\n{err_msg}\n")
        except Exception:
            pass
        input("Press Enter to exit...")


if __name__ == "__main__":
    main()
