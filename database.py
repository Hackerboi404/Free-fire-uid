import sqlite3
import logging
from contextlib import contextmanager

# Configure logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE_NAME = 'moderation_bot.db'

def get_db_connection():
    """Creates a database connection."""
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    return conn

@contextmanager
def get_db():
    """Context manager for database transactions."""
    conn = get_db_connection()
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        conn.close()

def init_db():
    """Initializes the database tables."""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Table to store registered groups
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS groups (
                id INTEGER PRIMARY KEY,
                group_id INTEGER UNIQUE NOT NULL,
                group_title TEXT,
                welcome_message TEXT DEFAULT 'Welcome {user}!',
                welcome_enabled INTEGER DEFAULT 1,
                anti_spam_threshold INTEGER DEFAULT 5
            )
        ''')
        
        # Table to store blocked words
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS blocked_words (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                word TEXT NOT NULL,
                FOREIGN KEY (group_id) REFERENCES groups (group_id) ON DELETE CASCADE
            )
        ''')
        
        # Table to store moderation logs
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                user_id INTEGER,
                username TEXT,
                action TEXT,
                details TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Table for general settings (optional, for bot-wide configs if needed)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        
    logger.info("Database initialized successfully.")

# --- Group Operations ---

def add_group(group_id, group_title):
    with get_db() as conn:
        conn.execute('INSERT OR IGNORE INTO groups (group_id, group_title) VALUES (?, ?)', (group_id, group_title))

def get_all_groups():
    with get_db() as conn:
        return conn.execute('SELECT * FROM groups').fetchall()

def is_group_registered(group_id):
    with get_db() as conn:
        return conn.execute('SELECT 1 FROM groups WHERE group_id = ?', (group_id,)).fetchone() is not None

# --- Blocked Words Operations ---

def add_blocked_word(group_id, word):
    with get_db() as conn:
        conn.execute('INSERT OR IGNORE INTO blocked_words (group_id, word) VALUES (?, ?)', (group_id, word.lower()))

def remove_blocked_word(group_id, word):
    with get_db() as conn:
        conn.execute('DELETE FROM blocked_words WHERE group_id = ? AND word = ?', (group_id, word.lower()))

def get_blocked_words(group_id):
    with get_db() as conn:
        return [row['word'] for row in conn.execute('SELECT word FROM blocked_words WHERE group_id = ?', (group_id,)).fetchall()]

# --- Log Operations ---

def add_log(group_id, user_id, username, action, details):
    with get_db() as conn:
        conn.execute('INSERT INTO logs (group_id, user_id, username, action, details) VALUES (?, ?, ?, ?, ?)',
                     (group_id, user_id, username, action, details))

def get_logs(group_id=None, limit=50):
    with get_db() as conn:
        if group_id:
            return conn.execute('SELECT * FROM logs WHERE group_id = ? ORDER BY timestamp DESC LIMIT ?', (group_id, limit)).fetchall()
        return conn.execute('SELECT * FROM logs ORDER BY timestamp DESC LIMIT ?', (limit,)).fetchall()

# --- Settings Operations ---

def update_group_setting(group_id, setting_column, value):
    # Dynamic update for specific columns in groups table
    query = f'UPDATE groups SET {setting_column} = ? WHERE group_id = ?'
    with get_db() as conn:
        conn.execute(query, (value, group_id))

def get_group_setting(group_id, setting_column):
    query = f'SELECT {setting_column} FROM groups WHERE group_id = ?'
    with get_db() as conn:
        result = conn.execute(query, (group_id,)).fetchone()
        return result[setting_column] if result else None
