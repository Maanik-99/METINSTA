"""
run_meta_from_pool.py
Directly creates a Meta account using pre-generated Ninja emails from ninja_created_accounts.txt pool.
"""

import asyncio
import sys
from autometainstabot import create_meta_account_task, load_config
from email_service import get_random_name

async def main():
    cfg = load_config()
    target_pwd = cfg.get("only_meta_password") or "saikat50968"
    first, last = get_random_name()
    
    print("=" * 60)
    print(f"  Meta Account Creation from Pre-generated Ninja Pool")
    print(f"  Name: {first} {last} | Pwd: {target_pwd}")
    print("=" * 60)
    
    ok, email, token = await create_meta_account_task(
        playwright=None,
        first_name=first,
        last_name=last,
        password=target_pwd,
        instance_name="POOL-1"
    )
    
    print("\n" + "=" * 60)
    if ok and email:
        print(f"🎉 SUCCESS! Meta Account Created:")
        print(f"   Email: {email}")
        print(f"   Password: {target_pwd}")
    else:
        print(f"❌ Failed to create Meta Account.")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
