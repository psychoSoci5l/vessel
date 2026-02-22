#!/usr/bin/env python3
"""Self-evolving memory — Fase 16B + 18C + 19A.
Cron job settimanale: summarize+archivia chat, pulisce usage, pota KG stale, stats.
Schedule: 0 3 * * 0  python3.13 ~/self_evolve.py
"""
import http.client
import json
import sqlite3
import time
from datetime import datetime, timedelta
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


OLLAMA_HOST = "127.0.0.1"
OLLAMA_PORT = 11434
OLLAMA_MODEL = "gemma3:4b"
OLLAMA_TIMEOUT = 180


def _call_ollama(prompt: str) -> str:
    """Chiama Ollama locale (sync) e ritorna il testo generato."""
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "keep_alive": "60m",
        "options": {"num_predict": 512},
    })
    conn = http.client.HTTPConnection(OLLAMA_HOST, OLLAMA_PORT, timeout=OLLAMA_TIMEOUT)
    conn.request("POST", "/api/chat", body=payload,
                 headers={"Content-Type": "application/json"})
    resp = conn.getresponse()
    body = resp.read().decode("utf-8", errors="replace")
    conn.close()
    if resp.status != 200:
        raise RuntimeError(f"Ollama HTTP {resp.status}: {body[:200]}")
    data = json.loads(body)
    return data.get("message", {}).get("content", "").strip()


