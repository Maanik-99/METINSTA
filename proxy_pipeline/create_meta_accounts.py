"""
create_meta_accounts.py
==============================================================================
⚡ COMBINED 1-STEP NINJA & META ACCOUNT GENERATOR (via US Residential Proxy)
==============================================================================
"""

import sys
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(BASE_DIR)
for p in [BASE_DIR, PARENT_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from create_ninja_meta import run_pipeline, DEFAULT_DELAY_SECONDS

if __name__ == "__main__":
    count = 10
    if len(sys.argv) > 1:
        try:
            count = int(sys.argv[1])
        except ValueError:
            count = 10
    else:
        try:
            user_input = input("কয়টি Meta অ্যাকাউন্ট তৈরি করতে চান? (ডিফল্ট: 10): ").strip()
            if user_input:
                count = int(user_input)
        except Exception:
            count = 10

    run_pipeline(target_count=max(1, count), delay_seconds=DEFAULT_DELAY_SECONDS)
