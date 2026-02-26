  // ── Widget: Bug Tracker ──
  let _trackerFormVisible = false;

  function loadTracker(statusFilter) {
    const status = statusFilter || document.getElementById('tracker-status-filter')?.value || 'open';
    send({ action: 'tracker_get', status });
  }

  function showTrackerForm() {
    _trackerFormVisible = !_trackerFormVisible;
    const form = document.getElementById('tracker-form');
    if (form) form.style.display = _trackerFormVisible ? 'block' : 'none';
  }

  function submitTracker() {
    const title = document.getElementById('tracker-input-title')?.value.trim();
    if (!title) { showToast('Titolo obbligatorio'); return; }
    const body     = document.getElementById('tracker-input-body')?.value.trim() || '';
    const itype    = document.getElementById('tracker-input-type')?.value || 'note';
    const priority = document.getElementById('tracker-input-priority')?.value || 'P2';
    send({ action: 'tracker_add', title, body, itype, priority });
    // Reset form
    ['tracker-input-title','tracker-input-body'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.value = '';
    });
    _trackerFormVisible = false;
    const form = document.getElementById('tracker-form');
    if (form) form.style.display = 'none';
  }

  function trackerUpdateStatus(id, status) {
    send({ action: 'tracker_update', id, status });
  }

  function trackerDelete(id) {
    send({ action: 'tracker_delete', id });
  }

  function renderTracker(items) {
    // Aggiorna preview tile
    const tp = document.getElementById('wt-tracker-preview');
    if (tp) {
      const open = (items || []).filter(i => i.status === 'open').length;
      tp.textContent = open ? open + ' open' : 'nessuno';
    }

    const el = document.getElementById('tracker-body');
    if (!el) return;

    const statusFilter = document.getElementById('tracker-status-filter')?.value || 'open';
    const TYPE_BADGE = { bug: 'badge-red', feature: 'badge-green', note: 'badge-muted' };
    const PRI_BADGE  = { P0: 'badge-red', P1: 'badge-amber', P2: 'badge-muted', P3: 'badge-muted' };

    let rows = '';
    if (!items || items.length === 0) {
      rows = '<div class="no-items">Nessun item ' + statusFilter + '</div>';
    } else {
      rows = items.map(it => {
        const typeCls = TYPE_BADGE[it.type] || 'badge-muted';
        const priCls  = PRI_BADGE[it.priority] || 'badge-muted';
        const isClosed = it.status === 'closed';
        const toggleLabel = isClosed ? '↩' : '✓';
        const toggleStatus = isClosed ? 'open' : 'closed';
        return `<div class="tracker-item${isClosed ? ' tracker-closed' : ''}">
          <div class="tracker-item-head">
            <span class="badge ${typeCls}">${esc(it.type)}</span>
            <span class="badge ${priCls}">${esc(it.priority)}</span>
            <span class="tracker-title">${esc(it.title)}</span>
            <div class="tracker-item-actions">
              <button class="btn-ghost btn-xs" title="${toggleStatus}" onclick="trackerUpdateStatus(${it.id},'${toggleStatus}')">${toggleLabel}</button>
              <button class="btn-ghost btn-xs" title="Elimina" onclick="trackerDelete(${it.id})">×</button>
            </div>
          </div>
          ${it.body ? `<div class="tracker-body-text">${esc(it.body)}</div>` : ''}
          <div class="tracker-item-meta">${it.ts.substring(0,16).replace('T',' ')}</div>
        </div>`;
      }).join('');
    }

    el.innerHTML = `
      <div style="display:flex;gap:6px;margin-bottom:10px;align-items:center;">
        <select id="tracker-status-filter" class="input-field" style="flex:1;font-size:11px;"
                onchange="loadTracker(this.value)">
          <option value="open"${statusFilter==='open'?' selected':''}>Open</option>
          <option value="closed"${statusFilter==='closed'?' selected':''}>Closed</option>
          <option value=""${statusFilter===''?' selected':''}>Tutti</option>
        </select>
        <button class="btn-ghost btn-sm" onclick="loadTracker()">↻</button>
      </div>
      <div id="tracker-form" style="display:none;margin-bottom:10px;padding:10px;border:1px solid var(--border);border-radius:4px;">
        <input type="text" id="tracker-input-title" class="input-field" placeholder="Titolo *" style="width:100%;margin-bottom:6px;">
        <textarea id="tracker-input-body" class="input-field" placeholder="Note (opzionale)" rows="2" style="width:100%;margin-bottom:6px;resize:vertical;"></textarea>
        <div style="display:flex;gap:6px;margin-bottom:6px;">
          <select id="tracker-input-type" class="input-field" style="flex:1;font-size:11px;">
            <option value="bug">Bug</option>
            <option value="feature">Feature</option>
            <option value="note" selected>Note</option>
          </select>
          <select id="tracker-input-priority" class="input-field" style="flex:1;font-size:11px;">
            <option value="P0">P0 critico</option>
            <option value="P1">P1 alto</option>
            <option value="P2" selected>P2 medio</option>
            <option value="P3">P3 basso</option>
          </select>
        </div>
        <div style="display:flex;gap:6px;">
          <button class="btn-green btn-sm" onclick="submitTracker()">Salva</button>
          <button class="btn-ghost btn-sm" onclick="showTrackerForm()">Annulla</button>
        </div>
      </div>
      <div id="tracker-list">${rows}</div>`;
  }
