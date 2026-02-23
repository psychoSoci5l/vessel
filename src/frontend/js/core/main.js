  // ═══════════════════════════════════════════
  // VESSEL DASHBOARD — JS Core v3
  // Tab navigation + WebSocket + All widgets
  // ═══════════════════════════════════════════

  let ws = null;
  let reconnectTimer = null;
  let memoryEnabled = false;
  let currentTab = 'dashboard';
  let chatProvider = 'cloud';
  let streamDiv = null;
  let activeDrawer = null;
  let claudeRunning = false;

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

  function esc(s) {
    if (typeof s !== 'string') return s == null ? '' : String(s);
    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
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
    else if (msg.type === 'chat_done') { finalizeStream(); document.getElementById('chat-send').disabled = false; }
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

  // ── Tab Navigation ──
  function switchView(tabName) {
    if (currentTab === tabName) return;
    currentTab = tabName;

    document.querySelectorAll('.tab-view').forEach(v => v.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));

    const view = document.getElementById('tab-' + tabName);
    if (view) view.classList.add('active');

    const navBtn = document.querySelector(`.nav-item[data-tab="${tabName}"]`);
    if (navBtn) navBtn.classList.add('active');

    // Ridisegna chart quando torniamo a dashboard
    if (tabName === 'dashboard') requestAnimationFrame(() => drawChart());

    // Desktop split-pane: auto-load task data quando si apre Code
    if (tabName === 'code' && window.matchMedia('(min-width: 768px)').matches) {
      send({ action: 'check_bridge' });
      send({ action: 'get_claude_tasks' });
    }
  }

  function scrollToSys(sectionId) {
    setTimeout(() => {
      const el = document.getElementById(sectionId);
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 100);
  }

  // ── Code Panel toggle ──
  function switchCodePanel(panel, btn) {
    document.querySelectorAll('.code-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.code-panel').forEach(p => p.classList.remove('active'));

    btn.classList.add('active');
    const el = document.getElementById('code-' + panel);
    if (el) el.classList.add('active');

    // Auto-load bridge status quando si apre Task
    if (panel === 'task') {
      send({ action: 'check_bridge' });
      send({ action: 'get_claude_tasks' });
    }
  }

  // ── Stats ──
  const MAX_SAMPLES = 180;
  const cpuHistory = [];
  const tempHistory = [];

  function updateStats(pi) {
    const cpuPct = pi.cpu_val || 0;
    const tempC = pi.temp_val || 0;
    const memPct = pi.mem_pct || 0;

    const hcCpu = document.getElementById('hc-cpu-val');
    if (hcCpu) hcCpu.textContent = pi.cpu ? cpuPct.toFixed(1) + '%' : '--';
    const hcRam = document.getElementById('hc-ram-val');
    if (hcRam) hcRam.textContent = memPct + '%';
    const hcRamSub = document.getElementById('hc-ram-sub');
    if (hcRamSub) hcRamSub.textContent = pi.mem || '';
    const hcTemp = document.getElementById('hc-temp-val');
    if (hcTemp) hcTemp.textContent = pi.temp || '--';
    const hcUptime = document.getElementById('hc-uptime-val');
    if (hcUptime) hcUptime.textContent = pi.uptime || '--';

    // Bars
    const cpuBar = document.getElementById('hc-cpu-bar');
    if (cpuBar) {
      cpuBar.style.width = cpuPct + '%';
      cpuBar.style.background = cpuPct > 80 ? 'var(--red)' : cpuPct > 60 ? 'var(--amber)' : 'var(--green)';
    }
    const ramBar = document.getElementById('hc-ram-bar');
    if (ramBar) {
      ramBar.style.width = memPct + '%';
      ramBar.style.background = memPct > 85 ? 'var(--red)' : memPct > 70 ? 'var(--amber)' : 'var(--cyan)';
    }
    const tempBar = document.getElementById('hc-temp-bar');
    if (tempBar) {
      const tPct = Math.min(100, (tempC / 85) * 100);
      tempBar.style.width = tPct + '%';
      tempBar.style.background = tempC > 70 ? 'var(--red)' : 'var(--amber)';
    }
    const diskPct = pi.disk_pct || 0;
    const hcDisk = document.getElementById('hc-disk-val');
    if (hcDisk) hcDisk.textContent = diskPct + '%';
    const hcDiskSub = document.getElementById('hc-disk-sub');
    if (hcDiskSub) hcDiskSub.textContent = pi.disk || '';
    const diskBar = document.getElementById('hc-disk-bar');
    if (diskBar) {
      diskBar.style.width = diskPct + '%';
      diskBar.style.background = diskPct > 85 ? 'var(--red)' : diskPct > 70 ? 'var(--amber)' : 'var(--green)';
    }

    // Health dots
    ['home-health-dot', 'chat-health-dot'].forEach(id => {
      const el = document.getElementById(id);
      if (el) {
        el.className = 'health-dot ' + (pi.health || '');
        el.title = pi.health === 'red' ? 'ATTENZIONE' : pi.health === 'yellow' ? 'Sotto controllo' : 'Tutto OK';
      }
    });

    // Temp in headers
    const chatTemp = document.getElementById('chat-temp');
    if (chatTemp) chatTemp.textContent = pi.temp || '--';
    const homeTemp = document.getElementById('home-temp');
    if (homeTemp) homeTemp.textContent = pi.temp || '--';

    // History
    cpuHistory.push(cpuPct);
    tempHistory.push(tempC);
    if (cpuHistory.length > MAX_SAMPLES) cpuHistory.shift();
    if (tempHistory.length > MAX_SAMPLES) tempHistory.shift();
    drawChart();
  }

  function drawChart() {
    const canvas = document.getElementById('pi-chart');
    if (!canvas || canvas.offsetParent === null) return;
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);
    const w = rect.width, h = rect.height;
    ctx.clearRect(0, 0, w, h);
    ctx.strokeStyle = 'rgba(0,255,65,0.08)';
    ctx.lineWidth = 1;
    for (let y = 0; y <= h; y += h / 4) {
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
    }
    if (cpuHistory.length < 2) return;
    function drawLine(data, maxVal, color) {
      ctx.strokeStyle = color; ctx.lineWidth = 1.5; ctx.lineJoin = 'round';
      ctx.beginPath();
      const step = w / (MAX_SAMPLES - 1);
      const offset = MAX_SAMPLES - data.length;
      for (let i = 0; i < data.length; i++) {
        const x = (offset + i) * step;
        const y = h - (data[i] / maxVal) * (h - 4) - 2;
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }
      ctx.stroke();
    }
    drawLine(cpuHistory, 100, '#00ff41');
    drawLine(tempHistory, 85, '#ffb000');
  }

  function updateSessions(sessions) {
    const el = document.getElementById('session-list');
    const countEl = document.getElementById('hc-sessions-sub');
    if (!sessions || !sessions.length) {
      const empty = '<div class="no-items">// nessuna sessione attiva</div>';
      if (el) el.innerHTML = empty;
      if (countEl) countEl.textContent = '0 sessioni';
      return;
    }
    const html = sessions.map(s => `
      <div class="session-item">
        <div class="session-name"><div class="session-dot"></div><code>${esc(s.name)}</code></div>
        <button class="btn-red btn-sm" onclick="killSession('${esc(s.name)}')">✕</button>
      </div>`).join('');
    if (el) el.innerHTML = html;
    if (countEl) countEl.textContent = sessions.length + ' session' + (sessions.length !== 1 ? 'i' : 'e');
  }

  // ── Chat ──
  function sendChat() {
    const input = document.getElementById('chat-input');
    const text = (input.value || '').trim();
    if (!text) return;
    // Auto-switch to Code tab > Chat panel if not there
    if (currentTab !== 'code') switchView('code');
    appendMessage(text, 'user');
    send({ action: 'chat', text, provider: chatProvider });
    input.value = '';
    input.style.height = 'auto';
    document.getElementById('chat-send').disabled = true;
  }

  function autoResizeInput(el) {
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 120) + 'px';
  }

  function appendMessage(text, role) {
    const box = document.getElementById('chat-messages');
    if (role === 'bot') {
      const wrap = document.createElement('div');
      wrap.className = 'copy-wrap';
      wrap.style.cssText = 'align-self:flex-start;max-width:85%;';
      const div = document.createElement('div');
      div.className = 'msg msg-bot';
      div.style.maxWidth = '100%';
      div.textContent = text;
      const btn = document.createElement('button');
      btn.className = 'copy-btn'; btn.textContent = '📋'; btn.title = 'Copia';
      btn.onclick = () => copyToClipboard(div.textContent);
      wrap.appendChild(div); wrap.appendChild(btn);
      box.appendChild(wrap);
    } else {
      const div = document.createElement('div');
      div.className = `msg msg-${role}`;
      div.textContent = text;
      box.appendChild(div);
    }
    box.scrollTop = box.scrollHeight;
  }

  function appendChunk(text) {
    const box = document.getElementById('chat-messages');
    if (!streamDiv) {
      streamDiv = document.createElement('div');
      streamDiv.className = 'msg msg-bot';
      streamDiv.textContent = '';
      box.appendChild(streamDiv);
    }
    streamDiv.textContent += text;
    box.scrollTop = box.scrollHeight;
  }

  function finalizeStream() {
    if (streamDiv) {
      const box = streamDiv.parentNode;
      const wrap = document.createElement('div');
      wrap.className = 'copy-wrap';
      wrap.style.cssText = 'align-self:flex-start;max-width:85%;';
      streamDiv.style.maxWidth = '100%';
      box.insertBefore(wrap, streamDiv);
      wrap.appendChild(streamDiv);
      const btn = document.createElement('button');
      btn.className = 'copy-btn'; btn.textContent = '📋'; btn.title = 'Copia';
      btn.onclick = () => copyToClipboard(streamDiv.textContent);
      wrap.appendChild(btn);
    }
    streamDiv = null;
  }

  function appendThinking() {
    const box = document.getElementById('chat-messages');
    const div = document.createElement('div');
    div.id = 'thinking'; div.className = 'msg-thinking';
    div.innerHTML = 'elaborazione <span class="dots"><span>.</span><span>.</span><span>.</span></span>';
    box.appendChild(div); box.scrollTop = box.scrollHeight;
  }
  function removeThinking() { const el = document.getElementById('thinking'); if (el) el.remove(); }

  function clearChat() {
    document.getElementById('chat-messages').innerHTML =
      '<div class="msg msg-bot">Chat pulita 🧹</div>';
    send({ action: 'clear_chat' });
  }

  // ── Provider ──
  function toggleProviderMenu() {
    document.getElementById('provider-dropdown').classList.toggle('open');
  }
  function switchProvider(provider) {
    chatProvider = provider;
    const dot = document.getElementById('provider-dot');
    const label = document.getElementById('provider-short');
    const names = { cloud: 'Haiku', local: 'Local', pc_coder: 'PC Coder', pc_deep: 'PC Deep', deepseek: 'DeepSeek' };
    const dotClass = { cloud: 'dot-cloud', local: 'dot-local', pc_coder: 'dot-pc-coder', pc_deep: 'dot-pc-deep', deepseek: 'dot-deepseek' };
    dot.className = 'provider-dot ' + (dotClass[provider] || 'dot-local');
    label.textContent = names[provider] || 'Local';
    document.getElementById('provider-dropdown').classList.remove('open');
  }
  document.addEventListener('click', (e) => {
    const dd = document.getElementById('provider-dropdown');
    if (dd && !dd.contains(e.target)) dd.classList.remove('open');
  });

  // ── Memory toggle ──
  function toggleMemory() { send({ action: 'toggle_memory' }); }

  // ── Drawer (bottom sheet per Briefing/Token/Crypto) ──
  const DRAWER_CFG = {
    briefing: { title: '▤ Morning Briefing', actions: '<button class="btn-ghost btn-sm" onclick="loadBriefing(this)">Carica</button><button class="btn-green btn-sm" onclick="runBriefing(this)">▶ Genera</button>' },
    tokens:   { title: '¤ Token & API', actions: '<button class="btn-ghost btn-sm" onclick="loadTokens(this)">Carica</button>' },
    crypto:   { title: '₿ Crypto', actions: '<button class="btn-ghost btn-sm" onclick="loadCrypto(this)">Carica</button>' },
  };

  function openDrawer(widgetId) {
    if (activeDrawer === widgetId) { closeDrawer(); return; }
    document.querySelectorAll('.drawer-widget').forEach(w => w.classList.remove('active'));
    const dw = document.getElementById('dw-' + widgetId);
    if (dw) dw.classList.add('active');
    const cfg = DRAWER_CFG[widgetId];
    document.getElementById('drawer-title').textContent = cfg ? cfg.title : widgetId;
    document.getElementById('drawer-actions').innerHTML =
      (cfg ? cfg.actions : '') +
      '<button class="btn-ghost btn-sm" onclick="closeDrawer()">✕</button>';
    document.getElementById('drawer-overlay').classList.add('show');
    activeDrawer = widgetId;
  }

  function closeDrawer() {
    document.getElementById('drawer-overlay').classList.remove('show');
    activeDrawer = null;
  }

  // Swipe-down to close
  (function() {
    const drawer = document.querySelector('.drawer');
    if (!drawer) return;
    let touchStartY = 0;
    drawer.addEventListener('touchstart', function(e) {
      touchStartY = e.touches[0].clientY;
    }, { passive: true });
    drawer.addEventListener('touchmove', function(e) {
      const dy = e.touches[0].clientY - touchStartY;
      if (dy > 80) { closeDrawer(); touchStartY = 9999; }
    }, { passive: true });
  })();

  // Escape
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      if (activeDrawer) closeDrawer();
      const outFs = document.getElementById('output-fullscreen');
      if (outFs && outFs.classList.contains('show')) closeOutputFullscreen();
    }
  });

  // ── Widget loaders ──
  function loadTokens(btn) { if (btn) btn.textContent = '…'; send({ action: 'get_tokens' }); }
  function loadLogs(btn) {
    if (btn) btn.textContent = '…';
    const dateEl = document.getElementById('log-date-filter');
    const searchEl = document.getElementById('log-search-filter');
    send({ action: 'get_logs', date: dateEl ? dateEl.value : '', search: searchEl ? searchEl.value.trim() : '' });
  }
  function loadCron(btn) { if (btn) btn.textContent = '…'; send({ action: 'get_cron' }); }
  function loadBriefing(btn) { if (btn) btn.textContent = '…'; send({ action: 'get_briefing' }); }
  function runBriefing(btn) { if (btn) btn.textContent = '…'; send({ action: 'run_briefing' }); }
  function loadCrypto(btn) { if (btn) btn.textContent = '…'; send({ action: 'get_crypto' }); }

  // ── Renderers ──
  function renderCrypto(data) {
    const el = document.getElementById('crypto-body');
    if (data.error && !data.btc) {
      el.innerHTML = `<div class="no-items">// errore: ${esc(data.error)}</div><div style="margin-top:8px;text-align:center;"><button class="btn-ghost btn-sm" onclick="loadCrypto()">↻ Riprova</button></div>`;
      return;
    }
    function coinRow(symbol, label, d) {
      if (!d) return '';
      const arrow = d.change_24h >= 0 ? '▲' : '▼';
      const color = d.change_24h >= 0 ? 'var(--green)' : 'var(--red)';
      return `<div style="display:flex;align-items:center;justify-content:space-between;background:var(--bg2);border:1px solid var(--border);border-radius:6px;padding:10px 12px;margin-bottom:6px;">
        <div><div style="font-size:13px;font-weight:700;color:var(--amber);">${symbol} ${label}</div><div style="font-size:10px;color:var(--muted);margin-top:2px;">€${d.eur.toLocaleString()}</div></div>
        <div style="text-align:right;"><div style="font-size:15px;font-weight:700;color:var(--green);">$${d.usd.toLocaleString()}</div><div style="font-size:11px;color:${color};margin-top:2px;">${arrow} ${Math.abs(d.change_24h)}%</div></div>
      </div>`;
    }
    el.innerHTML = coinRow('₿', 'Bitcoin', data.btc) + coinRow('Ξ', 'Ethereum', data.eth) +
      '<div style="margin-top:4px;"><button class="btn-ghost btn-sm" onclick="loadCrypto()">↻ Aggiorna</button></div>';
    const hBtc = document.getElementById('home-btc-price');
    if (hBtc && data.btc) hBtc.textContent = '$' + data.btc.usd.toLocaleString();
    const hEth = document.getElementById('home-eth-price');
    if (hEth && data.eth) hEth.textContent = '$' + data.eth.usd.toLocaleString();
  }

  function renderBriefing(data) {
    const bp = document.getElementById('wt-briefing-preview');
    if (bp) {
      if (data.last) {
        const parts = [];
        const ts = (data.last.ts || '').split('T')[0];
        if (ts) parts.push(ts);
        if (data.last.weather) parts.push(data.last.weather.substring(0, 25));
        const cal = (data.last.calendar_today || []).length;
        if (cal > 0) parts.push(cal + ' eventi oggi');
        bp.textContent = parts.join(' · ') || 'Caricato';
      } else { bp.textContent = 'Nessun briefing'; }
    }
    const el = document.getElementById('briefing-body');
    if (!data.last) {
      el.innerHTML = '<div class="no-items">// nessun briefing</div><div style="margin-top:8px;text-align:center;"><button class="btn-green btn-sm" onclick="runBriefing()">▶ Genera</button></div>';
      return;
    }
    const b = data.last;
    const ts = b.ts ? b.ts.replace('T', ' ') : '—';
    const weather = b.weather || '—';
    const calToday = b.calendar_today || [];
    const calTomorrow = b.calendar_tomorrow || [];
    const calTodayHtml = calToday.length > 0
      ? calToday.map(e => { const loc = e.location ? ` <span style="color:var(--muted)">@ ${esc(e.location)}</span>` : ''; return `<div style="margin:3px 0;font-size:11px;"><span style="color:var(--cyan);font-weight:600">${esc(e.time)}</span> <span style="color:var(--text2)">${esc(e.summary)}</span>${loc}</div>`; }).join('')
      : '<div style="font-size:11px;color:var(--muted);font-style:italic">Nessun evento</div>';
    const calTomorrowHtml = calTomorrow.length > 0
      ? `<div style="font-size:10px;color:var(--muted);margin-top:8px;margin-bottom:4px">📅 DOMANI</div>` +
        calTomorrow.map(e => `<div style="margin:2px 0;font-size:10px;color:var(--text2)"><span style="color:var(--cyan)">${esc(e.time)}</span> ${esc(e.summary)}</div>`).join('')
      : '';
    const stories = (b.stories || []).map((s, i) => `<div style="margin:4px 0;font-size:11px;color:var(--text2);">${i+1}. ${esc(s.title)}</div>`).join('');
    el.innerHTML = `
      <div style="display:flex;justify-content:space-between;margin-bottom:8px;">
        <div style="font-size:10px;color:var(--muted);">ULTIMO: <span style="color:var(--amber)">${ts}</span></div>
        <div style="font-size:10px;color:var(--muted);">PROSSIMO: <span style="color:var(--cyan)">${data.next_run || '07:30'}</span></div>
      </div>
      <div style="background:var(--bg2);border:1px solid var(--border);border-radius:6px;padding:10px 12px;margin-bottom:8px;">
        <div style="font-size:11px;color:var(--amber);margin-bottom:8px;">🌤 ${esc(weather)}</div>
        <div style="font-size:10px;color:var(--muted);margin-bottom:4px;">📅 OGGI</div>
        ${calTodayHtml}${calTomorrowHtml}
        <div style="font-size:10px;color:var(--muted);margin-top:8px;margin-bottom:4px;">📰 NEWS</div>
        ${stories}
      </div>
      <div style="display:flex;gap:6px;">
        <button class="btn-ghost btn-sm" onclick="loadBriefing()">↻ Aggiorna</button>
        <button class="btn-green btn-sm" onclick="runBriefing()">▶ Genera</button>
        <button class="btn-ghost btn-sm" onclick="copyToClipboard(document.getElementById('briefing-body').textContent)">📋</button>
      </div>`;
  }

  function renderTokens(data) {
    const tp = document.getElementById('wt-tokens-preview');
    if (tp) {
      const inTok = (data.today_input || 0);
      const outTok = (data.today_output || 0);
      const fmt = n => n >= 1000 ? (n/1000).toFixed(1) + 'K' : n;
      const model = (data.last_model || '').split('-').pop() || '';
      tp.textContent = fmt(inTok) + ' in / ' + fmt(outTok) + ' out' + (model ? ' · ' + model : '');
    }
    const src = data.source === 'api' ? '🌐 API' : '📁 Local';
    document.getElementById('tokens-body').innerHTML = `
      <div class="token-grid">
        <div class="token-item"><div class="token-label">Input</div><div class="token-value">${(data.today_input||0).toLocaleString()}</div></div>
        <div class="token-item"><div class="token-label">Output</div><div class="token-value">${(data.today_output||0).toLocaleString()}</div></div>
        <div class="token-item"><div class="token-label">Calls</div><div class="token-value">${data.total_calls||0}</div></div>
      </div>
      <div style="margin-bottom:6px;font-size:10px;color:var(--muted);">
        MODELLO: <span style="color:var(--cyan)">${esc(data.last_model||'N/A')}</span> · FONTE: <span style="color:var(--text2)">${src}</span>
      </div>
      <div class="mono-block" style="max-height:100px;">${(data.log_lines||[]).map(l=>esc(l)).join('\n')||'// nessun log'}</div>
      <div style="margin-top:8px;display:flex;gap:6px;"><button class="btn-ghost btn-sm" onclick="loadTokens()">↻</button><button class="btn-ghost btn-sm" onclick="copyToClipboard(document.getElementById('tokens-body').textContent)">📋</button></div>`;
  }

  // ── Usage Report ──
  function loadUsageReport(period, btn) {
    if (btn) {
      document.querySelectorAll('.usage-period-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
    }
    send({ action: 'get_usage_report', period: period || 'day' });
  }

  const _providerNames = {
    anthropic: 'Haiku', openrouter: 'DeepSeek', ollama: 'Local',
    ollama_pc_coder: 'PC Coder', ollama_pc_deep: 'PC Deep', unknown: '?'
  };
  const _providerColors = {
    anthropic: 'var(--green)', openrouter: 'var(--amber)', ollama: 'var(--muted)',
    ollama_pc_coder: 'var(--cyan)', ollama_pc_deep: '#aa66ff'
  };

  function renderUsageReport(data) {
    const el = document.getElementById('usage-report-body');
    if (!el) return;
    const fmt = n => n >= 1000000 ? (n/1000000).toFixed(1) + 'M' : n >= 1000 ? (n/1000).toFixed(1) + 'K' : n;
    const rows = data.rows || [];
    const total = data.total || { input: 0, output: 0, calls: 0 };
    if (!rows.length) {
      el.innerHTML = '<div class="no-items">// nessun utilizzo nel periodo</div>';
      return;
    }
    let html = '<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;font-size:11px;">';
    html += '<tr style="color:var(--muted);text-align:left;border-bottom:1px solid var(--border);"><th style="padding:4px 6px;">Provider</th><th style="padding:4px 6px;text-align:right;">In</th><th style="padding:4px 6px;text-align:right;">Out</th><th style="padding:4px 6px;text-align:right;">Tot</th><th style="padding:4px 6px;text-align:right;">Calls</th></tr>';
    rows.forEach(r => {
      const name = _providerNames[r.provider] || r.provider;
      const color = _providerColors[r.provider] || 'var(--text2)';
      const tot = r.input + r.output;
      html += `<tr style="border-bottom:1px solid var(--border);">
        <td style="padding:4px 6px;color:${color};font-weight:600;">${esc(name)}</td>
        <td style="padding:4px 6px;text-align:right;color:var(--text2);">${fmt(r.input)}</td>
        <td style="padding:4px 6px;text-align:right;color:var(--text2);">${fmt(r.output)}</td>
        <td style="padding:4px 6px;text-align:right;color:var(--text);">${fmt(tot)}</td>
        <td style="padding:4px 6px;text-align:right;color:var(--muted);">${r.calls}</td>
      </tr>`;
    });
    const grandTot = total.input + total.output;
    html += `<tr style="font-weight:700;">
      <td style="padding:6px;color:var(--green);">TOTALE</td>
      <td style="padding:6px;text-align:right;color:var(--green);">${fmt(total.input)}</td>
      <td style="padding:6px;text-align:right;color:var(--green);">${fmt(total.output)}</td>
      <td style="padding:6px;text-align:right;color:var(--green);">${fmt(grandTot)}</td>
      <td style="padding:6px;text-align:right;color:var(--green);">${total.calls}</td>
    </tr>`;
    html += '</table></div>';
    el.innerHTML = html;
  }

  function renderLogs(data) {
    const lp = document.getElementById('wt-logs-preview');
    if (lp) {
      const lines = (typeof data === 'object' && data.lines) ? data.lines : [];
      const last = lines.length ? lines[lines.length - 1] : '';
      lp.textContent = last ? last.substring(0, 60) : 'Nessun log';
    }
    const el = document.getElementById('logs-body');
    if (typeof data === 'string') {
      el.innerHTML = `<div class="mono-block">${esc(data)||'(nessun log)'}</div>
        <div style="margin-top:8px;"><button class="btn-ghost btn-sm" onclick="loadLogs()">↻</button></div>`;
      return;
    }
    const dateVal = document.getElementById('log-date-filter')?.value || '';
    const searchVal = document.getElementById('log-search-filter')?.value || '';
    const lines = data.lines || [];
    const total = data.total || 0;
    const filtered = data.filtered || 0;
    const countInfo = (dateVal || searchVal)
      ? `<span style="color:var(--amber)">${filtered}</span> / ${total} righe`
      : `${total} righe`;
    let content = lines.length ? lines.map(l => {
      if (searchVal) {
        const re = new RegExp('(' + searchVal.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'gi');
        return l.replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(re, '<span style="background:var(--green-dim);color:var(--green);font-weight:700;">$1</span>');
      }
      return l.replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }).join('\n') : '(nessun log)';
    el.innerHTML = `
      <div style="display:flex;gap:6px;margin-bottom:8px;flex-wrap:wrap;">
        <input type="date" id="log-date-filter" value="${dateVal}" class="input-field input-date" style="min-width:130px;flex:0;">
        <input type="text" id="log-search-filter" placeholder="🔍 cerca…" value="${searchVal}" class="input-field">
        <button class="btn-green btn-sm" onclick="loadLogs()">🔍</button>
        <button class="btn-ghost btn-sm" onclick="clearLogFilters()">✕</button>
      </div>
      <div style="font-size:10px;color:var(--muted);margin-bottom:6px;">${countInfo}</div>
      <div class="mono-block" style="max-height:240px;">${content}</div>
      <div style="margin-top:8px;display:flex;gap:6px;"><button class="btn-ghost btn-sm" onclick="loadLogs()">↻</button><button class="btn-ghost btn-sm" onclick="copyToClipboard(document.querySelector('#logs-body .mono-block')?.textContent||'')">📋</button></div>`;
    document.getElementById('log-search-filter')?.addEventListener('keydown', e => {
      if (e.key === 'Enter') loadLogs();
    });
  }
  function clearLogFilters() {
    const d = document.getElementById('log-date-filter');
    const s = document.getElementById('log-search-filter');
    if (d) d.value = '';
    if (s) s.value = '';
    loadLogs();
  }

  function renderCron(jobs) {
    const cp = document.getElementById('wt-cron-preview');
    if (cp) cp.textContent = ((jobs && jobs.length) || 0) + ' job attivi';
    const el = document.getElementById('cron-body');
    const jobList = (jobs && jobs.length) ? '<div class="cron-list">' + jobs.map((j, i) => `
      <div class="cron-item" style="align-items:center;">
        <div class="cron-schedule">${j.schedule}</div>
        <div style="flex:1;"><div class="cron-cmd">${j.command}</div>${j.desc?`<div class="cron-desc">// ${j.desc}</div>`:''}</div>
        <button class="btn-red btn-sm" style="padding:3px 8px;" onclick="deleteCron(${i})">✕</button>
      </div>`).join('') + '</div>'
      : '<div class="no-items">// nessun cron job</div>';
    el.innerHTML = jobList + `
      <div style="margin-top:10px;border-top:1px solid var(--border);padding-top:10px;">
        <div style="font-size:10px;color:var(--muted);margin-bottom:6px;">AGGIUNGI</div>
        <div style="display:flex;gap:6px;margin-bottom:6px;">
          <input id="cron-schedule" placeholder="30 7 * * *" class="input-field" style="width:120px;flex:0;">
          <input id="cron-command" placeholder="python3.13 /path/script.py" class="input-field">
        </div>
        <div style="display:flex;gap:6px;">
          <button class="btn-green btn-sm" onclick="addCron()">+ Aggiungi</button>
          <button class="btn-ghost btn-sm" onclick="loadCron()">↻</button>
        </div>
      </div>`;
  }
  function addCron() {
    const sched = document.getElementById('cron-schedule').value.trim();
    const cmd = document.getElementById('cron-command').value.trim();
    if (!sched || !cmd) { showToast('⚠️ Compila schedule e comando'); return; }
    send({ action: 'add_cron', schedule: sched, command: cmd });
  }
  function deleteCron(index) { send({ action: 'delete_cron', index: index }); }

  // ── Remote Code ──
  const TASK_CATEGORIES = [
    { id: 'debug',    label: 'DEBUG',    color: '#ff5555', loop: true,
      keywords: ['debug','errore','crash','fix','correggi','problema','risolvi','broken','traceback','exception','fallisce','non funziona'] },
    { id: 'modifica', label: 'MODIFICA', color: '#ffaa00', loop: true,
      keywords: ['modifica','aggiorna','cambia','refactor','aggiungi','rimuovi','sostituisci','rinomina','sposta','estendi','integra'] },
    { id: 'deploy',   label: 'DEPLOY',   color: '#aa66ff', loop: true,
      keywords: ['deploy','installa','avvia','configura','setup','migra','pubblica','rilascia','lancia'] },
    { id: 'crea',     label: 'CREA',     color: '#00ff41', loop: false,
      keywords: ['crea','genera','scrivi','costruisci','make','nuova','nuovo','implementa','progetta','realizza'] },
    { id: 'analizza', label: 'ANALIZZA', color: '#44aaff', loop: false,
      keywords: ['analizza','spiega','controlla','leggi','dimmi','cosa fa','verifica','mostra','elenca','lista','log','report','confronta'] },
  ];

  function detectTaskCategory(prompt) {
    const p = prompt.toLowerCase();
    for (const cat of TASK_CATEGORIES) {
      if (cat.keywords.some(kw => p.includes(kw))) return cat;
    }
    return { id: 'generico', label: 'GENERICO', color: '#666', loop: false };
  }

  function updateCategoryBadge() {
    const ta = document.getElementById('claude-prompt');
    const badge = document.getElementById('task-category-badge');
    const loopToggle = document.getElementById('ralph-toggle');
    if (!badge || !ta) return;
    const cat = detectTaskCategory(ta.value);
    const manualLoop = loopToggle?.checked || false;
    const willLoop = manualLoop || cat.loop;
    badge.textContent = cat.label;
    badge.style.color = cat.color;
    badge.style.borderColor = cat.color;
    const loopBadge = document.getElementById('task-loop-badge');
    if (loopBadge) loopBadge.style.display = willLoop ? 'inline-block' : 'none';
  }

  const promptTemplates = [
    { label: '— Template —', value: '' },
    { label: 'Build + Deploy', value: 'Esegui build.py nella cartella Pi Nanobot, copia il file generato sul Pi via SCP e riavvia il servizio in tmux.' },
    { label: 'Fix bug', value: 'Analizza il seguente errore e correggi il codice sorgente in src/:\n\n' },
    { label: 'Git status + diff', value: 'Mostra git status e git diff nella cartella Pi Nanobot. Non fare commit, solo mostra lo stato.' },
    { label: 'Test dashboard', value: 'Verifica che la dashboard Vessel risponda correttamente: curl http://picoclaw.local:8090/ e riporta il risultato.' },
    { label: 'Log Pi', value: 'Connettiti via SSH a picoclaw.local e mostra le ultime 50 righe del log del gateway nanobot: tail -50 ~/.nanobot/gateway.log' },
  ];

  function loadBridge(btn) {
    if (btn) btn.textContent = '...';
    send({ action: 'check_bridge' });
    send({ action: 'get_claude_tasks' });
  }

  function applyTemplate(sel) {
    if (!sel.value) return;
    const ta = document.getElementById('claude-prompt');
    if (ta) { ta.value = sel.value; ta.focus(); }
    sel.selectedIndex = 0;
  }

  function runClaudeTask() {
    const input = document.getElementById('claude-prompt');
    const prompt = input.value.trim();
    if (!prompt) { showToast('Scrivi un prompt'); return; }
    if (claudeRunning) { showToast('Task già in esecuzione'); return; }
    claudeRunning = true;
    document.getElementById('claude-run-btn').disabled = true;
    document.getElementById('claude-cancel-btn').style.display = 'inline-block';
    const wrap = document.getElementById('claude-output-wrap');
    if (wrap) wrap.style.display = 'block';
    const out = document.getElementById('claude-output');
    if (out) out.innerHTML = '';
    const manualLoop = document.getElementById('ralph-toggle')?.checked || false;
    const cat = detectTaskCategory(prompt);
    const useLoop = manualLoop || cat.loop;
    send({ action: 'claude_task', prompt: prompt, use_loop: useLoop });
  }

  function cancelClaudeTask() { send({ action: 'claude_cancel' }); }

  function finalizeClaudeTask(data) {
    claudeRunning = false;
    const rb = document.getElementById('claude-run-btn');
    const cb = document.getElementById('claude-cancel-btn');
    if (rb) rb.disabled = false;
    if (cb) cb.style.display = 'none';
    const status = data.completed ? '✅' : '⚠️';
    const dur = (data.duration_ms / 1000).toFixed(1);
    const iter = data.iterations > 1 ? ` (${data.iterations} iter)` : '';
    showToast(`${status} Task in ${dur}s${iter}`);
    send({ action: 'get_claude_tasks' });
  }

  function renderBridgeStatus(data) {
    const codePrev = document.getElementById('wt-code-preview');
    if (codePrev) {
      const isOnline = data.status === 'ok';
      codePrev.innerHTML = '<span class="dot ' + (isOnline ? 'dot-local' : '') + '" style="display:inline-block;width:6px;height:6px;margin-right:4px;vertical-align:middle;' + (!isOnline ? 'background:var(--red);box-shadow:0 0 4px var(--red);' : '') + '"></span>' +
        (isOnline ? 'Bridge online' : 'Bridge offline');
    }
    const dot = document.getElementById('bridge-dot');
    if (dot) {
      dot.className = data.status === 'ok' ? 'health-dot green' : 'health-dot red';
      dot.title = data.status === 'ok' ? 'Bridge online' : 'Bridge offline';
    }
    const body = document.getElementById('claude-body');
    if (body && body.querySelector('.widget-placeholder')) {
      renderClaudeUI(data.status === 'ok');
    }
  }

  function renderClaudeUI(isOnline) {
    const body = document.getElementById('claude-body');
    if (!body) return;
    const opts = promptTemplates.map(t => `<option value="${t.value.replace(/"/g,'&quot;')}">${t.label}</option>`).join('');
    body.innerHTML = `
      <div style="margin-bottom:10px;">
        <select onchange="applyTemplate(this)" style="width:100%;margin-bottom:6px;background:var(--bg2);border:1px solid var(--border);border-radius:6px;color:var(--text2);padding:6px 8px;font-family:var(--font);font-size:11px;outline:none;cursor:pointer;">${opts}</select>
        <textarea id="claude-prompt" rows="3" placeholder="Descrivi il task..."
          oninput="updateCategoryBadge()"
          style="width:100%;background:var(--bg2);border:1px solid var(--border2);border-radius:6px;color:var(--green);padding:10px 12px;font-family:var(--font);font-size:13px;outline:none;resize:vertical;caret-color:var(--green);min-height:60px;box-sizing:border-box;"></textarea>
        <div style="display:flex;gap:6px;margin-top:6px;align-items:center;flex-wrap:wrap;">
          <button class="btn-green" id="claude-run-btn" onclick="runClaudeTask()" ${!isOnline ? 'disabled title="Bridge offline"' : ''}>▶ Esegui</button>
          <button class="btn-red" id="claude-cancel-btn" onclick="cancelClaudeTask()" style="display:none;">■ Stop</button>
          <span id="task-category-badge" style="font-size:9px;font-weight:700;letter-spacing:1px;border:1px solid #666;border-radius:3px;padding:1px 6px;color:#666;">GENERICO</span>
          <span id="task-loop-badge" style="display:none;font-size:9px;font-weight:700;letter-spacing:1px;border:1px solid #ffaa00;border-radius:3px;padding:1px 6px;color:#ffaa00;">⟳ LOOP</span>
          <label style="display:flex;align-items:center;gap:4px;font-size:10px;color:var(--text2);margin-left:auto;cursor:pointer;">
            <input type="checkbox" id="ralph-toggle" style="accent-color:var(--green);cursor:pointer;" onchange="updateCategoryBadge()"> Ralph Loop
          </label>
          <button class="btn-ghost btn-sm" onclick="loadBridge()">↻</button>
        </div>
      </div>
      <div id="claude-output-wrap" style="display:none;margin-bottom:10px;">
        <div class="claude-output-header">
          <span>OUTPUT</span>
          <div style="display:flex;gap:4px;">
            <button class="btn-ghost btn-sm" onclick="copyClaudeOutput()">📋</button>
            <button class="btn-ghost btn-sm" onclick="openOutputFullscreen()">⛶</button>
          </div>
        </div>
        <div id="claude-output" class="claude-output"></div>
      </div>
      <div id="claude-tasks-list"></div>`;
  }

  function renderClaudeTasks(tasks) {
    const body = document.getElementById('claude-body');
    if (body && body.querySelector('.widget-placeholder')) {
      renderClaudeUI(document.getElementById('bridge-dot')?.classList.contains('green'));
    }
    const el = document.getElementById('claude-tasks-list');
    if (!el) return;
    if (!tasks || !tasks.length) {
      el.innerHTML = '<div class="no-items">// nessun task</div>';
      return;
    }
    const list = tasks.slice().reverse();
    el.innerHTML = '<div style="font-size:10px;color:var(--muted);margin-bottom:6px;">ULTIMI TASK</div>' +
      list.map(t => {
        const dur = t.duration_ms ? (t.duration_ms/1000).toFixed(1)+'s' : '';
        const ts = (t.ts || '').replace('T', ' ');
        return `<div class="claude-task-item">
          <div class="claude-task-prompt" title="${esc(t.prompt)}">${esc(t.prompt)}</div>
          <div class="claude-task-meta">
            <span class="claude-task-status ${esc(t.status)}">${esc(t.status)}</span>
            <span>${esc(ts)}</span><span>${dur}</span>
          </div>
        </div>`;
      }).join('');
  }

  // ── Knowledge Graph ──
  function loadEntities(btn) { if (btn) btn.textContent = '...'; send({ action: 'get_entities' }); }
  function deleteEntity(id) { send({ action: 'delete_entity', id: id }); }

  function renderKnowledgeGraph(entities, relations) {
    const mp = document.getElementById('wt-mem-preview');
    if (mp) mp.textContent = (entities ? entities.length : 0) + ' entità · ' + (relations ? relations.length : 0) + ' relazioni';
    const el = document.getElementById('grafo-body');
    if (!entities || entities.length === 0) {
      el.innerHTML = '<div class="no-items">// nessuna entità</div><div style="margin-top:8px;"><button class="btn-ghost btn-sm" onclick="loadEntities()">↻</button></div>';
      return;
    }
    const groups = { tech: [], person: [], place: [] };
    entities.forEach(e => {
      if (groups[e.type]) groups[e.type].push(e);
      else { if (!groups.other) groups.other = []; groups.other.push(e); }
    });
    const labels = { tech: 'Tech', person: 'Persone', place: 'Luoghi', other: 'Altro' };
    const colors = { tech: 'var(--cyan)', person: 'var(--green)', place: 'var(--amber)', other: 'var(--text2)' };
    let html = '<div style="font-size:10px;color:var(--muted);margin-bottom:8px;">' + entities.length + ' entità</div>';
    for (const [type, items] of Object.entries(groups)) {
      if (!items.length) continue;
      html += '<div style="margin-bottom:12px;">';
      html += '<div style="font-size:10px;color:' + colors[type] + ';text-transform:uppercase;letter-spacing:1px;margin-bottom:4px;font-weight:700;">' + labels[type] + ' (' + items.length + ')</div>';
      items.forEach(e => {
        const since = e.first_seen ? e.first_seen.split('T')[0] : '';
        const last = e.last_seen ? e.last_seen.split('T')[0] : '';
        html += '<div style="display:flex;align-items:center;justify-content:space-between;background:var(--bg2);border:1px solid var(--border);border-radius:6px;padding:6px 10px;margin-bottom:3px;">';
        html += '<div style="flex:1;min-width:0;"><span style="color:var(--text2);font-size:12px;font-weight:600;">' + esc(e.name) + '</span> <span style="color:var(--muted);font-size:10px;">freq:' + e.frequency + '</span>';
        html += '<div style="font-size:9px;color:var(--muted);">' + since + ' → ' + last + '</div></div>';
        html += '<button class="btn-red btn-sm" style="padding:2px 6px;font-size:9px;margin-left:6px;flex-shrink:0;" onclick="deleteEntity(' + e.id + ')">✕</button></div>';
      });
      html += '</div>';
    }
    html += '<div><button class="btn-ghost btn-sm" onclick="loadEntities()">↻</button></div>';
    el.innerHTML = html;
  }

  // ── Memory Tabs ──
  function switchMemTab(name, btn) {
    const section = btn.closest('.prof-section');
    section.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    section.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('tab-' + name)?.classList.add('active');
    if (name === 'history') send({ action: 'get_history' });
    if (name === 'quickref') send({ action: 'get_quickref' });
    if (name === 'grafo') loadEntities();
  }

  // ── Misc ──
  function requestStats() { send({ action: 'get_stats' }); }
  function refreshMemory() { send({ action: 'get_memory' }); }
  function refreshHistory() { send({ action: 'get_history' }); }

  function searchMemory() {
    const keyword = document.getElementById('mem-search-keyword')?.value.trim() || '';
    const date = document.getElementById('mem-search-date')?.value || '';
    if (!keyword && !date) { showToast('Inserisci almeno una keyword o data'); return; }
    document.getElementById('search-results').innerHTML = '<span style="color:var(--muted)">Ricerca…</span>';
    send({ action: 'search_memory', keyword: keyword, date_from: date, date_to: date });
  }

  function renderMemorySearch(results) {
    const el = document.getElementById('search-results');
    if (!results || results.length === 0) { el.innerHTML = '<span style="color:var(--muted)">Nessun risultato</span>'; return; }
    const keyword = document.getElementById('mem-search-keyword')?.value.trim() || '';
    el.innerHTML = '<div style="color:var(--amber);margin-bottom:6px;">' + results.length + ' risultati</div>' +
      results.map(r => {
        const ts = r.ts.replace('T', ' ');
        const role = r.role === 'user' ? '<span style="color:var(--green)">user</span>' : '<span style="color:var(--cyan)">bot</span>';
        let snippet = (r.content || '').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        if (snippet.length > 200) snippet = snippet.substring(0, 200) + '…';
        if (keyword) {
          const re = new RegExp('(' + keyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'gi');
          snippet = snippet.replace(re, '<span style="background:var(--green-dim);color:var(--green);font-weight:700;">$1</span>');
        }
        return '<div style="border-bottom:1px solid var(--border);padding:4px 0;"><div style="display:flex;gap:8px;font-size:10px;color:var(--muted);margin-bottom:2px;"><span>' + ts + '</span>' + role + '</div><div style="font-size:11px;">' + snippet + '</div></div>';
      }).join('');
  }

  function killSession(name) { send({ action: 'tmux_kill', session: name }); }
  function gatewayRestart() { showToast('⏳ Riavvio gateway…'); send({ action: 'gateway_restart' }); }

  // ── Modals ──
  function showHelpModal() { document.getElementById('help-modal').classList.add('show'); }
  function closeHelpModal() { document.getElementById('help-modal').classList.remove('show'); }
  function showRebootModal() { document.getElementById('reboot-modal').classList.add('show'); }
  function hideRebootModal() { document.getElementById('reboot-modal').classList.remove('show'); }
  function confirmReboot() { hideRebootModal(); send({ action: 'reboot' }); }
  function showShutdownModal() { document.getElementById('shutdown-modal').classList.add('show'); }
  function hideShutdownModal() { document.getElementById('shutdown-modal').classList.remove('show'); }
  function confirmShutdown() { hideShutdownModal(); send({ action: 'shutdown' }); }

  function startRebootWait() {
    document.getElementById('reboot-overlay').classList.add('show');
    const statusEl = document.getElementById('reboot-status');
    let seconds = 0;
    const timer = setInterval(() => { seconds++; statusEl.textContent = `Attesa: ${seconds}s`; }, 1000);
    const tryReconnect = setInterval(() => {
      fetch('/', { method: 'HEAD', cache: 'no-store' })
        .then(r => {
          if (r.ok) {
            clearInterval(timer); clearInterval(tryReconnect);
            document.getElementById('reboot-overlay').classList.remove('show');
            showToast('✅ Pi riavviato');
            if (ws) { try { ws.close(); } catch(e) {} }
            connect();
          }
        }).catch(() => {});
    }, 3000);
    setTimeout(() => { clearInterval(timer); clearInterval(tryReconnect); statusEl.textContent = 'Timeout — ricarica manualmente.'; }, 120000);
  }

  function showToast(text) {
    const el = document.getElementById('toast');
    el.textContent = text; el.classList.add('show');
    setTimeout(() => el.classList.remove('show'), Math.max(2500, Math.min(text.length * 60, 6000)));
  }

  function copyToClipboard(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(() => showToast('📋 Copiato')).catch(() => _fallbackCopy(text));
    } else { _fallbackCopy(text); }
  }
  function _fallbackCopy(text) {
    const ta = document.createElement('textarea');
    ta.value = text; ta.style.cssText = 'position:fixed;left:-9999px;top:-9999px;';
    document.body.appendChild(ta); ta.select();
    try { document.execCommand('copy'); showToast('📋 Copiato'); } catch(e) { showToast('Copia non riuscita'); }
    document.body.removeChild(ta);
  }

  // ── Claude output helpers ──
  let _claudeLineBuf = '';
  const _toolPattern = /^[⏺●▶►•]\s*(Read|Edit|Write|Bash|Glob|Grep|Task|Search|WebFetch|WebSearch|NotebookEdit)\b/;
  const _toolStartPattern = /^[⏺●▶►•]\s/;

  function appendClaudeChunk(out, text) {
    _claudeLineBuf += text;
    const lines = _claudeLineBuf.split('\n');
    _claudeLineBuf = lines.pop();
    for (const line of lines) {
      if (_toolPattern.test(line)) {
        const el = document.createElement('div');
        el.className = 'claude-tool-use'; el.textContent = line;
        out.appendChild(el);
      } else if (_toolStartPattern.test(line) && line.length < 200) {
        const el = document.createElement('div');
        el.className = 'claude-tool-info'; el.textContent = line;
        out.appendChild(el);
      } else {
        out.appendChild(document.createTextNode(line + '\n'));
      }
    }
    if (_claudeLineBuf) {
      out.appendChild(document.createTextNode(_claudeLineBuf));
      _claudeLineBuf = '';
    }
  }

  function copyClaudeOutput() {
    const out = document.getElementById('claude-output');
    if (out) copyToClipboard(out.textContent);
  }
  function openOutputFullscreen() {
    const out = document.getElementById('claude-output');
    if (!out) return;
    document.getElementById('output-fs-content').textContent = out.textContent;
    document.getElementById('output-fullscreen').classList.add('show');
  }
  function closeOutputFullscreen() {
    document.getElementById('output-fullscreen').classList.remove('show');
  }

  // ── Clock ──
  setInterval(() => {
    const t = new Date().toLocaleTimeString('it-IT');
    ['home-clock', 'chat-clock'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.textContent = t;
    });
  }, 1000);

  // ── Input handlers ──
  document.addEventListener('DOMContentLoaded', () => {
    const chatInput = document.getElementById('chat-input');
    chatInput.addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(); }
    });
    chatInput.addEventListener('input', () => autoResizeInput(chatInput));
    document.getElementById('mem-search-keyword')?.addEventListener('keydown', e => {
      if (e.key === 'Enter') searchMemory();
    });
  });

  // ── iOS virtual keyboard ──
  if (window.visualViewport) {
    const appLayout = document.querySelector('.app-layout');
    let pendingVV = null;
    const handleVV = () => {
      if (pendingVV) return;
      pendingVV = requestAnimationFrame(() => {
        pendingVV = null;
        const vvh = window.visualViewport.height;
        const vvTop = window.visualViewport.offsetTop;
        appLayout.style.height = vvh + 'px';
        appLayout.style.transform = 'translateY(' + vvTop + 'px)';
        const msgs = document.getElementById('chat-messages');
        if (msgs) msgs.scrollTop = msgs.scrollHeight;
      });
    };
    window.visualViewport.addEventListener('resize', handleVV);
    window.visualViewport.addEventListener('scroll', handleVV);
  }

  // ── Service Worker ──
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js').catch(() => {});
  }

  // ── Connect ──
  connect();

  // ── Plugin System ──
  async function loadPlugins() {
    try {
      const resp = await fetch('/api/plugins');
      if (!resp.ok) return;
      const plugins = await resp.json();
      if (!plugins.length) return;
      plugins.forEach(p => {
        const pid = 'plugin_' + p.id;
        const actHtml = p.actions === 'load'
          ? '<button class="btn-ghost btn-sm" onclick="pluginLoad_' + p.id + '(this)">Carica</button>'
          : '';
        DRAWER_CFG[pid] = { title: p.icon + ' ' + p.title, actions: actHtml, wide: p.wide || false };
        const body = document.querySelector('.drawer-body');
        if (body) {
          const dw = document.createElement('div');
          dw.className = 'drawer-widget';
          dw.id = 'dw-' + pid;
          dw.innerHTML = '<div id="plugin-' + p.id + '-body"><div class="widget-placeholder"><span class="ph-icon">' + p.icon + '</span><span>' + p.title + '</span></div></div>';
          body.appendChild(dw);
        }
        if (p.css) { const st = document.createElement('style'); st.textContent = p.css; document.head.appendChild(st); }
        if (p.js) { try { (new Function(p.js))(); } catch(e) { console.error('[Plugin] ' + p.id + ':', e); } }
        if (p.actions === 'load' && !window['pluginLoad_' + p.id]) {
          window['pluginLoad_' + p.id] = function(btn) { if (btn) btn.textContent = '…'; send({ action: pid }); };
        }
      });
    } catch(e) { console.error('[Plugins]', e); }
  }
  setTimeout(loadPlugins, 500);
