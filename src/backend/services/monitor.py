# ─── Heartbeat Monitor (Fase 17B) ────────────────────────────────────────────
_heartbeat_last_alert: dict[str, float] = {}
_heartbeat_known_down: set[str] = set()  # servizi noti come down (no re-alert)
_BINARY_ALERT_KEYS = {"bridge_down", "ollama_down"}  # notifica solo cambio stato

async def heartbeat_task():
    """Loop background: controlla salute del sistema ogni HEARTBEAT_INTERVAL secondi.
    Servizi (bridge/ollama): notifica solo cambio stato (down/recovery).
    Soglie (temp/RAM): cooldown per evitare spam."""
    print("[Heartbeat] Monitor avviato")
    await asyncio.sleep(30)  # attendi stabilizzazione post-boot
    while True:
        try:
            alerts = []
            now = time.time()

            # 1) Temperatura Pi
            pi = await get_pi_stats()
            temp = pi.get("temp_val", 0)
            if temp > HEARTBEAT_TEMP_THRESHOLD:
                alerts.append(("temp_high", f"🌡️ Temperatura Pi: {temp:.1f}°C (soglia: {HEARTBEAT_TEMP_THRESHOLD}°C)"))

            # 2) RAM critica (> 90%)
            mem_pct = pi.get("mem_pct", 0)
            if mem_pct > 90:
                alerts.append(("mem_high", f"💾 RAM Pi: {mem_pct}% (critica)"))

            # 3) Ollama + Bridge — check paralleli
            checks = [bg(check_ollama_health)]
            if CLAUDE_BRIDGE_TOKEN:
                checks.append(bg(check_bridge_health))
            results = await asyncio.gather(*checks, return_exceptions=True)

            ollama_ok = results[0] if not isinstance(results[0], Exception) else False
            if not ollama_ok:
                alerts.append(("ollama_down", "🔴 Ollama locale non raggiungibile"))

            if CLAUDE_BRIDGE_TOKEN and len(results) > 1:
                bridge = results[1] if not isinstance(results[1], Exception) else {"status": "offline"}
                if bridge.get("status") == "offline":
                    alerts.append(("bridge_down", "🔴 Claude Bridge offline"))

            # Invia alert con logica differenziata
            active_keys = {k for k, _ in alerts}
            for alert_key, alert_msg in alerts:
                if alert_key in _BINARY_ALERT_KEYS:
                    # Servizi: notifica solo al cambio stato (up → down)
                    if alert_key not in _heartbeat_known_down:
                        _heartbeat_known_down.add(alert_key)
                        telegram_send(f"[Heartbeat] {alert_msg}")
                        db_log_audit("heartbeat_alert", resource=alert_key, details=alert_msg)
                        db_log_event("system", "alert", status="error",
                                     payload={"key": alert_key, "msg": alert_msg})
                        print(f"[Heartbeat] ALERT: {alert_msg}")
                else:
                    # Soglie (temp/RAM): cooldown come prima
                    last = _heartbeat_last_alert.get(alert_key, 0)
                    if now - last >= HEARTBEAT_ALERT_COOLDOWN:
                        _heartbeat_last_alert[alert_key] = now
                        telegram_send(f"[Heartbeat] {alert_msg}")
                        db_log_audit("heartbeat_alert", resource=alert_key, details=alert_msg)
                        db_log_event("system", "alert", status="error",
                                     payload={"key": alert_key, "msg": alert_msg})
                        print(f"[Heartbeat] ALERT: {alert_msg}")

            # Recovery: notifica quando servizi tornano online (down → up)
            for key in list(_heartbeat_known_down):
                if key not in active_keys:
                    _heartbeat_known_down.discard(key)
                    label = key.replace("_down", "").replace("_", " ").title()
                    telegram_send(f"[Heartbeat] ✅ {label} tornato online")
                    db_log_audit("heartbeat_recovery", resource=key)
                    db_log_event("system", "recovery", payload={"key": key, "service": label})
                    print(f"[Heartbeat] RECOVERY: {label} online")

            # Tamagotchi: ALERT se ci sono problemi, IDLE se risolti
            if alerts:
                _set_tamagotchi_local("ALERT")
            elif _heartbeat_last_alert or _heartbeat_known_down:
                pass  # ancora problemi noti, mantieni stato corrente
            else:
                _set_tamagotchi_local("IDLE")

            # Pulisci cooldown soglie risolte
            for key in list(_heartbeat_last_alert.keys()):
                if key not in active_keys:
                    del _heartbeat_last_alert[key]

        except Exception as e:
            print(f"[Heartbeat] Error: {e}")
        await asyncio.sleep(HEARTBEAT_INTERVAL)


async def crypto_push_task():
    """Loop background: push prezzi BTC/ETH all'ESP32 ogni 15 minuti via broadcast_raw.
    Usa globals() per accedere a broadcast_tamagotchi_raw definita in routes.py
    (nel file compilato unico tutto è nello stesso namespace globale).
    """
    print("[Crypto] Push task avviato")
    await asyncio.sleep(60)  # attendi boot completo
    while True:
        try:
            _conns    = globals().get("_tamagotchi_connections", set())
            _bcast    = globals().get("broadcast_tamagotchi_raw")
            if _conns and _bcast:
                data = await bg(get_crypto_prices)
                btc  = data.get("btc")
                eth  = data.get("eth")
                if not data.get("error") and btc and btc.get("usd", 0) > 0:
                    payload = {
                        "action":     "crypto_update",
                        "btc":        btc["usd"],
                        "eth":        eth["usd"]        if eth else 0,
                        "btc_change": btc["change_24h"] if btc else 0,
                        "eth_change": eth["change_24h"] if eth else 0,
                    }
                    await _bcast(payload)
                    print(f"[Crypto] Push → BTC ${btc['usd']:.0f} ({btc['change_24h']:+.1f}%)")
        except Exception as e:
            print(f"[Crypto] Push error: {e}")
        await asyncio.sleep(900)  # 15 minuti
