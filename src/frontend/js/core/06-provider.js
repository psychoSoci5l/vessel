  // ── Provider ──
  function toggleProviderMenu() {
    document.getElementById('provider-dropdown').classList.toggle('open');
  }
  function switchProvider(provider) {
    chatProvider = provider;
    const dot = document.getElementById('provider-dot');
    const label = document.getElementById('provider-short');
    const names = { auto: 'Auto', cloud: 'Haiku', local: 'Local', pc: 'PC', deepseek: 'OpenRouter', brain: 'Brain' };
    const dotClass = { auto: 'dot-auto', cloud: 'dot-cloud', local: 'dot-local', pc: 'dot-pc', deepseek: 'dot-deepseek', brain: 'dot-brain' };
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
