# ─── Database SQLite ──────────────────────────────────────────────────────────
DB_PATH = Path.home() / ".nanobot" / "vessel.db"
SCHEMA_VERSION = 1


def _db_conn():
    """Crea connessione SQLite con row_factory dict-like."""
    conn = sqlite3.connect(str(DB_PATH), timeout=5)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Crea tabelle + indici. Migra JSONL se presenti e tabelle vuote."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _db_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);

            CREATE TABLE IF NOT EXISTS usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                input INTEGER NOT NULL DEFAULT 0,
                output INTEGER NOT NULL DEFAULT 0,
                model TEXT NOT NULL DEFAULT '',
                provider TEXT NOT NULL DEFAULT '',
                response_time_ms INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_usage_ts ON usage(ts);

            CREATE TABLE IF NOT EXISTS briefings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                weather TEXT DEFAULT '',
                stories TEXT DEFAULT '[]',
                calendar_today TEXT DEFAULT '[]',
                calendar_tomorrow TEXT DEFAULT '[]',
                text TEXT DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_briefings_ts ON briefings(ts);

            CREATE TABLE IF NOT EXISTS claude_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                prompt TEXT DEFAULT '',
                status TEXT DEFAULT '',
                exit_code INTEGER DEFAULT 0,
                duration_ms INTEGER DEFAULT 0,
                output_preview TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                provider TEXT NOT NULL,
                channel TEXT NOT NULL DEFAULT 'dashboard',
                role TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_chat_pct ON chat_messages(provider, channel, ts);

            CREATE TABLE IF NOT EXISTS chat_messages_archive (
                id INTEGER PRIMARY KEY,
                ts TEXT NOT NULL,
                provider TEXT NOT NULL,
                channel TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                action TEXT NOT NULL,
                actor TEXT DEFAULT '',
                resource TEXT DEFAULT '',
                status TEXT DEFAULT 'ok',
                details TEXT DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(ts);
            CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action);

            CREATE TABLE IF NOT EXISTS entities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                name TEXT NOT NULL UNIQUE,
                description TEXT DEFAULT '',
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                frequency INTEGER DEFAULT 1
            );
            CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(type);

            CREATE TABLE IF NOT EXISTS relations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_a INTEGER NOT NULL,
                entity_b INTEGER NOT NULL,
                relation TEXT NOT NULL,
                frequency INTEGER DEFAULT 1,
                ts TEXT NOT NULL,
                FOREIGN KEY(entity_a) REFERENCES entities(id),
                FOREIGN KEY(entity_b) REFERENCES entities(id)
            );

            CREATE TABLE IF NOT EXISTS weekly_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                week_start TEXT NOT NULL,
                week_end TEXT NOT NULL,
                summary TEXT NOT NULL DEFAULT '',
                stats TEXT NOT NULL DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_weekly_ts ON weekly_summaries(ts);
        """)
        # Schema version
        row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
        if not row:
            conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))

    _migrate_jsonl()
    print(f"[DB] SQLite inizializzato: {DB_PATH}")


def _migrate_jsonl():
    """Importa dati da JSONL esistenti se le tabelle sono vuote. Rinomina in .bak."""
    with _db_conn() as conn:
        # usage_dashboard.jsonl
        usage_jsonl = Path.home() / ".nanobot" / "usage_dashboard.jsonl"
        if usage_jsonl.exists():
            count = conn.execute("SELECT COUNT(*) FROM usage").fetchone()[0]
            if count == 0:
                migrated = 0
                for line in usage_jsonl.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                        conn.execute(
                            "INSERT INTO usage (ts, input, output, model, provider, response_time_ms) VALUES (?, ?, ?, ?, ?, ?)",
                            (d.get("ts", ""), d.get("input", 0), d.get("output", 0),
                             d.get("model", ""), d.get("provider", ""), d.get("response_time_ms", 0))
                        )
                        migrated += 1
                    except Exception:
                        continue
                if migrated > 0:
                    usage_jsonl.rename(usage_jsonl.with_suffix(".jsonl.bak"))
                    print(f"[DB] Migrati {migrated} record usage → SQLite")

        # briefing_log.jsonl
        briefing_jsonl = Path.home() / ".nanobot" / "briefing_log.jsonl"
        if briefing_jsonl.exists():
            count = conn.execute("SELECT COUNT(*) FROM briefings").fetchone()[0]
            if count == 0:
                migrated = 0
                for line in briefing_jsonl.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                        conn.execute(
                            "INSERT INTO briefings (ts, weather, stories, calendar_today, calendar_tomorrow, text) VALUES (?, ?, ?, ?, ?, ?)",
                            (d.get("ts", ""), d.get("weather", ""),
                             json.dumps(d.get("stories", []), ensure_ascii=False),
                             json.dumps(d.get("calendar_today", []), ensure_ascii=False),
                             json.dumps(d.get("calendar_tomorrow", []), ensure_ascii=False),
                             d.get("text", ""))
                        )
                        migrated += 1
                    except Exception:
                        continue
                if migrated > 0:
                    briefing_jsonl.rename(briefing_jsonl.with_suffix(".jsonl.bak"))
                    print(f"[DB] Migrati {migrated} record briefings → SQLite")

        # claude_tasks.jsonl
        tasks_jsonl = Path.home() / ".nanobot" / "claude_tasks.jsonl"
        if tasks_jsonl.exists():
            count = conn.execute("SELECT COUNT(*) FROM claude_tasks").fetchone()[0]
            if count == 0:
                migrated = 0
                for line in tasks_jsonl.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                        conn.execute(
                            "INSERT INTO claude_tasks (ts, prompt, status, exit_code, duration_ms, output_preview) VALUES (?, ?, ?, ?, ?, ?)",
                            (d.get("ts", ""), d.get("prompt", ""), d.get("status", ""),
                             d.get("exit_code", 0), d.get("duration_ms", 0), d.get("output_preview", ""))
                        )
                        migrated += 1
                    except Exception:
                        continue
                if migrated > 0:
                    tasks_jsonl.rename(tasks_jsonl.with_suffix(".jsonl.bak"))
                    print(f"[DB] Migrati {migrated} record claude_tasks → SQLite")


# ─── Usage (token tracking) ──────────────────────────────────────────────────

def db_log_usage(input_tokens: int, output_tokens: int, model: str,
                 provider: str = "anthropic", response_time_ms: int = 0):
    """Logga utilizzo token in SQLite."""
    with _db_conn() as conn:
        conn.execute(
            "INSERT INTO usage (ts, input, output, model, provider, response_time_ms) VALUES (?, ?, ?, ?, ?, ?)",
            (time.strftime("%Y-%m-%dT%H:%M:%S"), input_tokens, output_tokens,
             model, provider, response_time_ms)
        )


def db_get_token_stats() -> dict:
    """Legge statistiche token di oggi da SQLite."""
    stats = {"today_input": 0, "today_output": 0, "total_calls": 0,
             "last_model": "N/A", "log_lines": [], "source": "local"}
    today = time.strftime("%Y-%m-%d")
    with _db_conn() as conn:
        rows = conn.execute(
            "SELECT input, output, model FROM usage WHERE ts LIKE ? ORDER BY ts",
            (today + "%",)
        ).fetchall()
        for r in rows:
            stats["today_input"] += r["input"]
            stats["today_output"] += r["output"]
            stats["total_calls"] += 1
            if r["model"]:
                stats["last_model"] = r["model"]
        # Ultime 8 righe per il widget log
        recent = conn.execute(
            "SELECT ts, input, output, model, provider, response_time_ms FROM usage ORDER BY id DESC LIMIT 8"
        ).fetchall()
        stats["log_lines"] = [
            json.dumps({"ts": r["ts"], "input": r["input"], "output": r["output"],
                        "model": r["model"], "provider": r["provider"],
                        "response_time_ms": r["response_time_ms"]})
            for r in reversed(recent)
        ]
    return stats


def db_get_usage_report(period: str = "day") -> dict:
    """Report utilizzo token aggregato per provider. period: day|week|month."""
    days = {"day": 0, "week": 7, "month": 30}.get(period, 0)
    if days == 0:
        since = time.strftime("%Y-%m-%d")
    else:
        since = time.strftime("%Y-%m-%d", time.localtime(time.time() - days * 86400))
    rows_out = []
    total = {"input": 0, "output": 0, "calls": 0}
    with _db_conn() as conn:
        rows = conn.execute(
            "SELECT provider, SUM(input) AS tok_in, SUM(output) AS tok_out, COUNT(*) AS calls "
            "FROM usage WHERE ts >= ? GROUP BY provider ORDER BY tok_out DESC",
            (since,)
        ).fetchall()
        for r in rows:
            entry = {"provider": r["provider"] or "unknown",
                     "input": r["tok_in"] or 0, "output": r["tok_out"] or 0, "calls": r["calls"] or 0}
            rows_out.append(entry)
            total["input"] += entry["input"]
            total["output"] += entry["output"]
            total["calls"] += entry["calls"]
    return {"rows": rows_out, "total": total, "period": period}


# ─── Briefings ────────────────────────────────────────────────────────────────

def db_get_briefing() -> dict:
    """Legge ultimo briefing da SQLite."""
    data = {"last": None, "next_run": "07:30"}
    with _db_conn() as conn:
        row = conn.execute(
            "SELECT ts, weather, stories, calendar_today, calendar_tomorrow, text FROM briefings ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row:
            data["last"] = {
                "ts": row["ts"], "weather": row["weather"],
                "stories": json.loads(row["stories"]),
                "calendar_today": json.loads(row["calendar_today"]),
                "calendar_tomorrow": json.loads(row["calendar_tomorrow"]),
                "text": row["text"],
            }
    return data


def db_log_briefing(ts: str, weather: str, stories: list,
                    calendar_today: list, calendar_tomorrow: list, text: str):
    """Inserisce un record briefing in SQLite."""
    with _db_conn() as conn:
        conn.execute(
            "INSERT INTO briefings (ts, weather, stories, calendar_today, calendar_tomorrow, text) VALUES (?, ?, ?, ?, ?, ?)",
            (ts, weather, json.dumps(stories, ensure_ascii=False),
             json.dumps(calendar_today, ensure_ascii=False),
             json.dumps(calendar_tomorrow, ensure_ascii=False), text)
        )


# ─── Claude Tasks ─────────────────────────────────────────────────────────────

def db_get_claude_tasks(n: int = 10) -> list:
    """Legge ultimi N task Claude da SQLite."""
    with _db_conn() as conn:
        rows = conn.execute(
            "SELECT ts, prompt, status, exit_code, duration_ms, output_preview FROM claude_tasks ORDER BY id DESC LIMIT ?",
            (n,)
        ).fetchall()
        return [dict(r) for r in reversed(rows)]


def db_log_claude_task(prompt: str, status: str, exit_code: int = 0,
                       duration_ms: int = 0, output_preview: str = ""):
    """Logga un task Claude in SQLite."""
    with _db_conn() as conn:
        conn.execute(
            "INSERT INTO claude_tasks (ts, prompt, status, exit_code, duration_ms, output_preview) VALUES (?, ?, ?, ?, ?, ?)",
            (time.strftime("%Y-%m-%dT%H:%M:%S"), prompt[:200], status,
             exit_code, duration_ms, output_preview[:200])
        )


# ─── Chat Messages (history persistente) ──────────────────────────────────────

def db_save_chat_message(provider: str, channel: str, role: str, content: str):
    """Salva un singolo messaggio chat in SQLite."""
    with _db_conn() as conn:
        conn.execute(
            "INSERT INTO chat_messages (ts, provider, channel, role, content) VALUES (?, ?, ?, ?, ?)",
            (time.strftime("%Y-%m-%dT%H:%M:%S"), provider, channel, role, content)
        )


def db_load_chat_history(provider: str, channel: str = "dashboard", limit: int = 40) -> list:
    """Carica ultimi N messaggi per provider/channel. Ritorna [{"role": ..., "content": ...}]."""
    with _db_conn() as conn:
        rows = conn.execute(
            "SELECT role, content FROM chat_messages WHERE provider = ? AND channel = ? ORDER BY id DESC LIMIT ?",
            (provider, channel, limit)
        ).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def db_clear_chat_history(channel: str = "dashboard"):
    """Cancella tutta la chat history per un channel."""
    with _db_conn() as conn:
        conn.execute("DELETE FROM chat_messages WHERE channel = ?", (channel,))


def db_search_chat(keyword: str = "", provider: str = "", date_from: str = "",
                   date_to: str = "", limit: int = 50) -> list:
    """Ricerca nei messaggi chat per keyword, provider e range date."""
    with _db_conn() as conn:
        query = "SELECT ts, provider, channel, role, content FROM chat_messages WHERE 1=1"
        params = []
        if keyword:
            query += " AND content LIKE ?"
            params.append(f"%{keyword}%")
        if provider:
            query += " AND provider = ?"
            params.append(provider)
        if date_from:
            query += " AND ts >= ?"
            params.append(date_from + "T00:00:00")
        if date_to:
            query += " AND ts <= ?"
            params.append(date_to + "T23:59:59")
        query += " ORDER BY ts DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


# ─── Archivio (self-evolving) ─────────────────────────────────────────────────

def db_archive_old_chats(days: int = 90) -> int:
    """Sposta messaggi chat più vecchi di N giorni nella tabella archive."""
    cutoff = time.strftime("%Y-%m-%dT%H:%M:%S",
                           time.localtime(time.time() - days * 86400))
    with _db_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO chat_messages_archive SELECT * FROM chat_messages WHERE ts < ?",
            (cutoff,))
        cur = conn.execute("DELETE FROM chat_messages WHERE ts < ?", (cutoff,))
        return cur.rowcount


def db_archive_old_usage(days: int = 180) -> int:
    """Elimina record usage più vecchi di N giorni."""
    cutoff = time.strftime("%Y-%m-%dT%H:%M:%S",
                           time.localtime(time.time() - days * 86400))
    with _db_conn() as conn:
        cur = conn.execute("DELETE FROM usage WHERE ts < ?", (cutoff,))
        return cur.rowcount


def db_get_chat_stats() -> dict:
    """Statistiche aggregate sui messaggi chat."""
    with _db_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0]
        archived = conn.execute("SELECT COUNT(*) FROM chat_messages_archive").fetchone()[0]
        by_provider = {}
        for row in conn.execute(
            "SELECT provider, COUNT(*) as cnt FROM chat_messages GROUP BY provider"
        ).fetchall():
            by_provider[row["provider"]] = row["cnt"]
        return {"total": total, "archived": archived, "by_provider": by_provider}


# ─── Audit Log ────────────────────────────────────────────────────────────────

def db_log_audit(action: str, actor: str = "", resource: str = "",
                 status: str = "ok", details: str = ""):
    """Logga un'azione nel registro audit."""
    with _db_conn() as conn:
        conn.execute(
            "INSERT INTO audit_log (ts, action, actor, resource, status, details) VALUES (?, ?, ?, ?, ?, ?)",
            (time.strftime("%Y-%m-%dT%H:%M:%S"), action, actor[:100],
             resource[:200], status, details[:500])
        )


