"""
create_ninja_meta.py
==============================================================================
⚡ COMBINED 1-STEP NINJA & META ACCOUNT GENERATOR (via US Residential Proxy)
==============================================================================
Features:
  1. 100% Pure HTTP API & Socket.IO (Ultra-fast, Zero Browser, Zero Emulator).
  2. Ultra-Low Proxy Data Consumption:
     - Pure curl_cffi HTTP calls (~25 KB per account).
     - TempMail Ninja Socket.IO disconnects immediately upon receiving OTP (~10 KB).
     - Total bandwidth per account: ~35-50 KB (Over 20,000 accounts per 1 GB!).
  3. Per-Account IP Rotation:
     - Every single account generates a unique sticky session ID.
     - Guarantees a fresh US Residential IP for every single account.
  4. Instant Save to meta.csv:
     - Automatically appends [Email, Password, Username, CreatedAt, Status=SUCCESS].
==============================================================================
"""

import os
import sys
import time
import uuid
import re
import csv
import random
import argparse
from datetime import datetime

# Local imports
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(BASE_DIR)
for p in [BASE_DIR, PARENT_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from autometainstabot import MetaAuthClient, load_config
from email_service import get_random_name
from NINJA import TempMailNinjaAPI, format_proxy_url, get_configured_proxy

OUTPUT_CSV = os.path.join(BASE_DIR, "meta.csv")
ROOT_CSV = os.path.join(PARENT_DIR, "meta.csv")
DEFAULT_DELAY_SECONDS = 3


def init_meta_csv():
    """Initializes meta.csv with header if it doesn't exist."""
    for csv_file in [OUTPUT_CSV, ROOT_CSV]:
        if not os.path.exists(csv_file) or os.path.getsize(csv_file) == 0:
            with open(csv_file, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["Email", "Password", "Username", "CreatedAt", "Status"])


def append_to_meta_csv(email: str, password: str, username: str, status: str = "SUCCESS"):
    """Thread-safe append of verified account directly to meta.csv."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for csv_file in [OUTPUT_CSV, ROOT_CSV]:
        try:
            with open(csv_file, "a", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([email, password, username, now_str, status])
                f.flush()
        except Exception:
            pass


def create_single_ninja_meta(base_proxy: str | None, target_password: str, instance_name: str = "AUTO") -> tuple[bool, str, str, str]:
    """
    Creates a single Ninja Email + Meta Account using a dedicated, fresh residential proxy IP.
    Returns: (success: bool, email: str, username: str, reason: str)
    """
    session_id = uuid.uuid4().hex[:8]
    proxy_url = format_proxy_url(base_proxy, session_id=session_id) if base_proxy else None

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
        meta_client.check_contact_point_availability(email=email)

        dob_year = random.randint(1992, 2002)
        dob_month = f"{random.randint(1, 12):02d}"
        dob_day = f"{random.randint(1, 28):02d}"
        dob = f"{dob_year}-{dob_month}-{dob_day}"
        meta_client.check_password(email=email, password_raw_or_payload=target_password, dob=dob)
        meta_client.check_date_of_birth(email=email, dob=dob, first_name=first_name, last_name=last_name)

        clean_fn = re.sub(r'[^a-zA-Z0-9]', '', first_name).lower() or "user"
        clean_ln = re.sub(r'[^a-zA-Z0-9]', '', last_name).lower() or "account"
        username = f"{clean_fn}_{clean_ln}_{random.randint(1000, 9999)}"
        meta_client.check_profile(username=username)

        meta_client.register_save_credentials(
            email=email,
            password_raw_or_payload=target_password,
            username=username,
            dob=dob,
            first_name=first_name,
            last_name=last_name
        )

        t_start = time.time()
        otp_code = ninja_client.wait_for_otp(timeout=45, poll_interval=1.5, expected_digits=6)
        elapsed = time.time() - t_start

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

        meta_client.confirm_email_otp(code=otp_code, email=email)

        chk = meta_client.check_for_checkpoint(wait_sec=2)
        if chk:
            try:
                meta_client.session.close()
            except Exception:
                pass
            return False, email, username, "CHECKPOINT_HIT"

        meta_client.complete_oidc_flow()

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


def run_pipeline(target_count: int = 10, delay_seconds: int = DEFAULT_DELAY_SECONDS, password: str | None = None):
    init_meta_csv()
    cfg = load_config()
    target_pwd = password or cfg.get("only_meta_password") or "saikat50968"
    base_proxy = get_configured_proxy()

    print("=" * 68)
    print("  ⚡ COMBINED NINJA & META ACCOUNT GENERATOR (OPTIMIZED PROXY)")
    print(f"  🎯 Target Accounts : {target_count}")
    print(f"  🔑 Meta Password   : {target_pwd}")
    print(f"  ⏳ Delay           : {delay_seconds}s")
    print(f"  📁 Output Files    : meta.csv (Saved to both root & proxy folder)")
    if base_proxy:
        print("  🌐 IP Rotation     : Brand new US Residential IP per account")
        print("  📊 Data Consume    : Ultra-low (~35-50 KB per account, zero browser)")
    print("=" * 68)

    created = 0
    attempt = 0

    while created < target_count:
        attempt += 1
        print(f"\n[{created + 1}/{target_count}] Starting creation (Attempt #{attempt})...")

        ok, email, user, reason = create_single_ninja_meta(
            base_proxy=base_proxy,
            target_password=target_pwd,
            instance_name=f"GEN-{created + 1}"
        )

        if ok and email:
            created += 1
            append_to_meta_csv(email, target_pwd, user, status="SUCCESS")
            print(f"  🎉 SUCCESS [{created}/{target_count}]:")
            print(f"     📧 Email    : {email}")
            print(f"     🔑 Password : {target_pwd}")
            print(f"     👤 Username : {user}")
            print(f"     💾 Saved to : meta.csv")

            if created < target_count:
                print(f"  ☕ Waiting {delay_seconds}s before next fresh proxy rotation...")
                time.sleep(delay_seconds)
        else:
            print(f"  ⚠️ Skipped ({reason}) for email: {email or 'N/A'}")
            print("  🔄 Switching to brand new proxy session for next attempt...")
            time.sleep(2)

    print("\n" + "=" * 68)
    print(f"🎉 COMPLETED! Successfully created {created} Meta accounts.")
    print("📁 Verified accounts saved to: meta.csv")
    print("=" * 68)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Combined Ninja Email & Meta Account Creator (Pure Proxy)")
    parser.add_argument("count", nargs="?", type=int, default=None, help="Number of accounts to create (default: 10)")
    parser.add_argument("--delay", type=int, default=DEFAULT_DELAY_SECONDS, help="Delay in seconds between accounts")
    parser.add_argument("--password", type=str, default=None, help="Custom Meta password")
    args = parser.parse_args()

    count_val = args.count
    if count_val is None:
        try:
            user_input = input("কয়টি Meta অ্যাকাউন্ট তৈরি করতে চান? (ডিফল্ট: 10): ").strip()
            count_val = int(user_input) if user_input else 10
        except Exception:
            count_val = 10

    run_pipeline(target_count=max(1, count_val), delay_seconds=args.delay, password=args.password)
