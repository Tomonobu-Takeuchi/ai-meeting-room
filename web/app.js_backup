/**
 * AI-PERSONA会議室 - フロントエンドロジック
 */
const State = {
  sessionId: null, topic: '', members: [], facilitator: null,
  selectedMemberIds: [], isStreaming: false, attachedFiles: [], streamingMessages: {},
};

const $ = id => document.getElementById(id);
const DOM = {
  newMeetingBtn: $('newMeetingBtn'), facilitatorBtn: $('facilitatorBtn'),
  topicInput: $('topicInput'), fileInput: $('fileInput'),
  startMeetingBtn: $('startMeetingBtn'), attachmentsBar: $('attachmentsBar'),
  memberList: $('memberList'), autoDiscussBtn: $('autoDiscussBtn'),
  welcomeScreen: $('welcomeScreen'), chatMessages: $('chatMessages'),
  chatInputArea: $('chatInputArea'), chatInput: $('chatInput'),
  sendBtn: $('sendBtn'), memberTriggers: $('memberTriggers'),
  allRespondBtn: $('allRespondBtn'), sessionBar: $('sessionBar'),
  sessionInfo: $('sessionInfo'), addMemberBtn: $('addMemberBtn'),
  addPersonaModal: $('addPersonaModal'), cancelAddPersona: $('cancelAddPersona'),
  confirmAddPersona: $('confirmAddPersona'), toastContainer: $('toastContainer'),
};

const API = {
  async get(path) {
    const res = await fetch(path);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },
  async post(path, body) {
    const res = await fetch(path, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) { const e = await res.json().catch(() => ({ error: res.statusText })); throw new Error(e.error || res.statusText); }
    return res.json();
  },
};

async function init() {
  try {
    const data = await API.get('/api/personas/members');
    State.members = data.members;
    renderMemberList();
  } catch (e) { showToast('ペルソナ読み込み失敗: ' + e.message, 'error'); }

  DOM.newMeetingBtn.addEventListener('click', resetMeeting);
  DOM.startMeetingBtn.addEventListener('click', startMeeting);
  DOM.facilitatorBtn.addEventListener('click', invokeFacilitator);
  DOM.autoDiscussBtn.addEventListener('click', autoDiscuss);
  DOM.sendBtn.addEventListener('click', sendUserMessage);
  DOM.allRespondBtn.addEventListener('click', allRespond);
  DOM.addMemberBtn.addEventListener('click', () => DOM.addPersonaModal.classList.remove('hidden'));
  DOM.cancelAddPersona.addEventListener('click', () => DOM.addPersonaModal.classList.add('hidden'));
  DOM.confirmAddPersona.addEventListener('click', submitAddPersona);
  DOM.fileInput.addEventListener('change', handleFileAttach);
  DOM.chatInput.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendUserMessage(); }
  });
  DOM.chatInput.addEventListener('input', () => {
    DOM.chatInput.style.height = 'auto';
    DOM.chatInput.style.height = Math.min(DOM.chatInput.scrollHeight, 120) + 'px';
  });
}

function renderMemberList() {
  DOM.memberList.innerHTML = '';
  if (State.selectedMemberIds.length === 0)
    State.selectedMemberIds = State.members.map(m => m.id);
  State.members.forEach(member => {
    const isSelected = State.selectedMemberIds.includes(member.id);
    const card = document.createElement('div');
    card.className = `member-card ${isSelected ? 'selected' : ''}`;
    card.dataset.id = member.id;
    card.innerHTML = `
      <div class="member-avatar" style="background:${member.color}22;border:2px solid ${member.color}44;">${member.avatar}</div>
      <div class="member-info">
        <div class="member-name">${member.name}</div>
        <div class="member-role">${(member.description||'').slice(0,28)}${(member.description||'').length>28?'…':''}</div>
      </div>
      <div class="member-status ${State.sessionId ? 'online' : ''}"></div>`;
    card.addEventListener('click', () => toggleMemberSelection(member.id));
    DOM.memberList.appendChild(card);
  });
  renderMemberTriggers();
}

function toggleMemberSelection(memberId) {
  if (State.sessionId) return;
  const idx = State.selectedMemberIds.indexOf(memberId);
  if (idx >= 0) { if (State.selectedMemberIds.length <= 1) return; State.selectedMemberIds.splice(idx, 1); }
  else State.selectedMemberIds.push(memberId);
  renderMemberList();
}

