"""
==============================================================================
🔥 INSTA AUTOMATION MULTI-INSTANCE GUI CONTROLLER & DASHBOARD 🔥
==============================================================================
- Instant Startup (<0.5s GUI Launch)
- Dual-Tab Interface: Automation Dashboard & Dedicated Balance Checker
- Accurate Emulator Detection & Dynamic Device Selection ComboBox
- Independent Per-Instance Controls: Start, Pause, Stop, Restart
- Global Master Controls: Start All, Pause All, Stop All, Restart All, Refresh
- Unified Global Statistics Panel (Total Balance, Submitted, Approved, Cycles)
- Rock-Solid Backend Architecture from original gui_controller.py
==============================================================================
"""

import asyncio
import os
import queue
import re
import sys
import threading
import time
from datetime import datetime
from typing import Dict, Optional, List

import customtkinter as ctk

# Core imports
import importlib.util
OPTIMIZE_SCRIPT_PATH = os.path.join(os.path.dirname(__file__), "1tasklytometatoinsta_multi_optimize.py")
if os.path.exists(OPTIMIZE_SCRIPT_PATH):
    spec = importlib.util.spec_from_file_location("optimize_runner", OPTIMIZE_SCRIPT_PATH)
    optimize_runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(optimize_runner)
else:
    import autometainstabot as optimize_runner

# Appearance
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# Global Event Queue for Thread-Safe GUI Updates
GUI_LOG_QUEUE = queue.Queue()


def simplify_log_message(tag: str, raw_msg: str) -> Optional[str]:
    """Transforms verbose logs into clean, readable status updates"""
    tag_clean = tag.upper().strip()
    msg_clean = raw_msg.strip()

    # Filter out noisy internal debug dumps
    if any(k in tag_clean for k in ["XML", "HIERARCHY", "DUMP", "PAGE-DUMP", "COORD", "REL-COORD", "DEV-SCAN"]):
        return None
    if any(k in msg_clean.lower() for k in ["xml hierarchy", "empty ui dump", "getting screen hierarchy"]):
        return None

    # Highlight key milestones
    if "CYCLE-START" in tag_clean or "Starting Taskly" in msg_clean:
        m = re.search(r"Cycle #(\d+)", msg_clean)
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

    elif "STEP-3" in tag_clean or "Running Instagram" in msg_clean:
        if "cookies" in msg_clean.lower() or "cookies" in tag_clean.lower():
            return "📱 Emulator: Starting Instagram Cookies Setup..."
        return "📱 Emulator: Starting Instagram & 2FA Setup..."

    elif "COOKIE-EXTRACT" in tag_clean or "COOKIE-SUCCESS" in tag_clean or "COOKIE-FLOW" in tag_clean:
        return f"🍪 {msg_clean}"

    elif "TG-COOKIES" in tag_clean or "Sent account cookies" in msg_clean:
        return "🍪 Sent account cookies to Telegram bot!"

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
        m_s = re.search(r"Total Submitted:\s*(\d+)", msg_clean)
        s_str = f" [Total: {m_s.group(1)}]" if m_s else ""
        return f"📥 ✅ Report Received & Submitted to Bot!{s_str}"

    elif "TG-BALANCE" in tag_clean or "your balance:" in msg_clean.lower() or "current balance:" in msg_clean.lower() or ("balance:" in msg_clean.lower() and "$" in msg_clean):
        m_b = re.search(r"(\$[\d\.]+|\d+\.\d{2,4})", msg_clean)
        b_str = m_b.group(1) if m_b else msg_clean
        if not b_str.startswith("$") and re.match(r"^\d", b_str):
            b_str = f"${b_str}"
        return f"💰 Current Balance: {b_str}"

    elif "TG-APPROVED" in tag_clean or "report approved" in msg_clean.lower() or "+$0.03" in msg_clean:
        m_a = re.search(r"Total Approved:\s*(\d+)", msg_clean)
        a_str = f" [Total: {m_a.group(1)}]" if m_a else ""
        return f"💰 ✅ Report Approved (+$0.03)!{a_str}"

    elif "Report confirmed and accepted" in msg_clean:
        return "✅ Bot confirmed task report & credited reward!"

    elif "PHASE-1" in tag_clean:
        return "⚡ Starting fast pure-request signup..."

    elif "REQ-OTP-CONFIRM" in tag_clean or "OTP-CONFIRM" in tag_clean:
        return "📨 Submitting Meta OTP confirmation..."

    elif "PHASE-2" in tag_clean:
        return "🌐 Opening browser with session cookies..."

    elif "CHECKPOINT-FLOW" in tag_clean or "CHECKPOINT-NAV" in tag_clean:
        return "🛡️ Handling Meta Checkpoint & Human Verification..."

    elif "2CAPTCHA" in tag_clean:
        return f"🤖 2Captcha Solver: {msg_clean}"

    elif "IMG-UPLOAD" in tag_clean:
        return f"📸 Selfie Upload: {msg_clean}"

    elif "META-SUCCESS" in tag_clean:
        return "🎉 Meta AI Account Created & Verified!"

    elif "SUCCESS" in tag_clean:
        return f"✅ {msg_clean}"

    elif "ERR" in tag_clean or "FAILED" in tag_clean:
        return f"❌ {msg_clean}"

    elif "WARN" in tag_clean or "CYCLE-ABORT" in tag_clean:
        return f"⚠️ {msg_clean}"

    if len(msg_clean) < 140 and not ("{" in msg_clean and "}" in msg_clean):
        return msg_clean

    return None


def custom_gui_log_callback(tag, message, instance_name=""):
    """Intercepts optimize script logs and sends clean lines to GUI log queue"""
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


# Bind logging callback to runner module
optimize_runner.set_log_callback(custom_gui_log_callback)


def parse_balance_text(text: str) -> Optional[float]:
    """Extracts balance float value from Telegram bot response text"""
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


