  // ── Widget: Tokens (preview tile only — detail in Profile) ──
  function renderTokens(data) {
    const tp = document.getElementById('wt-tokens-preview');
    if (tp) {
      const inTok = (data.today_input || 0);
      const outTok = (data.today_output || 0);
      const fmt = n => n >= 1000 ? (n/1000).toFixed(1) + 'K' : n;
      const model = (data.last_model || '').split('-').pop() || '';
      tp.textContent = fmt(inTok) + ' in / ' + fmt(outTok) + ' out' + (model ? ' · ' + model : '');
    }
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
    anthropic: 'Haiku', openrouter: 'OpenRouter', ollama: 'Local',
    ollama_pc: 'PC', unknown: '?'
  };
  const _providerColors = {
    anthropic: 'var(--accent)', openrouter: 'var(--amber)', ollama: 'var(--muted)',
    ollama_pc: 'var(--cyan)'
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
      <td style="padding:6px;color:var(--accent);">TOTALE</td>
      <td style="padding:6px;text-align:right;color:var(--accent);">${fmt(total.input)}</td>
      <td style="padding:6px;text-align:right;color:var(--accent);">${fmt(total.output)}</td>
      <td style="padding:6px;text-align:right;color:var(--accent);">${fmt(grandTot)}</td>
      <td style="padding:6px;text-align:right;color:var(--accent);">${total.calls}</td>
    </tr>`;
    html += '</table></div>';
    el.innerHTML = html;
  }
