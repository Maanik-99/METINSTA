import sqlite3
import shutil
import os

os.makedirs("scratch", exist_ok=True)
for f in os.listdir("."):
    if f.endswith(".session") and not f.endswith("-journal") and not f.endswith("-shm") and not f.endswith("-wal"):
        temp_name = os.path.join("scratch", "copy_" + f)
        try:
            shutil.copy2(f, temp_name)
            con = sqlite3.connect(temp_name)
            cur = con.cursor()
            tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            print(f"Session {f}: tables = {tables}")
            con.close()
            os.remove(temp_name)
            break
        except Exception as e:
            print(f"Error reading {f}: {e}")
