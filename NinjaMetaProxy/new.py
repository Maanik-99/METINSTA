"""
==============================================================================
⚡ NINJA & META PROXY ACCOUNT GENERATOR (100% STANDALONE & MULTI-THREADED)
==============================================================================
Features:
  1. 100% Self-Contained: Zero external dependencies on METINSTA project.
     Move this folder anywhere and run independently!
  2. Multi-Threaded: Blazing fast concurrent account creation.
  3. Ultra-Low Data Consumption: ~35-50 KB per account (Zero browser, zero emulator).
  4. Automatic IP Rotation: Supports Residential gateways & proxy pools with sticky session.
  5. Cryptographic Random Passwords for every account.
  6. Instant Save: Verified accounts are thread-safely saved to meta.csv.
  7. Strict Checkpoint & Captcha Filter: Rejects blocked or flagged accounts.
==============================================================================
"""

import os
import sys

# Force UTF-8 encoding on Windows to prevent UnicodeEncodeError with emojis
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import time
import uuid
import re
import csv
import string
import secrets
import random
import base64
import hashlib
import json
import threading
import argparse
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

# 3rd-Party Dependencies
import socketio
from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import nacl.public

# Current Folder Paths
DIR_PATH = os.path.dirname(os.path.abspath(__file__))
PROXIES_FILE = os.path.join(DIR_PATH, "proxies.txt")
OUTPUT_CSV = os.path.join(DIR_PATH, "meta.csv")

# Known DNS Fix: Auto-resolve proxy.h143.xyz to active IP
H143_ACTIVE_IP = "31.59.160.7"

# First & Last Names Pool
FIRST_NAMES = [
    "Alex", "James", "John", "David", "Michael", "Emily", "Sarah", "Daniel",
    "Chris", "Ryan", "Matt", "Jessica", "Andrew", "Kevin", "Brian", "Jason",
    "Luke", "Sam", "Nathan", "Brandon", "Oliver", "Lucas", "Ethan", "Henry"
]
LAST_NAMES = [
    "Smith", "Miller", "Brown", "Jones", "Davis", "Wilson", "Taylor", "White",
    "Clark", "Hall", "Allen", "Young", "King", "Wright", "Scott", "Green",
    "Baker", "Adams", "Nelson", "Hill", "Carter", "Mitchell", "Roberts", "Turner"
]


# ==============================================================================
# 🔐 CRYPTO & UTILITIES
# ==============================================================================

def get_random_name() -> tuple[str, str]:
    return random.choice(FIRST_NAMES), random.choice(LAST_NAMES)


def generate_random_password(length: int = 12) -> str:
    """Generates strong Meta-compliant random password."""
    lower = string.ascii_lowercase
    upper = string.ascii_uppercase
    digits = string.digits
    special = "@#$!_"
    pwd = [
        secrets.choice(lower),
        secrets.choice(upper),
        secrets.choice(digits),
        secrets.choice(special),
    ]
    pool = lower + upper + digits + special
    pwd += [secrets.choice(pool) for _ in range(max(8, length) - len(pwd))]
    secrets.SystemRandom().shuffle(pwd)
    return "".join(pwd)


def base36_encode(number: int) -> str:
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
    base36 = ""
    while number:
        number, i = divmod(number, 36)
        base36 = alphabet[i] + base36
    return base36 or "0"


def compute_jazoest(token: str) -> str:
    if not token:
        return "22206"
    return "2" + str(sum(ord(c) for c in token))


def format_pwd_browser(encrypted_b64: str, timestamp: int | None = None, version: int = 5) -> str:
    ts = timestamp or int(time.time())
    return f"#PWD_BROWSER:{version}:{ts}:{encrypted_b64}"


def encrypt_meta_password(password: str, public_key_hex: str, key_id: int = 199, timestamp: int | None = None) -> str:
    """Encrypts password using Meta EnvelopeEncryption (AES-256-GCM + X25519 SealedBox)."""
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
    envelope.append(1)
    envelope.append(int(key_id))
    envelope.append(sealed_len & 0xFF)
    envelope.append((sealed_len >> 8) & 0xFF)
    envelope.extend(sealed_key)
    envelope.extend(tag)
    envelope.extend(ciphertext)

    b64_payload = base64.b64encode(envelope).decode("utf-8")
    return format_pwd_browser(b64_payload, timestamp=ts)


