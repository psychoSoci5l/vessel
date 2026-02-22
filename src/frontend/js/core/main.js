let ws = null;
  let reconnectTimer = null;

  function connect() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    ws = new WebSocket(`${proto}://${location.host}/ws`);
    ws.onopen = () => {
      ['home-conn-dot', 'chat-conn-dot'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.classList.add('on');
      });
      if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
    };
    ws.onclose = (e) => {
      ['home-conn-dot', 'chat-conn-dot'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.classList.remove('on');
      });
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

  function handleMessage(msg) {
    if (msg.type === 'init') {
      updateStats(msg.data.pi);
      updateSessions(msg.data.tmux);
      document.getElementById('version-badge').textContent = msg.data.version;
      document.getElementById('memory-content').textContent = msg.data.memory;
    }
    else if (msg.type === 'stats') {
      updateStats(msg.data.pi); updateSessions(msg.data.tmux);
      ['home-clock', 'chat-clock'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.textContent = msg.data.time;
      });
    }
    else if (msg.type === 'chat_thinking') { appendThinking(); }
    else if (msg.type === 'chat_chunk') { removeThinking(); appendChunk(msg.text); }
    else if (msg.type === 'chat_done') { finalizeStream(); document.getElementById('chat-send').disabled = false; }
    else if (msg.type === 'chat_reply') { removeThinking(); appendMessage(msg.text, 'bot'); document.getElementById('chat-send').disabled = false; }
    else if (msg.type === 'ollama_status') { /* ollama status ricevuto — info disponibile via provider dropdown */ }
    else if (msg.type === 'memory')   { document.getElementById('memory-content').textContent = msg.text; }
    else if (msg.type === 'history')  { document.getElementById('history-content').textContent = msg.text; }
    else if (msg.type === 'quickref') { document.getElementById('quickref-content').textContent = msg.text; }
    else if (msg.type === 'logs')    { renderLogs(msg.data); }
    else if (msg.type === 'cron')    { renderCron(msg.jobs); }
    else if (msg.type === 'tokens')  { renderTokens(msg.data); }
    else if (msg.type === 'briefing') { renderBriefing(msg.data); }
    else if (msg.type === 'crypto')   { renderCrypto(msg.data); }
    else if (msg.type === 'toast')   { showToast(msg.text); }
    else if (msg.type === 'reboot_ack') { startRebootWait(); }
    else if (msg.type === 'shutdown_ack') { document.getElementById('reboot-overlay').classList.add('show'); document.getElementById('reboot-status').textContent = 'Il Pi si sta spegnendo…'; document.querySelector('.reboot-text').textContent = 'Spegnimento in corso…'; }
    else if (msg.type === 'claude_thinking') {
      const wrap = document.getElementById('claude-output-wrap');
      if (wrap) wrap.style.display = 'block';
      const out = document.getElementById('claude-output');
      if (out) { out.innerHTML = ''; out.appendChild(document.createTextNode('Connessione al bridge...\n')); }
    }
    else if (msg.type === 'claude_chunk') {
      const out = document.getElementById('claude-output');
      if (out) { out.appendChild(document.createTextNode(msg.text)); out.scrollTop = out.scrollHeight; }
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
  }

  // ── Storico campioni per grafico ──
  const MAX_SAMPLES = 180; // 180 campioni x 5s = 15 minuti di storia
  const cpuHistory = [];
  const tempHistory = [];

  function updateStats(pi) {
    const cpuPct = pi.cpu_val || 0;
    const tempC = pi.temp_val || 0;
    const memPct = pi.mem_pct || 0;

    // ── Home cards ──
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

    // Barre progresso
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
      tempBar.style.background = tempC > 70 ? 'var(--red)' : tempC > 55 ? 'var(--amber)' : 'var(--amber)';
    }

    // ── Stats detail (sezione servizi) ──
    const sc = document.getElementById('stat-cpu');    if (sc) sc.textContent = pi.cpu || '—';
    const st = document.getElementById('stat-temp');   if (st) st.textContent = pi.temp || '—';
    const sm = document.getElementById('stat-mem');    if (sm) sm.textContent = pi.mem || '—';
    const sd = document.getElementById('stat-disk');   if (sd) sd.textContent = pi.disk || '—';
    const su = document.getElementById('stat-uptime'); if (su) su.textContent = pi.uptime || '—';

    // ── Health dots (tutti) ──
    ['home-health-dot', 'chat-health-dot'].forEach(id => {
      const el = document.getElementById(id);
      if (el) {
        el.className = 'health-dot ' + (pi.health || '');
        el.title = pi.health === 'red' ? 'ATTENZIONE' : pi.health === 'yellow' ? 'Sotto controllo' : 'Tutto OK';
      }
    });

    // ── Chat compact temp ──
    const chatTemp = document.getElementById('chat-temp');
    if (chatTemp) chatTemp.textContent = pi.temp || '--';

    // ── Storico per grafico ──
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
    // Griglia
    ctx.strokeStyle = 'rgba(0,255,65,0.08)';
    ctx.lineWidth = 1;
    for (let y = 0; y <= h; y += h / 4) {
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
    }
    if (cpuHistory.length < 2) return;
    // Disegna linea
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
    if (!sessions || !sessions.length) {
      el.innerHTML = '<div class="no-items">// nessuna sessione attiva</div>'; return;
    }
    el.innerHTML = sessions.map(s => `
      <div class="session-item">
        <div class="session-name"><div class="session-dot"></div><code>${esc(s.name)}</code></div>
        <button class="btn-red" onclick="killSession('${esc(s.name)}')">✕ Kill</button>
      </div>`).join('');
  }

  // ── Vista corrente + Chat ──
  let currentView = 'home';
  let chatProvider = 'local';
  let streamDiv = null;

  // ── Transizione Home → Chat ──
  function switchToChat() {
    if (currentView === 'chat') return;
    currentView = 'chat';

    const homeView = document.getElementById('home-view');
    const chatView = document.getElementById('chat-view');

    // Sposta input + provider + send nel chat view
    const chatInputRow = document.getElementById('chat-input-row-v2');
    chatInputRow.appendChild(document.getElementById('chat-input'));
    chatInputRow.appendChild(document.getElementById('provider-dropdown'));
    chatInputRow.appendChild(document.getElementById('chat-send'));

    // Switch viste
    homeView.style.display = 'none';
    chatView.style.display = 'flex';
    chatView.classList.add('active');
    chatView.classList.add('entering');
    setTimeout(() => chatView.classList.remove('entering'), 250);

    const msgs = document.getElementById('chat-messages');
    msgs.scrollTop = msgs.scrollHeight;
    document.getElementById('chat-input').focus();
  }

  // ── Transizione Chat → Home ──
  function goHome() {
    if (currentView === 'home') return;
    currentView = 'home';

    const homeView = document.getElementById('home-view');
    const chatView = document.getElementById('chat-view');

    // Sposta input + provider + send nella home
    const homeInputRow = document.getElementById('home-input-row');
    homeInputRow.appendChild(document.getElementById('chat-input'));
    homeInputRow.appendChild(document.getElementById('provider-dropdown'));
    homeInputRow.appendChild(document.getElementById('chat-send'));

    // Switch viste
    chatView.style.display = 'none';
    chatView.classList.remove('active');
    homeView.style.display = 'flex';

    // Ridisegna il canvas (potrebbe aver perso dimensioni)
    requestAnimationFrame(() => drawChart());
  }

  // ── Provider dropdown ──
  function toggleProviderMenu() {
    document.getElementById('provider-dropdown').classList.toggle('open');
  }
  function switchProvider(provider) {
    chatProvider = provider;
    const dot = document.getElementById('provider-dot');
    const label = document.getElementById('provider-short');
    const names = { cloud: 'Haiku', local: 'Local', pc_coder: 'PC Coder', pc_deep: 'PC Deep', deepseek: 'Deep' };
    const dotClass = { cloud: 'dot-cloud', local: 'dot-local', pc_coder: 'dot-pc-coder', pc_deep: 'dot-pc-deep', deepseek: 'dot-deepseek' };
    dot.className = 'provider-dot ' + (dotClass[provider] || 'dot-local');
    label.textContent = names[provider] || 'Local';
    document.getElementById('provider-dropdown').classList.remove('open');
  }
  // Chiudi dropdown quando click fuori
  document.addEventListener('click', (e) => {
    const dd = document.getElementById('provider-dropdown');
    if (dd && !dd.contains(e.target)) dd.classList.remove('open');
  });

  // ── Home services toggle ──
  function toggleHomeServices() {
    const svc = document.getElementById('home-services');
    const btn = document.getElementById('home-svc-toggle');
    svc.classList.toggle('open');
    btn.classList.toggle('open');
  }

  // ── Focus input → chat mode (solo mobile) ──
  document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('chat-input').addEventListener('focus', () => {
      if (window.innerWidth < 768) switchToChat();
    });
  });

  // ── Tastiera virtuale: mantieni input visibile (stile Claude iOS) ──
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
        // Scrolla chat ai messaggi più recenti
        const msgs = document.getElementById('chat-messages');
        if (msgs) msgs.scrollTop = msgs.scrollHeight;
      });
    };
    window.visualViewport.addEventListener('resize', handleVV);
    window.visualViewport.addEventListener('scroll', handleVV);
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

  function sendChat() {
    const input = document.getElementById('chat-input');
    const text = (input.textContent || '').trim();
    if (!text) return;
    switchToChat();
    appendMessage(text, 'user');
    send({ action: 'chat', text, provider: chatProvider });
    input.textContent = '';
    document.getElementById('chat-send').disabled = true;
  }
  document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('chat-input').addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(); }
    });
  });
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

  /* toggleStatusDetail e updateStatusBar rimossi — home cards aggiornate da updateStats */

  // ── Drawer (bottom sheet) ──
  let activeDrawer = null;
  const DRAWER_CFG = {
    briefing: { title: '▤ Morning Briefing', actions: '<button class="btn-ghost" onclick="loadBriefing(this)">Carica</button><button class="btn-green" onclick="runBriefing(this)">▶ Genera</button>' },
    crypto:   { title: '₿ Crypto', actions: '<button class="btn-ghost" onclick="loadCrypto(this)">Carica</button>' },
    tokens:   { title: '¤ Token & API', actions: '<button class="btn-ghost" onclick="loadTokens(this)">Carica</button>' },
    logs:     { title: '≡ Log Nanobot', actions: '<button class="btn-ghost" onclick="loadLogs(this)">Carica</button>' },
    cron:     { title: '◇ Task schedulati', actions: '<button class="btn-ghost" onclick="loadCron(this)">Carica</button>' },
    claude:   { title: '>_ Remote Code', actions: '<span id="bridge-dot" class="health-dot" title="Bridge" style="width:8px;height:8px;"></span><button class="btn-ghost" onclick="loadBridge(this)">Carica</button>' },
    memoria:  { title: '◎ Memoria', actions: '' }
  };
  function openDrawer(widgetId) {
    // Toggle: se clicchi lo stesso tab, chiudi
    if (activeDrawer === widgetId) { closeDrawer(); return; }
    // Hide all, show target
    document.querySelectorAll('.drawer-widget').forEach(w => w.classList.remove('active'));
    const dw = document.getElementById('dw-' + widgetId);
    if (dw) dw.classList.add('active');
    // Header
    const cfg = DRAWER_CFG[widgetId];
    document.getElementById('drawer-title').textContent = cfg ? cfg.title : widgetId;
    document.getElementById('drawer-actions').innerHTML =
      (cfg ? cfg.actions : '') +
      '<button class="btn-ghost" onclick="closeDrawer()" style="min-height:28px;padding:3px 8px;">✕</button>';
    // Show overlay + enable two-column on desktop
    document.getElementById('drawer-overlay').classList.add('show');
    document.querySelector('.app-content').classList.add('has-drawer');
    // Tab bar highlight
    document.querySelectorAll('.tab-bar-btn').forEach(b =>
      b.classList.toggle('active', b.dataset.widget === widgetId));
    activeDrawer = widgetId;
  }
  function closeDrawer() {
    document.getElementById('drawer-overlay').classList.remove('show');
    document.querySelector('.app-content').classList.remove('has-drawer');
    document.querySelectorAll('.tab-bar-btn').forEach(b => b.classList.remove('active'));
    activeDrawer = null;
  }

  // ── Drawer swipe-down to close (mobile) ──
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

  // Escape chiude chat view / drawer / overlay
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      if (currentView === 'chat') goHome();
      else if (activeDrawer) closeDrawer();
      const outFs = document.getElementById('output-fullscreen');
      if (outFs && outFs.classList.contains('show')) closeOutputFullscreen();
    }
  });

  // ── On-demand widget loaders ──
  function loadTokens(btn) {
    if (btn) btn.textContent = '…';
    send({ action: 'get_tokens' });
  }
  function loadLogs(btn) {
    if (btn) btn.textContent = '…';
    const dateEl = document.getElementById('log-date-filter');
    const searchEl = document.getElementById('log-search-filter');
    const dateVal = dateEl ? dateEl.value : '';
    const searchVal = searchEl ? searchEl.value.trim() : '';
    send({ action: 'get_logs', date: dateVal, search: searchVal });
  }
  function loadCron(btn) {
    if (btn) btn.textContent = '…';
    send({ action: 'get_cron' });
  }
  function loadBriefing(btn) {
    if (btn) btn.textContent = '…';
    send({ action: 'get_briefing' });
  }
  function runBriefing(btn) {
    if (btn) btn.textContent = '…';
    send({ action: 'run_briefing' });
  }

  function loadCrypto(btn) {
    if (btn) btn.textContent = '…';
    send({ action: 'get_crypto' });
  }

  function renderCrypto(data) {
    const el = document.getElementById('crypto-body');
    if (data.error && !data.btc) {
      el.innerHTML = `<div class="no-items">// errore: ${esc(data.error)}</div>
        <div style="margin-top:8px;text-align:center;"><button class="btn-ghost" onclick="loadCrypto()">↻ Riprova</button></div>`;
      return;
    }
    function coinRow(symbol, label, d) {
      if (!d) return '';
      const arrow = d.change_24h >= 0 ? '▲' : '▼';
      const color = d.change_24h >= 0 ? 'var(--green)' : 'var(--red)';
      return `
        <div style="display:flex;align-items:center;justify-content:space-between;background:var(--bg2);border:1px solid var(--border);border-radius:4px;padding:10px 12px;margin-bottom:6px;">
          <div>
            <div style="font-size:13px;font-weight:700;color:var(--amber);">${symbol} ${label}</div>
            <div style="font-size:10px;color:var(--muted);margin-top:2px;">€${d.eur.toLocaleString()}</div>
          </div>
          <div style="text-align:right;">
            <div style="font-size:15px;font-weight:700;color:var(--green);">$${d.usd.toLocaleString()}</div>
            <div style="font-size:11px;color:${color};margin-top:2px;">${arrow} ${Math.abs(d.change_24h)}%</div>
          </div>
        </div>`;
    }
    el.innerHTML = coinRow('₿', 'Bitcoin', data.btc) + coinRow('Ξ', 'Ethereum', data.eth) +
      '<div style="margin-top:4px;"><button class="btn-ghost" onclick="loadCrypto()">↻ Aggiorna</button></div>';
  }

  function renderBriefing(data) {
    const el = document.getElementById('briefing-body');
    if (!data.last) {
      el.innerHTML = '<div class="no-items">// nessun briefing generato ancora</div>' +
        '<div style="margin-top:8px;text-align:center;"><button class="btn-green" onclick="runBriefing()">▶ Genera ora</button></div>';
      return;
    }
    const b = data.last;
    const ts = b.ts ? b.ts.replace('T', ' ') : '—';
    const weather = b.weather || '—';
    const calToday = b.calendar_today || [];
    const calTomorrow = b.calendar_tomorrow || [];
    const calTodayHtml = calToday.length > 0
      ? calToday.map(e => {
          const loc = e.location ? ` <span style="color:var(--muted)">@ ${esc(e.location)}</span>` : '';
          return `<div style="margin:3px 0;font-size:11px;"><span style="color:var(--cyan);font-weight:600">${esc(e.time)}</span> <span style="color:var(--text2)">${esc(e.summary)}</span>${loc}</div>`;
        }).join('')
      : '<div style="font-size:11px;color:var(--muted);font-style:italic">Nessun evento oggi</div>';
    const calTomorrowHtml = calTomorrow.length > 0
      ? `<div style="font-size:10px;color:var(--muted);margin-top:8px;margin-bottom:4px">📅 DOMANI (${calTomorrow.length} eventi)</div>` +
        calTomorrow.map(e =>
          `<div style="margin:2px 0;font-size:10px;color:var(--text2)"><span style="color:var(--cyan)">${esc(e.time)}</span> ${esc(e.summary)}</div>`
        ).join('')
      : '';
    const stories = (b.stories || []).map((s, i) =>
      `<div style="margin:4px 0;font-size:11px;color:var(--text2);">${i+1}. ${esc(s.title)}</div>`
    ).join('');
    el.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
        <div style="font-size:10px;color:var(--muted);">ULTIMO: <span style="color:var(--amber)">${ts}</span></div>
        <div style="font-size:10px;color:var(--muted);">PROSSIMO: <span style="color:var(--cyan)">${data.next_run || '07:30'}</span></div>
      </div>
      <div style="background:var(--bg2);border:1px solid var(--border);border-radius:4px;padding:9px 11px;margin-bottom:8px;">
        <div style="font-size:11px;color:var(--amber);margin-bottom:8px;">🌤 ${esc(weather)}</div>
        <div style="font-size:10px;color:var(--muted);margin-bottom:4px;">📅 CALENDARIO OGGI</div>
        ${calTodayHtml}
        ${calTomorrowHtml}
        <div style="font-size:10px;color:var(--muted);margin-top:8px;margin-bottom:4px;">📰 TOP HACKERNEWS</div>
        ${stories}
      </div>
      <div style="display:flex;gap:6px;">
        <button class="btn-ghost" onclick="loadBriefing()">↻ Aggiorna</button>
        <button class="btn-green" onclick="runBriefing()">▶ Genera nuovo</button>
        <button class="btn-ghost" onclick="copyToClipboard(document.getElementById('briefing-body').textContent)">📋 Copia</button>
      </div>`;
  }

  function renderTokens(data) {
    const src = data.source === 'api' ? '🌐 Anthropic API' : '📁 Log locale';
    document.getElementById('tokens-body').innerHTML = `
      <div class="token-grid">
        <div class="token-item"><div class="token-label">Input oggi</div><div class="token-value">${(data.today_input||0).toLocaleString()}</div></div>
        <div class="token-item"><div class="token-label">Output oggi</div><div class="token-value">${(data.today_output||0).toLocaleString()}</div></div>
        <div class="token-item"><div class="token-label">Chiamate</div><div class="token-value">${data.total_calls||0}</div></div>
      </div>
      <div style="margin-bottom:6px;font-size:10px;color:var(--muted);">
        MODELLO: <span style="color:var(--cyan)">${esc(data.last_model||'N/A')}</span>
        &nbsp;·&nbsp; FONTE: <span style="color:var(--text2)">${src}</span>
      </div>
      <div class="mono-block" style="max-height:100px;">${(data.log_lines||[]).map(l=>esc(l)).join('\n')||'// nessun log disponibile'}</div>
      <div style="margin-top:8px;display:flex;gap:6px;"><button class="btn-ghost" onclick="loadTokens()">↻ Aggiorna</button><button class="btn-ghost" onclick="copyToClipboard(document.getElementById('tokens-body').textContent)">📋 Copia</button></div>`;
  }

  function renderLogs(data) {
    const el = document.getElementById('logs-body');
    // data può essere stringa (vecchio formato) o oggetto {lines, total, filtered}
    if (typeof data === 'string') {
      el.innerHTML = `<div class="mono-block" style="max-height:200px;">${esc(data)||'(nessun log)'}</div>
        <div style="margin-top:8px;display:flex;gap:6px;"><button class="btn-ghost" onclick="loadLogs()">↻ Aggiorna</button><button class="btn-ghost" onclick="copyToClipboard(document.querySelector('#logs-body .mono-block')?.textContent||'')">📋 Copia</button></div>`;
      return;
    }
    const dateVal = document.getElementById('log-date-filter')?.value || '';
    const searchVal = document.getElementById('log-search-filter')?.value || '';
    const lines = data.lines || [];
    const total = data.total || 0;
    const filtered = data.filtered || 0;
    const countInfo = (dateVal || searchVal)
      ? `<span style="color:var(--amber)">${filtered}</span> / ${total} righe`
      : `${total} righe totali`;
    // Evidenzia testo cercato nelle righe
    let content = lines.length ? lines.map(l => {
      if (searchVal) {
        const re = new RegExp('(' + searchVal.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'gi');
        return l.replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(re, '<span style="background:var(--green-dim);color:var(--green);font-weight:700;">$1</span>');
      }
      return l.replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }).join('\n') : '(nessun log corrispondente)';
    el.innerHTML = `
      <div style="display:flex;gap:6px;margin-bottom:8px;flex-wrap:wrap;align-items:center;">
        <input type="date" id="log-date-filter" value="${dateVal}" tabindex="-1"
          style="background:var(--bg2);border:1px solid var(--border2);border-radius:4px;color:var(--amber);padding:5px 8px;font-family:var(--font);font-size:11px;outline:none;min-height:32px;">
        <input type="text" id="log-search-filter" placeholder="🔍 cerca…" value="${searchVal}" tabindex="-1"
          style="flex:1;min-width:120px;background:var(--bg2);border:1px solid var(--border2);border-radius:4px;color:var(--green);padding:5px 8px;font-family:var(--font);font-size:11px;outline:none;min-height:32px;">
        <button class="btn-green" onclick="loadLogs()" style="min-height:32px;">🔍 Filtra</button>
        <button class="btn-ghost" onclick="clearLogFilters()" style="min-height:32px;">✕ Reset</button>
      </div>
      <div style="font-size:10px;color:var(--muted);margin-bottom:6px;">${countInfo}</div>
      <div class="mono-block" style="max-height:240px;">${content}</div>
      <div style="margin-top:8px;display:flex;gap:6px;"><button class="btn-ghost" onclick="loadLogs()">↻ Aggiorna</button><button class="btn-ghost" onclick="copyToClipboard(document.querySelector('#logs-body .mono-block')?.textContent||'')">📋 Copia</button></div>`;
    // Enter su campo ricerca = filtra
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
    const el = document.getElementById('cron-body');
    const jobList = (jobs && jobs.length) ? '<div class="cron-list">' + jobs.map((j, i) => `
      <div class="cron-item" style="align-items:center;">
        <div class="cron-schedule">${j.schedule}</div>
        <div style="flex:1;"><div class="cron-cmd">${j.command}</div>${j.desc?`<div class="cron-desc">// ${j.desc}</div>`:''}</div>
        <button class="btn-red" style="padding:3px 8px;font-size:10px;min-height:28px;" onclick="deleteCron(${i})">✕</button>
      </div>`).join('') + '</div>'
      : '<div class="no-items">// nessun cron job configurato</div>';
    el.innerHTML = jobList + `
      <div style="margin-top:10px;border-top:1px solid var(--border);padding-top:10px;">
        <div style="font-size:10px;color:var(--muted);margin-bottom:6px;">AGGIUNGI TASK</div>
        <div style="display:flex;gap:6px;margin-bottom:6px;">
          <input id="cron-schedule" placeholder="30 7 * * *" tabindex="-1" style="width:120px;background:var(--bg2);border:1px solid var(--border2);border-radius:4px;color:var(--green);padding:6px 8px;font-family:var(--font);font-size:11px;outline:none;">
          <input id="cron-command" placeholder="python3.13 /path/to/script.py" tabindex="-1" style="flex:1;background:var(--bg2);border:1px solid var(--border2);border-radius:4px;color:var(--green);padding:6px 8px;font-family:var(--font);font-size:11px;outline:none;">
        </div>
        <div style="display:flex;gap:6px;">
          <button class="btn-green" onclick="addCron()">+ Aggiungi</button>
          <button class="btn-ghost" onclick="loadCron()">↻ Aggiorna</button>
        </div>
      </div>`;
  }
  function addCron() {
    const sched = document.getElementById('cron-schedule').value.trim();
    const cmd = document.getElementById('cron-command').value.trim();
    if (!sched || !cmd) { showToast('⚠️ Compila schedule e comando'); return; }
    send({ action: 'add_cron', schedule: sched, command: cmd });
  }
  function deleteCron(index) {
    send({ action: 'delete_cron', index: index });
  }

  // ── Remote Code ──
  let claudeRunning = false;

  function loadBridge(btn) {
    if (btn) btn.textContent = '...';
    send({ action: 'check_bridge' });
    send({ action: 'get_claude_tasks' });
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
    send({ action: 'claude_task', prompt: prompt });
  }

  function cancelClaudeTask() {
    send({ action: 'claude_cancel' });
  }

  function finalizeClaudeTask(data) {
    claudeRunning = false;
    const rb = document.getElementById('claude-run-btn');
    const cb = document.getElementById('claude-cancel-btn');
    if (rb) rb.disabled = false;
    if (cb) cb.style.display = 'none';
    const status = data.completed ? '✅ completato' : (data.exit_code === 0 ? '⚠️ incompleto' : '⚠️ errore');
    const dur = (data.duration_ms / 1000).toFixed(1);
    const iter = data.iterations > 1 ? ` (${data.iterations} iter)` : '';
    showToast(`Task ${status} in ${dur}s${iter}`);
    send({ action: 'get_claude_tasks' });
  }

  function renderBridgeStatus(data) {
    const dot = document.getElementById('bridge-dot');
    if (!dot) return;
    if (data.status === 'ok') {
      dot.className = 'health-dot green';
      dot.title = 'Bridge online';
    } else {
      dot.className = 'health-dot red';
      dot.title = 'Bridge offline';
    }
    // Se il body è ancora il placeholder, renderizza il form
    const body = document.getElementById('claude-body');
    if (body && body.querySelector('.widget-placeholder')) {
      renderClaudeUI(data.status === 'ok');
    }
  }

  function renderClaudeUI(isOnline) {
    const body = document.getElementById('claude-body');
    if (!body) return;
    body.innerHTML = `
      <div style="margin-bottom:10px;">
        <textarea id="claude-prompt" rows="3" placeholder="Descrivi il task per Claude Code..." tabindex="-1"
          style="width:100%;background:var(--bg2);border:1px solid var(--border2);border-radius:4px;
          color:var(--green);padding:9px 12px;font-family:var(--font);font-size:13px;
          outline:none;resize:vertical;caret-color:var(--green);min-height:60px;box-sizing:border-box;"></textarea>
        <div style="display:flex;gap:6px;margin-top:6px;">
          <button class="btn-green" id="claude-run-btn" onclick="runClaudeTask()"
            ${!isOnline ? 'disabled title="Bridge offline"' : ''}>▶ Esegui</button>
          <button class="btn-red" id="claude-cancel-btn" onclick="cancelClaudeTask()"
            style="display:none;">■ Stop</button>
          <button class="btn-ghost" onclick="loadBridge()">↻ Stato</button>
        </div>
      </div>
      <div id="claude-output-wrap" style="display:none;margin-bottom:10px;">
        <div class="claude-output-header">
          <span>OUTPUT</span>
          <div style="display:flex;gap:4px;">
            <button class="btn-ghost" style="padding:2px 8px;font-size:10px;min-height:24px;" onclick="copyClaudeOutput()">📋 Copia</button>
            <button class="btn-ghost" style="padding:2px 8px;font-size:10px;min-height:24px;" onclick="openOutputFullscreen()">⛶ Espandi</button>
          </div>
        </div>
        <div id="claude-output" class="claude-output"></div>
      </div>
      <div id="claude-tasks-list"></div>`;
  }

  function renderClaudeTasks(tasks) {
    // Se il body è ancora placeholder, renderizza prima il form
    const body = document.getElementById('claude-body');
    if (body && body.querySelector('.widget-placeholder')) {
      renderClaudeUI(document.getElementById('bridge-dot')?.classList.contains('green'));
    }
    const el = document.getElementById('claude-tasks-list');
    if (!el) return;
    if (!tasks || !tasks.length) {
      el.innerHTML = '<div class="no-items">// nessun task eseguito</div>';
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
            <span>${esc(ts)}</span>
            <span>${dur}</span>
          </div>
        </div>`;
      }).join('');
  }

  // ── Tabs ──
  function switchTab(name, btn) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('tab-' + name).classList.add('active');
    if (name === 'history') send({ action: 'get_history' });
    if (name === 'quickref') send({ action: 'get_quickref' });
  }

  // ── Misc ──
  // ── Collapsible cards ──
  function toggleCard(id) {
    const card = document.getElementById(id);
    if (card) card.classList.toggle('collapsed');
  }
  function expandCard(id) {
    const card = document.getElementById(id);
    if (card) card.classList.remove('collapsed');
  }

  function requestStats() { send({ action: 'get_stats' }); }
  function refreshMemory() { send({ action: 'get_memory' }); }
  function refreshHistory() { send({ action: 'get_history' }); }
  function killSession(name) { send({ action: 'tmux_kill', session: name }); }
  function gatewayRestart() { showToast('⏳ Riavvio gateway…'); send({ action: 'gateway_restart' }); }

  // ── Reboot / Shutdown ──
  function showRebootModal() {
    document.getElementById('reboot-modal').classList.add('show');
  }
  function hideRebootModal() {
    document.getElementById('reboot-modal').classList.remove('show');
  }
  function confirmReboot() {
    hideRebootModal();
    send({ action: 'reboot' });
  }
  function showShutdownModal() {
    document.getElementById('shutdown-modal').classList.add('show');
  }
  function hideShutdownModal() {
    document.getElementById('shutdown-modal').classList.remove('show');
  }
  function confirmShutdown() {
    hideShutdownModal();
    send({ action: 'shutdown' });
  }
  function startRebootWait() {
    document.getElementById('reboot-overlay').classList.add('show');
    const statusEl = document.getElementById('reboot-status');
    let seconds = 0;
    const timer = setInterval(() => {
      seconds++;
      statusEl.textContent = `Attesa: ${seconds}s — tentativo riconnessione…`;
    }, 1000);
    // Tenta di riconnettersi ogni 3 secondi
    const tryReconnect = setInterval(() => {
      fetch('/', { method: 'HEAD', cache: 'no-store' })
        .then(r => {
          if (r.ok) {
            clearInterval(timer);
            clearInterval(tryReconnect);
            document.getElementById('reboot-overlay').classList.remove('show');
            showToast('✅ Pi riavviato con successo');
            // Riconnetti WebSocket
            if (ws) { try { ws.close(); } catch(e) {} }
            connect();
          }
        })
        .catch(() => {});
    }, 3000);
    // Timeout massimo: 2 minuti
    setTimeout(() => {
      clearInterval(timer);
      clearInterval(tryReconnect);
      statusEl.textContent = 'Timeout — il Pi potrebbe non essere raggiungibile. Ricarica la pagina manualmente.';
    }, 120000);
  }

  function showToast(text) {
    const el = document.getElementById('toast');
    el.textContent = text; el.classList.add('show');
    const ms = Math.max(2500, Math.min(text.length * 60, 6000));
    setTimeout(() => el.classList.remove('show'), ms);
  }

  function copyToClipboard(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(() => showToast('📋 Copiato'))
        .catch(() => _fallbackCopy(text));
    } else { _fallbackCopy(text); }
  }
  function _fallbackCopy(text) {
    const ta = document.createElement('textarea');
    ta.value = text; ta.style.cssText = 'position:fixed;left:-9999px;top:-9999px;';
    document.body.appendChild(ta); ta.select();
    try { document.execCommand('copy'); showToast('📋 Copiato'); }
    catch(e) { showToast('Copia non riuscita'); }
    document.body.removeChild(ta);
  }

  // ── Remote Code output helpers ──
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

  setInterval(() => {
    const t = new Date().toLocaleTimeString('it-IT');
    ['home-clock', 'chat-clock'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.textContent = t;
    });
  }, 1000);

  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js').catch(() => {});
  }

  connect();