  // ═══════════════════════════════════════════
  // VESSEL DASHBOARD — Global State
  // ═══════════════════════════════════════════

  let ws = null;
  let reconnectTimer = null;
  let memoryEnabled = false;
  let currentTab = 'dashboard';
  let chatProvider = 'cloud';
  let streamDiv = null;
  let activeDrawer = null;

  function esc(s) {
    if (typeof s !== 'string') return s == null ? '' : String(s);
    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
  }
