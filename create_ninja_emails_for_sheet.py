"""
create_ninja_emails_for_sheet.py
==============================================================================
🎯 ONLY NINJA EMAIL GENERATOR (FOR GOOGLE SHEET & MANUAL ACCOUNT CREATION)
==============================================================================
Features:
- Generates 100% active Ninja TempMail emails with valid inbox tokens
- Generates matching password (from config 'only_meta_password' or custom format)
- Formatted for Google Sheets:
    * ninja_accounts_for_sheet.txt  (Tab-separated for direct 1-click copy-paste into Sheets)
    * ninja_accounts_for_sheet.csv  (CSV format for easy import)
- Automatic IP Rotation on Rate Limit:
    * Real USB Phone connected -> Toggles Airplane Mode ON/OFF
    * WiFi connected -> Disconnects & Reconnects WiFi to rotate IP
- Optional: Auto-insert directly into Google Sheet (Sheet1) via Google Sheets API
- Built-in OTP Listener: Enter any generated email to fetch its incoming OTP code!
==============================================================================
"""

import os
import sys
import time
import json
import re
from datetime import datetime

# Local imports
from NINJA import (
    TempMailNinjaAPI,
    get_or_create_ninja_client,
    toggle_wifi,
    _NINJA_CLIENTS
)
from airplane_mode import (
    is_usb_phone_connected,
    rotate_ip_on_ninja_failure
)
from email_service import (
    load_config,
    generate_custom_password
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_TSV = os.path.join(BASE_DIR, "ninja_accounts_for_sheet.txt")
OUTPUT_CSV = os.path.join(BASE_DIR, "ninja_accounts_for_sheet.csv")
POOL_FILE  = os.path.join(BASE_DIR, "ninja_created_accounts.txt")


def get_default_password() -> str:
    """Gets default password from config.json"""
    cfg = load_config()
    return cfg.get("only_meta_password") or generate_custom_password()


def rotate_ip(reason: str = "Rate Limit Hit"):
    """Rotates IP via USB Phone Airplane Mode (if connected) or WiFi Reset fallback"""
    print(f"\n[🔄 IP ROTATION] {reason}")
    try:
        if is_usb_phone_connected():
            print("[📱 USB PHONE] Triggering Airplane Mode ON -> OFF...")
            rotate_ip_on_ninja_failure(reason=reason, log_fn=print)
            time.sleep(3)
            return True
        else:
            print("[📶 WIFI] USB phone not detected. Resetting WiFi connection...")
            toggle_wifi()
            time.sleep(4)
            return True
    except Exception as e:
        print(f"[-] IP rotation error: {e}")
        time.sleep(4)
        return False


def create_single_ninja_account(password: str = None) -> tuple[str | None, str, str | None]:
    """
    Creates one fresh Ninja TempMail email.
    Returns: (email, password, token)
    """
    if not password:
        password = get_default_password()

    client = TempMailNinjaAPI()
    try:
        client.connect()
        email = client.create_temp_email(auto_rotate_on_fail=False)
        if not email:
            raise RuntimeError("Empty email returned from Ninja API")

        token = f"NINJA:{client.visitor_token}:{email}"
        ip = getattr(client, "ip", "Unknown")
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 1. Save to TSV (Tab-separated: Email \t Password) -> Pastes directly into Google Sheet columns A & B!
        with open(OUTPUT_TSV, "a", encoding="utf-8") as f:
            f.write(f"{email}\t{password}\t{token}\t{now_str}\n")

        # 2. Save to CSV
        file_exists = os.path.exists(OUTPUT_CSV)
        with open(OUTPUT_CSV, "a", encoding="utf-8") as f:
            if not file_exists or os.path.getsize(OUTPUT_CSV) == 0:
                f.write("Email,Password,Token,CreatedAt\n")
            f.write(f'"{email}","{password}","{token}","{now_str}"\n')

        # 3. Save to ninja_created_accounts.txt pool as READY
        with open(POOL_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{now_str}] | IP: {ip} | Email: {email} | Token: {token} | Status: READY\n")

        return email, password, token

    finally:
        try:
            client.disconnect()
        except Exception:
            pass


def generate_ninja_batch(count: int = 10, delay_sec: int = 10, auto_sheet: bool = False):
    """Generates multiple Ninja emails with auto-rotation on error"""
    print("\n" + "=" * 65)
    print(f"  🚀 GENERATING {count} NINJA EMAILS FOR GOOGLE SHEET")
    print(f"  Target Delay: {delay_sec}s  |  Output: {os.path.basename(OUTPUT_TSV)}")
    print("=" * 65)

    created_accounts = []
    consecutive_fails = 0

    while len(created_accounts) < count:
        current_num = len(created_accounts) + 1
        print(f"\n[{current_num}/{count}] Requesting Ninja email...")

        try:
            email, pwd, token = create_single_ninja_account()
            if email:
                consecutive_fails = 0
                created_accounts.append((email, pwd, token))
                print(f"  ✅ SUCCESS #{current_num}:")
                print(f"     📧 Email   : {email}")
                print(f"     🔑 Password: {pwd}")
                print(f"     📋 Sheet-ready format appended to {os.path.basename(OUTPUT_TSV)}")

                # Optional Google Sheet API Auto-Insert
                if auto_sheet:
                    try:
                        from google_sheet_manager import gsheet_manager
                        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        ok = gsheet_manager.append_done_account(
                            email=email,
                            password=pwd,
                            account_id="",
                            instance_name="MANUAL"
                        )
                        if ok:
                            print(f"     📊 Auto-synced to Google Sheet (Sheet1) successfully!")
                    except Exception as gs_err:
                        print(f"     ⚠ Google Sheet sync note: {gs_err}")

                if len(created_accounts) < count:
                    print(f"  ⏳ Waiting {delay_sec}s before next creation...")
                    time.sleep(delay_sec)

        except Exception as e:
            consecutive_fails += 1
            err_msg = str(e)
            print(f"  ❌ Error on attempt {current_num}: {err_msg}")

            # Rotate IP via Airplane mode or WiFi
            rotate_ip(reason=f"Ninja generate failed ({err_msg})")
            time.sleep(3)

    print("\n" + "=" * 65)
    print(f"🎉 COMPLETED! Generated {len(created_accounts)} Ninja Emails.")
    print("=" * 65)
    print(f"\n📂 Files Created/Updated:")
    print(f"1. {OUTPUT_TSV}  --> (Open and Copy-paste directly into Google Sheet)")
    print(f"2. {OUTPUT_CSV}  --> (CSV format)")
    print(f"3. {POOL_FILE}   --> (Main Bot / GUI Pool)")

    print("\n📋 FIRST 5 READY ACCOUNTS FOR YOUR SHEET:")
    print("-" * 50)
    print("EMAIL\t\t\t\t\tPASSWORD")
    print("-" * 50)
    for em, pw, _ in created_accounts[:5]:
        print(f"{em}\t{pw}")
    print("-" * 50)


def listen_otp_cli(email_or_token: str):
    """Real-time OTP listener for any generated email"""
    print(f"\n[*] Connecting to TempMail Ninja inbox for: {email_or_token}...")
    client = get_or_create_ninja_client(email_or_token)
    if not client:
        # Search in file
        token = None
        if os.path.exists(POOL_FILE):
            with open(POOL_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    if email_or_token in line and "Token:" in line:
                        parts = line.split("|")
                        for p in parts:
                            if "Token:" in p:
                                token = p.replace("Token:", "").strip()
                                break
        if token:
            client = get_or_create_ninja_client(token)

    if not client:
        print(f"❌ Could not connect or find token for {email_or_token}.")
        return

    print(f"✔ Connected to inbox! Listening for incoming OTP (waiting up to 120s)...")
    try:
        otp = client.wait_for_otp(timeout=120, poll_interval=2, expected_digits=6)
        if otp:
            print(f"\n🎉 KEY RECEIVED! OTP Code: >>> {otp} <<<")
        else:
            print("\n⌛ Timeout: No OTP arrived within 120 seconds.")
    except KeyboardInterrupt:
        print("\n⏹ Stopped listening.")
    except Exception as e:
        print(f"[-] Error: {e}")


def interactive_menu():
    print("""
======================================================
  🥷 NINJA EMAIL GENERATOR (FOR GOOGLE SHEET)
======================================================
1. Generate 1 Email (Quick Copy)
2. Generate 5 Emails (For Sheet)
3. Generate 10 Emails (For Sheet)
4. Generate 30 Emails (Batch for Sheet)
5. Custom Count (You specify count)
6. Listen for OTP on an Email (Real-time Code Viewer)
7. Exit
======================================================
""")
    choice = input("Select option (1-7): ").strip()

    if choice == "1":
        generate_ninja_batch(count=1, delay_sec=5)
    elif choice == "2":
        generate_ninja_batch(count=5, delay_sec=10)
    elif choice == "3":
        generate_ninja_batch(count=10, delay_sec=10)
    elif choice == "4":
        generate_ninja_batch(count=30, delay_sec=10)
    elif choice == "5":
        try:
            num = int(input("Enter number of emails to generate: ").strip())
            generate_ninja_batch(count=max(1, num), delay_sec=10)
        except ValueError:
            print("Invalid number!")
    elif choice == "6":
        target = input("Enter email address to wait OTP for: ").strip()
        if target:
            listen_otp_cli(target)
    else:
        print("Goodbye!")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        try:
            arg_count = int(sys.argv[1])
            generate_ninja_batch(count=arg_count)
        except ValueError:
            if "@" in sys.argv[1]:
                listen_otp_cli(sys.argv[1])
            else:
                interactive_menu()
    else:
        interactive_menu()
