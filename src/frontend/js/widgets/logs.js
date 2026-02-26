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
        <input type="text" id="log-search-filter" placeholder="> cerca…" value="${searchVal}" class="input-field">
        <button class="btn-green btn-sm" onclick="loadLogs()">></button>
        <button class="btn-ghost btn-sm" onclick="clearLogFilters()">✕</button>
      </div>
      <div style="font-size:10px;color:var(--muted);margin-bottom:6px;">${countInfo}</div>
      <div class="mono-block" style="max-height:240px;">${content}</div>
      <div style="margin-top:8px;display:flex;gap:6px;"><button class="btn-ghost btn-sm" onclick="loadLogs()">↻</button><button class="btn-ghost btn-sm" onclick="copyToClipboard(document.querySelector('#logs-body .mono-block')?.textContent||'')">[cp]</button></div>`;
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

  // ── Chat history diagnostica ──
  async function loadChatHistory(date) {
    const el = document.getElementById('logs-body');
    if (!el) return;
    el.innerHTML = '<div class="mono-block" style="color:var(--muted)">Caricamento…</div>';
    const d = date || new Date().toISOString().slice(0, 10);
    try {
      const r = await fetch('/api/chat/history?channel=dashboard&date=' + d + '&limit=100');
      const data = await r.json();
      renderChatHistory(data.messages || [], d);
    } catch(e) {
      el.innerHTML = '<div class="mono-block">Errore: ' + esc(String(e)) + '</div>';
    }
  }

  function renderChatHistory(messages, date) {
    const el = document.getElementById('logs-body');
    if (!el) return;
    let rows = '';
    if (!messages.length) {
      rows = '<div class="no-items">Nessun messaggio per ' + esc(date) + '</div>';
    } else {
      rows = messages.map(m => {
        const roleColor = m.role === 'user' ? 'var(--accent2)' : 'var(--accent)';
        const pruned = m.ctx_pruned
          ? ' <span class="badge badge-amber" title="Contesto troncato prima dell\'invio">prune</span>' : '';
        const memTags = (m.mem_types || []).map(t =>
          `<span class="badge badge-muted">${esc(t)}</span>`).join(' ');
        const meta = m.role === 'assistant' ? `
          <div style="font-size:9px;color:var(--muted);margin-top:3px;display:flex;flex-wrap:wrap;gap:4px;">
            ${m.model ? '<span>' + esc(m.model) + '</span>' : ''}
            ${m.tokens_in ? '<span>' + m.tokens_in + '+' + m.tokens_out + 't</span>' : ''}
            ${m.latency_ms ? '<span>' + m.latency_ms + 'ms</span>' : ''}
            ${m.sys_hash ? '<span>sys:' + esc(m.sys_hash) + '</span>' : ''}
            ${pruned} ${memTags}
          </div>` : '';
        const snippet = (m.content || '').slice(0, 280);
        const more = (m.content || '').length > 280 ? '…' : '';
        return `<div style="border-bottom:1px solid var(--border);padding:6px 0;">
          <div style="font-size:9px;color:var(--muted);">
            ${esc((m.ts||'').replace('T',' '))}
            <span style="color:${roleColor};">[${esc(m.role)}]</span>
            ${m.provider ? '· ' + esc(m.provider) : ''}
          </div>
          <div style="font-size:11px;margin-top:3px;white-space:pre-wrap;word-break:break-word;">${esc(snippet)}${more}</div>
          ${meta}
        </div>`;
      }).join('');
    }
    el.innerHTML = `
      <div style="display:flex;gap:6px;margin-bottom:8px;align-items:center;">
        <input type="date" id="chat-hist-date" value="${esc(date)}" class="input-field input-date" style="flex:1;min-width:130px;">
        <button class="btn-green btn-sm" onclick="loadChatHistory(document.getElementById('chat-hist-date').value)">></button>
        <button class="btn-ghost btn-sm" onclick="loadLogs()">Logs</button>
      </div>
      <div style="max-height:280px;overflow-y:auto;">${rows}</div>`;
  }
