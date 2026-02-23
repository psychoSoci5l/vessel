  // ── Chat ──
  function sendChat() {
    const input = document.getElementById('chat-input');
    const text = (input.value || '').trim();
    if (!text) return;
    // Auto-switch to Code tab > Chat panel if not there
    if (currentTab !== 'code') switchView('code');
    appendMessage(text, 'user');
    send({ action: 'chat', text, provider: chatProvider });
    input.value = '';
    input.style.height = 'auto';
    document.getElementById('chat-send').disabled = true;
  }

  function autoResizeInput(el) {
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 120) + 'px';
  }

  function appendMessage(text, role) {
    const box = document.getElementById('chat-messages');
    if (role === 'bot') {
      const wrap = document.createElement('div');
      wrap.className = 'copy-wrap';
      wrap.style.cssText = 'align-self:flex-start;max-width:85%;';
      const div = document.createElement('div');
      div.className = 'msg msg-bot';
      div.style.maxWidth = '100%';
      div.textContent = text;
      const btn = document.createElement('button');
      btn.className = 'copy-btn'; btn.textContent = '📋'; btn.title = 'Copia';
      btn.onclick = () => copyToClipboard(div.textContent);
      wrap.appendChild(div); wrap.appendChild(btn);
      box.appendChild(wrap);
    } else {
      const div = document.createElement('div');
      div.className = `msg msg-${role}`;
      div.textContent = text;
      box.appendChild(div);
    }
    box.scrollTop = box.scrollHeight;
  }

  function appendChunk(text) {
    const box = document.getElementById('chat-messages');
    if (!streamDiv) {
      streamDiv = document.createElement('div');
      streamDiv.className = 'msg msg-bot';
      streamDiv.textContent = '';
      box.appendChild(streamDiv);
    }
    streamDiv.textContent += text;
    box.scrollTop = box.scrollHeight;
  }

  function showAgentBadge(agentId) {
    const box = document.getElementById('chat-messages');
    const wraps = box.querySelectorAll('.copy-wrap');
    const last = wraps[wraps.length - 1];
    if (!last) return;
    const existing = last.querySelector('.agent-badge');
    if (existing) return;
    const badge = document.createElement('span');
    badge.className = 'agent-badge';
    badge.dataset.agent = agentId;
    badge.textContent = agentId;
    const msgDiv = last.querySelector('.msg-bot');
    if (msgDiv) msgDiv.appendChild(badge);
  }

  function finalizeStream() {
    if (streamDiv) {
      const box = streamDiv.parentNode;
      const wrap = document.createElement('div');
      wrap.className = 'copy-wrap';
      wrap.style.cssText = 'align-self:flex-start;max-width:85%;';
      streamDiv.style.maxWidth = '100%';
      box.insertBefore(wrap, streamDiv);
      wrap.appendChild(streamDiv);
      const btn = document.createElement('button');
      btn.className = 'copy-btn'; btn.textContent = '📋'; btn.title = 'Copia';
      btn.onclick = () => copyToClipboard(streamDiv.textContent);
      wrap.appendChild(btn);
    }
    streamDiv = null;
  }

  function appendThinking() {
    const box = document.getElementById('chat-messages');
    const div = document.createElement('div');
    div.id = 'thinking'; div.className = 'msg-thinking';
    div.innerHTML = 'elaborazione <span class="dots"><span>.</span><span>.</span><span>.</span></span>';
    box.appendChild(div); box.scrollTop = box.scrollHeight;
  }
  function removeThinking() { const el = document.getElementById('thinking'); if (el) el.remove(); }

  function clearChat() {
    document.getElementById('chat-messages').innerHTML =
      '<div class="msg msg-bot">Chat pulita 🧹</div>';
    send({ action: 'clear_chat' });
  }

  // ── Saved Prompts ──
  let _savedPrompts = [];

  function renderSavedPrompts(prompts) {
    _savedPrompts = prompts || [];
    const sel = document.getElementById('prompt-select');
    if (!sel) return;
    sel.innerHTML = '<option value="">Template...</option>';
    prompts.forEach(p => {
      const opt = document.createElement('option');
      opt.value = p.id;
      opt.textContent = p.title;
      opt.dataset.prompt = p.prompt;
      opt.dataset.provider = p.provider || '';
      sel.appendChild(opt);
    });
  }

  function loadSavedPrompt() {
    const sel = document.getElementById('prompt-select');
    if (!sel || !sel.value) return;
    const opt = sel.selectedOptions[0];
    if (!opt) return;
    const input = document.getElementById('chat-input');
    if (input) { input.value = opt.dataset.prompt; autoResizeInput(input); }
    if (opt.dataset.provider) switchProvider(opt.dataset.provider);
    sel.value = '';
  }

  function saveCurrentPrompt() {
    const input = document.getElementById('chat-input');
    const text = (input && input.value || '').trim();
    if (!text) { showToast('Scrivi un prompt prima di salvarlo'); return; }
    const title = prompt('Nome per il template:');
    if (!title || !title.trim()) return;
    send({ action: 'save_prompt', title: title.trim(), prompt: text, provider: chatProvider });
  }

  function deleteSavedPrompt() {
    const sel = document.getElementById('prompt-select');
    if (!sel || !sel.value) { showToast('Seleziona un template da eliminare'); return; }
    const id = parseInt(sel.value);
    if (!id) return;
    if (!confirm('Eliminare questo template?')) return;
    send({ action: 'delete_saved_prompt', id });
  }
