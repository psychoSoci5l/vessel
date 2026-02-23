#!/usr/bin/env python3.13
"""Routine Buonanotte — Fase 19B.
Cron serale: invia su Telegram un riepilogo di domani (calendario + task pending).
Schedule: 0 22 * * *  python3.13 ~/scripts/goodnight.py
"""
import json
import os
import subprocess
import urllib.request
from datetime import datetime
from pathlib import Path

# ─── Config ──────────────────────────────────────────────────────────────────
NANOBOT_DIR = Path.home() / ".nanobot"
GOOGLE_PYTHON = Path.home() / ".local" / "share" / "google-workspace-mcp" / "bin" / "python"
GOOGLE_HELPER = Path.home() / "scripts" / "google_helper.py"


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
        print("[Goodnight] Telegram non configurato")
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
        print(f"[Goodnight] Telegram error: {e}")
        return False


# ─── Google Helper subprocess ────────────────────────────────────────────────
def _call_google(args: list) -> str | None:
    if not GOOGLE_PYTHON.exists() or not GOOGLE_HELPER.exists():
        return None
    try:
        result = subprocess.run(
            [str(GOOGLE_PYTHON), str(GOOGLE_HELPER)] + args,
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        return None
    except Exception:
        return None


# ─── Buonanotte ──────────────────────────────────────────────────────────────
def build_goodnight_message() -> str:
    """Costruisce il messaggio serale con calendario domani + task pending."""
    sections = []

    # 1. Calendario domani
    output = _call_google(["calendar", "tomorrow", "--json"])
    if output:
        try:
            data = json.loads(output)
            events = data.get("events", [])
            if events:
                lines = []
                for e in events:
                    time_str = e.get("time", "")
                    summary = e.get("summary", "")
                    loc = f" @ {e['location']}" if e.get("location") else ""
                    lines.append(f"  {time_str} — {summary}{loc}")
                sections.append(f"<b>Domani ({len(events)} eventi):</b>\n" + "\n".join(lines))
            else:
                sections.append("Domani: nessun evento in calendario.")
        except json.JSONDecodeError:
            pass

    # 2. Task pending
    output = _call_google(["tasks", "list"])
    if output:
        today = datetime.now().strftime("%Y-%m-%d")
        pending = []
        for line in output.splitlines():
            line = line.strip()
            if line.startswith("- "):
                task_text = line[2:]
                if "(ID:" in task_text:
                    task_text = task_text[:task_text.index("(ID:")].strip()
                pending.append(f"  {task_text}")

        if pending:
            sections.append(f"<b>Task pending ({len(pending)}):</b>\n" + "\n".join(pending[:8]))
            if len(pending) > 8:
                sections[-1] += f"\n  ... e altri {len(pending) - 8}"

    if not sections:
        return ""

    return "Buonanotte Filippo!\n\n" + "\n\n".join(sections) + "\n\nBuon riposo!"


def get_mood_counter() -> dict:
    """Legge il contatore mood giornaliero dal backend (HAPPY/ALERT/ERROR)."""
    try:
        req = urllib.request.Request("http://127.0.0.1:8090/api/tamagotchi/mood")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"[Goodnight] Mood fetch error: {e}")
        return {}

def set_tamagotchi_state(state: str, mood: dict | None = None):
    """Imposta lo stato del tamagotchi ESP32 via REST locale.
    Se mood è fornito, viene incluso nel payload (es. {"happy":5,"alert":2,"error":1}).
    """
    try:
        url  = "http://127.0.0.1:8090/api/tamagotchi/state"
        body: dict = {"state": state}
        if mood:
            body["mood"] = mood
        data = json.dumps(body).encode("utf-8")
        req  = urllib.request.Request(url, data=data,
                                      headers={"Content-Type": "application/json"},
                                      method="POST")
        urllib.request.urlopen(req, timeout=5)
        print(f"[Goodnight] Tamagotchi → {state}" + (f" mood={mood}" if mood else ""))
    except Exception as e:
        print(f"[Goodnight] Tamagotchi error: {e}")


def main():
    now = datetime.now()
    print(f"[Goodnight] {now.strftime('%Y-%m-%d %H:%M')}")

    msg = build_goodnight_message()
    if not msg:
        print("[Goodnight] Niente da notificare")
        return

    if telegram_send(msg):
        print(f"[Goodnight] Inviato ({len(msg)} chars)")
    else:
        print("[Goodnight] Invio fallito")

    mood = get_mood_counter()
    set_tamagotchi_state("SLEEPING", mood=mood if mood else None)


if __name__ == "__main__":
    main()