def format_proxy_url(proxy_str: str | None = None, session_id: str | None = None) -> str | None:
    """Formats proxy string into standard http://user:pass@host:port URL with sticky session support."""
    if not proxy_str:
        return None
    raw = proxy_str.strip()
    if not raw:
        return None

    # Resolve domain to active IP if needed
    if "proxy.h143.xyz" in raw:
        raw = raw.replace("proxy.h143.xyz", H143_ACTIVE_IP)

    scheme = "http"
    if "://" in raw:
        scheme, raw = raw.split("://", 1)

    if "@" in raw:
        userpass, hostport = raw.split("@", 1)
        user_parts = userpass.split(":", 1)
        user = user_parts[0]
        passwd = user_parts[1] if len(user_parts) > 1 else ""
        host_parts = hostport.split(":", 1)
        host = host_parts[0]
        port = host_parts[1] if len(host_parts) > 1 else "8080"
    else:
        parts = raw.split(":")
        if len(parts) == 4:
            host, port, user, passwd = parts
        elif len(parts) == 2:
            return f"{scheme}://{parts[0]}:{parts[1]}"
        else:
            return f"{scheme}://{raw}"

    if session_id:
        if "-session-" in user:
            user = re.sub(r"-session-[a-zA-Z0-9_-]+", f"-session-{session_id}", user)
        else:
            user = f"{user}-session-{session_id}"

    return f"{scheme}://{user}:{passwd}@{host}:{port}"


# ==============================================================================
# 🌐 PROXY POOL MANAGER (THREAD-SAFE)
# ==============================================================================

