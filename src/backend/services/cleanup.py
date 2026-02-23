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
