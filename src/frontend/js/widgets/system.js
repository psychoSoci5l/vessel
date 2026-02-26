  // ── Widget: System actions ──
  function killSession(name) { send({ action: 'tmux_kill', session: name }); }
  function gatewayRestart() { showToast('[..] Riavvio gateway…'); send({ action: 'gateway_restart' }); }
  function requestStats() { send({ action: 'get_stats' }); }
  async function flashOTA() {
    if (!confirm('Aggiornare firmware ESP32 via WiFi?\nIl Sigil si riavvierà al termine.')) return;
    showToast('[..] OTA in corso…');
    try {
      const r = await fetch('/api/tamagotchi/ota', { method: 'POST' });
      const d = await r.json();
      showToast(d.ok ? '[ok] OTA inviato — Sigil si aggiorna' : '[!] OTA fallito: ' + (d.error || '?'));
    } catch (e) {
      showToast('[!] Errore OTA: ' + e.message);
    }
  }
