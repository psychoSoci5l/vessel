#!/usr/bin/env python3
"""
Vessel Backup — backup settimanale su HDD esterno.
Copia vessel.db + config files in /mnt/backup/vessel_backups/
Rotazione: mantiene le ultime 7 copie.
Se l'HDD non e' montato, avvisa via Telegram.

Cron suggerito: 0 4 * * 0  python3.13 ~/backup_db.py

SAFETY: identifica l'HDD per mount point /mnt/backup.
NON scrive MAI sul disco di sistema se l'HDD non e' montato.
"""

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

# ─── Config ──────────────────────────────────────────────────────────────────
BACKUP_MOUNT = Path("/mnt/backup")
BACKUP_DIR = BACKUP_MOUNT / "vessel_backups"
MAX_BACKUPS = 7

NANOBOT_DIR = Path.home() / ".nanobot"
DB_FILE = NANOBOT_DIR / "vessel.db"
DB_WAL = NANOBOT_DIR / "vessel.db-wal"
DB_SHM = NANOBOT_DIR / "vessel.db-shm"
CONFIG_FILES = [
    NANOBOT_DIR / "config.json",
    NANOBOT_DIR / "bridge.json",
    NANOBOT_DIR / "telegram.json",
    NANOBOT_DIR / "openrouter.json",
    NANOBOT_DIR / "ollama_pc.json",
    NANOBOT_DIR / "dashboard_pin.hash",
]
WORKSPACE_DIR = NANOBOT_DIR / "workspace"

# Telegram config
_tg_cfg_path = NANOBOT_DIR / "telegram.json"


def _load_telegram_config() -> tuple:
    """Carica token e chat_id da telegram.json."""
    try:
        if _tg_cfg_path.exists():
            cfg = json.loads(_tg_cfg_path.read_text())
            return cfg.get("token", ""), str(cfg.get("chat_id", ""))
    except Exception:
        pass
    return os.environ.get("TELEGRAM_TOKEN", ""), os.environ.get("TELEGRAM_CHAT_ID", "")


