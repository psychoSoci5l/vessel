  // ── Theme Engine ──
  const THEMES = [
    { id: '',      label: 'Terminal Green', accent: '#00ff41' },
    { id: 'amber', label: 'Amber CRT',     accent: '#ffb000' },
    { id: 'cyan',  label: 'Cyan Ice',       accent: '#00ffcc' },
    { id: 'red',   label: 'Red Alert',      accent: '#ff3333' },
    { id: 'ghost', label: 'Ghost White',    accent: '#e0e0e0' },
  ];

  function applyTheme(id) {
    if (id) {
      document.documentElement.setAttribute('data-theme', id);
    } else {
      document.documentElement.removeAttribute('data-theme');
    }
    localStorage.setItem('vessel-theme', id || '');
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) {
      const cs = getComputedStyle(document.documentElement);
      meta.setAttribute('content', cs.getPropertyValue('--bg').trim());
    }
  }

  function getThemeId() {
    return localStorage.getItem('vessel-theme') || '';
  }

  // Applica subito per evitare flash
  applyTheme(getThemeId());
