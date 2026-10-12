import os
import sys
import uuid
import time
import re
import random

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from autometainstabot import MetaAuthClient, load_config
from email_service import get_random_name
from NINJA import TempMailNinjaAPI, format_proxy_url, get_configured_proxy

def test_combine_single():
    cfg = load_config()
    target_pwd = cfg.get("only_meta_password") or "saikat50968"
    base_proxy = get_configured_proxy()
    session_id = uuid.uuid4().hex[:6]
    proxy_url = format_proxy_url(base_proxy, session_id=session_id)
    
    print(f"[*] Proxy Session: {session_id}")
    print(f"[*] Formatted Proxy: {proxy_url}")
    
    # 1. Connect TempMail Ninja
    print("[1] Connecting to TempMail Ninja via proxy...")
    ninja = TempMailNinjaAPI(proxy=proxy_url, session_id=session_id)
    ninja.connect()
    email = ninja.create_temp_email(auto_rotate_on_fail=False)
    print(f"    ✔ Ninja Email Generated: {email} (IP: {ninja.ip})")
    
    if not email:
        ninja.disconnect()
        return False
        
    # 2. Meta Auth registration via same proxy
    print("[2] Initializing MetaAuthClient via same proxy...")
    first_name, last_name = get_random_name()
    meta = MetaAuthClient(proxy=proxy_url, instance_name="TEST-COMBINE")
    if not meta.init_session():
        print("    ❌ Failed to init Meta session")
        ninja.disconnect()
        return False
        
    print(f"    ✔ Meta Session Ready (LSD: {meta.lsd})")
    print(f"[3] Checking contact point & registering: {email}...")
    meta.check_contact_point_availability(email=email)
    
    dob = f"{random.randint(1992, 2002)}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"
    meta.check_password(email=email, password_raw_or_payload=target_pwd, dob=dob)
    meta.check_date_of_birth(email=email, dob=dob, first_name=first_name, last_name=last_name)
    
    clean_fn = re.sub(r'[^a-zA-Z0-9]', '', first_name).lower() or "user"
    clean_ln = re.sub(r'[^a-zA-Z0-9]', '', last_name).lower() or "account"
    username = f"{clean_fn}_{clean_ln}_{random.randint(1000, 9999)}"
    meta.check_profile(username=username)
    
    meta.register_save_credentials(
        email=email,
        password_raw_or_payload=target_pwd,
        username=username,
        dob=dob,
        first_name=first_name,
        last_name=last_name
    )
    print(f"    ✔ Registration submitted! Username: {username}")
    
    # 3. Wait for OTP
    print("[4] Waiting for 6-digit OTP code on Ninja socket...")
    t0 = time.time()
    otp = ninja.wait_for_otp(timeout=45, poll_interval=1.5, expected_digits=6)
    elapsed = time.time() - t0
    
    # Immediately disconnect ninja to stop proxy data consumption!
    try:
        ninja.disconnect()
    except Exception:
        pass
        
    print(f"    ✔ Ninja disconnected after {elapsed:.1f}s.")
    if not otp:
        print("    ❌ OTP Timeout!")
        return False
        
    print(f"    🎉 OTP Received: {otp}")
    
    # 4. Confirm OTP
    print("[5] Confirming OTP with Meta GraphQL...")
    conf = meta.confirm_email_otp(code=otp, email=email)
    print(f"    ✔ Confirmation Response: {conf}")
    
    # 5. Check checkpoint
    chk = meta.check_for_checkpoint(wait_sec=2)
    if chk:
        print(f"    ⚠️ Checkpoint hit: {chk}")
        return False
        
    meta.complete_oidc_flow()
    print(f"    🎉 100% Meta Account Successfully Created: {email} | {target_pwd} | {username}")
    return True

if __name__ == "__main__":
    test_combine_single()
