# ─── Background broadcaster ───────────────────────────────────────────────────
async def stats_broadcaster():
    cycle = 0
    while True:
        await asyncio.sleep(5)
        cycle += 1
        if cycle % 60 == 0:
            _cleanup_expired()
        if manager.connections:
            pi = await get_pi_stats()
            tmux = await bg(get_tmux_sessions)
            await manager.broadcast({
                "type": "stats",
                "data": {
                    "pi": pi,
                    "tmux": tmux,
                    "time": time.strftime("%H:%M:%S"),
                }
            })

# ─── Plugin Handler Registration ────────────────────────────────────────────
def _load_plugin_handlers():
    """Carica handler.py dei plugin e li registra nel WS_DISPATCHER."""
    for plugin in PLUGINS:
        plugin_id = plugin["id"]
        handler_path = Path(plugin["_path"]) / "handler.py"
        if not handler_path.exists():
            print(f"[Plugin] {plugin_id}: handler.py non trovato, skip")
            continue
        try:
            code = handler_path.read_text(encoding="utf-8")
            code_hash = hashlib.sha256(code.encode()).hexdigest()[:16]
            print(f"[Plugin] {plugin_id}: handler hash={code_hash}")
            plugin_ns = {"__builtins__": __builtins__, "json": json, "asyncio": asyncio,
                         "time": time, "Path": Path, "bg": bg}
            exec(compile(code, str(handler_path), "exec"), plugin_ns)
            handler_fn = plugin_ns.get("handle")
            if handler_fn is None:
                print(f"[Plugin] {plugin_id}: nessuna funzione handle(), skip")
                continue
            action_name = f"plugin_{plugin_id}"
            async def _safe_handler(ws, msg, ctx, _fn=handler_fn, _pid=plugin_id):
                try:
                    await _fn(ws, msg, ctx)
                except Exception as e:
                    print(f"[Plugin] {_pid}: errore handler: {e}")
                    await ws.send_json({"type": "toast", "text": f"Errore plugin {_pid}: {e}"})
            WS_DISPATCHER[action_name] = _safe_handler
            print(f"[Plugin] {plugin_id}: handler registrato (action={action_name})")
        except Exception as e:
            print(f"[Plugin] {plugin_id}: errore caricamento: {e}")

_load_plugin_handlers()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    token = websocket.cookies.get("vessel_session", "")
    if not _is_authenticated(token):
        await websocket.close(code=4001, reason="Non autenticato")
        return
    await manager.connect(websocket)
    provider_map = {
        "ollama": "ollama", "cloud": "anthropic", "deepseek": "openrouter",
        "pc_coder": "ollama_pc_coder", "pc_deep": "ollama_pc_deep",
        "brain": "brain"
    }
    ctx = {k: db_load_chat_history(pid) for k, pid in provider_map.items()}
    await websocket.send_json({
        "type": "init",
        "data": {
            "pi": await get_pi_stats(),
            "tmux": await bg(get_tmux_sessions),
            "version": get_nanobot_version(),
            "memory": get_memory_preview(),
            "time": time.strftime("%H:%M:%S"),
        }
    })
    await broadcast_tamagotchi("CURIOUS")
    try:
        while True:
            msg = await websocket.receive_json()
            action = msg.get("action")
            handler = WS_DISPATCHER.get(action)
            if handler:
                await handler(websocket, msg, ctx)
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# ─── Auth routes ─────────────────────────────────────────────────────────────
@app.post("/auth/login")
async def auth_login(request: Request):
    ip = request.client.host
    if not _rate_limit(ip, "auth", MAX_AUTH_ATTEMPTS, AUTH_LOCKOUT_SECONDS):
        return JSONResponse({"error": "Troppi tentativi. Riprova tra 5 minuti."}, status_code=429)
    body = await request.json()
    pin = body.get("pin", "")
    if not PIN_FILE.exists():
        if len(pin) != 4 or not pin.isdigit():
            return JSONResponse({"error": "Il PIN deve essere 4 cifre"}, status_code=400)
        _set_pin(pin)
        token = _create_session()
        resp = JSONResponse({"ok": True, "setup": True})
        is_secure = request.url.scheme == "https"
        resp.set_cookie("vessel_session", token, max_age=SESSION_TIMEOUT,
                        httponly=True, samesite="lax", secure=is_secure)
        return resp
    if not _verify_pin(pin):
        db_log_audit("login_fail", actor=ip)
        return JSONResponse({"error": "PIN errato"}, status_code=401)
    RATE_LIMITS.pop(f"{ip}:auth", None)
    token = _create_session()
    db_log_audit("login", actor=ip)
    resp = JSONResponse({"ok": True})
    is_secure = request.url.scheme == "https"
    resp.set_cookie("vessel_session", token, max_age=SESSION_TIMEOUT,
                    httponly=True, samesite="lax", secure=is_secure)
    return resp

@app.post("/auth/logout")
async def auth_logout(request: Request):
    token = request.cookies.get("vessel_session", "")
    if token in SESSIONS:
        del SESSIONS[token]
        _save_sessions()
    db_log_audit("logout", actor=request.client.host)
    resp = JSONResponse({"ok": True})
    is_secure = request.url.scheme == "https"
    resp.delete_cookie("vessel_session", path="/", httponly=True,
                       samesite="lax", secure=is_secure)
    return resp

