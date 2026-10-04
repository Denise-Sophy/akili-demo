"""Long-term decision memory: append-only SQLite.

Working memory = the current conversation; this is the organisational layer
("what did we decide with Initech, and why?"). Exposed only through the MCP
server so it inherits the same auth, client scoping, audit and PII masking.
"""
import datetime as dt
import os
import sqlite3

DB_PATH = os.environ.get("AKILI_MEMORY_DB", "data/memory.db")


def _conn():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE IF NOT EXISTS decisions (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               ts TEXT NOT NULL, author TEXT NOT NULL, client TEXT NOT NULL,
               decision TEXT NOT NULL, rationale TEXT NOT NULL DEFAULT '')"""
    )
    return conn


def remember(author: str, client: str, decision: str, rationale: str = "") -> int:
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO decisions (ts, author, client, decision, rationale) VALUES (?, ?, ?, ?, ?)",
            (dt.datetime.now(dt.timezone.utc).isoformat(), author, client, decision, rationale),
        )
        return cur.lastrowid


def recall(client: str, query: str = "", limit: int = 10) -> list[dict]:
    sql = "SELECT ts, author, client, decision, rationale FROM decisions WHERE client = ?"
    args: list = [client]
    if query:
        sql += " AND (decision LIKE ? OR rationale LIKE ?)"
        args += [f"%{query}%", f"%{query}%"]
    sql += " ORDER BY id DESC LIMIT ?"
    args.append(limit)
    with _conn() as conn:
        return [dict(r) for r in conn.execute(sql, args)]
