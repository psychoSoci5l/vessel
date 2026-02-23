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
