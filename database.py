# database.py — Sets up and manages the SQLite database

import sqlite3
import os

DB_PATH = "tracker.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            url TEXT NOT NULL UNIQUE,
            keyword TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            processed INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()
    print("[DB] Database ready.")

def save_post(platform, url, keyword, timestamp):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("""
            INSERT OR IGNORE INTO posts (platform, url, keyword, timestamp, processed)
            VALUES (?, ?, ?, ?, 0)
        """, (platform, url, keyword, timestamp))
        conn.commit()
    except Exception as e:
        print(f"[DB] Error saving post: {e}")
    finally:
        conn.close()

def get_unprocessed_posts():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, platform, url, keyword, timestamp FROM posts WHERE processed = 0")
    rows = c.fetchall()
    conn.close()
    return rows

def get_recent_post_counts(hours=2):
    """Returns keyword volume counts for the last N hours for spike detection."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT keyword, platform, COUNT(*) as count
        FROM posts
        WHERE datetime(timestamp) >= datetime('now', ?)
        GROUP BY keyword, platform
        ORDER BY count DESC
    """, (f'-{hours} hours',))
    rows = c.fetchall()
    conn.close()
    return rows

def mark_processed(post_ids):
    if not post_ids:
        return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.executemany("UPDATE posts SET processed = 1 WHERE id = ?", [(i,) for i in post_ids])
    conn.commit()
    conn.close()
