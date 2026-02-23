  // ── Widget: Cron Jobs ──
  function loadCron(btn) { if (btn) btn.textContent = '…'; send({ action: 'get_cron' }); }

  function renderCron(jobs) {
    const cp = document.getElementById('wt-cron-preview');
    if (cp) cp.textContent = ((jobs && jobs.length) || 0) + ' job attivi';
    const el = document.getElementById('cron-body');
    const jobList = (jobs && jobs.length) ? '<div class="cron-list">' + jobs.map((j, i) => `
      <div class="cron-item" style="align-items:center;">
        <div class="cron-schedule">${j.schedule}</div>
        <div style="flex:1;"><div class="cron-cmd">${j.command}</div>${j.desc?`<div class="cron-desc">// ${j.desc}</div>`:''}</div>
        <button class="btn-red btn-sm" style="padding:3px 8px;" onclick="deleteCron(${i})">✕</button>
      </div>`).join('') + '</div>'
      : '<div class="no-items">// nessun cron job</div>';
    el.innerHTML = jobList + `
      <div style="margin-top:10px;border-top:1px solid var(--border);padding-top:10px;">
        <div style="font-size:10px;color:var(--muted);margin-bottom:6px;">AGGIUNGI</div>
        <div style="display:flex;gap:6px;margin-bottom:6px;">
          <input id="cron-schedule" placeholder="30 7 * * *" class="input-field" style="width:120px;flex:0;">
          <input id="cron-command" placeholder="python3.13 /path/script.py" class="input-field">
        </div>
        <div style="display:flex;gap:6px;">
          <button class="btn-green btn-sm" onclick="addCron()">+ Aggiungi</button>
          <button class="btn-ghost btn-sm" onclick="loadCron()">↻</button>
        </div>
      </div>`;
  }
  function addCron() {
    const sched = document.getElementById('cron-schedule').value.trim();
    const cmd = document.getElementById('cron-command').value.trim();
    if (!sched || !cmd) { showToast('⚠️ Compila schedule e comando'); return; }
    send({ action: 'add_cron', schedule: sched, command: cmd });
  }
  function deleteCron(index) { send({ action: 'delete_cron', index: index }); }
