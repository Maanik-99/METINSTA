"""
test_ninja_loop.py
Testing TempMail Ninja account creation with a 15-second delay.
Every 5 successful accounts, automatically turns WiFi OFF and ON to rotate IP.
Tracks detected IP address for each creation and saves results to a text file.
"""

import sys
import time
import datetime
import subprocess
from NINJA import TempMailNinjaAPI, log

OUTPUT_FILE = "ninja_created_accounts.txt"
DELAY_SECONDS = 15
WIFI_RESET_INTERVAL = 5  # Toggle WiFi every 5 successful creations

_last_known_wifi_profile = "Redmi A2+"

def get_current_wifi_profile():
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

def toggle_wifi(profile_name=None):
    """Turns WiFi OFF and ON to obtain a fresh IP from the router"""
    if not profile_name:
        profile_name = get_current_wifi_profile()

    print(f"\n[🔄 WiFi Reset] Turning WiFi OFF & ON to rotate IP (Profile: {profile_name})...")
    try:
        # 1. Disconnect
        subprocess.run(["netsh", "wlan", "disconnect"], capture_output=True)
        time.sleep(3)

        # 2. Reconnect
        subprocess.run(["netsh", "wlan", "connect", f"name={profile_name}"], capture_output=True)

        # 3. Wait and verify connection state
        is_connected = False
        for remaining in range(6, 0, -1):
            sys.stdout.write(f"\r    Reconnecting WiFi... waiting {remaining}s for network...")
            sys.stdout.flush()
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

        if not is_connected:
            subprocess.run(["netsh", "wlan", "connect", f"name={profile_name}"], capture_output=True)
            time.sleep(3)

        print("\r" + " " * 65 + "\r", end="")
        print(f"[✓] [WiFi Reset] WiFi successfully reconnected to '{profile_name}'!\n")
    except Exception as e:
        print(f"[-] [WiFi Reset] Error toggling WiFi: {e}\n")

def run_ninja_test(total_accounts=None):
    """
    Runs Ninja account creation in a loop with a 15-second gap.
    Toggles WiFi every 5 accounts to prevent rate limits.
    Logs IP address, country, email address, token, and saves them to OUTPUT_FILE.
    
    :param total_accounts: Total accounts to create (None for infinite until Ctrl+C)
    """
    profile_name = get_current_wifi_profile()

    print("=" * 65)
    print("      TEMPORARY MAIL NINJA - 15-SECOND TEST RUNNER")
    print("=" * 65)
    print(f"[*] Save Destination : {OUTPUT_FILE}")
    print(f"[*] Interval Delay   : {DELAY_SECONDS} seconds")
    print(f"[*] WiFi Auto-Reset  : Every {WIFI_RESET_INTERVAL} accounts (Profile: {profile_name})")
    print(f"[*] Total Target     : {'Infinite (Ctrl+C to stop)' if total_accounts is None else total_accounts}")
    print("=" * 65 + "\n")

    attempt_count = 0
    successful_count = 0

    try:
        while True:
            attempt_count += 1
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"\n[{attempt_count}] Starting creation at {now_str} (Total Success: {successful_count})...")

            client = TempMailNinjaAPI()
            account_ok = False

            try:
                # 1. Connect and initialize session
                client.connect()

                # IP tracking
                client_ip = getattr(client, "ip", "Unknown") or "Unknown"
                client_country = getattr(client, "country", "Unknown") or "Unknown"

                # 2. Generate email
                email = client.create_temp_email()
                token = client.visitor_token or "N/A"
                full_token = f"NINJA:{token}:{email}"

                # 3. Log to file
                record_line = f"[{now_str}] | IP: {client_ip} ({client_country}) | Email: {email} | Token: {full_token}\n"
                with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
                    f.write(record_line)

                successful_count += 1
                account_ok = True

                print(f"[✓] SUCCESS #{successful_count}:")
                print(f"    - IP Used: {client_ip} ({client_country})")
                print(f"    - Email  : {email}")
                print(f"    - Saved to {OUTPUT_FILE}")

            except Exception as e:
                err_str = str(e)
                print(f"[X] FAILED on attempt #{attempt_count}: {e}")
                from airplane_mode import is_usb_phone_connected, rotate_ip_on_ninja_failure
                if is_usb_phone_connected():
                    print(f"\n[📱 USB PHONE DETECTED] Ninja mail create failed. Auto-toggling Airplane Mode to rotate IP...\n")
                    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
                        f.write(f"[{now_str}] | IP: Error/Limit | Action: Auto-resetting Airplane Mode\n")
                    rotate_ip_on_ninja_failure(reason=f"Ninja loop attempt #{attempt_count} failed: {e}", log_fn=print)
                elif "rate_limit_exceeded" in err_str or "Rate Limit Exceeded" in err_str or "namespaces failed to connect" in err_str:
                    print(f"\n[⚠️ RATE LIMIT HIT] Attempt #{attempt_count}: Server temporarily blocked this IP!")
                    print(f"    - Action: Auto-toggling WiFi now to get a new IP...\n")
                    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
                        f.write(f"[{now_str}] | IP: Rate-Limited | Action: Auto-resetting WiFi\n")
                    toggle_wifi(profile_name)
                else:
                    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
                        f.write(f"[{now_str}] | IP: Error | Error: {e}\n")
            finally:
                try:
                    client.disconnect()
                except Exception:
                    pass

            # Check if user target reached
            if total_accounts is not None and successful_count >= total_accounts:
                print(f"\n[+] Completed target of {total_accounts} accounts!")
                break

            # Auto-reset IP every 5 successful creations
            if account_ok and WIFI_RESET_INTERVAL and (successful_count % WIFI_RESET_INTERVAL == 0):
                print(f"\n[🔔 Target Milestone] Reached {successful_count} accounts!")
                from airplane_mode import is_usb_phone_connected, rotate_ip_on_ninja_failure
                if is_usb_phone_connected():
                    rotate_ip_on_ninja_failure(reason=f"Milestone {successful_count} accounts reached", log_fn=print)
                else:
                    toggle_wifi(profile_name)

            # 15 seconds countdown
            print(f"[*] Waiting {DELAY_SECONDS}s before next creation...")
            for remaining in range(DELAY_SECONDS, 0, -1):
                sys.stdout.write(f"\r    Next request in {remaining}s... ")
                sys.stdout.flush()
                time.sleep(1)
            print("\r" + " " * 35 + "\r", end="")

    except KeyboardInterrupt:
        print(f"\n\n[!] Test stopped by user. Total successful accounts: {successful_count}")
    
    print(f"\n[*] All records saved in: {OUTPUT_FILE}")

if __name__ == "__main__":
    target = None
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        target = int(sys.argv[1])
    run_ninja_test(total_accounts=target)