class ProxyManager:
    """Thread-safe proxy loader and round-robin rotator."""

    def __init__(self, file_path: str = PROXIES_FILE):
        self.file_path = file_path
        self.proxies: list[str] = []
        self.index = 0
        self.lock = threading.Lock()
        self.load_proxies()

    def load_proxies(self):
        if not os.path.exists(self.file_path):
            print(f"⚠️ Warning: {self.file_path} not found.")
            return
        with open(self.file_path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        self.proxies = lines
        self.index = 0
        print(f"✅ Loaded {len(self.proxies)} proxies from {os.path.basename(self.file_path)}")

    def get_next_proxy(self) -> str | None:
        if not self.proxies:
            return None
        with self.lock:
            proxy = self.proxies[self.index % len(self.proxies)]
            self.index += 1
            return proxy

    def total(self) -> int:
        return len(self.proxies)


# ==============================================================================
# 📧 TEMPMAIL NINJA API CLIENT (PURE SOCKET.IO & ULTRA-LOW DATA)
# ==============================================================================

class TempMailNinjaAPI:
    """Socket.IO client for TempMail Ninja API with immediate disconnect after OTP."""
    BASE_URL = "https://tm-app.solucioneswc.com:2083"

    def __init__(self, proxy: str | None = None, session_id: str | None = None):
        self.session_id = session_id or uuid.uuid4().hex[:8]
        self.proxy_url = format_proxy_url(proxy, session_id=self.session_id) if proxy else None
        self.http_session = None

        if self.proxy_url:
            import requests as req
            self.http_session = req.Session()
            self.http_session.proxies = {'http': self.proxy_url, 'https': self.proxy_url}

        self.sio = socketio.Client(
            http_session=self.http_session,
            logger=False,
            engineio_logger=False,
            reconnection=False
        )
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Origin': 'https://tempmail.ninja',
            'Referer': 'https://tempmail.ninja/'
        }

        self.email_address = None
        self.visitor_token = None
        self.latest_otp = None
        self.processed_message_ids = set()
        self._otp_event = threading.Event()

        self.sio.on("new_message_notify", self._on_new_message)

    def _on_new_message(self, data):
        self.check_and_read_inbox()

    def _emit_ack(self, event, *args, timeout=12):
        if not self.sio.connected and event != "get_guest_user_data":
            return None
        res_box = []
        evt = threading.Event()

        def cb(response):
            res_box.append(response)
            evt.set()

        try:
            self.sio.emit(event, *args, callback=cb)
            evt.wait(timeout=timeout)
        except Exception:
            return None
        return res_box[0] if res_box else None

    def connect(self):
        last_err = None
        for attempt in range(1, 3):
            try:
                self.sio.connect(
                    f"{self.BASE_URL}?locale=en",
                    headers=self.headers,
                    transports=['websocket', 'polling'],
                    wait_timeout=25
                )
                guest = self._emit_ack("get_guest_user_data", {"token": self.visitor_token})
                if guest:
                    ip = guest.get("ip", "Unknown")
                    cc = guest.get("country", "Unknown")
                    print(f"[+] Ninja Connected (IP: {ip}, Country: {cc})")
                return
            except Exception as e:
                last_err = e
                if attempt < 2:
                    time.sleep(2)
        raise RuntimeError(f"Ninja connection error ({last_err})")

    def disconnect(self):
        try:
            if self.sio.connected:
                self.sio.disconnect()
        except Exception:
            pass

    def create_temp_email(self) -> str:
        res = self._emit_ack("generate_temp_mail")
        if not res or "emailData" not in res:
            raise RuntimeError(f"Failed generating email: {res}")
        ed = res.get("emailData", {})
        self.email_address = ed.get("emailAddress") or ed.get("address")
        self.visitor_token = res.get("newToken")
        return self.email_address

    def extract_otp(self, text: str) -> str | None:
        clean = re.sub(r'Menlo\s+Park[^\n\r]*\b94025\b', '', text, flags=re.IGNORECASE)
        patterns = [
            r'(?:code|otp|pin|código)[\s\:\-\n\r]+(?:is\s*)?([0-9]{6})\b',
            r'\b([0-9]{6})\s+(?:is\s+your\s+(?:Meta|Instagram|Facebook|security|confirmation)\s+code)\b',
            r'\b([0-9]{6})\b',
        ]
        for p in patterns:
            m = re.search(p, clean, re.IGNORECASE)
            if m:
                code = m.group(1)
                if code != "94025" and not code.startswith("0000"):
                    return code
        return None

    def check_and_read_inbox(self) -> str | None:
        res = self._emit_ack("get_email_messages", {"messageType": "inbound"})
        if not res or not isinstance(res, dict):
            return None
        messages = res.get("email_messages") or []
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            mid = msg.get("id") or msg.get("email_message_id")
            if not mid or mid in self.processed_message_ids:
                continue
            self.processed_message_ids.add(mid)
            detail = self._emit_ack("get_email_message", {"messageId": mid, "messageType": "inbound"}, timeout=8)
            msg_data = {}
            if detail and isinstance(detail, dict):
                em = detail.get("emailMessage")
                if isinstance(em, dict):
                    msg_data = em.get("data") or {}
            if not msg_data and isinstance(msg, dict):
                msg_data = msg
            if not isinstance(msg_data, dict):
                msg_data = {}
            subject = str(msg_data.get("subject") or "")
            raw_html = str(msg_data.get("html") or msg_data.get("content") or "")
            raw_text = str(msg_data.get("text") or "")
            clean = raw_text.strip()
            if not clean and raw_html:
                soup = BeautifulSoup(raw_html, "html.parser")
                clean = soup.get_text(separator="\n").strip()
            combined = f"{subject}\n{clean}"
            otp = self.extract_otp(combined)
            if otp:
                self.latest_otp = otp
                self._otp_event.set()
                print(f"⭐ [NINJA-OTP] Extracted Code: >>> {otp} <<< (Subj: {subject})")
                return otp
        return None

    def wait_for_otp(self, timeout=45, poll_interval=1.5) -> str | None:
        start = time.time()
        while time.time() - start < timeout:
            if self._otp_event.is_set() and self.latest_otp:
                return self.latest_otp
            otp = self.check_and_read_inbox()
            if otp:
                return otp
            time.sleep(poll_interval)
        return None


# ==============================================================================
# 🤖 META AUTH CLIENT (PURE HTTP REQUESTS & ZERO BROWSER)
# ==============================================================================

