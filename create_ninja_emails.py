"""
create_ninja_emails.py
==============================================================================
🥷 ONLY NINJA EMAIL GENERATOR
==============================================================================
- Creates fresh TempMail Ninja emails
- Saves directly to: ninja_created_accounts.txt
- Auto IP Rotation on Rate Limit or Error:
    * USB phone connected  --> Airplane Mode ON -> OFF
    * WiFi connected       --> WiFi Reset OFF -> ON
==============================================================================
"""

import os
import sys
import time
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Local imports
try:
    from NINJA import (
        TempMailNinjaAPI,
        toggle_wifi
    )
except ImportError:
    from ninja import (
        TempMailNinjaAPI,
        toggle_wifi
    )

from airplane_mode import (
    is_usb_phone_connected,
    rotate_ip_on_ninja_failure
)

import uuid

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(BASE_DIR, "ninja_created_accounts.txt")
DEFAULT_DELAY_SECONDS = 10


def rotate_ip(reason: str = "Rate Limit", use_proxy: bool = True, old_session: str | None = None) -> str | None:
    """Auto-rotates IP via Residential Proxy Session, USB Phone Airplane Mode, or WiFi Reset"""
    if use_proxy:
        new_session = uuid.uuid4().hex[:6]
        print(f"\n[🔄 PROXY ROTATION] Switching to new residential IP session ({new_session})...")
        print(f"     Reason: {reason}")
        print("     (PC WiFi & Phone remain completely uninterrupted)")
        return new_session

    print(f"\n[🔄 IP ROTATION] {reason}")
    try:
        if is_usb_phone_connected():
            print("[📱 USB PHONE DETECTED] Toggling Airplane Mode ON -> OFF...")
            rotate_ip_on_ninja_failure(reason=reason, log_fn=print)
            time.sleep(3)
        else:
            print("[📶 WIFI DETECTED] Resetting WiFi to rotate IP...")
            toggle_wifi()
            time.sleep(4)
    except Exception as e:
        print(f"[-] IP rotation error: {e}")
        time.sleep(4)
    return None


def create_ninja_emails(target_count: int = 10, delay_seconds: int = DEFAULT_DELAY_SECONDS):
    print("=" * 60)
    print(f"  🥷 NINJA EMAIL GENERATOR (Residential Proxy Enabled)")
    print(f"  Target: {target_count} Emails | Delay: {delay_seconds}s")
    print(f"  Output: {os.path.basename(OUTPUT_FILE)}")
    print("=" * 60)

    created = 0
    attempt = 0
    current_session = uuid.uuid4().hex[:6]

    while created < target_count:
        attempt += 1
        print(f"\n[{created + 1}/{target_count}] Generating email (attempt #{attempt})...")

        client = TempMailNinjaAPI(session_id=current_session)
        is_proxy = bool(client.proxy_url)
        try:
            client.connect()
            email = client.create_temp_email(auto_rotate_on_fail=False)

            if not email:
                raise RuntimeError("Empty email returned from Ninja API")

            token = f"NINJA:{client.visitor_token}:{email}"
            ip = getattr(client, "ip", "Unknown")
            country = getattr(client, "country", "")
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Save immediately to ninja_created_accounts.txt
            line = f"[{now_str}] | IP: {ip} | Email: {email} | Token: {token} | Status: READY\n"
            with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
                f.write(line)

            created += 1
            ip_display = f"{ip} ({country}) [Residential Proxy]" if is_proxy else ip
            print(f"  ✔ SUCCESS [{created}/{target_count}]:")
            print(f"     📧 Email : {email}")
            print(f"     🌐 IP    : {ip_display}")
            print(f"     💾 Saved to {os.path.basename(OUTPUT_FILE)}")

            if created < target_count:
                print(f"  ⏳ Waiting {delay_seconds}s before next request...")
                time.sleep(delay_seconds)

        except Exception as e:
            err_msg = str(e)
            print(f"  ❌ Error: {err_msg}")
            # Rotate IP via Proxy session or fallback to phone/WiFi
            new_sess = rotate_ip(reason=f"Ninja generate failed ({err_msg})", use_proxy=is_proxy, old_session=current_session)
            if new_sess:
                current_session = new_sess
            time.sleep(2)

        finally:
            try:
                client.disconnect()
            except Exception:
                pass

    print("\n" + "=" * 60)
    print(f"🎉 DONE! Successfully created {created} Ninja emails.")
    print(f"📁 All saved to: {OUTPUT_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    count = 10
    if len(sys.argv) > 1:
        try:
            count = int(sys.argv[1])
        except ValueError:
            count = 10
    else:
        try:
            user_input = input("কয়টি Ninja ইমেইল তৈরি করতে চান? (ডিফল্ট: 10): ").strip()
            if user_input:
                count = int(user_input)
        except Exception:
            count = 10

    create_ninja_emails(target_count=max(1, count))
