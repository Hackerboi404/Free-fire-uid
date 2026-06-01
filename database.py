import sqlite3
import os
from datetime import datetime

DB_PATH = os.environ.get("DB_PATH", "bot_data.db")

class Database:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.create_tables()

    def create_tables(self):
        c = self.conn.cursor()
        c.executescript("""
            CREATE TABLE IF NOT EXISTS authorized_users (
                user_id INTEGER PRIMARY KEY,
                name TEXT,
                added_at TEXT
            );

            CREATE TABLE IF NOT EXISTS punished_users (
                chat_id INTEGER,
                user_id INTEGER,
                punished_at TEXT,
                PRIMARY KEY (chat_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS locks (
                chat_id INTEGER,
                lock_type TEXT,
                PRIMARY KEY (chat_id, lock_type)
            );

            CREATE TABLE IF NOT EXISTS action_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                target_id INTEGER,
                action TEXT,
                done_by INTEGER,
                reason TEXT,
                timestamp TEXT
            );
        """)
        self.conn.commit()

    # ── Authorized Users ──────────────────────
    def add_authorized(self, user_id: int, name: str):
        c = self.conn.cursor()
        c.execute(
            "INSERT OR REPLACE INTO authorized_users (user_id, name, added_at) VALUES (?, ?, ?)",
            (user_id, name, datetime.now().isoformat())
        )
        self.conn.commit()

    def remove_authorized(self, user_id: int):
        c = self.conn.cursor()
        c.execute("DELETE FROM authorized_users WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def is_authorized(self, user_id: int) -> bool:
        c = self.conn.cursor()
        c.execute("SELECT 1 FROM authorized_users WHERE user_id = ?", (user_id,))
        return c.fetchone() is not None

    def get_authorized_list(self):
        c = self.conn.cursor()
        c.execute("SELECT user_id, name FROM authorized_users")
        return c.fetchall()

    # ── Punish ────────────────────────────────
    def punish_user(self, chat_id: int, user_id: int):
        c = self.conn.cursor()
        c.execute(
            "INSERT OR REPLACE INTO punished_users (chat_id, user_id, punished_at) VALUES (?, ?, ?)",
            (chat_id, user_id, datetime.now().isoformat())
        )
        self.conn.commit()

    def unpunish_user(self, chat_id: int, user_id: int):
        c = self.conn.cursor()
        c.execute(
            "DELETE FROM punished_users WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id)
        )
        self.conn.commit()

    def is_punished(self, chat_id: int, user_id: int) -> bool:
        c = self.conn.cursor()
        c.execute(
            "SELECT 1 FROM punished_users WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id)
        )
        return c.fetchone() is not None

    # ── Locks ─────────────────────────────────
    def set_lock(self, chat_id: int, lock_type: str, locked: bool):
        c = self.conn.cursor()
        if locked:
            c.execute(
                "INSERT OR IGNORE INTO locks (chat_id, lock_type) VALUES (?, ?)",
                (chat_id, lock_type)
            )
        else:
            c.execute(
                "DELETE FROM locks WHERE chat_id = ? AND lock_type = ?",
                (chat_id, lock_type)
            )
        self.conn.commit()

    def get_locks(self, chat_id: int):
        c = self.conn.cursor()
        c.execute("SELECT lock_type FROM locks WHERE chat_id = ?", (chat_id,))
        return [row[0] for row in c.fetchall()]

    def is_locked(self, chat_id: int, lock_type: str) -> bool:
        c = self.conn.cursor()
        c.execute(
            "SELECT 1 FROM locks WHERE chat_id = ? AND (lock_type = ? OR lock_type = 'all')",
            (chat_id, lock_type)
        )
        return c.fetchone() is not None

    # ── Action Logs ───────────────────────────
    def log_action(self, chat_id: int, target_id: int, action: str, done_by: int, reason: str = ""):
        c = self.conn.cursor()
        c.execute(
            "INSERT INTO action_logs (chat_id, target_id, action, done_by, reason, timestamp) VALUES (?,?,?,?,?,?)",
            (chat_id, target_id, action, done_by, reason, datetime.now().isoformat())
        )
        self.conn.commit()
