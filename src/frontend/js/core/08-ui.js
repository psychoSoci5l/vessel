  // ── Toast ──
  function showToast(text) {
    const el = document.getElementById('toast');
    el.textContent = text; el.classList.add('show');
    setTimeout(() => el.classList.remove('show'), Math.max(2500, Math.min(text.length * 60, 6000)));
  }

  // ── Clipboard ──
  function copyToClipboard(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(() => showToast('[cp] Copiato')).catch(() => _fallbackCopy(text));
    } else { _fallbackCopy(text); }
  }
  function _fallbackCopy(text) {
    const ta = document.createElement('textarea');
    ta.value = text; ta.style.cssText = 'position:fixed;left:-9999px;top:-9999px;';
    document.body.appendChild(ta); ta.select();
    try { document.execCommand('copy'); showToast('[cp] Copiato'); } catch(e) { showToast('Copia non riuscita'); }
    document.body.removeChild(ta);
  }

  // ── Modals ──
  function showHelpModal() { document.getElementById('help-modal').classList.add('show'); }
  function closeHelpModal() { document.getElementById('help-modal').classList.remove('show'); }
  function showRebootModal() { document.getElementById('reboot-modal').classList.add('show'); }
  function hideRebootModal() { document.getElementById('reboot-modal').classList.remove('show'); }
  function confirmReboot() { hideRebootModal(); send({ action: 'reboot' }); }
  function showShutdownModal() { document.getElementById('shutdown-modal').classList.add('show'); }
  function hideShutdownModal() { document.getElementById('shutdown-modal').classList.remove('show'); }
  function confirmShutdown() { hideShutdownModal(); send({ action: 'shutdown' }); }

  function startRebootWait() {
    document.getElementById('reboot-overlay').classList.add('show');
    const statusEl = document.getElementById('reboot-status');
    let seconds = 0;
    const timer = setInterval(() => { seconds++; statusEl.textContent = `Attesa: ${seconds}s`; }, 1000);
    const tryReconnect = setInterval(() => {
      fetch('/', { method: 'HEAD', cache: 'no-store' })
        .then(r => {
          if (r.ok) {
            clearInterval(timer); clearInterval(tryReconnect);
            document.getElementById('reboot-overlay').classList.remove('show');
            showToast('[ok] Pi riavviato');
            if (ws) { try { ws.close(); } catch(e) {} }
            connect();
          }
        }).catch(() => {});
    }, 3000);
    setTimeout(() => { clearInterval(timer); clearInterval(tryReconnect); statusEl.textContent = 'Timeout — ricarica manualmente.'; }, 120000);
  }

  // ── Deep Learn ──
  function triggerDeepLearn() {
    const btn = document.getElementById('btn-deep-learn');
    if (btn) { btn.disabled = true; btn.textContent = 'In corso...'; }
    send({ action: 'deep_learn' });
  }

  // ── Sigil Indicator → moved to sigil.js (Fase 44) ──

  // ── Logout ──
  async function doLogout() {
    try {
      await fetch('/auth/logout', { method: 'POST', credentials: 'same-origin' });
    } catch(e) {}
    window.location.replace('/');
  }

  // ── Clock ──
  setInterval(() => {
    const t = new Date().toLocaleTimeString('it-IT');
    ['home-clock', 'chat-clock'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.textContent = t;
    });
  }, 1000);

  // ── iOS virtual keyboard ──
  if (window.visualViewport) {
    const appLayout = document.querySelector('.app-layout');
    let pendingVV = null;
    const handleVV = () => {
      if (pendingVV) return;
      pendingVV = requestAnimationFrame(() => {
        pendingVV = null;
        const vvh = window.visualViewport.height;
        const vvTop = window.visualViewport.offsetTop;
        appLayout.style.height = vvh + 'px';
        appLayout.style.transform = 'translateY(' + vvTop + 'px)';
        const msgs = document.getElementById('chat-messages');
        if (msgs) msgs.scrollTop = msgs.scrollHeight;
      });
    };
    window.visualViewport.addEventListener('resize', handleVV);
    window.visualViewport.addEventListener('scroll', handleVV);
  }

  // ── Service Worker ──
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js').catch(() => {});
  }
