import sqlite3
from typing import List
from config import DB_PATH

from contextlib import contextmanager

@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS seen_listings (
                uid TEXT PRIMARY KEY,
                source TEXT,
                title TEXT,
                price TEXT,
                url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                sent_to_telegram INTEGER DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS subscribers (
                chat_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                subscribed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                has_received_initial INTEGER DEFAULT 0
            )
        """)
        # Safe migration if table already existed without column
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(subscribers)")
        cols = [col[1] for col in cur.fetchall()]
        if "has_received_initial" not in cols:
            conn.execute("ALTER TABLE subscribers ADD COLUMN has_received_initial INTEGER DEFAULT 0")

        conn.commit()

def is_listing_seen(uid: str, url: str = "") -> bool:
    with get_connection() as conn:
        cur = conn.cursor()
        if url:
            cur.execute("SELECT 1 FROM seen_listings WHERE uid = ? OR url = ?", (uid, url))
        else:
            cur.execute("SELECT 1 FROM seen_listings WHERE uid = ?", (uid,))
        return cur.fetchone() is not None

def mark_listing_seen(uid: str, source: str, title: str, price: str, url: str, sent: int = 1):
    with get_connection() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO seen_listings (uid, source, title, price, url, sent_to_telegram)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (uid, source, title, price, url, sent))
        conn.commit()

def add_subscriber(chat_id: int, username: str = "", first_name: str = "") -> bool:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM subscribers WHERE chat_id = ?", (chat_id,))
        exists = cur.fetchone() is not None
        if not exists:
            cur.execute("""
                INSERT INTO subscribers (chat_id, username, first_name, has_received_initial)
                VALUES (?, ?, ?, 0)
            """, (chat_id, username, first_name))
            conn.commit()
            return True
        return False

def has_user_received_initial(chat_id: int) -> bool:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT has_received_initial FROM subscribers WHERE chat_id = ?", (chat_id,))
        row = cur.fetchone()
        return bool(row[0]) if row else False

def mark_user_initial_received(chat_id: int):
    with get_connection() as conn:
        conn.execute("UPDATE subscribers SET has_received_initial = 1 WHERE chat_id = ?", (chat_id,))
        conn.commit()

def get_subscribers() -> List[int]:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT chat_id FROM subscribers")
        return [row[0] for row in cur.fetchall()]

def get_stats() -> dict:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM seen_listings")
        total_seen = cur.fetchone()[0]
        cur.execute("SELECT source, COUNT(*) FROM seen_listings GROUP BY source")
        by_source = dict(cur.fetchall())
        cur.execute("SELECT COUNT(*) FROM subscribers")
        total_subscribers = cur.fetchone()[0]
        return {
            "total_seen": total_seen,
            "by_source": by_source,
            "total_subscribers": total_subscribers
        }

def is_db_empty() -> bool:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM seen_listings")
        count = cur.fetchone()[0]
        return count == 0
