"""
database.py — Persistence Layer
Handles all SQLite operations for chat history AND memory facts.
"""

import sqlite3
from datetime import datetime
from pathlib import Path


class ChatDatabase:
    """
    Manages a local SQLite database with two tables:
      messages  — full chat history with sentiment
      memory    — persistent key/value facts about the user
    """

    DEFAULT_PATH = Path(__file__).parent / "chat_history.db"

    def __init__(self, db_path=None):
        path = Path(db_path) if db_path else self.DEFAULT_PATH
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._cursor = self._conn.cursor()
        self._create_schema()

    # ── Schema ────────────────────────────────────────────────────────────
    def _create_schema(self):
        self._cursor.executescript("""
            CREATE TABLE IF NOT EXISTS messages (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp       TEXT    NOT NULL,
                sender          TEXT    NOT NULL,
                message         TEXT    NOT NULL,
                sentiment_score INTEGER NOT NULL DEFAULT 0
            );
        """)
        # Handle memory table migration — old schema had no 'user' column
        self._cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='memory'"
        )
        if self._cursor.fetchone():
            # Table exists — check if 'user' column is present
            cols = [r[1] for r in self._cursor.execute("PRAGMA table_info(memory)")]
            if "user" not in cols:
                # Old schema — drop and recreate with new schema
                self._cursor.execute("DROP TABLE memory")
        self._cursor.executescript("""
            CREATE TABLE IF NOT EXISTS memory (
                user        TEXT NOT NULL,
                key         TEXT NOT NULL,
                value       TEXT NOT NULL,
                learned_at  TEXT NOT NULL,
                PRIMARY KEY (user, key)
            );
        """)
        self._conn.commit()

    # ── Messages: Write ───────────────────────────────────────────────────
    def insert_message(self, sender, message, sentiment=0):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._cursor.execute(
            "INSERT INTO messages (timestamp, sender, message, sentiment_score) VALUES (?, ?, ?, ?)",
            (timestamp, sender, message, sentiment)
        )
        self._conn.commit()
        return self._cursor.lastrowid

    # ── Messages: Read ────────────────────────────────────────────────────
    def fetch_all(self):
        self._cursor.execute("SELECT * FROM messages ORDER BY id ASC")
        return [dict(row) for row in self._cursor.fetchall()]

    def fetch_by_sender(self, sender):
        self._cursor.execute(
            "SELECT * FROM messages WHERE sender = ? ORDER BY id ASC", (sender,)
        )
        return [dict(row) for row in self._cursor.fetchall()]

    def fetch_recent(self, n=20):
        self._cursor.execute(
            "SELECT * FROM (SELECT * FROM messages ORDER BY id DESC LIMIT ?) ORDER BY id ASC", (n,)
        )
        return [dict(row) for row in self._cursor.fetchall()]

    def message_count(self):
        self._cursor.execute("SELECT COUNT(*) FROM messages")
        return self._cursor.fetchone()[0]

    # ── Messages: Analytics ───────────────────────────────────────────────
    def sentiment_stats(self):
        self._cursor.execute(
            "SELECT sentiment_score FROM messages WHERE sender != 'PyChat'"
        )
        scores = [row[0] for row in self._cursor.fetchall()]
        if not scores:
            return {"total": 0, "average": 0.0, "positive_count": 0,
                    "negative_count": 0, "neutral_count": 0, "overall_mood": "neutral"}
        total   = sum(scores)
        average = total / len(scores)
        pos     = sum(1 for s in scores if s > 0)
        neg     = sum(1 for s in scores if s < 0)
        neu     = sum(1 for s in scores if s == 0)
        mood    = "positive" if total > 2 else "negative" if total < -2 else "neutral"
        return {"total": total, "average": round(average, 2),
                "positive_count": pos, "negative_count": neg,
                "neutral_count": neu, "overall_mood": mood}

    # ── Messages: Export ──────────────────────────────────────────────────
    def export_as_lines(self):
        rows = self.fetch_all()
        return list(map(
            lambda r: f"[{r['timestamp']}] {r['sender']}: {r['message']}", rows
        ))

    # ── Memory: Write ─────────────────────────────────────────────────────
    def save_memory(self, facts: dict, user: str = "default"):
        """Upsert all facts for a specific user."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for key, value in facts.items():
            self._cursor.execute(
                """INSERT INTO memory (user, key, value, learned_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(user, key) DO UPDATE SET
                       value=excluded.value,
                       learned_at=excluded.learned_at""",
                (user.lower().strip(), key.lower().strip(), value.strip(), timestamp)
            )
        self._conn.commit()

    def load_memory(self, user: str = "default") -> dict:
        """Load all stored facts for a specific user."""
        self._cursor.execute(
            "SELECT key, value FROM memory WHERE user = ?",
            (user.lower().strip(),)
        )
        return {row["key"]: row["value"] for row in self._cursor.fetchall()}

    def clear_memory(self, user: str = "default"):
        """Wipe all memory facts for a specific user."""
        self._cursor.execute("DELETE FROM memory WHERE user = ?",
                             (user.lower().strip(),))
        self._conn.commit()

    # ── Maintenance ───────────────────────────────────────────────────────
    def clear_all(self):
        self._cursor.execute("DELETE FROM messages")
        self._conn.commit()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def __repr__(self):
        return f"ChatDatabase(messages={self.message_count()})"


if __name__ == "__main__":
    import os
    TEST_DB = "test_chat.db"
    with ChatDatabase(TEST_DB) as db:
        db.insert_message("You", "Hello!", sentiment=1)
        db.insert_message("PyChat", "Hi there!", sentiment=0)
        db.save_memory({"name": "Kunal", "age": "20", "location": "Mumbai"})

        print("── Messages ──────────────────────────────")
        for r in db.fetch_all():
            print(f"  {r['sender']}: {r['message']}")

        print("\n── Memory ────────────────────────────────")
        print(f"  {db.load_memory()}")

        print(f"\n── Stats ─────────────────────────────────")
        for k, v in db.sentiment_stats().items():
            print(f"  {k:<18}: {v}")

    os.remove(TEST_DB)
    print("\n  ✓ test_chat.db removed")