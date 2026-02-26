# ─── Token Usage ─────────────────────────────────────────────────────────────
USAGE_LOG = Path.home() / ".nanobot" / "usage_dashboard.jsonl"
ADMIN_KEY_FILE = Path.home() / ".nanobot" / "admin_api_key"

def log_token_usage(input_tokens: int, output_tokens: int, model: str,
                    provider: str = "anthropic", response_time_ms: int = 0):
    """Logga utilizzo token in SQLite."""
    db_log_usage(input_tokens, output_tokens, model, provider, response_time_ms)

def get_token_stats() -> dict:
    stats = {"today_input": 0, "today_output": 0, "total_calls": 0,
             "last_model": "N/A", "log_lines": [], "source": "local"}
    today = time.strftime("%Y-%m-%d")
    # 1) Prova Admin API se la chiave esiste
    if ADMIN_KEY_FILE.exists():
        admin_key = ADMIN_KEY_FILE.read_text().strip()
        if admin_key:
            try:

                now = time.strftime("%Y-%m-%dT00:00:00Z")
                end = time.strftime("%Y-%m-%dT23:59:59Z")
                url = (f"https://api.anthropic.com/v1/organizations/usage_report/messages?"
                       f"starting_at={now}&ending_at={end}&bucket_width=1d&group_by[]=model")
                req = urllib.request.Request(url, headers={
                    "anthropic-version": "2023-06-01",
                    "x-api-key": admin_key,
                })
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read())
                    for bucket in data.get("data", []):
                        stats["today_input"]  += bucket.get("input_tokens", 0) + bucket.get("input_cached_tokens", 0)
                        stats["today_output"] += bucket.get("output_tokens", 0)
                        stats["total_calls"]  += bucket.get("request_count", 0)
                        if bucket.get("model"):
                            stats["last_model"] = bucket["model"]
                    stats["source"] = "api"
                    stats["log_lines"] = [f"Dati da Anthropic Admin API — {today}"]
                    return stats
            except Exception as e:
                stats["log_lines"].append(f"Admin API fallita: {str(e)[:80]}")
    # 2) Fallback: log locale SQLite
    db_stats = db_get_token_stats()
    stats["today_input"] = db_stats["today_input"]
    stats["today_output"] = db_stats["today_output"]
    stats["total_calls"] = db_stats["total_calls"]
    if db_stats["last_model"] != "N/A":
        stats["last_model"] = db_stats["last_model"]
    stats["log_lines"] = db_stats["log_lines"]
    if stats["total_calls"] == 0:
        stats["log_lines"].append("// nessuna chiamata API oggi")
        # Leggo config nanobot per mostrare almeno il modello
        cfg = _get_config("config.json")
        raw = cfg.get("agents", {}).get("defaults", {}).get("model", "N/A")
        stats["last_model"] = raw.split("/")[-1] if "/" in raw else raw
    return stats

def _resolve_model(raw: str) -> str:
    """Converte 'anthropic/claude-haiku-4-5' → 'claude-haiku-4-5-20251001' per l'API."""
    MODEL_MAP = {
        "claude-haiku-4-5": "claude-haiku-4-5-20251001",
        "claude-sonnet-4-5": "claude-sonnet-4-5-20250514",
    }
    name = raw.split("/")[-1] if "/" in raw else raw
    return MODEL_MAP.get(name, name)

def _provider_defaults(provider_id: str) -> tuple:
    """Ritorna (model, system_prompt) di default per un provider_id."""
    if provider_id == "anthropic":
        return ANTHROPIC_MODEL, ANTHROPIC_SYSTEM
    if provider_id == "openrouter":
        return OPENROUTER_MODEL, OPENROUTER_SYSTEM
    if provider_id == "ollama":
        return OLLAMA_MODEL, OLLAMA_SYSTEM
    if provider_id == "ollama_pc":
        return OLLAMA_PC_MODEL, OLLAMA_PC_SYSTEM
    if provider_id == "brain":
        return BRAIN_MODEL, BRAIN_SYSTEM
    return OLLAMA_MODEL, OLLAMA_SYSTEM

# ─── Tamagotchi helper (REST locale, evita import circolari) ──────────────────
def _set_tamagotchi_local(state: str):
    """Imposta stato tamagotchi via REST locale (non importa routes)."""
    try:
        data = json.dumps({"state": state}).encode("utf-8")
        req = urllib.request.Request(
            "http://127.0.0.1:8090/api/tamagotchi/state",
            data=data, headers={"Content-Type": "application/json"}, method="POST"
        )
        urllib.request.urlopen(req, timeout=3)
    except Exception:
        pass
