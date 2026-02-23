  // ── Input handlers ──
  document.addEventListener('DOMContentLoaded', () => {
    const chatInput = document.getElementById('chat-input');
    chatInput.addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(); }
    });
    chatInput.addEventListener('input', () => autoResizeInput(chatInput));
    document.getElementById('mem-search-keyword')?.addEventListener('keydown', e => {
      if (e.key === 'Enter') searchMemory();
    });
  });

  // ── Connect ──
  connect();

  // ── Plugin System ──
  async function loadPlugins() {
    try {
      const resp = await fetch('/api/plugins');
      if (!resp.ok) return;
      const plugins = await resp.json();
      if (!plugins.length) return;
      plugins.forEach(p => {
        const pid = 'plugin_' + p.id;
        const actHtml = p.actions === 'load'
          ? '<button class="btn-ghost btn-sm" onclick="pluginLoad_' + p.id + '(this)">Carica</button>'
          : '';
        DRAWER_CFG[pid] = { title: p.icon + ' ' + p.title, actions: actHtml, wide: p.wide || false };
        const body = document.querySelector('.drawer-body');
        if (body) {
          const dw = document.createElement('div');
          dw.className = 'drawer-widget';
          dw.id = 'dw-' + pid;
          dw.innerHTML = '<div id="plugin-' + p.id + '-body"><div class="widget-placeholder"><span class="ph-icon">' + p.icon + '</span><span>' + p.title + '</span></div></div>';
          body.appendChild(dw);
        }
        if (p.css) { const st = document.createElement('style'); st.textContent = p.css; document.head.appendChild(st); }
        if (p.js) { try { (new Function(p.js))(); } catch(e) { console.error('[Plugin] ' + p.id + ':', e); } }
        if (p.actions === 'load' && !window['pluginLoad_' + p.id]) {
          window['pluginLoad_' + p.id] = function(btn) { if (btn) btn.textContent = '…'; send({ action: pid }); };
        }
      });
    } catch(e) { console.error('[Plugins]', e); }
  }
  setTimeout(loadPlugins, 500);
