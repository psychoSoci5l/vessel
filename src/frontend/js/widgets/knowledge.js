  // ── Widget: Knowledge Graph ──
  function loadEntities(btn) { if (btn) btn.textContent = '...'; send({ action: 'get_entities' }); }
  function deleteEntity(id) { send({ action: 'delete_entity', id: id }); }

  function renderKnowledgeGraph(entities, relations) {
    const mp = document.getElementById('wt-mem-preview');
    if (mp) mp.textContent = (entities ? entities.length : 0) + ' entità · ' + (relations ? relations.length : 0) + ' relazioni';
    const el = document.getElementById('grafo-body');
    if (!entities || entities.length === 0) {
      el.innerHTML = '<div class="no-items">// nessuna entità</div><div style="margin-top:8px;"><button class="btn-ghost btn-sm" onclick="loadEntities()">↻</button></div>';
      return;
    }
    const groups = { tech: [], person: [], place: [] };
    entities.forEach(e => {
      if (groups[e.type]) groups[e.type].push(e);
      else { if (!groups.other) groups.other = []; groups.other.push(e); }
    });
    const labels = { tech: 'Tech', person: 'Persone', place: 'Luoghi', other: 'Altro' };
    const colors = { tech: 'var(--cyan)', person: 'var(--accent)', place: 'var(--amber)', other: 'var(--text2)' };
    let html = '<div style="font-size:10px;color:var(--muted);margin-bottom:8px;">' + entities.length + ' entità</div>';
    for (const [type, items] of Object.entries(groups)) {
      if (!items.length) continue;
      html += '<div style="margin-bottom:12px;">';
      html += '<div style="font-size:10px;color:' + colors[type] + ';text-transform:uppercase;letter-spacing:1px;margin-bottom:4px;font-weight:700;">' + labels[type] + ' (' + items.length + ')</div>';
      items.forEach(e => {
        const since = e.first_seen ? e.first_seen.split('T')[0] : '';
        const last = e.last_seen ? e.last_seen.split('T')[0] : '';
        html += '<div style="display:flex;align-items:center;justify-content:space-between;background:var(--bg2);border:1px solid var(--border);border-radius:6px;padding:6px 10px;margin-bottom:3px;">';
        html += '<div style="flex:1;min-width:0;"><span style="color:var(--text2);font-size:12px;font-weight:600;">' + esc(e.name) + '</span> <span style="color:var(--muted);font-size:10px;">freq:' + e.frequency + '</span>';
        html += '<div style="font-size:9px;color:var(--muted);">' + since + ' → ' + last + '</div></div>';
        html += '<button class="btn-red btn-sm" style="padding:2px 6px;font-size:9px;margin-left:6px;flex-shrink:0;" onclick="deleteEntity(' + e.id + ')">✕</button></div>';
      });
      html += '</div>';
    }
    html += '<div><button class="btn-ghost btn-sm" onclick="loadEntities()">↻</button></div>';
    el.innerHTML = html;
  }
