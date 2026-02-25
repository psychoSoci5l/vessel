#!/usr/bin/env python3
"""Deep Learn — Fase 48: Self-Learning via Claude Brain.
Raccoglie dati da vessel.db, li invia al Bridge /brain per analisi con Claude Code CLI.
Claude-mem si attiva automaticamente (hooks) e memorizza insights cross-sessione.

Cron:  0 2 1 * *  python3.13 ~/deep_learn.py  (mensile, 1° del mese alle 2:00)
Manual: python3.13 ~/deep_learn.py
"""
import http.client
import json
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path.home() / ".nanobot" / "vessel.db"


def _load_bridge_config() -> dict:
    cfg_file = Path.home() / ".nanobot" / "bridge.json"
    if cfg_file.exists():
        try:
            return json.loads(cfg_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _db_conn():
    conn = sqlite3.connect(str(DB_PATH), timeout=5)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


# ─── Data Collection ─────────────────────────────────────────────────────────

def gather_learning_data(days: int = 30) -> dict:
    """Raccoglie dati operativi per l'auto-analisi."""
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00")

    with _db_conn() as conn:
        # Chat per provider
        chat_by_provider = {}
        for row in conn.execute(
            "SELECT provider, COUNT(*) as cnt FROM chat_messages WHERE ts >= ? GROUP BY provider",
            (cutoff,),
        ).fetchall():
            chat_by_provider[row["provider"]] = row["cnt"]

        # Chat per canale
        chat_by_channel = {}
        for row in conn.execute(
            "SELECT channel, COUNT(*) as cnt FROM chat_messages WHERE ts >= ? GROUP BY channel",
            (cutoff,),
        ).fetchall():
            chat_by_channel[row["channel"]] = row["cnt"]

        # Sample messaggi utente
        user_msgs = conn.execute(
            "SELECT content FROM chat_messages WHERE ts >= ? AND role='user' ORDER BY ts DESC LIMIT 30",
            (cutoff,),
        ).fetchall()

        # Knowledge Graph
        entity_count = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
        relation_count = conn.execute("SELECT COUNT(*) FROM relations").fetchone()[0]
        top_entities = conn.execute(
            "SELECT name, type, frequency FROM entities ORDER BY frequency DESC LIMIT 15"
        ).fetchall()
        stale_entities = conn.execute(
            "SELECT COUNT(*) FROM entities WHERE frequency = 1 AND last_seen < ?",
            (cutoff,),
        ).fetchone()[0]

        # Token usage
        usage_by_provider = {}
        for row in conn.execute(
            "SELECT provider, SUM(input) as inp, SUM(output) as outp, COUNT(*) as calls, "
            "AVG(response_time_ms) as avg_rt "
            "FROM usage WHERE ts >= ? GROUP BY provider",
            (cutoff,),
        ).fetchall():
            usage_by_provider[row["provider"]] = {
                "input_tokens": row["inp"] or 0,
                "output_tokens": row["outp"] or 0,
                "calls": row["calls"] or 0,
                "avg_response_ms": int(row["avg_rt"] or 0),
            }

        # Weekly summaries
        summaries = conn.execute(
            "SELECT week_start, week_end, summary FROM weekly_summaries ORDER BY id DESC LIMIT 4"
        ).fetchall()

        # Notes
        notes = conn.execute(
            "SELECT content, tags FROM notes ORDER BY id DESC LIMIT 10"
        ).fetchall()

        # Audit log
        audit_actions = {}
        for row in conn.execute(
            "SELECT action, COUNT(*) as cnt FROM audit_log WHERE ts >= ? GROUP BY action ORDER BY cnt DESC LIMIT 10",
            (cutoff,),
        ).fetchall():
            audit_actions[row["action"]] = row["cnt"]

    return {
        "period_days": days,
        "chat_by_provider": chat_by_provider,
        "chat_by_channel": chat_by_channel,
        "user_messages_sample": [r["content"][:150] for r in user_msgs],
        "entity_count": entity_count,
        "relation_count": relation_count,
        "top_entities": [(r["name"], r["type"], r["frequency"]) for r in top_entities],
        "stale_entities": stale_entities,
        "usage_by_provider": usage_by_provider,
        "weekly_summaries": [
            {"period": f"{r['week_start'][:10]}~{r['week_end'][:10]}", "text": r["summary"][:200]}
            for r in summaries
        ],
        "recent_notes": [{"content": r["content"][:120], "tags": r["tags"]} for r in notes],
        "audit_actions": audit_actions,
    }


# ─── Prompt Builder ──────────────────────────────────────────────────────────

def build_analysis_prompt(data: dict) -> str:
    sections = []
    sections.append(f"## Periodo analizzato: ultimi {data['period_days']} giorni")

    if data["chat_by_provider"]:
        prov_str = ", ".join(f"{k}: {v}" for k, v in data["chat_by_provider"].items())
        sections.append(f"Chat per provider: {prov_str}")
    if data["chat_by_channel"]:
        ch_str = ", ".join(f"{k}: {v}" for k, v in data["chat_by_channel"].items())
        sections.append(f"Chat per canale: {ch_str}")

    if data["usage_by_provider"]:
        lines = []
        for p, u in data["usage_by_provider"].items():
            lines.append(
                f"  {p}: {u['calls']} calls, {u['input_tokens'] + u['output_tokens']} tok, avg {u['avg_response_ms']}ms"
            )
        sections.append("Utilizzo API:\n" + "\n".join(lines))

    sections.append(
        f"Knowledge Graph: {data['entity_count']} entita, {data['relation_count']} relazioni, "
        f"{data['stale_entities']} stale (freq=1)"
    )
    if data["top_entities"]:
        ents = ", ".join(f"{n} ({t}, x{f})" for n, t, f in data["top_entities"][:10])
        sections.append(f"Top entita: {ents}")

    if data["weekly_summaries"]:
        for ws in data["weekly_summaries"][:2]:
            sections.append(f"Summary {ws['period']}: {ws['text']}")

    if data["user_messages_sample"]:
        sections.append("Esempi domande utente:")
        for msg in data["user_messages_sample"][:10]:
            sections.append(f"  - {msg}")

    if data["recent_notes"]:
        notes_str = "\n".join(
            f"  - {n['content']}" + (f" [{n['tags']}]" if n["tags"] else "")
            for n in data["recent_notes"][:5]
        )
        sections.append(f"Note recenti:\n{notes_str}")

    if data["audit_actions"]:
        audit_str = ", ".join(f"{k}: {v}" for k, v in data["audit_actions"].items())
        sections.append(f"Azioni audit: {audit_str}")

    data_block = "\n\n".join(sections)

    return (
        "Sei Vessel, assistente personale di Filippo su Raspberry Pi 5.\n"
        "Analizza questi dati operativi del sistema e genera un report strutturato.\n\n"
        f"{data_block}\n\n"
        "---\n\n"
        "Rispondi con un report strutturato in sezioni (in italiano):\n\n"
        "1. **Pattern di utilizzo**: come Filippo usa il sistema, provider preferiti, canali, orari\n"
        "2. **Gap nel Knowledge Graph**: entita stale, relazioni mancanti, suggerimenti per arricchire\n"
        "3. **Trend sistema**: performance, token usage, problemi ricorrenti\n"
        "4. **Suggerimenti operativi**: 3-5 migliorie concrete e actionable\n"
        "5. **Insight personali**: pattern comportamentali, interessi emergenti, temi ricorrenti\n\n"
        "Sii conciso (max 400 parole), concreto, basato sui dati. Non inventare."
    )


# ─── Bridge Communication ────────────────────────────────────────────────────

def call_brain(prompt: str, bridge_url: str, bridge_token: str) -> str:
    """Chiama il bridge /brain e raccoglie la risposta completa."""
    from urllib.parse import urlparse

    parsed = urlparse(bridge_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 8095

    payload = json.dumps({"token": bridge_token, "prompt": prompt}).encode("utf-8")

    conn_class = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    conn = conn_class(host, port, timeout=180)
    conn.request("POST", "/brain", body=payload, headers={"Content-Type": "application/json"})
    resp = conn.getresponse()

    if resp.status == 429:
        raise RuntimeError("Rate limit raggiunto, riprova piu' tardi")
    if resp.status != 200:
        body = resp.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Bridge HTTP {resp.status}: {body[:200]}")

    # Parse NDJSON stream
    full_text = ""
    buf = ""
    while True:
        raw = resp.read(512)
        if not raw:
            break
        buf += raw.decode("utf-8", errors="replace")
        while "\n" in buf:
            line, buf = buf.split("\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                if data.get("type") == "chunk":
                    full_text += data.get("text", "")
                elif data.get("type") == "error":
                    raise RuntimeError(data.get("text", "brain error"))
            except json.JSONDecodeError:
                pass
    conn.close()
    return full_text.strip()


# ─── Output ──────────────────────────────────────────────────────────────────

def save_insights(report: str):
    """Salva il report come nota in vessel.db con tag #deep_learn."""
    with _db_conn() as conn:
        conn.execute(
            "INSERT INTO notes (ts, content, tags) VALUES (?, ?, ?)",
            (time.strftime("%Y-%m-%dT%H:%M:%S"), report[:2000], "#deep_learn #auto"),
        )
    print(f"[DeepLearn] Report salvato in notes ({len(report)} chars)")


def main():
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"[DeepLearn] Avvio: {now}")

    if not DB_PATH.exists():
        print("[DeepLearn] DB non trovato, skip")
        return

    cfg = _load_bridge_config()
    bridge_url = cfg.get("url", "http://localhost:8095")
    bridge_token = cfg.get("token", "")
    if not bridge_token:
        print("[DeepLearn] Bridge token mancante, skip")
        return

    data = gather_learning_data(30)
    total_msgs = sum(data["chat_by_provider"].values())
    print(f"[DeepLearn] Dati raccolti: {total_msgs} chat, {data['entity_count']} entita")

    if total_msgs < 5:
        print("[DeepLearn] Troppo pochi dati, skip")
        return

    prompt = build_analysis_prompt(data)
    print(f"[DeepLearn] Prompt: {len(prompt)} chars, chiamo Bridge /brain...")

    try:
        report = call_brain(prompt, bridge_url, bridge_token)
    except Exception as e:
        print(f"[DeepLearn] Errore Brain: {e}")
        stats_summary = (
            f"DeepLearn {now}: {total_msgs} msg, {data['entity_count']} entita, "
            f"{data['stale_entities']} stale. Brain non disponibile."
        )
        save_insights(stats_summary)
        return

    if report:
        print(f"[DeepLearn] Report ({len(report)} chars): {report[:100]}...")
        save_insights(report)
    else:
        print("[DeepLearn] Report vuoto dal Brain")

    print("[DeepLearn] Completato")


if __name__ == "__main__":
    main()
