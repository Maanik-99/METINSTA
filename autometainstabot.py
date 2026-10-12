#!/usr/bin/env python3
"""
=============================================================================
🤖 AUTOMETAINSTABOT - Complete Meta AI + Telegram Bot + Instagram 2FA Pipeline
=============================================================================
Combines:
  1. Telegram Userbot (Taskly / PayGoeasy):
     - Automates task receiving from Telegram bot (@Taskl1_bot / @PayGoeasy_bot)
     - Fetches First Name, Username, and Password directly from the Telegram bot
     - Submits 2FA Secret Key & confirms completed task to Telegram bot
  2. TempMail Ninja (NINJA.PY):
     - Real-time Socket.IO disposable email generation
     - Automated real-time push notification & OTP code extraction
  3. Meta Auth Pure Request Engine (meta with otp.py):
     - Envelope AES-256-GCM + TweetNaCl SealedBox password encryption
     - Fast HTTP request registration on auth.meta.com (Contact point, Password, DOB, Handle check, Registration)
     - Automated GraphQL OTP confirmation (FRLConfirmEmailMutation)
  4. Playwright Stealth Handover:
     - Session cookie injection for checkpoint & human verification / 2Captcha solving
  5. Android ADB Instagram & 2FA Pipeline:
     - Automates Via browser on Android emulators
     - Instagram login, terms acceptance, account linking
     - 2FA secret key extraction, TOTP setup, Account center username sync
     - CSV (credentials.csv) & Google Sheets automatic synchronization
  6. Multi-Worker & Multi-Device Parallel Processing:
     - Supports concurrent workers across all active ADB emulators
=============================================================================
"""

import asyncio
import base64
import csv
import glob
import hashlib
import json
import os
import random
import re
import secrets
import shutil
import string
import subprocess
import sys
import threading
import time
import urllib.parse
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote, urlencode

import pyotp
import urllib3
import nacl.public
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

try:
    from curl_cffi import requests as curl_requests
    USE_CURL_CFFI = True
except ImportError:
    import requests as curl_requests
    USE_CURL_CFFI = False

import requests
import urllib.request
from urllib.parse import quote, urlencode, urlparse, parse_qs

try:
    from playwright.async_api import async_playwright, Playwright, BrowserContext, Page
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False
    Playwright = Any
    BrowserContext = Any
    Page = Any
from telethon import TelegramClient, events, errors
from telethon.tl.custom import Button

# QR Code Decoding for 2FA
try:
    import zxingcpp
except ImportError:
    zxingcpp = None

try:
    import cv2
except ImportError:
    cv2 = None

# Import TempMail Ninja API
try:
    from NINJA import TempMailNinjaAPI
    HAS_NINJA = True
except ImportError:
    try:
        from ninja import TempMailNinjaAPI
        HAS_NINJA = True
    except ImportError:
        HAS_NINJA = False

# Import Email Service & Config
from email_service import (
    generate_temp_email as fallback_generate_temp_email,
    fetch_otp_from_temp_mail as fallback_fetch_otp,
    mark_ninja_email_status,
    pop_ready_meta_account,
    mark_meta_account_status,
    replenish_ninja_pool,
    load_config,
    save_config,
    get_random_name,
    generate_custom_password,
    DEFAULT_CONFIG,
    CONFIG_FILE
)
from google_sheet_manager import gsheet_manager

urllib3.disable_warnings()

# Ensure safe terminal encoding on Windows
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

# ==============================================================================
# ⚙️ CONFIGURATION & SETTINGS (Loaded from config.json)
# ==============================================================================
_CFG = load_config()
_TG_CFG = _CFG.get("telegram", {})

# Auto Follow Suggested Accounts Setting (Default: True)
AUTO_FOLLOW_SUGGESTED = bool(_CFG.get("auto_follow_suggested", True))

def set_auto_follow_suggested(enabled: bool):
    global AUTO_FOLLOW_SUGGESTED
    AUTO_FOLLOW_SUGGESTED = bool(enabled)

# No Captcha / Skip Checkpoint Mode (Default: False)
SKIP_CAPTCHA = bool(_CFG.get("skip_captcha", False))

def set_skip_captcha(enabled: bool):
    global SKIP_CAPTCHA
    SKIP_CAPTCHA = bool(enabled)

def normalize_target_bots(val):
    if isinstance(val, list):
        bots = [str(b).strip().lstrip("@") for b in val if str(b).strip()]
        return bots if bots else ["Taskl1_bot", "RealEarningBangladesh_Bot"]
    elif isinstance(val, str) and val.strip():
        bots = [str(b).strip().lstrip("@") for b in val.split(",") if str(b).strip()]
        return bots if bots else ["Taskl1_bot", "RealEarningBangladesh_Bot"]
    return ["Taskl1_bot", "RealEarningBangladesh_Bot"]

# Target Telegram bots
TARGET_BOTS = normalize_target_bots(_TG_CFG.get("target_bot") or _TG_CFG.get("target_bots"))
TARGET_BOT = TARGET_BOTS[0] if TARGET_BOTS else "Taskl1_bot"

# Telegram accounts
TELEGRAM_ACCOUNTS = _TG_CFG.get("accounts", [])
for _acc in TELEGRAM_ACCOUNTS:
    raw_acc_bots = _acc.get("target_bots") or _acc.get("target_bot") or TARGET_BOTS
    _acc["target_bots"] = normalize_target_bots(raw_acc_bots)
    _acc["target_bot"] = _acc["target_bots"][0]

def get_only_meta_password() -> str:
    """Dynamically reads and sanitizes the Only Meta password from config.json."""
    try:
        fresh_cfg = load_config()
        pwd = (
            fresh_cfg.get("only_meta_password")
            or fresh_cfg.get("telegram", {}).get("only_meta_password")
            or _CFG.get("only_meta_password")
            or _TG_CFG.get("only_meta_password")
            or "saikat50968"
        )
        pwd = re.sub(r"[`'\"*]", "", str(pwd)).strip()
        return pwd or "saikat50968"
    except Exception:
        return "saikat50968"

# ==============================================================================
# 🔄 GLOBAL TELEGRAM ACCOUNT POOL & FLOOD COOLDOWN MANAGER
# ==============================================================================
class TelegramAccountPool:
    _lock = threading.Lock()
    _active_accounts: Dict[str, str] = {}      # clean_phone -> instance_name
    _assigned_accounts: Dict[str, str] = {}    # clean_phone -> instance_name (Dedicated emulator mapping)
    _flood_cooldowns: Dict[str, float] = {}    # clean_phone -> unix timestamp
    _all_accounts: List[dict] = []

    @classmethod
    def initialize(cls, accounts: list):
        with cls._lock:
            cls._all_accounts = list(accounts)

    @classmethod
    def set_assigned_accounts(cls, mapping: Dict[str, str]):
        """Sets dedicated instance -> phone mappings so accounts never interfere across emulators."""
        with cls._lock:
            cls._assigned_accounts = {
                re.sub(r'[^0-9]', '', str(p)): inst
                for inst, p in mapping.items() if p
            }

    @classmethod
    def set_assigned_account(cls, phone: str, instance_name: str):
        if not phone:
            return
        with cls._lock:
            clean = re.sub(r'[^0-9]', '', str(phone))
            cls._assigned_accounts[clean] = instance_name

    @classmethod
    def is_account_busy(cls, phone: str, instance_name: str) -> Tuple[bool, str]:
        """Checks if account is currently active on another running emulator."""
        if not phone:
            return False, ""
        with cls._lock:
            clean = re.sub(r'[^0-9]', '', str(phone))
            occupant = cls._active_accounts.get(clean)
            if occupant and occupant != instance_name:
                return True, occupant
            return False, ""

    @classmethod
    def register_active(cls, phone: str, instance_name: str):
        if not phone:
            return
        with cls._lock:
            clean = re.sub(r'[^0-9]', '', str(phone))
            cls._active_accounts[clean] = instance_name

    @classmethod
    def release_active(cls, phone: str):
        if not phone:
            return
        with cls._lock:
            clean = re.sub(r'[^0-9]', '', str(phone))
            if clean in cls._active_accounts:
                del cls._active_accounts[clean]

    @classmethod
    def mark_flood(cls, phone: str, seconds: int):
        if not phone:
            return
        with cls._lock:
            clean = re.sub(r'[^0-9]', '', str(phone))
            cls._flood_cooldowns[clean] = time.time() + seconds

    @classmethod
    def is_cooling_down(cls, phone: str) -> bool:
        if not phone:
            return False
        with cls._lock:
            clean = re.sub(r'[^0-9]', '', str(phone))
            return time.time() < cls._flood_cooldowns.get(clean, 0.0)

    @classmethod
    def get_cooldown_remaining(cls, phone: str) -> int:
        if not phone:
            return 0
        with cls._lock:
            clean = re.sub(r'[^0-9]', '', str(phone))
            rem = int(cls._flood_cooldowns.get(clean, 0.0) - time.time())
            return max(0, rem)

    @classmethod
    def find_free_account(cls, current_phone: str, instance_name: str) -> Optional[dict]:
        with cls._lock:
            curr_clean = re.sub(r'[^0-9]', '', str(current_phone)) if current_phone else ""
            now = time.time()
            for acc in cls._all_accounts:
                acc_phone = re.sub(r'[^0-9]', '', str(acc.get('phone', '')))
                if not acc_phone or acc_phone == curr_clean:
                    continue
                # If account is assigned to another emulator instance, NEVER take it!
                assigned_owner = cls._assigned_accounts.get(acc_phone)
                if assigned_owner and assigned_owner != instance_name:
                    continue
                # If account is currently in FloodWait cooldown, skip
                if cls._flood_cooldowns.get(acc_phone, 0.0) > now:
                    continue
                # If account is currently in use by another running emulator, skip
                occupant = cls._active_accounts.get(acc_phone)
                if occupant and occupant != instance_name:
                    continue
                return acc
            return None

TelegramAccountPool.initialize(TELEGRAM_ACCOUNTS)

AUTO_REPEAT_TASKS = _TG_CFG.get("auto_repeat_tasks", True)
DELAY_BETWEEN_STEPS = _TG_CFG.get("delay_between_steps", 2.0)

# Meta AI & URLs
TARGET_URL = "https://www.meta.ai/"
CHECKPOINT_REDIRECT_URL = "https://auth.meta.com/checkpoints/675270400317265/?next=https%3A%2F%2Fauth.meta.com%2Frecover%2Fsuccess%2F%3Fredirect_uri%3Dhttps%253A%252F%252Fauth.meta.com%252F"

# Browser settings
HEADLESS = _CFG.get("headless", False)

def set_headless(val: bool):
    global HEADLESS
    HEADLESS = bool(val)
    _CFG["headless"] = HEADLESS
VIEWPORT_WIDTH = _CFG.get("viewport_width", 500)
VIEWPORT_HEIGHT = _CFG.get("viewport_height", 700)
PACKAGE_NAME = "mark.via.gp"

INSTA_LOGIN_URL = "https://www.instagram.com/accounts/login/?"
TWO_FACTOR_URL = "https://accountscenter.instagram.com/password_and_security/two_factor/"
ACCOUNTS_OVERVIEW_URL = "https://accountscenter.instagram.com/account_overview/"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if os.getcwd() != BASE_DIR:
    try:
        os.chdir(BASE_DIR)
    except Exception:
        pass
CREDENTIALS_CSV = os.path.join(BASE_DIR, "credentials.csv")

# ==============================================================================
# 🧩 2CAPTCHA & CHECKPOINT API CONFIGURATION
# ==============================================================================
_CAPTCHA_CFG = _CFG.get("captcha", {})
API_KEY_2CAPTCHA = _CAPTCHA_CFG.get("api_key") or "1d0543cab02e928f092f4f24736efd85"
DEFAULT_RECAPTCHA_SITE_KEY = _CAPTCHA_CFG.get("site_key") or "6LdktRgnAAAAAFQ6icovYI2-masYLFjEFyzQzpix"
CAPTCHA_TIMEOUT = int(_CAPTCHA_CFG.get("timeout", 120))
DOC_ID_CONFIRM_EMAIL = "9851798224911796"
DOC_ID_UFAC_CHECKPOINT = "28029617096670386"
DEFAULT_IMAGE_PATH = os.path.join(BASE_DIR, "image.jpg")


csv_lock = threading.Lock()
ADB_SEMAPHORE = threading.Semaphore(4)
CLIENT_CACHE: Dict[str, TelegramClient] = {}

# ==============================================================================
# 📝 LOGGING
# ==============================================================================
LOG_CALLBACK = None

def set_log_callback(cb):
    global LOG_CALLBACK
    LOG_CALLBACK = cb

def log(tag, message, instance_name=""):
    timestamp = time.strftime("%H:%M:%S")
    inst_tag = f"[{instance_name:^8}]" if instance_name else "[  MAIN  ]"
    tag_padded = f"[{tag:<14}]"
    log_str = f"[{timestamp}] {inst_tag} {tag_padded} {message}"
    try:
        print(log_str, flush=True)
    except UnicodeEncodeError:
        safe_str = log_str.encode(sys.stdout.encoding or 'ascii', errors='replace').decode(sys.stdout.encoding or 'ascii')
        print(safe_str, flush=True)
    if LOG_CALLBACK:
        try:
            LOG_CALLBACK(tag, message, instance_name)
        except Exception:
            pass

# ==============================================================================
# 💾 CREDENTIAL STORAGE & GOOGLE SHEETS
# ==============================================================================
def save_credentials_csv(email, password, two_factor_secret="", username="", instance_name="", status="ACTIVE_2FA", cookies=""):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    uname = username.strip() if username else "Instagram_User"
    if cookies and two_factor_secret:
        secret_or_cookies = f"2FA: {two_factor_secret} | Cookies: {cookies}"
        st = status if status else "ACTIVE_2FA_COOKIES"
    else:
        secret_or_cookies = cookies if cookies else two_factor_secret
        st = status if status else ("ACTIVE_COOKIES" if cookies else "ACTIVE_2FA")
    
    with csv_lock:
        file_exists = os.path.exists(CREDENTIALS_CSV)
        try:
            with open(CREDENTIALS_CSV, mode='a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(["Timestamp", "Email", "Username", "Password", "2FA / Cookies", "Status"])
                writer.writerow([timestamp, email, uname, password, secret_or_cookies, st])
            log("CSV-SAVE", f"Saved credentials for {email} ({uname}) to credentials.csv", instance_name=instance_name)
        except Exception as e:
            log("CSV-ERR", f"Failed saving to credentials.csv: {e}", instance_name=instance_name)

    if gsheet_manager.is_configured():
        def _save_gsheet():
            try:
                gsheet_manager.save_done_account(timestamp, email, uname, password, secret_or_cookies, instance_name=instance_name)
            except Exception as e:
                log("GSHEET-ERR", f"Failed syncing to Google Sheet: {e}", instance_name=instance_name)
        threading.Thread(target=_save_gsheet, daemon=True).start()

# ==============================================================================
# 🔐 META AUTH CRYPTO & REQUEST CLIENT
# ==============================================================================

def format_pwd_browser(encrypted_b64: str, timestamp: Optional[int] = None, version: int = 5) -> str:
    """Formats password in Meta browser format: #PWD_BROWSER:<ver>:<ts>:<payload>"""
    ts = timestamp or int(time.time())
    return f"#PWD_BROWSER:{version}:{ts}:{encrypted_b64}"

def encrypt_meta_password(
    password: str,
    public_key_hex: str,
    key_id: int = 199,
    timestamp: Optional[int] = None
) -> str:
    """
    Encrypts password using Meta's EnvelopeEncryption standard:
    1. Ephemeral 32-byte AES-256 key.
    2. AES-256-GCM encryption with 12 zero IV bytes and timestamp AAD.
    3. TweetNaCl SealedBox encryption with Meta's X25519 public key.
    4. Meta binary envelope pack.
    """
    ts = timestamp or int(time.time())
    ts_str = str(ts)

    aes_key = os.urandom(32)
    iv = bytes(12)
    aesgcm = AESGCM(aes_key)
    aad = ts_str.encode("utf-8")
    plaintext = password.encode("utf-8")

    ciphertext_and_tag = aesgcm.encrypt(iv, plaintext, aad)
    ciphertext = ciphertext_and_tag[:-16]
    tag = ciphertext_and_tag[-16:]

    recipient_pk_bytes = bytes.fromhex(public_key_hex)
    recipient_pk = nacl.public.PublicKey(recipient_pk_bytes)
    sealed_box = nacl.public.SealedBox(recipient_pk)
    sealed_key = sealed_box.encrypt(aes_key)
    sealed_len = len(sealed_key)

    envelope = bytearray()
    envelope.append(1)                  # Version = 1
    envelope.append(int(key_id))        # Key ID
    envelope.append(sealed_len & 0xFF)  # Length low byte
    envelope.append((sealed_len >> 8) & 0xFF)  # Length high byte
    envelope.extend(sealed_key)
    envelope.extend(tag)
    envelope.extend(ciphertext)

    b64_payload = base64.b64encode(envelope).decode("utf-8")
    return format_pwd_browser(b64_payload, timestamp=ts)

def compute_jazoest(token: str) -> str:
    """Computes Meta dynamic jazoest checksum from LSD or fb_dtsg."""
    if not token:
        return "22206"
    return "2" + str(sum(ord(c) for c in token))

def build_falco_payload(
    event_name: str,
    event_data: Dict[str, Any],
    client_session_id: str,
    web_session_id: str = "npdr3i:q5lguu:55za44",
    claim: str = "hmac_ttl.1789134777.AR1GWI4H8HqheGesK9mJOlXPT5j4lcjCd4vFk0DAT3lhNJOv"
) -> Tuple[str, str]:
    now_ms = time.time() * 1000
    post_item = [
        event_name,
        {
            "e": json.dumps(event_data),
            "r": 1,
            "d": "fd.ARvsnj8V0mnfNo2m10abybzPIxHOsKjvFZTY6hCzdfR5bSZczDsdeGF6Q55k3ROaFJ2oCMsf8z_TGy97tRAQzjXy",
            "s": web_session_id,
            "t": now_ms,
            "a": "1047.303.469.0 (1047303469)",
            "b": [1, 128],
            "id": {
                "appScopedIdentity": "0",
                "claim": claim
            }
        },
        now_ms,
        0,
        1200
    ]

    q_array = [
        {
            "app_id": "713378262994144",
            "posts": [post_item],
            "trigger": event_name,
            "user": "0",
            "webSessionId": web_session_id
        }
    ]
    return str(int(now_ms)), json.dumps(q_array)


# =====================================================================
# 🧩 2CAPTCHA SOLVER MODULE (Modern API + Legacy Fallback)
# =====================================================================
class TwoCaptchaSolver:
    """
    Automated 2Captcha solver for reCAPTCHA Enterprise on Meta / Facebook.
    Uses robust urllib and HTTP APIs with modern and legacy fallback.
    """
    DEFAULT_IFRAME_URL = "https://www.fbsbx.com/captcha/recaptcha/iframe/?transparent_bg=true&referer=https%253A%252F%252Fauth.meta.com&locale=en_GB"

    def __init__(self, api_key: Optional[str] = None):
        cfg = load_config()
        self.api_key = api_key or cfg.get("captcha", {}).get("api_key") or API_KEY_2CAPTCHA

    def get_balance(self) -> Optional[float]:
        try:
            resp = self._http_get_json(f"https://2captcha.com/res.php?key={self.api_key}&action=getbalance&json=1", timeout=10)
            if resp.get("status") == 1:
                return float(resp.get("request"))
        except Exception:
            pass
        return None

    def _http_post_json(self, url: str, data: dict, timeout: int = 25) -> dict:
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def _http_post_form(self, url: str, data: dict, timeout: int = 25) -> dict:
        req = urllib.request.Request(
            url,
            data=urlencode(data).encode("utf-8"),
            headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            text = response.read().decode("utf-8")
            try:
                return json.loads(text)
            except Exception:
                return {"status": 0, "request": text}

    def _http_get_json(self, url: str, timeout: int = 25) -> dict:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def solve_recaptcha_v2(
        self,
        site_key: str = DEFAULT_RECAPTCHA_SITE_KEY,
        page_url: str = DEFAULT_IFRAME_URL,
        max_retries: int = 3,
        max_wait_sec: int = CAPTCHA_TIMEOUT,
        instance_name: str = ""
    ) -> Optional[str]:
        # Dynamically reload latest API key if updated in config.json
        if not self.api_key:
            cfg = load_config()
            self.api_key = cfg.get("captcha", {}).get("api_key") or API_KEY_2CAPTCHA

        target_url = page_url or self.DEFAULT_IFRAME_URL

        for attempt in range(1, max_retries + 1):
            log("2CAPTCHA", f"Attempt {attempt}/{max_retries}: Submitting reCAPTCHA Enterprise to 2Captcha API...", instance_name)

            # 1. Primary: 2Captcha Enterprise Legacy API (fastest & most reliable for enterprise=1)
            try:
                in_resp = self._http_post_form(
                    "https://2captcha.com/in.php",
                    {
                        "key": self.api_key,
                        "method": "userrecaptcha",
                        "googlekey": site_key,
                        "pageurl": target_url,
                        "enterprise": 1,
                        "json": 1
                    }
                )
                if in_resp.get("request") == "ERROR_ZERO_BALANCE":
                    log("2CAPTCHA-ERR", "🚨 2Captcha balance is ZERO or negative ($0.00)! Please top up your 2Captcha account balance.", instance_name)
                    return None
                if in_resp.get("request") == "ERROR_KEY_DOES_USER_KEY_NOT_EXIST":
                    log("2CAPTCHA-ERR", "🚨 Invalid 2Captcha API Key! Please verify config.json.", instance_name)
                    return None

                if in_resp.get("status") == 1:
                    captcha_id = in_resp.get("request")
                    log("2CAPTCHA", f"Task created (ID: {captcha_id}). Polling solution...", instance_name)
                    start_time = time.time()
                    time.sleep(5)

                    while time.time() - start_time < max_wait_sec:
                        res_resp = self._http_get_json(
                            f"https://2captcha.com/res.php?key={self.api_key}&action=get&id={captcha_id}&json=1"
                        )
                        elapsed = int(time.time() - start_time)
                        if res_resp.get("status") == 1:
                            token = res_resp.get("request")
                            log("2CAPTCHA-OK", f"🎉 Captcha solved in {elapsed}s via 2Captcha!", instance_name)
                            return token
                        elif res_resp.get("request") == "CAPCHA_NOT_READY":
                            log("2CAPTCHA", f"⏳ Polling 2Captcha solution (Task {captcha_id})... ({elapsed}s elapsed)", instance_name)
                        else:
                            log("2CAPTCHA-WARN", f"Legacy response: {res_resp}", instance_name)
                            break
                        time.sleep(5)
            except Exception as e:
                log("2CAPTCHA-WARN", f"Legacy API error: {e}", instance_name)

            # 2. Modern API Fallback
            try:
                create_resp = self._http_post_json(
                    "https://api.2captcha.com/createTask",
                    {
                        "clientKey": self.api_key,
                        "task": {
                            "type": "RecaptchaV2EnterpriseTaskProxyless",
                            "websiteURL": target_url,
                            "websiteKey": site_key
                        }
                    }
                )

                if create_resp.get("errorCode") == "ERROR_ZERO_BALANCE":
                    log("2CAPTCHA-ERR", "🚨 2Captcha balance is ZERO or negative ($0.00)! Please top up your 2Captcha account balance.", instance_name)
                    return None

                if create_resp.get("errorId") == 0 and "taskId" in create_resp:
                    task_id = create_resp["taskId"]
                    log("2CAPTCHA", f"Modern Task ID: {task_id}. Polling solution...", instance_name)
                    start_time = time.time()
                    time.sleep(5)

                    while time.time() - start_time < max_wait_sec:
                        poll = self._http_post_json(
                            "https://api.2captcha.com/getTaskResult",
                            {"clientKey": self.api_key, "taskId": task_id}
                        )
                        elapsed = int(time.time() - start_time)
                        if poll.get("status") == "ready":
                            token = poll.get("solution", {}).get("gRecaptchaResponse")
                            log("2CAPTCHA-OK", f"🎉 Captcha solved in {elapsed}s via Modern API!", instance_name)
                            return token
                        elif poll.get("status") == "processing":
                            log("2CAPTCHA", f"⏳ Polling Modern Task {task_id}... ({elapsed}s elapsed)", instance_name)
                        else:
                            log("2CAPTCHA-WARN", f"Task poll status: {poll}", instance_name)
                            break
                        time.sleep(5)
            except Exception as e:
                log("2CAPTCHA-WARN", f"Modern API error: {e}", instance_name)

            log("2CAPTCHA-WARN", f"Attempt {attempt} failed, retrying in 3s...", instance_name)
            time.sleep(3)

        return None

def get_random_verification_image() -> str:
    """Finds a random selfie/verification photo from images/ directory."""
    cand_dirs = [
        os.path.join(BASE_DIR, "images"),
        os.path.join(os.path.dirname(BASE_DIR), "images"),
        BASE_DIR
    ]
    all_imgs = []
    for d in cand_dirs:
        if os.path.exists(d) and os.path.isdir(d):
            for ext in ["*.jpg", "*.jpeg", "*.png"]:
                all_imgs.extend(glob.glob(os.path.join(d, ext)))
    if all_imgs:
        return random.choice(all_imgs)

    for cand in ["image.jpg", "image.jpeg", "image.png"]:
        p = os.path.join(BASE_DIR, cand)
        if os.path.exists(p):
            return p
    return ""

class MetaAuthClient:
    """
    Automates fast pure-HTTP request registration on auth.meta.com.
    """
    BASE_URL = "https://auth.meta.com"
    SOURCE_APP_ID = "1522763855472543"
    TOS_CMS_ID = "957798449862312"

    def __init__(self, proxy: Optional[str] = None, impersonate: str = "chrome124", instance_name: str = "", captcha_api_key: str = API_KEY_2CAPTCHA):
        self.instance_name = instance_name
        self.session = curl_requests.Session(impersonate=impersonate) if USE_CURL_CFFI else curl_requests.Session()
        self.captcha_solver = TwoCaptchaSolver(api_key=captcha_api_key)
        self.checkpoint_url: Optional[str] = None
        if proxy:
            self.session.proxies = {"http": proxy, "https": proxy}

        self.waterfall_id = str(uuid.uuid4())
        self.client_session_id = self._generate_client_session_id()
        self.device_id: Optional[str] = None
        self.email: Optional[str] = None
        self.req_counter = 1

        self.code_verifier = self._generate_client_session_id() + self._generate_client_session_id()
        self.code_challenge = self._generate_code_challenge(self.code_verifier)
        self.oidc_redirect_uri = self._build_oidc_redirect_uri()

        self.lsd: Optional[str] = None
        self.jazoest: Optional[str] = None
        self.public_key: Optional[str] = None
        self.key_id: int = 199
        self.rcs: Optional[str] = None
        self.jurisdiction: str = "BD"
        self.reg_integrity: Optional[str] = None
        self.fb_dtsg: Optional[str] = None
        self.created_user_id: Optional[str] = None

        self.rev = "1047303469"
        self.hsi = "7684275360328234786"
        self.hs = "20707.HYP:frl_comet_auth_pkg.2.1...0"
        self.s = "npdr3i:q5lguu:55za44"
        self.spin_r = "1047303469"
        self.spin_b = "trunk"
        self.spin_t = "1789134777"
        self.dyn = "7xe6E5aQ1Py8s-3eaQ412nwvG1Ww4KwhE2LwFwn82nwb-q2i5U4e1FxO0SE2Bw46wrU6C0AU1OU1vE2Yw45w43w16-0Co5G0zE1AE17U1eE1ko38w4mw4ewCw3mE1hE3Pw"
        self.csr = ""
        self.hsdp = ""
        self.hblp = ""
        self.sjsp = ""

        self._init_default_headers()

    def _generate_client_session_id(self) -> str:
        chars = string.ascii_letters + string.digits + "_-"
        return "".join(random.choices(chars, k=24))

    def _generate_code_challenge(self, verifier: str) -> str:
        digest = hashlib.sha256(verifier.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")

    def _build_oidc_redirect_uri(self) -> str:
        state_payload = {
            "csrf_token": self._generate_client_session_id() + "-" + self._generate_client_session_id(),
            "redirect_to": "https://meta.ai/oidc/callback",
            "started_at": int(time.time() * 1000),
            "waterfall_id": self.waterfall_id
        }
        state_b64 = base64.b64encode(json.dumps(state_payload).encode("utf-8")).decode("utf-8")

        params = {
            "app_id": self.SOURCE_APP_ID,
            "redirect_uri": "https://auth.meta.ai/ecto",
            "response_type": "code",
            "scope": "openid linking",
            "state": state_b64,
            "waterfall_id": self.waterfall_id,
            "code_challenge": self.code_challenge,
            "code_challenge_method": "S256"
        }
        return f"{self.BASE_URL}/oidc/?{urlencode(params)}"

    def _get_cookie(self, name: str) -> str:
        try:
            if hasattr(self.session.cookies, "get_dict"):
                return self.session.cookies.get_dict().get(name, "")
            return self.session.cookies.get(name, domain=".meta.com") or ""
        except Exception:
            return ""

    def _generate_qpl_join_id(self) -> str:
        return "f" + uuid.uuid4().hex[:16]

    def _next_req(self) -> str:
        val = hex(self.req_counter)[2:]
        self.req_counter += 1
        return val

    def _get_current_referer(self) -> str:
        ref = (
            f"{self.BASE_URL}/?waterfall_id={self.waterfall_id}"
            f"&redirect_uri={quote(self.oidc_redirect_uri)}"
            f"&source_app_id={self.SOURCE_APP_ID}&force_reauth=0"
        )
        if self.rcs:
            ref += f"&rcs={self.rcs}"
        return ref

    def _init_default_headers(self):
        self.session.headers.update({
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9",
            "origin": self.BASE_URL,
            "referer": self._get_current_referer(),
            "sec-ch-prefers-color-scheme": "dark",
            "sec-ch-ua": '"Chromium";v="124", "Not?A_Brand";v="24", "Google Chrome";v="124"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "x-asbd-id": "359341",
        })

    def _get_base_spin_params(self) -> Dict[str, Any]:
        token_for_jazoest = self.fb_dtsg if self.fb_dtsg else (self.lsd or "AdS4dILcliXDKFeDHlE3nhTH-OQ")
        jazoest_val = compute_jazoest(token_for_jazoest)

        params = {
            "__user": "0",
            "__a": "1",
            "__req": self._next_req(),
            "__hs": self.hs,
            "dpr": "1",
            "__ccg": "GOOD",
            "__rev": self.rev,
            "__s": self.s,
            "__hsi": self.hsi,
            "__dyn": self.dyn,
            "__csr": self.csr,
            "__hsdp": self.hsdp,
            "__hblp": self.hblp,
            "__sjsp": self.sjsp,
            "__comet_req": "33",
            "lsd": self.lsd or "AdS4dILcliXDKFeDHlE3nhTH-OQ",
            "jazoest": jazoest_val,
            "__spin_r": self.spin_r,
            "__spin_b": self.spin_b,
            "__spin_t": self.spin_t,
            "__jssesw": "1",
        }
        if self.fb_dtsg:
            params["fb_dtsg"] = self.fb_dtsg
        return params

    def init_session(self, oidc_redirect_uri: Optional[str] = None) -> bool:
        """Step 1: Load landing page to capture datr, LSD, public key, key ID, and rcs."""
        log("REQ-INIT", "Initializing Meta Auth request session...", self.instance_name)
        landing_url = f"{self.BASE_URL}/"
        if oidc_redirect_uri:
            self.oidc_redirect_uri = oidc_redirect_uri

        params = {
            "waterfall_id": self.waterfall_id,
            "redirect_uri": self.oidc_redirect_uri,
            "source_app_id": self.SOURCE_APP_ID,
            "force_reauth": "0"
        }

        doc_headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "none",
            "sec-fetch-user": "?1",
            "upgrade-insecure-requests": "1",
        }

        try:
            resp = self.session.get(landing_url, params=params, headers=doc_headers)
            text = resp.text

            if "rcs=" in resp.url:
                self.rcs = resp.url.split("rcs=")[-1].split("&")[0]

            lsd_match = re.search(r'\["LSD",\[\],\{"token":"([^"]+)"\}', text)
            if not lsd_match:
                lsd_match = re.search(r'name="lsd"\s+value="([^"]+)"', text)
            if lsd_match:
                self.lsd = lsd_match.group(1)
                self.jazoest = compute_jazoest(self.lsd)

            pk_match = re.search(r'publicKey":"([a-f0-9]{64})"', text)
            if pk_match:
                self.public_key = pk_match.group(1)
            key_id_match = re.search(r'keyId":(\d+)', text)
            if key_id_match:
                self.key_id = int(key_id_match.group(1))

            juris_match = re.search(r'regulation_jurisdiction":\["([^"]+)"\]', text)
            if juris_match:
                self.jurisdiction = juris_match.group(1)

            self.session.headers["referer"] = self._get_current_referer()
            log("REQ-INIT", f"Session Ready! LSD: {self.lsd} | KeyID: {self.key_id} | Juris: {self.jurisdiction}", self.instance_name)
            return True
        except Exception as e:
            log("REQ-ERR", f"Failed initializing auth session: {e}", self.instance_name)
            return False

    def _safe_request(self, method: str, url: str, **kwargs) -> Any:
        if "timeout" not in kwargs:
            kwargs["timeout"] = 25
        for attempt in range(1, 4):
            try:
                if method.lower() == "get":
                    return self.session.get(url, **kwargs)
                else:
                    return self.session.post(url, **kwargs)
            except Exception as e:
                log("REQ-RETRY", f"Network delay/retry on {url} (attempt {attempt}/3): {e}", instance_name=self.instance_name)
                if attempt < 3:
                    time.sleep(1.5 * attempt)
                else:
                    raise e

    def init_session(self, oidc_redirect_uri: Optional[str] = None) -> bool:
        """Step 1: Load landing page to capture datr, LSD, public key, key ID, and rcs."""
        log("REQ-INIT", "Initializing Meta Auth request session...", self.instance_name)
        landing_url = f"{self.BASE_URL}/"
        if oidc_redirect_uri:
            self.oidc_redirect_uri = oidc_redirect_uri

        params = {
            "waterfall_id": self.waterfall_id,
            "redirect_uri": self.oidc_redirect_uri,
            "source_app_id": self.SOURCE_APP_ID,
            "force_reauth": "0"
        }

        doc_headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "none",
            "sec-fetch-user": "?1",
            "upgrade-insecure-requests": "1",
        }

        try:
            resp = self._safe_request("get", landing_url, params=params, headers=doc_headers)
            text = resp.text

            if "rcs=" in resp.url:
                self.rcs = resp.url.split("rcs=")[-1].split("&")[0]

            lsd_match = re.search(r'\["LSD",\[\],\{"token":"([^"]+)"\}', text)
            if not lsd_match:
                lsd_match = re.search(r'name="lsd"\s+value="([^"]+)"', text)
            if lsd_match:
                self.lsd = lsd_match.group(1)
                self.jazoest = compute_jazoest(self.lsd)

            pk_match = re.search(r'publicKey":"([a-f0-9]{64})"', text)
            if pk_match:
                self.public_key = pk_match.group(1)
            key_id_match = re.search(r'keyId":(\d+)', text)
            if key_id_match:
                self.key_id = int(key_id_match.group(1))

            juris_match = re.search(r'regulation_jurisdiction":\["([^"]+)"\]', text)
            if juris_match:
                self.jurisdiction = juris_match.group(1)

            self.session.headers["referer"] = self._get_current_referer()
            log("REQ-INIT", f"Session Ready! LSD: {self.lsd} | KeyID: {self.key_id} | Juris: {self.jurisdiction}", self.instance_name)
            return True
        except Exception as e:
            log("REQ-ERR", f"Failed initializing auth session: {e}", self.instance_name)
            return False

    def encrypt_password(self, password: str, timestamp: Optional[int] = None) -> str:
        pk = self.public_key or "19c30cf2379e56b8ab368d6f2479cb893a09a023db2d062b2686bb8761881e47"
        return encrypt_meta_password(password=password, public_key_hex=pk, key_id=self.key_id, timestamp=timestamp)

    def check_contact_point_availability(self, email: str) -> Dict[str, Any]:
        """Step 2: Check contact point availability."""
        log("REQ-CP", f"Checking availability for: {email}", self.instance_name)
        self.email = email
        url = f"{self.BASE_URL}/api/check-contact-point-availability/"
        data = {
            "allow_fallback": "true",
            "caa_event_flow": "ntm",
            "contact_point": email,
            "contact_point_type": "EMAIL_ADDRESS",
            "device_id": "",
            "enable_youth_consent_flow": "true",
            "entry_point": "login_home",
            "event_client_time": f"{time.time():.2f}",
            "google_id_token": "",
            "has_youth_consent": "false",
            "is_bootstrap_flow": "false",
            "is_kadabra_zero": "false",
            "qpl_join_id": self._generate_qpl_join_id(),
            "reg_navigation_flow_name": "new_to_family_c50_r1",
            "regulation_jurisdiction": json.dumps([self.jurisdiction]),
            "source_app_id": self.SOURCE_APP_ID,
            "waterfall_id": self.waterfall_id,
        }
        data.update(self._get_base_spin_params())

        headers = {
            "content-type": "application/x-www-form-urlencoded",
            "referer": self._get_current_referer(),
        }

        resp = self._safe_request("post", url, data=data, headers=headers)
        parsed = self._parse_fb_response(resp.text)

        if isinstance(parsed, dict) and "payload" in parsed:
            payload = parsed.get("payload")
            if isinstance(payload, dict):
                reg_int = payload.get("regIntegrity") or payload.get("reg_integrity")
                if reg_int:
                    self.reg_integrity = reg_int

                restrictions = payload.get("restrictions")
                if isinstance(restrictions, dict):
                    res_data = restrictions.get("restriction_data")
                    if isinstance(res_data, dict):
                        reg_info = res_data.get("account_reg_info")
                        if isinstance(reg_info, dict) and "device_id" in reg_info:
                            self.device_id = reg_info["device_id"]

                if "contactPoint" in payload and payload["contactPoint"]:
                    self.email = payload["contactPoint"]

        return parsed

    def check_password(self, email: str, password_raw_or_payload: str, dob: str = "2000-01-01") -> Dict[str, Any]:
        """Step 3: Check password validity."""
        url = f"{self.BASE_URL}/api/check-password/"
        if password_raw_or_payload.startswith("#PWD_BROWSER:"):
            password_payload = password_raw_or_payload
        else:
            password_payload = self.encrypt_password(password_raw_or_payload)

        data = {
            "contact_point": email,
            "date_of_birth": dob,
            "name": "",
            "password": password_payload,
            "contact_pointless_account": "false",
            "qpl_join_id": self._generate_qpl_join_id(),
        }
        data.update(self._get_base_spin_params())

        headers = {
            "content-type": "application/x-www-form-urlencoded",
            "referer": self._get_current_referer(),
        }
        resp = self._safe_request("post", url, data=data, headers=headers)
        return self._parse_fb_response(resp.text)

    def check_date_of_birth(self, email: str, dob: str = "2000-01-01", first_name: str = "", last_name: str = "") -> Dict[str, Any]:
        """Step 4: Check date of birth."""
        url = f"{self.BASE_URL}/api/check-date-of-birth/"
        data = {
            "caa_event_flow": "ntm",
            "date_of_birth": dob,
            "email": email,
            "first_name": first_name or "",
            "has_youth_consent": "false",
            "isf": "false",
            "last_name": last_name or "",
            "phone_number": "",
            "qpl_join_id": self._generate_qpl_join_id(),
            "reg_integrity": self.reg_integrity or "",
            "source_app_id": self.SOURCE_APP_ID,
        }
        data.update(self._get_base_spin_params())

        headers = {
            "content-type": "application/x-www-form-urlencoded",
            "referer": self._get_current_referer(),
        }
        resp = self._safe_request("post", url, data=data, headers=headers)
        parsed = self._parse_fb_response(resp.text)
        if isinstance(parsed, dict) and "payload" in parsed:
            payload = parsed.get("payload")
            if isinstance(payload, dict):
                reg_int = payload.get("regIntegrity") or payload.get("reg_integrity")
                if reg_int:
                    self.reg_integrity = reg_int
        return parsed

    def suggest_username(self) -> Dict[str, Any]:
        """Step 5: Suggest Kadabra username."""
        url = f"{self.BASE_URL}/api/kadabra/suggest_username/"
        data = {
            "caa_event_flow": "ntm",
            "device_id": self.device_id or "",
            "first_name": "",
            "last_name": "",
            "qpl_join_id": self._generate_qpl_join_id(),
            "reg_integrity": self.reg_integrity or "",
            "source_app_id": self.SOURCE_APP_ID,
            "waterfall_id": self.waterfall_id,
        }
        data.update(self._get_base_spin_params())

        headers = {
            "content-type": "application/x-www-form-urlencoded",
            "referer": self._get_current_referer(),
        }
        resp = self._safe_request("post", url, data=data, headers=headers)
        return self._parse_fb_response(resp.text)

    def check_profile(self, username: str) -> Dict[str, Any]:
        """Step 6: Confirm username availability and TOS agreement."""
        url = f"{self.BASE_URL}/api/kadabra/check_profile/"
        data = {
            "caa_event_flow": "ntm",
            "display_name": "",
            "foa_import_source_name": "",
            "foa_import_source_obid": "",
            "nta_disclosures_summary_cms_id": "",
            "picture_source": "",
            "qpl_join_id": self._generate_qpl_join_id(),
            "tos_cms_id": self.TOS_CMS_ID,
            "username": username,
        }
        data.update(self._get_base_spin_params())

        headers = {
            "content-type": "application/x-www-form-urlencoded",
            "referer": self._get_current_referer(),
        }
        resp = self._safe_request("post", url, data=data, headers=headers)
        return self._parse_fb_response(resp.text)

    def register_save_credentials(
        self,
        email: str,
        password_raw_or_payload: str,
        username: str,
        dob: str = "2000-01-01",
        first_name: str = "",
        last_name: str = "",
        redirect_uri: Optional[str] = None
    ) -> Dict[str, Any]:
        """Step 7: Submit final registration to trigger OTP send."""
        log("REQ-REGISTER", f"Submitting registration for {email} ({username})...", self.instance_name)
        url = f"{self.BASE_URL}/login/device-based/kadabra-register-save-credentials/"

        if password_raw_or_payload.startswith("#PWD_BROWSER:"):
            password_payload = password_raw_or_payload
        else:
            password_payload = self.encrypt_password(password_raw_or_payload)

        data = {
            "client_consent_timestamp": str(int(time.time())),
            "display_name": f"{first_name} {last_name}".strip(),
            "foa_import_source_name": "",
            "foa_import_source_obid": "",
            "nta_disclosures_summary_cms_id": "",
            "picture_source": "",
            "tos_cms_id": self.TOS_CMS_ID,
            "username": username,
            "consent_version": "",
            "contact_point": email,
            "contact_point_type": "EMAIL_ADDRESS",
            "csi": self.client_session_id,
            "date_of_birth": dob,
            "device_id": self.device_id or "",
            "fb_encrypted_access_token": "",
            "fb_oidc_access_token": "",
            "first_name": first_name or "",
            "google_id_token": "",
            "has_youth_consent": "false",
            "ig_encrypted_access_token": "",
            "ig_encrypted_auth_header": "",
            "ig_oidc_access_token": "",
            "last_name": last_name or "",
            "opt_into_marketing": "false",
            "password": password_payload,
            "redirect_uri": redirect_uri or self.oidc_redirect_uri,
            "reg_integrity": self.reg_integrity or "",
            "should_save_credentials": "true",
            "source_app_id": self.SOURCE_APP_ID,
            "third_party_age_verification_id": "",
            "waterfall_id": self.waterfall_id,
            "caa_event_flow": "ntm",
            "entry_point": "login_home",
            "event_client_time": f"{time.time():.2f}",
            "is_kadabra_zero": "false",
            "reg_navigation_flow_name": "new_to_family_c50_r1",
            "regulation_jurisdiction": json.dumps([self.jurisdiction]),
            "qpl_join_id": self._generate_qpl_join_id(),
        }
        data.update(self._get_base_spin_params())

        headers = {
            "content-type": "application/x-www-form-urlencoded",
            "referer": self._get_current_referer(),
        }
        resp = self._safe_request("post", url, data=data, headers=headers)
        parsed = self._parse_fb_response(resp.text)

        if isinstance(parsed, dict):
            if "dtsgToken" in parsed:
                self.fb_dtsg = parsed["dtsgToken"]

            if "payload" in parsed:
                payload = parsed.get("payload", {})
                if isinstance(payload, dict):
                    user_id = payload.get("account_id") or payload.get("uid") or payload.get("user_id")
                    if user_id:
                        self.created_user_id = str(user_id)
                        log("REQ-SUCCESS", f"Registered Meta Account ID: {self.created_user_id}", self.instance_name)

        return parsed

    def confirm_email_otp(self, code: str, email: Optional[str] = None) -> Dict[str, Any]:
        """Submits 6-digit confirmation code / OTP to confirm and activate Meta account."""
        target_email = email or self.email
        clean_code = str(code).strip()
        log("REQ-OTP", f"Submitting OTP '{clean_code}' for {target_email}...", self.instance_name)
        variables = {
            "input": {
                "confirmation_code": {
                    "sensitive_string_value": clean_code
                },
                "confirmation_code_type": "OTP_CODE",
                "event_flow": "ntm",
                "rl_client_session_id": self.client_session_id,
                "source_app_id": self.SOURCE_APP_ID,
                "waterfall_id": self.waterfall_id
            }
        }
        return self.send_graphql_request(doc_id="9851798224911796", variables=variables)

    def send_graphql_request(self, doc_id: str, variables: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.BASE_URL}/api/graphql/"
        data = {
            "doc_id": doc_id,
            "variables": json.dumps(variables),
        }
        data.update(self._get_base_spin_params())

        headers = {
            "content-type": "application/x-www-form-urlencoded",
            "referer": self._get_current_referer(),
        }
        resp = self._safe_request("post", url, data=data, headers=headers)
        return resp.json() if resp.headers.get("content-type", "").startswith("application/json") else self._parse_fb_response(resp.text)

    def _parse_fb_response(self, text: str) -> Any:
        clean_text = text
        if clean_text.startswith("for (;;);"):
            clean_text = clean_text[9:]
        try:
            return json.loads(clean_text)
        except Exception:
            return {"raw_response": text}

    def get_cookies_dict(self) -> Dict[str, str]:
        try:
            if hasattr(self.session.cookies, "get_dict"):
                return self.session.cookies.get_dict()
            return {c.name: c.value for c in self.session.cookies}
        except Exception:
            return {}

    def get_cookies_string(self) -> str:
        cookies_dict = self.get_cookies_dict()
        return "; ".join([f"{k}={v}" for k, v in cookies_dict.items()])

    def check_for_checkpoint(self, wait_sec: int = 3) -> Optional[str]:
        log("CHECKPOINT-POLL", f"Checking for checkpoint status (waiting {wait_sec}s)...", self.instance_name)
        time.sleep(wait_sec)

        doc_headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "none",
            "sec-fetch-user": "?1",
            "upgrade-insecure-requests": "1",
            "referer": self._get_current_referer()
        }

        try:
            resp = self.session.get(f"{self.BASE_URL}/", headers=doc_headers, allow_redirects=True)
            if "checkpoint" in resp.url.lower() or "confirm that you're human" in resp.text.lower() or "checkpoints" in resp.text.lower() or "confirm you’re human" in resp.text.lower():
                log("CHECKPOINT-DETECT", f"Checkpoint detected at: {resp.url}", self.instance_name)
                self.checkpoint_url = resp.url
                return resp.url

            resp_oidc = self.session.get(self.oidc_redirect_uri, headers=doc_headers, allow_redirects=True)
            if "checkpoint" in resp_oidc.url.lower() or "confirm that you're human" in resp_oidc.text.lower() or "confirm you’re human" in resp_oidc.text.lower():
                log("CHECKPOINT-DETECT", f"Checkpoint detected via OIDC: {resp_oidc.url}", self.instance_name)
                self.checkpoint_url = resp_oidc.url
                return resp_oidc.url

        except Exception as e:
            log("CHECKPOINT-WARN", f"Error checking checkpoint: {e}", self.instance_name)

        return None

    def extract_captcha_persist_data(self, resp_text: str) -> str:
        match = re.search(r'"(?:bot_)?captcha_persist_data"\s*:\s*"([^"]+)"', resp_text)
        if match:
            persist_val = match.group(1)
            log("UFAC-DATA", f"Extracted captcha_persist_data: {persist_val[:30]}...", self.instance_name)
            return persist_val

        try:
            clean = resp_text[9:] if resp_text.startswith("for (;;);") else resp_text
            data = json.loads(clean)
            for root_key in ["ufac_client_submit_action", "ufac_submit_action", "ufac_action"]:
                node = data.get("data", {}).get(root_key, {})
                if isinstance(node, dict):
                    state = node.get("ufac_client", {}).get("state", {}) if "ufac_client" in node else node.get("state", {})
                    if isinstance(state, dict):
                        persist = state.get("captcha_persist_data") or state.get("bot_captcha_persist_data") or state.get("persist_data")
                        if persist:
                            log("UFAC-DATA", f"Extracted captcha_persist_data from JSON: {persist[:30]}...", self.instance_name)
                            return str(persist)
        except Exception:
            pass

        return "..."

    def resolve_ufac_checkpoint(
        self,
        checkpoint_url: Optional[str] = None,
        image_path: Optional[str] = None
    ) -> bool:
        page_url = checkpoint_url or self.checkpoint_url or f"{self.BASE_URL}/checkpoint/"
        actor_id = self.created_user_id or self.get_cookies_dict().get("c_user") or "1227049917168618"
        lsd = self.lsd or "RyHFQ20E53MNpQQ7jYBChR"
        fb_dtsg = self.fb_dtsg or ""
        jazoest = compute_jazoest(fb_dtsg or lsd)

        log("UFAC-START", f"Resolving UFAC Checkpoint via API for Actor: {actor_id}", self.instance_name)

        checkpoint_headers = {
            'accept': '*/*',
            'origin': self.BASE_URL,
            'referer': page_url,
            'user-agent': self.session.headers.get("user-agent", 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'),
            'x-asbd-id': '359341',
            'x-fb-lsd': lsd
        }

        checkpoint_params = {
            'fb_dtsg': fb_dtsg,
            'jazoest': jazoest,
            'lsd': lsd
        }

        # Step 1: Submit PROCEED Action
        log("UFAC-1", "[1/4] Submitting FRLUFACSubmitActionMutation (PROCEED)...", self.instance_name)
        mutation_proceed = {
            'av': actor_id,
            '__user': '0',
            '__a': '1',
            '__req': self._next_req(),
            'fb_api_caller_class': 'RelayModern',
            'fb_api_req_friendly_name': 'FRLUFACSubmitActionMutation',
            'server_timestamps': 'true',
            'variables': json.dumps({
                "input": {
                    "actor_id": actor_id,
                    "client_mutation_id": "1",
                    "action": "PROCEED",
                    "caller": None,
                    "enrollment_id": None
                },
                "scale": 1
            }),
            'doc_id': DOC_ID_UFAC_CHECKPOINT
        }

        persist_data = "..."
        try:
            resp_proceed = self.session.post(
                f"{self.BASE_URL}/api/graphql/",
                params=checkpoint_params,
                headers=checkpoint_headers,
                data=mutation_proceed
            )
            log("UFAC-PROCEED", f"PROCEED response [{resp_proceed.status_code}]: {resp_proceed.text[:180]}", self.instance_name)
            persist_data = self.extract_captcha_persist_data(resp_proceed.text)
        except Exception as e:
            log("UFAC-WARN", f"Warning during PROCEED step: {e}", self.instance_name)

        # Step 2: Solve reCAPTCHA Enterprise via 2Captcha
        log("2CAPTCHA", f"[2/4] Solving reCAPTCHA Enterprise via 2Captcha API (sitekey: {DEFAULT_RECAPTCHA_SITE_KEY[:15]}...)...", self.instance_name)
        token = self.captcha_solver.solve_recaptcha_v2(
            site_key=DEFAULT_RECAPTCHA_SITE_KEY,
            page_url=TwoCaptchaSolver.DEFAULT_IFRAME_URL,
            instance_name=self.instance_name
        )

        if token:
            log("2CAPTCHA-OK", f"🎉 Got 2Captcha Solution Token: {token[:35]}...", self.instance_name)
        else:
            log("2CAPTCHA-WARN", "⚠️ 2Captcha token not obtained. Attempting to proceed...", self.instance_name)
            token = ""

        # Step 3: Submit SUBMIT_BOT_CAPTCHA_RESPONSE mutation
        log("UFAC-3", "[3/4] Submitting SUBMIT_BOT_CAPTCHA_RESPONSE mutation...", self.instance_name)
        mutation_captcha = {
            'av': actor_id,
            '__user': '0',
            '__a': '1',
            '__req': self._next_req(),
            'fb_api_caller_class': 'RelayModern',
            'fb_api_req_friendly_name': 'FRLUFACSubmitActionMutation',
            'server_timestamps': 'true',
            'variables': json.dumps({
                "input": {
                    "actor_id": actor_id,
                    "client_mutation_id": "2",
                    "action": "SUBMIT_BOT_CAPTCHA_RESPONSE",
                    "bot_captcha_persist_data": persist_data,
                    "captcha_persist_data": persist_data,
                    "bot_captcha_response": token or None,
                    "captcha_response": token or None,
                    "caller": None,
                    "enrollment_id": None
                },
                "scale": 1
            }),
            'doc_id': DOC_ID_UFAC_CHECKPOINT
        }

        captcha_resp_text = ""
        try:
            resp_captcha = self.session.post(
                f"{self.BASE_URL}/api/graphql/",
                params=checkpoint_params,
                headers=checkpoint_headers,
                data=mutation_captcha
            )
            log("UFAC-CAPTCHA", f"Captcha submission response [{resp_captcha.status_code}]: {resp_captcha.text[:200]}", self.instance_name)
            captcha_resp_text = resp_captcha.text
        except Exception as e:
            log("UFAC-ERR", f"Error submitting bot captcha: {e}", self.instance_name)

        # Step 4: Submit UPLOAD_IMAGE Mutation for UFACImageUploadChallengeState
        target_image = image_path or get_random_verification_image()
        if "ImageUpload" in captcha_resp_text or "image_upload" in captcha_resp_text or target_image:
            log("UFAC-4", f"[4/4] Submitting Image Upload Challenge via API with image: {os.path.basename(str(target_image))}...", self.instance_name)
            mutation_image = {
                'av': actor_id,
                '__user': '0',
                '__a': '1',
                '__req': self._next_req(),
                'fb_api_caller_class': 'RelayModern',
                'fb_api_req_friendly_name': 'FRLUFACSubmitActionMutation',
                'server_timestamps': 'true',
                'variables': json.dumps({
                    "input": {
                        "actor_id": actor_id,
                        "client_mutation_id": "3",
                        "action": "UPLOAD_IMAGE",
                        "uploaded_image_file": "file",
                        "caller": None,
                        "enrollment_id": None
                    },
                    "scale": 1
                }),
                'doc_id': DOC_ID_UFAC_CHECKPOINT
            }

            try:
                if USE_CURL_CFFI:
                    try:
                        from curl_cffi.curl import CurlMime
                        mime = CurlMime()
                        for k, v in mutation_image.items():
                            mime.addpart(name=k, data=str(v).encode("utf-8"))
                        if target_image and os.path.exists(target_image):
                            log("IMG-MIME", f"Attaching verification photo (CurlMime): {os.path.basename(target_image)}", self.instance_name)
                            mime.addpart(
                                name="file",
                                local_path=target_image,
                                filename="image.jpeg",
                                content_type="image/jpeg"
                            )
                        upload_resp = self.session.post(
                            f"{self.BASE_URL}/api/graphql/",
                            params=checkpoint_params,
                            headers=checkpoint_headers,
                            multipart=mime
                        )
                    except Exception as c_err:
                        if target_image and os.path.exists(target_image):
                            with open(target_image, "rb") as f:
                                upload_resp = self.session.post(
                                    f"{self.BASE_URL}/api/graphql/",
                                    params=checkpoint_params,
                                    headers=checkpoint_headers,
                                    data=mutation_image,
                                    files={'file': ('image.jpeg', f.read(), 'image/jpeg')}
                                )
                        else:
                            upload_resp = self.session.post(
                                f"{self.BASE_URL}/api/graphql/",
                                params=checkpoint_params,
                                headers=checkpoint_headers,
                                data=mutation_image
                            )
                else:
                    if target_image and os.path.exists(target_image):
                        log("IMG-REQ", f"Attaching verification photo: {os.path.basename(target_image)}", self.instance_name)
                        with open(target_image, "rb") as f:
                            upload_resp = self.session.post(
                                f"{self.BASE_URL}/api/graphql/",
                                params=checkpoint_params,
                                headers=checkpoint_headers,
                                data=mutation_image,
                                files={'file': ('image.jpeg', f.read(), 'image/jpeg')}
                            )
                    else:
                        upload_resp = self.session.post(
                            f"{self.BASE_URL}/api/graphql/",
                            params=checkpoint_params,
                            headers=checkpoint_headers,
                            data=mutation_image
                        )

                log("UFAC-UPLOAD", f"Image Upload Response [{upload_resp.status_code}]: {upload_resp.text[:200]}", self.instance_name)
            except Exception as e:
                log("UFAC-ERR", f"Failed to submit image upload: {e}", self.instance_name)

        log("UFAC-SUCCESS", "🎉 UFAC Checkpoint API resolution completed!", self.instance_name)

        # Extract and follow 'next' redirect chain
        try:
            parsed_cp = urllib.parse.urlparse(page_url)
            query_params = urllib.parse.parse_qs(parsed_cp.query)
            next_target = query_params.get("next", [None])[0]
            if next_target:
                log("REDIRECT", f"Following post-checkpoint redirect: {next_target}", self.instance_name)
                redir_headers = {
                    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                    "sec-fetch-dest": "document",
                    "sec-fetch-mode": "navigate",
                    "referer": page_url
                }
                redir_resp = self.session.get(next_target, headers=redir_headers, allow_redirects=True)
                log("REDIRECT-OK", f"Landed at: {redir_resp.url} (Status: {redir_resp.status_code})", self.instance_name)
        except Exception as ex:
            log("REDIRECT-WARN", f"Could not follow redirect: {ex}", self.instance_name)

        return True

    def complete_oidc_flow(self) -> Dict[str, Any]:
        log("OIDC", "Completing OIDC Authorization flow...", self.instance_name)
        doc_headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "referer": self._get_current_referer()
        }
        try:
            resp = self.session.get(self.oidc_redirect_uri, headers=doc_headers, allow_redirects=True)
            log("OIDC-STATUS", f"OIDC flow final URL: {resp.url} [{resp.status_code}]", self.instance_name)

            code = None
            if "code=" in resp.url:
                parsed_url = urllib.parse.urlparse(resp.url)
                params = urllib.parse.parse_qs(parsed_url.query)
                code = params.get("code", [None])[0]
                if code:
                    log("OIDC-CODE", f"Obtained OIDC Authorization Code: {code[:20]}...", self.instance_name)

            cookies_dict = self.get_cookies_dict()
            return {
                "success": True,
                "code": code,
                "final_url": resp.url,
                "user_id": self.created_user_id or cookies_dict.get("c_user"),
                "cookies": cookies_dict
            }
        except Exception as e:
            log("OIDC-ERR", f"Error completing OIDC flow: {e}", self.instance_name)
            return {"success": False, "error": str(e)}


async def solve_checkpoint_via_playwright(client: MetaAuthClient, checkpoint_url: str, headless: bool = False, instance_name: str = "") -> bool:
    """
    Fallback checkpoint solver using Playwright.
    Transfers active Meta session cookies, opens the checkpoint challenge URL,
    allows the user (if non-headless) or stealth page to complete the challenge,
    and pulls updated session cookies back to client.session.
    """
    if not HAS_PLAYWRIGHT or not checkpoint_url:
        return False

    mode_text = "headless" if headless else "visible window"
    log("PW-CHECKPOINT", f"🌐 Opening Meta Checkpoint in Playwright ({mode_text})...", instance_name)
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            channel = _CFG.get("browser_channel", "chrome")
            launch_args = ["--disable-blink-features=AutomationControlled", "--no-sandbox"]
            browser = None
            try:
                browser = await p.chromium.launch(headless=headless, channel=channel, args=launch_args)
            except Exception:
                try:
                    browser = await p.chromium.launch(headless=headless, args=launch_args)
                except Exception as b_err:
                    log("PW-ERR", f"Could not launch browser: {b_err}", instance_name)
                    return False

            context = await browser.new_context(
                viewport={"width": 500, "height": 700},
                user_agent=client.session.headers.get("user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            )

            # Inject cookies from client.session
            pw_cookies = []
            cookie_dict = client.get_cookies_dict() if hasattr(client, "get_cookies_dict") else {}
            if not cookie_dict and hasattr(client.session.cookies, "get_dict"):
                cookie_dict = client.session.cookies.get_dict()
            elif not cookie_dict and isinstance(client.session.cookies, dict):
                cookie_dict = client.session.cookies

            if cookie_dict:
                for name, val in cookie_dict.items():
                    pw_cookies.append({
                        "name": str(name),
                        "value": str(val),
                        "domain": ".meta.com",
                        "path": "/"
                    })
            elif hasattr(client.session.cookies, "__iter__"):
                for c in client.session.cookies:
                    if hasattr(c, "name") and hasattr(c, "value"):
                        pw_cookies.append({
                            "name": str(c.name),
                            "value": str(c.value),
                            "domain": getattr(c, "domain", ".meta.com") or ".meta.com",
                            "path": getattr(c, "path", "/") or "/"
                        })

            if pw_cookies:
                try:
                    await context.add_cookies(pw_cookies)
                except Exception as c_err:
                    log("PW-WARN", f"Cookie inject warning: {c_err}", instance_name)

            page = await context.new_page()
            try:
                await page.goto(checkpoint_url, wait_until="domcontentloaded", timeout=30000)
            except Exception as nav_err:
                log("PW-WARN", f"Navigation warning: {nav_err}", instance_name)

            log("PW-WAIT", f"⏳ Waiting for checkpoint completion (up to 60s)...", instance_name)

            start_wait = time.time()
            solved = False
            while time.time() - start_wait < 60:
                current_url = page.url
                if "checkpoints" not in current_url.lower() and ("recover/success" in current_url.lower() or "auth.meta.com" in current_url.lower()):
                    solved = True
                    break

                try:
                    btn_cont = await page.query_selector("button:has-text('Continue'), input[value='Continue'], button[type='submit']")
                    if btn_cont and await btn_cont.is_visible():
                        await btn_cont.click()
                except Exception:
                    pass

                await asyncio.sleep(2.0)

            if solved:
                log("PW-SUCCESS", "🎉 Checkpoint completed in browser! Syncing session cookies...", instance_name)
                new_cookies = await context.cookies()
                for ck in new_cookies:
                    try:
                        client.session.cookies.set(ck["name"], ck["value"], domain=ck.get("domain", ".meta.com"), path=ck.get("path", "/"))
                    except Exception:
                        pass
                await browser.close()
                return True
            else:
                log("PW-FAIL", "⚠️ Checkpoint not passed within timeout.", instance_name)
                await browser.close()
                return False
    except Exception as e:
        log("PW-ERR", f"Playwright checkpoint error: {e}", instance_name)
        return False


# ==============================================================================
# 🚀 100% PURE-API META ACCOUNT CREATION TASK (NO BROWSER / NO PLAYWRIGHT)
# ==============================================================================
async def create_meta_account_task(
    playwright: Optional[Any] = None,
    first_name: str = "",
    last_name: str = "",
    password: str = "",
    username: str = "",
    instance_name: str = "Inst-1",
    task_context: Optional[Dict[str, Any]] = None,
    proxy: Optional[str] = None
) -> Tuple[bool, str, str]:
    """
    Creates a Meta Account 100% PURE API (FAST, ULTRA-LIGHTWEIGHT, NO BROWSER):
      1. TempMail Ninja (Socket.IO) or Mail.td for disposable email & OTP
      2. MetaAuthClient pure-HTTP registration with TweetNaCl + AES-256-GCM envelope encryption
      3. GraphQL OTP confirmation (FRLConfirmEmailMutation)
      4. Direct API Checkpoint detection + UFAC GraphQL solving (2Captcha + Multipart Image Upload)
      5. OIDC flow completion & account activation
    """
    ninja_client: Optional[Any] = None
    email = ""
    mail_token = ""

    try:
        # 1. CREATE DISPOSABLE EMAIL
        email = None
        mail_token = None
        ninja_client = None

        for attempt in range(1, 4):
            log("GEN", f"Generating temporary email for Meta AI (attempt {attempt}/3)...", instance_name=instance_name)
            email, _, mail_token = fallback_generate_temp_email(instance_name=instance_name)
            if email:
                break
            if HAS_NINJA and _CFG.get("email_services", {}).get("ninja", False):
                try:
                    log("TEMPMAIL-NINJA", "Trying TempMail Ninja fallback...", instance_name=instance_name)
                    ninja_client = TempMailNinjaAPI()
                    ninja_client.connect()
                    email = ninja_client.create_temp_email()
                    if email:
                        if task_context is not None:
                            task_context['ninja_client'] = ninja_client
                        break
                except Exception as e:
                    log("TEMPMAIL-WARN", f"Ninja fallback error: {e}", instance_name=instance_name)
                    try:
                        from airplane_mode import is_usb_phone_connected, rotate_ip_on_ninja_failure
                        if is_usb_phone_connected():
                            rotate_ip_on_ninja_failure(reason=f"Meta AI Ninja fallback error: {e}")
                    except Exception:
                        pass
                    ninja_client = None
            time.sleep(1.0)

        if not email:
            log("ERR", "Failed to generate email across all available email providers.", instance_name=instance_name)
            return False, "", ""

        if task_context is not None:
            task_context['email'] = email
            task_context['mail_token'] = mail_token

        log("META-INIT", f"Target Email: {email} | Password: {password} | User: {username}", instance_name=instance_name)

        # 2. PURE-REQUEST META REGISTRATION FLOW
        dob_year = random.randint(1992, 2002)
        dob_month = f"{random.randint(1, 12):02d}"
        dob_day = f"{random.randint(1, 28):02d}"
        dob = f"{dob_year}-{dob_month}-{dob_day}"

        # Resolve proxy
        meta_proxy = proxy
        if not meta_proxy and _CFG.get("ninja_proxy", {}).get("enabled", False):
            try:
                from NINJA import format_proxy_url
                p_str = _CFG.get("ninja_proxy", {}).get("proxy")
                if p_str:
                    meta_proxy = format_proxy_url(p_str, session_id=uuid.uuid4().hex[:6])
            except Exception:
                pass

        if meta_proxy:
            log("META-PROXY", "Using US Residential Proxy for Meta registration & verification", instance_name=instance_name)

        client = MetaAuthClient(proxy=meta_proxy, instance_name=instance_name)
        if not client.init_session():
            log("ERR", "Failed to initialize Meta auth request session.", instance_name=instance_name)
            if ninja_client:
                ninja_client.disconnect()
            return False, "", ""

        # Step 1: Check contact point
        client.check_contact_point_availability(email=email)

        # Step 2: Check password (password received from Telegram bot)
        client.check_password(email=email, password_raw_or_payload=password, dob=dob)

        # Step 3: Check DOB
        client.check_date_of_birth(email=email, dob=dob, first_name=first_name, last_name=last_name)

        # Step 4: Determine username
        chosen_username = username.strip() if username else ""
        if not chosen_username:
            suggest_resp = client.suggest_username()
            chosen_username = (
                suggest_resp.get("payload", {}).get("username")
                if isinstance(suggest_resp, dict) and "payload" in suggest_resp
                else None
            )
        if not chosen_username:
            clean_fn = re.sub(r'[^a-zA-Z0-9]', '', first_name).lower() or "user"
            clean_ln = re.sub(r'[^a-zA-Z0-9]', '', last_name).lower() or "account"
            chosen_username = f"{clean_fn}{clean_ln}{random.randint(100, 9999)}"

        if task_context is not None:
            task_context['username'] = chosen_username

        # Step 5: Validate handle
        client.check_profile(username=chosen_username)

        # Step 6: Submit registration (Meta will send 6-digit confirmation OTP)
        client.register_save_credentials(
            email=email,
            password_raw_or_payload=password,
            username=chosen_username,
            dob=dob,
            first_name=first_name,
            last_name=last_name
        )

        # 3. POLL OTP VIA MAIL SERVICE
        log("OTP-POLL", f"Waiting for 6-digit OTP code on {email}...", instance_name=instance_name)
        otp_code = None

        if mail_token:
            otp_code = fallback_fetch_otp(
                email=email,
                password=password,
                token=mail_token,
                max_wait_sec=60,
                expected_digits=6,
                instance_name=instance_name
            )

        if not otp_code and ninja_client:
            try:
                otp_code = ninja_client.wait_for_otp(timeout=60, poll_interval=2, expected_digits=6)
            except Exception as e:
                log("OTP-WARN", f"Ninja OTP wait error: {e}", instance_name=instance_name)

        if not otp_code:
            log("OTP-TIMEOUT", f"⌛ Failed/Late OTP for {email}. Abandoning this email and moving to next...", instance_name=instance_name)
            try:
                mark_ninja_email_status(email, "OTP_TIMEOUT", instance_name=instance_name)
            except Exception:
                pass
            if ninja_client:
                try:
                    ninja_client.disconnect()
                except Exception:
                    pass
            return False, "", "OTP_TIMEOUT"

        log("OTP-RECV", f"🔑 Retrieved Meta OTP Code: {otp_code}", instance_name=instance_name)

        # Step 7: Confirm OTP via GraphQL mutation
        confirm_resp = client.confirm_email_otp(code=otp_code, email=email)
        log("OTP-CONFIRM", f"Confirmation GraphQL response: {confirm_resp}", instance_name=instance_name)

        # 4. PURE-API CHECKPOINT & 2CAPTCHA + IMAGE RESOLUTION
        log("CHECKPOINT-FLOW", "Checking for Checkpoint / 'Confirm you are human' challenge via API...", instance_name=instance_name)
        checkpoint_url = client.check_for_checkpoint(wait_sec=3)
        if checkpoint_url:
            if SKIP_CAPTCHA or _CFG.get("skip_captcha", False):
                log("NO-CAPTCHA", f"⚡ [No Captcha Mode] Checkpoint/Captcha detected for {email}! Skipping to keep only clean, no-captcha accounts.", instance_name=instance_name)
                try:
                    mark_ninja_email_status(email, "CAPTCHA_SKIPPED", instance_name=instance_name)
                except Exception:
                    pass
                # Rotate IP immediately for a clean next attempt
                try:
                    if meta_proxy:
                        log("NO-CAPTCHA", "🔄 Proxy in use: next attempt will use fresh residential session.", instance_name=instance_name)
                    else:
                        from airplane_mode import is_usb_phone_connected, rotate_ip_on_ninja_failure
                        if is_usb_phone_connected():
                            log("NO-CAPTCHA", "📱 USB phone detected! Rotating IP via Airplane Mode...", instance_name=instance_name)
                            rotate_ip_on_ninja_failure(reason="Checkpoint hit - Rotating IP for clean Meta attempt", log_fn=lambda m: log("NO-CAPTCHA", m, instance_name=instance_name))
                        else:
                            from NINJA import toggle_wifi
                            log("NO-CAPTCHA", "🔄 Resetting WiFi to rotate IP...", instance_name=instance_name)
                            toggle_wifi()
                except Exception as ex_rot:
                    log("NO-CAPTCHA-WARN", f"IP rotation warning: {ex_rot}", instance_name=instance_name)
                if ninja_client:
                    try:
                        ninja_client.disconnect()
                    except Exception:
                        pass
                return False, "", "CHECKPOINT_SKIPPED"

            log("CHECKPOINT", f"Checkpoint challenge active! Attempting resolution (2Captcha + Photo)...", instance_name=instance_name)
            ufac_ok = client.resolve_ufac_checkpoint(checkpoint_url=checkpoint_url)
            if not ufac_ok:
                log("UFAC-WARN", "API checkpoint resolution incomplete. Trying browser fallback...", instance_name=instance_name)
                if HAS_PLAYWRIGHT:
                    ufac_ok = await solve_checkpoint_via_playwright(client, checkpoint_url, headless=HEADLESS, instance_name=instance_name)

            if not ufac_ok:
                log("META-FAIL", f"❌ Checkpoint not resolved for {email}! Please check 2Captcha balance or use Headless OFF in GUI.", instance_name=instance_name)
                return False, "", ""

        # Complete OIDC authorization
        client.complete_oidc_flow()

        log("META-SUCCESS", f"🎉 Meta Account Created & Verified 100% via API for {email}!", instance_name=instance_name)
        try:
            mark_ninja_email_status(email, "DONE", instance_name=instance_name)
        except Exception:
            pass
        return True, email, mail_token

    except Exception as e:
        log("META-ERR", f"Meta creation exception: {e}", instance_name=instance_name)
        if ninja_client:
            try:
                ninja_client.disconnect()
            except Exception:
                pass
        return False, "", ""

# ==============================================================================
# 📱 ADB EMULATOR CONTROL & UI DETECTION
# ==============================================================================
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


def find_adb():
    """Finds available ADB executable with deep multi-drive and emulator folder search."""
    # 1. First check relative to discovered MuMuManager if present
    mumu_p = find_mumu_manager()
    if mumu_p and os.path.exists(mumu_p):
        mumu_dir = os.path.dirname(mumu_p)
        parent_dir = os.path.dirname(mumu_dir)
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

ADB_PATH = find_adb()

def get_device_unique_signature(dev_serial):
    try:
        res = subprocess.run(
            f'"{ADB_PATH}" -s {dev_serial} shell "cat /proc/sys/kernel/random/boot_id 2>/dev/null || getprop ro.serialno 2>/dev/null || settings get secure android_id 2>/dev/null"',
            shell=True, capture_output=True, encoding='utf-8', errors='ignore', timeout=2
        )
        sig = res.stdout.strip() if res.stdout else ""
        if sig:
            for l in sig.splitlines():
                l = l.strip()
                if l and len(l) > 4:
                    return l
    except Exception:
        pass
    return dev_serial

def get_unique_devices(emulators_only=True):
    # Query current devices first to avoid creating duplicate IP connections
    cur_res = subprocess.run(f'"{ADB_PATH}" devices', shell=True, capture_output=True, encoding='utf-8', errors='ignore')
    active_now = []
    for line in cur_res.stdout.strip().splitlines()[1:]:
        parts = line.strip().split()
        if len(parts) >= 2 and parts[1] == "device":
            active_now.append(parts[0])

    # Disconnect any duplicate 127.0.0.1:55XX ports where emulator-55XX already exists
    for dev in list(active_now):
        if dev.startswith("127.0.0.1:") and ":" in dev:
            try:
                p_num = int(dev.split(":")[1])
                if 5555 <= p_num <= 5700:
                    matching_emu = f"emulator-{p_num - 1}"
                    if matching_emu in active_now:
                        subprocess.run(f'"{ADB_PATH}" disconnect {dev}', shell=True, capture_output=True)
                        if dev in active_now:
                            active_now.remove(dev)
            except Exception:
                pass

    ports = [
        5555, 5557, 5559, 5561, 5563, 5565, 5567, 5569,
        7555, 16384, 16416, 16448, 16480, 16512,
        62001, 62025, 62026,
        21503, 21513, 21523
    ]

    from concurrent.futures import ThreadPoolExecutor
    def _quick_connect(p):
        try:
            # Skip if standard emulator-{p-1} is already active
            if 5555 <= p <= 5700 and f"emulator-{p - 1}" in active_now:
                return
            if f"127.0.0.1:{p}" in active_now:
                return
            subprocess.run(f'"{ADB_PATH}" connect 127.0.0.1:{p}', shell=True, capture_output=True, timeout=0.4)
        except Exception:
            pass

    with ThreadPoolExecutor(max_workers=12) as executor:
        list(executor.map(_quick_connect, ports))

    res = subprocess.run(f'"{ADB_PATH}" devices', shell=True, capture_output=True, encoding='utf-8', errors='ignore')
    lines = res.stdout.strip().splitlines()
    raw_devices = []
    for line in lines[1:]:
        parts = line.strip().split()
        if len(parts) >= 2 and parts[1] == "device":
            raw_devices.append(parts[0])

    seen_signatures = set()
    unique_devices = []

    for dev in raw_devices:
        sig = get_device_unique_signature(dev)
        if sig not in seen_signatures:
            seen_signatures.add(sig)
            unique_devices.append(dev)

    if emulators_only:
        emu_list = [d for d in unique_devices if "127.0.0.1:" in d or "localhost:" in d or d.startswith("emulator-")]
        if emu_list:
            return emu_list

    return unique_devices

def run_adb_command(args, device_serial=None, instance_name="", timeout=12):
    if isinstance(args, str):
        if args.startswith("adb "):
            args = args[4:]
        cmd_type = args.split()[0] if args.split() else ""
        target = device_serial
        if target and cmd_type not in ["connect", "disconnect", "devices"]:
            cmd = f'"{ADB_PATH}" -s {target} {args}'
        else:
            cmd = f'"{ADB_PATH}" {args}'
    else:
        cmd = [ADB_PATH] + args

    with ADB_SEMAPHORE:
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, encoding='utf-8', errors='ignore', timeout=timeout)
            return result.stdout.strip() if result.stdout else ""
        except subprocess.TimeoutExpired:
            log("ADB-TIMEOUT", f"ADB command timed out ({timeout}s): {str(args)[:40]}", instance_name=instance_name)
            return ""
        except Exception as e:
            log("ADB-ERR", f"Execution error: {e}", instance_name=instance_name)
            return ""

def is_keyboard_visible(device_serial=None, instance_name=""):
    out = run_adb_command("shell dumpsys input_method", device_serial=device_serial, instance_name=instance_name)
    return "mInputShown=true" in out or "mHasSurface=true" in out

def clear_input_field(length=35, device_serial=None, instance_name=""):
    run_adb_command("shell input keyevent 123", device_serial=device_serial, instance_name=instance_name)
    del_keys = " ".join(["67"] * length)
    run_adb_command(f"shell input keyevent {del_keys}", device_serial=device_serial, instance_name=instance_name)

def type_text(text, device_serial=None, instance_name="", human_like=False, min_delay=0.04, max_delay=0.12):
    if not text:
        return
    clean_str = str(text)
    if human_like:
        for char in clean_str:
            if char.isdigit():
                run_adb_command(f'shell input text {char}', device_serial=device_serial, instance_name=instance_name)
            else:
                escaped = char.replace(' ', '%s').replace('&', r'\&').replace('<', r'\<').replace('>', r'\>').replace('"', r'\"').replace("'", r"\'").replace('$', r'\$').replace('`', r'\`')
                run_adb_command(f'shell input text "{escaped}"', device_serial=device_serial, instance_name=instance_name)
            time.sleep(random.uniform(min_delay, max_delay))
    else:
        if clean_str.isdigit():
            run_adb_command(f'shell input text {clean_str}', device_serial=device_serial, instance_name=instance_name)
        else:
            escaped = clean_str.replace(' ', '%s').replace('&', r'\&').replace('<', r'\<').replace('>', r'\>').replace('"', r'\"').replace("'", r"\'")
            run_adb_command(f'shell input text "{escaped}"', device_serial=device_serial, instance_name=instance_name)

def hide_keyboard(device_serial=None, instance_name=""):
    run_adb_command("shell input keyevent 111", device_serial=device_serial, instance_name=instance_name)
    time.sleep(0.2)

def parse_bounds(bounds_str):
    match = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds_str)
    if match:
        left, top, right, bottom = map(int, match.groups())
        cx, cy = (left + right) // 2, (top + bottom) // 2
        if cx > 10 and cy > 10:
            return cx, cy
    return None

def get_screen_dimensions(root):
    if root is not None:
        bounds = root.attrib.get('bounds', '')
        match = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds)
        if match:
            w = int(match.group(3))
            h = int(match.group(4))
            if w > 100 and h > 100:
                return w, h
    return 540, 960

def get_rel_coords(root, rx, ry):
    w, h = get_screen_dimensions(root)
    return int(w * rx), int(h * ry)

def get_screen_hierarchy(device_serial=None, instance_name="", max_retries=2):
    safe_ser = device_serial.replace(':', '_').replace('.', '_').replace('-', '_') if device_serial else "default"
    dump_path = f"/sdcard/window_dump_{safe_ser}.xml"
    
    for attempt in range(1, max_retries + 1):
        time.sleep(0.08 if attempt == 1 else 0.25)
        run_adb_command(f"shell uiautomator dump {dump_path}", device_serial=device_serial, instance_name=instance_name, timeout=8)
        xml_str = run_adb_command(f"shell cat {dump_path}", device_serial=device_serial, instance_name=instance_name, timeout=6)
        if xml_str and xml_str.startswith("<?xml"):
            try:
                return ET.fromstring(xml_str)
            except Exception:
                pass
        if attempt < max_retries:
            time.sleep(0.2)
    return None

def extract_screen_texts(node):
    texts = []
    if node is None:
        return texts
    text = node.attrib.get('text', '').strip()
    desc = node.attrib.get('content-desc', '').strip()
    if text:
        texts.append(text)
    if desc and desc != text:
        texts.append(desc)
    for child in node:
        texts.extend(extract_screen_texts(child))
    return texts

def find_password_field(root):
    if root is None:
        return None
    for node in root.iter('node'):
        cls = node.attrib.get('class', '').lower()
        is_pwd = node.attrib.get('password', '').lower() == 'true'
        if 'edittext' in cls and is_pwd:
            coords = parse_bounds(node.attrib.get('bounds', ''))
            if coords:
                return coords
    for node in root.iter('node'):
        cls = node.attrib.get('class', '').lower()
        if 'edittext' in cls:
            coords = parse_bounds(node.attrib.get('bounds', ''))
            if coords:
                return coords
    return None

def find_code_input_field(root):
    """
    Find the Code input box on 'Check your email' screen/modal.
    Prioritizes:
    1. EditText nodes in the expected input region (0.35 to 0.80 of screen).
    2. Node with exact text/content-desc 'Code', 'Enter code', 'Enter the code'.
    3. Fallback relative coords based on screen style (Facebook page: 0.66, Modal: 0.48).
    """
    if root is None:
        return 270, 460
    w, h = get_screen_dimensions(root)
    
    # 1. Search for EditText node in valid middle region
    for node in root.iter('node'):
        cls = node.attrib.get('class', '').lower()
        if 'edittext' in cls:
            coords = parse_bounds(node.attrib.get('bounds', ''))
            if coords and int(h * 0.35) <= coords[1] <= int(h * 0.80):
                return coords[0], coords[1]
                
    # 2. Look for exact "Enter code" / "Code" placeholder text
    for node in root.iter('node'):
        t = node.attrib.get('text', '').strip().lower()
        d = node.attrib.get('content-desc', '').strip().lower()
        if t in ["enter code", "enter the code", "code"] or d in ["enter code", "enter the code", "code"]:
            coords = parse_bounds(node.attrib.get('bounds', ''))
            if coords and int(h * 0.35) <= coords[1] <= int(h * 0.80):
                return coords[0], coords[1]

    # 3. Fallback based on page style
    texts = extract_screen_texts(root)
    blob = " ".join(texts).lower()
    if "facebook" in blob or "enter code" in blob:
        return int(w * 0.50), int(h * 0.66)
    return int(w * 0.50), int(h * 0.48)

def find_2fa_code_input_field(root):
    """
    Accurately finds the 6-digit or 8-digit verification code input field.
    Handles hints ('Enter code'), empty text, and relative bounds.
    """
    if root is None:
        return 270, 480
    w, h = get_screen_dimensions(root)

    # 1. Look for EditText with 'code' or 'enter' in hint, text, desc, or res-id
    for node in root.iter('node'):
        cls = node.attrib.get('class', '').lower()
        if 'edittext' in cls:
            hint = node.attrib.get('hint', '').lower()
            text = node.attrib.get('text', '').lower()
            desc = node.attrib.get('content-desc', '').lower()
            res = node.attrib.get('resource-id', '').lower()
            comb = f"{hint} {text} {desc} {res}"
            coords = parse_bounds(node.attrib.get('bounds', ''))
            if coords and int(h * 0.25) <= coords[1] <= int(h * 0.80):
                if any(k in comb for k in ["code", "enter", "pin", "token", "digit"]):
                    return coords[0], coords[1]

    # 2. Look for ANY EditText in middle area (on OTP screen there is only one input box)
    for node in root.iter('node'):
        cls = node.attrib.get('class', '').lower()
        if 'edittext' in cls:
            coords = parse_bounds(node.attrib.get('bounds', ''))
            if coords and int(h * 0.25) <= coords[1] <= int(h * 0.80):
                return coords[0], coords[1]

    # 3. Look for node matching 'enter code' text/hint
    for node in root.iter('node'):
        hint = node.attrib.get('hint', '').strip().lower()
        text = node.attrib.get('text', '').strip().lower()
        if "enter code" in hint or "enter code" in text or hint == "code" or text == "code":
            coords = parse_bounds(node.attrib.get('bounds', ''))
            if coords and int(h * 0.25) <= coords[1] <= int(h * 0.80):
                return coords[0], coords[1]

    # 4. Fallback relative coords for 2FA code screen (center around 0.48)
    return int(w * 0.50), int(h * 0.48)

def paste_or_type_code(code: str, device_serial=None, instance_name="", field_coords=None):
    """
    Unblockable, bulletproof 2FA / verification code input helper:
    1. Focuses input field accurately
    2. Clears previous text
    3. Tries setting Android clipboard & sending KEYCODE_PASTE (279)
    4. Inputs via direct unquoted ADB input text
    5. Fallback hardware digit keyevents to defeat segmented/custom OTP inputs
    """
    if not code:
        return False
    clean_code = str(code).strip()
    digits_only = re.sub(r'[^0-9]', '', clean_code)
    use_code = digits_only if len(digits_only) in [6, 8] else clean_code

    if field_coords:
        fx, fy = field_coords[0], field_coords[1]
    else:
        root = get_screen_hierarchy(device_serial=device_serial, instance_name=instance_name)
        fx, fy = find_2fa_code_input_field(root)

    log("STATE-ACTION", f"Tapping 2FA code field at ({fx}, {fy}) to focus and paste '{use_code}'...", instance_name=instance_name)
    run_adb_command(f"shell input tap {fx} {fy}", device_serial=device_serial, instance_name=instance_name)
    time.sleep(0.3)

    # Clear field thoroughly
    clear_input_field(length=15, device_serial=device_serial, instance_name=instance_name)
    time.sleep(0.2)

    # 1. Try Android Clipboard Paste (Sets clipboard and fires KEYCODE_PASTE 279)
    try:
        run_adb_command(f"shell cmd clipboard set text {use_code}", device_serial=device_serial, instance_name=instance_name)
    except Exception:
        pass
    run_adb_command("shell input keyevent 279", device_serial=device_serial, instance_name=instance_name)
    time.sleep(0.2)

    # Check if text was entered
    root_chk = get_screen_hierarchy(device_serial=device_serial, instance_name=instance_name, max_retries=1)
    texts_chk = extract_screen_texts(root_chk) if root_chk is not None else []
    pasted_ok = any(use_code in t.replace(' ', '') for t in texts_chk)

    # 2. If not pasted or empty, input via direct unquoted input text
    if not pasted_ok:
        run_adb_command(f"shell input text {use_code}", device_serial=device_serial, instance_name=instance_name)
        time.sleep(0.3)
        root_chk2 = get_screen_hierarchy(device_serial=device_serial, instance_name=instance_name, max_retries=1)
        texts_chk2 = extract_screen_texts(root_chk2) if root_chk2 is not None else []
        pasted_ok = any(use_code in t.replace(' ', '') for t in texts_chk2)

    # 3. If still not filled (e.g. segmented OTP cells where input text dropped chars), send individual numeric keyevents
    if not pasted_ok and use_code.isdigit():
        log("2FA-ACTION", f"Typing code via hardware digit keyevents...", instance_name=instance_name)
        run_adb_command(f"shell input tap {fx} {fy}", device_serial=device_serial, instance_name=instance_name)
        time.sleep(0.2)
        clear_input_field(length=12, device_serial=device_serial, instance_name=instance_name)
        key_list = [str(int(d) + 7) for d in use_code]
        for k in key_list:
            run_adb_command(f"shell input keyevent {k}", device_serial=device_serial, instance_name=instance_name)
            time.sleep(0.06)
        time.sleep(0.3)

    hide_keyboard(device_serial=device_serial, instance_name=instance_name)
    time.sleep(0.2)
    return True

def find_input_box(root, hint_patterns=None, default_rx=0.50, default_ry=0.40):
    if root is None:
        return int(540 * default_rx), int(960 * default_ry)
    w, h = get_screen_dimensions(root)
    if hint_patterns is None:
        hint_patterns = ["full name", "username", "email", "code", "password"]
    
    # 1. Look for node matching any hint_pattern in text, content-desc, or resource-id in the body (0.20 to 0.85)
    for node in root.iter('node'):
        t = node.attrib.get('text', '').strip().lower()
        d = node.attrib.get('content-desc', '').strip().lower()
        r = node.attrib.get('resource-id', '').strip().lower()
        comb = f"{t} {d} {r}".strip()
        coords = parse_bounds(node.attrib.get('bounds', ''))
        if coords and int(h * 0.20) < coords[1] < int(h * 0.85):
            for hp in hint_patterns:
                hp_lower = hp.lower().strip()
                if hp_lower == t or hp_lower == d or hp_lower in comb:
                    return coords[0], coords[1]

    # 2. Look for EditText node around the expected vertical position (default_ry +- 0.15)
    for node in root.iter('node'):
        cls = node.attrib.get('class', '').lower()
        if 'edittext' in cls:
            coords = parse_bounds(node.attrib.get('bounds', ''))
            if coords and abs(coords[1] - int(h * default_ry)) < int(h * 0.15):
                return coords[0], coords[1]

    # 3. Fallback to default relative position
    return int(w * default_rx), int(h * default_ry)

def find_element(root, search_pattern, by_class=None, exact=False):
    if root is None:
        return None
    pattern_lower = search_pattern.lower().strip()
    candidates = []
    w, h = get_screen_dimensions(root)
    
    for node in root.iter('node'):
        node_text = node.attrib.get('text', '').strip()
        node_desc = node.attrib.get('content-desc', '').strip()
        node_hint = node.attrib.get('hint', '').strip()
        node_res = node.attrib.get('resource-id', '').strip()
        node_cls = node.attrib.get('class', '').strip()
        is_clickable = node.attrib.get('clickable', 'false').lower() == 'true'
        
        if by_class and by_class.lower() not in node_cls.lower():
            continue
            
        text_lower = node_text.lower()
        desc_lower = node_desc.lower()
        hint_lower = node_hint.lower()
        res_lower = node_res.lower()

        if pattern_lower == "continue" and ("facebook" in text_lower or "instagram" in text_lower):
            continue

        is_exact_match = (text_lower == pattern_lower or desc_lower == pattern_lower or hint_lower == pattern_lower)
        is_substring_match = (pattern_lower in text_lower or pattern_lower in desc_lower or pattern_lower in res_lower or pattern_lower in hint_lower)
        
        if exact and not is_exact_match:
            continue
            
        if is_exact_match or is_substring_match:
            bounds = node.attrib.get('bounds', '')
            coords = parse_bounds(bounds)
            if coords:
                cx, cy = coords
                if cy > int(h * 0.91) or cy < int(h * 0.10):
                    continue
                matched_label = node_text or node_desc or node_hint or search_pattern
                score = 0
                if is_exact_match:
                    score += 100
                if len(matched_label) < 25:
                    score += 20
                if is_clickable or 'button' in node_cls.lower() or 'edittext' in node_cls.lower():
                    score += 10
                candidates.append((score, cx, cy, matched_label, bounds))
                
    if candidates:
        candidates.sort(key=lambda c: c[0], reverse=True)
        best = candidates[0]
        return best[1], best[2], best[3], best[4]
        
    return None

def tap_or_fallback_rel(root, search_text, rel_x, rel_y, label_name="element", exact=False, device_serial=None, instance_name=""):
    elem = find_element(root, search_text, exact=exact)
    if elem:
        x, y, found_label, bounds = elem
        log("ACTION", f"Found UI element '{found_label}' at {bounds}. Tapping ({x}, {y})...", instance_name=instance_name)
        run_adb_command(f"shell input tap {x} {y}", device_serial=device_serial, instance_name=instance_name)
        return True
    else:
        fx, fy = get_rel_coords(root, rel_x, rel_y)
        log("ACTION-FALLBACK", f"'{search_text}' not in XML. Tapping relative fallback ({fx}, {fy}) for {label_name}...", instance_name=instance_name)
        run_adb_command(f"shell input tap {fx} {fy}", device_serial=device_serial, instance_name=instance_name)
        return False

def find_instagram_landing_login(root):
    if root is None:
        return None
    w, h = get_screen_dimensions(root)
    # 1. Exact match for "Log In" node
    elem = find_element(root, "log in", exact=True)
    if elem:
        return elem[0], elem[1]
    
    # 2. Check nodes containing "log in" or "log in or sign up"
    for node in root.iter('node'):
        node_text = node.attrib.get('text', '').strip()
        node_desc = node.attrib.get('content-desc', '').strip()
        comb = (node_text + " " + node_desc).strip().lower()
        if "log in" in comb:
            coords = parse_bounds(node.attrib.get('bounds', ''))
            if coords:
                cx, cy = coords
                if int(h * 0.40) <= cy <= int(h * 0.90):
                    match = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', node.attrib.get('bounds', ''))
                    if match:
                        left, top, right, bottom = map(int, match.groups())
                        if "sign up" in comb or "or" in comb:
                            # "Log In" is on the left half of "Log In or sign up"
                            target_x = left + int((right - left) * 0.28)
                            return target_x, cy
                        return cx, cy
    return None

def find_instagram_login_button(root, elem_pwd=None):
    """
    Accurately locates the primary 'Log In' submit button on Instagram Login Page.
    Handles various button wrappers, classes, and avoids Facebook/Forgot links.
    """
    if root is None:
        return None
    w, h = get_screen_dimensions(root)
    min_y = (elem_pwd[1] + 15) if (elem_pwd and elem_pwd[1] > 0) else int(h * 0.45)
    max_y = int(h * 0.85)

    candidates = []
    for node in root.iter('node'):
        node_text = node.attrib.get('text', '').strip()
        node_desc = node.attrib.get('content-desc', '').strip()
        comb = (node_text + " " + node_desc).strip().lower()
        if not comb:
            continue
        # Strictly ignore Facebook login or Forgot password buttons/links
        if any(bad in comb for bad in ["facebook", "forgot", "sign up", "help", "switch"]):
            continue

        if "log in" in comb or "login" in comb:
            coords = parse_bounds(node.attrib.get('bounds', ''))
            if coords:
                cx, cy = coords
                if min_y <= cy <= max_y:
                    score = 0
                    if comb in ["log in", "login"]:
                        score += 100
                    if node.attrib.get('clickable', 'false').lower() == 'true':
                        score += 30
                    if 'button' in node.attrib.get('class', '').lower():
                        score += 20
                    # Prefer button closer to right below password field
                    if elem_pwd:
                        dist = abs(cy - (elem_pwd[1] + int(h * 0.08)))
                        score -= int(dist * 0.05)
                    candidates.append((score, cx, cy))

    if candidates:
        candidates.sort(key=lambda c: c[0], reverse=True)
        return candidates[0][1], candidates[0][2]

    # Direct search via find_element
    elem = find_element(root, "log in", exact=True) or find_element(root, "log in")
    if elem and min_y <= elem[1] <= max_y:
        return elem[0], elem[1]

    return None


def get_emulator_type_and_index(device_serial: str, instance_name: str = ""):
    """
    Identifies whether the target ADB device belongs to MuMu Player or LDPlayer,
    and calculates its zero-indexed instance number.
    Prioritizes explicit instance_name (e.g. 'LD-7', 'LDPlayer-7') if provided.
    """
    if instance_name:
        ld_m = re.search(r'LD(?:Player)?[-_]?(\d+)', instance_name, re.IGNORECASE)
        if ld_m:
            return 'ld', int(ld_m.group(1))
        mumu_m = re.search(r'MuMu(?:Device)?[-_]?(\d+)', instance_name, re.IGNORECASE)
        if mumu_m:
            return 'mumu', int(mumu_m.group(1))

    if not device_serial:
        return 'unknown', 0
    port_match = re.search(r':(\d+)', device_serial)
    if port_match:
        port = int(port_match.group(1))
        if port == 7555:
            return 'mumu', 0
        elif 16384 <= port <= 17000:
            return 'mumu', (port - 16384) // 32
        elif 5555 <= port <= 5700:
            return 'ld', (port - 5555) // 2
    emu_match = re.search(r'emulator-(\d+)', device_serial)
    if emu_match:
        port = int(emu_match.group(1))
        return 'ld', max(0, (port - 5554) // 2)
    return 'unknown', 0

def randomize_emulator_identity(device_serial: str, instance_name: str = ""):
    """
    Generates and applies a new IMEI, Android ID, and MAC Address for LDPlayer or MuMu Player.
    """
    emu_type, idx = get_emulator_type_and_index(device_serial, instance_name=instance_name)
    new_imei = "86" + "".join([str(random.randint(0, 9)) for _ in range(13)])
    new_android_id = "".join(random.choices("0123456789abcdef", k=16))
    new_mac = ":".join([f"{random.randint(0, 255):02x}" for _ in range(6)])

    log("IMEI-CHANGE", f"🎲 Randomizing identity for {device_serial} (Type: {emu_type.upper()}, Index: {idx})...", instance_name=instance_name)

    # 1. Update Android ID live via ADB
    run_adb_command(f"shell settings put secure android_id {new_android_id}", device_serial=device_serial, instance_name=instance_name, timeout=5)
    log("IMEI-CHANGE", f"📱 New Android ID set: {new_android_id}", instance_name=instance_name)

    # 2. Update hardware IMEI & MAC in emulator
    if emu_type == "mumu":
        mumu_mgr = find_mumu_manager()
        if mumu_mgr:
            try:
                subprocess.run(f'"{mumu_mgr}" simulation -v {idx} -sk imei -sv {new_imei}', shell=True, capture_output=True, timeout=5)
                subprocess.run(f'"{mumu_mgr}" simulation -v {idx} -sk android_id -sv {new_android_id}', shell=True, capture_output=True, timeout=5)
                subprocess.run(f'"{mumu_mgr}" simulation -v {idx} -sk mac_address -sv {new_mac}', shell=True, capture_output=True, timeout=5)
                log("IMEI-CHANGE", f"✨ [MuMu #{idx}] Hardware IMEI set: {new_imei} | MAC: {new_mac}", instance_name=instance_name)
            except Exception as e:
                log("IMEI-CHANGE", f"MuMu simulation error: {e}", instance_name=instance_name)

    elif emu_type == "ld":
        ldconsole = find_ldconsole()
        if ldconsole:
            try:
                subprocess.run(f'"{ldconsole}" modify --index {idx} --imei auto --androidid {new_android_id} --mac auto --imsi auto --simserial auto', shell=True, capture_output=True, timeout=6)
                log("IMEI-CHANGE", f"✨ [LDPlayer #{idx}] Hardware IMEI, IMSI, Android ID & MAC randomized via ldconsole!", instance_name=instance_name)
            except Exception as e:
                log("IMEI-CHANGE", f"LDPlayer modify error: {e}", instance_name=instance_name)

def recover_device_after_failures(device_serial: str, instance_name: str = ""):
    """
    Cleans up and resets an emulator device after repeated failures:
    - Kills stuck browser and uiautomator processes
    - Clears browser app cache & data
    - Removes old window dumps from sdcard
    - Randomizes Device IMEI, Android ID, and MAC address
    - Wakes up screen & sends Home keyevent
    - Reconnects ADB if port-based connection
    """
    log("DEVICE-RECOVER", f"Performing deep recovery on device {device_serial}...", instance_name=instance_name)
    try:
        run_adb_command(f"shell am force-stop {PACKAGE_NAME}", device_serial=device_serial, instance_name=instance_name, timeout=5)
        run_adb_command("shell pkill -f uiautomator", device_serial=device_serial, instance_name=instance_name, timeout=5)
        run_adb_command(f"shell pm clear {PACKAGE_NAME}", device_serial=device_serial, instance_name=instance_name, timeout=6)
        run_adb_command("shell rm -f /sdcard/window_dump_*.xml", device_serial=device_serial, instance_name=instance_name, timeout=5)

        # 🌟 Randomize Device Identity (IMEI / Android ID / MAC)
        randomize_emulator_identity(device_serial, instance_name=instance_name)

        run_adb_command("shell input keyevent 224", device_serial=device_serial, instance_name=instance_name, timeout=3)
        run_adb_command("shell input keyevent 3", device_serial=device_serial, instance_name=instance_name, timeout=3)
        if ":" in str(device_serial):
            run_adb_command(f"connect {device_serial}", device_serial=None, instance_name=instance_name, timeout=6)
        res = run_adb_command("devices", device_serial=None, instance_name=instance_name, timeout=6)
        if device_serial and device_serial in res:
            log("DEVICE-RECOVER", f"Device {device_serial} is ONLINE with fresh identity.", instance_name=instance_name)
        else:
            log("DEVICE-RECOVER", f"Device {device_serial} recovery completed.", instance_name=instance_name)
    except Exception as e:
        log("DEVICE-RECOVER", f"Recovery error on {device_serial}: {e}", instance_name=instance_name)

def reload_browser_page(root=None, device_serial=None, instance_name=""):
    log("RELOAD", "Page reload initiated...", instance_name=instance_name)
    if root is not None:
        for node in root.iter('node'):
            txt = node.attrib.get('text', '').strip().lower()
            desc = node.attrib.get('content-desc', '').strip().lower()
            if txt in ['reload', 'refresh'] or desc in ['reload', 'refresh']:
                coords = parse_bounds(node.attrib.get('bounds', ''))
                if coords:
                    run_adb_command(f"shell input tap {coords[0]} {coords[1]}", device_serial=device_serial, instance_name=instance_name)
                    time.sleep(3.5)
                    return True
                    
    fx, fy = get_rel_coords(root, 0.93, 0.075)
    run_adb_command(f"shell input tap {fx} {fy}", device_serial=device_serial, instance_name=instance_name)
    time.sleep(3.5)
    return True

def generate_totp_code(secret_key):
    if not secret_key:
        return ""
    clean_secret = re.sub(r'[^A-Z0-9]', '', str(secret_key)).upper().strip()
    if not clean_secret:
        return ""
    try:
        totp = pyotp.TOTP(clean_secret)
        return totp.now()
    except Exception:
        pass
    return ""

def get_android_clipboard(device_serial=None, instance_name=""):
    try:
        out = run_adb_command("shell cmd clipboard get", device_serial=device_serial, instance_name=instance_name)
        if out and "Error" not in out and "exception" not in out.lower():
            return out.strip()
    except Exception:
        pass
        
    try:
        dump = run_adb_command("shell dumpsys clipboard", device_serial=device_serial, instance_name=instance_name)
        for line in dump.splitlines():
            if "text=" in line or "text:" in line or "mText=" in line:
                parts = line.split("text=", 1) if "text=" in line else line.split("text:", 1)
                if len(parts) > 1:
                    clip_val = parts[1].strip()
                    if clip_val and clip_val != "null" and len(clip_val) > 5:
                        return clip_val
    except Exception:
        pass
        
    return ""

def open_via_site_info(root=None, device_serial=None, instance_name=""):
    """Tap Via Browser's SSL / Site Security checkmark icon [✓] in top address bar to open Site Info"""
    log("STATE-ACTION", "Tapping Via Browser checkmark / site info icon [✓]...", instance_name=instance_name)
    if root is not None:
        w, h = get_screen_dimensions(root)
        for node in root.iter('node'):
            bounds_str = node.attrib.get('bounds', '')
            coords = parse_bounds(bounds_str)
            if coords:
                cx, cy = coords
                if cy < int(h * 0.15) and cx < int(w * 0.20):
                    res_id = node.attrib.get('resource-id', '').lower()
                    cls = node.attrib.get('class', '').lower()
                    desc = node.attrib.get('content-desc', '').lower()
                    if 'site info' in desc or 'site' in desc or 'ssl' in res_id or 'security' in res_id or 'lock' in res_id or 'image' in cls or 'icon' in res_id or 'title' in res_id:
                        log("SITE-INFO", f"Found SSL/Site Info icon at {coords} ({desc}). Tapping...", instance_name=instance_name)
                        run_adb_command(f"shell input tap {cx} {cy}", device_serial=device_serial, instance_name=instance_name)
                        return True

    fx, fy = get_rel_coords(root, 0.067, 0.075)
    log("SITE-INFO", f"Tapping address bar checkmark icon at ({fx}, {fy})...", instance_name=instance_name)
    run_adb_command(f"shell input tap {fx} {fy}", device_serial=device_serial, instance_name=instance_name)
    return True

def extract_cookies_from_screen_texts(texts):
    """Extract cookie values directly from visible UI hierarchy texts"""
    cookie_parts = []
    for t in texts:
        if "=" in t and (";" in t or "sessionid" in t.lower() or "csrftoken" in t.lower() or "mid=" in t.lower() or "datr=" in t.lower() or "ds_user_id=" in t.lower()):
            cookie_parts.append(t.strip())
    if cookie_parts:
        return " ".join(cookie_parts)
    return ""

def extract_via_cookies(device_serial: str, instance_name: str = "", max_attempts: int = 4) -> Optional[str]:
    """
    Extracts Instagram cookies directly from Via Browser:
    1. Tap top-left site info / SSL checkmark [✓] icon
    2. Tap 'View Cookies' in popup
    3. Read node text or tap 'Copy' in dialog
    4. Validate cookies strictly (must contain sessionid=)
    5. Cleanly dismiss all dialogs
    """
    for attempt in range(1, max_attempts + 1):
        log("COOKIE-EXTRACT", f"[Attempt {attempt}/{max_attempts}] Opening Via Browser site info [✓]...", instance_name=instance_name)
        root = get_screen_hierarchy(device_serial=device_serial, instance_name=instance_name)
        open_via_site_info(root=root, device_serial=device_serial, instance_name=instance_name)
        time.sleep(1.2)

        # Check for site info popup
        root = get_screen_hierarchy(device_serial=device_serial, instance_name=instance_name)
        texts = extract_screen_texts(root) if root is not None else []
        blob = " ".join(texts).lower()

        # If popup not opened yet, try tapping relative again
        if "view cookies" not in blob and "cookies" not in blob and "view certificate" not in blob and "site configuration" not in blob:
            fx, fy = get_rel_coords(root, 0.067, 0.075)
            run_adb_command(f"shell input tap {fx} {fy}", device_serial=device_serial, instance_name=instance_name)
            time.sleep(1.2)
            root = get_screen_hierarchy(device_serial=device_serial, instance_name=instance_name)
            texts = extract_screen_texts(root) if root is not None else []
            blob = " ".join(texts).lower()

        # Tap 'View Cookies'
        elem_vc = find_element(root, "view cookies", exact=False) or find_element(root, "cookies", exact=False)
        if elem_vc:
            log("COOKIE-EXTRACT", f"Tapping 'View Cookies' at {elem_vc}...", instance_name=instance_name)
            run_adb_command(f"shell input tap {elem_vc[0]} {elem_vc[1]}", device_serial=device_serial, instance_name=instance_name)
        else:
            # On 540x960, View Cookies is centered at (270, 306) -> rel (0.50, 0.318)
            fx, fy = get_rel_coords(root, 0.50, 0.318)
            log("COOKIE-EXTRACT", f"Tapping fallback 'View Cookies' at ({fx}, {fy})...", instance_name=instance_name)
            run_adb_command(f"shell input tap {fx} {fy}", device_serial=device_serial, instance_name=instance_name)
        time.sleep(1.2)

        # Check for Cookies dialog
        root = get_screen_hierarchy(device_serial=device_serial, instance_name=instance_name)
        texts = extract_screen_texts(root) if root is not None else []
        
        # 1. Direct Node Text Extraction (Fastest & 100% Reliable in Via Browser)
        cookies = None
        if root is not None:
            for node in root.iter('node'):
                txt = node.attrib.get('text', '').strip()
                if 'csrftoken=' in txt or 'sessionid=' in txt or 'datr=' in txt:
                    cookies = txt
                    log("COOKIE-EXTRACT", f"✨ Direct UI Node extraction successful ({len(cookies)} chars)!", instance_name=instance_name)
                    break

        # 2. Fallback: If not found in node directly, click 'Copy' and retrieve from Android clipboard
        if not cookies or len(cookies) < 20:
            elem_copy = find_element(root, "copy", exact=True) or find_element(root, "copy")
            if elem_copy:
                log("COOKIE-EXTRACT", f"Tapping 'Copy' at {elem_copy}...", instance_name=instance_name)
                run_adb_command(f"shell input tap {elem_copy[0]} {elem_copy[1]}", device_serial=device_serial, instance_name=instance_name)
            else:
                # Copy button on 540x960 is at [389,597][485,674] -> center (437, 635) -> rel (0.81, 0.66)
                fx, fy = get_rel_coords(root, 0.81, 0.66)
                log("COOKIE-EXTRACT", f"Tapping fallback 'Copy' at ({fx}, {fy})...", instance_name=instance_name)
                run_adb_command(f"shell input tap {fx} {fy}", device_serial=device_serial, instance_name=instance_name)
            time.sleep(0.6)

            cookies = get_android_clipboard(device_serial=device_serial, instance_name=instance_name)
            if not cookies or len(cookies) < 15:
                cookies = extract_cookies_from_screen_texts(texts)

        # STRICT VALIDATION: Verified Instagram cookies MUST have sessionid=
        if cookies and "sessionid=" in cookies.lower():
            log("COOKIE-EXTRACT", f"🎉 Successfully extracted verified Instagram cookies ({len(cookies)} chars)!\nPreview: {cookies[:80]}...", instance_name=instance_name)
            # Dismiss dialog & popup cleanly (send Back key twice)
            run_adb_command("shell input keyevent 4", device_serial=device_serial, instance_name=instance_name)
            time.sleep(0.4)
            run_adb_command("shell input keyevent 4", device_serial=device_serial, instance_name=instance_name)
            time.sleep(0.4)
            return cookies.strip()
        elif cookies:
            log("COOKIE-WARN", f"Attempt {attempt} got cookies but missing 'sessionid=' ({cookies[:50]}...). Login session not fully established yet. Retrying in 2.0s...", instance_name=instance_name)
            # Dismiss modal and retry
            run_adb_command("shell input keyevent 4", device_serial=device_serial, instance_name=instance_name)
            time.sleep(0.4)
            run_adb_command("shell input keyevent 4", device_serial=device_serial, instance_name=instance_name)
            time.sleep(2.0)
        else:
            log("COOKIE-WARN", f"Attempt {attempt} got empty cookies. Retrying in 1.5s...", instance_name=instance_name)
            run_adb_command("shell input keyevent 4", device_serial=device_serial, instance_name=instance_name)
            time.sleep(0.4)
            run_adb_command("shell input keyevent 4", device_serial=device_serial, instance_name=instance_name)
            time.sleep(1.5)

    return None

def generate_random_2fa_key() -> str:
    """Generates a standard 16-character base32 Instagram 2FA Secret Key accepted by all Telegram bots."""
    return ''.join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567", k=16))


def is_valid_b32_secret(secret_str: str) -> bool:
    if not secret_str:
        return False
    clean = re.sub(r'[^A-Z0-9]', '', str(secret_str).upper().strip())
    # Instagram/Meta 2FA secret keys can be 16, 26, or 32 base32 characters (RFC 6238)
    if len(clean) not in [16, 26, 32]:
        return False
    if clean.isdigit():
        return False
    forbidden_words = [
        "CHOOSE", "CONFIRM", "PROTECT", "ACCOUNT", "AUTHENTICAT", "INSTRUCT",
        "DOWNLOAD", "BARCODE", "RECOGNIZE", "DEVICE", "SETTING", "PASSWORD",
        "INSTAGRAM", "GOOGLE", "MOBILE", "RECOMMEND", "CONTINUE", "SECURITY",
        "DETAILS", "PERSONAL", "PROFILE", "WELCOME", "ENTERCODE", "CANCEL",
        "RELOAD", "REFRESH", "TERMS", "POLICY", "HELP", "SETUP", "ETUP", "SCAN", "COPY"
    ]
    for w in forbidden_words:
        if w in clean:
            return False
    try:
        totp = pyotp.TOTP(clean)
        code = totp.now()
        if code and len(code) == 6 and code.isdigit():
            return True
    except Exception:
        return False
    return True

def extract_2fa_secret_and_copy(root, device_serial=None, instance_name=""):
    secret_key = ""
    w, h = get_screen_dimensions(root)

    def scan_qr_from_screen():
        """Fast, 100% accurate QR code extraction directly from screen using zxing-cpp."""
        if zxingcpp is None:
            return ""
        try:
            safe_ser = device_serial.replace(':', '_').replace('.', '_').replace('-', '_') if device_serial else "default"
            sd_path = f"/sdcard/qr_scan_{safe_ser}.png"
            local_path = os.path.join(BASE_DIR, f"qr_scan_{safe_ser}.png")
            run_adb_command(f"shell screencap -p {sd_path}", device_serial=device_serial, instance_name=instance_name, timeout=5)
            run_adb_command(f"pull {sd_path} \"{local_path}\"", device_serial=device_serial, instance_name=instance_name, timeout=5)
            if os.path.exists(local_path) and os.path.getsize(local_path) > 1000:
                img = cv2.imread(local_path) if cv2 is not None else Image.open(local_path)
                barcodes = zxingcpp.read_barcodes(img)
                for b in barcodes:
                    txt = b.text or ""
                    m_sec = re.search(r'[?&]secret=([A-Z0-9]+)', txt, re.IGNORECASE)
                    if m_sec:
                        cand = m_sec.group(1).upper()
                        if is_valid_b32_secret(cand):
                            try:
                                os.remove(local_path)
                            except Exception:
                                pass
                            return cand
                try:
                    os.remove(local_path)
                except Exception:
                    pass
        except Exception as qr_err:
            log("2FA-DEBUG", f"QR decode notice: {qr_err}", instance_name=instance_name)
        return ""

    def find_key_in_texts(texts_list):
        if not texts_list:
            return ""

        # Priority 1: Check individual UI elements that directly contain valid 16, 26, or 32-char key
        for t in texts_list:
            cleaned = re.sub(r'[^A-Z0-9]', '', t.upper())
            if len(cleaned) in [16, 26, 32] and is_valid_b32_secret(cleaned):
                return cleaned

        # Priority 2: Check 4 groups of 4 (standard 16-char layout, e.g. "MPSF 5IHI ZNDU T5O4")
        for t in texts_list:
            m_4g = re.search(r'\b([A-Z0-9]{4}(?:[\s\n\-]+[A-Z0-9]{4}){3})\b', t.upper())
            if m_4g:
                c = re.sub(r'[^A-Z0-9]', '', m_4g.group(1))
                if is_valid_b32_secret(c):
                    return c

        # Priority 3: Check 8 groups of 4 (standard 32-char layout)
        for t in texts_list:
            m_8g = re.search(r'\b([A-Z0-9]{4}(?:[\s\n\-]+[A-Z0-9]{4}){7})\b', t.upper())
            if m_8g:
                c = re.sub(r'[^A-Z0-9]', '', m_8g.group(1))
                if is_valid_b32_secret(c):
                    return c

        # Priority 4: Check consecutive elements with 16-chars each (standard 2-line display)
        for i in range(len(texts_list) - 1):
            c1 = re.sub(r'[^A-Z0-9]', '', texts_list[i].upper())
            c2 = re.sub(r'[^A-Z0-9]', '', texts_list[i+1].upper())
            if len(c1) == 16 and len(c2) == 16:
                comb = c1 + c2
                if is_valid_b32_secret(comb):
                    return comb

        # Priority 5: Full joined blob search for 8 groups or 4 groups of 4
        blob = " ".join(texts_list).upper()
        m = re.search(r'\b([A-Z0-9]{4}(?:[\s\n\-]+[A-Z0-9]{4}){7})\b', blob)
        if m:
            c = re.sub(r'[^A-Z0-9]', '', m.group(1))
            if is_valid_b32_secret(c):
                return c

        m = re.search(r'\b([A-Z0-9]{4}(?:[\s\n\-]+[A-Z0-9]{4}){3})\b', blob)
        if m:
            c = re.sub(r'[^A-Z0-9]', '', m.group(1))
            if is_valid_b32_secret(c):
                return c

        # Priority 6: Check for 2 groups of 16 base32 chars in blob
        m = re.search(r'\b([A-Z0-9]{16}[\s\n\-]+[A-Z0-9]{16})\b', blob)
        if m:
            c = re.sub(r'[^A-Z0-9]', '', m.group(1))
            if is_valid_b32_secret(c):
                return c

        # Priority 7: Check for exact 32, 26, or 16 base32 token in blob
        for length in [32, 26, 16]:
            m = re.search(rf'\b([A-Z2-7]{{{length}}})\b', blob)
            if m:
                c = m.group(1)
                if is_valid_b32_secret(c):
                    return c

        return ""

    def find_real_copy_button(node_root):
        if node_root is None:
            return None
        for node in node_root.iter('node'):
            t = node.attrib.get('text', '').strip().lower()
            d = node.attrib.get('content-desc', '').strip().lower()
            comb = t or d
            if len(comb) <= 25:
                if comb in ["copy key", "copy the key", "copy", "copy code", "copy this key"]:
                    coords = parse_bounds(node.attrib.get('bounds', ''))
                    if coords:
                        return coords
                elif "copy key" in comb or "copy the key" in comb or comb == "copy":
                    coords = parse_bounds(node.attrib.get('bounds', ''))
                    if coords:
                        return coords
        return None

    # Step 0: Try scanning QR code directly from initial screen
    qr_key = scan_qr_from_screen()
    if qr_key:
        log("2FA-EXTRACT", f"✔ Found Secret Key via QR Code ({len(qr_key)} chars): {qr_key}", instance_name=instance_name)
        return qr_key

    # Step 1: Check if full key (16 or 32 chars) is already visible in screen texts
    if root is not None:
        texts = extract_screen_texts(root)
        found = find_key_in_texts(texts)
        if found:
            secret_key = found
            log("2FA-EXTRACT", f"✔ Found complete Secret Key in UI text ({len(secret_key)} chars): {secret_key}", instance_name=instance_name)
            return secret_key

    # Step 2: Try tapping Copy key button
    btn_copy = find_real_copy_button(root)
    if btn_copy:
        log("2FA-ACTION", f"Tapping 'Copy key' button at ({btn_copy[0]}, {btn_copy[1]})...", instance_name=instance_name)
        run_adb_command(f"shell input tap {btn_copy[0]} {btn_copy[1]}", device_serial=device_serial, instance_name=instance_name)
        time.sleep(0.5)
        clip = get_android_clipboard(device_serial=device_serial, instance_name=instance_name)
        if clip:
            clean_clip = re.sub(r'[^A-Z0-9]', '', clip.upper())
            if is_valid_b32_secret(clean_clip):
                secret_key = clean_clip
                log("2FA-CLIPBOARD", f"✔ Secret Key recovered from clipboard ({len(secret_key)} chars): '{secret_key}'", instance_name=instance_name)
                return secret_key
            elif len(clean_clip) == 16:
                if root is not None:
                    texts = extract_screen_texts(root)
                    for i, t in enumerate(texts):
                        c1 = re.sub(r'[^A-Z0-9]', '', t.upper())
                        if c1 == clean_clip and i + 1 < len(texts):
                            c2 = re.sub(r'[^A-Z0-9]', '', texts[i+1].upper())
                            if len(c2) == 16:
                                comb = c1 + c2
                                if is_valid_b32_secret(comb):
                                    secret_key = comb
                                    log("2FA-CLIPBOARD", f"✔ Secret Key paired from clipboard + UI text (32 chars): '{secret_key}'", instance_name=instance_name)
                                    return secret_key

    # Step 3: Scroll down past QR code to reveal full secret key / buttons
    log("2FA-ACTION", "Scrolling down past QR code to reveal full secret key / buttons...", instance_name=instance_name)
    run_adb_command(f"shell input swipe {int(w*0.50)} {int(h*0.75)} {int(w*0.50)} {int(h*0.25)} 300", device_serial=device_serial, instance_name=instance_name)
    time.sleep(0.8)
    root = get_screen_hierarchy(device_serial=device_serial, instance_name=instance_name)
    
    if root is not None:
        texts = extract_screen_texts(root)
        found = find_key_in_texts(texts)
        if found:
            secret_key = found
            log("2FA-EXTRACT", f"✔ Found Secret Key in UI text after scroll ({len(secret_key)} chars): {secret_key}", instance_name=instance_name)
            return secret_key

    btn_copy = find_real_copy_button(root)
    if btn_copy:
        log("2FA-ACTION", f"Found 'Copy key' after scroll at ({btn_copy[0]}, {btn_copy[1]}). Tapping...", instance_name=instance_name)
        run_adb_command(f"shell input tap {btn_copy[0]} {btn_copy[1]}", device_serial=device_serial, instance_name=instance_name)
        time.sleep(0.5)
        clip = get_android_clipboard(device_serial=device_serial, instance_name=instance_name)
        if clip:
            clean_clip = re.sub(r'[^A-Z0-9]', '', clip.upper())
            if is_valid_b32_secret(clean_clip):
                secret_key = clean_clip
                log("2FA-CLIPBOARD", f"✔ Secret Key recovered from clipboard: '{secret_key}'", instance_name=instance_name)
                return secret_key

    # Step 4: If still not found, scroll back up to re-align QR code and try QR scanner again
    if not secret_key:
        run_adb_command(f"shell input swipe {int(w*0.50)} {int(h*0.30)} {int(w*0.50)} {int(h*0.75)} 300", device_serial=device_serial, instance_name=instance_name)
        time.sleep(0.6)
        qr_key2 = scan_qr_from_screen()
        if qr_key2:
            log("2FA-EXTRACT", f"✔ Found Secret Key via QR Code after scroll reset ({len(qr_key2)} chars): {qr_key2}", instance_name=instance_name)
            return qr_key2

    return secret_key

def find_instagram_account_tile(root, email="", username=""):
    if root is None:
        return None
    w, h = get_screen_dimensions(root)
    email_lower = email.lower().strip() if email else ""
    user_lower = username.lower().strip() if username else ""
    email_prefix = email_lower.split("@")[0] if "@" in email_lower else ""

    FORBIDDEN_WORDS = [
        "find another", "find account", "forgot", "forget", "forgotten",
        "find your account", "another account", "not your account", "help",
        "close", "cancel", "sign up", "log in to another", "search for your account"
    ]

    # Priority 1: Match by email, email prefix, or username in nodes inside card area
    for node in root.iter('node'):
        node_text = node.attrib.get('text', '').strip().lower()
        node_desc = node.attrib.get('content-desc', '').strip().lower()
        combined = (node_text + " " + node_desc).strip()
        if not combined:
            continue
        if any(f_word in combined for f_word in FORBIDDEN_WORDS):
            continue

        is_match = False
        if email_lower and email_lower in combined:
            is_match = True
        elif email_prefix and len(email_prefix) >= 4 and email_prefix in combined:
            is_match = True
        elif user_lower and len(user_lower) >= 4 and user_lower in combined:
            is_match = True
        elif "@" in combined and any(domain in combined for domain in [".net", ".td", ".cx", ".com", ".org", ".me", ".io", ".uqu.me"]):
            is_match = True

        if is_match:
            bounds = node.attrib.get('bounds', '')
            coords = parse_bounds(bounds)
            if coords and int(h * 0.60) < coords[1] < int(h * 0.92):
                return coords[0], coords[1], combined, bounds

    # Priority 2: Look for node right below the "OR" divider
    or_y = None
    for node in root.iter('node'):
        txt = node.attrib.get('text', '').strip()
        if "OR" in txt.upper() and len(txt.strip()) <= 15:
            c = parse_bounds(node.attrib.get('bounds', ''))
            if c:
                or_y = c[1]
                break

    if or_y and or_y < int(h * 0.85):
        for node in root.iter('node'):
            c = parse_bounds(node.attrib.get('bounds', ''))
            if c and c[1] > or_y + 15 and c[1] < int(h * 0.92):
                txt = node.attrib.get('text', '').strip().lower()
                desc = node.attrib.get('content-desc', '').strip().lower()
                comb = txt + " " + desc
                if not any(f_word in comb for f_word in FORBIDDEN_WORDS):
                    return c[0], c[1], f"below_or_{txt[:15]}", node.attrib.get('bounds', '')

    # Priority 3: Center of bottom Meta account card [0.83h]
    return int(w * 0.50), int(h * 0.83), "fallback_card_center", ""


def detect_current_page(root):
    if root is None:
        return "UNKNOWN_SCREEN", []
    texts = extract_screen_texts(root)
    text_blob = " ".join(texts).lower()

    if not text_blob.strip():
        return "GENERIC_PAGE", texts

    # Check if page is just loading the top toolbar without content
    meaningful_texts = [t for t in texts if t.strip().lower() not in ['site info', 'two-factor authentication · account settings | meta', 'reload', 'tabs', 'home', 'bookmarks', 'menu', 'back', 'forward', '2', '1', '']]
    if not meaningful_texts and len(texts) <= 4:
        return "GENERIC_PAGE", texts

    if ("http_transport_error" in text_blob 
          or "transport_error" in text_blob 
          or "network request encountered error" in text_blob
          or "encountered error http" in text_blob):
        return "HTTP_TRANSPORT_ERROR_PAGE", texts

    if ("can't make this change at the moment" in text_blob 
        or "cant make this change at the moment" in text_blob 
        or "cannot make this change" in text_blob
        or "you don't usually use" in text_blob
        or "used this device for a while" in text_blob
        or ("keep your account safe" in text_blob and "device" in text_blob)):
        return "CANNOT_MAKE_CHANGE_POPUP", texts
    elif ("we suspect automated behavior on your account" in text_blob 
          or "suspect automated behavior" in text_blob 
          or "automated behavior" in text_blob 
          or "automated activity" in text_blob 
          or ("automated" in text_blob and "dismiss" in text_blob)):
        return "SUSPECT_AUTOMATED_BEHAVIOR_PAGE", texts
    elif ("this page isn't available right now" in text_blob
          or "this page isn't available" in text_blob
          or "this page is not available" in text_blob
          or "page isn't available right now" in text_blob
          or "page isn't available" in text_blob
          or "page is not available" in text_blob
          or "try reloading this page" in text_blob
          or ("technical error" in text_blob and "reload" in text_blob)
          or "reload page" in text_blob):
        return "PAGE_NOT_AVAILABLE_ERROR_PAGE", texts
    elif ("use another profile" in text_blob 
          or "switch accounts" in text_blob 
          or ("continue" in text_blob and "create new account" in text_blob)
          or ("continue as" in text_blob and "instagram" in text_blob)):
        return "INSTAGRAM_CONTINUE_PROFILE_PAGE", texts
    elif ("re-enter your password" in text_blob
          or "enter your password" in text_blob
          or "enter password" in text_blob
          or ("for your security" in text_blob and "password" in text_blob)
          or "confirm your password" in text_blob):
        return "REENTER_PASSWORD_PAGE", texts
    elif "this content is no longer available" in text_blob or "content is no longer available" in text_blob or "the content you requested cannot be displayed" in text_blob:
        return "CONTENT_NO_LONGER_AVAILABLE_PAGE", texts
    elif ("check your email" in text_blob
          or "enter the code we sent to" in text_blob
          or "get a new code" in text_blob
          or "we can send a new code in" in text_blob):
        return "TWO_FACTOR_CHECK_EMAIL_PAGE", texts
    elif ("set up extra protection for your meta account" in text_blob or "extra protection for your meta account" in text_blob or "extra protection for your account" in text_blob or ("extra protection" in text_blob and ("get started" in text_blob or "meta account" in text_blob))) and "instagram" not in text_blob and "choose an account" not in text_blob:
        return "TWO_FACTOR_EXTRA_PROTECTION_PAGE", texts
    elif ("help protect your account" in text_blob
          or "help protect" in text_blob
          or "choose how to confirm it's you" in text_blob
          or "choose how to confirm" in text_blob
          or ("authentication app" in text_blob and "sms or whatsapp" in text_blob)
          or ("authentication app" in text_blob and "recommended" in text_blob and "scan" not in text_blob)):
        return "TWO_FACTOR_CHOOSE_METHOD_PAGE", texts
    elif ("instructions for setup" in text_blob
          or "scan this barcode/qr code" in text_blob
          or "scan this barcode" in text_blob
          or "scan this qr code" in text_blob
          or "scan this barcode/qr code or copy the key" in text_blob
          or "copy the key" in text_blob
          or "or copy the key" in text_blob
          or ("instructions" in text_blob and ("setup" in text_blob or "barcode" in text_blob or "qr" in text_blob))):
        return "TWO_FACTOR_INSTRUCTIONS_PAGE", texts
    elif ("get your code from your authentication app" in text_blob
          or "enter the 6-digit code" in text_blob
          or "enter confirmation code" in text_blob
          or "enter 6-digit code" in text_blob
          or "enter code generated" in text_blob
          or ("enter code" in text_blob and "next" in text_blob and "instructions for setup" not in text_blob and "scan this" not in text_blob and "download an" not in text_blob)):
        return "TWO_FACTOR_ENTER_CODE_PAGE", texts
    elif "copy key" in text_blob or "enter key in authenticator app" in text_blob or "set up on same device" in text_blob or "enter this key into" in text_blob:
        return "TWO_FACTOR_COPY_KEY_PAGE", texts
    elif "something went wrong" in text_blob or "there was a problem" in text_blob or "try again later" in text_blob:
        return "ACCOUNT_ERROR_PAGE", texts
    elif "incorrect password" in text_blob or "wrong password" in text_blob:
        return "INCORRECT_PASSWORD_POPUP", texts
    elif "we couldn't find an account" in text_blob or "user not found" in text_blob or "can't find account" in text_blob:
        return "CANNOT_FIND_ACCOUNT_POPUP", texts
    elif "choose an account to set up two-factor authentication" in text_blob or ("two-factor authentication" in text_blob and ("choose an account" in text_blob or "instagram" in text_blob) and "instructions" not in text_blob and "help protect" not in text_blob and "is on" not in text_blob) or ("extra protection" in text_blob and ("instagram" in text_blob or "choose an account" in text_blob)):
        return "TWO_FACTOR_CHOOSE_ACCOUNT_PAGE", texts
    elif (("two-factor authentication is on" in text_blob
           or "two-factor is on" in text_blob
           or "2-factor authentication is on" in text_blob
           or "authentication app is on" in text_blob
           or "two-step verification is on" in text_blob
           or "authenticator app is on" in text_blob
           or "two-factor authentication turned on" in text_blob
           or "two-factor authentication enabled" in text_blob
           or "two-factor authentication is set up" in text_blob
           or "your two-factor authentication is set up" in text_blob
           or ("backup codes" in text_blob and "two-factor" in text_blob)
           or ("turn off two-factor" in text_blob or "manage two-factor" in text_blob))
          and "instructions" not in text_blob
          and "download an authentication" not in text_blob
          and "scan this" not in text_blob
          and "barcode" not in text_blob
          and "qr code" not in text_blob
          and "check your email" not in text_blob
          and "extra protection" not in text_blob
          and "help protect" not in text_blob
          and "choose how to confirm" not in text_blob):
        return "TWO_FACTOR_SUCCESS_PAGE", texts
    elif ("save your login info" in text_blob 
          or "save login info" in text_blob 
          or "won't need to enter it next time" in text_blob 
          or "wont need to enter it next time" in text_blob 
          or ("save" in text_blob and "not now" in text_blob)
          or "save info" in text_blob):
        return "INSTAGRAM_SAVE_INFO_PAGE", texts
    elif ("suggested for you" in text_blob 
          or "discover people" in text_blob 
          or "follow 5 accounts" in text_blob 
          or "follow accounts to see" in text_blob 
          or ("suggested" in text_blob and "follow" in text_blob)):
        return "INSTAGRAM_SUGGESTED_PAGE", texts
    elif "connect to facebook" in text_blob or "find friends to follow" in text_blob:
        return "INSTAGRAM_CONNECT_FB_PAGE", texts
    elif "save password on" in text_blob or ("save password" in text_blob and "cancel" in text_blob):
        return "INSTAGRAM_SAVE_PASSWORD_POPUP", texts
    elif ("find your account" in text_blob 
          or "enter your mobile number" in text_blob 
          or "i think my account is hacked" in text_blob 
          or ("can't log in" in text_blob and ("facebook" in text_blob or "find" in text_blob))
          or ("forgot password" in text_blob and ("facebook" in text_blob or "mobile number" in text_blob))):
        return "FACEBOOK_FIND_ACCOUNT_PAGE", texts
    elif "no instagram account found" in text_blob or "no instagram profile found" in text_blob or "matched a meta account" in text_blob or "matched an existing meta account" in text_blob or "find another account" in text_blob or "account we found" in text_blob:
        return "INSTAGRAM_NO_ACCOUNT_FOUND", texts
    elif "what's your name" in text_blob or "whats your name" in text_blob:
        return "INSTAGRAM_NAME_PAGE", texts
    elif "create a username" in text_blob or "create username" in text_blob:
        return "INSTAGRAM_USERNAME_PAGE", texts
    elif "allow the following" in text_blob or "create an instagram account with your meta account" in text_blob or "allow and continue" in text_blob:
        return "INSTAGRAM_ALLOW_CONTINUE_PAGE", texts
    elif "agree to instagram's terms" in text_blob or "agree to instagram" in text_blob or ("i agree" in text_blob and ("terms" in text_blob or "policies" in text_blob)):
        return "INSTAGRAM_AGREE_TERMS_PAGE", texts
    elif "allow all cookies" in text_blob or "only allow essential cookies" in text_blob or "decline optional cookies" in text_blob:
        return "INSTAGRAM_COOKIE_PAGE", texts
    elif "share everyday moments" in text_blob or "open instagram" in text_blob or "log in or sign up" in text_blob:
        return "INSTAGRAM_LANDING_PAGE", texts
    elif "username, email or mobile number" in text_blob or ("forgot password?" in text_blob and "log in" in text_blob) or ("phone number, username, or email" in text_blob) or ("log in" in text_blob and ("password" in text_blob or "don't have an account" in text_blob)):
        return "INSTAGRAM_LOGIN_PAGE", texts
    elif "welcome" in text_blob and ("agree" in text_blob or "terms" in text_blob):
        return "BROWSER_TERMS_PAGE", texts
    elif "view cookies" in text_blob or "view certificate" in text_blob or "site configuration" in text_blob:
        return "VIA_SITE_INFO_POPUP", texts
    elif "cookies for" in text_blob or ("cookies" in text_blob and ("copy" in text_blob or "delete" in text_blob)):
        return "VIA_COOKIES_DIALOG", texts
    elif "turn on notifications" in text_blob or "know when people follow you" in text_blob:
        return "INSTAGRAM_NOTIFICATIONS_PAGE", texts
    elif "accounts/registered" in text_blob or "registered" in text_blob:
        return "INSTAGRAM_REGISTERED_PAGE", texts
    else:
        return "GENERIC_PAGE", texts

# ==============================================================================
# 🛠️ INSTAGRAM & 2FA AUTOMATION PIPELINE (Matching 1tasklytometatoinsta)
# ==============================================================================
def update_username_in_accounts_center(device_serial: str, target_username: str, instance_name=""):
    log("UNAME-UPDATE", f"Starting username change to '{target_username}' via Accounts Center ({ACCOUNTS_OVERVIEW_URL})...", instance_name=instance_name)
    run_adb_command(f'shell am start -a android.intent.action.VIEW -d "{ACCOUNTS_OVERVIEW_URL}" {PACKAGE_NAME}', device_serial=device_serial, instance_name=instance_name)
    time.sleep(1.8)

    stage = "PROFILES_PAGE"
    start_time = time.time()
    max_wait = 30

    while time.time() - start_time < max_wait:
        root = get_screen_hierarchy(device_serial=device_serial, instance_name=instance_name)
        if root is None:
            time.sleep(0.4)
            continue

        texts = extract_screen_texts(root)
        text_blob = " ".join(texts).lower()
        w, h = get_screen_dimensions(root)

        if stage == "PROFILES_PAGE":
            insta_tile = None
            for node in root.iter('node'):
                t = node.attrib.get('text', '').strip()
                d = node.attrib.get('content-desc', '').strip()
                comb = (t + " " + d).lower()
                if "instagram" in comb and "meta" not in comb:
                    coords = parse_bounds(node.attrib.get('bounds', ''))
                    if coords and coords[1] < int(h * 0.90):
                        insta_tile = coords
                        break

            if insta_tile:
                log("UNAME-UPDATE", f"Found Instagram profile card at {insta_tile}. Tapping...", instance_name=instance_name)
                run_adb_command(f"shell input tap {insta_tile[0]} {insta_tile[1]}", device_serial=device_serial, instance_name=instance_name)
                stage = "PROFILE_MENU"
                time.sleep(1.2)
            elif "profiles" in text_blob or "your account" in text_blob or "account settings" in text_blob:
                fx, fy = get_rel_coords(root, 0.50, 0.68)
                log("UNAME-UPDATE", f"Tapping fallback Instagram profile card at ({fx}, {fy})...", instance_name=instance_name)
                run_adb_command(f"shell input tap {fx} {fy}", device_serial=device_serial, instance_name=instance_name)
                stage = "PROFILE_MENU"
                time.sleep(1.2)
            else:
                time.sleep(0.6)

        elif stage == "PROFILE_MENU":
            elem_uname = find_element(root, "username", exact=True) or find_element(root, "username")
            if elem_uname:
                log("UNAME-UPDATE", f"Found 'Username' menu item at ({elem_uname[0]}, {elem_uname[1]}). Tapping...", instance_name=instance_name)
                run_adb_command(f"shell input tap {elem_uname[0]} {elem_uname[1]}", device_serial=device_serial, instance_name=instance_name)
                stage = "EDIT_USERNAME"
                time.sleep(1.2)
            elif "name" in text_blob and "avatar" in text_blob:
                fx, fy = get_rel_coords(root, 0.50, 0.69)
                log("UNAME-UPDATE", f"Tapping fallback 'Username' menu item at ({fx}, {fy})...", instance_name=instance_name)
                run_adb_command(f"shell input tap {fx} {fy}", device_serial=device_serial, instance_name=instance_name)
                stage = "EDIT_USERNAME"
                time.sleep(1.2)
            else:
                time.sleep(0.6)

        elif stage == "EDIT_USERNAME":
            log("UNAME-UPDATE", f"Entering target Taskly username '{target_username}'...", instance_name=instance_name)
            elem_edit = find_element(root, "username", by_class="EditText") or find_password_field(root)
            if elem_edit:
                run_adb_command(f"shell input tap {elem_edit[0]} {elem_edit[1]}", device_serial=device_serial, instance_name=instance_name)
            else:
                fx, fy = get_rel_coords(root, 0.50, 0.35)
                run_adb_command(f"shell input tap {fx} {fy}", device_serial=device_serial, instance_name=instance_name)
            
            time.sleep(0.3)
            clear_input_field(length=40, device_serial=device_serial, instance_name=instance_name)
            time.sleep(0.2)
            type_text(target_username, device_serial=device_serial, instance_name=instance_name, human_like=True)
            time.sleep(0.3)
            hide_keyboard(device_serial=device_serial, instance_name=instance_name)
            time.sleep(0.2)

            root = get_screen_hierarchy(device_serial=device_serial, instance_name=instance_name)
            log("UNAME-UPDATE", "Tapping 'Done' button...", instance_name=instance_name)
            elem_done = (find_element(root, "done", exact=True)
                         or find_element(root, "done")
                         or find_element(root, "save", exact=True)
                         or find_element(root, "save")
                         or find_element(root, "change username"))
            if elem_done:
                run_adb_command(f"shell input tap {elem_done[0]} {elem_done[1]}", device_serial=device_serial, instance_name=instance_name)
            else:
                fx, fy = get_rel_coords(root, 0.50, 0.88)
                run_adb_command(f"shell input tap {fx} {fy}", device_serial=device_serial, instance_name=instance_name)
            
            time.sleep(1.5)
            root = get_screen_hierarchy(device_serial=device_serial, instance_name=instance_name)
            p_name, _ = detect_current_page(root)
            if p_name == "CANNOT_MAKE_CHANGE_POPUP":
                log("UNAME-ERR", f"Encountered restriction '{p_name}'. Aborting...", instance_name=instance_name)
                return False

            log("UNAME-UPDATE", f"✔ Username successfully updated to '{target_username}' in Accounts Center!", instance_name=instance_name)
            stage = "DONE"
            break

    return True

def fetch_email_security_code(email: str, password: str, mail_token=None, ninja_client=None, max_wait_sec: int = 75, expected_digits=8, instance_name: str = "") -> Optional[str]:
    """
    Universal email security code retriever:
    1. Checks TempMail Ninja client if active.
    2. Falls back to Mail.td / email_service inbox polling.
    Accepts expected_digits (defaults to 8-digit security verification code for 2FA).
    """
    log("EMAIL-CODE", f"Fetching email security code for {email} ({expected_digits}-digit expected, timeout {max_wait_sec}s)...", instance_name=instance_name)
    if ninja_client:
        try:
            log("NINJA-OTP", f"Polling TempMail Ninja for {expected_digits}-digit security code ({email})...", instance_name=instance_name)
            code = ninja_client.wait_for_otp(timeout=max_wait_sec, expected_digits=expected_digits, reset_latest=True)
            if code:
                clean_code = re.sub(r'\D', '', str(code).strip())
                if expected_digits:
                    if len(clean_code) == expected_digits:
                        log("NINJA-OTP", f"✔ Received verified {len(clean_code)}-digit security code from Ninja: {clean_code}", instance_name=instance_name)
                        return clean_code
                    else:
                        log("NINJA-WARN", f"Ignored code with length {len(clean_code)} != expected {expected_digits}: {clean_code}", instance_name=instance_name)
                elif len(clean_code) in [6, 8]:
                    log("NINJA-OTP", f"✔ Received verified {len(clean_code)}-digit security code from Ninja: {clean_code}", instance_name=instance_name)
                    return clean_code
                else:
                    log("NINJA-WARN", f"Ignored unexpected length code from Ninja: {code} (length: {len(clean_code)})", instance_name=instance_name)
        except Exception as e:
            log("NINJA-ERR", f"Error polling Ninja TempMail: {e}", instance_name=instance_name)

    code = fallback_fetch_otp(email, password, token=mail_token, max_wait_sec=max_wait_sec, expected_digits=expected_digits, instance_name=instance_name)
    if code:
        clean_code = re.sub(r'\D', '', str(code).strip())
        if expected_digits:
            if len(clean_code) == expected_digits:
                log("EMAIL-CODE", f"✔ Received verified {len(clean_code)}-digit security code from mail service: {clean_code}", instance_name=instance_name)
                return clean_code
            else:
                log("EMAIL-WARN", f"Ignored code with length {len(clean_code)} != expected {expected_digits}: {clean_code}", instance_name=instance_name)
        elif len(clean_code) in [6, 8]:
            log("EMAIL-CODE", f"✔ Received verified {len(clean_code)}-digit security code from mail service: {clean_code}", instance_name=instance_name)
            return clean_code
        else:
            log("EMAIL-WARN", f"Ignored unexpected length fallback code: {code} (length: {len(clean_code)})", instance_name=instance_name)
    return None

SUGGESTED_PEOPLE_URL = "https://www.instagram.com/explore/people/"

def find_all_follow_buttons(root):
    """
    Finds all visible 'Follow' button coordinates on screen.
    Strictly matches 'Follow' and excludes 'Following', 'Followers', etc.
    """
    if root is None:
        return []
    w, h = get_screen_dimensions(root)
    buttons = []
    seen_coords = set()

    for node in root.iter('node'):
        node_text = (node.attrib.get('text') or '').strip()
        node_desc = (node.attrib.get('content-desc') or '').strip()

        t_clean = node_text.strip().lower()
        d_clean = node_desc.strip().lower()

        is_follow = False
        if t_clean == 'follow' or d_clean == 'follow':
            is_follow = True
        elif (t_clean.startswith('follow') or d_clean.startswith('follow')) and len(t_clean or d_clean) <= 7:
            if 'following' not in t_clean and 'followers' not in t_clean:
                is_follow = True

        if is_follow:
            bounds = node.attrib.get('bounds', '')
            coords = parse_bounds(bounds)
            if coords:
                cx, cy = coords
                # Only consider buttons within viewable content area (skip top header/URL bar area ~150px)
                if int(h * 0.16) <= cy <= int(h * 0.90):
                    # Group coordinates within 15px to avoid duplicate taps on same button
                    grid_key = (round(cx, -1), round(cy, -1))
                    if grid_key not in seen_coords:
                        seen_coords.add(grid_key)
                        buttons.append((cx, cy))

    return buttons


class FollowFailedException(Exception):
    """Raised when following suggested accounts fails or is blocked by Instagram."""
    pass


def check_for_follow_error(device_serial: str, instance_name: str = "", root=None) -> tuple[bool, str]:
    """Checks screen hierarchy texts and logcat for Instagram follow failure / action block indicators."""
    error_keywords = [
        "failed to load",
        "couldn't load",
        "action blocked",
        "try again later",
        "we limit how often",
        "something went wrong",
        "we restrict certain activity",
        "please try again later",
        "could not load"
    ]
    if root is not None:
        texts = extract_screen_texts(root)
        blob = " ".join(texts).lower()
        for kw in error_keywords:
            if kw in blob:
                return True, f"Screen text contains '{kw}'"

    # Also check adb logcat for transient toast or system error messages
    try:
        out = run_adb_command("shell logcat -d -t 60", device_serial=device_serial, instance_name=instance_name, timeout=2)
        out_low = out.lower()
        for kw in ["failed to load", "action blocked", "try again later", "we restrict certain activity"]:
            if kw in out_low:
                return True, f"Logcat reports '{kw}'"
    except Exception:
        pass

    return False, ""


def follow_suggested_accounts(device_serial: str, instance_name: str = "", count: int = 5, timeout: float = 65.0, task_context=None) -> int:
    """
    Subscribes (follows) target number of suggested accounts on Instagram (default 5).
    1. Checks if current screen already displays 'Follow' buttons or 'Suggested for you'.
    2. If not, navigates to https://www.instagram.com/explore/people/
    3. Waits properly for the follow page and suggested accounts to load (polling screen hierarchy).
    4. If the page is slow or gets stuck, automatically reloads the page.
    5. Finds and taps 'Follow' buttons up to `count` (5) with human randomized delays.
    6. Swipes down to reveal more accounts if count not yet reached.
    7. Ensures pipeline never closes without following the required 5 accounts.
    """
    if not AUTO_FOLLOW_SUGGESTED:
        log("FOLLOW-SKIP", "Auto 5 subscribe is disabled in settings.", instance_name=instance_name)
        return 0

    log("FOLLOW", f"👥 Subscribing to {count} suggested accounts on Instagram ({instance_name})...", instance_name=instance_name)
    start_time = time.time()
    followed_count = 0
    tapped_locations = set()
    suggested_url = SUGGESTED_PEOPLE_URL

    def _check_and_dismiss_save_info(current_root) -> bool:
        """
        Detects and dismisses 'Save your login info to Instagram?' bottom sheet / overlay
        which often covers the screen and hides the suggested follow buttons.
        """
        if current_root is None:
            return False
        cur_texts = extract_screen_texts(current_root)
        cur_blob = " ".join(cur_texts).lower()
        if any(k in cur_blob for k in ["save your login info", "save login info", "wont need to enter it next time", "won't need to enter it next time", "save info to instagram"]):
            log("FOLLOW-POPUP", "Detected 'Save your login info to Instagram?' overlay covering follow page! Tapping Save/Not now...", instance_name=instance_name)
            btn_save = find_element(current_root, "save", exact=True) or find_element(current_root, "not now", exact=False) or find_element(current_root, "save")
            w_s, h_s = get_screen_dimensions(current_root)
            if btn_save:
                log("FOLLOW-POPUP", f"Found button at ({btn_save[0]}, {btn_save[1]}). Tapping...", instance_name=instance_name)
                run_adb_command(f"shell input tap {btn_save[0]} {btn_save[1]}", device_serial=device_serial, instance_name=instance_name)
            else:
                log("FOLLOW-POPUP", f"Tapping calculated Save button position at ({int(w_s*0.50)}, {int(h_s*0.74)})...", instance_name=instance_name)
                run_adb_command(f"shell input tap {int(w_s*0.50)} {int(h_s*0.74)}", device_serial=device_serial, instance_name=instance_name)
            time.sleep(2.0)
            return True
        return False

    def _trigger_page_reload(current_root=None):
        log("FOLLOW-RELOAD", f"🔄 Follow page taking too long or unresponsive. Reloading page...", instance_name=instance_name)
        if current_root is not None:
            retry_btn = find_element(current_root, "try again") or find_element(current_root, "retry") or find_element(current_root, "reload")
            if retry_btn:
                log("FOLLOW-RELOAD", f"Found retry button at ({retry_btn[0]}, {retry_btn[1]}). Tapping...", instance_name=instance_name)
                run_adb_command(f"shell input tap {retry_btn[0]} {retry_btn[1]}", device_serial=device_serial, instance_name=instance_name)
                time.sleep(2.5)
                return
        # Re-launch URL and send browser reload keyevent (F5)
        run_adb_command(f'shell am start -a android.intent.action.VIEW -d "{suggested_url}" {PACKAGE_NAME}', device_serial=device_serial, instance_name=instance_name)
        time.sleep(1.2)
        run_adb_command("shell input keyevent 131", device_serial=device_serial, instance_name=instance_name)
        time.sleep(2.5)

    def _wait_for_follow_buttons(max_wait=12.0) -> tuple[Optional[ET.Element], list]:
        """Polls screen hierarchy until Follow buttons appear or max_wait seconds elapse."""
        w_start = time.time()
        cur_root = None
        while (time.time() - w_start) < max_wait:
            cur_root = get_screen_hierarchy(device_serial=device_serial, instance_name=instance_name)
            if cur_root is not None:
                # Check and dismiss 'Save your login info' overlay if present
                if _check_and_dismiss_save_info(cur_root):
                    cur_root = get_screen_hierarchy(device_serial=device_serial, instance_name=instance_name)
                    if cur_root is None:
                        continue

                has_err, err_reason = check_for_follow_error(device_serial, instance_name, cur_root)
                if has_err:
                    if any(b in err_reason.lower() for b in ["action blocked", "we restrict", "we limit"]):
                        log("FOLLOW-FAIL", f"❌ Instagram follow blocked ({err_reason})! Halting immediately...", instance_name=instance_name)
                        if task_context is not None:
                            task_context['follow_failed'] = True
                        raise FollowFailedException(err_reason)
                    log("FOLLOW-WARN", f"⚠️ Follow page warning: '{err_reason}'. Will trigger reload...", instance_name=instance_name)
                    return cur_root, []

                # If "See all" is present without buttons yet, tap it to open the list
                see_all = find_element(cur_root, "see all", exact=True)
                btns = find_all_follow_buttons(cur_root)
                if see_all and not btns:
                    log("FOLLOW", f"Tapping 'See all' at ({see_all[0]}, {see_all[1]}) to reveal suggested accounts...", instance_name=instance_name)
                    run_adb_command(f"shell input tap {see_all[0]} {see_all[1]}", device_serial=device_serial, instance_name=instance_name)
                    time.sleep(2.0)
                    cur_root = get_screen_hierarchy(device_serial=device_serial, instance_name=instance_name)
                    btns = find_all_follow_buttons(cur_root)

                if btns:
                    return cur_root, btns

            time.sleep(1.5)
        return cur_root, []

    # Step 1: Initial Screen Inspection
    root = get_screen_hierarchy(device_serial=device_serial, instance_name=instance_name)
    if _check_and_dismiss_save_info(root):
        root = get_screen_hierarchy(device_serial=device_serial, instance_name=instance_name)
    texts = extract_screen_texts(root) if root is not None else []
    blob = " ".join(texts).lower()

    # Check for immediate follow error / action block
    has_err, err_reason = check_for_follow_error(device_serial, instance_name, root)
    if has_err:
        if any(b in err_reason.lower() for b in ["action blocked", "we restrict", "we limit"]):
            log("FOLLOW-FAIL", f"❌ Follow failed on initial screen ({err_reason})! Halting pipeline immediately...", instance_name=instance_name)
            if task_context is not None:
                task_context['follow_failed'] = True
            raise FollowFailedException(err_reason)
        log("FOLLOW-WARN", f"⚠️ Follow warning on initial screen: '{err_reason}'. Will navigate to suggested accounts...", instance_name=instance_name)

    follow_buttons = find_all_follow_buttons(root)

    # If no follow buttons on current screen, navigate to explore/people/
    if not follow_buttons and not any(k in blob for k in ["suggested for you", "discover people", "follow accounts"]):
        log("FOLLOW", f"Opening {suggested_url} to locate suggested accounts...", instance_name=instance_name)
        run_adb_command(f'shell am start -a android.intent.action.VIEW -d "{suggested_url}" {PACKAGE_NAME}', device_serial=device_serial, instance_name=instance_name)
        time.sleep(2.0)

    # Step 2: Patient Wait & Reload Loop for Initial Accounts
    reload_count = 0
    max_reloads = 3
    if not follow_buttons:
        while not follow_buttons and reload_count <= max_reloads:
            log("FOLLOW-WAIT", f"⏳ Waiting for follow page to load accounts (attempt {reload_count + 1}/{max_reloads + 1})...", instance_name=instance_name)
            root, follow_buttons = _wait_for_follow_buttons(max_wait=10.0)
            if follow_buttons:
                log("FOLLOW", f"✔ Follow page loaded successfully! Found {len(follow_buttons)} accounts on screen.", instance_name=instance_name)
                break
            reload_count += 1
            if reload_count <= max_reloads:
                _trigger_page_reload(root)

    # Step 3: Following & Scrolling Loop
    scroll_attempts = 0
    max_scrolls = 6

    while followed_count < count and (time.time() - start_time) < timeout:
        if root is None:
            root = get_screen_hierarchy(device_serial=device_serial, instance_name=instance_name)
        if root is None:
            time.sleep(0.8)
            continue

        # Check for error on current screen
        has_err, err_reason = check_for_follow_error(device_serial, instance_name, root)
        if has_err:
            if any(b in err_reason.lower() for b in ["action blocked", "we restrict", "we limit"]):
                log("FOLLOW-FAIL", f"❌ Follow failed on screen ({err_reason})! Halting pipeline immediately...", instance_name=instance_name)
                if task_context is not None:
                    task_context['follow_failed'] = True
                raise FollowFailedException(err_reason)

        if _check_and_dismiss_save_info(root):
            root = get_screen_hierarchy(device_serial=device_serial, instance_name=instance_name)
            if root is None:
                continue

        w, h = get_screen_dimensions(root)
        follow_buttons = find_all_follow_buttons(root)

        # Tap all un-followed visible buttons
        for bx, by in follow_buttons:
            if followed_count >= count:
                break
            grid_key = (round(bx, -1), round(by, -1))
            if grid_key in tapped_locations:
                continue

            log("FOLLOW", f"👉 [{followed_count + 1}/{count}] Following suggested account at ({bx}, {by})...", instance_name=instance_name)
            run_adb_command(f"shell input tap {bx} {by}", device_serial=device_serial, instance_name=instance_name)
            tapped_locations.add(grid_key)
            followed_count += 1
            time.sleep(random.uniform(1.2, 1.8))

            # Verify if this follow tap triggered 'Failed to Load' toast or block
            root_post = get_screen_hierarchy(device_serial=device_serial, instance_name=instance_name)
            has_tap_err, tap_reason = check_for_follow_error(device_serial, instance_name, root_post)
            if has_tap_err and any(b in tap_reason.lower() for b in ["action blocked", "we restrict", "we limit"]):
                log("FOLLOW-FAIL", f"❌ Follow failed after tap ({tap_reason})! Halting pipeline immediately...", instance_name=instance_name)
                if task_context is not None:
                    task_context['follow_failed'] = True
                raise FollowFailedException(tap_reason)

        if followed_count >= count:
            break

        # If more follows needed, swipe down to reveal next accounts
        scroll_attempts += 1
        if scroll_attempts > max_scrolls:
            # If scrolls exhausted and still under target, reload the page to get fresh recommendations
            if reload_count <= max_reloads:
                log("FOLLOW", f"🔄 Need {count - followed_count} more follows after max scrolls. Reloading page for fresh recommendations...", instance_name=instance_name)
                _trigger_page_reload(root)
                reload_count += 1
                scroll_attempts = 0
                tapped_locations.clear()
                root, follow_buttons = _wait_for_follow_buttons(max_wait=10.0)
                continue
            else:
                break

        log("FOLLOW", f"Scrolling down to find more suggested accounts (Followed: {followed_count}/{count})...", instance_name=instance_name)
        run_adb_command(f"shell input swipe {w // 2} {int(h * 0.72)} {w // 2} {int(h * 0.32)} 350", device_serial=device_serial, instance_name=instance_name)
        # Give screen a moment to settle and render new content
        time.sleep(1.8)
        root = None

    # Step 4: Strict Verification - Ensure we never close/proceed without full follows
    if followed_count < count:
        log("FOLLOW-FAIL", f"❌ Follow incomplete: Only {followed_count}/{count} accounts followed! Halting pipeline to prevent incomplete accounts...", instance_name=instance_name)
        if task_context is not None:
            task_context['follow_failed'] = True
        raise FollowFailedException(f"Incomplete follow count: {followed_count}/{count}")

    log("FOLLOW", f"✨ Successfully subscribed to {followed_count}/{count} suggested accounts!", instance_name=instance_name)

    # If a 'Next', 'Done', or 'Start' button is present on screen after following, tap it
    root_after = get_screen_hierarchy(device_serial=device_serial, instance_name=instance_name)
    if root_after is not None:
        btn_next = find_element(root_after, "next", exact=True) or find_element(root_after, "done", exact=True) or find_element(root_after, "start", exact=True)
        if btn_next:
            log("FOLLOW", f"Tapping '{btn_next[2]}' to complete suggested accounts step...", instance_name=instance_name)
            run_adb_command(f"shell input tap {btn_next[0]} {btn_next[1]}", device_serial=device_serial, instance_name=instance_name)
            time.sleep(1.5)

    return followed_count


def run_instagram_pipeline(device_serial: str, email: str, password: str, target_login: str, mail_token="", instance_name="Inst-1", task_context=None, task_mode="cookies"):
    log("ACC-START", f"Processing Instagram ({task_mode.upper()} mode) for: {email} on device {device_serial}...", instance_name=instance_name)

    log("STEP-1", f"Cleaning Via Browser data ({PACKAGE_NAME})...", instance_name=instance_name)
    run_adb_command(f"shell am force-stop {PACKAGE_NAME}", device_serial=device_serial, instance_name=instance_name)
    time.sleep(0.3)
    run_adb_command(f"shell pm clear {PACKAGE_NAME}", device_serial=device_serial, instance_name=instance_name)
    time.sleep(0.4)

    log("STEP-2", f"Launching '{INSTA_LOGIN_URL}' in browser...", instance_name=instance_name)
    run_adb_command(f'shell am start -a android.intent.action.VIEW -d "{INSTA_LOGIN_URL}" {PACKAGE_NAME}', device_serial=device_serial, instance_name=instance_name)
    time.sleep(1.6)

    login_submitted = False
    login_wait_count = 0
    agree_terms_submitted = False
    agree_retry_count = 0
    username_attempted = False
    auto_username_used = False
    captured_username = target_login
    two_factor_secret = ""
    two_factor_initiated = False
    suggested_accounts_followed = False
    should_follow_suggested = AUTO_FOLLOW_SUGGESTED
    if task_context is not None and "auto_follow_suggested" in task_context:
        should_follow_suggested = bool(task_context.get("auto_follow_suggested"))

    def _do_follow_suggested() -> bool:
        nonlocal suggested_accounts_followed
        if not suggested_accounts_followed:
            if should_follow_suggested:
                try:
                    fol_cnt = follow_suggested_accounts(device_serial=device_serial, instance_name=instance_name, count=5, task_context=task_context)
                    if fol_cnt < 5:
                        log("FOLLOW-ABORT", f"❌ Follow incomplete ({fol_cnt}/5). Halting Instagram pipeline immediately without proceeding further!", instance_name=instance_name)
                        if task_context is not None:
                            task_context['follow_failed'] = True
                        return False
                except FollowFailedException as e_fol:
                    log("FOLLOW-ABORT", f"❌ Follow failed: {e_fol}. Halting Instagram pipeline immediately without proceeding further!", instance_name=instance_name)
                    if task_context is not None:
                        task_context['follow_failed'] = True
                    return False
                except Exception as e_fol:
                    log("FOLLOW-ABORT", f"❌ Error during auto-follow: {e_fol}. Halting Instagram pipeline immediately!", instance_name=instance_name)
                    if task_context is not None:
                        task_context['follow_failed'] = True
                    return False
            else:
                log("FOLLOW-SKIP", "Auto 5 subscribe is OFF in settings. Skipping suggested accounts...", instance_name=instance_name)
            suggested_accounts_followed = True
        return True
    max_loops = 100
    loop_count = 0

    last_page_name = ""
    page_enter_time = time.time()
    page_stuck_back_count = 0
    no_account_card_taps = 0

    log("STATE-LOOP", f"Starting UI state machine for {email}...", instance_name=instance_name)

    while loop_count < max_loops:
        if task_context and (task_context.get('status') == 'cancelled' or task_context.get('cancelled')):
            log("TASK-CANCELLED", f"Task was cancelled by Telegram bot for {target_login}! Aborting Instagram 2FA immediately...", instance_name=instance_name)
            return False, ""
        loop_count += 1
        root = get_screen_hierarchy(device_serial=device_serial, instance_name=instance_name)
        if root is None:
            log("UI-WARN", f"[Loop {loop_count}/{max_loops}] Temporary ADB screen dump lag on {device_serial}. Retrying...", instance_name=instance_name)
            time.sleep(0.5)
            continue

        page_name, visible_texts = detect_current_page(root)
        current_time = time.time()
        stuck_duration = current_time - page_enter_time

        if page_name != last_page_name:
            last_page_name = page_name
            page_enter_time = current_time
            stuck_duration = 0.0
            page_stuck_back_count = 0
            login_wait_count = 0
            no_account_card_taps = 0
            if page_name not in ["INSTAGRAM_AGREE_TERMS_PAGE", "INSTAGRAM_ALLOW_CONTINUE_PAGE", "INSTAGRAM_USERNAME_PAGE"]:
                agree_retry_count = 0
            sample = visible_texts[:3] if visible_texts else ["Empty UI dump"]
            log("PAGE-CHANGE", f"[Loop {loop_count}/{max_loops}] Detected: '{page_name}' | Preview: {sample}", instance_name=instance_name)
        else:
            if page_name == "INSTAGRAM_AGREE_TERMS_PAGE":
                if stuck_duration >= 35.0:
                    agree_retry_count += 1
                    if agree_retry_count <= 3:
                        log("TIMEOUT-WARN", f"Screen '{page_name}' stuck for {int(stuck_duration)}s. Pressing Back to repeat...", instance_name=instance_name)
                        run_adb_command("shell input keyevent 4", device_serial=device_serial, instance_name=instance_name)
                        agree_terms_submitted = False
                        last_page_name = ""
                        page_enter_time = time.time()
                        time.sleep(1.0)
                        continue
                    else:
                        log("TIMEOUT-ABORT", f"Screen '{page_name}' still stuck after retries. Aborting...", instance_name=instance_name)
                        return False, ""
                elif agree_terms_submitted:
                    time.sleep(0.3)
                    continue

            elif stuck_duration >= 25.0:
                if page_name == "TWO_FACTOR_CHECK_EMAIL_PAGE":
                    if stuck_duration >= 70.0:
                        log("TIMEOUT-ABORT", "Stuck on 'Check your email' screen >70s. Aborting to start fresh cycle...", instance_name=instance_name)
                        run_adb_command(f"shell am force-stop {PACKAGE_NAME}", device_serial=device_serial, instance_name=instance_name)
                        return False, ""
                    time.sleep(0.5)
                    continue
                page_stuck_back_count += 1
                if two_factor_initiated:
                    log("TIMEOUT-WARN", f"Screen '{page_name}' unresponsive ({int(stuck_duration)}s) during 2FA. Re-opening: {TWO_FACTOR_URL}...", instance_name=instance_name)
                    run_adb_command(f'shell am start -a android.intent.action.VIEW -d "{TWO_FACTOR_URL}" {PACKAGE_NAME}', device_serial=device_serial, instance_name=instance_name)
                    page_enter_time = time.time()
                    time.sleep(2.0)
                    if page_stuck_back_count >= 5:
                        log("TIMEOUT-ABORT", f"Stuck in 2FA phase >90s. Aborting account...", instance_name=instance_name)
                        return False, ""
                    continue
                elif page_name in ["BROWSER_TERMS_PAGE", "INSTAGRAM_LANDING_PAGE", "INSTAGRAM_LOGIN_PAGE", "GENERIC_PAGE", "UNKNOWN_SCREEN"]:
                    if page_name == "INSTAGRAM_LOGIN_PAGE" and login_submitted:
                        # Allow up to 12s for Instagram login response before auto reload & re-fill
                        if stuck_duration < 12.0:
                            time.sleep(1.5)
                            continue
                    log("TIMEOUT-WARN", f"Screen '{page_name}' unresponsive ({int(stuck_duration)}s). Reloading...", instance_name=instance_name)
                    reload_browser_page(root=root, device_serial=device_serial, instance_name=instance_name)
                    if page_name == "INSTAGRAM_LOGIN_PAGE":
                        login_submitted = False
                        login_wait_count = 0
                else:
                    log("TIMEOUT-WARN", f"Screen '{page_name}' unresponsive ({int(stuck_duration)}s). Pressing Back...", instance_name=instance_name)
                    run_adb_command("shell input keyevent 4", device_serial=device_serial, instance_name=instance_name)

                page_enter_time = time.time()
                time.sleep(1.0)

                if page_stuck_back_count >= 4:
                    log("TIMEOUT-ABORT", f"Stuck on {page_name} >80s. Aborting account...", instance_name=instance_name)
                    return False, ""

        # --- State Handlers ---
        if page_name == "BROWSER_TERMS_PAGE":
            log("STATE-ACTION", "Browser terms page -> Tapping AGREE...", instance_name=instance_name)
            tap_or_fallback_rel(root, "agree", 0.5, 0.88, "Agree Button", exact=True, device_serial=device_serial, instance_name=instance_name)
            time.sleep(0.8)
            run_adb_command(f'shell am start -a android.intent.action.VIEW -d "{INSTA_LOGIN_URL}" {PACKAGE_NAME}', device_serial=device_serial, instance_name=instance_name)
            time.sleep(0.5)
            run_adb_command("shell input keyevent 66", device_serial=device_serial, instance_name=instance_name)
            time.sleep(1.5)

        elif page_name == "INSTAGRAM_COOKIE_PAGE":
            log("STATE-ACTION", "Cookie banner detected -> Tapping 'Allow all cookies'...", instance_name=instance_name)
            tap_or_fallback_rel(root, "allow all cookies", 0.5, 0.70, "Allow Cookies", device_serial=device_serial, instance_name=instance_name)
            time.sleep(1.2)

        elif page_name == "HOME_SCREEN":
            log("STATE-ACTION", "Home screen detected -> Re-opening instagram.com...", instance_name=instance_name)
            run_adb_command(f'shell am start -a android.intent.action.VIEW -d "{INSTA_LOGIN_URL}" {PACKAGE_NAME}', device_serial=device_serial, instance_name=instance_name)
            time.sleep(0.5)
            run_adb_command("shell input keyevent 66", device_serial=device_serial, instance_name=instance_name)
            time.sleep(1.5)

        elif page_name in ["CANNOT_FIND_ACCOUNT_POPUP", "INCORRECT_PASSWORD_POPUP", "ACCOUNT_ERROR_PAGE", "HTTP_TRANSPORT_ERROR_PAGE"]:
            log("STATE-ABORT", f"Account restriction or transport error detected '{page_name}'. Aborting current cycle...", instance_name=instance_name)
            run_adb_command(f"shell am force-stop {PACKAGE_NAME}", device_serial=device_serial, instance_name=instance_name)
            return False, ""

        elif page_name == "INSTAGRAM_LANDING_PAGE":
            log("STATE-ACTION", "Instagram landing page -> Tapping 'Log in'...", instance_name=instance_name)
            login_coords = find_instagram_landing_login(root)
            if login_coords:
                lx, ly = login_coords
                log("ACTION", f"Found 'Log In' element at ({lx}, {ly}). Tapping...", instance_name=instance_name)
                run_adb_command(f"shell input tap {lx} {ly}", device_serial=device_serial, instance_name=instance_name)
            else:
                fx, fy = get_rel_coords(root, 0.40, 0.74)
                log("ACTION-FALLBACK", f"Tapping relative fallback ({fx}, {fy}) for 'Log In'...", instance_name=instance_name)
                run_adb_command(f"shell input tap {fx} {fy}", device_serial=device_serial, instance_name=instance_name)
            time.sleep(2.0)

        elif page_name == "INSTAGRAM_LOGIN_PAGE":
            if not login_submitted:
                log("STATE-ACTION", f"Entering credentials for {email}...", instance_name=instance_name)
                elem_user = find_input_box(root, hint_patterns=["username, email or mobile number", "phone number, username, or email", "username", "email", "phone", "mobile"], default_rx=0.50, default_ry=0.46)
                log("STATE-ACTION", f"Entering email '{email}' at ({elem_user[0]}, {elem_user[1]})...", instance_name=instance_name)
                run_adb_command(f"shell input tap {elem_user[0]} {elem_user[1]}", device_serial=device_serial, instance_name=instance_name)
                time.sleep(0.15)
                run_adb_command(f"shell input tap {elem_user[0]} {elem_user[1]}", device_serial=device_serial, instance_name=instance_name)
                time.sleep(0.3)
                clear_input_field(device_serial=device_serial, instance_name=instance_name)
                type_text(email, device_serial=device_serial, instance_name=instance_name)
                time.sleep(0.3)

                root = get_screen_hierarchy(device_serial=device_serial, instance_name=instance_name)
                log("STATE-ACTION", "Entering password...", instance_name=instance_name)
                elem_pwd = find_password_field(root) or find_input_box(root, hint_patterns=["password"], default_rx=0.50, default_ry=0.57)
                run_adb_command(f"shell input tap {elem_pwd[0]} {elem_pwd[1]}", device_serial=device_serial, instance_name=instance_name)
                time.sleep(0.15)
                run_adb_command(f"shell input tap {elem_pwd[0]} {elem_pwd[1]}", device_serial=device_serial, instance_name=instance_name)
                time.sleep(0.3)
                clear_input_field(device_serial=device_serial, instance_name=instance_name)
                type_text(password, device_serial=device_serial, instance_name=instance_name)
                time.sleep(0.3)

                # Ensure keyboard is fully hidden so it does not block the Log in button
                hide_keyboard(device_serial=device_serial, instance_name=instance_name)
                time.sleep(0.5)

                root = get_screen_hierarchy(device_serial=device_serial, instance_name=instance_name)
                w, h = get_screen_dimensions(root)
                login_btn = find_instagram_login_button(root, elem_pwd=elem_pwd)
                log("STATE-ACTION", "Submitting login credentials (tapping 'Log in')...", instance_name=instance_name)
                if login_btn:
                    lx, ly = login_btn
                    log("STATE-ACTION", f"✔ Found verified 'Log In' button at ({lx}, {ly}). Tapping...", instance_name=instance_name)
                    run_adb_command(f"shell input tap {lx} {ly}", device_serial=device_serial, instance_name=instance_name)
                else:
                    fallback_y = elem_pwd[1] + int(h * 0.08) if elem_pwd else int(h * 0.67)
                    fallback_y = min(max(fallback_y, int(h * 0.60)), int(h * 0.74))
                    log("ACTION-FALLBACK", f"Tapping calculated fallback 'Log In' position at ({int(w*0.50)}, {fallback_y})...", instance_name=instance_name)
                    run_adb_command(f"shell input tap {int(w*0.50)} {fallback_y}", device_serial=device_serial, instance_name=instance_name)

                # Backup Enter key to trigger form submission
                time.sleep(0.2)
                run_adb_command("shell input keyevent 66", device_serial=device_serial, instance_name=instance_name)

                login_submitted = True
                login_wait_count = 0
                log("STATE-ACTION", "⏳ 'Log In' button pressed! Waiting patiently for Instagram to process credentials & load next page (network buffer)...", instance_name=instance_name)
                time.sleep(4.0)
            else:
                login_wait_count += 1
                log("STATE-ACTION", f"⏳ Waiting for login transition to 'No Instagram profile found' (check #{login_wait_count}/3)...", instance_name=instance_name)

                # 🔁 Active re-tap at check #1 in case the initial touch was missed
                if login_wait_count == 1:
                    log("STATE-ACTION", "Login page still active (check #1). Re-tapping 'Log in' button...", instance_name=instance_name)
                    hide_keyboard(device_serial=device_serial, instance_name=instance_name)
                    time.sleep(0.3)
                    root = get_screen_hierarchy(device_serial=device_serial, instance_name=instance_name)
                    btn_re = find_instagram_login_button(root)
                    if btn_re:
                        run_adb_command(f"shell input tap {btn_re[0]} {btn_re[1]}", device_serial=device_serial, instance_name=instance_name)
                    else:
                        w, h = get_screen_dimensions(root)
                        run_adb_command(f"shell input tap {int(w*0.50)} {int(h*0.67)}", device_serial=device_serial, instance_name=instance_name)
                    run_adb_command("shell input keyevent 66", device_serial=device_serial, instance_name=instance_name)
                    time.sleep(2.0)

                # 🔄 If still on login page at check >= 3 (~9-10s without showing 'No Instagram profile found'):
                # Reload the page and re-fill the credentials as requested!
                elif login_wait_count >= 3:
                    log("STATE-ACTION", "🔄 Login page stuck! 'No Instagram profile found' did not appear. Reloading page and re-filling form...", instance_name=instance_name)
                    reload_browser_page(root=root, device_serial=device_serial, instance_name=instance_name)
                    time.sleep(1.5)
                    run_adb_command(f'shell am start -a android.intent.action.VIEW -d "{INSTA_LOGIN_URL}" {PACKAGE_NAME}', device_serial=device_serial, instance_name=instance_name)
                    time.sleep(2.5)
                    login_submitted = False
                    login_wait_count = 0
                else:
                    time.sleep(2.0)

        elif page_name == "INSTAGRAM_SAVE_PASSWORD_POPUP":
            log("STATE-ACTION", "Save password popup -> Tapping 'Cancel'...", instance_name=instance_name)
            tap_or_fallback_rel(root, "cancel", 0.5, 0.65, "Cancel Button", exact=True, device_serial=device_serial, instance_name=instance_name)
            time.sleep(1.2)

        elif page_name == "FACEBOOK_FIND_ACCOUNT_PAGE":
            log("STATE-ACTION", "Facebook 'Find your account' page detected -> Pressing Android Back to return to Instagram name flow...", instance_name=instance_name)
            run_adb_command("shell input keyevent 4", device_serial=device_serial, instance_name=instance_name)
            time.sleep(1.8)

        elif page_name == "INSTAGRAM_NO_ACCOUNT_FOUND":
            w, h = get_screen_dimensions(root)
            no_account_card_taps += 1
            log("STATE-ACTION", f"No Instagram profile overlay detected (attempt #{no_account_card_taps}) -> Scrolling down immediately to reveal Meta card...", instance_name=instance_name)

            # 🚀 USER REQUIREMENT: As soon as arriving at this page, scroll down immediately!
            # Swipe up from bottom-half (0.74h -> 0.32h) to bring the Meta Account card clearly into view
            # and push the 'Find another account' / 'Forgotten account' button out of the way.
            run_adb_command(f"shell input swipe {int(w*0.50)} {int(h*0.74)} {int(w*0.50)} {int(h*0.32)} 350", device_serial=device_serial, instance_name=instance_name)
            time.sleep(0.8)

            # Re-fetch screen hierarchy after scrolling
            root = get_screen_hierarchy(device_serial=device_serial, instance_name=instance_name)
            if root is None:
                time.sleep(0.4)
                root = get_screen_hierarchy(device_serial=device_serial, instance_name=instance_name)

            tile_coords = find_instagram_account_tile(root, email, target_login)
            raw_x = tile_coords[0] if tile_coords else int(w * 0.50)
            raw_y = tile_coords[1] if tile_coords else int(h * 0.82)

            # 🛡️ STRICT SAFETY GUARD: NEVER click 'Find another account' / 'Forgotten account' button!
            # Clamped strictly in the lower card region [0.78h, 0.86h] well below the top buttons
            safe_x = int(w * 0.50)
            safe_y = min(max(raw_y, int(h * 0.78)), int(h * 0.86))
            desc = tile_coords[2] if tile_coords else "card_center"

            log("STATE-ACTION", f"Carefully tapping Meta account card at ({safe_x}, {safe_y}) [{desc}] (STRICTLY bypassing 'Find another account')...", instance_name=instance_name)
            run_adb_command(f"shell input tap {safe_x} {safe_y}", device_serial=device_serial, instance_name=instance_name)
            time.sleep(2.0)


        elif page_name == "INSTAGRAM_NAME_PAGE":
            log("STATE-ACTION", f"'What\\'s your name?' screen -> Filling name with '{target_login}'...", instance_name=instance_name)
            nx, ny = find_input_box(root, hint_patterns=["full name"], default_rx=0.50, default_ry=0.40)
            log("STATE-ACTION", f"Targeting Full name input at ({nx}, {ny}). Tapping to focus...", instance_name=instance_name)
            run_adb_command(f"shell input tap {nx} {ny}", device_serial=device_serial, instance_name=instance_name)
            time.sleep(0.15)
            run_adb_command(f"shell input tap {nx} {ny}", device_serial=device_serial, instance_name=instance_name)
            time.sleep(0.3)
            clear_input_field(length=40, device_serial=device_serial, instance_name=instance_name)
            time.sleep(0.15)
            type_text(target_login, device_serial=device_serial, instance_name=instance_name, human_like=True)
            time.sleep(0.3)
            hide_keyboard(device_serial=device_serial, instance_name=instance_name)
            time.sleep(0.2)

            root = get_screen_hierarchy(device_serial=device_serial, instance_name=instance_name)
            log("STATE-ACTION", "Tapping 'Next' on Name screen...", instance_name=instance_name)
            tap_or_fallback_rel(root, "next", 0.50, 0.51, "Next Button", exact=True, device_serial=device_serial, instance_name=instance_name)
            time.sleep(1.8)

        elif page_name == "INSTAGRAM_USERNAME_PAGE":
            text_blob_curr = " ".join(visible_texts).lower()
            is_uname_error = any(err in text_blob_curr for err in [
                "choose a username", "not available", "isn't available", "isnt available",
                "another account", "try another", "can't use", "cant use"
            ])

            if is_uname_error:
                log("USERNAME-WARN", f"Username '{target_login}' not accepted (Error shown)! Navigating Back (<) to regenerate auto-suggested username...", instance_name=instance_name)
                hide_keyboard(device_serial=device_serial, instance_name=instance_name)
                time.sleep(0.3)
                
                # Tap top-left back arrow (<) or keyevent 4
                back_btn = find_element(root, "back") or find_element(root, "go back")
                if back_btn:
                    run_adb_command(f"shell input tap {back_btn[0]} {back_btn[1]}", device_serial=device_serial, instance_name=instance_name)
                else:
                    fx_b, fy_b = get_rel_coords(root, 0.06, 0.19)
                    run_adb_command(f"shell input tap {fx_b} {fy_b}", device_serial=device_serial, instance_name=instance_name)
                    run_adb_command("shell input keyevent 4", device_serial=device_serial, instance_name=instance_name)
                time.sleep(1.2)

                root = get_screen_hierarchy(device_serial=device_serial, instance_name=instance_name)
                p_name, _ = detect_current_page(root)
                if p_name == "INSTAGRAM_NAME_PAGE":
                    log("STATE-ACTION", "On Name screen -> Tapping 'Next' to trigger auto username...", instance_name=instance_name)
                    tap_or_fallback_rel(root, "next", 0.50, 0.51, "Next Button", exact=True, device_serial=device_serial, instance_name=instance_name)
                    time.sleep(1.5)

                root = get_screen_hierarchy(device_serial=device_serial, instance_name=instance_name)
                log("STATE-ACTION", "On Username screen with auto-filled value -> Tapping 'Next'...", instance_name=instance_name)
                hide_keyboard(device_serial=device_serial, instance_name=instance_name)
                time.sleep(0.2)
                tap_or_fallback_rel(root, "next", 0.5, 0.60, "Next Button", exact=True, device_serial=device_serial, instance_name=instance_name)
                auto_username_used = True
                time.sleep(1.8)
            else:
                log("STATE-ACTION", f"'Create a username' screen -> Pre-filled from Full Name. Tapping 'Next'...", instance_name=instance_name)
                hide_keyboard(device_serial=device_serial, instance_name=instance_name)
                time.sleep(0.2)
                tap_or_fallback_rel(root, "next", 0.5, 0.60, "Next Button", exact=True, device_serial=device_serial, instance_name=instance_name)
                username_attempted = True
                time.sleep(1.8)

        elif page_name == "INSTAGRAM_ALLOW_CONTINUE_PAGE":
            log("STATE-ACTION", "Instagram link confirmation -> Tapping 'Allow and continue'...", instance_name=instance_name)
            tap_or_fallback_rel(root, "allow and continue", 0.5, 0.88, "Allow and continue", device_serial=device_serial, instance_name=instance_name)
            time.sleep(1.8)

        elif page_name == "INSTAGRAM_AGREE_TERMS_PAGE":
            if not agree_terms_submitted:
                log("STATE-ACTION", "Terms of Use page -> Tapping 'I agree'...", instance_name=instance_name)
                tap_or_fallback_rel(root, "i agree", 0.5, 0.88, "I agree Button", exact=True, device_serial=device_serial, instance_name=instance_name)
                agree_terms_submitted = True
                page_enter_time = time.time()

                # Persistently wait on new page until 'Save' button is found
                log("STATE-WAIT", "Waiting for post-registration screen / 'Save' button after 'I agree' (up to 35s)...", instance_name=instance_name)
                save_clicked = False
                for sec in range(1, 36):
                    time.sleep(1.0)
                    root_check = get_screen_hierarchy(device_serial=device_serial, instance_name=instance_name)
                    if root_check is None:
                        continue
                    p_check, texts_check = detect_current_page(root_check)
                    blob_check = " ".join(texts_check).lower()
                    
                    # Check for Save button or Save Info page
                    btn_save = find_element(root_check, "save", exact=True) or find_element(root_check, "save")
                    if p_check in ["INSTAGRAM_SAVE_INFO_PAGE", "INSTAGRAM_REGISTERED_PAGE", "INSTAGRAM_SUGGESTED_PAGE"] or (btn_save and "save" in blob_check and "terms" not in blob_check):
                        log("STATE-ACTION", f"✔ Registration reached post-login screen '{p_check}' at sec {sec}!", instance_name=instance_name)
                        
                        w_c, h_c = get_screen_dimensions(root_check)
                        if btn_save and btn_save[1] > int(h_c * 0.50):
                            run_adb_command(f"shell input tap {btn_save[0]} {btn_save[1]}", device_serial=device_serial, instance_name=instance_name)
                        else:
                            fx, fy = get_rel_coords(root_check, 0.50, 0.74)
                            run_adb_command(f"shell input tap {fx} {fy}", device_serial=device_serial, instance_name=instance_name)
                        time.sleep(2.0)

                        if not _do_follow_suggested():
                            return False, "FOLLOW_FAILED"

                        if task_mode == "cookies":
                            log("COOKIE-FLOW", "🍪 In Cookies mode: Post-registration & follow complete. Extracting cookies...", instance_name=instance_name)
                            cookies = extract_via_cookies(device_serial=device_serial, instance_name=instance_name)
                            if not cookies:
                                time.sleep(2.0)
                                cookies = extract_via_cookies(device_serial=device_serial, instance_name=instance_name)
                            if cookies:
                                if task_context is not None:
                                    task_context['cookies'] = cookies
                                return True, cookies
                            return False, ""

                        if task_mode in ["2fa_cookies", "random_2fa_cookies"]:
                            log("COOKIE-FLOW", f"🍪 [{task_mode.upper()}] Extracting Instagram cookies directly to memory before 2FA...", instance_name=instance_name)
                            cookies = extract_via_cookies(device_serial=device_serial, instance_name=instance_name)
                            if not cookies:
                                # Fallback: tap Save and retry extraction
                                fx, fy = get_rel_coords(root_check, 0.50, 0.74)
                                run_adb_command(f"shell input tap {fx} {fy}", device_serial=device_serial, instance_name=instance_name)
                                time.sleep(2.0)
                                cookies = extract_via_cookies(device_serial=device_serial, instance_name=instance_name)
                            if cookies:
                                if task_context is not None:
                                    task_context['cookies'] = cookies
                                log("COOKIE-FLOW", f"✨ [{task_mode.upper()}] Cookies saved to memory ({len(cookies)} chars)!", instance_name=instance_name)
                            else:
                                log("COOKIE-WARN", f"⚠️ [{task_mode.upper()}] Cookie extraction attempt incomplete...", instance_name=instance_name)

                        if auto_username_used:
                            log("STATE-ACTION", f"Registration complete with auto username! Opening Accounts Overview to change username to '{target_login}'...", instance_name=instance_name)
                            update_username_in_accounts_center(device_serial=device_serial, target_username=target_login, instance_name=instance_name)
                            auto_username_used = False
                            time.sleep(1.0)

                        save_clicked = True
                        break
                    elif p_check in ["INSTAGRAM_CONTINUE_PROFILE_PAGE", "REENTER_PASSWORD_PAGE", "TWO_FACTOR_CHECK_EMAIL_PAGE", "TWO_FACTOR_CHOOSE_ACCOUNT_PAGE", "TWO_FACTOR_EXTRA_PROTECTION_PAGE", "TWO_FACTOR_CHOOSE_METHOD_PAGE", "TWO_FACTOR_INSTRUCTIONS_PAGE", "TWO_FACTOR_ENTER_CODE_PAGE"]:
                        log("STATE-PROGRESS", f"Screen advanced directly to '{p_check}'! Continuing...", instance_name=instance_name)
                        save_clicked = True
                        break
                    elif p_check in ["INSTAGRAM_NOTIFICATIONS_PAGE", "INSTAGRAM_CONNECT_FB_PAGE", "INSTAGRAM_REGISTERED_PAGE", "INSTAGRAM_SUGGESTED_PAGE"]:
                        log("STATE-PROGRESS", f"Screen moved to '{p_check}'.", instance_name=instance_name)
                        if not _do_follow_suggested():
                            return False, "FOLLOW_FAILED"
                        if task_mode == "cookies":
                            log("COOKIE-FLOW", f"🍪 Post-registration screen '{p_check}' detected in Cookies mode! Extracting cookies...", instance_name=instance_name)
                            cookies = extract_via_cookies(device_serial=device_serial, instance_name=instance_name)
                            if cookies:
                                if task_context is not None:
                                    task_context['cookies'] = cookies
                                return True, cookies
                            return False, ""
                        elif task_mode == "random_2fa_cookies":
                            log("RANDOM-2FA", f"🎲 Post-registration screen '{p_check}' in Random 2FA+Cookies mode! Extracting cookies & generating random 2FA key...", instance_name=instance_name)
                            cookies = extract_via_cookies(device_serial=device_serial, instance_name=instance_name)
                            if cookies and task_context is not None:
                                task_context['cookies'] = cookies
                            saved_cookies = (task_context.get('cookies') if task_context else '') or (cookies or '')
                            random_2fa_key = generate_random_2fa_key()
                            if task_context is not None:
                                task_context['two_fa_key'] = random_2fa_key
                            save_credentials_csv(email, password, two_factor_secret=random_2fa_key, username=target_login, instance_name=instance_name, status="ACTIVE_RANDOM_2FA_COOKIES", cookies=saved_cookies)
                            log("RANDOM-2FA", f"🎲 [Random 2FA+Cookies] Generated 16-char 2FA key '{random_2fa_key}' & cookies ({len(saved_cookies)} chars)! Skipping app 2FA enrollment.", instance_name=instance_name)
                            return True, random_2fa_key
                        elif task_mode == "2fa_cookies" and (not task_context or not task_context.get('cookies')):
                            log("COOKIE-FLOW", f"🍪 [2FA+Cookies] Post-registration screen '{p_check}' detected! Extracting cookies to memory...", instance_name=instance_name)
                            cookies = extract_via_cookies(device_serial=device_serial, instance_name=instance_name)
                            if cookies and task_context is not None:
                                task_context['cookies'] = cookies
                                log("COOKIE-FLOW", f"✨ [2FA+Cookies] Cookies stored in memory ({len(cookies)} chars)!", instance_name=instance_name)
                        if auto_username_used:
                            update_username_in_accounts_center(device_serial=device_serial, target_username=target_login, instance_name=instance_name)
                            auto_username_used = False
                            time.sleep(1.0)
                        save_clicked = True
                        break

                if task_mode == "random_2fa_cookies":
                    if not _do_follow_suggested():
                        return False, "FOLLOW_FAILED"
                    saved_cookies = (task_context.get('cookies') if task_context else '')
                    if not saved_cookies:
                        cookies = extract_via_cookies(device_serial=device_serial, instance_name=instance_name)
                        if cookies and task_context is not None:
                            task_context['cookies'] = cookies
                        saved_cookies = cookies or ''
                    random_2fa_key = generate_random_2fa_key()
                    if task_context is not None:
                        task_context['two_fa_key'] = random_2fa_key
                    save_credentials_csv(email, password, two_factor_secret=random_2fa_key, username=target_login, instance_name=instance_name, status="ACTIVE_RANDOM_2FA_COOKIES", cookies=saved_cookies)
                    log("RANDOM-2FA", f"🎲 [Random 2FA+Cookies] Generated 16-char 2FA key '{random_2fa_key}' & cookies ({len(saved_cookies)} chars)! Skipping app 2FA enrollment.", instance_name=instance_name)
                    return True, random_2fa_key

                if task_mode in ["2fa", "2fa_cookies"]:
                    # After saving (or screen advanced), redirect to 2FA URL
                    log("2FA-START", f"Save completed! Redirecting to 2FA URL: {TWO_FACTOR_URL}...", instance_name=instance_name)
                    run_adb_command(f'shell am start -a android.intent.action.VIEW -d "{TWO_FACTOR_URL}" {PACKAGE_NAME}', device_serial=device_serial, instance_name=instance_name)
                    two_factor_initiated = True
                    page_enter_time = time.time()
                    time.sleep(2.5)
            else:
                log("STATE-WAIT", "Waiting for Save login info screen transition...", instance_name=instance_name)
                time.sleep(1.5)

        elif page_name in ["INSTAGRAM_SAVE_INFO_PAGE", "INSTAGRAM_REGISTERED_PAGE", "INSTAGRAM_SUGGESTED_PAGE"]:
            log("STATE-ACTION", f"Post-registration screen ({page_name}) -> Tapping 'Save' if present & following suggested accounts...", instance_name=instance_name)
            btn_save = find_element(root, "save", exact=True) or find_element(root, "save")
            w, h = get_screen_dimensions(root)
            if btn_save and btn_save[1] > int(h * 0.60):
                run_adb_command(f"shell input tap {btn_save[0]} {btn_save[1]}", device_serial=device_serial, instance_name=instance_name)
            elif btn_save:
                run_adb_command(f"shell input tap {btn_save[0]} {btn_save[1]}", device_serial=device_serial, instance_name=instance_name)
            else:
                fx, fy = get_rel_coords(root, 0.50, 0.74)
                run_adb_command(f"shell input tap {fx} {fy}", device_serial=device_serial, instance_name=instance_name)
            time.sleep(2.0)

            if not _do_follow_suggested():
                return False, "FOLLOW_FAILED"

            if task_mode == "cookies":
                log("COOKIE-FLOW", f"🍪 Screen '{page_name}' detected in Cookies mode! Extracting verified cookies...", instance_name=instance_name)
                cookies = extract_via_cookies(device_serial=device_serial, instance_name=instance_name)
                if not cookies:
                    time.sleep(2.0)
                    cookies = extract_via_cookies(device_serial=device_serial, instance_name=instance_name)
                if cookies:
                    if task_context is not None:
                        task_context['cookies'] = cookies
                    return True, cookies
                return False, ""
            elif task_mode == "random_2fa_cookies":
                log("RANDOM-2FA", f"🎲 Screen '{page_name}' in Random 2FA+Cookies mode! Extracting cookies & generating random 2FA key...", instance_name=instance_name)
                cookies = extract_via_cookies(device_serial=device_serial, instance_name=instance_name)
                if not cookies:
                    time.sleep(2.0)
                    cookies = extract_via_cookies(device_serial=device_serial, instance_name=instance_name)
                if cookies and task_context is not None:
                    task_context['cookies'] = cookies
                saved_cookies = (task_context.get('cookies') if task_context else '') or (cookies or '')
                random_2fa_key = generate_random_2fa_key()
                if task_context is not None:
                    task_context['two_fa_key'] = random_2fa_key
                save_credentials_csv(email, password, two_factor_secret=random_2fa_key, username=target_login, instance_name=instance_name, status="ACTIVE_RANDOM_2FA_COOKIES", cookies=saved_cookies)
                log("RANDOM-2FA", f"🎲 [Random 2FA+Cookies] Generated 16-char 2FA key '{random_2fa_key}' & cookies ({len(saved_cookies)} chars)! Skipping app 2FA enrollment.", instance_name=instance_name)
                return True, random_2fa_key
            elif task_mode == "2fa_cookies" and (not task_context or not task_context.get('cookies')):
                log("COOKIE-FLOW", f"🍪 [2FA+Cookies] Screen '{page_name}' detected! Extracting cookies to memory...", instance_name=instance_name)
                cookies = extract_via_cookies(device_serial=device_serial, instance_name=instance_name)
                if cookies and task_context is not None:
                    task_context['cookies'] = cookies
                    log("COOKIE-FLOW", f"✨ [2FA+Cookies] Cookies stored in memory ({len(cookies)} chars)!", instance_name=instance_name)

            if auto_username_used:
                log("STATE-ACTION", f"Registration complete with auto username! Opening Accounts Overview to change username to '{target_login}'...", instance_name=instance_name)
                update_username_in_accounts_center(device_serial=device_serial, target_username=target_login, instance_name=instance_name)
                auto_username_used = False
                time.sleep(1.0)

            log("2FA-START", f"Saved login info & followed suggested accounts! Navigating directly to 2FA URL: {TWO_FACTOR_URL}...", instance_name=instance_name)
            run_adb_command(f'shell am start -a android.intent.action.VIEW -d "{TWO_FACTOR_URL}" {PACKAGE_NAME}', device_serial=device_serial, instance_name=instance_name)
            two_factor_initiated = True
            time.sleep(2.2)

        elif page_name in ["INSTAGRAM_NOTIFICATIONS_PAGE", "INSTAGRAM_CONNECT_FB_PAGE"]:
            if not _do_follow_suggested():
                return False, "FOLLOW_FAILED"

            if task_mode == "cookies":
                log("COOKIE-FLOW", f"🍪 Screen '{page_name}' detected in Cookies mode! Extracting cookies directly...", instance_name=instance_name)
                cookies = extract_via_cookies(device_serial=device_serial, instance_name=instance_name)
                if cookies:
                    if task_context is not None:
                        task_context['cookies'] = cookies
                    return True, cookies
                return False, ""
            elif task_mode == "random_2fa_cookies":
                log("RANDOM-2FA", f"🎲 Screen '{page_name}' in Random 2FA+Cookies mode! Extracting cookies & generating random 2FA key...", instance_name=instance_name)
                cookies = extract_via_cookies(device_serial=device_serial, instance_name=instance_name)
                if cookies and task_context is not None:
                    task_context['cookies'] = cookies
                saved_cookies = (task_context.get('cookies') if task_context else '') or (cookies or '')
                random_2fa_key = generate_random_2fa_key()
                if task_context is not None:
                    task_context['two_fa_key'] = random_2fa_key
                save_credentials_csv(email, password, two_factor_secret=random_2fa_key, username=target_login, instance_name=instance_name, status="ACTIVE_RANDOM_2FA_COOKIES", cookies=saved_cookies)
                log("RANDOM-2FA", f"🎲 [Random 2FA+Cookies] Generated 16-char 2FA key '{random_2fa_key}' & cookies ({len(saved_cookies)} chars)! Skipping app 2FA enrollment.", instance_name=instance_name)
                return True, random_2fa_key
            elif task_mode == "2fa_cookies" and (not task_context or not task_context.get('cookies')):
                log("COOKIE-FLOW", f"🍪 [2FA+Cookies] Screen '{page_name}' detected! Extracting cookies to memory...", instance_name=instance_name)
                cookies = extract_via_cookies(device_serial=device_serial, instance_name=instance_name)
                if cookies and task_context is not None:
                    task_context['cookies'] = cookies
                    log("COOKIE-FLOW", f"✨ [2FA+Cookies] Cookies stored in memory ({len(cookies)} chars)!", instance_name=instance_name)

            log("STATE-ACTION", f"Post-registration screen ({page_name}) -> Transitioning to 2FA setup...", instance_name=instance_name)
            if auto_username_used:
                update_username_in_accounts_center(device_serial=device_serial, target_username=target_login, instance_name=instance_name)
                auto_username_used = False
                time.sleep(1.0)

            log("2FA-START", f"Navigating directly to 2FA URL: {TWO_FACTOR_URL}...", instance_name=instance_name)
            run_adb_command(f'shell am start -a android.intent.action.VIEW -d "{TWO_FACTOR_URL}" {PACKAGE_NAME}', device_serial=device_serial, instance_name=instance_name)
            two_factor_initiated = True
            time.sleep(2.2)

        elif page_name == "INSTAGRAM_CONTINUE_PROFILE_PAGE":
            log("STATE-ACTION", "Instagram Continue Profile screen detected -> Tapping 'Continue'...", instance_name=instance_name)
            login_submitted = False
            tap_or_fallback_rel(root, "continue", 0.50, 0.75, "Continue Button", exact=True, device_serial=device_serial, instance_name=instance_name)
            time.sleep(2.5)

        elif page_name == "REENTER_PASSWORD_PAGE":
            log("STATE-ACTION", f"Password confirmation requested -> Entering password for {email}...", instance_name=instance_name)
            pw_box = find_password_field(root) or find_input_box(root, hint_patterns=["password"], default_rx=0.50, default_ry=0.45)
            if pw_box:
                run_adb_command(f"shell input tap {pw_box[0]} {pw_box[1]}", device_serial=device_serial, instance_name=instance_name)
                time.sleep(0.2)
            clear_input_field(length=40, device_serial=device_serial, instance_name=instance_name)
            type_text(password, device_serial=device_serial, instance_name=instance_name)
            time.sleep(0.3)
            hide_keyboard(device_serial=device_serial, instance_name=instance_name)
            time.sleep(0.2)
            root = get_screen_hierarchy(device_serial=device_serial, instance_name=instance_name)
            tap_or_fallback_rel(root, "continue", 0.50, 0.60, "Continue Button", exact=True, device_serial=device_serial, instance_name=instance_name) or tap_or_fallback_rel(root, "next", 0.50, 0.60, "Next Button", exact=True, device_serial=device_serial, instance_name=instance_name)
            time.sleep(2.0)

        elif page_name == "CANNOT_MAKE_CHANGE_POPUP":
            log("STATE-ACTION", "Encountered 'Can't make this change at the moment' popup. Attempting to dismiss dialog...", instance_name=instance_name)
            dismiss_btn = (find_element(root, "dismiss", exact=True)
                           or find_element(root, "close", exact=True)
                           or find_element(root, "ok", exact=True)
                           or find_element(root, "got it", exact=True))
            if dismiss_btn:
                run_adb_command(f"shell input tap {dismiss_btn[0]} {dismiss_btn[1]}", device_serial=device_serial, instance_name=instance_name)
            else:
                run_adb_command("shell input keyevent 4", device_serial=device_serial, instance_name=instance_name)
            time.sleep(1.5)

            root = get_screen_hierarchy(device_serial=device_serial, instance_name=instance_name)
            p_after, _ = detect_current_page(root)
            insta_elem = (find_element(root, target_login, exact=False) if target_login else None) \
                         or find_element(root, "instagram", exact=False)
            if insta_elem and p_after != "CANNOT_MAKE_CHANGE_POPUP":
                log("STATE-ACTION", f"Found Instagram element after popup dismissal. Tapping ({insta_elem[0]}, {insta_elem[1]})...", instance_name=instance_name)
                run_adb_command(f"shell input tap {insta_elem[0]} {insta_elem[1]}", device_serial=device_serial, instance_name=instance_name)
                time.sleep(2.0)
            else:
                log("2FA-BLOCKED", "2FA blocked by Instagram: 'Can't make this change at the moment'. Transitioning directly to last step balance checking...", instance_name=instance_name)
                if task_context is not None:
                    task_context['cannot_make_change'] = True

                saved_cookies = task_context.get('cookies', '') if task_context else ""
                final_user = captured_username or target_login
                if saved_cookies:
                    log("SUCCESS", f"🍪 Account {final_user} has valid cookies! Saving to credentials and completing via cookies...", instance_name=instance_name)
                    save_credentials_csv(email, password, two_factor_secret="", username=final_user, instance_name=instance_name, status="ACTIVE_COOKIES", cookies=saved_cookies)

                run_adb_command(f"shell am force-stop {PACKAGE_NAME}", device_serial=device_serial, instance_name=instance_name)
                return (True if saved_cookies else False), "CANNOT_MAKE_CHANGE"

        elif page_name == "SUSPECT_AUTOMATED_BEHAVIOR_PAGE":
            log("ERR", "Instagram flagged 'Suspect automated behavior'. Aborting to start a fresh cycle...", instance_name=instance_name)
            return False, ""

        elif page_name in ["PAGE_NOT_AVAILABLE_ERROR_PAGE", "CONTENT_NO_LONGER_AVAILABLE_PAGE", "ACCOUNT_ERROR_PAGE", "HTTP_TRANSPORT_ERROR_PAGE"]:
            log("ERR", f"Error screen '{page_name}' ('HTTP_TRANSPORT_ERROR / Network request encountered error') encountered. Aborting to start fresh cycle...", instance_name=instance_name)
            run_adb_command(f"shell am force-stop {PACKAGE_NAME}", device_serial=device_serial, instance_name=instance_name)
            return False, ""

        elif page_name in ["INCORRECT_PASSWORD_POPUP", "CANNOT_FIND_ACCOUNT_POPUP"]:
            log("ERR", f"Account error '{page_name}' encountered. Aborting to start fresh cycle...", instance_name=instance_name)
            return False, ""

        elif page_name == "TWO_FACTOR_EXTRA_PROTECTION_PAGE":
            two_factor_initiated = True
            insta_elem = (find_element(root, target_login, exact=False) if target_login else None) \
                         or find_element(root, "instagram", exact=False)
            if insta_elem:
                log("STATE-ACTION", f"2FA: Instagram account present on screen -> Tapping Instagram card at ({insta_elem[0]}, {insta_elem[1]})...", instance_name=instance_name)
                run_adb_command(f"shell input tap {insta_elem[0]} {insta_elem[1]}", device_serial=device_serial, instance_name=instance_name)
                time.sleep(2.0)
            else:
                log("STATE-ACTION", "2FA: 'Set up extra protection for your Meta Account' -> Tapping 'Get started'...", instance_name=instance_name)
                tap_or_fallback_rel(root, "get started", 0.5, 0.88, "Get Started Button", exact=True, device_serial=device_serial, instance_name=instance_name)
                time.sleep(1.8)


        elif page_name == "TWO_FACTOR_CHECK_EMAIL_PAGE":
            two_factor_initiated = True

            # Fast check if error already present on screen before doing anything
            texts_init = extract_screen_texts(root)
            blob_init = " ".join(texts_init).lower() if texts_init else ""
            if any(err in blob_init for err in ["http_transport_error", "transport_error", "network request encountered error", "encountered error http"]):
                log("ERR", "Network request error 'HTTP_TRANSPORT_ERROR' detected on Check your email screen! Aborting to start fresh cycle...", instance_name=instance_name)
                run_adb_command(f"shell am force-stop {PACKAGE_NAME}", device_serial=device_serial, instance_name=instance_name)
                return False, ""

            ninja_client = task_context.get('ninja_client') if task_context else None
            log("STATE-ACTION", f"2FA Check Email Code Screen -> Fetching recent 8-digit security code for {email} (max 30s)...", instance_name=instance_name)
            
            # Wait up to 30 seconds for recent 8-digit email security code for 2FA
            email_code = fetch_email_security_code(
                email,
                password,
                mail_token=mail_token,
                ninja_client=ninja_client,
                max_wait_sec=30,
                expected_digits=8,
                instance_name=instance_name
            )

            if not email_code or len(str(email_code).strip()) != 8:
                log("ERR", f"8-digit email security code not received for {email} on first attempt. Aborting to start fresh cycle...", instance_name=instance_name)
                return False, ""

            # Check screen hierarchy after waiting for OTP
            root = get_screen_hierarchy(device_serial=device_serial, instance_name=instance_name)
            refreshed_page, r_texts = detect_current_page(root)
            r_blob = " ".join(r_texts).lower() if r_texts else ""

            if refreshed_page == "HTTP_TRANSPORT_ERROR_PAGE" or any(err in r_blob for err in ["http_transport_error", "transport_error", "network request encountered error", "encountered error http"]):
                log("ERR", "Network request error 'HTTP_TRANSPORT_ERROR' detected while waiting for OTP. Aborting to start fresh cycle...", instance_name=instance_name)
                run_adb_command(f"shell am force-stop {PACKAGE_NAME}", device_serial=device_serial, instance_name=instance_name)
                return False, ""

            if refreshed_page == "TWO_FACTOR_SUCCESS_PAGE" and two_factor_secret:
                log("SUCCESS", f"✔ 2FA already succeeded after email code wait for {email}!", instance_name=instance_name)
                return True, two_factor_secret

            # If page drifted away during mail polling, re-open 2FA URL
            if refreshed_page not in ["TWO_FACTOR_CHECK_EMAIL_PAGE", "TWO_FACTOR_CHOOSE_METHOD_PAGE", "TWO_FACTOR_INSTRUCTIONS_PAGE", "TWO_FACTOR_COPY_KEY_PAGE", "TWO_FACTOR_ENTER_CODE_PAGE"]:
                log("2FA-RELOAD", f"Screen moved to '{refreshed_page}' during OTP wait. Re-opening 2FA URL: {TWO_FACTOR_URL}...", instance_name=instance_name)
                run_adb_command(f'shell am start -a android.intent.action.VIEW -d "{TWO_FACTOR_URL}" {PACKAGE_NAME}', device_serial=device_serial, instance_name=instance_name)
                page_enter_time = time.time()
                time.sleep(2.5)
                continue

            if refreshed_page == "TWO_FACTOR_CHECK_EMAIL_PAGE" and email_code and len(str(email_code).strip()) == 8:
                clean_email_code = str(email_code).strip()
                log("STATE-ACTION", f"Entering verified {len(clean_email_code)}-digit email security code '{clean_email_code}'...", instance_name=instance_name)
                for attempt in range(1, 3):
                    root = get_screen_hierarchy(device_serial=device_serial, instance_name=instance_name)
                    curr_p, curr_texts = detect_current_page(root)
                    curr_blob = " ".join(curr_texts).lower() if curr_texts else ""
                    if curr_p == "HTTP_TRANSPORT_ERROR_PAGE" or any(err in curr_blob for err in ["http_transport_error", "transport_error", "network request encountered error", "encountered error http"]):
                        log("ERR", "Network request error 'HTTP_TRANSPORT_ERROR' detected on screen. Aborting to start fresh cycle...", instance_name=instance_name)
                        run_adb_command(f"shell am force-stop {PACKAGE_NAME}", device_serial=device_serial, instance_name=instance_name)
                        return False, ""

                    if curr_p != "TWO_FACTOR_CHECK_EMAIL_PAGE":
                        log("2FA-PROGRESS", f"Moved from 'Check your email' to '{curr_p}'!", instance_name=instance_name)
                        break

                    # Locate Code input field accurately using specialized helper (handles both Facebook page and Instagram modal)
                    code_coords = find_code_input_field(root)
                    paste_or_type_code(clean_email_code, device_serial=device_serial, instance_name=instance_name, field_coords=code_coords)
                    time.sleep(0.3)

                    root = get_screen_hierarchy(device_serial=device_serial, instance_name=instance_name)
                    log("STATE-ACTION", f"Tapping 'Continue' button on 'Check your email' modal (attempt {attempt}/2)...", instance_name=instance_name)
                    btn_found = (find_element(root, "continue", exact=True)
                                 or find_element(root, "next", exact=True)
                                 or find_element(root, "continue")
                                 or find_element(root, "next"))
                    if btn_found:
                        run_adb_command(f"shell input tap {btn_found[0]} {btn_found[1]}", device_serial=device_serial, instance_name=instance_name)
                    else:
                        texts_btn = extract_screen_texts(root)
                        blob_btn = " ".join(texts_btn).lower()
                        if "facebook" in blob_btn or "enter code" in blob_btn:
                            fx, fy = get_rel_coords(root, 0.50, 0.86)
                        else:
                            fx, fy = get_rel_coords(root, 0.50, 0.65)
                        run_adb_command(f"shell input tap {fx} {fy}", device_serial=device_serial, instance_name=instance_name)

                    time.sleep(2.5)
                    root = get_screen_hierarchy(device_serial=device_serial, instance_name=instance_name)
                    post_p, post_texts = detect_current_page(root)
                    post_blob = " ".join(post_texts).lower() if post_texts else ""

                    if post_p == "HTTP_TRANSPORT_ERROR_PAGE" or any(err in post_blob for err in ["http_transport_error", "transport_error", "network request encountered error", "encountered error http"]):
                        log("ERR", "Network request error 'HTTP_TRANSPORT_ERROR' encountered after clicking Continue! Aborting to start fresh cycle...", instance_name=instance_name)
                        run_adb_command(f"shell am force-stop {PACKAGE_NAME}", device_serial=device_serial, instance_name=instance_name)
                        return False, ""

                    if post_p != "TWO_FACTOR_CHECK_EMAIL_PAGE":
                        log("2FA-ACTION", f"Successfully moved to '{post_p}' after email verification!", instance_name=instance_name)
                        page_enter_time = time.time()
                        
                        # Re-open 2FA URL to resume setup if not already on 2FA flow screen
                        if post_p not in ["TWO_FACTOR_CHOOSE_ACCOUNT_PAGE", "TWO_FACTOR_EXTRA_PROTECTION_PAGE", "TWO_FACTOR_CHOOSE_METHOD_PAGE", "TWO_FACTOR_INSTRUCTIONS_PAGE", "TWO_FACTOR_COPY_KEY_PAGE", "TWO_FACTOR_ENTER_CODE_PAGE", "TWO_FACTOR_SUCCESS_PAGE"]:
                            log("2FA-REDIRECT", f"Redirecting back to 2FA URL to complete remaining setup: {TWO_FACTOR_URL}...", instance_name=instance_name)
                            run_adb_command(f'shell am start -a android.intent.action.VIEW -d "{TWO_FACTOR_URL}" {PACKAGE_NAME}', device_serial=device_serial, instance_name=instance_name)
                            time.sleep(2.2)
                        break
                    else:
                        log("2FA-WARN", "Still on 'Check your email'. Retrying Continue tap...", instance_name=instance_name)
                        texts_btn = extract_screen_texts(root)
                        blob_btn = " ".join(texts_btn).lower()
                        if any(err in blob_btn for err in ["http_transport_error", "transport_error", "network request encountered error", "encountered error http"]):
                            log("ERR", "Network request error 'HTTP_TRANSPORT_ERROR' detected! Aborting to start fresh cycle...", instance_name=instance_name)
                            run_adb_command(f"shell am force-stop {PACKAGE_NAME}", device_serial=device_serial, instance_name=instance_name)
                            return False, ""

                        if "facebook" in blob_btn or "enter code" in blob_btn:
                            fx, fy = get_rel_coords(root, 0.50, 0.86)
                        else:
                            fx, fy = get_rel_coords(root, 0.50, 0.65)
                        run_adb_command(f"shell input tap {fx} {fy}", device_serial=device_serial, instance_name=instance_name)
                        page_enter_time = time.time()
                        time.sleep(1.5)

        elif page_name == "TWO_FACTOR_CHOOSE_ACCOUNT_PAGE":
            two_factor_initiated = True
            log("STATE-ACTION", "2FA choose account screen -> Locating and tapping Instagram profile card...", instance_name=instance_name)
            insta_elem = None
            if target_login:
                insta_elem = find_element(root, target_login, exact=False)
            if not insta_elem and captured_username:
                insta_elem = find_element(root, captured_username, exact=False)
            if not insta_elem:
                insta_elem = find_element(root, "instagram", exact=False)
            if not insta_elem and email:
                prefix = email.split('@')[0]
                if len(prefix) >= 4:
                    insta_elem = find_element(root, prefix, exact=False)

            if insta_elem:
                log("ACTION", f"Found Instagram element at ({insta_elem[0]}, {insta_elem[1]}). Tapping...", instance_name=instance_name)
                run_adb_command(f"shell input tap {insta_elem[0]} {insta_elem[1]}", device_serial=device_serial, instance_name=instance_name)
            else:
                tap_or_fallback_rel(root, "instagram", 0.5, 0.65, "Instagram Profile Card", device_serial=device_serial, instance_name=instance_name)
            time.sleep(2.0)


        elif page_name == "TWO_FACTOR_CHOOSE_METHOD_PAGE":
            two_factor_initiated = True
            log("STATE-ACTION", "2FA: 'Help protect your account' -> Selecting Authentication app & tapping 'Continue/Next'...", instance_name=instance_name)
            auth_app = find_element(root, "authentication app", exact=False)
            if auth_app:
                run_adb_command(f"shell input tap {auth_app[0]} {auth_app[1]}", device_serial=device_serial, instance_name=instance_name)
                time.sleep(0.3)
            tapped = tap_or_fallback_rel(root, "continue", 0.50, 0.86, "Continue Button", exact=False, device_serial=device_serial, instance_name=instance_name)
            if not tapped:
                tap_or_fallback_rel(root, "next", 0.50, 0.86, "Next Button", exact=False, device_serial=device_serial, instance_name=instance_name)
            time.sleep(1.8)

        elif page_name in ["TWO_FACTOR_INSTRUCTIONS_PAGE", "TWO_FACTOR_COPY_KEY_PAGE"]:
            two_factor_initiated = True
            log("STATE-ACTION", f"2FA: Setup screen ({page_name}) -> Scrolling and extracting secret key...", instance_name=instance_name)
            
            # Robust key extraction (up to 4 attempts)
            for attempt in range(1, 4):
                root = get_screen_hierarchy(device_serial=device_serial, instance_name=instance_name)
                extracted_key = extract_2fa_secret_and_copy(root, device_serial=device_serial, instance_name=instance_name)
                if extracted_key and is_valid_b32_secret(extracted_key):
                    two_factor_secret = extracted_key
                    if task_context is not None:
                        task_context['two_fa_key'] = two_factor_secret
                    log("2FA-CAPTURED", f"✔ Secret Key captured ({len(two_factor_secret)} chars): '{two_factor_secret}'", instance_name=instance_name)
                    break
                else:
                    clip = get_android_clipboard(device_serial=device_serial, instance_name=instance_name)
                    if clip:
                        clean_clip = re.sub(r'[^A-Z0-9]', '', clip.upper())
                        if is_valid_b32_secret(clean_clip):
                            two_factor_secret = clean_clip
                            if task_context is not None:
                                task_context['two_fa_key'] = two_factor_secret
                            log("2FA-CLIPBOARD", f"✔ Secret Key recovered from clipboard ({len(two_factor_secret)} chars): '{two_factor_secret}'", instance_name=instance_name)
                            break
                log("2FA-WARN", f"Secret key not yet captured on attempt {attempt}/3. Scrolling down and retrying...", instance_name=instance_name)
                w, h = get_screen_dimensions(root)
                run_adb_command(f"shell input swipe {int(w*0.50)} {int(h*0.75)} {int(w*0.50)} {int(h*0.30)} 250", device_serial=device_serial, instance_name=instance_name)
                time.sleep(1.0)

            # If key is not yet captured after attempts, abort immediately
            if not two_factor_secret:
                log("ERR", "Secret key could not be captured on 2FA setup page. Aborting account to start fresh cycle...", instance_name=instance_name)
                return False, ""

            # Scroll down to reveal 'Next' / 'Enter code' button and tap
            w, h = get_screen_dimensions(root)
            run_adb_command(f"shell input swipe {int(w*0.50)} {int(h*0.75)} {int(w*0.50)} {int(h*0.35)} 250", device_serial=device_serial, instance_name=instance_name)
            time.sleep(0.4)

            root = get_screen_hierarchy(device_serial=device_serial, instance_name=instance_name)
            elem_enter = (find_element(root, "next", exact=True)
                          or find_element(root, "enter code", exact=True)
                          or find_element(root, "next")
                          or find_element(root, "enter code")
                          or find_element(root, "continue"))
            if elem_enter:
                log("2FA-ACTION", f"Tapping '{elem_enter[2]}' button to go to OTP entry...", instance_name=instance_name)
                run_adb_command(f"shell input tap {elem_enter[0]} {elem_enter[1]}", device_serial=device_serial, instance_name=instance_name)
            else:
                fx, fy = get_rel_coords(root, 0.50, 0.86)
                log("2FA-ACTION", f"Tapping fallback 'Next/Enter code' position at ({fx},{fy})...", instance_name=instance_name)
                run_adb_command(f"shell input tap {fx} {fy}", device_serial=device_serial, instance_name=instance_name)
            time.sleep(1.8)

        elif page_name == "TWO_FACTOR_ENTER_CODE_PAGE":
            two_factor_initiated = True
            log("STATE-ACTION", "2FA: 'Enter the 6-digit code' -> Generating OTP via pyotp...", instance_name=instance_name)
            if not two_factor_secret:
                clip = get_android_clipboard(device_serial=device_serial, instance_name=instance_name)
                if clip:
                    clean_clip = re.sub(r'[^A-Z0-9]', '', clip.upper())
                    if is_valid_b32_secret(clean_clip):
                        two_factor_secret = clean_clip
                        if task_context is not None: task_context['two_fa_key'] = two_factor_secret
                if not two_factor_secret and task_context and task_context.get('two_fa_key'):
                    two_factor_secret = task_context.get('two_fa_key')

            # Generate OTP immediately using pyotp from 2FA Secret Key
            otp_to_fill = ""
            if two_factor_secret and is_valid_b32_secret(two_factor_secret):
                otp_to_fill = generate_totp_code(two_factor_secret)
                log("2FA-OTP", f"🔑 Generated 6-Digit OTP via pyotp: '{otp_to_fill}'", instance_name=instance_name)
            elif task_context and task_context.get('otp_code'):
                otp_to_fill = task_context['otp_code']
                log("2FA-OTP", f"🔑 Using Bot 6-digit OTP: '{otp_to_fill}'", instance_name=instance_name)
            elif task_context and task_context.get('two_fa_key'):
                two_factor_secret = task_context.get('two_fa_key')
                if is_valid_b32_secret(two_factor_secret):
                    otp_to_fill = generate_totp_code(two_factor_secret)
                    log("2FA-OTP", f"🔑 Generated 6-Digit OTP via task_context: '{otp_to_fill}'", instance_name=instance_name)

            if otp_to_fill:
                code_coords = find_2fa_code_input_field(root)
                paste_or_type_code(otp_to_fill, device_serial=device_serial, instance_name=instance_name, field_coords=code_coords)
            else:
                log("2FA-WARN", "No 2FA secret key or OTP code available to fill!", instance_name=instance_name)

            root = get_screen_hierarchy(device_serial=device_serial, instance_name=instance_name)
            clicked_next = tap_or_fallback_rel(root, "next", 0.50, 0.84, "Next Button", exact=False, device_serial=device_serial, instance_name=instance_name)
            log("2FA-ACTION", f"✔ Clicked 'Next' button after OTP input ({clicked_next}). Waiting for confirmation...", instance_name=instance_name)
            time.sleep(2.5)

            # Verify if 2FA succeeded immediately
            root = get_screen_hierarchy(device_serial=device_serial, instance_name=instance_name)
            p_check, check_texts = detect_current_page(root)
            check_blob = " ".join(check_texts).lower() if check_texts else ""
            if p_check == "TWO_FACTOR_SUCCESS_PAGE" or "two-factor authentication is on" in check_blob or "two-factor is on" in check_blob or "is on" in check_blob:
                log("SUCCESS", f"🎉 Two-factor authentication successfully enabled for {email}!", instance_name=instance_name)
                tap_or_fallback_rel(root, "done", 0.5, 0.88, "Done Button", device_serial=device_serial, instance_name=instance_name)
                time.sleep(1.0)
                final_user = captured_username or target_login
                saved_cookies = task_context.get('cookies', '') if task_context else ""
                st = "ACTIVE_2FA_COOKIES" if saved_cookies else "ACTIVE_2FA"
                save_credentials_csv(email, password, two_factor_secret=two_factor_secret, username=final_user, instance_name=instance_name, status=st, cookies=saved_cookies)
                return True, two_factor_secret

        elif page_name == "TWO_FACTOR_SUCCESS_PAGE":
            if not two_factor_secret:
                log("2FA-WARN", "Encountered TWO_FACTOR_SUCCESS_PAGE but secret key is not recorded yet. Attempting recovery from clipboard / task context...", instance_name=instance_name)
                clip = get_android_clipboard(device_serial=device_serial, instance_name=instance_name)
                if clip:
                    clean_clip = re.sub(r'[^A-Z0-9]', '', clip.upper())
                    if is_valid_b32_secret(clean_clip):
                        two_factor_secret = clean_clip
                        if task_context is not None:
                            task_context['two_fa_key'] = two_factor_secret
                if not two_factor_secret and task_context and task_context.get('two_fa_key'):
                    two_factor_secret = task_context.get('two_fa_key')

            log("SUCCESS", f"🎉 Two-Factor Authentication is successfully active for {email}!", instance_name=instance_name)
            tap_or_fallback_rel(root, "done", 0.5, 0.88, "Done Button", device_serial=device_serial, instance_name=instance_name)
            time.sleep(1.0)
            
            # Save account to CSV and Google Sheets
            final_user = captured_username or target_login
            saved_cookies = task_context.get('cookies', '') if task_context else ""
            st = "ACTIVE_2FA_COOKIES" if saved_cookies else "ACTIVE_2FA"
            save_credentials_csv(email, password, two_factor_secret=two_factor_secret, username=final_user, instance_name=instance_name, status=st, cookies=saved_cookies)
            return True, two_factor_secret

        else:
            time.sleep(0.6)

    return False, two_factor_secret

def run_instagram_2fa_pipeline(device_serial: str, email: str, password: str, target_login: str, mail_token="", instance_name="Inst-1", task_context=None):
    return run_instagram_pipeline(device_serial, email, password, target_login, mail_token, instance_name, task_context, task_mode="2fa")

def run_instagram_cookies_pipeline(device_serial: str, email: str, password: str, target_login: str, mail_token="", instance_name="Inst-1", task_context=None):
    return run_instagram_pipeline(device_serial, email, password, target_login, mail_token, instance_name, task_context, task_mode="cookies")

# ==============================================================================
# 🤖 TELEGRAM TASK WORKER CLASS (Multi-Account Parallel Execution)
# ==============================================================================
class TasklyWorker:
    def __init__(
        self,
        account_cfg: dict,
        device_serial: str,
        instance_name: str,
        target_bot: str,
        client: TelegramClient,
        on_account_switched_callback: Optional[Callable] = None,
        available_bots: Optional[List[str]] = None,
        task_mode: str = "2fa",
        on_state_change: Optional[Callable] = None,
        auto_shift: bool = False,
        shift_task_mode: str = ""
    ):
        self.account_cfg = account_cfg
        self.device_serial = device_serial
        self.instance_name = instance_name
        self.available_bots = available_bots if available_bots else (account_cfg.get("target_bots") or TARGET_BOTS)
        self.target_bots = self.available_bots or [target_bot]
        self.current_bot_idx = 0
        self.target_bot = target_bot
        self.client = client
        self.on_account_switched_callback = on_account_switched_callback
        self.task_mode = (task_mode or _CFG.get("task_mode", "2fa")).lower()
        self.on_state_change = on_state_change
        self.auto_shift = bool(auto_shift if auto_shift is not None else (_CFG.get("auto_shift", False) or _CFG.get("telegram", {}).get("auto_shift", False)))
        self.shift_task_mode = (shift_task_mode or _CFG.get("shift_task_mode", "") or _CFG.get("telegram", {}).get("shift_task_mode", "")).lower()

        self.hourly_limit_event = asyncio.Event()
        self.is_hourly_limited = False
        self.hourly_limit_until: Optional[datetime] = None

        self.current_task: Dict[str, Any] = {
            'status': 'idle',
            'first_name': None,
            'last_name': None,
            'login': None,
            'password': None,
            'two_fa_key': None,
            'two_fa_sent': False,
            'otp_code': None,
            'cookies': None,
            'cookies_sent': False,
            'cookies_requested': False,
            'meta_email_sent': False,
            'meta_password_sent': False,
            'cancelled': False
        }

        self.task_received_event = asyncio.Event()
        self.two_fa_requested_event = asyncio.Event()
        self.cookies_requested_event = asyncio.Event()
        self.meta_email_requested_event = asyncio.Event()
        self.meta_password_requested_event = asyncio.Event()
        self.otp_received_event = asyncio.Event()
        self.report_received_event = asyncio.Event()
        self.task_cancelled_event = asyncio.Event()

        self.submitted_count = 0
        self.approved_count = 0
        self.current_balance = "$0.00"
        self.is_stopped = False
        self.consecutive_fails = 0
        self.consecutive_timeouts = 0
        self.max_consecutive_fails = int(_CFG.get("max_consecutive_fails", 3))
        self.fail_cooldown_seconds = int(_CFG.get("device_fail_cooldown", 60))

        self.task_confirm_btn_msg = None
        self._last_processed_key = None
        self._last_processed_time = 0.0
        self._last_sent_commands: Dict[str, float] = {}
        self.only_meta_started = False

        # Register current account as active in global pool
        if self.account_cfg and self.account_cfg.get("phone"):
            TelegramAccountPool.register_active(self.account_cfg.get("phone"), self.instance_name)

        self._register_handlers()

    def _register_handlers(self):
        targets = self.target_bots if self.target_bots else [self.target_bot]
        @self.client.on(events.NewMessage(chats=targets))
        async def _bot_handler(event):
            await self.handle_bot_message(event)

        @self.client.on(events.MessageEdited(chats=targets))
        async def _bot_edit_handler(event):
            await self.handle_bot_message(event)

    async def switch_target_bot(self, next_bot: Optional[str] = None) -> str:
        """Switches the target Telegram bot (e.g. PayGoeasy_bot <-> Taskl1_bot)."""
        old_bot = self.target_bot
        if next_bot:
            new_bot = next_bot.strip().lstrip("@")
        else:
            bots = self.target_bots if self.target_bots else ["Taskl1_bot", "PayGoeasy_bot"]
            curr_idx = 0
            for idx, b in enumerate(bots):
                if b.lower() == old_bot.lower():
                    curr_idx = idx
                    break
            new_bot = bots[(curr_idx + 1) % len(bots)]

        self.target_bot = new_bot
        self._last_sent_commands.clear()
        log("TG-SWITCH-BOT", f"🔀 Switched target bot: @{old_bot} ➔ @{new_bot}", instance_name=self.instance_name)

        if self.on_account_switched_callback:
            try:
                self.on_account_switched_callback(self.instance_name, self.account_cfg.get("phone"), new_bot)
            except Exception:
                pass

        return new_bot

    async def switch_account(self, new_account_cfg: dict, new_target_bot: Optional[str] = None) -> bool:
        """Gracefully disconnects current Telegram client and switches to a free account."""
        new_phone = new_account_cfg.get("phone")
        old_phone = self.account_cfg.get("phone")
        log("TG-SWITCH", f"🔄 Switching account for {self.instance_name}: {old_phone} ➔ {new_phone}...", instance_name=self.instance_name)

        # Release old account
        TelegramAccountPool.release_active(old_phone)

        # Disconnect old client
        try:
            if self.client:
                if self.client.is_connected():
                    await self.client.disconnect()
                if hasattr(self.client, 'session') and hasattr(self.client.session, '_conn') and self.client.session._conn:
                    self.client.session._conn.close()
        except Exception as e:
            log("TG-WARN", f"Error disconnecting previous client: {e}", instance_name=self.instance_name)

        # Connect new client
        try:
            clean_phone = re.sub(r'[^0-9]', '', str(new_phone))
            sess_name = new_account_cfg.get('session_name') or f"Taskl1_session_{clean_phone}"
            sess_path = os.path.join(BASE_DIR, sess_name) if not os.path.isabs(sess_name) else sess_name
            if not os.path.exists(sess_path + ".session") and not os.path.exists(sess_path):
                for alt in [f"Taskl1_session_{clean_phone}", f"taskly_session_{clean_phone}"]:
                    alt_p = os.path.join(BASE_DIR, alt)
                    if os.path.exists(alt_p + ".session"):
                        sess_path = alt_p
                        sess_name = alt
                        break
            new_client = TelegramClient(sess_path, new_account_cfg['api_id'], new_account_cfg['api_hash'])
            await new_client.start(phone=clean_phone)

            self.client = new_client
            self.account_cfg = new_account_cfg
            TelegramAccountPool.register_active(new_phone, self.instance_name)

            if new_target_bot:
                self.target_bot = new_target_bot

            self._register_handlers()
            self._last_sent_commands.clear()

            if self.on_account_switched_callback:
                try:
                    self.on_account_switched_callback(self.instance_name, new_phone, self.target_bot)
                except Exception:
                    pass

            log("TG-SWITCH", f"✨ New account {new_phone} successfully activated for {self.instance_name} (Bot: @{self.target_bot})!", instance_name=self.instance_name)

            # Refresh balance for new account
            try:
                await self.fetch_bot_balance()
            except Exception:
                pass
            return True
        except Exception as e:
            log("TG-ERR", f"❌ Failed to activate new account {new_phone}: {e}", instance_name=self.instance_name)
            return False

    async def handle_flood_rotation(self, flood_seconds: int) -> bool:
        """Handles FloodWait by switching to a free account or alternating bots."""
        curr_phone = self.account_cfg.get("phone")
        TelegramAccountPool.mark_flood(curr_phone, flood_seconds)
        log("FLOOD-WAIT", f"⚠️ Account {curr_phone} placed on FloodWait cooldown for {flood_seconds}s.", instance_name=self.instance_name)

        # 1. Try to find another free account
        free_acc = TelegramAccountPool.find_free_account(curr_phone, self.instance_name)
        if free_acc:
            new_phone = free_acc.get("phone")
            log("TG-ROTATE", f"🔄 Free account found ({new_phone})! Rotating Telegram session...", instance_name=self.instance_name)
            ok = await self.switch_account(free_acc)
            if ok:
                await asyncio.sleep(random.uniform(2.5, 4.5))
                return True

        # 2. If no free account, switch bot to avoid locked peer only if auto_shift is enabled
        if self.auto_shift:
            log("TG-ROTATE", f"⚠️ No free account available! Auto-Shift is ON -> Switching target bot to prevent stall...", instance_name=self.instance_name)
            new_bot = await self.switch_target_bot()
            if self.shift_task_mode and self.shift_task_mode in ["2fa", "cookies", "2fa_cookies", "random_2fa_cookies"]:
                self.task_mode = self.shift_task_mode
            await asyncio.sleep(random.uniform(3.0, 6.0))
        else:
            log("TG-ROTATE", f"⚠️ Account placed on FloodWait ({flood_seconds}s). Auto-Shift is OFF -> Remaining on @{self.target_bot} and waiting...", instance_name=self.instance_name)
            await asyncio.sleep(min(flood_seconds, 60))
        return False

    async def ensure_connected(self, max_wait_sec: int = 180) -> bool:
        """
        Monitors Telegram client connection. If disconnected (e.g. network/internet drop):
        - Waits patiently for network/internet connectivity to return.
        - Actively attempts to reconnect the Telegram client.
        - If reconnected, allows the current task to seamlessly continue!
        - If still unreachable after max_wait_sec, re-initializes client or signals clean restart.
        """
        if self.is_stopped:
            return False

        if self.client and self.client.is_connected():
            return True

        log("TG-NET", "⚠️ Telegram disconnected ('Cannot send requests while disconnected'). Waiting for network to return and reconnecting...", instance_name=self.instance_name)
        start_wait = time.time()
        attempt = 0

        while not self.is_stopped and (time.time() - start_wait < max_wait_sec):
            attempt += 1
            elapsed = int(time.time() - start_wait)
            try:
                if self.client:
                    if not self.client.is_connected():
                        log("TG-NET", f"🔄 Attempting Telegram reconnect (attempt #{attempt}, {elapsed}s elapsed)...", instance_name=self.instance_name)
                        await asyncio.wait_for(self.client.connect(), timeout=12.0)

                    if self.client.is_connected():
                        log("TG-NET", f"✨ Internet restored! Telegram reconnected successfully after {elapsed}s. Continuing task...", instance_name=self.instance_name)
                        return True
            except asyncio.TimeoutError:
                log("TG-NET", f"⏳ Connection attempt timed out (no internet yet, {elapsed}s elapsed). Retrying in 5s...", instance_name=self.instance_name)
            except Exception as e:
                log("TG-NET", f"⏳ Waiting for internet to return ({e}, {elapsed}s elapsed). Retrying in 5s...", instance_name=self.instance_name)

            await asyncio.sleep(5.0)

        # If max_wait_sec reached and still disconnected, try full client re-initialization
        if not self.is_stopped and self.account_cfg:
            log("TG-NET", "⚠️ Reconnect timed out. Performing fresh Telegram client initialization...", instance_name=self.instance_name)
            try:
                if self.client:
                    try:
                        if self.client.is_connected():
                            await self.client.disconnect()
                        if hasattr(self.client, 'session') and hasattr(self.client.session, '_conn') and self.client.session._conn:
                            self.client.session._conn.close()
                    except Exception:
                        pass
                clean_phone = re.sub(r'[^0-9]', '', str(self.account_cfg.get("phone", "")))
                sess_name = self.account_cfg.get('session_name') or f"Taskl1_session_{clean_phone}"
                sess_path = os.path.join(BASE_DIR, sess_name) if not os.path.isabs(sess_name) else sess_name
                if not os.path.exists(sess_path + ".session") and not os.path.exists(sess_path):
                    for alt in [f"Taskl1_session_{clean_phone}", f"taskly_session_{clean_phone}"]:
                        alt_p = os.path.join(BASE_DIR, alt)
                        if os.path.exists(alt_p + ".session"):
                            sess_path = alt_p
                            break
                new_client = TelegramClient(sess_path, self.account_cfg['api_id'], self.account_cfg['api_hash'])
                await asyncio.wait_for(new_client.start(phone=clean_phone), timeout=25.0)
                if new_client.is_connected():
                    self.client = new_client
                    self._register_handlers()
                    log("TG-NET", "✨ Fresh Telegram client connected successfully! Continuing task...", instance_name=self.instance_name)
                    return True
            except Exception as reinit_err:
                log("TG-NET", f"❌ Client re-initialization failed: {reinit_err}", instance_name=self.instance_name)

        return False

    async def safe_send_message(self, chat, text, max_retries=5, min_interval=5.0):
        if self.is_stopped:
            return None

        # 1. Throttling: Prevent duplicate repetitive commands (e.g. rapid /start spam)
        clean_text = text.strip()
        cmd_key = f"{chat}_{clean_text.lower()}"
        now = time.time()
        last_sent = self._last_sent_commands.get(cmd_key, 0.0)
        time_diff = now - last_sent

        if time_diff < min_interval:
            if clean_text.startswith("/") or clean_text in ["▶️ Start", "📋 Tasks", "💰 Balance"]:
                log("TG-THROTTLE", f"⏳ Skipping duplicate command '{clean_text}' (sent {time_diff:.1f}s ago to avoid FloodWait)", instance_name=self.instance_name)
                return None
            else:
                await asyncio.sleep(random.uniform(1.2, 2.5))

        # 2. Randomized human delay before sending
        await asyncio.sleep(random.uniform(1.2, 2.5))

        for attempt in range(max_retries):
            if self.is_stopped:
                return None
            try:
                # Ensure connection is active; wait for net if disconnected
                if not self.client or not self.client.is_connected():
                    is_ok = await self.ensure_connected(max_wait_sec=180)
                    if not is_ok:
                        log("TG-ERR", "❌ Network offline: could not send message. Retrying...", instance_name=self.instance_name)
                        return None

                res = await self.client.send_message(chat, text)
                self._last_sent_commands[cmd_key] = time.time()
                return res
            except errors.FloodWaitError as e:
                log("FLOOD-WAIT", f"⚠️ Telegram FloodWait: {e.seconds}s on send_message...", instance_name=self.instance_name)
                if e.seconds > 45:
                    # Heavy flood: auto-rotate account or switch bot
                    rotated = await self.handle_flood_rotation(e.seconds)
                    if rotated:
                        return await self.safe_send_message(self.target_bot, text, max_retries=2)
                    return None
                else:
                    await asyncio.sleep(e.seconds + random.uniform(1.5, 3.5))
            except Exception as e:
                err_str = str(e).lower()
                if "disconnected" in err_str or "connection" in err_str or "network" in err_str:
                    log("TG-NET", f"⚠️ Disconnected during send_message ({e}). Waiting for net to return and reconnecting...", instance_name=self.instance_name)
                    reconnected = await self.ensure_connected(max_wait_sec=180)
                    if reconnected:
                        log("TG-NET", "✨ Net restored! Retrying send_message now...", instance_name=self.instance_name)
                        continue
                log("TG-ERR", f"send_message error ({e}). Retrying...", instance_name=self.instance_name)
                await asyncio.sleep(random.uniform(2.5, 4.0))
        return None

    async def safe_click_button(self, btn, max_retries=5):
        if self.is_stopped:
            return False

        # Human-like thinking delay before clicking
        await asyncio.sleep(random.uniform(1.0, 2.4))

        for attempt in range(max_retries):
            if self.is_stopped:
                return False
            try:
                if not self.client or not self.client.is_connected():
                    is_ok = await self.ensure_connected(max_wait_sec=180)
                    if not is_ok:
                        return False

                await btn.click()
                return True
            except errors.FloodWaitError as e:
                log("FLOOD-WAIT", f"⚠️ Telegram FloodWait on button: {e.seconds}s...", instance_name=self.instance_name)
                if e.seconds > 45:
                    await self.handle_flood_rotation(e.seconds)
                    return False
                else:
                    await asyncio.sleep(e.seconds + random.uniform(1.5, 3.0))
            except Exception as e:
                err_str = str(e).lower()
                if "disconnected" in err_str or "connection" in err_str or "network" in err_str:
                    log("TG-NET", f"⚠️ Disconnected during button click ({e}). Waiting for net to return...", instance_name=self.instance_name)
                    reconnected = await self.ensure_connected(max_wait_sec=180)
                    if reconnected:
                        continue
                await asyncio.sleep(random.uniform(1.5, 3.0))
        return False

    async def click_any_button(self, message, pattern, exclude_pattern=None):
        if message and message.buttons:
            for row_idx, row in enumerate(message.buttons):
                for col_idx, btn in enumerate(row):
                    b_text = btn.text or ""
                    if exclude_pattern and re.search(exclude_pattern, b_text, re.IGNORECASE):
                        continue
                    if re.search(pattern, b_text, re.IGNORECASE):
                        log("TG-BOT", f"👉 [Button Click]: '{b_text}'", instance_name=self.instance_name)
                        if await self.safe_click_button(btn):
                            return True
                        try:
                            await message.click(row_idx, col_idx)
                            return True
                        except Exception:
                            pass
        return False

    async def click_button_by_pattern(self, pattern, exclude_pattern=None):
        try:
            if not self.client or not self.client.is_connected():
                if not await self.ensure_connected(max_wait_sec=60):
                    return False

            candidates = []
            if self.task_confirm_btn_msg and getattr(self.task_confirm_btn_msg, 'buttons', None):
                candidates.append(self.task_confirm_btn_msg)
            recent_msgs = await self.client.get_messages(self.target_bot, limit=6)
            if recent_msgs:
                candidates.extend(recent_msgs)

            seen_ids = set()
            for msg in candidates:
                if not msg or getattr(msg, 'id', None) in seen_ids:
                    continue
                seen_ids.add(msg.id)
                if msg.buttons:
                    msg_age = (datetime.now(timezone.utc) - msg.date).total_seconds() if msg.date else 0
                    if msg_age > 300:
                        continue
                    for row_idx, row in enumerate(msg.buttons):
                        for col_idx, btn in enumerate(row):
                            b_text = getattr(btn, 'text', '') or ""
                            if exclude_pattern and re.search(exclude_pattern, b_text, re.IGNORECASE):
                                continue
                            if re.search(pattern, b_text, re.IGNORECASE):
                                log("TG-BOT", f"👉 [Button Click on msg #{msg.id}]: '{b_text}'", instance_name=self.instance_name)
                                self.task_confirm_btn_msg = msg
                                if await self.safe_click_button(btn):
                                    return True
                                try:
                                    await msg.click(row_idx, col_idx)
                                    return True
                                except Exception:
                                    pass
                                try:
                                    await self.safe_send_message(self.target_bot, b_text)
                                    return True
                                except Exception:
                                    pass
        except Exception as e:
            log("TG-WARN", f"Error searching recent messages: {e}", instance_name=self.instance_name)
        return False

    async def fetch_bot_balance(self) -> Optional[str]:
        """Requests account balance from Telegram bot using '💰 Balance' command or button."""
        if self.task_mode in ["only_meta", "only meta", "only mete"] or "realearning" in (self.target_bot or "").lower():
            return None
        try:
            if not self.client or not self.client.is_connected():
                if not await self.ensure_connected(max_wait_sec=60):
                    return None

            log("TG-BALANCE", f"💰 Requesting balance update from @{self.target_bot}...", instance_name=self.instance_name)
            clicked = await self.click_button_by_pattern(r"Balance|💰\s*Balance|💰")
            if not clicked:
                await self.safe_send_message(self.target_bot, "💰 Balance")

            # Lightweight gentle polling (max 4 checks every 1.2s to prevent flood)
            for _ in range(4):
                await asyncio.sleep(1.2)
                recent_msgs = await self.client.get_messages(self.target_bot, limit=2)
                for msg in recent_msgs:
                    t = (msg.text or "").strip()
                    if ("balance" in t.lower() or "your balance" in t.lower()) and ("$" in t or re.search(r"\d+\.\d+", t)):
                        m_bal = re.search(r"(\$[\d\.]+|\d+\.\d{2,4})", t)
                        if m_bal:
                            bal_str = m_bal.group(1)
                            if not bal_str.startswith("$"):
                                bal_str = f"${bal_str}"
                            self.current_balance = bal_str
                            log("TG-BALANCE", f"💰 Current Balance: {bal_str}", instance_name=self.instance_name)
                            return bal_str
        except Exception as e:
            log("TG-WARN", f"Failed fetching balance: {e}", instance_name=self.instance_name)
        return self.current_balance

    async def handle_bot_message(self, event):
        msg = event.message
        text = (msg.text or "").strip()
        if not text:
            return

        now = time.time()
        msg_key = f"{msg.id}_{text[:25]}"
        if msg_key == self._last_processed_key and (now - self._last_processed_time) < 1.5:
            return
        self._last_processed_key = msg_key
        self._last_processed_time = now

        if msg.buttons:
            self.task_confirm_btn_msg = msg

        try:
            sender = await event.get_sender()
            sender_bot = (getattr(sender, 'username', '') or "").lstrip("@")
            if sender_bot:
                # If Auto-Shift is OFF, strictly ignore messages from other bots
                if sender_bot.lower() != self.target_bot.lower():
                    if not self.auto_shift:
                        return
                    if any(sender_bot.lower() == b.lower() for b in self.target_bots):
                        for idx, b in enumerate(self.target_bots):
                            if sender_bot.lower() == b.lower():
                                self.target_bot = b
                                self.current_bot_idx = idx
                                break
                    else:
                        return
        except Exception:
            pass

        log("TG-RECV", f"📩 Message from @{self.target_bot}:\n{text}", instance_name=self.instance_name)

        # 0. Balance check
        if ("your balance:" in text.lower() or "balance:" in text.lower()) and ("$" in text or re.search(r"\d+\.\d+", text)):
            m_bal = re.search(r"(\$[\d\.]+|\d+\.\d{2,4})", text)
            if m_bal:
                bal_str = m_bal.group(1)
                if not bal_str.startswith("$"):
                    bal_str = f"${bal_str}"
                self.current_balance = bal_str
                log("TG-BALANCE", f"💰 Current Balance: {bal_str}", instance_name=self.instance_name)

        # 0.5 RealEarningBangladesh_Bot / Only Meta: Managed sequentially by process_only_meta_cycle
        if self.task_mode in ["only_meta", "only meta", "only mete"] or "realearning" in (self.target_bot or "").lower():
            # In Only Meta mode, the entire Telegram dialogue is strictly driven by process_only_meta_cycle()
            return

        # 0.5.5 Bot Channel Join Verification / Welcome Prompt
        elif ("click the joined button" in text.lower() or "joined button" in text.lower() or "join all required channels" in text.lower()):
            log("TG-STEP", "Channel join verification received -> Clicking 'Joined'...", instance_name=self.instance_name)
            await asyncio.sleep(random.uniform(1.0, 1.5))
            clicked = await self.click_any_button(msg, r"Joined|✅\s*Joined|Join")
            if not clicked:
                clicked = await self.click_button_by_pattern(r"Joined|✅\s*Joined|Join")
            if not clicked:
                await self.safe_send_message(self.target_bot, "✅ Joined")
            return

        # 1. Account Credentials Received (First name, Login, Password) - MUST BE CHECKED FIRST
        fn_match = re.search(r"(?:First\s*name|Full\s*name|Name)[\s\*\_]*[:：\-]\s*([^\r\n]+)", text, re.IGNORECASE)
        login_match = re.search(r"(?:Login|Username|User)[\s\*\_]*[:：\-]\s*([^\r\n]+)", text, re.IGNORECASE)
        pass_match = re.search(r"(?:Password|Pass)[\s\*\_]*[:：\-]\s*([^\r\n]+)", text, re.IGNORECASE)

        if login_match or ((fn_match or login_match) and pass_match):
            log("TG-STEP", "Task Target Username Acquired from Telegram Bot!", instance_name=self.instance_name)
            raw_fn = fn_match.group(1).strip().replace("`", "").replace("*", "").strip() if fn_match else ""
            clean_fn = re.sub(r'[^\w\s]', '', raw_fn).strip()
            name_parts = clean_fn.split() if clean_fn else []
            if len(name_parts) >= 2:
                self.current_task['first_name'] = name_parts[0]
                self.current_task['last_name'] = " ".join(name_parts[1:])
            elif name_parts:
                self.current_task['first_name'] = name_parts[0]
                self.current_task['last_name'] = "User"
            else:
                self.current_task['first_name'] = "User"
                self.current_task['last_name'] = "Account"

            self.current_task['login'] = login_match.group(1).strip().replace("`", "").replace("*", "").strip() if login_match else ""
            # Note: We only take username from bot; Meta account & password come directly from meta.csv
            self.current_task['password'] = pass_match.group(1).strip().replace("`", "").replace("*", "").strip() if pass_match else ""
            self.current_task['two_fa_key'] = None
            self.current_task['otp_code'] = None
            self.current_task['status'] = 'credentials_ready'
            self.task_cancelled_event.clear()

            print("\n" + "="*50)
            print(f"📋 [{self.instance_name}] [BOT TASK USERNAME ACQUIRED]")
            print(f"👤 Full Name     : {self.current_task['first_name']} {self.current_task['last_name']}")
            print(f"🔑 Target User   : {self.current_task['login']}")
            print("📁 Meta Account  : Will be acquired directly from meta.csv")
            print("="*50 + "\n")

            self.task_received_event.set()
            return

        # 1.5 Bot asks for account Cookie
        elif (("cookie" in text.lower() and any(w in text.lower() for w in ["send", "enter", "submit", "account cookie", "cookie:"])) or "account cookie" in text.lower()) \
             and ("review time" not in text.lower() and "description:" not in text.lower() and "select a task" not in text.lower()):
            log("TG-STEP", "🍪 Bot is requesting account Cookie...", instance_name=self.instance_name)
            self.cookies_requested_event.set()
            self.current_task['cookies_requested'] = True

            # If task credentials were provided in the same message, parse them:
            fn_m = re.search(r"(?:First\s*name|Full\s*name|Name)\s*:\s*([^\r\n]+)", text, re.IGNORECASE)
            lg_m = re.search(r"(?:Login|Username|User)\s*:\s*([^\r\n]+)", text, re.IGNORECASE)
            pw_m = re.search(r"(?:Password|Pass)\s*:\s*([^\r\n]+)", text, re.IGNORECASE)
            if lg_m and pw_m:
                self.current_task['login'] = lg_m.group(1).strip().replace("`", "").replace("*", "").strip()
                self.current_task['password'] = pw_m.group(1).strip().replace("`", "").replace("*", "").strip()
                raw_fn = fn_m.group(1).strip().replace("`", "").replace("*", "").strip() if fn_m else "User"
                parts = raw_fn.split()
                self.current_task['first_name'] = parts[0] if parts else "User"
                self.current_task['last_name'] = " ".join(parts[1:]) if len(parts) > 1 else "Account"
                self.current_task['status'] = 'credentials_ready'
                self.task_received_event.set()
                log("TG-CREDS", f"Parsed bot credentials: {self.current_task['first_name']} {self.current_task['last_name']} | User: {self.current_task['login']}", instance_name=self.instance_name)
            elif not self.current_task.get('login') or self.current_task.get('status') != 'credentials_ready':
                # Check recent chat history first! (Bot often sends credentials as a separate message right before or after)
                found_in_history = False
                for wait_round in range(8):
                    try:
                        recent_msgs = await self.client.get_messages(self.target_bot, limit=5)
                        for rmsg in recent_msgs:
                            rtxt = rmsg.text or ""
                            r_lg = re.search(r"(?:Login|Username|User)\s*:\s*([^\r\n]+)", rtxt, re.IGNORECASE)
                            r_pw = re.search(r"(?:Password|Pass)\s*:\s*([^\r\n]+)", rtxt, re.IGNORECASE)
                            if (r_lg or "Login" in rtxt) and r_pw:
                                r_fn = re.search(r"(?:First\s*name|Full\s*name|Name)\s*:\s*([^\r\n]+)", rtxt, re.IGNORECASE)
                                raw_fn = r_fn.group(1).strip().replace("`", "").replace("*", "").strip() if r_fn else "User"
                                clean_fn = re.sub(r'[^\w\s]', '', raw_fn).strip()
                                parts = clean_fn.split() if clean_fn else []
                                self.current_task['first_name'] = parts[0] if parts else "User"
                                self.current_task['last_name'] = " ".join(parts[1:]) if len(parts) > 1 else "Account"
                                self.current_task['login'] = r_lg.group(1).strip().replace("`", "").replace("*", "").strip() if r_lg else ""
                                self.current_task['password'] = r_pw.group(1).strip().replace("`", "").replace("*", "").strip() if r_pw else ""
                                self.current_task['status'] = 'credentials_ready'
                                self.task_received_event.set()
                                log("TG-CREDS", f"✔ Acquired bot credentials from chat history: {self.current_task['first_name']} {self.current_task['last_name']} | User: {self.current_task['login']} | Password: {self.current_task['password']}", instance_name=self.instance_name)
                                found_in_history = True
                                break
                    except Exception as hist_err:
                        log("TG-WARN", f"History check error: {hist_err}", instance_name=self.instance_name)

                    if found_in_history:
                        break
                    # Wait 0.4s and retry checking chat (up to 3.2s total)
                    await asyncio.sleep(0.4)

                if not found_in_history and (not self.current_task.get('login') or self.current_task.get('status') != 'credentials_ready'):
                    first, last = get_random_name()
                    pwd = generate_custom_password(instance_name=self.instance_name)
                    clean_fn = re.sub(r'[^a-zA-Z0-9]', '', first).lower() or "user"
                    random_chars = ''.join(random.choices(string.ascii_lowercase, k=6))
                    uname = f"{clean_fn}_{random_chars}"
                    self.current_task['first_name'] = first
                    self.current_task['last_name'] = last
                    self.current_task['login'] = uname
                    self.current_task['password'] = pwd
                    self.current_task['status'] = 'credentials_ready'
                    self.task_received_event.set()
                    log("TG-CREDS", f"Generated profile for Cookies task: {first} {last} | User: {uname} | Pwd: {pwd}", instance_name=self.instance_name)

            # If cookies already extracted, submit them immediately!
            cookies = self.current_task.get('cookies')
            if cookies and not self.current_task.get('cookies_sent'):
                log("TG-BOT", f"🍪 Submitting captured Cookies to @{self.target_bot}...", instance_name=self.instance_name)
                await asyncio.sleep(DELAY_BETWEEN_STEPS)
                await self.safe_send_message(self.target_bot, cookies)
                self.current_task['cookies_sent'] = True
            return

        # 2. Bot asks for 2FA key or invalid key format retry (MUST NOT match task descriptions)
        elif ("2fa key" in text.lower() or "enter your 2fa" in text.lower() or "invalid key format" in text.lower() or "please enter your 2fa" in text.lower() or "send the 2fa" in text.lower() or "send 2fa" in text.lower()) \
             and ("review time" not in text.lower() and "description:" not in text.lower() and "report instruction" not in text.lower() and "in this task" not in text.lower()):
            log("TG-STEP", "Bot is requesting 2FA Secret Key...", instance_name=self.instance_name)
            self.two_fa_requested_event.set()
            key = self.current_task.get('two_fa_key')
            if key and len(key) >= 16:
                log("TG-BOT", f"🔑 Sending 2FA Secret Key '{key}' to @{self.target_bot}...", instance_name=self.instance_name)
                await asyncio.sleep(DELAY_BETWEEN_STEPS)
                await self.safe_send_message(self.target_bot, key)
                self.current_task['two_fa_sent'] = True
            return

        # 2.5 Welcome / Initial menu
        elif "welcome" in text.lower() or "terms of use" in text.lower() or "earn money" in text.lower() or "main menu" in text.lower():
            if self.current_task.get('status') in ('running', 'credentials_ready') or self.current_task.get('login') or self.task_received_event.is_set():
                if not (self.task_mode in ["only_meta", "only meta", "only mete"] or "realearning" in (self.target_bot or "").lower()):
                    return
            log("TG-STEP", "Welcome / Main Menu received -> Opening Tasks menu...", instance_name=self.instance_name)
            await asyncio.sleep(random.uniform(1.2, 2.5))
            if self.task_mode in ["only_meta", "only meta", "only mete"] or "realearning" in (self.target_bot or "").lower():
                clicked = await self.click_any_button(msg, r"(?:📱|📳|📲)?\s*(?:Task|𝑻𝒂𝒔𝒌|টাস্ক)\s*♻️?", exclude_pattern=r"Social|𝑺𝒐𝒄𝒊𝒂𝒍")
                if not clicked:
                    clicked = await self.click_button_by_pattern(r"(?:📱|📳|📲)?\s*(?:Task|𝑻𝒂𝒔𝒌|টাস্ক)\s*♻️?", exclude_pattern=r"Social|𝑺𝒐𝒄𝒊𝒂𝒍")
                if not clicked:
                    await self.safe_send_message(self.target_bot, "📱 𝑻𝒂𝒔𝒌 ♻️")
            else:
                clicked = await self.click_any_button(msg, r"Tasks|📋|Task|𝑻𝒂𝒔𝒌|টাস্ক")
                if not clicked:
                    clicked = await self.click_button_by_pattern(r"Tasks|📋|Task|𝑻𝒂𝒔𝒌|টাস্ক")
                if not clicked:
                    await self.safe_send_message(self.target_bot, "📋 Tasks")
            return

        # 2.6 Select task
        elif "please select a task" in text.lower() or "select a task" in text.lower() or "choose a task" in text.lower():
            if self.current_task.get('status') in ('running', 'credentials_ready') or self.current_task.get('login') or self.task_received_event.is_set():
                return
            await asyncio.sleep(random.uniform(1.8, 3.2))
            if self.task_mode in ["cookies", "2fa_cookies", "random_2fa_cookies"]:
                log("TG-STEP", f"Selecting '🍪' category button for @{self.target_bot} (Task Mode: {self.task_mode})...", instance_name=self.instance_name)
                # Match cookie button by cookie icon 🍪 or word Cookies/Cookie (e.g. '🍪 ($0.0250)', '🍪 Cookies ($0.0200)')
                clicked = await self.click_any_button(msg, r"🍪|Cookies|Cookie")
                if not clicked:
                    clicked = await self.click_button_by_pattern(r"🍪|Cookies|Cookie")
                if not clicked and msg.buttons:
                    for row in msg.buttons:
                        for b in row:
                            if re.search(r"🍪|Cookies|Cookie", b.text or "", re.IGNORECASE):
                                log("TG-BOT", f"👉 [Button Fallback Click]: '{b.text}'", instance_name=self.instance_name)
                                await self.safe_send_message(self.target_bot, b.text)
                                clicked = True
                                break
                        if clicked:
                            break
                if not clicked:
                    log("TG-WARN", "Could not locate cookie icon button on keyboard.", instance_name=self.instance_name)
            else:
                is_taskly = ("taskly" in (self.target_bot or "").lower()) or ("taskl1" in (self.target_bot or "").lower())
                if is_taskly:
                    log("TG-STEP", f"Selecting option: 'Create Inst' for @{self.target_bot}...", instance_name=self.instance_name)
                    clicked = await self.click_any_button(msg, r"2FA|No\s*mail|Create\s*Inst")
                    if not clicked:
                        clicked = await self.click_any_button(msg, r"Create\s*Inst")
                    if not clicked:
                        clicked = await self.click_button_by_pattern(r"2FA|No\s*mail|Create\s*Inst")
                    if not clicked and msg.buttons:
                        for row in msg.buttons:
                            for b in row:
                                if "Create Inst" in (b.text or "") or "2FA" in (b.text or ""):
                                    await self.safe_send_message(self.target_bot, b.text)
                                    clicked = True
                                    break
                            if clicked:
                                break
                else:
                    log("TG-STEP", "Selecting task '🔥Create Inst (2FA)' for @PayGoeasy_bot...", instance_name=self.instance_name)
                    clicked = await self.click_any_button(msg, r"2FA|Create\s*Inst.*2FA")
                    if not clicked:
                        clicked = await self.click_any_button(msg, r"Create\s*Inst")
                    if not clicked:
                        clicked = await self.click_button_by_pattern(r"2FA|Create\s*Inst")
                    if not clicked and msg.buttons:
                        for row in msg.buttons:
                            for b in row:
                                if "Create Inst" in (b.text or "") or "2FA" in (b.text or ""):
                                    await self.safe_send_message(self.target_bot, b.text)
                                    clicked = True
                                    break
                            if clicked:
                                break
            return

        # 2.7 Cookies Submenu
        elif "cookies:" in text.lower() or "🍪:" in text or text.strip() == "🍪:" or (text.strip().startswith("🍪") and any("inst" in (b.text or "").lower() for row in (msg.buttons or []) for b in row)):
            if self.current_task.get('status') in ('running', 'credentials_ready') or self.current_task.get('login') or self.task_received_event.is_set():
                return
            await asyncio.sleep(random.uniform(1.8, 3.2))
            log("TG-STEP", f"Selecting Instagram task from Cookies sub-menu for @{self.target_bot}...", instance_name=self.instance_name)
            # Matches:
            # - Taskl1_bot: '🍪 Create Inst (No mail) ($0.0210)'
            # - PayGoeasy_bot: '📱 Create Inst (Cookies) ($0.0200)'
            clicked = await self.click_any_button(msg, r"Create\s*Inst|Create\s*Instagram|🍪\s*Create|Inst.*Cookies|Inst.*No\s*mail|No\s*mail")
            if not clicked:
                clicked = await self.click_button_by_pattern(r"Create\s*Inst|Create\s*Instagram|🍪\s*Create|Inst.*Cookies|Inst.*No\s*mail|No\s*mail")
            if not clicked and msg.buttons:
                for row in msg.buttons:
                    for b in row:
                        if re.search(r"Create\s*Inst|Instagram|Inst", b.text or "", re.IGNORECASE):
                            log("TG-BOT", f"👉 [Button Fallback Click]: '{b.text}'", instance_name=self.instance_name)
                            await self.safe_send_message(self.target_bot, b.text)
                            clicked = True
                            break
                    if clicked:
                        break
            return

        # 2.8 Start task (Trigger ▶️ Start to receive credentials from task description)
        elif ("review time" in text.lower() or "description:" in text.lower() or "report instruction" in text.lower() or "📋 task:" in text.lower() or ("in this task" in text.lower() and "required!" in text.lower())) \
             and ("select a task" not in text.lower() and "choose a task" not in text.lower()):
            if self.current_task.get('status') in ('running', 'credentials_ready') and self.current_task.get('login'):
                log("TG-INFO", "Already have active credentials, skipping redundant Start click.", instance_name=self.instance_name)
                return
            log("TG-STEP", "Task description received -> Triggering ▶️ Start...", instance_name=self.instance_name)
            await asyncio.sleep(random.uniform(1.2, 2.5))
            clicked = await self.click_any_button(msg, r"Start|▶️")
            if not clicked:
                clicked = await self.click_button_by_pattern(r"Start|▶️")
            if not clicked:
                await self.safe_send_message(self.target_bot, "▶️ Start")
            return

        # 3. Registration Confirmation (ONLY when task is active, and NEVER for task descriptions, task selection, or after report received)
        elif ("confirm registration" in text.lower() or "account registered" in text.lower() or "cancel the task:" in text.lower() or "registered or cancel" in text.lower()) \
             and ("review time" not in text.lower() and "description:" not in text.lower() and "in this task" not in text.lower() and "report instruction" not in text.lower() and "select a task" not in text.lower()):
            if self.current_task.get('report_received') or self.report_received_event.is_set():
                log("TG-INFO", "✔ Report already received! Ignoring extra registration confirmation prompt.", instance_name=self.instance_name)
                return
            if not self.current_task.get('login') and self.current_task.get('status') not in ('running', 'credentials_ready'):
                log("TG-WARN", "Ignoring 'Account registered' pattern because no active task credentials exist yet.", instance_name=self.instance_name)
                return
            if self.current_task.get('account_registered_sent'):
                log("TG-INFO", "Already sent 'Account registered' once! Waiting for bot confirmation...", instance_name=self.instance_name)
                return

            # In 2FA + Cookies mode: ensure 2FA and Cookies are sent before confirmation!
            if self.task_mode in ["2fa_cookies", "random_2fa_cookies"]:
                key = self.current_task.get('two_fa_key')
                if key and len(key) >= 16 and not self.current_task.get('two_fa_sent'):
                    log("TG-BOT", f"🔑 [{self.task_mode.upper()}] Sending 2FA Key '{key}' before confirming registration...", instance_name=self.instance_name)
                    await self.safe_send_message(self.target_bot, key)
                    self.current_task['two_fa_sent'] = True
                    await asyncio.sleep(1.5)
                cookies = self.current_task.get('cookies')
                if cookies and not self.current_task.get('cookies_sent'):
                    log("TG-BOT", f"🍪 [{self.task_mode.upper()}] Submitting Cookies before confirming registration...", instance_name=self.instance_name)
                    await self.safe_send_message(self.target_bot, cookies)
                    self.current_task['cookies_sent'] = True
                    await asyncio.sleep(1.5)

            self.current_task['account_registered_sent'] = True
            log("TG-STEP", "Bot requested registration confirmation -> Clicking '✅ Account registered' (ONCE)...", instance_name=self.instance_name)
            clicked = await self.click_any_button(msg, r"Account registered|Registered|✅")
            if not clicked:
                clicked = await self.click_button_by_pattern(r"Account registered|Registered|✅")
            if not clicked and self.task_mode != "cookies" and (self.current_task.get('cookies_sent') or self.current_task.get('two_fa_sent') or self.current_task.get('status') == 'running'):
                await self.safe_send_message(self.target_bot, "✅ Account registered")
            return

        # 3.5 Bot sends OTP code
        elif "Your one-time code" in text or "Tap the code to copy" in text or (len(re.findall(r"\b\d{6}\b", text)) > 0 and self.current_task.get('two_fa_key')):
            log("TG-STEP", "One-time OTP code received from bot!", instance_name=self.instance_name)
            code_match = re.search(r"\b\d{6}\b", text)
            if code_match:
                self.current_task['otp_code'] = code_match.group(0)
                log("TG-OTP", f"🔑 Captured 6-Digit OTP: {self.current_task['otp_code']}", instance_name=self.instance_name)
                self.otp_received_event.set()

            if msg.buttons:
                self.task_confirm_btn_msg = msg
            return

        # 4. Report Received
        elif "report has been received" in text.lower() or "report received" in text.lower() or "your report has been received" in text.lower() or "task completed" in text.lower() or "reviewed shortly" in text.lower():
            if self.current_task.get('report_received') or self.report_received_event.is_set():
                log("TG-INFO", f"Report confirmation already recorded for this cycle. Total remains: {self.submitted_count}", instance_name=self.instance_name)
                return
            if self.current_task.get('status') not in ('running', 'submitted', 'credentials_ready') and not self.current_task.get('cookies_sent') and not self.current_task.get('two_fa_sent'):
                log("TG-WARN", "Ignoring report confirmation because no active submission was in progress.", instance_name=self.instance_name)
                return

            self.submitted_count += 1
            log("TG-SUBMITTED", f"📥 [SUBMITTED] Report received by Bot! (Total: {self.submitted_count})", instance_name=self.instance_name)
            self.current_task['report_received'] = True
            self.current_task['status'] = 'submitted'
            self.report_received_event.set()
            return

        # 4.5 Report Rejected / Time's up
        elif "report rejected" in text.lower() or "task rejected" in text.lower() or "task cancelled" in text.lower() or "time's up" in text.lower():
            clean_rej = text.replace('\n', ' ').strip()
            log("TG-REJECTED", f"❌ Bot rejected or cancelled task: '{clean_rej}'", instance_name=self.instance_name)
            self.current_task['status'] = 'rejected'
            self.task_cancelled_event.set()
            return

        # 5. Report Approved
        elif "report approved" in text.lower() or "+$0.03" in text or "+$0.02" in text or "+$0.0" in text or "approved, +" in text.lower() or "credited to your balance" in text:
            self.approved_count += 1
            log("TG-APPROVED", f"💰 [APPROVED] Report approved! (Total Approved: {self.approved_count})", instance_name=self.instance_name)
            return

        # 5.8 Hourly Limit Handling ("This hour's limit is reached. Next execution will be available in...")
        elif any(phrase in text.lower() for phrase in [
            "hour's limit is reached",
            "hours limit is reached",
            "limit is reached",
            "hourly limit",
            "next execution will be available in",
            "next execution will be available",
            "hour limit is reached",
            "hourly limit reached"
        ]):
            clean_msg = text.replace('\n', ' ').strip()
            if self.auto_shift:
                log("HOURLY-LIMIT", f"⏳ Bot @{self.target_bot} hourly limit: '{clean_msg}'. Auto-Shift is ON! Switching to other bot...", instance_name=self.instance_name)
                old_bot = self.target_bot
                new_bot = await self.switch_target_bot()
                if self.shift_task_mode and self.shift_task_mode in ["2fa", "cookies", "2fa_cookies", "random_2fa_cookies"]:
                    old_mode = self.task_mode
                    self.task_mode = self.shift_task_mode
                    log("TG-SHIFT-TASK", f"🔄 Switched task mode: {old_mode.upper()} ➔ {self.task_mode.upper()} for @{new_bot}", instance_name=self.instance_name)

                self.is_hourly_limited = False
                self.hourly_limit_event.clear()
                self.hourly_limit_until = None
                self.current_task['status'] = 'idle'
                self.current_task['login'] = None
                self.task_received_event.set()
                self.task_cancelled_event.set()
                if self.on_state_change:
                    try:
                        mode_icon = "🎲" if "random" in self.task_mode else ("🍪" if self.task_mode == "cookies" else ("🔐" if "2fa_cookies" in self.task_mode else "🔑"))
                        self.on_state_change(self.instance_name, f"Running ({mode_icon} @{self.target_bot})", "running")
                    except Exception:
                        pass
                return
            else:
                now = datetime.now()
                # Calculate target restart time at :59:55 of current hour (or next hour if already past :59:55)
                if now.minute < 59 or (now.minute == 59 and now.second < 55):
                    next_hour = now.replace(minute=59, second=55, microsecond=0)
                else:
                    next_hour = (now + timedelta(hours=1)).replace(minute=59, second=55, microsecond=0)

                wait_s = max(5, int((next_hour - now).total_seconds()))
                rem_m = wait_s // 60
                rem_sec = wait_s % 60
                log("HOURLY-LIMIT", f"⏳ Bot @{self.target_bot} hourly limit: '{clean_msg}'. Auto-Shift is OFF. Cooldown until {next_hour.strftime('%H:%M:%S')} ({rem_m}m {rem_sec}s)...", instance_name=self.instance_name)
                self.is_hourly_limited = True
                self.hourly_limit_until = next_hour
                self.hourly_limit_event.set()
                self.current_task['status'] = 'hourly_limited'
                if self.on_state_change:
                    try:
                        self.on_state_change(self.instance_name, f"⏳ {rem_m}m {rem_sec:02d}s", "waiting")
                    except Exception:
                        pass
                self.task_received_event.set()
                self.task_cancelled_event.set()
                return

        # 6. Rate Limit Handling
        elif "making requests too often" in text or "too often" in text.lower() or ("please wait" in text.lower() and "sec" in text.lower()):
            wait_match = re.search(r"wait\s*(\d+)\s*sec", text, re.IGNORECASE)
            wait_s = int(wait_match.group(1)) if wait_match else 20
            log("TG-RATE-LIMIT", f"⏳ Bot @{self.target_bot} rate-limited! (Cooldown {wait_s}s)", instance_name=self.instance_name)

            # If rate limit is high (>25s), alternate to another bot immediately ONLY if auto_shift is enabled
            if wait_s > 25:
                if self.auto_shift:
                    log("TG-RATE-LIMIT", f"🔄 Bot @{self.target_bot} cooldown is long ({wait_s}s). Auto-Shift is ON -> Switching to other bot...", instance_name=self.instance_name)
                    new_bot = await self.switch_target_bot()
                    if self.shift_task_mode and self.shift_task_mode in ["2fa", "cookies", "2fa_cookies", "random_2fa_cookies"]:
                        self.task_mode = self.shift_task_mode
                    return
                else:
                    log("TG-RATE-LIMIT", f"⏳ Bot @{self.target_bot} cooldown is {wait_s}s. Auto-Shift is OFF -> Remaining on @{self.target_bot}...", instance_name=self.instance_name)


            await asyncio.sleep(wait_s + random.uniform(1.5, 3.0))
            if self.current_task.get('status') in ('running', 'credentials_ready') or self.current_task.get('login') or self.is_stopped:
                return
            btn_clicked = await self.click_button_by_pattern(r"Start|▶️")
            if not btn_clicked:
                await self.safe_send_message(self.target_bot, "▶️ Start")
            return

        # 7. Time's up / Cancelled (Clean reset without immediate /start spam)
        elif "time's up" in text.lower() or "task cancelled" in text.lower() or "action cancelled" in text.lower():
            if self.current_task.get('report_received'):
                log("TG-INFO", "Ignoring cancellation notice because report was already marked as received.", instance_name=self.instance_name)
                return
            log("TG-WARN", "⏰ Task cancelled by bot! Flagging task for clean cycle reset...", instance_name=self.instance_name)
            self.current_task['status'] = 'cancelled'
            self.current_task['cancelled'] = True
            self.task_cancelled_event.set()
            self.task_received_event.set()
            self.two_fa_requested_event.set()
            self.report_received_event.clear()
            return

    async def wait_for_hourly_reset(self):
        """Freezes cycle execution immediately upon hitting hourly limit and sleeps until :59:55."""
        now = datetime.now()
        if not self.hourly_limit_until or self.hourly_limit_until <= now:
            if now.minute < 59 or (now.minute == 59 and now.second < 55):
                self.hourly_limit_until = now.replace(minute=59, second=55, microsecond=0)
            else:
                self.hourly_limit_until = (now + timedelta(hours=1)).replace(minute=59, second=55, microsecond=0)

        target = self.hourly_limit_until
        target_str = target.strftime('%H:%M:%S')
        total_wait = max(5, int((target - now).total_seconds()))
        log("HOURLY-FREEZE", f"⏸ Cycle frozen! Clock is {now.strftime('%H:%M:%S')}. Next restart scheduled for {target_str} ({total_wait // 60}m {total_wait % 60}s)...", instance_name=self.instance_name)

        while not self.is_stopped and datetime.now() < target:
            rem_s = int((target - datetime.now()).total_seconds())
            if rem_s <= 0:
                break
            rem_m = rem_s // 60
            rem_sec = rem_s % 60
            if self.on_state_change:
                try:
                    self.on_state_change(self.instance_name, f"⏳ {rem_m}m {rem_sec:02d}s", "waiting")
                except Exception:
                    pass
            await asyncio.sleep(1.0)

        if not self.is_stopped:
            now_str = datetime.now().strftime('%H:%M:%S')
            log("HOURLY-RESUME", f"⏰ Restart time reached ({now_str})! Unfreezing cycle and restarting bot with /start...", instance_name=self.instance_name)
            self.is_hourly_limited = False
            self.hourly_limit_event.clear()
            self.hourly_limit_until = None
            self.consecutive_fails = 0
            self.consecutive_timeouts = 0
            self.current_task['status'] = 'idle'
            self.current_task['login'] = None
            if self.on_state_change:
                try:
                    self.on_state_change(self.instance_name, f"Running (@{self.target_bot})", "running")
                except Exception:
                    pass

    async def process_only_meta_cycle(self, meta_email: str, target_password: str, target_username: str, cycle_num: int) -> bool:
        """
        Executes the exact Telegram sequence for @RealEarningBangladesh_Bot in 'Only Meta' mode:
        1. Cycle 1 sends /start (and clicks 'Joined' if verification button exists).
        2. Clicks or sends '📱 𝑻𝒂𝒔𝒌 ♻️'.
        3. Waits for delay, detects '🛒 ✨  ট্রেডিং মার্কেট ✨', and clicks '🆕 Meta Ai 📧'.
        4. Waits for delay, verifies bot sent '🤖 Meta AI ... 📩 এখন আপনার Meta AI Gmail পাঠান।👇'.
        5. Sends meta_email.
        6. Waits for bot's response 'জিমেইল অ্যাড্রেস সেভ করা হয়েছে! ... 🔑 এবার আপনার অ্যাকাউন্টের পাসওয়ার্ড (Password) দিন:⤵️ ⚠️ Password must be ...'.
        7. Sends password (e.g. saikat50968).
        8. Waits for bot's confirmation '✅ আপনার Meta AI রিকুয়েস্ট পাঠানো হয়েছে। 🆔 Request ID: MA-...'.
        9. Records credentials.
        """
        TASK_REGEX = r"(?:📱|📳|📲)?\s*(?:Task|𝑻𝒂𝒔𝒌|টাস্ক)\s*♻️?"
        TASK_EXCLUDE = r"Social|𝑺𝒐𝒄𝒊𝒂𝒍"

        # 1. First cycle only: Send /start
        if not self.only_meta_started:
            log("ONLY-META", f"First cycle: Sending /start to @{self.target_bot}...", instance_name=self.instance_name)
            await self.safe_send_message(self.target_bot, "/start")
            self.only_meta_started = True
            await asyncio.sleep(2.5)

            # Check if Joined verification button exists
            clicked_joined = await self.click_button_by_pattern(r"Joined|✅\s*Joined|Join")
            if clicked_joined:
                log("ONLY-META", "Clicked 'Joined' verification button...", instance_name=self.instance_name)
                await asyncio.sleep(2.0)

        # 2. Send '📱 𝑻𝒂𝒔𝒌 ♻️' (First cycle or repeated cycle)
        log("ONLY-META", f"[Step 1] Sending '📱 𝑻𝒂𝒔𝒌 ♻️' to @{self.target_bot}...", instance_name=self.instance_name)
        clicked_task = await self.click_button_by_pattern(TASK_REGEX, exclude_pattern=TASK_EXCLUDE)
        if not clicked_task:
            await self.safe_send_message(self.target_bot, "📱 𝑻𝒂𝒔𝒌 ♻️")

        # 3. '📱 𝑻𝒂𝒔𝒌 ♻️ commad er por aktu delay dia 🆕Meta Ai 📧 select korbe'
        log("ONLY-META", "[Step 2] Waiting for Trading Market menu from bot...", instance_name=self.instance_name)
        trading_menu_msg = None
        for wait_i in range(12):  # up to 15s
            await asyncio.sleep(1.2)
            try:
                recent_msgs = await self.client.get_messages(self.target_bot, limit=4)
            except Exception:
                recent_msgs = []
            for m in recent_msgs:
                mtxt = m.text or ""
                if "ট্রেডিং মার্কেট" in mtxt or "trading market" in mtxt.lower() or "টাস্ক কমপ্লিট করতে" in mtxt:
                    trading_menu_msg = m
                    break
                if m.buttons:
                    for row in m.buttons:
                        for b in row:
                            if re.search(r"Meta\s*Ai", b.text or "", re.IGNORECASE) and not re.search(r"Gmail|Instagram|Old", b.text or "", re.IGNORECASE):
                                trading_menu_msg = m
                                break
            if trading_menu_msg:
                break

        if not trading_menu_msg:
            log("ONLY-META-WARN", "Trading Market menu not received in time. Retrying Task click...", instance_name=self.instance_name)
            clicked_task = await self.click_button_by_pattern(TASK_REGEX, exclude_pattern=TASK_EXCLUDE)
            if not clicked_task:
                await self.safe_send_message(self.target_bot, "📱 𝑻𝒂𝒔𝒌 ♻️")
            await asyncio.sleep(2.5)

        # Explicit delay before selecting '🆕Meta Ai 📧' (as requested)
        delay_before_select = random.uniform(1.8, 2.8)
        log("ONLY-META", f"Delaying {delay_before_select:.1f}s before selecting '🆕Meta Ai 📧'...", instance_name=self.instance_name)
        await asyncio.sleep(delay_before_select)

        # Select '🆕Meta Ai 📧'
        clicked_meta = False
        if trading_menu_msg:
            clicked_meta = await self.click_any_button(trading_menu_msg, r"Meta\s*Ai", exclude_pattern=r"Gmail|Instagram|Old")
        if not clicked_meta:
            clicked_meta = await self.click_button_by_pattern(r"Meta\s*Ai", exclude_pattern=r"Gmail|Instagram|Old")
        if not clicked_meta:
            log("ONLY-META", "Button click fallback: Sending text '🆕 Meta Ai 📧'...", instance_name=self.instance_name)
            await self.safe_send_message(self.target_bot, "🆕 Meta Ai 📧")

        # 4. 'then delay then 🤖 Meta AI ... 📩 এখন আপনার Meta AI Gmail পাঠান।👇 ... ei rokom asbe tokhn meta er email ta bosai enter dibe'
        log("ONLY-META", "[Step 3] Waiting for '📩 এখন আপনার Meta AI Gmail পাঠান।👇' prompt...", instance_name=self.instance_name)
        email_prompt_found = False
        for wait_i in range(15):  # up to 18s
            await asyncio.sleep(1.2)
            try:
                recent_msgs = await self.client.get_messages(self.target_bot, limit=3)
            except Exception:
                recent_msgs = []
            for m in recent_msgs:
                mtxt = m.text or ""
                if "এখন আপনার meta ai gmail পাঠান" in mtxt.lower() or "gmail পাঠান" in mtxt or ("meta ai" in mtxt.lower() and ("পাঠান" in mtxt or "current rate" in mtxt.lower())):
                    email_prompt_found = True
                    break
            if email_prompt_found:
                break

        if not email_prompt_found:
            log("ONLY-META-WARN", "Bot did not show Gmail prompt in time. Aborting attempt to avoid desync...", instance_name=self.instance_name)
            return False

        # Reading/typing delay before sending email
        send_email_delay = random.uniform(1.4, 2.4)
        log("ONLY-META", f"✔ Gmail prompt confirmed! Waiting {send_email_delay:.1f}s then sending email...", instance_name=self.instance_name)
        await asyncio.sleep(send_email_delay)

        # Send email and press enter
        log("ONLY-META", f"📩 Sending Gmail '{meta_email}' to @{self.target_bot}...", instance_name=self.instance_name)
        await self.safe_send_message(self.target_bot, meta_email)
        self.current_task['meta_email_sent'] = True

        # 5. 'er por bot theke জিমেইল অ্যাড্রেস সেভ করা হয়েছে! ... 🔑 এবার আপনার অ্যাকাউন্টের পাসওয়ার্ড (Password) দিন:⤵️ ⚠️ Password must be saikat50968 ei rokom response asbe tokhon password bosabe becarefull'
        log("ONLY-META", "[Step 4] Waiting for bot response: 'জিমেইল অ্যাড্রেস সেভ করা হয়েছে! ... 🔑 এবার আপনার অ্যাকাউন্টের পাসওয়ার্ড দিন'...", instance_name=self.instance_name)
        pwd_prompt_found = False
        parsed_password = target_password or get_only_meta_password()

        for wait_i in range(20):  # up to 25s
            await asyncio.sleep(1.2)
            try:
                recent_msgs = await self.client.get_messages(self.target_bot, limit=3)
            except Exception:
                recent_msgs = []
            for m in recent_msgs:
                mtxt = m.text or ""
                if "জিমেইল অ্যাড্রেস সেভ" in mtxt or "এবার আপনার অ্যাকাউন্টের পাসওয়ার্ড" in mtxt or "password must be" in mtxt.lower() or ("পাসওয়ার্ড" in mtxt and "দিন" in mtxt):
                    pwd_prompt_found = True
                    log("ONLY-META", f"✔ Password prompt received: '{mtxt.strip()}'", instance_name=self.instance_name)
                    pwd_m = re.search(r"Password must be\s*([a-zA-Z0-9@_!#\$\%\^\&\*\-]+)", mtxt, re.IGNORECASE)
                    if pwd_m:
                        parsed_password = pwd_m.group(1).strip()
                        log("ONLY-META", f"🔑 Bot explicitly required password: '{parsed_password}'", instance_name=self.instance_name)
                    break
            if pwd_prompt_found:
                break

        if not pwd_prompt_found:
            log("ONLY-META-WARN", "Did not receive password prompt from bot. Aborting cycle to avoid desync...", instance_name=self.instance_name)
            return False

        # Careful typing delay before sending password
        send_pwd_delay = random.uniform(1.4, 2.4)
        log("ONLY-META", f"Waiting {send_pwd_delay:.1f}s before sending password...", instance_name=self.instance_name)
        await asyncio.sleep(send_pwd_delay)

        clean_pwd = re.sub(r"[`'\"*]", "", str(parsed_password)).strip()
        log("ONLY-META", f"🔑 Sending Password '{clean_pwd}' to @{self.target_bot}...", instance_name=self.instance_name)
        await self.safe_send_message(self.target_bot, clean_pwd)
        self.current_task['meta_password_sent'] = True

        # 6. 'then ✅ আপনার Meta AI রিকুয়েস্ট পাঠানো হয়েছে। 🆔 Request ID: MA-1791660989030-5442 দয়া করে অপেক্ষা করুন। emon asbe means successfully submited'
        log("ONLY-META", "[Step 5] Waiting for submission confirmation and Request ID...", instance_name=self.instance_name)
        confirmed = False
        req_id = ""

        for wait_i in range(20):  # up to 25s
            await asyncio.sleep(1.2)
            try:
                recent_msgs = await self.client.get_messages(self.target_bot, limit=3)
            except Exception:
                recent_msgs = []
            for m in recent_msgs:
                mtxt = m.text or ""
                if "রিকুয়েস্ট পাঠানো হয়েছে" in mtxt or "request id:" in mtxt.lower() or "দয়া করে অপেক্ষা করুন" in mtxt:
                    confirmed = True
                    req_id_m = re.search(r"Request ID:\s*([^\r\n]+)", mtxt, re.IGNORECASE)
                    req_id = req_id_m.group(1).strip() if req_id_m else f"MA-{int(time.time())}"
                    break
            if confirmed:
                break

        if confirmed:
            self.submitted_count += 1
            log("ONLY-META-SUCCESS", f"🎉 [ONLY META] Cycle #{cycle_num} Complete! Submitted to @{self.target_bot}! Request ID: {req_id} (Total: {self.submitted_count})", instance_name=self.instance_name)
            save_credentials_csv(meta_email, clean_pwd, two_factor_secret="", username=target_username, instance_name=self.instance_name, status="ACTIVE_META_AI", cookies=f"REQ_ID: {req_id}")
            return True
        else:
            log("ONLY-META-WARN", "Confirmation timed out, recording submission as pending...", instance_name=self.instance_name)
            self.submitted_count += 1
            save_credentials_csv(meta_email, clean_pwd, two_factor_secret="", username=target_username, instance_name=self.instance_name, status="ACTIVE_META_AI_PENDING", cookies="")
            return False

    async def run_automation_loop(self, playwright: Optional[Any] = None):
        cycle_num = 0
        while not self.is_stopped:
            try:
                if self.is_hourly_limited or self.hourly_limit_event.is_set():
                    await self.wait_for_hourly_reset()
                    continue

                secret_key = ""
                cycle_num += 1
                print("\n" + "#"*60)
                log("CYCLE-START", f"Starting AutoMetaInsta Cycle #{cycle_num} on device {self.device_serial}...", instance_name=self.instance_name)
                print("#"*60 + "\n")

                # ⚡ ONLY META MODE: Dedicated Pure Meta AI Creation + Submission to @RealEarningBangladesh_Bot
                is_only_meta_mode = (self.task_mode in ["only_meta", "only meta", "only mete"] or "realearning" in (self.target_bot or "").lower())
                if is_only_meta_mode:
                    log("ONLY-META", f"🚀 Starting 'Only Meta' Task #{cycle_num} targeting @{self.target_bot}...", instance_name=self.instance_name)
                    self.meta_email_requested_event.clear()
                    self.meta_password_requested_event.clear()
                    self.report_received_event.clear()
                    self.task_cancelled_event.clear()
                    self.current_task['meta_email_sent'] = False
                    self.current_task['meta_password_sent'] = False
                    self.current_task['report_received'] = False
                    self.current_task['status'] = 'idle'
                    self.current_task['cancelled'] = False

                    # 1. Generate identity & target password (dynamically loaded from config)
                    target_password = get_only_meta_password()
                    first_name, last_name = get_random_name()
                    clean_fn = re.sub(r'[^a-zA-Z0-9]', '', first_name).lower() or "user"
                    clean_ln = re.sub(r'[^a-zA-Z0-9]', '', last_name).lower() or "account"
                    target_username = f"{clean_fn}_{random.randint(1000, 99999)}"

                    # 2. Create Meta Account purely via API
                    meta_ok = False
                    meta_email = ""
                    meta_mail_token = ""
                    for attempt in range(1, 3):
                        log("ONLY-META", f"Creating Meta AI Account (attempt {attempt}/2): {first_name} {last_name} | Pwd: {target_password}...", instance_name=self.instance_name)
                        meta_ok, meta_email, meta_mail_token = await create_meta_account_task(
                            playwright,
                            first_name,
                            last_name,
                            target_password,
                            username=target_username,
                            instance_name=self.instance_name,
                            task_context=self.current_task
                        )
                        if meta_ok and meta_email:
                            break
                        await asyncio.sleep(2.0)

                    if not meta_ok or not meta_email:
                        log("ONLY-META-ERR", "Failed creating Meta AI account after retries. Resting...", instance_name=self.instance_name)
                        await asyncio.sleep(5.0)
                        continue

                    self.current_task['email'] = meta_email
                    self.current_task['password'] = target_password
                    self.current_task['login'] = target_username
                    self.current_task['status'] = 'running'
                    log("ONLY-META", f"✔ Meta AI account ready: {meta_email} | Submitting to @{self.target_bot}...", instance_name=self.instance_name)

                    # 3. Execute deterministic Only Meta Telegram submission
                    await self.process_only_meta_cycle(meta_email, target_password, target_username, cycle_num)

                    # Clean up task state
                    self.current_task['status'] = 'idle'
                    if self.current_task.get('ninja_client'):
                        try:
                            self.current_task['ninja_client'].disconnect()
                        except Exception:
                            pass
                        self.current_task['ninja_client'] = None

                    if not AUTO_REPEAT_TASKS:
                        break

                    cycle_delay = random.uniform(4.0, 8.0)
                    log("WAIT", f"☕ Cooldown: Waiting {cycle_delay:.1f}s before next cycle...", instance_name=self.instance_name)
                    await asyncio.sleep(cycle_delay)
                    continue

                # 🎲 Randomize device identity (IMEI, Android ID, MAC) at start of every cycle (Resolution/regulation untouched)
                loop = asyncio.get_running_loop()
                try:
                    await loop.run_in_executor(None, randomize_emulator_identity, self.device_serial, self.instance_name)
                    # Clear browser app data so Instagram sees clean device & cookies
                    await loop.run_in_executor(None, run_adb_command, f"shell pm clear {PACKAGE_NAME}", self.device_serial, self.instance_name, 5)
                except Exception as rand_err:
                    log("IMEI-WARN", f"Identity randomize error: {rand_err}", instance_name=self.instance_name)

                if self.current_task.get('status') == 'credentials_ready' and self.current_task.get('login'):
                    log("STEP-1", f"Using existing credentials from bot: {self.current_task['login']}", instance_name=self.instance_name)
                else:
                    self.task_received_event.clear()
                    self.two_fa_requested_event.clear()
                    self.otp_received_event.clear()
                    self.task_cancelled_event.clear()
                    self.report_received_event.clear()
                    self.current_task['report_received'] = False
                    self.current_task['account_registered_sent'] = False
                    self.current_task['status'] = 'idle'
                    self.current_task['cancelled'] = False

                    log("STEP-1", f"Starting new task cycle with /start on @{self.target_bot}...", instance_name=self.instance_name)
                    await self.safe_send_message(self.target_bot, "/start")
                    
                    log("WAIT", "Waiting for account credentials from Bot...", instance_name=self.instance_name)
                    try:
                        await asyncio.wait_for(self.task_received_event.wait(), timeout=75.0)
                        self.consecutive_timeouts = 0
                    except asyncio.TimeoutError:
                        if self.is_hourly_limited or self.hourly_limit_event.is_set() or self.current_task.get('status') == 'hourly_limited':
                            await self.wait_for_hourly_reset()
                            continue
                        self.consecutive_timeouts += 1
                        log("WARN", f"Timeout waiting for credentials from @{self.target_bot} (Timeout #{self.consecutive_timeouts})...", instance_name=self.instance_name)
                        self.current_task['status'] = 'idle'
                        if self.consecutive_timeouts >= 2:
                            if self.auto_shift:
                                log("WARN", f"Multiple timeouts on @{self.target_bot}. Auto-Shift is ON -> Switching target bot...", instance_name=self.instance_name)
                                self.consecutive_timeouts = 0
                                new_bot = await self.switch_target_bot()
                                if self.shift_task_mode and self.shift_task_mode in ["2fa", "cookies", "2fa_cookies", "random_2fa_cookies"]:
                                    self.task_mode = self.shift_task_mode
                            else:
                                log("WARN", f"Multiple timeouts on @{self.target_bot}. Auto-Shift is OFF -> Remaining on @{self.target_bot}...", instance_name=self.instance_name)
                                self.consecutive_timeouts = 0
                        await asyncio.sleep(random.uniform(5.0, 9.0))
                        continue

                    if self.is_hourly_limited or self.hourly_limit_event.is_set() or self.current_task.get('status') == 'hourly_limited':
                        await self.wait_for_hourly_reset()
                        continue

                if not self.current_task.get('login'):
                    if self.task_cancelled_event.is_set() or self.current_task.get('status') == 'cancelled':
                        log("CYCLE-ABORT", "Task cancelled by bot. Resting before fresh cycle...", instance_name=self.instance_name)
                        self.current_task['status'] = 'idle'
                        await asyncio.sleep(random.uniform(5.0, 9.0))
                        continue
                else:
                    self.task_cancelled_event.clear()

                self.current_task['status'] = 'running'
                first_name = self.current_task['first_name']
                last_name = self.current_task['last_name']
                target_login = self.current_task['login']
                target_password = self.current_task['password']

                # Step 2: Acquire Meta Account from meta.csv (Pre-verified via US Residential Proxy)
                meta_ok = False
                meta_email = ""
                meta_password = ""
                meta_mail_token = ""

                # 1. Pop from meta.csv
                m_email, m_pass, _ = pop_ready_meta_account(instance_name=self.instance_name)
                if m_email and m_pass:
                    meta_email = m_email
                    meta_password = m_pass
                    meta_mail_token = ""
                    meta_ok = True
                    log("META-CSV", f"🚀 Using pre-verified Meta account from meta.csv: {meta_email} (Instagram User: {target_login})", instance_name=self.instance_name)
                else:
                    log("META-CSV-WARN", "No available accounts in meta.csv! Falling back to creating Meta account on-the-fly...", instance_name=self.instance_name)
                    target_password = target_password or get_only_meta_password()
                    for attempt in range(1, 3):
                        log("STEP-2", f"Creating Meta Account on-the-fly (attempt {attempt}/2) for User: {target_login}...", instance_name=self.instance_name)
                        meta_ok, meta_email, meta_mail_token = await create_meta_account_task(
                            playwright,
                            first_name,
                            last_name,
                            target_password,
                            username=target_login,
                            instance_name=self.instance_name,
                            task_context=self.current_task
                        )
                        if meta_ok and meta_email:
                            meta_password = target_password
                            break
                        if self.current_task.get('status') == 'cancelled' or self.is_stopped:
                            break
                        await asyncio.sleep(2.0)

                if self.current_task.get('status') == 'cancelled':
                    log("CYCLE-ABORT", "Task cancelled during Meta preparation. Resetting...", instance_name=self.instance_name)
                    if meta_email:
                        mark_meta_account_status(meta_email, "CANCELLED", instance_name=self.instance_name)
                    self.current_task['status'] = 'idle'
                    btn_clicked = await self.click_button_by_pattern(r"Tasks|📋")
                    if not btn_clicked:
                        await self.safe_send_message(self.target_bot, "📋 Tasks")
                    await asyncio.sleep(random.uniform(3.0, 6.0))
                    continue

                if not meta_ok or not meta_email:
                    log("ERR", "Meta account not available. Resetting for next cycle...", instance_name=self.instance_name)
                    self.current_task['status'] = 'idle'
                    self.current_task['login'] = None
                    self.current_task['two_fa_key'] = None
                    self.task_received_event.clear()
                    await asyncio.sleep(random.uniform(3.0, 6.0))
                    continue

                actual_meta_password = meta_password or target_password

                # Step 3: Run Instagram Pipeline on Emulator (Cookies or 2FA)
                if self.task_mode == "cookies":
                    log("STEP-3", f"Running Instagram Cookies pipeline on emulator ({self.device_serial}) with Meta email: {meta_email} and Username: {target_login}...", instance_name=self.instance_name)
                    insta_ok, cookies_data = await loop.run_in_executor(
                        None,
                        run_instagram_pipeline,
                        self.device_serial,
                        meta_email,
                        actual_meta_password,
                        target_login,
                        meta_mail_token,
                        self.instance_name,
                        self.current_task,
                        "cookies"
                    )

                    if self.current_task.get('status') == 'cancelled':
                        log("CYCLE-ABORT", "Task explicitly cancelled during Instagram pipeline. Resetting with /start...", instance_name=self.instance_name)
                        if meta_email:
                            mark_meta_account_status(meta_email, "CANCELLED", instance_name=self.instance_name)
                        self.current_task['status'] = 'idle'
                        await self.safe_send_message(self.target_bot, "/start")
                        await asyncio.sleep(3.0)
                        continue

                    final_cookies = cookies_data or self.current_task.get('cookies')

                    if insta_ok and final_cookies and len(final_cookies) > 20:
                        if not self.current_task.get('cookies_sent'):
                            log("TG-BOT", f"🍪 Submitting captured Cookies to @{self.target_bot}...", instance_name=self.instance_name)
                            await self.safe_send_message(self.target_bot, final_cookies)
                            self.current_task['cookies_sent'] = True
                            await asyncio.sleep(2.0)

                        log("STEP-4", "Instagram Cookies submitted! Waiting for Bot confirmation...", instance_name=self.instance_name)
                        if not self.report_received_event.is_set() and not self.current_task.get('report_received'):
                            try:
                                await asyncio.wait_for(self.report_received_event.wait(), timeout=18.0)
                            except asyncio.TimeoutError:
                                pass

                        if self.report_received_event.is_set() or self.current_task.get('report_received'):
                            self.consecutive_fails = 0
                            log("TG-BOT", f"✔ Report confirmed by bot! (Submitted: {self.submitted_count} | Approved: {self.approved_count})", instance_name=self.instance_name)
                            save_credentials_csv(meta_email, actual_meta_password, two_factor_secret="", username=target_login, instance_name=self.instance_name, status="ACTIVE_COOKIES", cookies=final_cookies)
                            mark_meta_account_status(meta_email, "DONE", instance_name=self.instance_name)

                            print("\n" + "="*50)
                            log("SUCCESS", f"🎉 [{self.instance_name}] CYCLE #{cycle_num} COMPLETE (COOKIES MODE)! (Submitted: {self.submitted_count} | Approved: {self.approved_count})", instance_name=self.instance_name)
                            log("SUCCESS", f"Meta Email : {meta_email}", instance_name=self.instance_name)
                            log("SUCCESS", f"Username   : {target_login}", instance_name=self.instance_name)
                            log("SUCCESS", f"Password   : {target_password}", instance_name=self.instance_name)
                            log("SUCCESS", f"Cookies    : {final_cookies[:60]}...", instance_name=self.instance_name)
                            print("="*50 + "\n")
                        else:
                            if self.task_cancelled_event.is_set() or self.current_task.get('status') == 'rejected':
                                log("TG-WARN", f"❌ Cookies submission for {target_login} was rejected/cancelled by bot.", instance_name=self.instance_name)
                                save_credentials_csv(meta_email, target_password, two_factor_secret="", username=target_login, instance_name=self.instance_name, status="REJECTED_COOKIES", cookies=final_cookies)
                            else:
                                log("TG-WARN", f"⚠️ Bot confirmation timed out for {target_login}. Saved as ACTIVE_COOKIES_PENDING.", instance_name=self.instance_name)
                                save_credentials_csv(meta_email, target_password, two_factor_secret="", username=target_login, instance_name=self.instance_name, status="ACTIVE_COOKIES_PENDING", cookies=final_cookies)

                        # Clean up task state completely
                        self.current_task['status'] = 'idle'
                        self.current_task['login'] = None
                        self.current_task['cookies'] = None
                        self.current_task['cookies_sent'] = False
                        self.current_task['cookies_requested'] = False
                        self.current_task['account_registered_sent'] = False
                        self.current_task['report_received'] = False
                        self.report_received_event.clear()
                        self.task_received_event.clear()
                        self.task_cancelled_event.clear()
                        self.cookies_requested_event.clear()
                        if self.current_task.get('ninja_client'):
                            try:
                                self.current_task['ninja_client'].disconnect()
                            except Exception:
                                pass
                            self.current_task['ninja_client'] = None

                        # Refresh balance
                        try:
                            await asyncio.sleep(1.0)
                            await self.fetch_bot_balance()
                        except Exception as b_err:
                            log("TG-WARN", f"Balance update error: {b_err}", instance_name=self.instance_name)

                        if not AUTO_REPEAT_TASKS:
                            log("MAIN", "Auto-repeat disabled. Finishing execution.", instance_name=self.instance_name)
                            break

                        cycle_delay = random.uniform(6.0, 12.0)
                        log("WAIT", f"☕ Human cooldown: Waiting {cycle_delay:.1f}s before starting next cycle...", instance_name=self.instance_name)
                        await asyncio.sleep(cycle_delay)
                        continue
                    else:
                        if self.current_task.get('follow_failed'):
                            log("FOLLOW-RETRY", f"🔁 Follow failed for {target_login}! Preserving bot credentials and restarting cycle to create new Meta account first...", instance_name=self.instance_name)
                            self.current_task['status'] = 'credentials_ready'
                            self.current_task['follow_failed'] = False
                            self.current_task['cookies'] = None
                            self.current_task['cookies_sent'] = False
                            self.current_task['cookies_requested'] = False
                            self.current_task['two_fa_key'] = None
                            self.current_task['two_fa_sent'] = False
                            self.current_task['otp_code'] = None
                            self.current_task['account_registered_sent'] = False
                            self.current_task['report_received'] = False
                            self.cookies_requested_event.clear()
                            self.report_received_event.clear()
                            self.task_received_event.clear()
                            self.two_fa_requested_event.clear()
                            self.otp_received_event.clear()
                            self.task_cancelled_event.clear()
                            if self.current_task.get('ninja_client'):
                                try:
                                    self.current_task['ninja_client'].disconnect()
                                except Exception:
                                    pass
                                self.current_task['ninja_client'] = None

                            try:
                                run_adb_command(f"shell am force-stop {PACKAGE_NAME}", self.device_serial, self.instance_name)
                                run_adb_command(f"shell pm clear {PACKAGE_NAME}", self.device_serial, self.instance_name)
                            except Exception:
                                pass

                            await asyncio.sleep(2.0)
                            continue

                        self.consecutive_fails += 1
                        log("ERR", f"Instagram Cookies capture failed for {target_login} (Fail #{self.consecutive_fails}/{self.max_consecutive_fails} on {self.device_serial}). Resetting with /start...", instance_name=self.instance_name)
                        self.current_task['status'] = 'idle'
                        self.current_task['login'] = None
                        self.current_task['cookies'] = None
                        self.current_task['cookies_sent'] = False
                        self.current_task['cookies_requested'] = False
                        self.current_task['account_registered_sent'] = False
                        self.current_task['report_received'] = False
                        self.report_received_event.clear()
                        self.cookies_requested_event.clear()
                        if self.current_task.get('ninja_client'):
                            try:
                                self.current_task['ninja_client'].disconnect()
                            except Exception:
                                pass
                            self.current_task['ninja_client'] = None
                        self.task_received_event.clear()
                        self.task_cancelled_event.set()
                        await asyncio.sleep(random.uniform(5.0, 9.0))
                        continue
                else:
                    # Step 3: Run Instagram 2FA or 2FA + Cookies Creation on Emulator
                    is_both_mode = (self.task_mode in ["2fa_cookies", "random_2fa_cookies"])
                    mode_label = "Random 2FA + Cookies" if self.task_mode == "random_2fa_cookies" else ("2FA + Cookies" if is_both_mode else "2FA")
                    pipeline_mode = self.task_mode
                    log("STEP-3", f"Running Instagram {mode_label} on emulator ({self.device_serial}) with Meta email: {meta_email} and Username: {target_login}...", instance_name=self.instance_name)
                    self.current_task['two_fa_sent'] = False
                    stop_key_exchange = asyncio.Event()

                    async def handle_2fa_key_exchange():
                        while not stop_key_exchange.is_set():
                            if self.task_cancelled_event.is_set() or self.current_task.get('status') == 'cancelled':
                                return
                            key = self.current_task.get('two_fa_key')
                            if key and len(key) >= 16 and not self.current_task.get('two_fa_sent'):
                                log("TG-BOT", f"🔑 Sending extracted 2FA Secret Key '{key}' to @{self.target_bot}...", instance_name=self.instance_name)
                                await asyncio.sleep(DELAY_BETWEEN_STEPS)
                                await self.safe_send_message(self.target_bot, key)
                                self.current_task['two_fa_sent'] = True
                                break
                            await asyncio.sleep(0.3)

                    key_exchange_task = asyncio.create_task(handle_2fa_key_exchange())

                    insta_ok, secret_key = await loop.run_in_executor(
                        None,
                        run_instagram_pipeline,
                        self.device_serial,
                        meta_email,
                        actual_meta_password,
                        target_login,
                        meta_mail_token,
                        self.instance_name,
                        self.current_task,
                        pipeline_mode
                    )
                    
                    stop_key_exchange.set()
                    if not key_exchange_task.done():
                        key_exchange_task.cancel()
                    try:
                        await key_exchange_task
                    except (asyncio.CancelledError, Exception):
                        pass

                if self.current_task.get('status') == 'cancelled':
                    log("CYCLE-ABORT", "Task explicitly cancelled during Instagram pipeline. Resetting with /start...", instance_name=self.instance_name)
                    self.current_task['status'] = 'idle'
                    await self.safe_send_message(self.target_bot, "/start")
                    await asyncio.sleep(3.0)
                    continue

                final_2fa_key = secret_key or self.current_task.get('two_fa_key')
                is_cannot_make_change = (secret_key == "CANNOT_MAKE_CHANGE" or self.current_task.get('cannot_make_change'))

                if is_cannot_make_change:
                    log("TG-INFO", f"Detected 'Can\\'t make this change at the moment' on {target_login}. Transitioning to last step balance checking...", instance_name=self.instance_name)
                    # If cookies were extracted, submit them to bot and confirm
                    if self.current_task.get('cookies') and not self.current_task.get('cookies_sent'):
                        log("TG-BOT", f"🍪 Submitting captured Cookies to @{self.target_bot}...", instance_name=self.instance_name)
                        await self.safe_send_message(self.target_bot, self.current_task['cookies'])
                        self.current_task['cookies_sent'] = True
                        await asyncio.sleep(2.0)
                        clicked = await self.click_button_by_pattern(r"Account registered|Registered|Confirm|✅")
                        if not clicked and not self.task_cancelled_event.is_set():
                            await self.safe_send_message(self.target_bot, "✅ Account registered")
                        await asyncio.sleep(2.0)
                    else:
                        # Pure 2FA task blocked by device restriction -> cancel task in bot cleanly
                        clicked_cancel = await self.click_button_by_pattern(r"Cancel|❌|Stop")
                        if not clicked_cancel:
                            await self.safe_send_message(self.target_bot, "/start")
                        await asyncio.sleep(2.0)

                    self.consecutive_fails = 0
                    self.current_task['status'] = 'idle'
                    self.current_task['login'] = None
                    self.current_task['two_fa_key'] = None
                    self.current_task['two_fa_sent'] = False
                    self.current_task['cookies'] = None
                    self.current_task['cookies_sent'] = False
                    self.current_task['cookies_requested'] = False
                    self.cookies_requested_event.clear()
                    self.current_task['otp_code'] = None
                    self.current_task['cannot_make_change'] = False
                    if self.current_task.get('ninja_client'):
                        try:
                            self.current_task['ninja_client'].disconnect()
                        except Exception:
                            pass
                        self.current_task['ninja_client'] = None

                    # 💰 LAST STEP: Fetch updated balance from Telegram bot
                    log("TG-BALANCE", f"💰 [{self.instance_name}] Last step: Checking balance for @{self.target_bot}...", instance_name=self.instance_name)
                    try:
                        await asyncio.sleep(1.0)
                        await self.fetch_bot_balance()
                    except Exception as b_err:
                        log("TG-WARN", f"Balance update error: {b_err}", instance_name=self.instance_name)
                    continue

                elif insta_ok and final_2fa_key and len(final_2fa_key) >= 16:
                    if not self.current_task.get('two_fa_sent'):
                        log("TG-BOT", f"🔑 Submitting captured 2FA Secret Key '{final_2fa_key}' to @{self.target_bot}...", instance_name=self.instance_name)
                        await self.safe_send_message(self.target_bot, final_2fa_key)
                        self.current_task['two_fa_sent'] = True
                        await asyncio.sleep(2.0)

                    # In 2FA + Cookies mode: submit Cookies to bot after 2FA key!
                    if is_both_mode and self.current_task.get('cookies') and not self.current_task.get('cookies_sent'):
                        if not self.cookies_requested_event.is_set():
                            try:
                                await asyncio.wait_for(self.cookies_requested_event.wait(), timeout=2.0)
                            except asyncio.TimeoutError:
                                pass
                        log("TG-BOT", f"🍪 Submitting captured Cookies to @{self.target_bot}...", instance_name=self.instance_name)
                        await self.safe_send_message(self.target_bot, self.current_task['cookies'])
                        self.current_task['cookies_sent'] = True
                        await asyncio.sleep(2.0)

                    log("STEP-4", f"Instagram {mode_label} active & credentials saved! Confirming task completion in Bot...", instance_name=self.instance_name)
                    if self.report_received_event.is_set() or self.current_task.get('report_received'):
                        log("TG-BOT", "✔ Report was already received and confirmed by Bot! No extra confirmation clicks needed.", instance_name=self.instance_name)
                    else:
                        await asyncio.sleep(DELAY_BETWEEN_STEPS)
                        attempt = 0
                        max_confirm_attempts = 2
                        while not self.report_received_event.is_set() and not self.current_task.get('report_received') and attempt < max_confirm_attempts:
                            if self.task_cancelled_event.is_set() or self.current_task.get('status') not in ('running', 'submitted'):
                                break
                            attempt += 1
                            log("TG-BOT", f"Clicking '✅ Account registered' in Bot (Attempt {attempt}/{max_confirm_attempts})...", instance_name=self.instance_name)
                            clicked = await self.click_button_by_pattern(r"Account registered|Registered|Confirm|✅")
                            if not clicked and not self.task_cancelled_event.is_set() and not self.current_task.get('report_received'):
                                await self.safe_send_message(self.target_bot, "✅ Account registered")

                            try:
                                await asyncio.wait_for(self.report_received_event.wait(), timeout=5.0)
                                break
                            except asyncio.TimeoutError:
                                if self.current_task.get('report_received') or self.task_cancelled_event.is_set():
                                    break
                                await asyncio.sleep(2.0)

                    if self.report_received_event.is_set() or self.current_task.get('report_received'):
                        self.consecutive_fails = 0
                        log("TG-BOT", f"✔ Report confirmed by bot! (Submitted: {self.submitted_count} | Approved: {self.approved_count})", instance_name=self.instance_name)
                        save_credentials_csv(meta_email, actual_meta_password, two_factor_secret=final_2fa_key, username=target_login, instance_name=self.instance_name, status="ACTIVE_2FA", cookies=self.current_task.get('cookies') or "")
                        mark_meta_account_status(meta_email, "DONE", instance_name=self.instance_name)

                        print("\n" + "="*50)
                        log("SUCCESS", f"🎉 [{self.instance_name}] CYCLE #{cycle_num} COMPLETE ({mode_label.upper()} MODE)! (Submitted: {self.submitted_count} | Approved: {self.approved_count})", instance_name=self.instance_name)
                        log("SUCCESS", f"Meta Email : {meta_email}", instance_name=self.instance_name)
                        log("SUCCESS", f"Username   : {target_login}", instance_name=self.instance_name)
                        log("SUCCESS", f"Password   : {target_password}", instance_name=self.instance_name)
                        log("SUCCESS", f"2FA Secret : {final_2fa_key}", instance_name=self.instance_name)
                        if is_both_mode and self.current_task.get('cookies'):
                            log("SUCCESS", f"Cookies    : {self.current_task['cookies'][:60]}...", instance_name=self.instance_name)
                        print("="*50 + "\n")
                    else:
                        log("TG-WARN", f"⚠️ Bot confirmation not received for {target_login} ({mode_label}).", instance_name=self.instance_name)

                    # Clean up task state completely
                    self.current_task['status'] = 'idle'
                    self.current_task['login'] = None
                    self.current_task['two_fa_key'] = None
                    self.current_task['two_fa_sent'] = False
                    self.current_task['cookies'] = None
                    self.current_task['cookies_sent'] = False
                    self.current_task['cookies_requested'] = False
                    self.current_task['account_registered_sent'] = False
                    self.current_task['report_received'] = False
                    self.current_task['otp_code'] = None
                    self.report_received_event.clear()
                    self.task_received_event.clear()
                    self.task_cancelled_event.clear()
                    self.cookies_requested_event.clear()
                    if self.current_task.get('ninja_client'):
                        try:
                            self.current_task['ninja_client'].disconnect()
                        except Exception:
                            pass
                        self.current_task['ninja_client'] = None

                    # 💰 Fetch updated balance from Telegram bot at the end of the cycle
                    try:
                        await asyncio.sleep(1.0)
                        await self.fetch_bot_balance()
                    except Exception as b_err:
                        log("TG-WARN", f"Balance update error: {b_err}", instance_name=self.instance_name)

                else:
                    if self.current_task.get('follow_failed'):
                        log("FOLLOW-RETRY", f"🔁 Follow failed for {target_login}! Preserving bot credentials and restarting cycle to create new Meta account first...", instance_name=self.instance_name)
                        self.current_task['status'] = 'credentials_ready'
                        self.current_task['follow_failed'] = False
                        self.current_task['cookies'] = None
                        self.current_task['cookies_sent'] = False
                        self.current_task['cookies_requested'] = False
                        self.current_task['two_fa_key'] = None
                        self.current_task['two_fa_sent'] = False
                        self.current_task['otp_code'] = None
                        self.current_task['account_registered_sent'] = False
                        self.current_task['report_received'] = False
                        self.cookies_requested_event.clear()
                        self.report_received_event.clear()
                        self.task_received_event.clear()
                        self.two_fa_requested_event.clear()
                        self.otp_received_event.clear()
                        self.task_cancelled_event.clear()
                        if self.current_task.get('ninja_client'):
                            try:
                                self.current_task['ninja_client'].disconnect()
                            except Exception:
                                pass
                            self.current_task['ninja_client'] = None

                        try:
                            run_adb_command(f"shell am force-stop {PACKAGE_NAME}", self.device_serial, self.instance_name)
                            run_adb_command(f"shell pm clear {PACKAGE_NAME}", self.device_serial, self.instance_name)
                        except Exception:
                            pass

                        await asyncio.sleep(2.0)
                        continue

                    self.consecutive_fails += 1
                    log("ERR", f"Instagram 2FA process or key capture failed for {target_login} (Fail #{self.consecutive_fails}/{self.max_consecutive_fails} on {self.device_serial}). Resetting with /start...", instance_name=self.instance_name)
                    self.current_task['status'] = 'idle'
                    self.current_task['login'] = None
                    self.current_task['two_fa_key'] = None
                    self.current_task['two_fa_sent'] = False
                    self.current_task['cookies'] = None
                    self.current_task['cookies_sent'] = False
                    self.current_task['cookies_requested'] = False
                    self.current_task['account_registered_sent'] = False
                    self.current_task['report_received'] = False
                    self.current_task['otp_code'] = None
                    self.report_received_event.clear()
                    self.cookies_requested_event.clear()
                    if self.current_task.get('ninja_client'):
                        try:
                            self.current_task['ninja_client'].disconnect()
                        except Exception:
                            pass
                        self.current_task['ninja_client'] = None
                    self.task_received_event.clear()
                    self.task_cancelled_event.set()

                    if self.consecutive_fails >= self.max_consecutive_fails:
                        log("DEVICE-COOLDOWN", f"⚠️ Device {self.device_serial} ({self.instance_name}) reached {self.consecutive_fails} consecutive failures!", instance_name=self.instance_name)
                        log("DEVICE-COOLDOWN", f"Cleaning emulator state and cooling down for {self.fail_cooldown_seconds}s before retrying device {self.device_serial}...", instance_name=self.instance_name)
                        try:
                            await loop.run_in_executor(None, recover_device_after_failures, self.device_serial, self.instance_name)
                        except Exception as rec_err:
                            log("DEVICE-COOLDOWN", f"Recovery error: {rec_err}", instance_name=self.instance_name)

                        remaining = self.fail_cooldown_seconds
                        while remaining > 0 and not self.is_stopped:
                            step = min(remaining, 15)
                            await asyncio.sleep(step)
                            remaining -= step
                            if remaining > 0 and not self.is_stopped:
                                log("DEVICE-COOLDOWN", f"Cooldown for {self.device_serial} ({self.instance_name}): {remaining}s remaining...", instance_name=self.instance_name)

                        self.consecutive_fails = 0
                        log("DEVICE-RESUME", f"🔄 Cooldown finished! Resuming tasks on device {self.device_serial} ({self.instance_name})...", instance_name=self.instance_name)

                if not AUTO_REPEAT_TASKS:
                    log("MAIN", "Auto-repeat disabled. Finishing execution.", instance_name=self.instance_name)
                    break

                cycle_delay = random.uniform(6.0, 12.0)
                log("WAIT", f"☕ Human cooldown: Waiting {cycle_delay:.1f}s before starting next cycle...", instance_name=self.instance_name)
                await asyncio.sleep(cycle_delay)

            except Exception as cycle_err:
                self.consecutive_fails += 1
                log("CYCLE-RECOVER", f"Unexpected cycle error on {self.instance_name} ({self.device_serial}): {cycle_err}. (Fail #{self.consecutive_fails}/{self.max_consecutive_fails})", instance_name=self.instance_name)
                try:
                    if 'meta_email' in locals() and meta_email:
                        mark_meta_account_status(meta_email, "SUCCESS", instance_name=self.instance_name)
                except Exception:
                    pass
                if self.consecutive_fails >= self.max_consecutive_fails:
                    log("DEVICE-COOLDOWN", f"⚠️ Multiple consecutive cycle errors on {self.device_serial}. Performing device recovery & cooling down for {self.fail_cooldown_seconds}s...", instance_name=self.instance_name)
                    try:
                        loop = asyncio.get_running_loop()
                        await loop.run_in_executor(None, recover_device_after_failures, self.device_serial, self.instance_name)
                    except Exception:
                        pass
                    await asyncio.sleep(self.fail_cooldown_seconds)
                    self.consecutive_fails = 0
                    log("DEVICE-RESUME", f"🔄 Resuming tasks on device {self.device_serial} after cooldown...", instance_name=self.instance_name)
                else:
                    await asyncio.sleep(random.uniform(4.0, 8.0))

    async def run(self, playwright: Optional[Any] = None):
        while not self.is_stopped:
            try:
                if self.is_stopped:
                    break
                await self.run_automation_loop(playwright)
            except asyncio.CancelledError:
                break
            except Exception as e:
                if self.is_stopped:
                    break
                log("WORKER-RECOVER", f"Worker {self.instance_name} recovered from exception: {e}. Restarting in 5s...", instance_name=self.instance_name)
                await asyncio.sleep(5.0)

# ==============================================================================
# 🏁 MAIN ENTRYPOINT (PARALLEL EXECUTION ACROSS DEVICES & TELEGRAM ACCOUNTS)
# ==============================================================================
async def main_async():
    print("=" * 65)
    print("      🚀 AUTOMETAINSTABOT - FULLY AUTOMATED MULTI-BOT SYSTEM       ")
    print("=" * 65)

    devices = get_unique_devices()
    if not devices:
        log("ERR", "No active ADB emulator device found! Please start your Android emulator (LDPlayer, etc.).")
        return

    log("INIT", f"Detected {len(devices)} active ADB device(s): {', '.join(devices)}")
    log("INIT", f"Configured {len(TELEGRAM_ACCOUNTS)} Telegram account(s)")

    jobs = []
    for acc in TELEGRAM_ACCOUNTS:
        acc_bots = acc.get("target_bots") or acc.get("target_bot") or TARGET_BOTS
        norm_bots = normalize_target_bots(acc_bots)
        jobs.append({"account": acc, "target_bot": norm_bots[0]})

    num_to_run = min(len(devices), len(jobs))
    log("INIT", f"Parallel Workers Scheduled: {num_to_run} (Devices: {len(devices)}, Accounts: {len(jobs)})")

    # Connect unique Telegram clients sequentially first
    unique_clients = {}
    for i in range(num_to_run):
        job = jobs[i]
        acc = job["account"]
        clean_phone = re.sub(r'[^0-9]', '', str(acc['phone']))
        sess_name = acc.get('session_name') or f"Taskl1_session_{clean_phone}"
        sess_path = os.path.join(BASE_DIR, sess_name) if not os.path.isabs(sess_name) else sess_name
        if not os.path.exists(sess_path + ".session") and not os.path.exists(sess_path):
            for alt in [f"Taskl1_session_{clean_phone}", f"taskly_session_{clean_phone}"]:
                alt_p = os.path.join(BASE_DIR, alt)
                if os.path.exists(alt_p + ".session"):
                    sess_path = alt_p
                    sess_name = alt
                    break
        if sess_name not in unique_clients:
            tg_client = TelegramClient(sess_path, acc['api_id'], acc['api_hash'])
            unique_clients[sess_name] = (tg_client, acc['phone'])

    for sess_name, (tg_client, phone) in unique_clients.items():
        log("INIT", f"Connecting Telegram Userbot for {phone} (Session: {sess_name})...")
        await tg_client.start(phone=phone)
        CLIENT_CACHE[sess_name] = tg_client
        log("INIT", f"Telegram Userbot for {phone} logged in successfully!")

    workers = []
    for i in range(num_to_run):
        job = jobs[i]
        acc = job["account"]
        target_bot = job["target_bot"]
        dev = devices[i]
        inst_name = f"Inst-{i+1}"
        
        clean_phone = re.sub(r'[^0-9]', '', str(acc['phone']))
        sess_name = acc.get('session_name') or f"Taskl1_session_{clean_phone}"
        if sess_name not in CLIENT_CACHE:
            for alt in [f"Taskl1_session_{clean_phone}", f"taskly_session_{clean_phone}"]:
                if alt in CLIENT_CACHE:
                    sess_name = alt
                    break
        tg_client = CLIENT_CACHE.get(sess_name)
        
        worker = TasklyWorker(acc, dev, inst_name, target_bot=target_bot, client=tg_client)
        workers.append(worker)
        log("INIT", f"🚀 Worker [{inst_name}] assigned to bot @{target_bot} on device {dev}")

    async def _staggered_run(w, index):
        if index > 0:
            delay = index * 3.0
            log("INIT", f"Worker [{w.instance_name}] staggering start by {delay:.1f}s to prevent initial ADB / network contention...")
            await asyncio.sleep(delay)
        await w.run()

    log("INIT", f"🔥 Launching {len(workers)} worker(s) in PARALLEL with staggered initialization...")
    
    worker_tasks = [asyncio.create_task(_staggered_run(w, i)) for i, w in enumerate(workers)]
    await asyncio.gather(*worker_tasks, return_exceptions=True)

def main():
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        log("MAIN", "Process stopped by user.")

if __name__ == "__main__":
    main()
