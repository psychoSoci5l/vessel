  // ── Widget: Remote Code ──
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
        <textarea id="claude-prompt" rows="6" placeholder="Descrivi il task..."
          oninput="updateCategoryBadge()"
          style="width:100%;background:var(--bg2);border:1px solid var(--border2);border-radius:6px;color:var(--green);padding:10px 12px;font-family:var(--font);font-size:13px;outline:none;resize:vertical;caret-color:var(--green);min-height:120px;box-sizing:border-box;"></textarea>
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
    const list = tasks.slice().reverse().slice(0, 8);
    el.innerHTML = '<div style="font-size:10px;color:var(--muted);margin-bottom:6px;">ULTIMI TASK</div>' +
      '<div class="claude-tasks-scroll">' +
      list.map(t => {
        const dur = t.duration_ms ? (t.duration_ms/1000).toFixed(1)+'s' : '';
        const ts = (t.ts || '').replace('T', ' ');
        return `<div class="claude-task-item" onclick="copyToClipboard(this.querySelector('.claude-task-prompt').textContent)" style="cursor:pointer;" title="Click per copiare">
          <div class="claude-task-prompt">${esc(t.prompt)}</div>
          <div class="claude-task-meta">
            <span class="claude-task-status ${esc(t.status)}">${esc(t.status)}</span>
            <span>${esc(ts)}</span><span>${dur}</span>
          </div>
        </div>`;
      }).join('') + '</div>';
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
