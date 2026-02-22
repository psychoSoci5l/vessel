#!/usr/bin/env python3.13
"""Task Reminder — Fase 19B.
Cron ogni 15 min (ore 7-22): notifica Telegram per eventi calendario imminenti
e digest mattutino dei task pending.
Schedule: */15 7-22 * * *  python3.13 ~/scripts/task_reminder.py

Chiama google_helper.py via subprocess (stessa strategia di briefing.py)
per evitare dipendenza diretta dalle librerie Google.
"""
import json
import os
import subprocess
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

# ─── Config ──────────────────────────────────────────────────────────────────
NANOBOT_DIR = Path.home() / ".nanobot"
SENT_FILE = NANOBOT_DIR / "reminders_sent.json"
GOOGLE_PYTHON = Path.home() / ".local" / "share" / "google-workspace-mcp" / "bin" / "python"
GOOGLE_HELPER = Path.home() / "scripts" / "google_helper.py"
REMINDER_MINUTES = 20  # notifica se evento entro N minuti
MORNING_HOUR = 7       # digest tasks alla prima esecuzione dopo quest'ora


# ─── Telegram ────────────────────────────────────────────────────────────────
def _load_telegram_config():
    tg_path = NANOBOT_DIR / "telegram.json"
    if tg_path.exists():
        cfg = json.loads(tg_path.read_text())
        return cfg.get("token", ""), str(cfg.get("chat_id", ""))
    return os.environ.get("TELEGRAM_TOKEN", ""), os.environ.get("TELEGRAM_CHAT_ID", "")


def telegram_send(text: str) -> bool:
    token, chat_id = _load_telegram_config()
    if not token or not chat_id:
        print("[Reminder] Telegram non configurato")
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = json.dumps({
            "chat_id": chat_id,
            "text": text[:4096],
            "parse_mode": "HTML",
        }).encode("utf-8")
        req = urllib.request.Request(url, data=data,
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception as e:
        print(f"[Reminder] Telegram error: {e}")
        return False


# ─── Dedup ───────────────────────────────────────────────────────────────────
def _load_sent() -> dict:
    if SENT_FILE.exists():
        try:
            data = json.loads(SENT_FILE.read_text())
            cutoff = (datetime.now() - timedelta(days=2)).isoformat()
            return {k: v for k, v in data.items() if v > cutoff}
        except Exception:
            return {}
    return {}


def _save_sent(sent: dict):
    SENT_FILE.write_text(json.dumps(sent, indent=2))


# ─── Google Helper subprocess ────────────────────────────────────────────────
def _call_google(args: list) -> str | None:
    """Chiama google_helper.py via subprocess col Python del venv Google."""
    if not GOOGLE_PYTHON.exists() or not GOOGLE_HELPER.exists():
        print(f"[Reminder] Google helper non trovato")
        return None
    try:
        result = subprocess.run(
            [str(GOOGLE_PYTHON), str(GOOGLE_HELPER)] + args,
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        if result.stderr.strip():
            print(f"[Reminder] google_helper stderr: {result.stderr[:200]}")
        return None
    except subprocess.TimeoutExpired:
        print("[Reminder] google_helper timeout")
        return None
    except Exception as e:
        print(f"[Reminder] google_helper error: {e}")
        return None


# ─── Calendar Reminders ──────────────────────────────────────────────────────
def check_calendar_events(sent: dict) -> int:
    """Controlla eventi imminenti e notifica via Telegram."""
    now = datetime.now()

    # Fetch eventi di oggi in formato JSON
    output = _call_google(["calendar", "today", "--json"])
    if not output:
        return 0

    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return 0

    events = data.get("events", [])
    notified = 0

    for event in events:
        start_raw = event.get("start", "")
        summary = event.get("summary", "(senza titolo)")

        if not start_raw or "T" not in start_raw:
            continue  # skip eventi tutto il giorno

        # Parse orario evento
        try:
            start_str = start_raw[:19]
            event_time = datetime.fromisoformat(start_str)
        except Exception:
            continue

        # Solo eventi che iniziano tra 0 e REMINDER_MINUTES minuti
        diff_minutes = (event_time - now).total_seconds() / 60
        if diff_minutes < 0 or diff_minutes > REMINDER_MINUTES:
            continue

        # Dedup
        dedup_key = f"cal_{summary}_{now.strftime('%Y-%m-%d')}_{event.get('time', '')}"
        if dedup_key in sent:
            continue

        minutes_left = int(diff_minutes)
        location = event.get("location", "")
        loc_str = f"\n{location}" if location else ""

        msg = f"Tra {minutes_left} min: <b>{summary}</b>{loc_str}"
        if telegram_send(msg):
            sent[dedup_key] = now.isoformat()
            notified += 1
            print(f"[Reminder] Notificato: {summary} (tra {minutes_left} min)")

    return notified


# ─── Tasks Daily Digest ──────────────────────────────────────────────────────
def check_tasks_digest(sent: dict) -> bool:
    """Invia digest dei task pending una volta al giorno (mattina)."""
    today = datetime.now().strftime("%Y-%m-%d")
    dedup_key = f"tasks_digest_{today}"
    if dedup_key in sent:
        return False

    now = datetime.now()
    if now.hour > MORNING_HOUR + 1:
        return False

    # Chiama google_helper tasks list (output testuale, parse semplice)
    output = _call_google(["tasks", "list"])
    if not output:
        return False

    # Parse output testuale: "  - titolo [scad: 2026-02-22] (ID: xxx)"
    pending = []
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("- "):
            task_text = line[2:]
            # Estrai titolo (prima di ID)
            if "(ID:" in task_text:
                task_text = task_text[:task_text.index("(ID:")].strip()
            # Check scadenza
            due_info = ""
            if "[scad:" in task_text:
                due_start = task_text.index("[scad:")
                due_str = task_text[due_start+6:due_start+16].strip().rstrip("]")
                task_name = task_text[:due_start].strip()
                if due_str <= today:
                    due_info = f" (scad: {due_str})" if due_str < today else ""
                    pending.append(f"- {task_name}{due_info}")
            else:
                # Task senza scadenza
                pending.append(f"- {task_text}")

    if not pending:
        return False

    msg = f"<b>Task pending ({len(pending)}):</b>\n" + "\n".join(pending[:10])
    if len(pending) > 10:
        msg += f"\n... e altri {len(pending) - 10}"

    if telegram_send(msg):
        sent[dedup_key] = now.isoformat()
        print(f"[Reminder] Task digest inviato: {len(pending)} task")
        return True
    return False


# ─── Main ────────────────────────────────────────────────────────────────────
def main():
    now = datetime.now()
    print(f"[Reminder] {now.strftime('%H:%M')}", end="")

    sent = _load_sent()

    cal_count = check_calendar_events(sent)
    tasks_sent = check_tasks_digest(sent)

    _save_sent(sent)

    if cal_count == 0 and not tasks_sent:
        print(" — niente da notificare")
    else:
        print(f" — {cal_count} eventi, tasks={'si' if tasks_sent else 'no'}")


if __name__ == "__main__":
    main()
