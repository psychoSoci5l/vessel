  // ── Widget: Analytics (Fase 62) ──────────────────────────────────────────────
  const _anlProviderNames = {
    anthropic: 'Haiku', openrouter: 'OpenRouter', ollama: 'Local',
    ollama_pc: 'PC', brain: 'Brain', unknown: '?'
  };
  const _anlProviderColors = {
    anthropic: 'var(--accent)', openrouter: 'var(--amber)', ollama: 'var(--muted)',
    ollama_pc: 'var(--cyan)', brain: 'var(--red)'
  };

  let _anlPeriod = 'day';

  function loadAnalytics(period) {
    if (period) _anlPeriod = period;
    document.querySelectorAll('.anl-period-btn').forEach(b => {
      b.classList.toggle('active', b.dataset.period === _anlPeriod);
    });
    const el = document.getElementById('analytics-content');
    if (el) el.innerHTML = '<div class="no-items">// caricamento\u2026</div>';
    send({ action: 'get_analytics', period: _anlPeriod });
    send({ action: 'get_heatmap', days: 7 });
  }

  function renderAnalytics(data) {
    const el = document.getElementById('analytics-content');
    if (!el) return;
    let html = '';

    // ── Token Usage ──
    const usage = data.token_usage || [];
    const tot = data.token_total || {};
    html += '<div class="anl-section-label">TOKEN USAGE</div>';
    if (!usage.length) {
      html += '<div class="no-items">// nessun dato nel periodo</div>';
    } else {
      const maxTot = Math.max(...usage.map(r => (r.input || 0) + (r.output || 0)), 1);
      const fmt = n => n >= 1000000 ? (n/1000000).toFixed(1) + 'M' : n >= 1000 ? (n/1000).toFixed(1) + 'K' : String(n);
      html += '<div class="anl-bars">';
      usage.forEach(r => {
        const name = _anlProviderNames[r.provider] || r.provider;
        const color = _anlProviderColors[r.provider] || 'var(--text2)';
        const total = (r.input || 0) + (r.output || 0);
        const pct = Math.round((total / maxTot) * 100);
        html += `<div class="anl-bar-row">
          <span class="anl-bar-label" style="color:${color};">${esc(name)}</span>
          <div class="anl-bar-track"><div class="anl-bar-fill" style="width:${pct}%;background:${color};"></div></div>
          <span class="anl-bar-val">${fmt(total)}</span>
        </div>`;
      });
      html += '</div>';
      html += `<div class="anl-total">Totale periodo: <span>${fmt((tot.input||0)+(tot.output||0))} tok · ${tot.calls||0} call</span></div>`;
    }

    // ── Latency ──
    const latency = data.latency || [];
    html += '<div class="anl-section-label" style="margin-top:14px;">LATENZA MEDIA</div>';
    if (!latency.length) {
      html += '<div class="no-items">// nessun dato nel periodo</div>';
    } else {
      const maxMs = Math.max(...latency.map(r => r.max_ms || 0), 1);
      html += '<div class="anl-bars">';
      latency.forEach(r => {
        const name = _anlProviderNames[r.provider] || r.provider;
        const color = _anlProviderColors[r.provider] || 'var(--text2)';
        const pct = Math.round((r.avg_ms / maxMs) * 100);
        const avgSec = r.avg_ms >= 1000 ? (r.avg_ms / 1000).toFixed(1) + 's' : r.avg_ms + 'ms';
        html += `<div class="anl-bar-row">
          <span class="anl-bar-label" style="color:${color};">${esc(name)}</span>
          <div class="anl-bar-track"><div class="anl-bar-fill" style="width:${pct}%;background:${color};opacity:0.7;"></div></div>
          <span class="anl-bar-val">${avgSec}</span>
        </div>`;
      });
      html += '</div>';
    }

    // ── Error Rate ──
    const errors = (data.errors || []).filter(r => r.total > 0);
    html += '<div class="anl-section-label" style="margin-top:14px;">ERROR RATE</div>';
    if (!errors.length) {
      html += '<div class="no-items">// nessun errore nel periodo</div>';
    } else {
      html += '<div class="anl-error-row">';
      errors.forEach(r => {
        const name = _anlProviderNames[r.provider] || r.provider;
        const pct = Math.round((r.rate || 0) * 100);
        const bad = pct > 5;
        html += `<div class="anl-error-badge ${bad ? 'anl-error-bad' : ''}">
          <span class="anl-error-name">${esc(name)}</span>
          <span class="anl-error-pct">${pct}%</span>
          <span class="anl-error-detail">${r.count}/${r.total}</span>
        </div>`;
      });
      html += '</div>';
    }

    // ── Failover Log ──
    const failovers = data.failovers || [];
    html += '<div class="anl-section-label" style="margin-top:14px;">FAILOVER RECENTI</div>';
    if (!failovers.length) {
      html += '<div class="no-items">// nessun failover registrato</div>';
    } else {
      html += '<div class="anl-failover-list">';
      failovers.forEach(f => {
        const ts = (f.ts || '').slice(0, 16).replace('T', ' ');
        const route = f.resource || f.route || '';
        const reason = (f.details || f.reason || '').slice(0, 80);
        html += `<div class="anl-failover-item">
          <span class="anl-fail-ts">${esc(ts)}</span>
          <span class="anl-fail-route">${esc(route)}</span>
          ${reason ? `<span class="anl-fail-reason">${esc(reason)}</span>` : ''}
        </div>`;
      });
      html += '</div>';
    }

    // ── Heatmap placeholder (riempito da renderHeatmap) ──
    html += '<div class="anl-section-label" style="margin-top:14px;">ATTIVITA\' ULTIMI 7 GIORNI</div>';
    html += '<div id="anl-heatmap-wrap"><div class="no-items">// caricamento\u2026</div></div>';

    el.innerHTML = html;
  }

  function renderHeatmap(data) {
    const wrap = document.getElementById('anl-heatmap-wrap');
    if (!wrap) return;
    const matrix = data.matrix || [];
    const maxVal = data.max || 1;
    const labels = data.labels || [];
    const days = matrix.length;
    if (!days) { wrap.innerHTML = '<div class="no-items">// nessun dato</div>'; return; }

    const CELL = 13, GAP = 2;
    const labelW = 30, labelH = 16;
    const w = labelW + 24 * (CELL + GAP);
    const h = labelH + days * (CELL + GAP);

    const canvas = document.createElement('canvas');
    const dpr = window.devicePixelRatio || 1;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    canvas.style.width = w + 'px';
    canvas.style.height = h + 'px';
    canvas.style.display = 'block';
    canvas.style.maxWidth = '100%';

    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);
    const cs = getComputedStyle(document.documentElement);
    const accentRaw = cs.getPropertyValue('--accent').trim();
    const mutedColor = cs.getPropertyValue('--muted').trim();
    const borderColor = cs.getPropertyValue('--border').trim();

    // Sfondo
    ctx.fillStyle = cs.getPropertyValue('--card').trim() || '#111';
    ctx.fillRect(0, 0, w, h);

    // Label ore (0, 6, 12, 18, 23)
    ctx.fillStyle = mutedColor;
    ctx.font = `9px "JetBrains Mono", monospace`;
    ctx.textBaseline = 'top';
    [0, 6, 12, 18, 23].forEach(hr => {
      const x = labelW + hr * (CELL + GAP);
      ctx.fillText(String(hr).padStart(2, '0'), x, 0);
    });

    // Label giorni + celle
    for (let d = 0; d < days; d++) {
      const y = labelH + d * (CELL + GAP);
      // Label giorno
      ctx.fillStyle = mutedColor;
      ctx.textBaseline = 'middle';
      ctx.font = `9px "JetBrains Mono", monospace`;
      ctx.fillText((labels[d] || '').slice(0, 3), 0, y + CELL / 2);
      // Celle ore
      for (let hr = 0; hr < 24; hr++) {
        const x = labelW + hr * (CELL + GAP);
        const count = (matrix[d] && matrix[d][hr]) || 0;
        const intensity = maxVal > 0 ? count / maxVal : 0;
        if (intensity > 0) {
          // Interpola colore accent con opacity
          ctx.globalAlpha = 0.15 + intensity * 0.85;
          ctx.fillStyle = accentRaw;
        } else {
          ctx.globalAlpha = 1;
          ctx.fillStyle = borderColor;
        }
        ctx.fillRect(x, y, CELL, CELL);
      }
    }
    ctx.globalAlpha = 1;

    // Tooltip via mouseenter
    wrap.innerHTML = '';
    const container = document.createElement('div');
    container.style.position = 'relative';
    container.style.display = 'inline-block';
    container.style.width = w + 'px';

    const tooltip = document.createElement('div');
    tooltip.className = 'anl-heatmap-tip';
    tooltip.style.display = 'none';

    canvas.addEventListener('mousemove', e => {
      const rect = canvas.getBoundingClientRect();
      const mx = (e.clientX - rect.left) * (w / rect.width);
      const my = (e.clientY - rect.top) * (h / rect.height);
      const col = Math.floor((mx - labelW) / (CELL + GAP));
      const row = Math.floor((my - labelH) / (CELL + GAP));
      if (col >= 0 && col < 24 && row >= 0 && row < days) {
        const count = (matrix[row] && matrix[row][col]) || 0;
        const day = labels[row] || '';
        tooltip.style.display = 'block';
        tooltip.style.left = (e.clientX - rect.left + 8) + 'px';
        tooltip.style.top = (e.clientY - rect.top - 24) + 'px';
        tooltip.textContent = `${day} ${String(col).padStart(2,'0')}:00 — ${count} msg`;
      } else {
        tooltip.style.display = 'none';
      }
    });
    canvas.addEventListener('mouseleave', () => { tooltip.style.display = 'none'; });

    container.appendChild(canvas);
    container.appendChild(tooltip);
    wrap.appendChild(container);
  }
