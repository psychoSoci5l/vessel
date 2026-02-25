# ─── Entity Extraction (Fase 17A — auto-popola Knowledge Graph) ──────────────

# Pattern per estrazione entità leggera (regex, zero costo API)
_ENTITY_TECH = {
    "python", "javascript", "typescript", "rust", "go", "java", "c++", "c#",
    "ruby", "php", "swift", "kotlin", "scala", "haskell", "elixir", "lua",
    "cobol", "sql", "html", "css", "bash", "powershell", "docker", "kubernetes",
    "react", "vue", "angular", "svelte", "fastapi", "flask", "django", "express",
    "node", "nodejs", "deno", "bun", "ollama", "pytorch", "tensorflow",
    "raspberry pi", "arduino", "linux", "debian", "ubuntu", "windows", "macos",
    "git", "github", "gitlab", "sqlite", "postgres", "postgresql", "mongodb",
    "redis", "nginx", "anthropic", "openai", "gemma", "llama", "mistral",
    "deepseek", "qwen", "claude", "gpt", "telegram", "discord", "whatsapp",
}

# Città/paesi comuni (espandibile)
_ENTITY_PLACES = {
    "milano", "roma", "napoli", "torino", "firenze", "bologna", "venezia",
    "palermo", "genova", "bari", "catania", "verona", "padova", "trieste",
    "brescia", "bergamo", "modena", "parma", "como", "monza", "pavia",
    "italia", "germany", "france", "spain", "uk", "usa", "japan", "china",
    "london", "paris", "berlin", "new york", "tokyo", "amsterdam", "barcelona",
    "san francisco", "los angeles", "chicago", "seattle", "singapore",
}

# Regex per nomi propri: 2+ parole capitalizzate consecutive (pattern italiano/inglese)
_RE_PROPER_NAMES = re.compile(
    r'\b([A-Z\u00C0-\u00DC][a-z\u00E0-\u00FC]{2,}(?:\s+[A-Z\u00C0-\u00DC][a-z\u00E0-\u00FC]{2,})+)\b'
)

# Parole da ignorare come nomi propri (falsi positivi comuni)
_NAME_STOPWORDS = {
    "Come Posso", "Ciao Come", "Buon Giorno", "Buona Sera", "Per Favore",
    "Per Esempio", "Grazie Mille", "Che Cosa", "Non Posso", "Come Stai",
    "Buona Notte", "Ecco Come", "Vessel Dashboard", "Knowledge Graph",
    "Remote Code", "Chat Mode", "Home View", "Full Text", "Context Pruning",
    "Query String", "Rate Limit", "System Prompt",
}


def extract_entities(user_msg: str, assistant_msg: str) -> list[dict]:
    """Estrae entità leggere da coppia messaggio utente + risposta.
    Ritorna lista di dict: [{"type": "person|tech|place", "name": "..."}]
    Pensata per essere veloce e con pochi falsi positivi."""
    entities = []
    combined = user_msg + " " + assistant_msg
    combined_lower = combined.lower()
    seen = set()

    # 1) Tech keywords (match esatto case-insensitive)
    for tech in _ENTITY_TECH:
        if tech in combined_lower:
            # Verifica word boundary approssimativo
            idx = combined_lower.find(tech)
            before = combined_lower[idx - 1] if idx > 0 else " "
            after = combined_lower[idx + len(tech)] if idx + len(tech) < len(combined_lower) else " "
            if not before.isalnum() and not after.isalnum():
                key = ("tech", tech)
                if key not in seen:
                    seen.add(key)
                    entities.append({"type": "tech", "name": tech})

    # 2) Luoghi (match case-insensitive)
    for place in _ENTITY_PLACES:
        if place in combined_lower:
            idx = combined_lower.find(place)
            before = combined_lower[idx - 1] if idx > 0 else " "
            after = combined_lower[idx + len(place)] if idx + len(place) < len(combined_lower) else " "
            if not before.isalnum() and not after.isalnum():
                key = ("place", place)
                if key not in seen:
                    seen.add(key)
                    entities.append({"type": "place", "name": place.title()})

    # 3) Nomi propri (regex: 2+ parole capitalizzate, solo dal messaggio utente per ridurre rumore)
    for match in _RE_PROPER_NAMES.finditer(user_msg):
        name = match.group(1).strip()
        if name in _NAME_STOPWORDS:
            continue
        if len(name) < 5 or len(name) > 50:
            continue
        key = ("person", name.lower())
        if key not in seen:
            seen.add(key)
            entities.append({"type": "person", "name": name})

    return entities


def _bg_extract_and_store(user_msg: str, assistant_msg: str):
    """Background: estrae entità e le salva nel KG. Fire-and-forget."""
    try:
        entities = extract_entities(user_msg, assistant_msg)
        for ent in entities:
            db_upsert_entity(ent["type"], ent["name"])
    except Exception as e:
        print(f"[KG] Entity extraction error: {e}")


# ─── Memory Block (Fase 18 — KG → system prompt) ─────────────────────────────

_memory_block_cache: dict = {"text": "", "ts": 0}
MEMORY_BLOCK_TTL = 60  # refresh ogni 60s (non ad ogni messaggio)