function renderMemberTriggers() {
  DOM.memberTriggers.innerHTML = '';
  State.members.filter(m => State.selectedMemberIds.includes(m.id)).forEach(member => {
    const btn = document.createElement('button');
    btn.className = 'member-trigger-btn'; btn.dataset.id = member.id;
    btn.innerHTML = `${member.avatar} ${member.name.split(' ')[0]}`;
    btn.addEventListener('click', () => triggerMemberResponse(member.id));
    DOM.memberTriggers.appendChild(btn);
  });
}

async function startMeeting() {
  const topic = DOM.topicInput.value.trim();
  if (!topic) { showToast('議題を入力してください', 'error'); DOM.topicInput.focus(); return; }
  if (State.selectedMemberIds.length === 0) { showToast('メンバーを選択してください', 'error'); return; }
  setLoading(true);
  try {
    const data = await API.post('/api/meeting/start', { topic, member_ids: State.selectedMemberIds });
    State.sessionId = data.session_id; State.topic = data.topic;
    State.members = data.members; State.facilitator = data.facilitator;
    DOM.welcomeScreen.classList.add('hidden');
    DOM.chatMessages.classList.remove('hidden');
    DOM.chatInputArea.classList.remove('hidden');
    DOM.sessionBar.classList.remove('hidden');
    DOM.sessionInfo.textContent = `会議ID: ${State.sessionId} ｜ 議題: ${State.topic}`;
    DOM.facilitatorBtn.disabled = false; DOM.autoDiscussBtn.disabled = false;
    DOM.topicInput.disabled = true; DOM.startMeetingBtn.disabled = true;
    renderMemberList(); renderMemberTriggers();
    addSystemMessage(`会議を開始しました。議題：「${State.topic}」`);
    showToast('会議を開始しました！', 'success');
    await invokeFacilitator();
  } catch (e) { showToast('会議開始エラー: ' + e.message, 'error'); }
  finally { setLoading(false); }
}

function resetMeeting() {
  if (State.sessionId && !confirm('現在の会議を終了して新しい会議を始めますか？')) return;
  State.sessionId = null; State.topic = ''; State.selectedMemberIds = [];
  State.isStreaming = false; State.streamingMessages = {};
  DOM.chatMessages.innerHTML = '';
  DOM.chatMessages.classList.add('hidden'); DOM.chatInputArea.classList.add('hidden');
  DOM.welcomeScreen.classList.remove('hidden'); DOM.sessionBar.classList.add('hidden');
  DOM.topicInput.disabled = false; DOM.topicInput.value = '';
  DOM.startMeetingBtn.disabled = false; DOM.facilitatorBtn.disabled = true;
  DOM.autoDiscussBtn.disabled = true;
  State.selectedMemberIds = State.members.map(m => m.id);
  renderMemberList();
}

async function sendUserMessage() {
  const content = DOM.chatInput.value.trim();
  if (!content || !State.sessionId || State.isStreaming) return;
  DOM.chatInput.value = ''; DOM.chatInput.style.height = 'auto';
  addMessage({ role: 'user', persona_id: 'user', content, id: 'tmp_' + Date.now() });
  try { await API.post(`/api/meeting/${State.sessionId}/message`, { content }); }
  catch (e) { showToast('送信エラー: ' + e.message, 'error'); }
}

async function triggerMemberResponse(personaId, trigger = null) {
  if (!State.sessionId || State.isStreaming) return;
  State.isStreaming = true; setStreamingButtons(true);
  const persona = State.members.find(m => m.id === personaId);
  if (!persona) return;
  const typingEl = addTypingIndicator(persona);
  setMemberSpeaking(personaId, true);
  let url = `/api/stream/member/${State.sessionId}/${personaId}`;
  if (trigger) url += `?trigger=${encodeURIComponent(trigger)}`;
  const evtSource = new EventSource(url);
  let streamEl = null;
  evtSource.onmessage = (e) => {
    const data = JSON.parse(e.data);
    if (data.type === 'chunk') {
      typingEl?.remove();
      if (!streamEl) streamEl = addStreamingBubble(persona);
      appendToStreamingBubble(streamEl, data.text);
    } else if (data.type === 'done') {
      streamEl?.querySelector('.msg-bubble')?.classList.remove('streaming');
      evtSource.close(); State.isStreaming = false;
      setStreamingButtons(false); setMemberSpeaking(personaId, false); scrollToBottom();
    } else if (data.type === 'error') {
      typingEl?.remove(); streamEl?.remove(); evtSource.close();
      State.isStreaming = false; setStreamingButtons(false); setMemberSpeaking(personaId, false);
      showToast('エラー: ' + data.message, 'error');
    }
  };
  evtSource.onerror = () => {
    typingEl?.remove(); evtSource.close();
    State.isStreaming = false; setStreamingButtons(false); setMemberSpeaking(personaId, false);
  };
}

