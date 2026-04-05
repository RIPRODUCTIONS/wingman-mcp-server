"""
SQLite logging for requests and revenue.

Schema:
  requests(id, ts, service, status_code, payer, amount_usd, duration_ms, error)
"""
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from . import config


def _connect() -> sqlite3.Connection:
    Path(config.DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS requests (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ts          REAL    NOT NULL DEFAULT (unixepoch('now')),
                service     TEXT    NOT NULL,
                status_code INTEGER NOT NULL,
                payer       TEXT,
                amount_usd  REAL,
                duration_ms INTEGER,
                error       TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_requests_service ON requests(service)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_requests_ts ON requests(ts)")
        conn.commit()


def log_request(
    service: str,
    status_code: int,
    payer: str | None = None,
    amount_usd: float | None = None,
    duration_ms: int | None = None,
    error: str | None = None,
) -> None:
    try:
        with _connect() as conn:
            conn.execute(
                "INSERT INTO requests (service, status_code, payer, amount_usd, duration_ms, error) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (service, status_code, payer, amount_usd, duration_ms, error),
            )
            conn.commit()
    except Exception:
        pass  # logging must never crash the request path


def get_stats() -> dict:
    with _connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM requests").fetchone()[0]
        paid  = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(amount_usd), 0) FROM requests WHERE payer IS NOT NULL"
        ).fetchone()
        by_service = conn.execute(
            "SELECT service, COUNT(*) AS calls, COALESCE(SUM(amount_usd), 0) AS revenue "
            "FROM requests GROUP BY service ORDER BY revenue DESC"
        ).fetchall()
        recent = conn.execute(
            "SELECT service, status_code, payer, amount_usd, duration_ms, "
            "datetime(ts, 'unixepoch') AS ts FROM requests ORDER BY id DESC LIMIT 20"
        ).fetchall()

    return {
        "total_requests": total,
        "paid_requests": paid[0],
        "total_revenue_usd": round(float(paid[1]), 6),
        "by_service": [dict(r) for r in by_service],
        "recent_requests": [dict(r) for r in recent],
    }
