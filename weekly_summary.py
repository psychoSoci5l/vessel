#!/usr/bin/env python3
"""Weekly Summary — Fase 19A.
Cron job settimanale: raccoglie dati ultimi 7 giorni, chiama Ollama per
generare un riassunto narrativo, salva in SQLite.
Schedule: 0 5 * * 0  python3.13 ~/weekly_summary.py
(dopo self_evolve alle 3:00 e backup_db alle 4:00)
"""
import http.client
import json
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path.home() / ".nanobot" / "vessel.db"
OLLAMA_HOST = "127.0.0.1"
OLLAMA_PORT = 11434
OLLAMA_MODEL = "gemma3:4b"
OLLAMA_TIMEOUT = 180  # generoso per summary lungo


def _db_conn():
    conn = sqlite3.connect(str(DB_PATH), timeout=5)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_table():
    """Crea tabella weekly_summaries se non esiste."""
    with _db_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS weekly_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                week_start TEXT NOT NULL,
                week_end TEXT NOT NULL,
                summary TEXT NOT NULL DEFAULT '',
                stats TEXT NOT NULL DEFAULT '{}'
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_weekly_ts ON weekly_summaries(ts)")


def gather_week_data(week_start: str, week_end: str) -> dict:
    """Raccoglie statistiche degli ultimi 7 giorni dal DB."""
    with _db_conn() as conn:
        # Chat messages
        chat_total = conn.execute(
            "SELECT COUNT(*) FROM chat_messages WHERE ts >= ? AND ts <= ?",
            (week_start, week_end)).fetchone()[0]

        chat_by_channel = {}
        for row in conn.execute(
            "SELECT channel, COUNT(*) as cnt FROM chat_messages WHERE ts >= ? AND ts <= ? GROUP BY channel",
            (week_start, week_end)).fetchall():
            chat_by_channel[row["channel"]] = row["cnt"]

        chat_by_provider = {}
        for row in conn.execute(
            "SELECT provider, COUNT(*) as cnt FROM chat_messages WHERE ts >= ? AND ts <= ? GROUP BY provider",
            (week_start, week_end)).fetchall():
            chat_by_provider[row["provider"]] = row["cnt"]

        # Usage (API calls)
        usage_total = conn.execute(
            "SELECT COUNT(*) FROM usage WHERE ts >= ? AND ts <= ?",
            (week_start, week_end)).fetchone()[0]

        usage_row = conn.execute(
            "SELECT COALESCE(SUM(input), 0) as inp, COALESCE(SUM(output), 0) as out_ FROM usage WHERE ts >= ? AND ts <= ?",
            (week_start, week_end)).fetchone()
        total_input_tok = usage_row["inp"]
        total_output_tok = usage_row["out_"]

        # Entities: new this week
        new_entities = conn.execute(
            "SELECT name, type, frequency FROM entities WHERE first_seen >= ? AND first_seen <= ? ORDER BY frequency DESC LIMIT 10",
            (week_start, week_end)).fetchall()

        # Top entities overall (most active this week = updated last_seen)
        top_entities = conn.execute(
            "SELECT name, type, frequency FROM entities WHERE last_seen >= ? AND last_seen <= ? ORDER BY frequency DESC LIMIT 10",
            (week_start, week_end)).fetchall()

        # User message topics (sample of user messages for topic extraction)
        user_msgs = conn.execute(
            "SELECT content FROM chat_messages WHERE ts >= ? AND ts <= ? AND role = 'user' ORDER BY ts DESC LIMIT 20",
            (week_start, week_end)).fetchall()

        return {
            "chat_total": chat_total,
            "chat_by_channel": chat_by_channel,
            "chat_by_provider": chat_by_provider,
            "usage_calls": usage_total,
            "total_input_tokens": total_input_tok,
            "total_output_tokens": total_output_tok,
            "new_entities": [(r["name"], r["type"]) for r in new_entities],
            "top_entities": [(r["name"], r["type"], r["frequency"]) for r in top_entities],
            "user_messages_sample": [r["content"][:100] for r in user_msgs],
        }


