import sqlite3
from config import DB_NAME

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()

    # Authorized users
    cur.execute("""
    CREATE TABLE IF NOT EXISTS auth_users(
        user_id INTEGER PRIMARY KEY
    )
    """)

    # Punished users (group wise)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS punishments(
        chat_id INTEGER,
        user_id INTEGER,
        PRIMARY KEY(chat_id, user_id)
    )
    """)

    # Locks
    cur.execute("""
    CREATE TABLE IF NOT EXISTS locks(
        chat_id INTEGER,
        lock_type TEXT,
        PRIMARY KEY(chat_id, lock_type)
    )
    """)

    conn.commit()
    conn.close()

# ---------------- AUTH ----------------

def add_auth(user_id):
    conn = get_db()
    conn.execute(
        "INSERT OR IGNORE INTO auth_users(user_id) VALUES(?)",
        (user_id,)
    )
    conn.commit()
    conn.close()

def remove_auth(user_id):
    conn = get_db()
    conn.execute(
        "DELETE FROM auth_users WHERE user_id=?",
        (user_id,)
    )
    conn.commit()
    conn.close()

def is_auth(user_id):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM auth_users WHERE user_id=?",
        (user_id,)
    ).fetchone()
    conn.close()
    return bool(row)

# ---------------- PUNISH ----------------

def punish(chat_id, user_id):
    conn = get_db()
    conn.execute(
        "INSERT OR IGNORE INTO punishments(chat_id,user_id) VALUES(?,?)",
        (chat_id, user_id)
    )
    conn.commit()
    conn.close()

def unpunish(chat_id, user_id):
    conn = get_db()
    conn.execute(
        "DELETE FROM punishments WHERE chat_id=? AND user_id=?",
        (chat_id, user_id)
    )
    conn.commit()
    conn.close()

def is_punished(chat_id, user_id):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM punishments WHERE chat_id=? AND user_id=?",
        (chat_id, user_id)
    ).fetchone()
    conn.close()
    return bool(row)

# ---------------- LOCKS ----------------

def lock(chat_id, lock_type):
    conn = get_db()
    conn.execute(
        "INSERT OR IGNORE INTO locks(chat_id,lock_type) VALUES(?,?)",
        (chat_id, lock_type)
    )
    conn.commit()
    conn.close()

def unlock(chat_id, lock_type):
    conn = get_db()
    conn.execute(
        "DELETE FROM locks WHERE chat_id=? AND lock_type=?",
        (chat_id, lock_type)
    )
    conn.commit()
    conn.close()

def is_locked(chat_id, lock_type):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM locks WHERE chat_id=? AND lock_type=?",
        (chat_id, lock_type)
    ).fetchone()
    conn.close()
    return bool(row)