async function invokeFacilitator() {
  if (!State.sessionId || State.isStreaming) return;
  State.isStreaming = true; setStreamingButtons(true);
  const typingEl = addTypingIndicator(State.facilitator, true);
  const evtSource = new EventSource(`/api/stream/facilitator/${State.sessionId}`);
  let streamEl = null;
  evtSource.onmessage = (e) => {
    const data = JSON.parse(e.data);
    if (data.type === 'chunk') {
      typingEl?.remove();
      if (!streamEl) streamEl = addFacilitatorBanner();
      appendToFacilitatorBanner(streamEl, data.text);
    } else if (data.type === 'done') {
      evtSource.close(); State.isStreaming = false; setStreamingButtons(false); scrollToBottom();
    } else if (data.type === 'error') {
      typingEl?.remove(); streamEl?.remove(); evtSource.close();
      State.isStreaming = false; setStreamingButtons(false);
      showToast('ファシリテータエラー: ' + data.message, 'error');
    }
  };
  evtSource.onerror = () => { typingEl?.remove(); evtSource.close(); State.isStreaming = false; setStreamingButtons(false); };
}

async function allRespond() {
  if (!State.sessionId || State.isStreaming) return;
  for (const member of State.members.filter(m => State.selectedMemberIds.includes(m.id))) {
    await triggerMemberResponse(member.id);
    await waitForStreamEnd();
  }
}

async function autoDiscuss() {
  if (!State.sessionId || State.isStreaming) return;
  for (const member of State.members.filter(m => State.selectedMemberIds.includes(m.id))) {
    await triggerMemberResponse(member.id);
    await waitForStreamEnd();
  }
}

function waitForStreamEnd() {
  return new Promise(resolve => {
    const check = setInterval(() => { if (!State.isStreaming) { clearInterval(check); resolve(); } }, 100);
  });
}

async function submitAddPersona() {
  const name = $('pName').value.trim(), avatar = $('pAvatar').value.trim() || '👤';
  const description = $('pDescription').value.trim(), personality = $('pPersonality').value.trim();
  const speakingStyle = $('pSpeakingStyle').value.trim(), background = $('pBackground').value.trim();
  if (!name || !description || !personality || !speakingStyle) { showToast('必須項目を入力してください', 'error'); return; }
  try {
    const data = await API.post('/api/personas/add', {
      name, avatar, description, personality, speaking_style: speakingStyle, background, role: 'member',
      color: ['#E85D75','#F59E0B','#10B981','#3B82F6','#8B5CF6'][Math.floor(Math.random()*5)],
    });
    State.members.push(data.persona); State.selectedMemberIds.push(data.persona.id);
    renderMemberList(); DOM.addPersonaModal.classList.add('hidden');
    ['pName','pDescription','pPersonality','pSpeakingStyle','pBackground'].forEach(id => $(id).value = '');
    $('pAvatar').value = '👤';
    showToast(`${name} を追加しました`, 'success');
  } catch (e) { showToast('追加エラー: ' + e.message, 'error'); }
}

function handleFileAttach(e) {
  Array.from(e.target.files).forEach(file => {
    if (!State.attachedFiles.find(f => f.name === file.name)) State.attachedFiles.push(file);
  });
  renderAttachments(); e.target.value = '';
}

function renderAttachments() {
  if (State.attachedFiles.length === 0) { DOM.attachmentsBar.style.display = 'none'; return; }
  DOM.attachmentsBar.style.display = 'flex';
  DOM.attachmentsBar.innerHTML = State.attachedFiles.map((f, i) =>
    `<div class="attachment-preview">📄 ${f.name}<span class="remove-btn" data-idx="${i}">✕</span></div>`
  ).join('');
  DOM.attachmentsBar.querySelectorAll('.remove-btn').forEach(btn => {
    btn.addEventListener('click', () => { State.attachedFiles.splice(parseInt(btn.dataset.idx), 1); renderAttachments(); });
  });
}

