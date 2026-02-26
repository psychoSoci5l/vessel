# ─── Claude Bridge (PC Monitoring) ────────────────────────────────────────────
def check_bridge_health() -> dict:
    """Verifica se il Claude Bridge su Windows è raggiungibile."""
    t0 = time.time()
    try:
        req = urllib.request.Request(f"{CLAUDE_BRIDGE_URL}/health")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
            db_log_event("bridge", "ping", status="ok",
                         latency_ms=int((time.time() - t0) * 1000))
            return data
    except Exception:
        db_log_event("bridge", "ping", status="error",
                     latency_ms=int((time.time() - t0) * 1000),
                     error="unreachable")
        return {"status": "offline"}