@app.get("/auth/check")
async def auth_check(request: Request):
    token = request.cookies.get("vessel_session", "")
    return {"authenticated": _is_authenticated(token), "setup": not PIN_FILE.exists()}

# ─── HTML / PWA ──────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    token = request.cookies.get("vessel_session", "")
    if _is_authenticated(token):
        return HTML
    return LOGIN_HTML

@app.get("/manifest.json")
async def manifest():
    return {
        "name": "Vessel Dashboard",
        "short_name": "Vessel",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#060a06",
        "theme_color": "#060a06",
        "icons": [
            {"src": VESSEL_ICON, "sizes": "64x64", "type": "image/jpeg"},
            {"src": VESSEL_ICON_192, "sizes": "192x192", "type": "image/jpeg"}
        ]
    }

@app.get("/sw.js")
async def service_worker():
    sw_code = """
const CACHE = 'vessel-v3';
const OFFLINE_URL = '/';

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.add(OFFLINE_URL)));
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys =>
    Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
  ));
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  if (e.request.mode === 'navigate') {
    e.respondWith(
      fetch(e.request).catch(() => caches.match(OFFLINE_URL))
    );
  }
});
"""
    return Response(content=sw_code, media_type="application/javascript",
                    headers={"Service-Worker-Allowed": "/"})

# ─── API endpoints ───────────────────────────────────────────────────────────
@app.get("/api/health")
async def api_health():
    pi = await get_pi_stats()
    ollama = await bg(check_ollama_health)
    bridge = await bg(check_bridge_health)
    return {
        "status": "ok",
        "timestamp": time.time(),
        "services": {
            "pi": pi["health"],
            "ollama": "online" if ollama else "offline",
            "bridge": bridge.get("status", "offline")
        },
        "details": {
            "pi_temp": pi.get("temp_val"),
            "pi_cpu": pi.get("cpu_val"),
            "pi_mem": pi.get("mem_pct")
        }
    }

@app.get("/api/plugins")
async def api_plugins(request: Request):
    """Ritorna lista plugin con JS/CSS per injection frontend."""
    token = request.cookies.get("vessel_session", "")
    if not _is_authenticated(token):
        return JSONResponse({"error": "Non autenticato"}, status_code=401)
    result = []
    for plugin in PLUGINS:
        p_path = Path(plugin["_path"])
        entry = {"id": plugin["id"], "title": plugin["title"], "icon": plugin["icon"],
                 "tab_label": plugin["tab_label"], "actions": plugin.get("actions", "load"),
                 "wide": plugin.get("wide", False)}
        js_path = p_path / "widget.js"
        if js_path.exists():
            entry["js"] = js_path.read_text(encoding="utf-8")
        css_path = p_path / "widget.css"
        if css_path.exists():
            entry["css"] = css_path.read_text(encoding="utf-8")
        result.append(entry)
    return result

ALLOWED_FILE_BASES = [MEMORY_FILE, HISTORY_FILE, QUICKREF_FILE, BRIEFING_LOG, USAGE_LOG]

def _is_allowed_path(path_str: str) -> bool:
    """Verifica che il path risolto corrisponda a uno dei file consentiti."""
    try:
        real = Path(path_str).resolve()
    except Exception:
        return False
    return any(real == base.resolve() for base in ALLOWED_FILE_BASES)

@app.get("/api/file")
async def api_file(request: Request, path: str = ""):
    token = request.cookies.get("vessel_session", "")
    if not _is_authenticated(token):
        return JSONResponse({"error": "Non autenticato"}, status_code=401)
    ip = request.client.host
    if not _rate_limit(ip, "file", 30, 60):
        return JSONResponse({"error": "Troppe richieste"}, status_code=429)
    if not _is_allowed_path(path):
        return {"content": "Accesso negato"}
    try:
        return {"content": Path(path).resolve().read_text(encoding="utf-8")}
    except Exception:
        return {"content": "File non trovato"}

@app.get("/api/export")
async def export_data(request: Request):
    token = request.cookies.get("vessel_session", "")
    if not _is_authenticated(token):
        ip = request.client.host
        if not _rate_limit(ip, "auth", 5, 300):
            return JSONResponse({"error": "Rate limit superato"}, status_code=429)
        raise HTTPException(status_code=401, detail="Non autenticato")

    memory_dir = Path.home() / ".nanobot" / "workspace" / "memory"
    history_dir = Path.home() / ".nanobot" / "workspace" / "history"
    claude_log = Path.home() / ".nanobot" / "claude_tasks.jsonl"
    token_log = Path.home() / ".nanobot" / "tokens.jsonl"
    config_file = Path.home() / ".nanobot" / "config.json"

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
        for d in [memory_dir, history_dir]:
            if d.exists() and d.is_dir():
                for file_path in d.rglob("*"):
                    if file_path.is_file():
                        arcname = file_path.relative_to(Path.home() / ".nanobot")
                        zip_file.write(file_path, arcname=arcname)

        for f in [claude_log, token_log, config_file]:
            if f.exists():
                arcname = f.name
                zip_file.write(f, arcname=arcname)

    zip_buffer.seek(0)

    headers = {
        "Content-Disposition": 'attachment; filename="vessel_export.zip"'
    }
    return Response(zip_buffer.getvalue(), headers=headers, media_type="application/x-zip-compressed")