def build_prompt(data: dict, week_start: str, week_end: str) -> str:
    """Costruisce il prompt per Ollama. Compatto, ~400-500 token."""
    lines = [
        f"Periodo: {week_start[:10]} — {week_end[:10]}",
        f"Messaggi totali: {data['chat_total']}",
    ]
    if data["chat_by_channel"]:
        ch = ", ".join(f"{k}: {v}" for k, v in data["chat_by_channel"].items())
        lines.append(f"Per canale: {ch}")
    if data["chat_by_provider"]:
        pr = ", ".join(f"{k}: {v}" for k, v in data["chat_by_provider"].items())
        lines.append(f"Per provider: {pr}")
    lines.append(f"Chiamate API: {data['usage_calls']}, token: {data['total_input_tokens']}in + {data['total_output_tokens']}out")

    if data["top_entities"]:
        ents = ", ".join(f"{n} ({t})" for n, t, _ in data["top_entities"][:7])
        lines.append(f"Argomenti attivi: {ents}")
    if data["new_entities"]:
        new = ", ".join(f"{n} ({t})" for n, t in data["new_entities"][:5])
        lines.append(f"Nuovi argomenti: {new}")

    if data["user_messages_sample"]:
        lines.append("Esempi domande utente:")
        for msg in data["user_messages_sample"][:5]:
            lines.append(f"  - {msg}")

    data_block = "\n".join(lines)

    return f"""Sei Vessel, assistente personale di Filippo su Raspberry Pi.
Scrivi un breve riassunto settimanale (max 150 parole, italiano) basato su questi dati.
Tono informale, evidenzia pattern e temi ricorrenti. Non inventare dati.

{data_block}

Riassunto:"""


def call_ollama(prompt: str) -> str:
    """Chiama Ollama locale (sync, no streaming) e ritorna il testo generato."""
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


def save_summary(week_start: str, week_end: str, summary: str, stats: dict):
    """Salva il riassunto in SQLite."""
    with _db_conn() as conn:
        conn.execute(
            "INSERT INTO weekly_summaries (ts, week_start, week_end, summary, stats) VALUES (?, ?, ?, ?, ?)",
            (time.strftime("%Y-%m-%dT%H:%M:%S"), week_start, week_end,
             summary, json.dumps(stats, ensure_ascii=False))
        )


def main():
    now = datetime.now()
    print(f"[Weekly Summary] Avvio: {now.strftime('%Y-%m-%d %H:%M')}")

    if not DB_PATH.exists():
        print("[Weekly Summary] DB non trovato, skip")
        return

    _ensure_table()

    # Periodo: ultimi 7 giorni
    week_end = now.strftime("%Y-%m-%dT%H:%M:%S")
    week_start = (now - timedelta(days=7)).strftime("%Y-%m-%dT00:00:00")

    # Raccolta dati
    data = gather_week_data(week_start, week_end)
    print(f"[Weekly Summary] Dati: {data['chat_total']} msg, {data['usage_calls']} API calls")

    if data["chat_total"] == 0 and data["usage_calls"] == 0:
        print("[Weekly Summary] Nessuna attività questa settimana, skip")
        return

    # Genera summary con Ollama
    prompt = build_prompt(data, week_start, week_end)
    print(f"[Weekly Summary] Prompt: {len(prompt)} chars, chiamo Ollama ({OLLAMA_MODEL})...")

    try:
        summary = call_ollama(prompt)
    except Exception as e:
        print(f"[Weekly Summary] Errore Ollama: {e}")
        # Fallback: summary statistico senza LLM
        summary = f"Settimana {week_start[:10]}—{week_end[:10]}: {data['chat_total']} messaggi, {data['usage_calls']} chiamate API."
        if data["top_entities"]:
            topics = ", ".join(n for n, _, _ in data["top_entities"][:5])
            summary += f" Argomenti: {topics}."
        print(f"[Weekly Summary] Fallback statistico usato")

    print(f"[Weekly Summary] Summary ({len(summary)} chars): {summary[:100]}...")

    # Stats compact per il record
    stats = {
        "chat_total": data["chat_total"],
        "chat_by_channel": data["chat_by_channel"],
        "usage_calls": data["usage_calls"],
        "tokens": data["total_input_tokens"] + data["total_output_tokens"],
    }

    save_summary(week_start, week_end, summary, stats)
    print(f"[Weekly Summary] Salvato in DB. Completato.")


if __name__ == "__main__":
    main()
