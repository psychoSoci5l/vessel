  // ── Widget: Logs ──
  function loadLogs(btn) {
    if (btn) btn.textContent = '…';
    const dateEl = document.getElementById('log-date-filter');
    const searchEl = document.getElementById('log-search-filter');
    send({ action: 'get_logs', date: dateEl ? dateEl.value : '', search: searchEl ? searchEl.value.trim() : '' });
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
        return l.replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(re, '<span style="background:var(--accent-dim);color:var(--accent);font-weight:700;">$1</span>');
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
