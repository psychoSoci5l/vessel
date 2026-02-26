  // ── Drawer (bottom sheet per Briefing/Token/Crypto) ──
  const DRAWER_CFG = {
    briefing: { title: '▤ Morning Briefing', actions: '<button class="btn-ghost btn-sm" onclick="loadBriefing(this)">Carica</button>' },
    logs:     { title: '≡ Logs', actions: '<button class="btn-ghost btn-sm" onclick="loadLogs(this)">Logs</button><button class="btn-ghost btn-sm" onclick="loadChatHistory()">Chat</button>' },
    cron:     { title: '◇ Cron Jobs', actions: '<button class="btn-ghost btn-sm" onclick="loadCron(this)">Carica</button>' },
    system:   { title: '⚙ System', actions: '<button class="btn-ghost btn-sm" onclick="requestStats()">Refresh</button>' },
    tracker:  { title: '◈ Bug Tracker', actions: '<button class="btn-ghost btn-sm" onclick="loadTracker()">Carica</button><button class="btn-green btn-sm" onclick="showTrackerForm()">+ Aggiungi</button>' },
    tokens:   { title: '¤ Token Usage', actions: '<button class="btn-ghost btn-sm usage-period-btn active" onclick="loadUsageReport(\'day\',this)">Oggi</button><button class="btn-ghost btn-sm usage-period-btn" onclick="loadUsageReport(\'week\',this)">7gg</button><button class="btn-ghost btn-sm usage-period-btn" onclick="loadUsageReport(\'month\',this)">30gg</button>' },
  };

  function openDrawer(widgetId) {
    if (activeDrawer === widgetId) { closeDrawer(); return; }
    document.querySelectorAll('.drawer-widget').forEach(w => w.classList.remove('active'));
    const dw = document.getElementById('dw-' + widgetId);
    if (dw) dw.classList.add('active');
    const cfg = DRAWER_CFG[widgetId];
    document.getElementById('drawer-title').textContent = cfg ? cfg.title : widgetId;
    document.getElementById('drawer-actions').innerHTML =
      (cfg ? cfg.actions : '') +
      '<button class="btn-ghost btn-sm" onclick="closeDrawer()">✕</button>';
    document.getElementById('drawer-overlay').classList.add('show');
    document.body.classList.add('drawer-open');
    activeDrawer = widgetId;
  }

  function closeDrawer() {
    document.getElementById('drawer-overlay').classList.remove('show');
    document.body.classList.remove('drawer-open');
    activeDrawer = null;
  }

  // Swipe-down to close
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

  // Escape
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      if (activeDrawer) closeDrawer();
    }
  });