class MetaAuthClient:
    """Pure HTTP Meta account creator via auth.meta.com."""
    BASE_URL = "https://auth.meta.com"
    SOURCE_APP_ID = "1522763855472543"
    TOS_CMS_ID = "957798449862312"

    def __init__(self, proxy: str | None = None, instance_name: str = "WORKER"):
        self.instance_name = instance_name
        self.session = curl_requests.Session(impersonate="chrome124")
        if proxy:
            self.session.proxies = {"http": proxy, "https": proxy}

        self.waterfall_id = str(uuid.uuid4())
        chars = string.ascii_letters + string.digits + "_-"
        self.client_session_id = "".join(random.choices(chars, k=24))
        self.device_id = ""
        self.email = ""
        self.req_counter = 1

        self.code_verifier = self.client_session_id + self.client_session_id
        digest = hashlib.sha256(self.code_verifier.encode("utf-8")).digest()
        self.code_challenge = base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")
        self.oidc_redirect_uri = self._build_oidc_uri()

        self.lsd = None
        self.jazoest = None
        self.public_key = None
        self.key_id = 199
        self.jurisdiction = "BD"
        self.reg_integrity = None
        self.fb_dtsg = None
        self.created_user_id = None

        self.rev = "1047303469"
        self.hsi = "7684275360328234786"
        self.hs = "20707.HYP:frl_comet_auth_pkg.2.1...0"
        self.s = "npdr3i:q5lguu:55za44"
        self.spin_r = "1047303469"
        self.spin_b = "trunk"
        self.spin_t = "1789134777"
        self.dyn = "7xe6E5aQ1Py8s-3eaQ412nwvG1Ww4KwhE2LwFwn82nwb-q2i5U4e1FxO0SE2Bw46wrU6C0AU1OU1vE2Yw45w43w16-0Co5G0zE1AE17U1eE1ko38w4mw4ewCw3mE1hE3Pw"

        self.session.headers.update({
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9",
            "origin": self.BASE_URL,
            "referer": f"{self.BASE_URL}/",
            "sec-ch-ua": '"Chromium";v="124", "Not?A_Brand";v="24", "Google Chrome";v="124"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "x-asbd-id": "359341",
        })

    def _build_oidc_uri(self) -> str:
        state_payload = {
            "csrf_token": self.client_session_id + "-" + self.client_session_id,
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
        return f"{self.BASE_URL}/oidc/?{urllib.parse.urlencode(params)}"

    def _next_req(self) -> str:
        r = base36_encode(self.req_counter)
        self.req_counter += 1
        return r

    def _safe_request(self, method: str, url: str, **kwargs):
        if "timeout" not in kwargs:
            kwargs["timeout"] = 25
        for attempt in range(1, 4):
            try:
                if method.lower() == "get":
                    return self.session.get(url, **kwargs)
                return self.session.post(url, **kwargs)
            except Exception as e:
                if attempt < 3:
                    time.sleep(1.5 * attempt)
                else:
                    raise e

    def _parse_fb(self, text: str) -> dict:
        clean = text[9:] if text.startswith("for (;;);") else text
        try:
            return json.loads(clean)
        except Exception:
            return {"raw_text": text}

    def _spin_params(self) -> dict:
        token = self.fb_dtsg or self.lsd or "AdS4dILcliXDKFeDHlE3nhTH-OQ"
        p = {
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
            "__comet_req": "33",
            "lsd": self.lsd or "AdS4dILcliXDKFeDHlE3nhTH-OQ",
            "jazoest": compute_jazoest(token),
            "__spin_r": self.spin_r,
            "__spin_b": self.spin_b,
            "__spin_t": self.spin_t,
            "__jssesw": "1",
        }
        if self.fb_dtsg:
            p["fb_dtsg"] = self.fb_dtsg
        return p

    def init_session(self) -> bool:
        params = {
            "waterfall_id": self.waterfall_id,
            "redirect_uri": self.oidc_redirect_uri,
            "source_app_id": self.SOURCE_APP_ID,
            "force_reauth": "0"
        }
        doc_headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "none",
            "sec-fetch-user": "?1",
            "upgrade-insecure-requests": "1",
        }
        try:
            resp = self._safe_request("get", f"{self.BASE_URL}/", params=params, headers=doc_headers)
            text = resp.text

            lsd_match = re.search(r'\["LSD",\[\],\{"token":"([^"]+)"\}', text) or re.search(r'name="lsd"\s+value="([^"]+)"', text)
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

            self.session.headers["referer"] = f"{self.BASE_URL}/"
            return True
        except Exception:
            return False

    def check_contact_point(self, email: str) -> bool:
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
            "qpl_join_id": str(random.randint(1000000000000000, 9999999999999999)),
            "reg_navigation_flow_name": "new_to_family_c50_r1",
            "regulation_jurisdiction": json.dumps([self.jurisdiction]),
            "source_app_id": self.SOURCE_APP_ID,
            "waterfall_id": self.waterfall_id,
        }
        data.update(self._spin_params())
        headers = {"content-type": "application/x-www-form-urlencoded", "referer": f"{self.BASE_URL}/"}
        resp = self._safe_request("post", url, data=data, headers=headers)
        parsed = self._parse_fb(resp.text)
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
                            self.device_id = reg_info.get("device_id") or ""
                if "contactPoint" in payload and payload["contactPoint"]:
                    self.email = payload["contactPoint"]
        return True

    def check_password_and_dob(self, email: str, password: str, dob: str, first_name: str, last_name: str):
        url_pwd = f"{self.BASE_URL}/api/check-password/"
        pk = self.public_key or "19c30cf2379e56b8ab368d6f2479cb893a09a023db2d062b2686bb8761881e47"
        enc_pwd = encrypt_meta_password(password, public_key_hex=pk, key_id=self.key_id)

        data_pwd = {
            "contact_point": email,
            "date_of_birth": dob,
            "name": "",
            "password": enc_pwd,
            "contact_pointless_account": "false",
            "qpl_join_id": str(random.randint(1000000000000000, 9999999999999999)),
        }
        data_pwd.update(self._spin_params())
        headers = {"content-type": "application/x-www-form-urlencoded", "referer": f"{self.BASE_URL}/"}
        self._safe_request("post", url_pwd, data=data_pwd, headers=headers)

        url_dob = f"{self.BASE_URL}/api/check-date-of-birth/"
        data_dob = {
            "caa_event_flow": "ntm",
            "date_of_birth": dob,
            "email": email,
            "first_name": first_name or "",
            "has_youth_consent": "false",
            "isf": "false",
            "last_name": last_name or "",
            "phone_number": "",
            "qpl_join_id": str(random.randint(1000000000000000, 9999999999999999)),
            "reg_integrity": self.reg_integrity or "",
            "source_app_id": self.SOURCE_APP_ID,
        }
        data_dob.update(self._spin_params())
        resp_dob = self._safe_request("post", url_dob, data=data_dob, headers=headers)
        parsed_dob = self._parse_fb(resp_dob.text)
        if isinstance(parsed_dob, dict) and "payload" in parsed_dob:
            payload = parsed_dob.get("payload")
            if isinstance(payload, dict):
                reg_int = payload.get("regIntegrity") or payload.get("reg_integrity")
                if reg_int:
                    self.reg_integrity = reg_int
        return enc_pwd

    def check_profile(self, username: str):
        url = f"{self.BASE_URL}/api/kadabra/check_profile/"
        data = {
            "caa_event_flow": "ntm",
            "display_name": "",
            "foa_import_source_name": "",
            "foa_import_source_obid": "",
            "nta_disclosures_summary_cms_id": "",
            "picture_source": "",
            "qpl_join_id": str(random.randint(1000000000000000, 9999999999999999)),
            "tos_cms_id": self.TOS_CMS_ID,
            "username": username,
        }
        data.update(self._spin_params())
        headers = {"content-type": "application/x-www-form-urlencoded", "referer": f"{self.BASE_URL}/"}
        self._safe_request("post", url, data=data, headers=headers)

    def register_account(self, email: str, enc_pwd: str, username: str, dob: str, first_name: str, last_name: str) -> str | None:
        url = f"{self.BASE_URL}/login/device-based/kadabra-register-save-credentials/"
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
            "password": enc_pwd,
            "redirect_uri": self.oidc_redirect_uri,
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
            "qpl_join_id": str(random.randint(1000000000000000, 9999999999999999)),
        }
        data.update(self._spin_params())
        headers = {"content-type": "application/x-www-form-urlencoded", "referer": f"{self.BASE_URL}/"}
        resp = self._safe_request("post", url, data=data, headers=headers)
        parsed = self._parse_fb(resp.text)
        if isinstance(parsed, dict):
            # Explicit error ba captcha prompt check
            if "error" in parsed or "errors" in parsed:
                return None
            raw_str = str(parsed).lower()
            if "captcha" in raw_str or "checkpoint" in raw_str or "challenge" in raw_str:
                return None

            if "dtsgToken" in parsed:
                self.fb_dtsg = parsed["dtsgToken"]
            payload = parsed.get("payload")
            if isinstance(payload, dict):
                user_id = payload.get("account_id") or payload.get("uid") or payload.get("user_id")
                if user_id:
                    self.created_user_id = str(user_id)
                    return self.created_user_id
            return "PENDING_OTP"
        return None

    def confirm_otp(self, code: str, email: str) -> bool:
        """Strict verification: checks if OTP was truly confirmed without triggering captcha/checkpoint."""
        url = f"{self.BASE_URL}/api/graphql/"
        variables = {
            "input": {
                "confirmation_code": {"sensitive_string_value": str(code).strip()},
                "confirmation_code_type": "OTP_CODE",
                "event_flow": "ntm",
                "rl_client_session_id": self.client_session_id,
                "source_app_id": self.SOURCE_APP_ID,
                "waterfall_id": self.waterfall_id
            }
        }
        data = {"doc_id": "9851798224911796", "variables": json.dumps(variables)}
        data.update(self._spin_params())
        headers = {"content-type": "application/x-www-form-urlencoded", "referer": f"{self.BASE_URL}/"}
        resp = self._safe_request("post", url, data=data, headers=headers)
        parsed = self._parse_fb(resp.text)

        if isinstance(parsed, dict):
            # Error ba challenge response thakle reject hobe
            if "errors" in parsed or "error" in parsed:
                return False

            raw_txt = str(parsed).lower()
            if any(term in raw_txt for term in ["captcha", "checkpoint", "challenge", "fail", "blocked"]):
                return False

            data_obj = parsed.get("data")
            if isinstance(data_obj, dict):
                conf_obj = data_obj.get("confirm_email")
                if isinstance(conf_obj, dict):
                    # Strict validation: Meta theke isConfirmed True ashte hobe
                    return bool(conf_obj.get("isConfirmed", False))

        return False

    def complete_oidc(self) -> bool:
        """Checks final OAuth redirect to ensure account didn't hit a checkpoint or captcha wall."""
        doc_headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "referer": f"{self.BASE_URL}/"
        }
        try:
            resp = self.session.get(self.oidc_redirect_uri, headers=doc_headers, allow_redirects=True, timeout=15)
            final_url = str(resp.url).lower()
            resp_body = resp.text.lower()

            bad_indicators = [
                "checkpoint", "captcha", "challenge", "two_factor",
                "disabled", "suspend", "help/contact", "recaptcha"
            ]
            if any(term in final_url for term in bad_indicators):
                return False
            if "recaptcha" in resp_body or "challenge" in resp_body or "checkpoint" in resp_body:
                return False

            # Valid callback URL ba access code pawa gele verified
            if "code=" in final_url or "ecto" in final_url or "meta.ai" in final_url or resp.status_code in [200, 302]:
                return True
            return False
        except Exception:
            return False

    def close(self):
        try:
            self.session.close()
        except Exception:
            pass


