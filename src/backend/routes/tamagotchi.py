# ─── Tamagotchi ESP32 ─────────────────────────────────────────────────────────
_tamagotchi_connections: set = set()
_tamagotchi_state: str = "IDLE"
_mood_counter: dict = {"happy": 0, "alert": 0, "error": 0}

async def broadcast_tamagotchi(state: str, detail: str = "", text: str = "", mood: dict | None = None):
    global _tamagotchi_state, _mood_counter
    _tamagotchi_state = state
    # Aggiorna mood counter
    if state in ("HAPPY", "PROUD"): _mood_counter["happy"] += 1
    elif state == "ALERT":         _mood_counter["alert"] += 1
    elif state == "ERROR":         _mood_counter["error"] += 1
    elif state == "SLEEPING":
        # Reset counter dopo invio (fine giornata)
        pass
    payload: dict = {"state": state}
    if detail:
        payload["detail"] = detail
    if text:
        payload["text"] = text
    if mood is not None:
        payload["mood"] = mood
    dead = set()
    for ws in _tamagotchi_connections.copy():
        try:
            await ws.send_json(payload)
        except Exception:
            dead.add(ws)
    _tamagotchi_connections.difference_update(dead)
    # Notifica dashboard WS clients (Fase 38 — Emotion Bridge)
    try:
        await manager.broadcast({"type": "sigil_state", "state": state})
    except Exception:
        pass

async def broadcast_tamagotchi_raw(payload: dict):
    """Invia payload arbitrario (es. crypto_update) all'ESP32 senza modificare _tamagotchi_state."""
    dead = set()
    for ws in _tamagotchi_connections.copy():
        try:
            await ws.send_json(payload)
        except Exception:
            dead.add(ws)
    _tamagotchi_connections.difference_update(dead)

async def _handle_tamagotchi_cmd(ws: WebSocket, cmd: str, req_id: int):
    """Gestisce un comando inviato dall'ESP32 e risponde."""
    try:
        if cmd == "get_stats":
            pi = await get_pi_stats()
            await ws.send_json({"resp": "get_stats", "req_id": req_id, "ok": True, "data": {
                "cpu": pi["cpu"], "mem": pi["mem"], "temp": pi["temp"],
                "disk": pi["disk"], "uptime": pi["uptime"]}})

        elif cmd == "gateway_restart":
            subprocess.run(["tmux", "kill-session", "-t", "nanobot-gateway"],
                           capture_output=True, text=True, timeout=10)
            await asyncio.sleep(1)
            subprocess.run(["tmux", "new-session", "-d", "-s", "nanobot-gateway", "nanobot", "gateway"],
                           capture_output=True, text=True, timeout=10)
            await ws.send_json({"resp": "gateway_restart", "req_id": req_id, "ok": True,
                                "data": {"msg": "Gateway riavviato"}})

        elif cmd == "tmux_list":
            sessions = await bg(get_tmux_sessions)
            names = [s["name"] for s in sessions]
            await ws.send_json({"resp": "tmux_list", "req_id": req_id, "ok": True,
                                "data": {"sessions": names}})

        elif cmd == "reboot":
            db_log_audit("reboot", actor="tamagotchi_esp32")
            await ws.send_json({"resp": "reboot", "req_id": req_id, "ok": True,
                                "data": {"msg": "Rebooting..."}})
            await asyncio.sleep(0.5)
            subprocess.run(["sudo", "reboot"])

        elif cmd == "shutdown":
            db_log_audit("shutdown", actor="tamagotchi_esp32")
            await ws.send_json({"resp": "shutdown", "req_id": req_id, "ok": True,
                                "data": {"msg": "Shutting down..."}})
            await asyncio.sleep(0.5)
            subprocess.run(["sudo", "shutdown", "-h", "now"])

        elif cmd == "run_briefing":
            await bg(run_briefing)
            await ws.send_json({"resp": "run_briefing", "req_id": req_id, "ok": True,
                                "data": {"msg": "Briefing generato"}})

        elif cmd == "check_ollama":
            alive = await bg(check_ollama_health)
            await ws.send_json({"resp": "check_ollama", "req_id": req_id, "ok": True,
                                "data": {"alive": alive}})

        elif cmd == "check_bridge":
            health = await bg(check_bridge_health)
            await ws.send_json({"resp": "check_bridge", "req_id": req_id, "ok": True,
                                "data": health})

        elif cmd == "warmup_ollama":
            await bg(warmup_ollama)
            await ws.send_json({"resp": "warmup_ollama", "req_id": req_id, "ok": True,
                                "data": {"msg": "Modello precaricato"}})

        else:
            await ws.send_json({"resp": cmd, "req_id": req_id, "ok": False,
                                "data": {"msg": f"Comando sconosciuto: {cmd}"}})

    except Exception as e:
        print(f"[Tamagotchi] Errore cmd '{cmd}': {e}")
        try:
            await ws.send_json({"resp": cmd, "req_id": req_id, "ok": False,
                                "data": {"msg": str(e)[:60]}})
        except Exception:
            pass

