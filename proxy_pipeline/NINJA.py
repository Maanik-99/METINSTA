import os
import uuid
import sys
import io
import time
import json
import re
import threading
import subprocess
import socketio
import requests
from bs4 import BeautifulSoup

# Ensure safe terminal encoding & unbuffered output on all Windows platforms
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    elif sys.stdout.encoding != 'utf-8':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
except Exception:
    pass

def log(msg):
    """Safe immediate logging with flush"""
    print(msg, flush=True)

# ----- Proxy Configuration -----
DEFAULT_PROXY_STRING = "proxy.h143.xyz:8080:13d6d96e5acd20eef131b6cca806e203-country-US:2e25ca8966a93460"

def get_configured_proxy() -> str | None:
    """Reads proxy from config.json or returns DEFAULT_PROXY_STRING if enabled"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(base_dir, "config.json")
    try:
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                np = data.get("ninja_proxy", {})
                if np.get("enabled", True):
                    return np.get("proxy", DEFAULT_PROXY_STRING)
                return None
    except Exception:
        pass
    return DEFAULT_PROXY_STRING

def format_proxy_url(proxy_str: str | None = None, session_id: str | None = None) -> str | None:
    """
    Parses proxy string into standard http://user:pass@host:port URL.
    Supports formats:
      - host:port:user:pass
      - user:pass@host:port
      - http://user:pass@host:port
    Automatically inserts '-session-<session_id>' to username if session_id is provided.
    """
    if not proxy_str:
        return None

    raw = proxy_str.strip()
    if not raw:
        return None

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


class TempMailNinjaAPI:
    """
    TempMail Ninja (https://tempmail.ninja) API Client.
    Direct Socket.IO API connection with optional Residential Proxy support!
    Features:
      - Instant email generation
      - Residential Proxy support (US IP per session, no WiFi disconnect)
      - Real-time incoming email notifications
      - Automated OTP / Confirmation Code extraction (6-digit, 8-digit, 4-digit)
      - Link extraction
      - wait_for_otp() helper for automation scripts
    """
    BASE_URL = "https://tm-app.solucioneswc.com:2083"

    def __init__(self, locale="en", proxy: str | bool | None = None, session_id: str | None = None):
        self.locale = locale
        self.proxy_str = proxy if isinstance(proxy, str) else None
        self.session_id = session_id
        self.proxy_url = None
        self.http_session = None

        if proxy is not False:
            target_proxy = self.proxy_str or get_configured_proxy()
            if target_proxy:
                if not self.session_id:
                    self.session_id = uuid.uuid4().hex[:8]
                self.proxy_url = format_proxy_url(target_proxy, session_id=self.session_id)
                if self.proxy_url:
                    self.http_session = requests.Session()
                    self.http_session.proxies = {
                        'http': self.proxy_url,
                        'https': self.proxy_url
                    }

        self.sio = socketio.Client(
            http_session=self.http_session,
            logger=False,
            engineio_logger=False,
            reconnection=True,
            reconnection_attempts=5,
            reconnection_delay=2
        )
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Origin': 'https://tempmail.ninja',
            'Referer': 'https://tempmail.ninja/'
        }
        
        self.email_address = None
        self.visitor_token = None
        self.ip = None
        self.country = None
        self.email_data = None
        self.processed_message_ids = set()
        self.latest_otp = None
        self.latest_message = None
        self.is_running = False
        self._otp_event = threading.Event()
        self._lock = threading.Lock()

        # Socket.IO Event Handlers
        self.sio.on("connect", self._on_connect)
        self.sio.on("disconnect", self._on_disconnect)
        self.sio.on("new_message_notify", self._on_new_message_notify)

    def rotate_proxy(self, session_id: str | None = None):
        """Rotates residential proxy IP without disconnecting PC WiFi"""
        self.session_id = session_id or uuid.uuid4().hex[:8]
        target_proxy = self.proxy_str or get_configured_proxy()
        self.proxy_url = format_proxy_url(target_proxy, session_id=self.session_id)
        if self.proxy_url:
            self.http_session = requests.Session()
            self.http_session.proxies = {
                'http': self.proxy_url,
                'https': self.proxy_url
            }
            try:
                self.disconnect()
            except Exception:
                pass
            self.sio = socketio.Client(
                http_session=self.http_session,
                logger=False,
                engineio_logger=False,
                reconnection=True,
                reconnection_attempts=5,
                reconnection_delay=2
            )
            self.sio.on("connect", self._on_connect)
            self.sio.on("disconnect", self._on_disconnect)
            self.sio.on("new_message_notify", self._on_new_message_notify)

    def _on_connect(self):
        log("[+] Connected successfully to TempMail Ninja backend API.")

    def _on_disconnect(self):
        log("[!] Socket disconnected from server.")

    def _on_new_message_notify(self, data):
        """Called automatically when the server pushes a real-time new message event"""
        self.check_and_read_inbox()

    def _ensure_connected(self):
        if not self.sio.connected:
            try:
                log(f"[*] Reconnecting to TempMail Ninja backend API...")
                self.sio.connect(
                    f"{self.BASE_URL}?locale={self.locale}",
                    headers=self.headers,
                    transports=['websocket', 'polling'],
                    wait_timeout=15
                )
                if self.visitor_token:
                    self._emit_ack("get_guest_user_data", {"token": self.visitor_token})
            except Exception as e:
                log(f"[-] Reconnection error: {e}")

    def _emit_ack(self, event, *args, timeout=10):
        """Helper to emit Socket.IO event and wait for acknowledgement"""
        if not self.sio.connected and event != "get_guest_user_data":
            self._ensure_connected()
        if not self.sio.connected:
            return None

        result = []
        event_done = threading.Event()

        def callback(response):
            result.append(response)
            event_done.set()

        try:
            self.sio.emit(event, *args, callback=callback)
            event_done.wait(timeout=timeout)
        except Exception as e:
            log(f"[-] Error emitting event '{event}': {e}")
            return None

        return result[0] if result else None

    def connect(self, token=None):
        """Connects to Socket.IO backend and initializes guest session"""
        if token:
            self.visitor_token = token
        try:
            self.sio.connect(
                f"{self.BASE_URL}?locale={self.locale}",
                headers=self.headers,
                transports=['websocket', 'polling'],
                wait_timeout=15
            )
        except Exception as e:
            if "namespaces failed to connect" in str(e):
                raise RuntimeError("Ninja API Rate Limit Exceeded: Server temporarily blocked connections from this IP. Please wait 3-5 minutes or rotate your IP/VPN.") from e
            raise e

        # Initialize guest session
        guest_data = self._emit_ack("get_guest_user_data", {"token": self.visitor_token})
        if guest_data:
            self.ip = guest_data.get("ip", "Unknown")
            self.country = guest_data.get("country", "Unknown")
            log(f"[i] Guest session initialized (IP: {self.ip}, Country: {self.country})")

    def create_temp_email(self, auto_rotate_on_fail: bool = True):
        """Generates a temporary email address via API request"""
        try:
            res = self._emit_ack("generate_temp_mail")

            if not res or "emailData" not in res:
                raise RuntimeError(f"Failed to generate temp email. Response: {res}")

            self.email_data = res.get("emailData", {})
            self.email_address = self.email_data.get("emailAddress") or self.email_data.get("address")
            self.visitor_token = res.get("newToken")
            expires_at = self.email_data.get("expiresAt") or self.email_data.get("expires_at")

            log(f"[+] Created Ninja TempMail: {self.email_address}")
            return self.email_address
        except Exception as e:
            if auto_rotate_on_fail:
                if self.proxy_url:
                    try:
                        new_sess = uuid.uuid4().hex[:8]
                        log(f"[🔄] [NINJA] Rotating proxy to new residential IP session ({new_sess})...")
                        self.rotate_proxy(session_id=new_sess)
                        self.connect()
                        res_retry = self._emit_ack("generate_temp_mail")
                        if res_retry and "emailData" in res_retry:
                            self.email_data = res_retry.get("emailData", {})
                            self.email_address = self.email_data.get("emailAddress") or self.email_data.get("address")
                            self.visitor_token = res_retry.get("newToken")
                            log(f"[+] Created Ninja TempMail (after Proxy IP rotation): {self.email_address}")
                            return self.email_address
                    except Exception as p_err:
                        log(f"[-] [NINJA] Proxy rotation retry error: {p_err}")
                else:
                    try:
                        from airplane_mode import is_usb_phone_connected, rotate_ip_on_ninja_failure
                        if is_usb_phone_connected():
                            log(f"[!] [NINJA] TempMail creation failed: {e}. Rotating IP via phone Airplane Mode...")
                            if rotate_ip_on_ninja_failure(reason=f"Ninja mail create error: {e}", log_fn=log):
                                log("[*] [NINJA] Reconnecting to Ninja backend with new IP...")
                                try:
                                    self.disconnect()
                                except Exception:
                                    pass
                                time.sleep(2)
                                self.connect()
                                res_retry = self._emit_ack("generate_temp_mail")
                                if res_retry and "emailData" in res_retry:
                                    self.email_data = res_retry.get("emailData", {})
                                    self.email_address = self.email_data.get("emailAddress") or self.email_data.get("address")
                                    self.visitor_token = res_retry.get("newToken")
                                    log(f"[+] Created Ninja TempMail (after Airplane IP change): {self.email_address}")
                                    return self.email_address
                    except Exception as rot_e:
                        log(f"[-] [NINJA] Airplane mode auto-rotation attempt failed: {rot_e}")
            raise

    def extract_otp_or_code(self, subject, body_text, expected_digits=None):
        """
        Smart extraction of 6-digit, 8-digit, or 4-digit OTP / Confirmation Code
        from email subject and body with flexible length support.
        Filters out false positives (e.g. Menlo Park zip code 94025).
        """
        # Remove known footer boilerplate / zip codes (e.g. Menlo Park, CA 94025)
        clean_body = re.sub(r'Menlo\s+Park[^\n\r]*\b94025\b', '', body_text, flags=re.IGNORECASE)
        clean_body = re.sub(r'\b(?:CA|California)\s+94025\b', '', clean_body, flags=re.IGNORECASE)
        full_text = f"{subject}\n{clean_body}"

        # Ignore pure notification emails that do not contain verification codes
        ignore_subjects = [
            "did you just move a new profile",
            "action needed on your meta account",
            "security alert",
            "new login from",
            "account connected"
        ]
        if any(ign in subject.lower() for ign in ignore_subjects) and not re.search(r'\b(?:code|otp|pin|código|confirm)\b', full_text, re.IGNORECASE):
            return None

        if expected_digits:
            if isinstance(expected_digits, int):
                allowed_lengths = {expected_digits}
            elif isinstance(expected_digits, (list, tuple, set)):
                allowed_lengths = set(expected_digits)
            else:
                allowed_lengths = {6, 8}
        else:
            allowed_lengths = {6, 8, 4}

        # 1. High Priority: Keyword followed directly by code (supports 4 to 8 digits)
        keyword_patterns = [
            r'(?:confirmation|verification|security|auth(?:entication)?|login|access|activation|passcode|one-time)?\s*(?:code|otp|pin|código|kod)[\s\:\-\n\r]+(?:is\s*)?([0-9]{4,8}|[Gg]\-[0-9]{6}|[0-9]{3,4}[\-\s][0-9]{3,4})\b',
            r'(?:enter|use|with)\s+(?:the\s+)?(?:code\s+)?([0-9]{4,8})\s+(?:to\s+(?:confirm|verify|login|proceed|sign))',
            r'(?:code|otp|pin)[\s\:\=]+([0-9]{4,8})\b',
            r'\b([0-9]{6,8})\s+(?:is\s+your\s+(?:Instagram|Meta|Facebook|security|confirmation)\s+code)\b',
        ]
        for pattern in keyword_patterns:
            m = re.search(pattern, full_text, re.IGNORECASE)
            if m:
                raw_c = re.sub(r'\D', '', m.group(1))
                if len(raw_c) in allowed_lengths and raw_c != "94025":
                    return raw_c

        # 2. Subject Line numbers matching allowed lengths (check 8-digit first, then 6-digit)
        for d in sorted(allowed_lengths, reverse=True):
            subj_m = re.search(rf'\b([0-9]{{{d}}})\b', subject)
            if subj_m and subj_m.group(1) != "94025":
                return subj_m.group(1)

        # 3. Body numbers matching allowed lengths (check 8-digit first, then 6-digit)
        for d in sorted(allowed_lengths, reverse=True):
            body_matches = re.findall(rf'\b([0-9]{{{d}}})\b', clean_body)
            if body_matches:
                for c in reversed(body_matches):
                    if not c.startswith('000000') and c != "94025":
                        return c

        return None

    def get_message_detail(self, message_id):
        """Fetches complete message details by ID"""
        res = self._emit_ack("get_email_message", {"messageId": message_id, "messageType": "inbound"}, timeout=15)
        if not res or "emailMessage" not in res:
            return None
        return res.get("emailMessage", {})

    def check_and_read_inbox(self, expected_digits=None):
        """Fetches inbox and reads all unread messages, extracting OTP codes automatically"""
        self._ensure_connected()
        res = self._emit_ack("get_email_messages", {"messageType": "inbound"})
        if not res or not isinstance(res, dict):
            return []

        messages = res.get("email_messages", [])
        if not messages:
            return []

        new_found_messages = []

        for msg in messages:
            msg_id = msg.get("id") or msg.get("email_message_id")
            if not msg_id or msg_id in self.processed_message_ids:
                continue

            self.processed_message_ids.add(msg_id)
            
            # Fetch complete message content
            detail = self.get_message_detail(msg_id)
            msg_data = detail.get("data", {}) if detail else msg

            sender = msg_data.get("from")
            if isinstance(sender, dict):
                sender = sender.get("text") or sender.get("value", [{}])[0].get("address", "")
            
            recipient = msg_data.get("to")
            if isinstance(recipient, dict):
                recipient = recipient.get("text") or recipient.get("value", [{}])[0].get("address", "")

            subject = msg_data.get("subject", "No Subject")
            date_str = msg_data.get("date") or msg.get("created_at", "")
            raw_html = msg_data.get("html") or msg_data.get("content") or msg.get("content", "")
            raw_text = msg_data.get("text", "")

            # Convert HTML to clean readable text
            clean_text = raw_text.strip() if raw_text else ""
            if not clean_text and raw_html:
                soup = BeautifulSoup(raw_html, "html.parser")
                clean_text = soup.get_text(separator="\n").strip()

            # Smart OTP Extraction
            extracted_otp = self.extract_otp_or_code(subject, clean_text, expected_digits=expected_digits)
            if extracted_otp:
                with self._lock:
                    self.latest_otp = extracted_otp
                    self._otp_event.set()

            message_summary = {
                "id": msg_id,
                "from": sender,
                "to": recipient,
                "subject": subject,
                "date": date_str,
                "content": clean_text,
                "otp": extracted_otp
            }
            self.latest_message = message_summary
            new_found_messages.append(message_summary)

            # Clean and concise one-line logging
            if extracted_otp:
                log(f"⭐ [NINJA-OTP] Extracted Code: >>> {extracted_otp} <<< (From: {sender} | Subj: {subject})")
            else:
                log(f"[*] [NINJA-MAIL] Received email from: {sender} | Subj: {subject}")

        return new_found_messages

    def wait_for_otp(self, timeout=120, poll_interval=2, expected_digits=None, reset_latest=False):
        """
        Blocks until a fresh OTP / Confirmation code is received or timeout is reached.
        """
        if reset_latest:
            with self._lock:
                self.latest_otp = None
                self._otp_event.clear()

        if expected_digits:
            if isinstance(expected_digits, int):
                allowed_lengths = {expected_digits}
            elif isinstance(expected_digits, (list, tuple, set)):
                allowed_lengths = set(expected_digits)
            else:
                allowed_lengths = {6, 8}
        else:
            allowed_lengths = {4, 5, 6, 7, 8}

        log(f"[*] Waiting for OTP on '{self.email_address}' (Expected: {sorted(allowed_lengths)} digits, Timeout: {timeout}s)...")
        start_time = time.time()

        while time.time() - start_time < timeout:
            # 1. First check if latest_otp already arrived via socket notification
            with self._lock:
                if self.latest_otp:
                    otp = str(self.latest_otp).strip()
                    if len(otp) in allowed_lengths:
                        log(f"[✔] OTP successfully detected: {otp}")
                        return otp

            # 2. Check inbox via polling
            self._ensure_connected()
            new_msgs = self.check_and_read_inbox(expected_digits=expected_digits)
            for m in new_msgs:
                if m.get("otp"):
                    otp = str(m["otp"]).strip()
                    if len(otp) in allowed_lengths:
                        with self._lock:
                            self.latest_otp = otp
                        log(f"[✔] OTP successfully detected: {otp}")
                        return otp

            # 3. Wait on event or timeout
            remaining = timeout - (time.time() - start_time)
            if remaining <= 0:
                break
            wait_time = min(poll_interval, remaining)
            if self._otp_event.wait(timeout=wait_time):
                self._otp_event.clear()
                with self._lock:
                    if self.latest_otp:
                        otp = str(self.latest_otp).strip()
                        if len(otp) in allowed_lengths:
                            log(f"[✔] OTP successfully detected: {otp}")
                            return otp

        log("[-] Timeout reached waiting for OTP.")
        return None

    def listen_forever(self, poll_interval=5):
        """Continuously listens for incoming emails in real-time"""
        self.is_running = True
        log(f"[*] Listening for incoming emails on '{self.email_address}'...")
        log("[*] Real-time Push Notifications + Auto-polling + Auto-OTP extractor active.")
        log("[*] (Press Ctrl+C to stop at any time)\n")

        try:
            while self.is_running:
                self.check_and_read_inbox()
                time.sleep(poll_interval)
        except KeyboardInterrupt:
            log("\n[*] Stopping listener...")
        finally:
            self.disconnect()

    def disconnect(self):
        """Closes socket connection gracefully"""
        self.is_running = False
        if self.sio.connected:
            self.sio.disconnect()
            log("[*] Connection closed.")

# Global registry for active Ninja clients
_NINJA_CLIENTS: dict[str, TempMailNinjaAPI] = {}

# Thread-safe counter and locks for WiFi rotation
_wifi_lock = threading.Lock()
_ninja_counter_lock = threading.Lock()
_ninja_created_count = 0
WIFI_RESET_THRESHOLD = 10  # Reset WiFi every 10 successfully generated Ninja emails

_last_known_wifi_profile = "Redmi A2+"

def get_current_wifi_profile() -> str:
    """Detects active or visible Windows WiFi profile name accurately"""
    global _last_known_wifi_profile
    try:
        out = subprocess.check_output(["netsh", "wlan", "show", "interfaces"], text=True, errors="replace")
        for line in out.splitlines():
            parts = line.split(":", 1)
            if len(parts) == 2:
                k = parts[0].strip().lower()
                v = parts[1].strip()
                if k == "profile" and v and v.lower() != "profile":
                    _last_known_wifi_profile = v
                    return v
    except Exception:
        pass

    # Check visible networks in range
    try:
        net_out = subprocess.check_output(["netsh", "wlan", "show", "networks"], text=True, errors="replace")
        for line in net_out.splitlines():
            parts = line.split(":", 1)
            if len(parts) == 2:
                k = parts[0].strip().lower()
                v = parts[1].strip()
                if "ssid" in k and v:
                    _last_known_wifi_profile = v
                    return v
    except Exception:
        pass

    return _last_known_wifi_profile or "Redmi A2+"

def toggle_wifi(profile_name: str | None = None) -> bool:
    """Turns WiFi OFF and ON to rotate IP address and prevent server blocks"""
    with _wifi_lock:
        if not profile_name:
            profile_name = get_current_wifi_profile()

        log(f"\n[🔄 WiFi Reset] Turning WiFi OFF & ON to rotate IP (Profile: {profile_name})...")
        try:
            # 1. Disconnect
            subprocess.run(["netsh", "wlan", "disconnect"], capture_output=True)
            time.sleep(3)

            # 2. Reconnect to target profile
            subprocess.run(["netsh", "wlan", "connect", f"name={profile_name}"], capture_output=True)

            # 3. Wait and verify connection state
            is_connected = False
            for sec in range(1, 9):
                time.sleep(1)
                try:
                    chk = subprocess.check_output(["netsh", "wlan", "show", "interfaces"], text=True, errors="replace")
                    for line in chk.splitlines():
                        parts = line.split(":", 1)
                        if len(parts) == 2 and parts[0].strip().lower() == "state":
                            if "connected" in parts[1].strip().lower():
                                is_connected = True
                                break
                    if is_connected:
                        break
                except Exception:
                    pass

            # Fallback retry if not yet connected
            if not is_connected:
                log(f"[!] Re-attempting connection to {profile_name}...")
                subprocess.run(["netsh", "wlan", "connect", f"name={profile_name}"], capture_output=True)
                time.sleep(3)

            log(f"[✓] [WiFi Reset] WiFi successfully reconnected to '{profile_name}'!\n")
            return True
        except Exception as e:
            log(f"[-] [WiFi Reset] Error toggling WiFi: {e}\n")
            return False

def get_or_create_ninja_client(token_or_email: str | None = None, proxy: str | bool | None = None) -> TempMailNinjaAPI | None:
    """
    Returns existing connected TempMailNinjaAPI instance or reconnects via visitor token.
    """
    if not token_or_email:
        return None

    key = str(token_or_email).strip()
    if key in _NINJA_CLIENTS:
        return _NINJA_CLIENTS[key]

    token = key
    if token.startswith("NINJA:"):
        parts = token.split(":")
        if len(parts) >= 2 and parts[1]:
            token = parts[1]

    try:
        client = TempMailNinjaAPI(proxy=proxy)
        client.connect(token=token)
        _NINJA_CLIENTS[key] = client
        return client
    except Exception as e:
        log(f"[-] [NINJA] Failed to create/reconnect client for {key}: {e}")
        return None

def generate_ninja_account(password: str = "", instance_name: str = "", proxy: str | bool | None = None) -> tuple[str | None, str, str | None]:
    """
    Generates a temporary email using TempMail Ninja.
    Automatically rotates IP via Residential Proxy if configured,
    or falls back to Airplane Mode / WiFi reset.
    Returns: (email, password, token)
    """
    global _ninja_created_count
    tag = f"[{instance_name}] " if instance_name else ""

    for attempt in range(2):
        client = None
        try:
            client = TempMailNinjaAPI(proxy=proxy)
            client.connect()
            email = client.create_temp_email(auto_rotate_on_fail=False)
            if not email:
                raise RuntimeError("Empty email returned from Ninja API")

            token = f"NINJA:{client.visitor_token}:{email}"
            _NINJA_CLIENTS[email] = client
            _NINJA_CLIENTS[token] = client
            if client.visitor_token:
                _NINJA_CLIENTS[client.visitor_token] = client

            # Update count thread-safely
            with _ninja_counter_lock:
                _ninja_created_count += 1
                curr_count = _ninja_created_count

            log(f"[+] {tag}[NINJA] Account #{curr_count} generated: {email} (IP: {getattr(client, 'ip', 'Unknown')})")

            # Check if milestone reached
            if WIFI_RESET_THRESHOLD and (curr_count % WIFI_RESET_THRESHOLD == 0):
                if getattr(client, "proxy_url", None):
                    log(f"\n[🔔 {tag}NINJA] Milestone reached ({curr_count} accounts). Residential proxy IP will rotate per session.")
                else:
                    log(f"\n[🔔 {tag}NINJA] Milestone reached ({curr_count} accounts created). Rotating IP...")
                    try:
                        from airplane_mode import is_usb_phone_connected, rotate_ip_on_ninja_failure
                        if is_usb_phone_connected():
                            rotate_ip_on_ninja_failure(reason=f"Milestone {curr_count} accounts reached", log_fn=log)
                        else:
                            toggle_wifi()
                    except Exception as ex:
                        log(f"[-] IP rotation error: {ex}")

            return email, password, token

        except Exception as e:
            err_str = str(e)
            log(f"[-] {tag}[NINJA] Error generating Ninja email (attempt {attempt + 1}/2): {e}")

            if client and getattr(client, "proxy_url", None):
                log(f"[🔄 {tag}NINJA] Rotating residential proxy session...")
                if attempt == 0:
                    time.sleep(1)
                    continue

            try:
                from airplane_mode import is_usb_phone_connected, rotate_ip_on_ninja_failure
                if is_usb_phone_connected():
                    log(f"[📱 {tag}NINJA] USB phone connected! Rotating IP via Airplane Mode...")
                    rotate_ip_on_ninja_failure(reason=f"Ninja creation error: {e}", log_fn=log)
                    if attempt == 0:
                        time.sleep(2)
                        continue
                else:
                    if ("Rate Limit Exceeded" in err_str or "namespaces failed to connect" in err_str) and attempt == 0:
                        log(f"\n[⚠️ {tag}NINJA] Server rate limit detected! Auto-resetting WiFi now to rotate IP...")
                        toggle_wifi()
                        time.sleep(2)
                        continue
            except Exception as rot_e:
                log(f"[-] IP rotation handling error: {rot_e}")

            return None, password, None

def fetch_otp_ninja(token_or_email: str, max_wait_sec: int = 60, expected_digits: int | None = None, instance_name: str = "") -> str | None:
    """
    Polls/waits for OTP / verification code from TempMail Ninja.
    """
    client = get_or_create_ninja_client(token_or_email)
    if not client:
        return None
    try:
        otp = client.wait_for_otp(
            timeout=max_wait_sec,
            poll_interval=2,
            expected_digits=expected_digits,
            reset_latest=False
        )
        return otp
    except Exception as e:
        log(f"[-] [NINJA] Error waiting for OTP: {e}")
        return None


def main():
    client = TempMailNinjaAPI()
    try:
        # 1. Connect to backend API
        client.connect()

        # 2. Create new temp email
        email = client.create_temp_email()

        # 3. Wait and read any incoming messages with auto OTP detection
        client.listen_forever(poll_interval=5)

    except Exception as e:
        log(f"[-] Error: {e}")
    finally:
        client.disconnect()


if __name__ == "__main__":
    main()
