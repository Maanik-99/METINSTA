import sys
import time
from mail_td import MailTDClient, HTMLTextExtractor, extract_otp_from_mail_td_text

def read_inbox(address: str, password: str = "", token: str = "", live_refresh: bool = False, interval: int = 5):
    print("\n" + "=" * 60)
    print(f"[*] Target Email : {address}")
    print("=" * 60)
    
    client = MailTDClient()
    logged_in = False

    # 1. Access by Token if provided (format: MAILTD:<account_id>:<token> or just JWT token)
    if token:
        if token.startswith("MAILTD:"):
            parts = token.split(":", 2)
            client.account_id = parts[1] if len(parts) > 1 else None
            client.token = parts[2] if len(parts) > 2 else None
        else:
            client.token = token
        
        if client.token and client.account_id:
            try:
                # Test token
                client.get_messages()
                print(f"[+] Authenticated via Token! Account ID: {client.account_id}")
                logged_in = True
            except Exception:
                print("[-] Provided Token is invalid or expired.")
                logged_in = False

    # 2. Try Login with Password if not logged in
    if not logged_in and password:
        print(f"[*] Logging in with provided password...")
        try:
            data = client.login(address=address, password=password)
            print(f"[+] Login successful! Account ID: {client.account_id}")
            logged_in = True
        except Exception as e:
            print(f"[-] Login failed with password: {e}")

    # 3. If password wasn't provided or failed, try registering if account is new, or prompt
    if not logged_in:
        passwords_to_try = [password] if password else ["P@ssw0rd123!", "12345678", "password123"]
        for pwd in passwords_to_try:
            if not pwd:
                continue
            try:
                data = client.login(address=address, password=pwd)
                print(f"[+] Login successful with '{pwd}'! Account ID: {client.account_id}")
                logged_in = True
                break
            except Exception:
                pass

        if not logged_in:
            print(f"[*] Attempting to create/claim account for '{address}'...")
            reg_pwd = password or "P@ssw0rd123!"
            try:
                acc = client.create_account(address=address, password=reg_pwd)
                print(f"[+] Account registered successfully! Account ID: {acc.get('id')}")
                print(f"[+] Token: MAILTD:{acc.get('id')}:{acc.get('token')}")
                logged_in = True
            except Exception as ce:
                err_msg = str(ce)
                if "409" in err_msg or "Conflict" in err_msg:
                    print(f"\n[!] NOTE: '{address}' is already registered on Mail.td!")
                    print("[!] Mail.td accounts require their creation password or saved token to view messages.")
                    print("[!] If you created this email in a previous session, please pass its password or token.")
                else:
                    print(f"[-] Account creation failed: {ce}")
                return

    seen_msg_ids = set()

    def fetch_and_display():
        try:
            messages = client.get_messages()
        except Exception as e:
            print(f"[-] Failed to fetch messages: {e}")
            return 0

        if not messages:
            print(f"[{time.strftime('%H:%M:%S')}] Inbox is empty (0 messages). Waiting for incoming mails...")
            return 0

        new_count = 0
        for idx, msg in enumerate(messages, 1):
            msg_id = msg.get("id")
            if msg_id in seen_msg_ids:
                continue
            seen_msg_ids.add(msg_id)
            new_count += 1

            subject = msg.get("subject", "(No Subject)")
            sender = msg.get("from") or msg.get("sender", "Unknown Sender")
            date_str = msg.get("created_at") or msg.get("createdAt") or "Unknown Date"

            print("\n" + "#" * 60)
            print(f"📩 NEW MESSAGE #{idx}")
            print(f"ID      : {msg_id}")
            print(f"From    : {sender}")
            print(f"Subject : {subject}")
            print(f"Date    : {date_str}")

            if msg_id:
                try:
                    full_msg = client.get_message(msg_id)
                    text_body = full_msg.get("text_body") or ""
                    html_body = full_msg.get("html_body") or ""

                    extracted_text = ""
                    if html_body:
                        parser = HTMLTextExtractor()
                        try:
                            parser.feed(html_body)
                            extracted_text = parser.get_text()
                        except Exception:
                            pass

                    body_display = text_body.strip() or extracted_text.strip() or msg.get("preview_text", "")
                    
                    otp = extract_otp_from_mail_td_text(body_display, subj=subject, mail_from=str(sender))
                    if otp:
                        print("\n" + "*" * 40)
                        print(f"🔑 VERIFICATION OTP / CODE: {otp}")
                        print("*" * 40)

                    print("\n--- Message Body ---")
                    print(body_display[:1200] + ("\n... [truncated]" if len(body_display) > 1200 else ""))
                except Exception as e:
                    print(f"[-] Error loading message body: {e}")
            print("#" * 60)
        return new_count

    print(f"\n[*] Reading inbox...")
    fetch_and_display()

    if live_refresh:
        print(f"\n[*] Live Inbox Monitoring started (checking every {interval}s). Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(interval)
                fetch_and_display()
        except KeyboardInterrupt:
            print("\n[*] Stopped monitoring.")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        target_email = sys.argv[1].strip()
        pwd = sys.argv[2].strip() if len(sys.argv) > 2 else ""
        tok = sys.argv[3].strip() if len(sys.argv) > 3 else ""
    else:
        target_email = input("Enter Email Address [default: luca731@end.tw]: ").strip() or "luca731@end.tw"
        pwd = input("Enter Account Password (if you have one, else leave blank): ").strip()
        tok = input("Enter Token (if you have MAILTD:... token, else leave blank): ").strip()

    live_opt = input("Do you want live auto-refresh monitoring? (y/n) [default: y]: ").strip().lower()
    is_live = False if live_opt == 'n' else True

    read_inbox(target_email, password=pwd, token=tok, live_refresh=is_live)