def summarize_before_archive(days=90) -> str:
    """Genera summary dei messaggi che stanno per essere archiviati. Salva in weekly_summaries."""
    cutoff = time.strftime("%Y-%m-%dT%H:%M:%S",
                           time.localtime(time.time() - days * 86400))
    with _db_conn() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM chat_messages WHERE ts < ?", (cutoff,)).fetchone()[0]
        if count == 0:
            return ""

        # Raccogli statistiche dei messaggi da archiviare
        by_provider = {}
        for row in conn.execute(
            "SELECT provider, COUNT(*) as cnt FROM chat_messages WHERE ts < ? GROUP BY provider",
            (cutoff,)).fetchall():
            by_provider[row["provider"]] = row["cnt"]

        # Periodo coperto
        oldest = conn.execute(
            "SELECT MIN(ts) FROM chat_messages WHERE ts < ?", (cutoff,)).fetchone()[0]

        # Campione di messaggi utente (per contesto)
        user_msgs = conn.execute(
            "SELECT content FROM chat_messages WHERE ts < ? AND role = 'user' ORDER BY ts DESC LIMIT 10",
            (cutoff,)).fetchall()

    # Prompt compatto
    providers_str = ", ".join(f"{p}: {c}" for p, c in by_provider.items())
    sample = "\n".join(f"  - {r['content'][:80]}" for r in user_msgs[:5])

    prompt = f"""Sei Vessel, assistente personale di Filippo.
Questi {count} messaggi chat (periodo {oldest[:10]} — {cutoff[:10]}) stanno per essere archiviati.
Scrivi un breve riassunto (max 100 parole, italiano) di cosa è stato discusso.
Non inventare dati, basati solo su quello che vedi.

Messaggi per provider: {providers_str}
Esempi domande utente:
{sample}

Riassunto archivio:"""

    try:
        summary = _call_ollama(prompt)
    except Exception as e:
        print(f"[Self-evolve] Ollama offline per archive summary: {e}")
        topics = sample.replace("  - ", "").replace("\n", "; ")[:200]
        summary = f"Archivio {oldest[:10]}—{cutoff[:10]}: {count} messaggi ({providers_str}). Temi: {topics}"

    # Salva in weekly_summaries (riusa tabella esistente)
    with _db_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS weekly_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL, week_start TEXT NOT NULL, week_end TEXT NOT NULL,
                summary TEXT NOT NULL DEFAULT '', stats TEXT NOT NULL DEFAULT '{}'
            )
        """)
        stats = {"type": "archive", "chat_count": count, "by_provider": by_provider}
        conn.execute(
            "INSERT INTO weekly_summaries (ts, week_start, week_end, summary, stats) VALUES (?, ?, ?, ?, ?)",
            (time.strftime("%Y-%m-%dT%H:%M:%S"), oldest[:10], cutoff[:10],
             summary, json.dumps(stats, ensure_ascii=False))
        )

    return summary


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


def prune_stale_entities(days=60):
    """Elimina entità con freq=1 e last_seen più vecchio di N giorni (falsi positivi)."""
    cutoff = time.strftime("%Y-%m-%dT%H:%M:%S",
                           time.localtime(time.time() - days * 86400))
    with _db_conn() as conn:
        cur = conn.execute(
            "DELETE FROM entities WHERE frequency = 1 AND last_seen < ?",
            (cutoff,))
        return cur.rowcount


def cleanup_orphan_relations():
    """Elimina relazioni che puntano a entità cancellate."""
    with _db_conn() as conn:
        cur = conn.execute("""
            DELETE FROM relations
            WHERE entity_a NOT IN (SELECT id FROM entities)
               OR entity_b NOT IN (SELECT id FROM entities)
        """)
        return cur.rowcount


def compute_entity_stats():
    """Profilo statistico Knowledge Graph: top entities, distribuzione tipo, trend temporali."""
    with _db_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
        total_relations = conn.execute("SELECT COUNT(*) FROM relations").fetchone()[0]

        by_type = {}
        for row in conn.execute(
            "SELECT type, COUNT(*) as cnt FROM entities GROUP BY type ORDER BY cnt DESC"
        ).fetchall():
            by_type[row["type"]] = row["cnt"]

        top_entities = conn.execute(
            "SELECT name, type, frequency FROM entities ORDER BY frequency DESC LIMIT 10"
        ).fetchall()

        by_month = {}
        for row in conn.execute(
            "SELECT substr(first_seen, 1, 7) as month, COUNT(*) as cnt FROM entities GROUP BY month ORDER BY month"
        ).fetchall():
            by_month[row["month"]] = row["cnt"]

        return {
            "total_entities": total,
            "total_relations": total_relations,
            "by_type": by_type,
            "top_10": [(r["name"], r["type"], r["frequency"]) for r in top_entities],
            "new_by_month": by_month,
        }


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

    # 1. Summary prima di archiviare (preserva contesto)
    summary = summarize_before_archive(90)
    if summary:
        print(f"[Self-evolve] Archive summary ({len(summary)} chars): {summary[:100]}...")

    # 2. Archivia chat > 90 giorni
    archived = archive_old_chats(90)
    print(f"[Self-evolve] Chat archiviate: {archived}")

    # 3. Pulisci usage > 180 giorni
    cleaned = cleanup_old_usage(180)
    print(f"[Self-evolve] Usage eliminati: {cleaned}")

    # 4. Potatura entità stale (freq=1, >60gg)
    pruned = prune_stale_entities(60)
    print(f"[Self-evolve] Entità potate (freq=1, >60gg): {pruned}")

    # 5. Cleanup relazioni orfane
    orphans = cleanup_orphan_relations()
    print(f"[Self-evolve] Relazioni orfane rimosse: {orphans}")

    # 6. Stats chat
    stats = compute_stats()
    print(f"[Self-evolve] Chat: {stats['total_active']} attivi, {stats['total_archived']} archiviati")
    for p, c in stats["by_provider"].items():
        print(f"  {p}: {c} msg")

    # 7. Stats Knowledge Graph
    kg = compute_entity_stats()
    print(f"[Self-evolve] KG: {kg['total_entities']} entità, {kg['total_relations']} relazioni")
    for t, c in kg["by_type"].items():
        print(f"  {t}: {c}")
    if kg["top_10"]:
        print(f"[Self-evolve] Top entities:")
        for name, etype, freq in kg["top_10"]:
            print(f"  {name} ({etype}) freq={freq}")

    print(f"[Self-evolve] Completato")


if __name__ == "__main__":
    main()
