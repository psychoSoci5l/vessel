  // ── Widget: Crypto ──
  function loadCrypto(btn) { if (btn) btn.textContent = '…'; send({ action: 'get_crypto' }); }

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
