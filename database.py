import sqlite3
from typing import List, Optional
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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS favorites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                listing_uid TEXT,
                title TEXT,
                price TEXT,
                url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(chat_id, listing_uid)
            )
        """)
        # Safe migration if table already existed without column
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(subscribers)")
        cols = [col[1] for col in cur.fetchall()]
        if "has_received_initial" not in cols:
            conn.execute("ALTER TABLE subscribers ADD COLUMN has_received_initial INTEGER DEFAULT 0")

        # Clean up deprecated imoradar source completely
        conn.execute("DELETE FROM seen_listings WHERE source = 'imoradar'")
        conn.execute("DELETE FROM favorites WHERE listing_uid LIKE 'imoradar%'")

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

def reset_seen_listings():
    """Clears seen listings history and resets subscriber initial export status, keeping favorites and subscriber list intact."""
    with get_connection() as conn:
        conn.execute("DELETE FROM seen_listings")
        conn.execute("UPDATE subscribers SET has_received_initial = 0")
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

def get_listing_by_uid(uid: str) -> Optional[dict]:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT uid, source, title, price, url FROM seen_listings WHERE uid = ?", (uid,))
        row = cur.fetchone()
        if row:
            return {
                "uid": row[0],
                "source": row[1],
                "title": row[2],
                "price": row[3],
                "url": row[4]
            }
        return None

def is_favorite(chat_id: int, uid: str) -> bool:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM favorites WHERE chat_id = ? AND listing_uid = ?", (chat_id, uid))
        return cur.fetchone() is not None

def toggle_favorite(chat_id: int, uid: str) -> bool:
    """Toggles favorite status. Returns True if added, False if removed."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM favorites WHERE chat_id = ? AND listing_uid = ?", (chat_id, uid))
        if cur.fetchone():
            cur.execute("DELETE FROM favorites WHERE chat_id = ? AND listing_uid = ?", (chat_id, uid))
            conn.commit()
            return False
        else:
            listing = get_listing_by_uid(uid) or {}
            title = listing.get("title", "Apartament Timișoara")
            price = listing.get("price", "")
            url = listing.get("url", "")
            cur.execute("""
                INSERT OR REPLACE INTO favorites (chat_id, listing_uid, title, price, url)
                VALUES (?, ?, ?, ?, ?)
            """, (chat_id, uid, title, price, url))
            conn.commit()
            return True

def remove_favorite(chat_id: int, uid: str) -> bool:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM favorites WHERE chat_id = ? AND listing_uid = ?", (chat_id, uid))
        conn.commit()
        return cur.rowcount > 0

def get_favorites(chat_id: int) -> List[dict]:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT f.listing_uid, f.title, f.price, f.url, f.created_at, s.source
            FROM favorites f
            LEFT JOIN seen_listings s ON f.listing_uid = s.uid
            WHERE f.chat_id = ?
            ORDER BY f.created_at DESC
        """, (chat_id,))
        rows = cur.fetchall()
        return [
            {
                "listing_uid": r[0],
                "title": r[1],
                "price": r[2],
                "url": r[3],
                "created_at": r[4],
                "source": r[5] or "portal"
            }
            for r in rows
        ]