def db_get_audit_log(limit: int = 50, action: str = "") -> list:
    """Legge ultimi N record audit, filtrabile per azione."""
    with _db_conn() as conn:
        if action:
            rows = conn.execute(
                "SELECT ts, action, actor, resource, status, details FROM audit_log WHERE action = ? ORDER BY id DESC LIMIT ?",
                (action, limit)).fetchall()
        else:
            rows = conn.execute(
                "SELECT ts, action, actor, resource, status, details FROM audit_log ORDER BY id DESC LIMIT ?",
                (limit,)).fetchall()
        return [dict(r) for r in rows]


# ─── Knowledge Graph (entities + relations) ───────────────────────────────────

def db_upsert_entity(type: str, name: str, description: str = "") -> int:
    """Inserisce o aggiorna un'entity. Incrementa frequency se esiste. Ritorna id."""
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    with _db_conn() as conn:
        existing = conn.execute("SELECT id FROM entities WHERE name = ?", (name,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE entities SET frequency = frequency + 1, last_seen = ?, description = CASE WHEN ? != '' THEN ? ELSE description END WHERE id = ?",
                (now, description, description, existing["id"]))
            return existing["id"]
        else:
            cur = conn.execute(
                "INSERT INTO entities (type, name, description, first_seen, last_seen) VALUES (?, ?, ?, ?, ?)",
                (type, name, description, now, now))
            return cur.lastrowid


def db_add_relation(entity_a: int, entity_b: int, relation: str) -> int:
    """Aggiunge una relazione. Se esiste già, incrementa frequency."""
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    with _db_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM relations WHERE entity_a = ? AND entity_b = ? AND relation = ?",
            (entity_a, entity_b, relation)).fetchone()
        if existing:
            conn.execute("UPDATE relations SET frequency = frequency + 1, ts = ? WHERE id = ?",
                         (now, existing["id"]))
            return existing["id"]
        else:
            cur = conn.execute(
                "INSERT INTO relations (entity_a, entity_b, relation, ts) VALUES (?, ?, ?, ?)",
                (entity_a, entity_b, relation, now))
            return cur.lastrowid


