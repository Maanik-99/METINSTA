import asyncio
import json
import os
import shutil
from telethon import TelegramClient

async def main():
    with open('config.json') as f:
        cfg = json.load(f)
    
    # Pick an account that is configured
    for acc in cfg['telegram']['accounts']:
        sess_orig = acc['session_name'] + '.session'
        if not os.path.exists(sess_orig):
            continue
        
        # Check if WAL exists
        copy_sess = os.path.join('scratch', 'temp_reader.session')
        shutil.copy2(sess_orig, copy_sess)
        if os.path.exists(sess_orig + '-wal'):
            shutil.copy2(sess_orig + '-wal', copy_sess + '-wal')
        if os.path.exists(sess_orig + '-shm'):
            shutil.copy2(sess_orig + '-shm', copy_sess + '-shm')
            
        client = TelegramClient(os.path.join('scratch', 'temp_reader'), acc['api_id'], acc['api_hash'])
        try:
            await client.connect()
            if not await client.is_user_authorized():
                print(f"Account {acc['phone']} not authorized.")
                await client.disconnect()
                continue
            
            print(f"Connected to Telegram as {acc['phone']}")
            target_bot = acc.get('target_bot', 'Taskl1_bot')
            for b in [target_bot, 'Taskl1_bot', 'PayGoeasy_bot']:
                try:
                    msgs = await client.get_messages(b, limit=12)
                    print(f"\n================ RECENT MESSAGES FROM/TO @{b} ================")
                    for m in reversed(msgs):
                        direction = ">>> OUT" if m.out else "<<< IN"
                        buttons = []
                        if m.buttons:
                            for row in m.buttons:
                                buttons.append([btn.text for btn in row])
                        btn_str = f" | Buttons: {buttons}" if buttons else ""
                        print(f"[{m.date}] {direction} (ID: {m.id}):\n{m.text}{btn_str}\n" + "-"*40)
                except Exception as ex:
                    print(f"Error fetching from {b}: {ex}")
            await client.disconnect()
            break
        except Exception as e:
            print(f"Error: {e}")
            try:
                await client.disconnect()
            except Exception:
                pass

if __name__ == "__main__":
    asyncio.run(main())