def _build_memory_block() -> str:
    """Costruisce blocco memoria dal Knowledge Graph. Zero API, pura query SQLite."""
    now = time.time()
    if now - _memory_block_cache["ts"] < MEMORY_BLOCK_TTL and _memory_block_cache["text"]:
        return _memory_block_cache["text"]
    try:
        entities = db_get_entities(limit=30)
    except Exception:
        return _memory_block_cache.get("text", "")
    if not entities:
        return ""
    tech = [e["name"] for e in entities if e["type"] == "tech"][:8]
    people = [e["name"] for e in entities if e["type"] == "person"][:5]
    places = [e["name"] for e in entities if e["type"] == "place"][:5]
    if not tech and not people and not places:
        return ""
    lines = ["## Memoria persistente (dal Knowledge Graph)"]
    if tech:
        lines.append(f"- Interessi tech dell'utente: {', '.join(tech)}")
    if people:
        lines.append(f"- Persone menzionate: {', '.join(people)}")
    if places:
        lines.append(f"- Luoghi citati: {', '.join(places)}")
    block = "\n".join(lines)
    _memory_block_cache["text"] = block
    _memory_block_cache["ts"] = now
    return block


# ─── Weekly Summary Block (Fase 19A — Ollama summary → system prompt) ────────

_weekly_summary_cache: dict = {"text": "", "ts": 0}
WEEKLY_SUMMARY_TTL = 3600  # refresh ogni ora (cambia solo 1x/settimana)

def _build_weekly_summary_block() -> str:
    """Inietta l'ultimo riassunto settimanale nel system prompt. Cache 1h."""
    now = time.time()
    if now - _weekly_summary_cache["ts"] < WEEKLY_SUMMARY_TTL and _weekly_summary_cache["text"]:
        return _weekly_summary_cache["text"]
    try:
        ws = db_get_latest_weekly_summary()
    except Exception:
        return _weekly_summary_cache.get("text", "")
    if not ws or not ws["summary"]:
        return ""
    block = f"## Riassunto settimanale ({ws['week_start'][:10]} — {ws['week_end'][:10]})\n{ws['summary']}"
    _weekly_summary_cache["text"] = block
    _weekly_summary_cache["ts"] = now
    return block


# ─── Topic Recall (Fase 18B — RAG leggero su SQLite) ────────────────────────
TOPIC_RECALL_FREQ_THRESHOLD = 5     # solo entità menzionate >= 5 volte
TOPIC_RECALL_MAX_SNIPPETS = 2       # max 2 snippet per turno
TOPIC_RECALL_MAX_TOKENS = 300       # budget token massimo per recall
TOPIC_RECALL_SKIP_PROVIDERS = {"ollama"}  # provider con budget troppo stretto

def _inject_topic_recall(user_message: str, provider_id: str) -> str:
    """RAG leggero: estrae entità dal messaggio, cerca chat passate, ritorna contesto episodico.
    Zero API — tutto regex + SQLite LIKE. Skip su Ollama Pi (budget 3K troppo stretto)."""
    if provider_id in TOPIC_RECALL_SKIP_PROVIDERS:
        return ""
    # Estrai entità dal messaggio corrente (solo user, no assistant)
    entities = extract_entities(user_message, "")
    if not entities:
        return ""
    # Filtra per frequenza minima nel KG
    all_kg = db_get_entities(limit=200)
    kg_map = {e["name"].lower(): e for e in all_kg}
    relevant = []
    for ent in entities:
        kg_entry = kg_map.get(ent["name"].lower())
        if kg_entry and kg_entry["frequency"] >= TOPIC_RECALL_FREQ_THRESHOLD:
            relevant.append(ent["name"])
    if not relevant:
        return ""
    # Cerca snippet cross-channel per le entità più rilevanti
    snippets = []
    token_used = 0
    for keyword in relevant[:3]:  # max 3 keyword da cercare
        results = db_search_chat(keyword=keyword, limit=5)
        for r in results:
            if r["role"] != "assistant":
                continue
            text = r["content"][:200].strip()
            if not text or len(text) < 20:
                continue
            cost = estimate_tokens(text)
            if token_used + cost > TOPIC_RECALL_MAX_TOKENS:
                break
            snippets.append(f"[{r['ts'][:10]}] {text}")
            token_used += cost
            if len(snippets) >= TOPIC_RECALL_MAX_SNIPPETS:
                break
        if len(snippets) >= TOPIC_RECALL_MAX_SNIPPETS:
            break
    if not snippets:
        return ""
    block = "## Contesto da conversazioni passate\n" + "\n".join(f"- {s}" for s in snippets)
    return block


# ─── Context Pruning (Fase 16B) ───────────────────────────────────────────────
CONTEXT_BUDGETS = {
    "anthropic":        6000,
    "openrouter":       8000,
    "ollama":           3000,
    "ollama_pc_coder":  6000,
    "ollama_pc_deep":   6000,
    "brain":           12000,
}

def estimate_tokens(text: str) -> int:
    """Stima approssimativa token: ~3.5 char/token (compromesso it/en)."""
    return max(1, int(len(text) / 3.5))

def build_context(chat_history: list, provider_id: str, system_prompt: str) -> list:
    """Seleziona messaggi recenti fino a riempire il budget token del provider."""
    budget = CONTEXT_BUDGETS.get(provider_id, 4000)
    remaining = budget - estimate_tokens(system_prompt)
    selected = []
    for msg in reversed(chat_history):
        cost = estimate_tokens(msg["content"]) + 4
        if remaining - cost < 0 and len(selected) >= 4:
            break
        remaining -= cost
        selected.insert(0, msg)
    if len(selected) < len(chat_history):
        used = budget - remaining
        print(f"[Context] {provider_id}: {len(selected)}/{len(chat_history)} msg, ~{used}/{budget} tok")
    return selected
