  // ── Provider ──
  function toggleProviderMenu() {
    document.getElementById('provider-dropdown').classList.toggle('open');
  }
  function switchProvider(provider) {
    chatProvider = provider;
    const dot = document.getElementById('provider-dot');
    const label = document.getElementById('provider-short');
    const names = { auto: 'Auto', cloud: 'Haiku', local: 'Local', pc_coder: 'PC Coder', pc_deep: 'PC Deep', deepseek: 'DeepSeek', brain: 'Brain' };
    const dotClass = { auto: 'dot-auto', cloud: 'dot-cloud', local: 'dot-local', pc_coder: 'dot-pc-coder', pc_deep: 'dot-pc-deep', deepseek: 'dot-deepseek', brain: 'dot-brain' };
    dot.className = 'provider-dot ' + (dotClass[provider] || 'dot-local');
    label.textContent = names[provider] || 'Local';
    document.getElementById('provider-dropdown').classList.remove('open');
  }
  document.addEventListener('click', (e) => {
    const dd = document.getElementById('provider-dropdown');
    if (dd && !dd.contains(e.target)) dd.classList.remove('open');
  });

  // ── Memory toggle ──
  function toggleMemory() { send({ action: 'toggle_memory' }); }
