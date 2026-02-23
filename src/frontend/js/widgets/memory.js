  // ── Widget: Memory ──
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