# ==============================================================================
# 🚀 CORE ACCOUNT CREATION PIPELINE (SINGLE ACCOUNT)
# ==============================================================================

def create_single_account(proxy_str: str | None, target_password: str, worker_id: int = 1) -> tuple[bool, str, str, str]:
    """
    Creates a single Ninja Email + Meta Account.
    Returns: (success: bool, email: str, username: str, reason: str)
    """
    session_id = uuid.uuid4().hex[:8]
    proxy_url = format_proxy_url(proxy_str, session_id=session_id) if proxy_str else None

    # Step 1: Connect TempMail Ninja
    ninja = TempMailNinjaAPI(proxy=proxy_url, session_id=session_id)
    email = None
    try:
        ninja.connect()
        email = ninja.create_temp_email()
    except Exception as e:
        ninja.disconnect()
        return False, "", "", f"Ninja error: {e}"

    if not email:
        ninja.disconnect()
        return False, "", "", "Empty email received"

    # Step 2: Meta session init
    first, last = get_random_name()
    meta = MetaAuthClient(proxy=proxy_url, instance_name=f"W{worker_id}")

    if not meta.init_session():
        ninja.disconnect()
        meta.close()
        return False, email, "", "Meta session init failed"

    try:
        # Step 3: Registration flow
        meta.check_contact_point(email)
        dob = f"{random.randint(1992, 2002)}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"
        enc_pwd = meta.check_password_and_dob(email, target_password, dob, first, last)

        clean_fn = re.sub(r'[^a-zA-Z0-9]', '', first).lower() or "user"
        clean_ln = re.sub(r'[^a-zA-Z0-9]', '', last).lower() or "account"
        username = f"{clean_fn}_{clean_ln}_{random.randint(1000, 9999)}"
        meta.check_profile(username)

        acc_id = meta.register_account(email, enc_pwd, username, dob, first, last)
        if not acc_id:
            ninja.disconnect()
            meta.close()
            return False, email, username, "Registration request rejected / Captcha challenged"

        # Step 4: Receive 6-digit OTP
        otp_code = ninja.wait_for_otp(timeout=45, poll_interval=1.5)
        ninja.disconnect()

        if not otp_code:
            meta.close()
            return False, email, username, "OTP timeout (45s)"

        # Step 5: Confirm OTP with strict checkpoint validation
        is_confirmed = meta.confirm_otp(otp_code, email)
        if not is_confirmed:
            meta.close()
            return False, email, username, "OTP verification failed or Captcha required"

        # Step 6: Verify final redirection
        is_oidc_success = meta.complete_oidc()
        meta.close()

        if not is_oidc_success:
            return False, email, username, "Account hit checkpoint / Captcha post-verification"

        return True, email, username, "SUCCESS"

    except Exception as e:
        ninja.disconnect()
        meta.close()
        return False, email or "", "", f"Exception: {e}"