def db_get_entities(type: str = "", limit: int = 100) -> list:
    """Lista entities, filtrabile per tipo."""
    with _db_conn() as conn:
        if type:
            rows = conn.execute(
                "SELECT * FROM entities WHERE type = ? ORDER BY frequency DESC LIMIT ?",
                (type, limit)).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM entities ORDER BY frequency DESC LIMIT ?",
                (limit,)).fetchall()
        return [dict(r) for r in rows]


def db_delete_entity(entity_id: int) -> bool:
    """Elimina un'entity e tutte le relazioni associate (cascade)."""
    with _db_conn() as conn:
        conn.execute("DELETE FROM relations WHERE entity_a = ? OR entity_b = ?",
                     (entity_id, entity_id))
        cur = conn.execute("DELETE FROM entities WHERE id = ?", (entity_id,))
        return cur.rowcount > 0


def db_get_relations(entity_id: int = 0) -> list:
    """Relazioni di un'entity o tutte. Ritorna con nomi delle entities."""
    with _db_conn() as conn:
        if entity_id:
            rows = conn.execute("""
                SELECT r.*, ea.name as name_a, eb.name as name_b
                FROM relations r
                JOIN entities ea ON r.entity_a = ea.id
                JOIN entities eb ON r.entity_b = eb.id
                WHERE r.entity_a = ? OR r.entity_b = ?
                ORDER BY r.frequency DESC
            """, (entity_id, entity_id)).fetchall()
        else:
            rows = conn.execute("""
                SELECT r.*, ea.name as name_a, eb.name as name_b
                FROM relations r
                JOIN entities ea ON r.entity_a = ea.id
                JOIN entities eb ON r.entity_b = eb.id
                ORDER BY r.frequency DESC LIMIT 100
            """).fetchall()
        return [dict(r) for r in rows]


# ─── Weekly Summaries ────────────────────────────────────────────────────────

def db_save_weekly_summary(week_start: str, week_end: str,
                           summary: str, stats: dict):
    """Salva un riassunto settimanale generato da Ollama."""
    with _db_conn() as conn:
        conn.execute(
            "INSERT INTO weekly_summaries (ts, week_start, week_end, summary, stats) VALUES (?, ?, ?, ?, ?)",
            (time.strftime("%Y-%m-%dT%H:%M:%S"), week_start, week_end,
             summary, json.dumps(stats, ensure_ascii=False))
        )


def db_get_latest_weekly_summary() -> dict | None:
    """Ritorna l'ultimo riassunto settimanale, o None."""
    with _db_conn() as conn:
        row = conn.execute(
            "SELECT ts, week_start, week_end, summary, stats FROM weekly_summaries ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row:
            return {
                "ts": row["ts"], "week_start": row["week_start"],
                "week_end": row["week_end"], "summary": row["summary"],
                "stats": json.loads(row["stats"]),
            }
        return None
