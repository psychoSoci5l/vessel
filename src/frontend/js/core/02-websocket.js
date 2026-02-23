  // ── WebSocket ──
  function connect() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    ws = new WebSocket(`${proto}://${location.host}/ws`);
    ws.onopen = () => {
      const hhd = document.getElementById('home-health-dot');
      if (hhd && hhd.classList.contains('ws-offline')) {
        hhd.classList.remove('ws-offline', 'red');
        hhd.className = 'health-dot';
      }
      if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
      setTimeout(() => {
        send({ action: 'get_crypto' });
        send({ action: 'plugin_weather' });
        send({ action: 'get_tokens' });
        send({ action: 'get_briefing' });
        send({ action: 'get_cron' });
        send({ action: 'get_logs' });
        send({ action: 'check_bridge' });
        send({ action: 'get_entities' });
        send({ action: 'get_usage_report', period: 'day' });
        send({ action: 'get_saved_prompts' });
        send({ action: 'get_sigil_state' });
      }, 500);
    };
    ws.onclose = (e) => {
      const hhd = document.getElementById('home-health-dot');
      if (hhd) { hhd.className = 'health-dot red ws-offline'; hhd.title = 'Disconnesso'; }
      if (e.code === 4001) { window.location.href = '/'; return; }
      reconnectTimer = setTimeout(connect, 3000);
    };
    ws.onerror = () => ws.close();
    ws.onmessage = (e) => handleMessage(JSON.parse(e.data));
  }

  function send(data) {
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(data));
  }

  // ── Message handler ──
  function handleMessage(msg) {
    if (msg.type === 'init') {
      updateStats(msg.data.pi);
      updateSessions(msg.data.tmux);
      const vb = document.getElementById('version-badge');
      if (vb) vb.textContent = msg.data.version;
      const mc = document.getElementById('memory-content');
      if (mc) mc.textContent = msg.data.memory;
    }
    else if (msg.type === 'stats') {
      updateStats(msg.data.pi);
      updateSessions(msg.data.tmux);
      ['home-clock', 'chat-clock'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.textContent = msg.data.time;
      });
    }
    else if (msg.type === 'chat_thinking') { appendThinking(); }
    else if (msg.type === 'chat_chunk') { removeThinking(); appendChunk(msg.text); }
    else if (msg.type === 'chat_done') {
      finalizeStream();
      document.getElementById('chat-send').disabled = false;
      if (msg.agent) showAgentBadge(msg.agent);
    }
    else if (msg.type === 'chat_reply') { removeThinking(); appendMessage(msg.text, 'bot'); document.getElementById('chat-send').disabled = false; }
    else if (msg.type === 'memory')   { const el = document.getElementById('memory-content'); if (el) el.textContent = msg.text; }
    else if (msg.type === 'history')  { const el = document.getElementById('history-content'); if (el) el.textContent = msg.text; }
    else if (msg.type === 'quickref') { const el = document.getElementById('quickref-content'); if (el) el.textContent = msg.text; }
    else if (msg.type === 'memory_search') { renderMemorySearch(msg.results); }
    else if (msg.type === 'knowledge_graph') { renderKnowledgeGraph(msg.entities, msg.relations); }
    else if (msg.type === 'entity_deleted') { if (msg.success) loadEntities(); }
    else if (msg.type === 'memory_toggle') {
      memoryEnabled = msg.enabled;
      const btn = document.getElementById('memory-toggle');
      if (btn) btn.style.opacity = msg.enabled ? '1' : '0.4';
    }
    else if (msg.type === 'logs')    { renderLogs(msg.data); }
    else if (msg.type === 'cron')    { renderCron(msg.jobs); }
    else if (msg.type === 'tokens')  { renderTokens(msg.data); }
    else if (msg.type === 'usage_report') { renderUsageReport(msg.data); }
    else if (msg.type === 'briefing') { renderBriefing(msg.data); }
    else if (msg.type === 'crypto')   { renderCrypto(msg.data); }
    else if (msg.type === 'toast')   { showToast(msg.text); }
    else if (msg.type === 'reboot_ack') { startRebootWait(); }
    else if (msg.type === 'shutdown_ack') { document.getElementById('reboot-overlay').classList.add('show'); document.getElementById('reboot-status').textContent = 'Il Pi si sta spegnendo…'; document.querySelector('.reboot-text').textContent = 'Spegnimento in corso…'; }
    else if (msg.type === 'claude_thinking') {
      _claudeLineBuf = '';
      const wrap = document.getElementById('claude-output-wrap');
      if (wrap) wrap.style.display = 'block';
      const out = document.getElementById('claude-output');
      if (out) { out.innerHTML = ''; out.appendChild(document.createTextNode('Connessione al bridge...\n')); }
    }
    else if (msg.type === 'claude_chunk') {
      const out = document.getElementById('claude-output');
      if (out) { appendClaudeChunk(out, msg.text); out.scrollTop = out.scrollHeight; }
    }
    else if (msg.type === 'claude_iteration') {
      const out = document.getElementById('claude-output');
      if (out) {
        const m = document.createElement('div');
        m.className = 'ralph-marker';
        m.textContent = '═══ ITERAZIONE ' + msg.iteration + '/' + msg.max + ' ═══';
        out.appendChild(m);
        out.scrollTop = out.scrollHeight;
      }
    }
    else if (msg.type === 'claude_supervisor') {
      const out = document.getElementById('claude-output');
      if (out) {
        const m = document.createElement('div');
        m.className = 'ralph-supervisor';
        m.textContent = '▸ ' + msg.text;
        out.appendChild(m);
        out.scrollTop = out.scrollHeight;
      }
    }
    else if (msg.type === 'claude_info') {
      const out = document.getElementById('claude-output');
      if (out) {
        const m = document.createElement('div');
        m.className = 'ralph-info';
        m.textContent = msg.text;
        out.appendChild(m);
        out.scrollTop = out.scrollHeight;
      }
    }
    else if (msg.type === 'claude_done') { finalizeClaudeTask(msg); }
    else if (msg.type === 'claude_cancelled') {
      claudeRunning = false;
      const rb = document.getElementById('claude-run-btn');
      const cb = document.getElementById('claude-cancel-btn');
      if (rb) rb.disabled = false;
      if (cb) cb.style.display = 'none';
      showToast('Task cancellato');
    }
    else if (msg.type === 'bridge_status') { renderBridgeStatus(msg.data); }
    else if (msg.type === 'claude_tasks') { renderClaudeTasks(msg.tasks); }
    else if (msg.type === 'saved_prompts') { renderSavedPrompts(msg.prompts); }
    else if (msg.type === 'sigil_state') { updateSigilIndicator(msg.state); }
    else if (msg.type && msg.type.startsWith('plugin_')) {
      const hName = 'pluginRender_' + msg.type.replace('plugin_', '');
      if (window[hName]) { try { window[hName](msg); } catch(e) { console.error('[Plugin] render:', e); } }
      if (msg.type === 'plugin_weather' && msg.data) {
        const hw = document.getElementById('home-weather-text');
        if (hw) {
          const d = msg.data;
          const parts = [];
          if (d.city) parts.push(d.city);
          if (d.temp != null) parts.push(d.temp + '°C');
          if (d.condition) parts.push(d.condition);
          hw.textContent = parts.join(' · ') || '--';
        }
      }
    }
  }
