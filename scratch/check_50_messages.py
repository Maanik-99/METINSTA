import sqlite3
import os
import sys
import asyncio
from telethon import TelegramClient
from telethon.sessions import MemorySession
from telethon.crypto import AuthKey
import json

sys.stdout.reconfigure(encoding='utf-8')
os.makedirs("scratch", exist_ok=True)
sess_file = "taskly_session_8801949166249.session"
copy_file = os.path.join("scratch", "temp_db.sqlite")

with open(sess_file, "rb") as f_in, open(copy_file, "wb") as f_out:
    f_out.write(f_in.read())

con = sqlite3.connect(copy_file)
cur = con.cursor()
row = cur.execute("SELECT dc_id, server_address, port, auth_key FROM sessions").fetchone()
con.close()
os.remove(copy_file)

if row:
    dc_id, server_address, port, auth_key_bytes = row
    with open('config.json') as f:
        cfg = json.load(f)
    acc = cfg['telegram']['accounts'][0]
    
    mem = MemorySession()
    mem.set_dc(dc_id, server_address, port)
    mem.auth_key = AuthKey(data=auth_key_bytes)
    
    async def run():
        client = TelegramClient(mem, acc['api_id'], acc['api_hash'])
        await client.connect()
        print("Connected!")
        for b in ['Taskl1_bot', 'PayGoeasy_bot']:
            print(f"\n================ 50 RECENT MESSAGES FROM/TO @{b} ================")
            msgs = await client.get_messages(b, limit=50)
            for m in reversed(msgs):
                txt = (m.text or "").replace('\n', ' ')
                if len(txt) > 100:
                    txt = txt[:97] + '...'
                direction = ">>> OUT" if m.out else "<<< IN"
                print(f"[{m.date.strftime('%H:%M:%S')}] {direction}: {txt}")
        await client.disconnect()

    asyncio.run(run())