# ==============================================================================
# 🧵 MULTI-THREADED RUNNER
# ==============================================================================

class MultiThreadedRunner:
    """Orchestrates multi-threaded account generation."""

    def __init__(self, target_count: int, num_threads: int, delay_seconds: int = 2):
        self.target_count = target_count
        self.num_threads = max(1, num_threads)
        self.delay_seconds = delay_seconds

        self.proxy_mgr = ProxyManager(PROXIES_FILE)
        self.success_count = 0
        self.attempt_count = 0
        self.lock = threading.Lock()
        self.is_done = False

        self._init_csv()

    def _init_csv(self):
        if not os.path.exists(OUTPUT_CSV) or os.path.getsize(OUTPUT_CSV) == 0:
            with open(OUTPUT_CSV, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["Email", "Password", "Username", "CreatedAt", "Status"])

    def _save_account(self, email: str, password: str, username: str):
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(OUTPUT_CSV, "a", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([email, password, username, now_str, "SUCCESS"])
            f.flush()

    def _worker_loop(self, worker_id: int):
        while not self.is_done:
            with self.lock:
                if self.success_count >= self.target_count:
                    self.is_done = True
                    break
                self.attempt_count += 1
                current_attempt = self.attempt_count
                target = self.target_count

            current_proxy = self.proxy_mgr.get_next_proxy()
            pwd = generate_random_password(length=12)

            proxy_display = current_proxy.split("@")[-1] if current_proxy and "@" in current_proxy else (current_proxy or "DIRECT")
            print(f"\n[Worker #{worker_id} | Attempt #{current_attempt}] Starting creation...")
            print(f"  🌐 Proxy : {proxy_display}")
            print(f"  🔑 Pwd   : {pwd}")

            ok, email, user, reason = create_single_account(current_proxy, pwd, worker_id=worker_id)

            if ok and email:
                with self.lock:
                    if self.success_count < self.target_count:
                        self.success_count += 1
                        current_succ = self.success_count
                        self._save_account(email, pwd, user)
                        print(f"\n🎉 [Worker #{worker_id}] SUCCESS [{current_succ}/{target}]:")
                        print(f"   📧 Email    : {email}")
                        print(f"   🔑 Password : {pwd}")
                        print(f"   👤 Username : {user}")
                        print(f"   💾 Saved to : {os.path.basename(OUTPUT_CSV)}")
                    if self.success_count >= self.target_count:
                        self.is_done = True
                        break
                if self.delay_seconds > 0:
                    time.sleep(self.delay_seconds)
            else:
                print(f"  ⚠️ [Worker #{worker_id}] Skipped ({reason}) for email: {email or 'N/A'}")
                time.sleep(1.5)

    def run(self):
        print("=" * 72)
        print("  ⚡ NINJA & META ACCOUNT CREATOR (MULTI-THREADED & STANDALONE)")
        print(f"  🎯 Target Accounts : {self.target_count}")
        print(f"  🧵 Threads / Workers: {self.num_threads}")
        print(f"  🔑 Password Mode   : RANDOM (Generated per account)")
        print(f"  🌐 Proxies Pool    : {self.proxy_mgr.total()} loaded")
        print(f"  📊 Data Consume    : Ultra-low (~35-50 KB / account, pure HTTP API)")
        print(f"  📁 Output CSV      : {OUTPUT_CSV}")

        # Quick pre-flight proxy test
        first_proxy = self.proxy_mgr.get_next_proxy()
        if first_proxy:
            fmt_p = format_proxy_url(first_proxy)
            if fmt_p:
                try:
                    r = curl_requests.get("https://api.ipify.org?format=json", proxies={"http": fmt_p, "https": fmt_p}, timeout=15)
                    ip_val = r.json().get("ip", "Unknown") if r.status_code == 200 else f"HTTP {r.status_code}"
                    print(f"  🔍 Proxy Pre-flight : ✅ CONNECTED (Exit IP: {ip_val})")
                except Exception as ex:
                    print(f"  ⚠️ Proxy Pre-flight : ❌ Warning ({ex})")
                    print("     👉 Note for RDP: If proxy fails here, verify RDP IP whitelist in your proxy panel!")
        print("=" * 72)

        start_time = time.time()
        threads = []

        for i in range(1, self.num_threads + 1):
            t = threading.Thread(target=self._worker_loop, args=(i,), daemon=True)
            t.start()
            threads.append(t)
            time.sleep(0.5)

        try:
            while any(t.is_alive() for t in threads) and not self.is_done:
                time.sleep(0.3)
        except KeyboardInterrupt:
            print("\n[!] Ctrl+C detected. Shutting down gracefully...")
            self.is_done = True

        elapsed = time.time() - start_time
        print("\n" + "=" * 72)
        print(f"🎉 COMPLETED! Successfully created {self.success_count} Meta accounts in {elapsed:.1f}s.")
        print(f"📁 Verified accounts saved to: {OUTPUT_CSV}")
        print("=" * 72)


# ==============================================================================
# 🏁 MAIN ENTRY POINT
# ==============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Standalone Multi-Threaded Ninja & Meta Creator")
    parser.add_argument("count", nargs="?", type=int, default=None, help="Number of accounts to create (default: 10)")
    parser.add_argument("--threads", type=int, default=None, help="Number of concurrent threads (default: 3)")
    parser.add_argument("--delay", type=int, default=2, help="Delay in seconds between accounts per worker")
    args = parser.parse_args()

    count_val = args.count
    if count_val is None:
        try:
            user_input = input("কয়টি Meta অ্যাকাউন্ট তৈরি করতে চান? (ডিফল্ট: 10): ").strip()
            count_val = int(user_input) if user_input else 10
        except Exception:
            count_val = 10

    threads_val = args.threads
    if threads_val is None:
        try:
            user_threads = input("একসাথে কয়টি থ্রেড/ওয়ার্কার চালাতে চান? (ডিফল্ট: 3): ").strip()
            threads_val = int(user_threads) if user_threads else 3
        except Exception:
            threads_val = 3

    runner = MultiThreadedRunner(
        target_count=max(1, count_val),
        num_threads=max(1, threads_val),
        delay_seconds=args.delay
    )
    runner.run()