# ─── Cleanup ─────────────────────────────────────────────────────────────────
def _cleanup_expired():
    now = time.time()
    for key in list(RATE_LIMITS.keys()):
        RATE_LIMITS[key] = [t for t in RATE_LIMITS[key] if now - t < 600]
        if not RATE_LIMITS[key]:
            del RATE_LIMITS[key]
    for token in list(SESSIONS.keys()):
        if now - SESSIONS[token] > SESSION_TIMEOUT:
            del SESSIONS[token]


def cleanup_old_data():
    """Pulizia periodica dati vecchi (chiamabile da cron weekly)."""
    archived = db_archive_old_chats(90)
    purged_usage = db_archive_old_usage(180)
    purged_events = db_cleanup_old_events(90)
    print(f"[Cleanup] Archiviati {archived} chat, purged {purged_usage} usage, {purged_events} events")
