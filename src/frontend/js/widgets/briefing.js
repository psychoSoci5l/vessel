  // ── Widget: Briefing ──
  function loadBriefing(btn) { if (btn) btn.textContent = '…'; send({ action: 'get_briefing' }); }
  function runBriefing(btn) { if (btn) btn.textContent = '…'; send({ action: 'run_briefing' }); }

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