@app.websocket("/ws/tamagotchi")
async def tamagotchi_ws(websocket: WebSocket):
    await websocket.accept()
    _tamagotchi_connections.add(websocket)
    db_log_event("esp32", "connect", payload={"ip": websocket.client.host})
    print(f"[Tamagotchi] ESP32 connesso da {websocket.client.host}")
    try:
        await websocket.send_json({"state": _tamagotchi_state})
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                try:
                    msg = json.loads(data)
                    cmd = msg.get("cmd")
                    if cmd:
                        req_id = msg.get("req_id", 0)
                        await _handle_tamagotchi_cmd(websocket, cmd, req_id)
                        continue
                except (json.JSONDecodeError, ValueError):
                    pass
            except asyncio.TimeoutError:
                await websocket.send_json({"ping": True})
    except WebSocketDisconnect:
        _tamagotchi_connections.discard(websocket)
        db_log_event("esp32", "disconnect")
        print("[Tamagotchi] ESP32 disconnesso")
    except Exception:
        _tamagotchi_connections.discard(websocket)
        db_log_event("esp32", "disconnect", status="error")

@app.post("/api/tamagotchi/state")
async def set_tamagotchi_state(request: Request):
    """Aggiorna lo stato del tamagotchi ESP32. Chiamabile da cron/script locali."""
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "JSON non valido"}, status_code=400)
    global _mood_counter
    state  = data.get("state", "")
    detail = data.get("detail", "")
    text   = data.get("text", "")
    mood   = data.get("mood", None)
    valid_states = {"IDLE", "THINKING", "WORKING", "PROUD", "SLEEPING", "ERROR", "BOOTING", "HAPPY", "ALERT", "CURIOUS", "BORED", "PEEKING"}
    if state not in valid_states:
        return JSONResponse({"ok": False, "error": f"Stato non valido. Validi: {valid_states}"}, status_code=400)
    await broadcast_tamagotchi(state, detail, text, mood)
    if state == "SLEEPING":
        _mood_counter = {"happy": 0, "alert": 0, "error": 0}
    return {"ok": True, "state": state, "clients": len(_tamagotchi_connections)}

@app.post("/api/tamagotchi/text")
async def send_tamagotchi_text(request: Request):
    """Invia un messaggio di testo all'ESP32 per scrolling display."""
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "JSON non valido"}, status_code=400)
    text = data.get("text", "").strip()
    if not text or len(text) > 64:
        return JSONResponse({"ok": False, "error": "Testo vuoto o troppo lungo (max 64)"}, status_code=400)
    # Il firmware si aspetta "state" per processare il payload — manteniamo lo stato corrente
    await broadcast_tamagotchi_raw({"state": _tamagotchi_state, "text": text})
    return {"ok": True, "text": text, "clients": len(_tamagotchi_connections)}

@app.get("/api/tamagotchi/firmware")
async def get_tamagotchi_firmware():
    """Serve il firmware .bin per OTA update ESP32."""
    from pathlib import Path as _Path
    from fastapi.responses import FileResponse
    fw = _Path.home() / ".nanobot" / "firmware" / "tamagotchi.bin"
    if not fw.exists():
        return JSONResponse({"error": "Firmware non trovato. Esegui il deploy prima."}, status_code=404)
    return FileResponse(str(fw), media_type="application/octet-stream", filename="tamagotchi.bin")

@app.post("/api/tamagotchi/ota")
async def trigger_tamagotchi_ota(request: Request):
    """Invia comando OTA all'ESP32 via WebSocket."""
    dead = set()
    for ws in _tamagotchi_connections.copy():
        try:
            await ws.send_json({"action": "ota_update"})
        except Exception:
            dead.add(ws)
    _tamagotchi_connections.difference_update(dead)
    clients = len(_tamagotchi_connections) - len(dead)
    return {"ok": True, "notified": clients}

@app.get("/api/tamagotchi/state")
async def get_tamagotchi_state():
    return {"state": _tamagotchi_state, "clients": len(_tamagotchi_connections)}

@app.get("/api/tamagotchi/mood")
async def get_tamagotchi_mood():
    """Restituisce il contatore mood giornaliero. Usato da goodnight.py."""
    return dict(_mood_counter)
