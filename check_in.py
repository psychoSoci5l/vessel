#!/usr/bin/env python3.13
"""Check-In Serale — Fase B.
Cron ore 20:00: se non ci sono state chat nelle ultime 4h,
invia un breve messaggio contestuale su Telegram.
Schedule: 0 20 * * *  python3.13 ~/check_in.py
"""
import json
import os
import sqlite3
import subprocess
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

# ─── Config ──────────────────────────────────────────────────────────────────
NANOBOT_DIR = Path.home() / ".nanobot"
DB_PATH = NANOBOT_DIR / "vessel.db"
IDLE_HOURS = 4  # ore di silenzio prima del check-in


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
        print("[CheckIn] Telegram non configurato")
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
        print(f"[CheckIn] Telegram error: {e}")
        return False


# ─── Sigil ────────────────────────────────────────────────────────────────────
def _notify_sigil(state: str, detail: str = "", text: str = ""):
    try:
        payload: dict = {"state": state}
        if detail:
            payload["detail"] = detail
        if text:
            payload["text"] = text
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            "http://127.0.0.1:8090/api/tamagotchi/state",
            data=data, headers={"Content-Type": "application/json"}, method="POST"
        )
        urllib.request.urlopen(req, timeout=3)
    except Exception:
        pass


# ─── Idle check ──────────────────────────────────────────────────────────────
def _has_recent_chat() -> bool:
    """Ritorna True se ci sono state chat nelle ultime IDLE_HOURS ore."""
    if not DB_PATH.exists():
        return False
    cutoff = (datetime.now() - timedelta(hours=IDLE_HOURS)).strftime("%Y-%m-%dT%H:%M:%S")
    try:
        con = sqlite3.connect(str(DB_PATH))
        row = con.execute(
            "SELECT COUNT(*) FROM chat_messages WHERE role='user' AND ts > ?",
            (cutoff,)
        ).fetchone()
        con.close()
        return (row[0] or 0) > 0
    except Exception as e:
        print(f"[CheckIn] DB error: {e}")
        return True  # fallback conservativo: non inviare se non si può verificare


# ─── Context gathering ────────────────────────────────────────────────────────
def _get_open_tasks() -> list:
    """Legge task aperti dalla tabella tracker (SQLite)."""
    if not DB_PATH.exists():
        return []
    try:
        con = sqlite3.connect(str(DB_PATH))
        rows = con.execute(
            "SELECT title, priority FROM tracker WHERE status='open' ORDER BY priority LIMIT 5"
        ).fetchall()
        con.close()
        return [f"{r[1]} — {r[0]}" for r in rows]
    except Exception:
        return []


def _get_pi_temp() -> str:
    """Legge temperatura Pi da vcgencmd."""
    try:
        r = subprocess.run(["vcgencmd", "measure_temp"],
                           capture_output=True, text=True, timeout=3)
        if r.returncode == 0:
            return r.stdout.strip().replace("temp=", "")
    except Exception:
        pass
    return ""


def _get_last_git_commit() -> str:
    """Ritorna info sull'ultimo commit del repo vessel-pi."""
    try:
        r = subprocess.run(
            ["git", "-C", str(Path.home() / "vessel-pi"), "log", "--oneline", "-1"],
            capture_output=True, text=True, timeout=5
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()[:60]
    except Exception:
        pass
    return ""


# ─── Message builder ─────────────────────────────────────────────────────────
def build_checkin_message() -> str:
    parts = ["Ehi, tutto bene? Sono un po' di ore che non mi parli."]

    tasks = _get_open_tasks()
    if tasks:
        parts.append(f"<b>Task aperti ({len(tasks)}):</b>\n" + "\n".join(f"  {t}" for t in tasks))

    temp = _get_pi_temp()
    if temp:
        parts.append(f"Temp Pi: {temp}")

    commit = _get_last_git_commit()
    if commit:
        parts.append(f"Ultimo commit: <code>{commit}</code>")

    return "\n\n".join(parts)


# ─── Main ────────────────────────────────────────────────────────────────────
def main():
    now = datetime.now()
    print(f"[CheckIn] {now.strftime('%Y-%m-%d %H:%M')}")

    if _has_recent_chat():
        print("[CheckIn] Chat recente trovata, niente da fare")
        return

    msg = build_checkin_message()
    if telegram_send(msg):
        _notify_sigil("CURIOUS", detail="Check-in", text="Idle da 4h")
        print(f"[CheckIn] Inviato ({len(msg)} chars)")
    else:
        print("[CheckIn] Invio fallito")


if __name__ == "__main__":
    main()
