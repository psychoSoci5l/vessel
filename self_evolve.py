#!/usr/bin/env python3
"""Self-evolving memory — Fase 16B.
Cron job settimanale: archivia record vecchi, genera stats.
Schedule suggerito: 0 3 * * 0  python3.13 ~/self_evolve.py
"""
import sqlite3
import time
from datetime import datetime
from pathlib import Path

DB_PATH = Path.home() / ".nanobot" / "vessel.db"


def _db_conn():
    conn = sqlite3.connect(str(DB_PATH), timeout=5)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def ensure_archive_table():
    """Crea tabella archive se non esiste (safe per prima esecuzione)."""
    with _db_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_messages_archive (
                id INTEGER PRIMARY KEY,
                ts TEXT NOT NULL,
                provider TEXT NOT NULL,
                channel TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT ''
            )
        """)


def archive_old_chats(days=90):
    """Sposta messaggi chat più vecchi di N giorni nella tabella archive."""
    cutoff = time.strftime("%Y-%m-%dT%H:%M:%S",
                           time.localtime(time.time() - days * 86400))
    with _db_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO chat_messages_archive SELECT * FROM chat_messages WHERE ts < ?",
            (cutoff,))
        cur = conn.execute("DELETE FROM chat_messages WHERE ts < ?", (cutoff,))
        return cur.rowcount


def cleanup_old_usage(days=180):
    """Elimina record usage più vecchi di N giorni."""
    cutoff = time.strftime("%Y-%m-%dT%H:%M:%S",
                           time.localtime(time.time() - days * 86400))
    with _db_conn() as conn:
        cur = conn.execute("DELETE FROM usage WHERE ts < ?", (cutoff,))
        return cur.rowcount


def compute_stats():
    """Calcola statistiche sulla chat: messaggi per provider, per mese."""
    with _db_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0]
        archived = conn.execute("SELECT COUNT(*) FROM chat_messages_archive").fetchone()[0]

        by_provider = {}
        for row in conn.execute(
            "SELECT provider, COUNT(*) as cnt FROM chat_messages GROUP BY provider"
        ).fetchall():
            by_provider[row["provider"]] = row["cnt"]

        by_month = {}
        for row in conn.execute(
            "SELECT substr(ts, 1, 7) as month, COUNT(*) as cnt FROM chat_messages GROUP BY month ORDER BY month"
        ).fetchall():
            by_month[row["month"]] = row["cnt"]

        return {
            "total_active": total,
            "total_archived": archived,
            "by_provider": by_provider,
            "by_month": by_month,
        }


def main():
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"[Self-evolve] Avvio: {now}")

    if not DB_PATH.exists():
        print("[Self-evolve] DB non trovato, skip")
        return

    ensure_archive_table()

    # 1. Archivia chat > 90 giorni
    archived = archive_old_chats(90)
    print(f"[Self-evolve] Chat archiviate: {archived}")

    # 2. Pulisci usage > 180 giorni
    cleaned = cleanup_old_usage(180)
    print(f"[Self-evolve] Usage eliminati: {cleaned}")

    # 3. Stats
    stats = compute_stats()
    print(f"[Self-evolve] Stats: {stats['total_active']} attivi, {stats['total_archived']} archiviati")
    for p, c in stats["by_provider"].items():
        print(f"  {p}: {c} msg")

    print(f"[Self-evolve] Completato")


if __name__ == "__main__":
    main()