def telegram_send(text: str) -> bool:
    """Invia notifica Telegram."""
    token, chat_id = _load_telegram_config()
    if not token or not chat_id:
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = json.dumps({"chat_id": chat_id, "text": text[:4096]}).encode("utf-8")
        req = urllib.request.Request(url, data=data,
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception as e:
        print(f"[Telegram] send error: {e}")
        return False


def is_external_disk_mounted() -> bool:
    """Verifica che /mnt/backup sia un mount point reale (non il disco di sistema).

    Controlli safety:
    1. Il path deve essere un mount point (non una semplice directory sul disco di sistema)
    2. Il filesystem deve essere diverso da /
    3. Lo spazio totale deve essere > 100GB (discrimina da SSD sistema 91GB)
    """
    if not BACKUP_MOUNT.exists():
        return False

    # Check 1: deve essere un mount point reale
    try:
        result = subprocess.run(
            ["findmnt", "-rno", "SOURCE,FSTYPE", str(BACKUP_MOUNT)],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0 or not result.stdout.strip():
            print(f"[Backup] {BACKUP_MOUNT} non e' un mount point")
            return False
    except Exception as e:
        print(f"[Backup] findmnt error: {e}")
        return False

    # Check 2: device diverso da /
    try:
        stat_backup = os.stat(BACKUP_MOUNT)
        stat_root = os.stat("/")
        if stat_backup.st_dev == stat_root.st_dev:
            print("[Backup] SAFETY: stesso device di / — HDD non montato!")
            return False
    except Exception as e:
        print(f"[Backup] stat error: {e}")
        return False

    # Check 3: spazio > 100GB (HDD 1TB vs SSD 91GB)
    try:
        usage = shutil.disk_usage(BACKUP_MOUNT)
        total_gb = usage.total / (1024**3)
        if total_gb < 100:
            print(f"[Backup] SAFETY: disco troppo piccolo ({total_gb:.0f}GB) — potrebbe essere SSD sistema")
            return False
    except Exception as e:
        print(f"[Backup] disk_usage error: {e}")
        return False

    return True


def run_backup():
    """Esegue il backup."""
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    backup_subdir = BACKUP_DIR / f"backup_{timestamp}"

    print(f"[Backup] Avvio backup → {backup_subdir}")

    # Crea directory backup
    backup_subdir.mkdir(parents=True, exist_ok=True)
    copied = []

    # 1) Backup DB con sqlite3 .backup (consistente, gestisce WAL)
    db_backup_path = backup_subdir / "vessel.db"
    try:
        result = subprocess.run(
            ["sqlite3", str(DB_FILE), f".backup '{db_backup_path}'"],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            copied.append("vessel.db")
            print(f"[Backup] DB copiato ({db_backup_path.stat().st_size / 1024:.0f} KB)")
        else:
            # Fallback: copia diretta
            print(f"[Backup] sqlite3 .backup fallito: {result.stderr[:100]}, uso copia diretta")
            if DB_FILE.exists():
                shutil.copy2(DB_FILE, db_backup_path)
                copied.append("vessel.db (copy)")
    except Exception as e:
        print(f"[Backup] DB backup error: {e}")
        if DB_FILE.exists():
            shutil.copy2(DB_FILE, db_backup_path)
            copied.append("vessel.db (copy)")

    # 2) Config files
    config_dir = backup_subdir / "config"
    config_dir.mkdir(exist_ok=True)
    for cfg in CONFIG_FILES:
        if cfg.exists():
            shutil.copy2(cfg, config_dir / cfg.name)
            copied.append(cfg.name)

    # 3) Workspace (SOUL.md, FRIENDS.md, scripts, memory)
    if WORKSPACE_DIR.exists():
        ws_backup = backup_subdir / "workspace"
        shutil.copytree(WORKSPACE_DIR, ws_backup, dirs_exist_ok=True)
        copied.append("workspace/")

    # 4) Crontab
    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            (backup_subdir / "crontab.txt").write_text(result.stdout)
            copied.append("crontab.txt")
    except Exception:
        pass

    return backup_subdir, copied


def rotate_backups():
    """Mantiene solo le ultime MAX_BACKUPS copie."""
    if not BACKUP_DIR.exists():
        return
    backups = sorted(
        [d for d in BACKUP_DIR.iterdir() if d.is_dir() and d.name.startswith("backup_")],
        key=lambda d: d.name
    )
    while len(backups) > MAX_BACKUPS:
        old = backups.pop(0)
        print(f"[Backup] Rotazione: rimuovo {old.name}")
        shutil.rmtree(old, ignore_errors=True)


def main():
    print(f"[Backup] {time.strftime('%Y-%m-%d %H:%M:%S')} — Avvio backup Vessel")

    # Safety check: HDD esterno montato?
    if not is_external_disk_mounted():
        msg = (
            "⚠️ [Backup] HDD esterno non montato su /mnt/backup!\n"
            "Il backup settimanale NON e' stato eseguito.\n"
            "Collegare l'HDD e riprovare."
        )
        print(msg)
        telegram_send(msg)
        sys.exit(1)

    try:
        backup_path, copied = run_backup()
        rotate_backups()

        # Calcola dimensione totale
        total_size = sum(
            f.stat().st_size for f in backup_path.rglob("*") if f.is_file()
        )
        size_mb = total_size / (1024 * 1024)

        # Report
        usage = shutil.disk_usage(BACKUP_MOUNT)
        free_gb = usage.free / (1024**3)

        msg = (
            f"✅ [Backup] Completato\n"
            f"File: {', '.join(copied)}\n"
            f"Dimensione: {size_mb:.1f} MB\n"
            f"HDD libero: {free_gb:.0f} GB"
        )
        print(msg)
        telegram_send(msg)

    except Exception as e:
        msg = f"❌ [Backup] Errore: {e}"
        print(msg)
        telegram_send(msg)
        sys.exit(1)


if __name__ == "__main__":
    main()