def check_single_account_balance_sync(account_info: dict, status_cb=None, timeout: float = 8.0):
    """
    Executes an isolated, single-purpose Telegram balance check:
    1. Connects to TelegramClient for the account
    2. Sends '/start' to the bot
    3. Finds and clicks '💰 Balance' button (or falls back to sending '💰 Balance' text)
    4. Waits for the bot's reply and extracts the balance amount
    5. Cleanly disconnects client and returns (balance, None) or (None, error_msg)
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_async_check_balance(account_info, status_cb, timeout, loop))
    finally:
        try:
            loop.close()
        except Exception:
            pass


async def _async_check_balance(account_info: dict, status_cb, timeout, loop):
    from telethon import TelegramClient, errors
    import time

    phone = account_info.get("phone", "")
    clean_phone = re.sub(r'[^0-9]', '', str(phone))
    sess_name = account_info.get("session_name") or f"taskly_session_{clean_phone}"
    script_dir = os.path.dirname(os.path.abspath(__file__))
    sess_path = os.path.join(script_dir, sess_name)

    api_id = account_info.get("api_id")
    api_hash = account_info.get("api_hash")
    raw_bots = account_info.get("target_bots") or account_info.get("target_bot") or ["tasklyBux_bot"]
    target_bot = raw_bots[0] if isinstance(raw_bots, list) else str(raw_bots)

    if not api_id or not api_hash:
        return None, "Missing API ID/Hash"

    if status_cb:
        status_cb("Connecting...", "waiting")

    client = TelegramClient(sess_path, api_id, api_hash, loop=loop)
    try:
        await client.connect()
        if not await client.is_user_authorized():
            return None, "Not authorized"

        if status_cb:
            status_cb("Sending /start...", "waiting")

        await client.send_message(target_bot, "/start")
        await asyncio.sleep(1.2)

        if status_cb:
            status_cb("Checking Balance...", "waiting")

        clicked = False
        try:
            recent_msgs = await client.get_messages(target_bot, limit=5)
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
            await client.send_message(target_bot, "💰 Balance")

        start_t = time.time()
        captured_bal = None
        while (time.time() - start_t) < timeout:
            await asyncio.sleep(0.4)
            recent = await client.get_messages(target_bot, limit=4)
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
            return None, "No balance reply"

    except errors.FloodWaitError as fw:
        return None, f"FloodWait ({fw.seconds}s)"
    except Exception as e:
        err = str(e)
        if "database is locked" in err.lower() or "locked" in err.lower():
            return None, "Busy (Instance running)"
        return None, err[:35]
    finally:
        try:
            if client.is_connected():
                await client.disconnect()
        except Exception:
            pass


class InstanceCard(ctk.CTkFrame):
    """UI Card for controlling an individual instance and showing its own log box"""
    def __init__(self, master, instance_id: int, account_info: dict, device_serial: str, on_start, on_stop, on_restart, dashboard=None):
        super().__init__(master, corner_radius=12, fg_color="#1a1d24", border_width=1, border_color="#2a303c")
        
        self.instance_id = instance_id
        self.instance_name = f"Inst-{instance_id}"
        self.account_info = account_info
        self.device_serial = device_serial
        self.on_start = on_start
        self.on_stop = on_stop
        self.on_restart = on_restart
        self.dashboard = dashboard
        
        self.status = "Stopped"
        self.submitted_count = 0
        self.approved_count = 0
        self.cycle_count = 0
        self.balance = 0.0
        self.is_paused = False
        
        self._build_ui()

    def _build_ui(self):
        # Header Row
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=14, pady=(12, 4))

        title_label = ctk.CTkLabel(
            header_frame,
            text=f"⚡ INSTANCE {self.instance_id}",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color="#60a5fa"
        )
        title_label.pack(side="left")

        phone = self.account_info.get("phone", "Unknown")
        phone_badge = ctk.CTkLabel(
            header_frame,
            text=f"📱 {phone}",
            font=ctk.CTkFont(size=12),
            text_color="#94a3b8"
        )
        phone_badge.pack(side="left", padx=8)

        self.balance_badge = ctk.CTkLabel(
            header_frame,
            text="💵 $0.0000",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#10b981",
            fg_color="#064e3b",
            corner_radius=8,
            padx=8,
            pady=2
        )
        self.balance_badge.pack(side="left", padx=6)

        self.status_pill = ctk.CTkLabel(
            header_frame,
            text="● Stopped",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#ef4444",
            fg_color="#2d1519",
            corner_radius=8,
            padx=10,
            pady=3
        )
        self.status_pill.pack(side="right")

        # Info & Stats Row
        self.info_frame = ctk.CTkFrame(self, fg_color="#12151c", corner_radius=8)
        self.info_frame.pack(fill="x", padx=14, pady=4)

        adb_lbl = ctk.CTkLabel(
            self.info_frame,
            text="ADB:",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#94a3b8"
        )
        adb_lbl.pack(side="left", padx=(10, 4), pady=4)

        dev_choices = [self.device_serial] if self.device_serial and self.device_serial != "Detecting..." else ["Detecting..."]
        if self.dashboard and getattr(self.dashboard, "devices", None):
            dev_choices = self.dashboard.devices

        self.device_combo = ctk.CTkComboBox(
            self.info_frame,
            values=dev_choices,
            width=140,
            height=24,
            font=ctk.CTkFont(family="Consolas", size=11),
            command=self._on_device_selected
        )
        self.device_combo.set(self.device_serial)
        self.device_combo.pack(side="left", padx=(0, 8), pady=4)

        raw_bots = self.account_info.get("target_bots") or self.account_info.get("target_bot") or ["tasklyBux_bot"]
        bot_name = raw_bots[0] if isinstance(raw_bots, list) else str(raw_bots)
        self.bot_lbl = ctk.CTkLabel(
            self.info_frame,
            text=f"🤖 @{bot_name}",
            font=ctk.CTkFont(size=11),
            text_color="#64748b"
        )
        self.bot_lbl.pack(side="left", padx=4, pady=4)

        self.stats_lbl = ctk.CTkLabel(
            self.info_frame,
            text="Cycles: 0  |  📥 Sub: 0  |  💰 App: 0  |  💵 Bal: $0.0000",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#38bdf8"
        )
        self.stats_lbl.pack(side="right", padx=10, pady=4)

        # Dedicated Monospace Log Box
        self.log_box = ctk.CTkTextbox(
            self,
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color="#0d1117",
            text_color="#e2e8f0",
            corner_radius=8,
            border_width=1,
            border_color="#1e293b",
            wrap="word",
            height=160
        )
        self.log_box.pack(fill="both", expand=True, padx=14, pady=8)
        self.log_box.configure(state="disabled")

        # Action Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=14, pady=(4, 12))

        self.btn_start = ctk.CTkButton(
            btn_frame,
            text="▶ Start",
            width=75,
            height=30,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#16a34a",
            hover_color="#15803d",
            command=lambda: self.on_start(self.instance_id)
        )
        self.btn_start.pack(side="left", padx=(0, 6))

        self.btn_pause = ctk.CTkButton(
            btn_frame,
            text="⏸ Pause",
            width=75,
            height=30,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#d97706",
            hover_color="#b45309",
            command=self.toggle_pause
        )
        self.btn_pause.pack(side="left", padx=6)

        self.btn_stop = ctk.CTkButton(
            btn_frame,
            text="⏹ Stop",
            width=75,
            height=30,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#dc2626",
            hover_color="#b91c1c",
            command=lambda: self.on_stop(self.instance_id)
        )
        self.btn_stop.pack(side="left", padx=6)

        self.btn_restart = ctk.CTkButton(
            btn_frame,
            text="🔄 Restart",
            width=80,
            height=30,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            command=lambda: self.on_restart(self.instance_id)
        )
        self.btn_restart.pack(side="left", padx=6)

        self.btn_clear = ctk.CTkButton(
            btn_frame,
            text="🗑 Clear",
            width=65,
            height=30,
            font=ctk.CTkFont(size=12),
            fg_color="#334155",
            hover_color="#475569",
            command=self.clear_logs
        )
        self.btn_clear.pack(side="right")

    def _on_device_selected(self, choice: str):
        self.device_serial = choice
        self.append_log(datetime.now().strftime("%H:%M:%S"), f"📱 Device manually set to: {choice}")

    def append_log(self, time_str: str, text: str):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"[{time_str}] {text}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

        if "Current Balance:" in text or "TG-BALANCE" in text or "Your balance:" in text or "Account Balance:" in text or "Bal:" in text:
            m_b = re.search(r"(\$[\d\.]+|\d+\.\d{2,4})", text)
            if m_b:
                val = m_b.group(1).replace("$", "")
                try:
                    self.balance = float(val)
                    self.update_stats()
                    if self.dashboard and hasattr(self.dashboard, "update_global_summary"):
                        self.dashboard.update_global_summary()
                    if self.dashboard and hasattr(self.dashboard, "sync_balance_to_tab"):
                        self.dashboard.sync_balance_to_tab(self.instance_id, self.balance)
                except Exception:
                    pass

        m_sub = re.search(r"(?:Total\s+Submitted|\[SUBMITTED\].*?Total|Submitted|Sub):\s*(\d+)", text, re.IGNORECASE)
        if m_sub:
            val = int(m_sub.group(1))
            if val > self.submitted_count:
                self.submitted_count = val
                self.update_stats()
                if self.dashboard and hasattr(self.dashboard, "update_global_summary"):
                    self.dashboard.update_global_summary()

        m_app = re.search(r"(?:Total\s+Approved|\[APPROVED\].*?Total|Approved|App):\s*(\d+)", text, re.IGNORECASE)
        if m_app:
            val = int(m_app.group(1))
            if val > self.approved_count:
                self.approved_count = val
                self.update_stats()
                if self.dashboard and hasattr(self.dashboard, "update_global_summary"):
                    self.dashboard.update_global_summary()
        elif "Starting Cycle" in text:
            self.cycle_count += 1
            self.update_stats()
            if self.dashboard and hasattr(self.dashboard, "update_global_summary"):
                self.dashboard.update_global_summary()

    def clear_logs(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    def update_stats(self):
        self.stats_lbl.configure(text=f"Cycles: {self.cycle_count}  |  📥 Sub: {self.submitted_count}  |  💰 App: {self.approved_count}  |  💵 Bal: ${self.balance:.4f}")
        self.balance_badge.configure(text=f"💵 ${self.balance:.4f}")

    def update_device(self, new_device: str, all_devices: Optional[List[str]] = None):
        self.device_serial = new_device
        if hasattr(self, "device_combo"):
            if all_devices:
                self.device_combo.configure(values=all_devices)
            self.device_combo.set(new_device)
        raw_bots = self.account_info.get("target_bots") or self.account_info.get("target_bot") or ["tasklyBux_bot"]
        bot_name = raw_bots[0] if isinstance(raw_bots, list) else str(raw_bots)
        if hasattr(self, "bot_lbl"):
            self.bot_lbl.configure(text=f"🤖 @{bot_name}")

    def toggle_pause(self):
        if self.dashboard and hasattr(self.dashboard, "toggle_pause_instance"):
            self.dashboard.toggle_pause_instance(self.instance_id)

    def set_paused_ui(self, is_paused: bool):
        self.is_paused = is_paused
        if is_paused:
            self.btn_pause.configure(text="▶ Resume", fg_color="#2563eb", hover_color="#1d4ed8")
            self.set_status("Paused", "paused")
        else:
            self.btn_pause.configure(text="⏸ Pause", fg_color="#d97706", hover_color="#b45309")
            self.set_status("Running", "running")

    def set_status(self, status: str, color_type: str = "running"):
        self.status = status
        colors = {
            "running": ("● Running", "#22c55e", "#142d1e"),
            "working": (f"● {status}", "#38bdf8", "#11263c"),
            "waiting": (f"● {status}", "#fbbf24", "#302611"),
            "paused": ("● Paused", "#fbbf24", "#302611"),
            "stopped": ("● Stopped", "#ef4444", "#2d1519"),
            "success": ("● Success", "#22c55e", "#142d1e"),
            "error": ("● Error", "#f87171", "#331818"),
        }
        text, fg, bg = colors.get(color_type, (f"● {status}", "#94a3b8", "#1e293b"))
        self.status_pill.configure(text=text, text_color=fg, fg_color=bg)


class AccountBalanceRow(ctk.CTkFrame):
    """UI Row for an account in the dedicated Balance Checker tab"""
    def __init__(self, master, acc_index: int, account_info: dict, on_check_balance, dashboard=None):
        super().__init__(master, corner_radius=10, fg_color="#1a1d24", border_width=1, border_color="#2a303c")
        self.acc_index = acc_index
        self.account_info = account_info
        self.on_check_balance = on_check_balance
        self.dashboard = dashboard

        self.phone = str(self.account_info.get("phone", "Unknown"))
        self.balance = 0.0
        self.last_checked_time = "Never"
        self.status = "Idle"

        self._build_ui()

    def _build_ui(self):
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=10)

        # 1. Index Badge (#01, #02...)
        idx_str = f"#{self.acc_index + 1:02d}"
        self.idx_lbl = ctk.CTkLabel(
            row,
            text=idx_str,
            font=ctk.CTkFont(family="Consolas", size=13, weight="bold"),
            text_color="#94a3b8",
            fg_color="#1e293b",
            corner_radius=6,
            width=42,
            height=28
        )
        self.idx_lbl.pack(side="left", padx=(0, 10))

        # 2. Phone Number
        self.phone_lbl = ctk.CTkLabel(
            row,
            text=f"📱 {self.phone}",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#f8fafc",
            width=150,
            anchor="w"
        )
        self.phone_lbl.pack(side="left", padx=(0, 10))

        # 3. Target Bot
        raw_bots = self.account_info.get("target_bots") or self.account_info.get("target_bot") or ["tasklyBux_bot"]
        bot_name = raw_bots[0] if isinstance(raw_bots, list) else str(raw_bots)
        self.bot_lbl = ctk.CTkLabel(
            row,
            text=f"🤖 @{bot_name}",
            font=ctk.CTkFont(size=12),
            text_color="#64748b",
            width=140,
            anchor="w"
        )
        self.bot_lbl.pack(side="left", padx=(0, 10))

        # 4. Status Pill
        self.status_pill = ctk.CTkLabel(
            row,
            text="● Idle",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#94a3b8",
            fg_color="#1e293b",
            corner_radius=6,
            padx=10,
            pady=3,
            width=140
        )
        self.status_pill.pack(side="left", padx=(0, 10))

        # 5. Balance Badge (Large bold green)
        self.balance_badge = ctk.CTkLabel(
            row,
            text="💵 $0.0000",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#10b981",
            fg_color="#064e3b",
            corner_radius=8,
            padx=12,
            pady=4,
            width=110
        )
        self.balance_badge.pack(side="left", padx=(0, 12))

        # 6. Last Checked Time
        self.time_lbl = ctk.CTkLabel(
            row,
            text="🕒 Checked: Never",
            font=ctk.CTkFont(size=11),
            text_color="#64748b",
            width=130,
            anchor="w"
        )
        self.time_lbl.pack(side="left", padx=(0, 10))

        # 7. Action Button
        self.btn_check = ctk.CTkButton(
            row,
            text="🔄 Check Balance",
            width=130,
            height=30,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            command=self._on_check_clicked
        )
        self.btn_check.pack(side="right")

    def _on_check_clicked(self):
        if self.on_check_balance:
            self.on_check_balance(self.acc_index)

    def set_checking_state(self, is_checking: bool):
        if is_checking:
            self.btn_check.configure(state="disabled", text="⏳ Checking...")
            self.set_status("Checking...", "waiting")
        else:
            self.btn_check.configure(state="normal", text="🔄 Check Balance")

    def set_balance(self, bal: float, time_str: str = ""):
        self.balance = float(bal)
        self.balance_badge.configure(text=f"💵 ${self.balance:.4f}")
        if time_str:
            self.last_checked_time = time_str
            self.time_lbl.configure(text=f"🕒 Checked: {time_str}")

    def set_status(self, status: str, color_type: str = "idle"):
        self.status = status
        colors = {
            "idle": (f"● {status}", "#94a3b8", "#1e293b"),
            "waiting": (f"● {status}", "#fbbf24", "#302611"),
            "working": (f"● {status}", "#38bdf8", "#11263c"),
            "success": ("● Success", "#22c55e", "#142d1e"),
            "busy": (f"● {status}", "#f59e0b", "#3d2a06"),
            "error": (f"● {status}", "#f87171", "#331818"),
        }
        text, fg, bg = colors.get(color_type, (f"● {status}", "#94a3b8", "#1e293b"))
        self.status_pill.configure(text=text, text_color=fg, fg_color=bg)


class WorkerRunnerThread(threading.Thread):
    """Dedicated Thread per worker instance with isolated event loop & Telethon client"""
    def __init__(self, worker_id: int, account_info: dict, device_serial: str, task_mode: Optional[str] = None, on_state_change=None):
        super().__init__(daemon=True)
        self.worker_id = worker_id
        self.instance_name = f"Inst-{worker_id}"
        self.account_info = account_info
        self.device_serial = device_serial
        self.task_mode = task_mode
        self.on_state_change = on_state_change
        
        self.worker: Optional[optimize_runner.TasklyWorker] = None
        self.loop = None
        self._is_stopped = False

    def run(self):
        self._is_stopped = False
        if self.on_state_change:
            self.on_state_change(self.worker_id, "Running", "running")
            
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        try:
            self.loop.run_until_complete(self._async_run())
        except (asyncio.CancelledError, KeyboardInterrupt):
            pass
        except Exception as e:
            optimize_runner.log("WORKER-ERR", f"Worker error: {e}", instance_name=self.instance_name)
            if self.on_state_change:
                self.on_state_change(self.worker_id, "Error", "error")
        finally:
            self._is_stopped = True
            if self.on_state_change:
                self.on_state_change(self.worker_id, "Stopped", "stopped")

    async def _async_run(self):
        from playwright.async_api import async_playwright
        from telethon import TelegramClient

        acc = self.account_info
        clean_phone = re.sub(r'[^0-9]', '', str(acc['phone']))
        sess_name = acc.get('session_name') or f"taskly_session_{clean_phone}"

        # Connect isolated Telethon Client on current loop
        optimize_runner.log("INIT", f"Connecting Telegram Userbot for {acc['phone']}...", instance_name=self.instance_name)
        tg_client = TelegramClient(sess_name, acc['api_id'], acc['api_hash'], loop=self.loop)
        await tg_client.start(phone=acc['phone'])
        optimize_runner.log("INIT", f"Telegram logged in successfully for {acc['phone']}", instance_name=self.instance_name)

        raw_bots = acc.get("target_bots") or acc.get("target_bot") or optimize_runner.TARGET_BOTS
        norm_bots = optimize_runner.normalize_target_bots(raw_bots)

        task_mode = self.task_mode or acc.get("task_mode") or optimize_runner.load_config().get("task_mode", "cookies")

        self.worker = optimize_runner.TasklyWorker(
            acc,
            self.device_serial,
            self.instance_name,
            target_bot=norm_bots[0],
            client=tg_client,
            task_mode=task_mode
        )

        # Start Telethon update receiver background task
        tg_listener = asyncio.create_task(tg_client.run_until_disconnected())

        try:
            async with async_playwright() as pw:
                await self.worker.run(pw)
        finally:
            if not tg_listener.done():
                tg_listener.cancel()
            try:
                await tg_client.disconnect()
            except Exception:
                pass

    def pause(self):
        """Safely pauses the worker if supported"""
        if self.worker and hasattr(self.worker, "pause"):
            self.worker.pause()

    def resume(self):
        """Safely resumes the worker if supported"""
        if self.worker and hasattr(self.worker, "resume"):
            self.worker.resume()

    def stop(self):
        """Cleanly stops worker, browser context, and android app"""
        self._is_stopped = True
        if self.worker:
            self.worker.stop()
        if self.loop and self.loop.is_running():
            try:
                for task in asyncio.all_tasks(self.loop):
                    task.cancel()
            except Exception:
                pass
            self.loop.call_soon_threadsafe(self.loop.stop)


class MultiInstanceDashboard(ctk.CTk):
    """Main Application Window"""
    def __init__(self):
        super().__init__()

        self.title("⚡ Insta 2FA Multi-Instance Controller & Dashboard")
        self.geometry("1120, 800")
        self.minsize(850, 600)
        self.configure(fg_color="#0f1115")

        self.cfg = optimize_runner.load_config()
        self.accounts = self.cfg.get("telegram", {}).get("accounts", [])
        self.devices: List[str] = []

        self.active_tab = "automation"
        self.instance_cards: Dict[int, InstanceCard] = {}
        self.balance_rows: Dict[int, AccountBalanceRow] = {}
        self.worker_threads: Dict[int, WorkerRunnerThread] = {}
        self.is_all_paused = False

        self._is_checking_all = False
        self._cancel_check_all = False

        self._build_nav_bar()
        self._build_tab_containers()
        self._start_log_consumer()

        # Fast non-blocking background device discovery
        threading.Thread(target=self._async_initial_device_scan, daemon=True).start()

    def _build_nav_bar(self):
        self.nav_frame = ctk.CTkFrame(self, fg_color="#12151c", height=48, corner_radius=0)
        self.nav_frame.pack(fill="x", side="top", padx=0, pady=0)

        nav_inner = ctk.CTkFrame(self.nav_frame, fg_color="transparent")
        nav_inner.pack(fill="both", expand=True, padx=16, pady=7)

        self.btn_tab_automation = ctk.CTkButton(
            nav_inner,
            text="⚡ Automation Dashboard",
            width=190,
            height=34,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            command=lambda: self.switch_tab("automation")
        )
        self.btn_tab_automation.pack(side="left", padx=(0, 8))

        self.btn_tab_balance = ctk.CTkButton(
            nav_inner,
            text="💰 Balance Checker",
            width=170,
            height=34,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#1e293b",
            hover_color="#334155",
            command=lambda: self.switch_tab("balance")
        )
        self.btn_tab_balance.pack(side="left", padx=8)

        self.nav_title_lbl = ctk.CTkLabel(
            nav_inner,
            text="🔥 Insta 2FA Multi Controller & Dashboard",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#64748b"
        )
        self.nav_title_lbl.pack(side="right", padx=(8, 4))

    def _build_tab_containers(self):
        self.tab_automation_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.tab_balance_frame = ctk.CTkFrame(self, fg_color="transparent")

        # Tab 1: Automation Dashboard
        self._build_header(parent=self.tab_automation_frame)
        self._build_instances_grid(parent=self.tab_automation_frame)

        # Tab 2: Dedicated Balance Checker
        self._build_balance_tab(parent=self.tab_balance_frame)

        # Show Automation Dashboard by default
        self.tab_automation_frame.pack(fill="both", expand=True)

    def switch_tab(self, tab_name: str):
        if tab_name == "automation":
            self.active_tab = "automation"
            self.tab_balance_frame.pack_forget()
            self.tab_automation_frame.pack(fill="both", expand=True)
            self.btn_tab_automation.configure(fg_color="#2563eb", hover_color="#1d4ed8")
            self.btn_tab_balance.configure(fg_color="#1e293b", hover_color="#334155")
        elif tab_name == "balance":
            self.active_tab = "balance"
            self.tab_automation_frame.pack_forget()
            self.tab_balance_frame.pack(fill="both", expand=True)
            self.btn_tab_balance.configure(fg_color="#10b981", hover_color="#059669")
            self.btn_tab_automation.configure(fg_color="#1e293b", hover_color="#334155")

    def _build_header(self, parent=None):
        target_parent = parent if parent is not None else self
        header_frame = ctk.CTkFrame(target_parent, fg_color="#161922", corner_radius=14, border_width=1, border_color="#232936")
        header_frame.pack(fill="x", padx=16, pady=(16, 10))

        # Row 1: Action Controls Anchored to the LEFT CORNER
        controls_row = ctk.CTkFrame(header_frame, fg_color="transparent")
        controls_row.pack(fill="x", padx=14, pady=(10, 4))

        self.btn_start_all = ctk.CTkButton(
            controls_row,
            text="▶ Start All",
            width=95,
            height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#16a34a",
            hover_color="#15803d",
            command=self.start_all_instances
        )
        self.btn_start_all.pack(side="left", padx=(0, 6))

        self.btn_pause_all = ctk.CTkButton(
            controls_row,
            text="⏸ Pause All",
            width=95,
            height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#d97706",
            hover_color="#b45309",
            command=self.toggle_pause_all
        )
        self.btn_pause_all.pack(side="left", padx=6)

        self.btn_stop_all = ctk.CTkButton(
            controls_row,
            text="⏹ Stop All",
            width=95,
            height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#dc2626",
            hover_color="#b91c1c",
            command=self.stop_all_instances
        )
        self.btn_stop_all.pack(side="left", padx=6)

        self.btn_restart_all = ctk.CTkButton(
            controls_row,
            text="🔄 Restart All",
            width=100,
            height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            command=self.restart_all_instances
        )
        self.btn_restart_all.pack(side="left", padx=6)

        self.btn_refresh = ctk.CTkButton(
            controls_row,
            text="🔄 Refresh",
            width=85,
            height=32,
            font=ctk.CTkFont(size=12),
            fg_color="#334155",
            hover_color="#475569",
            command=self.refresh_devices_and_config
        )
        self.btn_refresh.pack(side="left", padx=6)

        self.btn_launch_ld9 = ctk.CTkButton(
            controls_row,
            text="📱 Launch Emulator",
            width=120,
            height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#7c3aed",
            hover_color="#6d28d9",
            command=self.launch_ldplayer_9
        )
        self.btn_launch_ld9.pack(side="left", padx=6)

        self.btn_fix_adb = ctk.CTkButton(
            controls_row,
            text="⚡ Fix ADB",
            width=85,
            height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#0891b2",
            hover_color="#0e7490",
            command=self.fix_and_restart_adb
        )
        self.btn_fix_adb.pack(side="left", padx=6)

        # Task Mode selector: Cookies Mode vs 2FA Mode vs 2FA + Cookies Mode
        initial_mode = self.cfg.get("task_mode", "cookies").lower()
        if "random" in initial_mode:
            mode_val = "🎲 Random 2FA + Cookies Mode"
        elif "2fa" in initial_mode and "cookie" in initial_mode:
            mode_val = "🔐 2FA + Cookies Mode"
        elif initial_mode == "cookies":
            mode_val = "🍪 Cookies Mode"
        else:
            mode_val = "🔐 2FA Mode"
        self.mode_var = ctk.StringVar(value=mode_val)
        self.mode_dropdown = ctk.CTkOptionMenu(
            controls_row,
            values=["🍪 Cookies Mode", "🔐 2FA Mode", "🔐 2FA + Cookies Mode", "🎲 Random 2FA + Cookies Mode"],
            variable=self.mode_var,
            width=185,
            height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#0f766e",
            button_color="#115e59",
            button_hover_color="#134e4a",
            command=self.on_mode_change
        )
        self.mode_dropdown.pack(side="left", padx=6)

        self.header_title_lbl = ctk.CTkLabel(
            controls_row,
            text="⚡ Insta Task Multi Controller",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#64748b"
        )
        self.header_title_lbl.pack(side="right", padx=(6, 2))

        # Row 2: Unified Global Statistics Panel (Left-aligned, never cut off)
        self.stats_tab_frame = ctk.CTkFrame(header_frame, fg_color="#0d1117", corner_radius=10, border_width=1, border_color="#1e293b")
        self.stats_tab_frame.pack(fill="x", padx=14, pady=(6, 12))

        # 💵 Total Balance Badge (Sum of all instances)
        self.total_balance_badge = ctk.CTkLabel(
            self.stats_tab_frame,
            text="💵 Total Balance: $0.0000",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#10b981",
            fg_color="#064e3b",
            corner_radius=8,
            padx=12,
            pady=6
        )
        self.total_balance_badge.pack(side="left", padx=(10, 6), pady=6)

        # 📥 Total Submitted Badge
        self.total_sub_lbl = ctk.CTkLabel(
            self.stats_tab_frame,
            text="📥 Total Submitted: 0",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#38bdf8",
            fg_color="#11263c",
            corner_radius=8,
            padx=10,
            pady=6
        )
        self.total_sub_lbl.pack(side="left", padx=6, pady=6)

        # 💰 Total Approved Badge
        self.total_app_lbl = ctk.CTkLabel(
            self.stats_tab_frame,
            text="💰 Total Approved: 0",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#fbbf24",
            fg_color="#302611",
            corner_radius=8,
            padx=10,
            pady=6
        )
        self.total_app_lbl.pack(side="left", padx=6, pady=6)

        # 🚀 Total Cycles Badge
        self.total_cycles_lbl = ctk.CTkLabel(
            self.stats_tab_frame,
            text="🚀 Total Cycles: 0",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#c084fc",
            fg_color="#2a153d",
            corner_radius=8,
            padx=10,
            pady=6
        )
        self.total_cycles_lbl.pack(side="left", padx=6, pady=6)

        # 📱 Emulators / Accounts Status
        self.status_summary_lbl = ctk.CTkLabel(
            self.stats_tab_frame,
            text=f"📱 Emulators: 0 Active | {len(self.accounts)} Accounts",
            font=ctk.CTkFont(size=12),
            text_color="#94a3b8",
            padx=8,
            pady=6
        )
        self.status_summary_lbl.pack(side="left", padx=(6, 10), pady=6)

    def _build_instances_grid(self, parent=None):
        target_parent = parent if parent is not None else self
        self.scroll_container = ctk.CTkScrollableFrame(target_parent, fg_color="transparent")
        self.scroll_container.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        num_instances = len(self.accounts) if self.accounts else 1
        self.scroll_container.grid_columnconfigure(0, weight=1)
        self.scroll_container.grid_columnconfigure(1, weight=1)

        for i in range(num_instances):
            inst_id = i + 1
            acc = self.accounts[i] if i < len(self.accounts) else {"phone": "Not Configured"}
            dev = self.devices[i] if i < len(self.devices) else "Detecting..."

            card = InstanceCard(
                self.scroll_container,
                instance_id=inst_id,
                account_info=acc,
                device_serial=dev,
                on_start=self.start_instance,
                on_stop=self.stop_instance,
                on_restart=self.restart_instance,
                dashboard=self
            )
            row = i // 2
            col = i % 2
            card.grid(row=row, column=col, padx=8, pady=8, sticky="nsew")
            self.instance_cards[inst_id] = card

    def _async_initial_device_scan(self):
        """Fast background discovery of active emulators"""
        devs = optimize_runner.get_unique_devices(emulators_only=True)
        self.after(0, lambda: self._apply_discovered_devices(devs))

    def _apply_discovered_devices(self, devs: List[str]):
        self.devices = devs
        self.update_global_summary()
        all_devs = self.devices if self.devices else ["No Device Detected"]
        for i, (inst_id, card) in enumerate(self.instance_cards.items()):
            assigned_dev = self.devices[i] if i < len(self.devices) else "No Device Detected"
            card.update_device(assigned_dev, all_devices=all_devs)

    def update_global_summary(self):
        """Updates top header stats bar with total balance, submitted, approved, and cycles"""
        total_balance = sum(getattr(c, "balance", 0.0) for c in self.instance_cards.values())
        total_sub = sum(c.submitted_count for c in self.instance_cards.values())
        total_app = sum(c.approved_count for c in self.instance_cards.values())
        total_cycles = sum(c.cycle_count for c in self.instance_cards.values())

        running_cnt = sum(1 for r in self.worker_threads.values() if r.is_alive() and not getattr(r, "_is_stopped", False) and not getattr(getattr(r, "worker", None), "is_paused", False))
        paused_cnt = sum(1 for r in self.worker_threads.values() if r.is_alive() and getattr(getattr(r, "worker", None), "is_paused", False))

        self.total_balance_badge.configure(text=f"💵 Total Balance: ${total_balance:.4f}")
        self.total_sub_lbl.configure(text=f"📥 Total Submitted: {total_sub}")
        self.total_app_lbl.configure(text=f"💰 Total Approved: {total_app}")
        self.total_cycles_lbl.configure(text=f"🚀 Total Cycles: {total_cycles}")
        
        emu_count = len(self.devices)
        acc_count = len(self.accounts)
        state_str = f" | 🟢 Running: {running_cnt}" if running_cnt > 0 else ""
        if paused_cnt > 0:
            state_str += f" | ⏸ Paused: {paused_cnt}"
        self.status_summary_lbl.configure(
            text=f"📱 Emulators: {emu_count} Active | {acc_count} Accounts{state_str}"
        )

    def toggle_pause_all(self):
        """Toggles pause/resume state across all running instances"""
        if not self.is_all_paused:
            self.is_all_paused = True
            for runner in self.worker_threads.values():
                if runner and runner.is_alive():
                    runner.pause()
            for inst_id, card in self.instance_cards.items():
                card.set_paused_ui(True)
            self.btn_pause_all.configure(text="▶ Resume All", fg_color="#2563eb", hover_color="#1d4ed8")
            self.update_global_summary()
        else:
            self.is_all_paused = False
            for runner in self.worker_threads.values():
                if runner and runner.is_alive():
                    runner.resume()
            for inst_id, card in self.instance_cards.items():
                card.set_paused_ui(False)
            self.btn_pause_all.configure(text="⏸ Pause All", fg_color="#d97706", hover_color="#b45309")
            self.update_global_summary()

    def toggle_pause_instance(self, inst_id: int):
        """Toggles pause/resume for a single instance"""
        runner = self.worker_threads.get(inst_id)
        card = self.instance_cards.get(inst_id)
        if not runner or not runner.is_alive():
            if card:
                card.append_log(datetime.now().strftime("%H:%M:%S"), "⚠️ Instance is not running, cannot pause.")
            return

        worker = getattr(runner, "worker", None)
        if worker and getattr(worker, "is_paused", False):
            runner.resume()
            if card:
                card.set_paused_ui(False)
        else:
            runner.pause()
            if card:
                card.set_paused_ui(True)
        self.update_global_summary()

    def _start_log_consumer(self):
        """Processes incoming log messages and routes them to appropriate instance cards"""
        def poll_queue():
            while not GUI_LOG_QUEUE.empty():
                item = GUI_LOG_QUEUE.get_nowait()
                inst_name = item.get("instance", "MAIN")
                time_str = item.get("time", "")
                text = item.get("text", "")
                
                m = re.search(r"Inst-(\d+)", inst_name, re.IGNORECASE)
                if m:
                    inst_id = int(m.group(1))
                    card = self.instance_cards.get(inst_id)
                    if card:
                        card.append_log(time_str, text)
                        if "Starting" in text or "Registering" in text or "Opening browser" in text:
                            card.set_status("Working", "working")
                        elif "Paused" in text:
                            card.set_status("Paused", "paused")
                        elif "Resumed" in text:
                            card.set_status("Working", "working")
                        elif "Waiting for" in text or "Fetching" in text or "Polling" in text or "Checking" in text:
                            card.set_status("Waiting", "waiting")
                        elif "CYCLE" in text and ("COMPLETE" in text or "SUCCESS" in text):
                            card.set_status("Success", "success")
                        elif "❌" in text or "Error" in text or "FAILED" in text:
                            card.set_status("Error", "error")
                else:
                    for card in self.instance_cards.values():
                        card.append_log(time_str, f"[System] {text}")

            self.after(150, poll_queue)

        self.after(150, poll_queue)

    def on_instance_state_changed(self, inst_id: int, status: str, color_type: str):
        card = self.instance_cards.get(inst_id)
        if card:
            self.after(0, lambda: card.set_status(status, color_type))
            self.after(0, self.update_global_summary)

    def start_instance(self, inst_id: int):
        card = self.instance_cards.get(inst_id)
        if not card:
            return

        runner = self.worker_threads.get(inst_id)
        if runner and runner.is_alive() and not runner._is_stopped:
            card.append_log(datetime.now().strftime("%H:%M:%S"), "⚠️ Instance is already running!")
            return

        if card.device_serial in ["No Device Detected", "Detecting..."]:
            card.append_log(datetime.now().strftime("%H:%M:%S"), "❌ Cannot start: No active ADB emulator assigned! Please start emulator and click Refresh.")
            return

        card.append_log(datetime.now().strftime("%H:%M:%S"), f"🚀 Starting Instance on {card.device_serial}...")
        card.set_status("Starting...", "working")

        if hasattr(self, "mode_var"):
            m_val = self.mode_var.get().lower()
            if "2fa" in m_val and "cookie" in m_val:
                selected_mode = "2fa_cookies"
            elif "cookies" in m_val:
                selected_mode = "cookies"
            else:
                selected_mode = "2fa"
        else:
            selected_mode = "2fa"
        new_runner = WorkerRunnerThread(
            worker_id=inst_id,
            account_info=card.account_info,
            device_serial=card.device_serial,
            task_mode=selected_mode,
            on_state_change=self.on_instance_state_changed
        )
        self.worker_threads[inst_id] = new_runner
        new_runner.start()
        self.update_global_summary()

    def stop_instance(self, inst_id: int):
        card = self.instance_cards.get(inst_id)
        if not card:
            return

        runner = self.worker_threads.get(inst_id)
        if runner and runner.is_alive():
            card.append_log(datetime.now().strftime("%H:%M:%S"), "⏹ Stopping instance worker...")
            card.set_status("Stopping...", "waiting")
            runner.stop()
        else:
            card.set_status("Stopped", "stopped")
        self.update_global_summary()

    def restart_instance(self, inst_id: int):
        card = self.instance_cards.get(inst_id)
        if not card:
            return
        card.append_log(datetime.now().strftime("%H:%M:%S"), "🔄 Restarting instance...")
        self.stop_instance(inst_id)
        self.after(1200, lambda: self.start_instance(inst_id))

    def start_all_instances(self):
        for idx, inst_id in enumerate(self.instance_cards.keys()):
            delay_ms = idx * 2500  # Stagger worker starts by 2.5s for clean parallel initialization
            self.after(delay_ms, lambda i=inst_id: self.start_instance(i))

    def stop_all_instances(self):
        for inst_id in self.instance_cards.keys():
            self.stop_instance(inst_id)

    def restart_all_instances(self):
        self.stop_all_instances()
        self.after(1500, self.start_all_instances)

    def on_mode_change(self, choice: str):
        choice_lower = choice.lower()
        if "random" in choice_lower:
            mode_str = "random_2fa_cookies"
        elif "2fa" in choice_lower and "cookie" in choice_lower:
            mode_str = "2fa_cookies"
        elif "cookies" in choice_lower:
            mode_str = "cookies"
        else:
            mode_str = "2fa"
        self.cfg["task_mode"] = mode_str
        optimize_runner.log("GUI", f"Switched Task Mode to: {choice.upper()}", instance_name="GUI")

    def refresh_devices_and_config(self):
        """Refreshes devices and config dynamically across both tabs"""
        self.cfg = optimize_runner.load_config()
        self.accounts = self.cfg.get("telegram", {}).get("accounts", [])
        self.status_summary_lbl.configure(text="Refreshing emulators & config...")
        self._populate_balance_rows()
        threading.Thread(target=self._async_initial_device_scan, daemon=True).start()

    def launch_ldplayer_9(self):
        """Launches MuMu Player or LDPlayer directly with working directory configured"""
        optimize_runner.ensure_ldplayer_adb_enabled()
        import subprocess
        candidates = [
            (r"E:\MuMuPlayerGlobal\nx_main\MuMuNxMain.exe", r"E:\MuMuPlayerGlobal\nx_main", "MuMu Player"),
            (r"D:\Program Files\Netease\MuMuPlayer\nx_main\MuMuNxMain.exe", r"D:\Program Files\Netease\MuMuPlayer\nx_main", "MuMu Player"),
            (r"D:\LDPlayer\LDPlayer9\dnplayer.exe", r"D:\LDPlayer\LDPlayer9", "LDPlayer 9"),
            (r"D:\LDPlayer\ldmutiplayer\dnmultiplayerex.exe", r"D:\LDPlayer\ldmutiplayer", "LDPlayer 9"),
            (r"C:\LDPlayer\LDPlayer9\dnplayer.exe", r"C:\LDPlayer\LDPlayer9", "LDPlayer 9"),
            (r"D:\LDPlayer\LDPlayer14\dnplayer.exe", r"D:\LDPlayer\LDPlayer14", "LDPlayer 14"),
        ]
        launched = False
        launched_name = "Emulator"
        for item in candidates:
            exe, cwd, name = item[0], item[1], item[2]
            if os.path.exists(exe):
                try:
                    subprocess.Popen([exe], cwd=cwd, shell=True)
                    launched = True
                    launched_name = name
                    break
                except Exception:
                    pass
        if launched:
            self.status_summary_lbl.configure(text=f"📱 {launched_name} launched! Detecting ports in 8s...")
            self.after(8000, self.refresh_devices_and_config)
            self.after(16000, self.refresh_devices_and_config)
        else:
            self.status_summary_lbl.configure(text="⚠️ Emulator executable (MuMu/LDPlayer) not found!")

    def fix_and_restart_adb(self):
        """Fixes hung ADB server, clears offline devices, and reconnects emulators"""
        self.status_summary_lbl.configure(text="⚡ Restarting ADB server...")
        def _worker():
            optimize_runner.restart_adb_server()
            time.sleep(1)
            self.after(0, self.refresh_devices_and_config)
        threading.Thread(target=_worker, daemon=True).start()

    # =========================================================================
    # 💰 DEDICATED BALANCE CHECKER TAB METHODS
    # =========================================================================

    def _build_balance_tab(self, parent):
        """Constructs the dedicated Balance Checker Tab layout"""
        bal_header = ctk.CTkFrame(parent, fg_color="#161922", corner_radius=14, border_width=1, border_color="#232936")
        bal_header.pack(fill="x", padx=16, pady=(16, 10))

        # Row 1: Action Controls
        ctrl_row = ctk.CTkFrame(bal_header, fg_color="transparent")
        ctrl_row.pack(fill="x", padx=14, pady=(12, 6))

        self.btn_check_all_bal = ctk.CTkButton(
            ctrl_row,
            text="💰 Check All Balances",
            width=175,
            height=34,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#16a34a",
            hover_color="#15803d",
            command=self.check_all_balances
        )
        self.btn_check_all_bal.pack(side="left", padx=(0, 8))

        self.btn_stop_bal_check = ctk.CTkButton(
            ctrl_row,
            text="⏹ Stop Checking",
            width=130,
            height=34,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#dc2626",
            hover_color="#b91c1c",
            state="disabled",
            command=self.stop_balance_check
        )
        self.btn_stop_bal_check.pack(side="left", padx=8)

        self.btn_refresh_bal_accounts = ctk.CTkButton(
            ctrl_row,
            text="🔄 Refresh List",
            width=120,
            height=34,
            font=ctk.CTkFont(size=12),
            fg_color="#334155",
            hover_color="#475569",
            command=self.refresh_balance_accounts
        )
        self.btn_refresh_bal_accounts.pack(side="left", padx=8)

        self.bal_progress_lbl = ctk.CTkLabel(
            ctrl_row,
            text=f"Ready • {len(self.accounts)} Accounts loaded",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#38bdf8"
        )
        self.bal_progress_lbl.pack(side="left", padx=16)

        tip_lbl = ctk.CTkLabel(
            ctrl_row,
            text="⚡ Sends /start ➔ 💰 Balance (pure check, no emulators)",
            font=ctk.CTkFont(size=11),
            text_color="#64748b"
        )
        tip_lbl.pack(side="right", padx=(6, 2))

        # Row 2: Grand Total & Statistics Bar
        bal_stats_frame = ctk.CTkFrame(bal_header, fg_color="#0d1117", corner_radius=10, border_width=1, border_color="#1e293b")
        bal_stats_frame.pack(fill="x", padx=14, pady=(6, 12))

        self.bal_grand_total_badge = ctk.CTkLabel(
            bal_stats_frame,
            text="💵 Grand Total Balance: $0.0000",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#10b981",
            fg_color="#064e3b",
            corner_radius=8,
            padx=14,
            pady=6
        )
        self.bal_grand_total_badge.pack(side="left", padx=(10, 8), pady=6)

        self.bal_total_acc_badge = ctk.CTkLabel(
            bal_stats_frame,
            text=f"👥 Accounts: {len(self.accounts)}",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#93c5fd",
            fg_color="#1e3a8a",
            corner_radius=8,
            padx=10,
            pady=6
        )
        self.bal_total_acc_badge.pack(side="left", padx=6, pady=6)

        self.bal_checked_count_badge = ctk.CTkLabel(
            bal_stats_frame,
            text=f"✅ Checked: 0 / {len(self.accounts)}",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#fbbf24",
            fg_color="#302611",
            corner_radius=8,
            padx=10,
            pady=6
        )
        self.bal_checked_count_badge.pack(side="left", padx=6, pady=6)

        # 2. Scrollable Container for Accounts
        self.bal_scroll_container = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        self.bal_scroll_container.pack(fill="both", expand=True, padx=16, pady=(0, 16))

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
                on_check_balance=self.check_single_account_balance_async,
                dashboard=self
            )
            row.pack(fill="x", padx=4, pady=4)
            self.balance_rows[i] = row

        self.update_balance_tab_totals()

    def update_balance_tab_totals(self):
        """Updates Grand Total balance and checked count in the Balance Tab"""
        total_bal = sum(r.balance for r in self.balance_rows.values())
        checked_cnt = sum(1 for r in self.balance_rows.values() if r.last_checked_time != "Never")
        total_cnt = len(self.balance_rows)

        self.bal_grand_total_badge.configure(text=f"💵 Grand Total Balance: ${total_bal:.4f}")
        self.bal_total_acc_badge.configure(text=f"👥 Accounts: {total_cnt}")
        self.bal_checked_count_badge.configure(text=f"✅ Checked: {checked_cnt} / {total_cnt}")

    def check_single_account_balance_async(self, acc_index: int):
        """Asynchronously checks balance for a single account without blocking GUI"""
        threading.Thread(target=self._run_single_account_check, args=(acc_index,), daemon=True).start()

    def _run_single_account_check(self, acc_index: int):
        row = self.balance_rows.get(acc_index)
        if not row:
            return

        inst_id = acc_index + 1
        runner = self.worker_threads.get(inst_id)
        if runner and runner.is_alive() and not getattr(runner, "_is_stopped", False):
            self.after(0, lambda: row.set_status("Busy (Instance running)", "busy"))
            return

        self.after(0, lambda: row.set_checking_state(True))

        def status_cb(txt, col_type):
            self.after(0, lambda: row.set_status(txt, col_type))

        bal, err = check_single_account_balance_sync(row.account_info, status_cb=status_cb)
        t_now = datetime.now().strftime("%H:%M:%S")

        def _finish_ui():
            row.set_checking_state(False)
            if bal is not None:
                row.set_balance(bal, t_now)
                row.set_status("Success", "success")
                self.update_balance_tab_totals()

                if inst_id in self.instance_cards:
                    card = self.instance_cards[inst_id]
                    card.balance = bal
                    card.update_stats()
                    self.update_global_summary()
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

            inst_id = acc_idx + 1
            runner = self.worker_threads.get(inst_id)
            if runner and runner.is_alive() and not getattr(runner, "_is_stopped", False):
                self.after(0, lambda r=row: r.set_status("Busy (Instance running)", "busy"))
                continue

            self.after(0, lambda i=idx, p=row.phone: self.bal_progress_lbl.configure(
                text=f"Checking [{i+1}/{total_cnt}] {p}..."
            ))

            self.after(0, lambda r=row: r.set_checking_state(True))

            def status_cb(txt, col_type, r=row):
                self.after(0, lambda: r.set_status(txt, col_type))

            bal, err = check_single_account_balance_sync(row.account_info, status_cb=status_cb)
            t_now = datetime.now().strftime("%H:%M:%S")

            def _update_row(r=row, b=bal, e=err, ai=acc_idx):
                r.set_checking_state(False)
                if b is not None:
                    r.set_balance(b, t_now)
                    r.set_status("Success", "success")
                    self.update_balance_tab_totals()
                    iid = ai + 1
                    if iid in self.instance_cards:
                        card = self.instance_cards[iid]
                        card.balance = b
                        card.update_stats()
                        self.update_global_summary()
                else:
                    err_msg = e or "Failed"
                    color = "busy" if "busy" in err_msg.lower() else "error"
                    r.set_status(err_msg, color)

            self.after(0, _update_row)

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

        self.after(0, _cleanup)

    def refresh_balance_accounts(self):
        """Reloads accounts from config.json and updates Balance tab"""
        self.cfg = optimize_runner.load_config()
        self.accounts = self.cfg.get("telegram", {}).get("accounts", [])
        self._populate_balance_rows()
        self.bal_progress_lbl.configure(text=f"Refreshed • {len(self.accounts)} Accounts loaded")

    def sync_balance_to_tab(self, instance_id: int, balance: float):
        """Synchronizes balance update from active automation worker to Balance tab"""
        acc_idx = instance_id - 1
        if acc_idx in self.balance_rows:
            row = self.balance_rows[acc_idx]
            t_now = datetime.now().strftime("%H:%M:%S")
            row.set_balance(balance, t_now)
            row.set_status("Success", "success")
            self.update_balance_tab_totals()


def main():
    app = MultiInstanceDashboard()
    app.mainloop()


if __name__ == "__main__":
    main()
