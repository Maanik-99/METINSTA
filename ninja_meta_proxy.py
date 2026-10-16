"""
ninja_meta_proxy.py
==============================================================================
⚡ NINJA & META ACCOUNT CREATOR WITH PROXY POOL & RANDOM PASSWORDS
==============================================================================
Features:
  1. Reads proxies from proxies.txt (rotates per account/attempt).
  2. Generates unique, secure random passwords for every account.
  3. Pure HTTP API & Socket.IO (Ultra-fast, zero browser, zero emulator).
  4. Ultra-low proxy data consumption (~35-50 KB per account).
  5. Automatically appends verified accounts to meta.csv:
     [Email, Password, Username, CreatedAt, Status]
==============================================================================
"""

import os
import sys
import time
import uuid
import re
import csv
import string
import secrets
import random
import argparse
from datetime import datetime

# Setup paths to import from root workspace
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(BASE_DIR)
for p in [BASE_DIR, PARENT_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from autometainstabot import MetaAuthClient, load_config
from email_service import get_random_name
from NINJA import TempMailNinjaAPI, format_proxy_url

OUTPUT_CSV = os.path.join(BASE_DIR, "meta.csv")
PROXIES_FILE = os.path.join(BASE_DIR, "proxies.txt")
DEFAULT_DELAY_SECONDS = 3


def generate_random_password(length: int = 12) -> str:
    """
    Generates a secure random password with letters, numbers, and symbols.
    Meets Meta's security requirements:
    - Uppercase & lowercase letters
    - Numbers
    - Allowed special characters (@, #, $, !, _)
    """
    lower = string.ascii_lowercase
    upper = string.ascii_uppercase
    digits = string.digits
    special = "@#$!_"

    # Guarantee at least 1 character from each group
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


class ProxyManager:
    """Loads and rotates proxies from proxies.txt."""

    def __init__(self, file_path: str = PROXIES_FILE):
        self.file_path = file_path
        self.proxies: list[str] = []
        self.index = 0
        self.load_proxies()

    def load_proxies(self):
        """Loads non-empty proxy lines from file."""
        if not os.path.exists(self.file_path):
            print(f"⚠️ Warning: {self.file_path} not found.")
            return

        with open(self.file_path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip() and not line.startswith("#")]

        self.proxies = lines
        self.index = 0
        print(f"✅ Loaded {len(self.proxies)} proxies from {os.path.basename(self.file_path)}")

    def get_next_proxy(self) -> str | None:
        """Returns the next proxy in round-robin fashion."""
        if not self.proxies:
            return None
        proxy = self.proxies[self.index % len(self.proxies)]
        self.index += 1
        return proxy

    def total(self) -> int:
        return len(self.proxies)


def init_meta_csv():
    """Initializes meta.csv with header if not present."""
    if not os.path.exists(OUTPUT_CSV) or os.path.getsize(OUTPUT_CSV) == 0:
        with open(OUTPUT_CSV, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Email", "Password", "Username", "CreatedAt", "Status"])


def append_to_meta_csv(email: str, password: str, username: str, status: str = "SUCCESS"):
    """Appends verified account to meta.csv."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(OUTPUT_CSV, "a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([email, password, username, now_str, status])
        f.flush()


def create_single_ninja_meta(proxy_str: str | None, target_password: str, instance_name: str = "AUTO") -> tuple[bool, str, str, str]:
    """
    Creates a single Ninja Email + Meta Account using the assigned proxy.
    Returns: (success: bool, email: str, username: str, reason: str)
    """
    # Resolve domain to active IP to bypass ISP DNS cache issues
    if proxy_str and "proxy.h143.xyz" in proxy_str:
        proxy_str = proxy_str.replace("proxy.h143.xyz", "31.59.160.7")

    session_id = uuid.uuid4().hex[:8]
    proxy_url = format_proxy_url(proxy_str, session_id=session_id) if proxy_str else None

    # 2. Connect TempMail Ninja via proxy
    ninja_client = TempMailNinjaAPI(proxy=proxy_url, session_id=session_id)
    email = None
    try:
        ninja_client.connect()
        email = ninja_client.create_temp_email(auto_rotate_on_fail=False)
    except Exception as e:
        try:
            ninja_client.disconnect()
        except Exception:
            pass
        return False, "", "", f"Ninja connect/email error: {e}"

    if not email:
        try:
            ninja_client.disconnect()
        except Exception:
            pass
        return False, "", "", "Empty email from Ninja"

    # 3. Meta registration via the exact same proxy session
    first_name, last_name = get_random_name()
    meta_client = MetaAuthClient(proxy=proxy_url, instance_name=instance_name)

    if not meta_client.init_session():
        try:
            ninja_client.disconnect()
        except Exception:
            pass
        try:
            meta_client.session.close()
        except Exception:
            pass
        return False, email, "", "Meta session init failed"

    try:
        # Step A: Check contact point availability
        meta_client.check_contact_point_availability(email=email)

        # Step B: Check password & DOB
        dob_year = random.randint(1992, 2002)
        dob_month = f"{random.randint(1, 12):02d}"
        dob_day = f"{random.randint(1, 28):02d}"
        dob = f"{dob_year}-{dob_month}-{dob_day}"
        meta_client.check_password(email=email, password_raw_or_payload=target_password, dob=dob)
        meta_client.check_date_of_birth(email=email, dob=dob, first_name=first_name, last_name=last_name)

        # Step C: Suggest / Choose username
        clean_fn = re.sub(r'[^a-zA-Z0-9]', '', first_name).lower() or "user"
        clean_ln = re.sub(r'[^a-zA-Z0-9]', '', last_name).lower() or "account"
        username = f"{clean_fn}_{clean_ln}_{random.randint(1000, 9999)}"
        meta_client.check_profile(username=username)

        # Step D: Submit registration (triggers 6-digit Meta verification email)
        meta_client.register_save_credentials(
            email=email,
            password_raw_or_payload=target_password,
            username=username,
            dob=dob,
            first_name=first_name,
            last_name=last_name
        )

        # 4. Receive 6-digit OTP from Ninja Socket.IO
        t_start = time.time()
        otp_code = ninja_client.wait_for_otp(timeout=45, poll_interval=1.5, expected_digits=6)
        elapsed = time.time() - t_start

        # Disconnect Ninja IMMEDIATELY to prevent proxy data drain
        try:
            ninja_client.disconnect()
        except Exception:
            pass

        if not otp_code:
            try:
                meta_client.session.close()
            except Exception:
                pass
            return False, email, username, f"OTP timeout ({elapsed:.1f}s)"

        # 5. Confirm OTP via Meta GraphQL
        confirm_resp = meta_client.confirm_email_otp(code=otp_code, email=email)

        # 6. Complete OIDC flow
        try:
            meta_client.complete_oidc_flow()
        except Exception:
            pass

        try:
            meta_client.session.close()
        except Exception:
            pass

        return True, email, username, "SUCCESS"

    except Exception as e:
        try:
            ninja_client.disconnect()
        except Exception:
            pass
        try:
            meta_client.session.close()
        except Exception:
            pass
        return False, email or "", "", f"Registration exception: {e}"


def run_pipeline(target_count: int = 10, delay_seconds: int = DEFAULT_DELAY_SECONDS, custom_password: str | None = None):
    init_meta_csv()
    proxy_mgr = ProxyManager()

    print("=" * 72)
    print("  ⚡ NINJA & META ACCOUNT CREATOR (PROXY POOL + RANDOM PASSWORDS)")
    print(f"  🎯 Target Accounts : {target_count}")
    print(f"  🔑 Password Mode   : {'Fixed (' + custom_password + ')' if custom_password else 'RANDOM (Generated per account)'}")
    print(f"  🌐 Proxies Loaded  : {proxy_mgr.total()} proxies in pool")
    print(f"  ⏳ Delay           : {delay_seconds}s")
    print(f"  📁 Output CSV      : {OUTPUT_CSV}")
    print("=" * 72)

    created = 0
    attempt = 0

    while created < target_count:
        attempt += 1
        current_proxy = proxy_mgr.get_next_proxy()
        
        # Generate fresh random password for this specific account
        account_password = custom_password if custom_password else generate_random_password(length=12)

        proxy_display = current_proxy.split("@")[-1] if current_proxy and "@" in current_proxy else (current_proxy or "DIRECT")
        print(f"\n[{created + 1}/{target_count}] Starting creation (Attempt #{attempt})...")
        print(f"  🌐 Using Proxy   : {proxy_display}")
        print(f"  🔑 Generated Pwd : {account_password}")

        ok, email, user, reason = create_single_ninja_meta(
            proxy_str=current_proxy,
            target_password=account_password,
            instance_name=f"PROXY-GEN-{created + 1}"
        )

        if ok and email:
            created += 1
            append_to_meta_csv(email, account_password, user, status="SUCCESS")
            print(f"  🎉 SUCCESS [{created}/{target_count}]:")
            print(f"     📧 Email    : {email}")
            print(f"     🔑 Password : {account_password}")
            print(f"     👤 Username : {user}")
            print(f"     💾 Saved to : {os.path.basename(OUTPUT_CSV)}")

            if created < target_count:
                print(f"  ☕ Waiting {delay_seconds}s before next account...")
                time.sleep(delay_seconds)
        else:
            print(f"  ⚠️ Skipped ({reason}) for email: {email or 'N/A'}")
            print("  🔄 Switching to next proxy from proxies.txt for next attempt...")
            time.sleep(2)

    print("\n" + "=" * 72)
    print(f"🎉 COMPLETED! Successfully created {created} Meta accounts.")
    print(f"📁 Verified accounts saved to: {OUTPUT_CSV}")
    print("=" * 72)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ninja Email & Meta Creator via proxies.txt with Random Passwords")
    parser.add_argument("count", nargs="?", type=int, default=None, help="Number of accounts to create (default: 10)")
    parser.add_argument("--delay", type=int, default=DEFAULT_DELAY_SECONDS, help="Delay in seconds between accounts")
    parser.add_argument("--password", type=str, default=None, help="Optional fixed password (default: random per account)")
    args = parser.parse_args()

    count_val = args.count
    if count_val is None:
        try:
            user_input = input("কয়টি Meta অ্যাকাউন্ট তৈরি করতে চান? (ডিফল্ট: 10): ").strip()
            count_val = int(user_input) if user_input else 10
        except Exception:
            count_val = 10

    run_pipeline(target_count=max(1, count_val), delay_seconds=args.delay, custom_password=args.password)
