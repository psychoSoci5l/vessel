  // ── Widget: System actions ──
  function killSession(name) { send({ action: 'tmux_kill', session: name }); }
  function gatewayRestart() { showToast('[..] Riavvio gateway…'); send({ action: 'gateway_restart' }); }
  function requestStats() { send({ action: 'get_stats' }); }