function addMessage(msg) {
  const persona = msg.persona_id === 'user'
    ? { name: 'あなた', avatar: '👤', color: '#2563EB' }
    : (State.members.find(m => m.id === msg.persona_id) || State.facilitator || {});
  const row = document.createElement('div');
  row.className = `message-row ${msg.role}`; row.dataset.msgId = msg.id;
  if (msg.role === 'facilitator') {
    row.innerHTML = `<div class="facilitator-banner"><div class="facilitator-label">🎯 ファシリテータ</div>${escapeHtml(msg.content)}</div>`;
  } else {
    row.innerHTML = `
      <div class="msg-avatar" style="background:${persona.color||'#888'}22;border:2px solid ${persona.color||'#888'}44;">${persona.avatar||'👤'}</div>
      <div class="msg-body"><div class="msg-name">${persona.name||'メンバー'}</div><div class="msg-bubble">${escapeHtml(msg.content)}</div></div>`;
  }
  DOM.chatMessages.appendChild(row); scrollToBottom(); return row;
}

function addSystemMessage(text) {
  const el = document.createElement('div'); el.className = 'system-msg'; el.textContent = text;
  DOM.chatMessages.appendChild(el); scrollToBottom();
}

function addTypingIndicator(persona, isFacilitator = false) {
  const row = document.createElement('div');
  row.className = `message-row ${isFacilitator ? 'facilitator' : 'member'} typing-row`;
  const dots = `<div class="typing-bubble"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div>`;
  if (isFacilitator) {
    row.innerHTML = `<div class="facilitator-banner"><div class="facilitator-label">🎯 ファシリテータ</div>${dots}</div>`;
  } else {
    row.innerHTML = `
      <div class="msg-avatar" style="background:${persona?.color||'#888'}22;border:2px solid ${persona?.color||'#888'}44;">${persona?.avatar||'👤'}</div>
      <div class="msg-body"><div class="msg-name">${persona?.name||'メンバー'}</div>${dots}</div>`;
  }
  DOM.chatMessages.appendChild(row); scrollToBottom(); return row;
}

function addStreamingBubble(persona) {
  const row = document.createElement('div'); row.className = 'message-row member';
  row.innerHTML = `
    <div class="msg-avatar" style="background:${persona.color}22;border:2px solid ${persona.color}44;">${persona.avatar}</div>
    <div class="msg-body"><div class="msg-name">${persona.name}</div><div class="msg-bubble streaming"></div></div>`;
  DOM.chatMessages.appendChild(row); scrollToBottom(); return row;
}

function appendToStreamingBubble(row, text) {
  const bubble = row.querySelector('.msg-bubble');
  if (bubble) { bubble.textContent += text; scrollToBottom(); }
}

function addFacilitatorBanner() {
  const row = document.createElement('div'); row.className = 'message-row facilitator';
  row.innerHTML = `<div class="facilitator-banner"><div class="facilitator-label">🎯 ファシリテータ</div><div class="facilitator-text"></div></div>`;
  DOM.chatMessages.appendChild(row); scrollToBottom(); return row;
}

function appendToFacilitatorBanner(row, text) {
  const el = row.querySelector('.facilitator-text');
  if (el) { el.textContent += text; scrollToBottom(); }
}

function setMemberSpeaking(personaId, isSpeaking) {
  DOM.memberList.querySelectorAll('.member-card').forEach(card => {
    const s = card.querySelector('.member-status');
    if (card.dataset.id === personaId) {
      card.classList.toggle('speaking', isSpeaking);
      if (s) s.className = `member-status ${isSpeaking ? 'speaking' : 'online'}`;
    }
  });
  DOM.memberTriggers.querySelectorAll('.member-trigger-btn').forEach(btn => {
    if (btn.dataset.id === personaId) btn.classList.toggle('active', isSpeaking);
  });
}

function setStreamingButtons(isStreaming) {
  DOM.sendBtn.disabled = isStreaming; DOM.allRespondBtn.disabled = isStreaming;
  DOM.autoDiscussBtn.disabled = isStreaming; DOM.facilitatorBtn.disabled = isStreaming;
  DOM.memberTriggers.querySelectorAll('.member-trigger-btn').forEach(btn => btn.disabled = isStreaming);
}

function setLoading(isLoading) {
  DOM.startMeetingBtn.disabled = isLoading;
  DOM.startMeetingBtn.textContent = isLoading ? '⏳ 開始中...' : '▶ 会議開始';
}

function scrollToBottom() { DOM.chatMessages.scrollTop = DOM.chatMessages.scrollHeight; }

function showToast(msg, type = 'info') {
  const toast = document.createElement('div'); toast.className = `toast ${type}`; toast.textContent = msg;
  DOM.toastContainer.appendChild(toast); setTimeout(() => toast.remove(), 3500);
}

function escapeHtml(text) { const d = document.createElement('div'); d.textContent = text; return d.innerHTML; }

document.addEventListener('DOMContentLoaded', init);