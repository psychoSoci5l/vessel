  // ── Tab Navigation ──
  function switchView(tabName) {
    if (currentTab === tabName) return;
    currentTab = tabName;

    document.querySelectorAll('.tab-view').forEach(v => v.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));

    const view = document.getElementById('tab-' + tabName);
    if (view) view.classList.add('active');

    const navBtn = document.querySelector(`.nav-item[data-tab="${tabName}"]`);
    if (navBtn) navBtn.classList.add('active');

    // Ridisegna chart quando torniamo a dashboard
    if (tabName === 'dashboard') requestAnimationFrame(() => drawChart());
  }

  // ── Memory Tabs ──
  function switchMemTab(name, btn) {
    const section = btn.closest('.prof-section');
    section.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    section.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('tab-' + name)?.classList.add('active');
    if (name === 'history') send({ action: 'get_history' });
    if (name === 'quickref') send({ action: 'get_quickref' });
    if (name === 'grafo') loadEntities();
  }
