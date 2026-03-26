
コピー

/**
 * AI-PERSONA会議室 - フロントエンドロジック（音声モード対応版）
 */
 
// ★ ペルソナごとの音声設定（voiceName: 使用する音声の名前の一部）
const VOICE_SETTINGS = {
  'koumei':      { pitch: 0.90, rate: 0.80, voiceName: 'Ichiro'  }, // 落ち着いた中年男性
  'hideyoshi':   { pitch: 1.05, rate: 1.10, voiceName: 'Ichiro'  }, // 陽気な年配男性
  'professor':   { pitch: 1.10, rate: 1.00, voiceName: 'Google'  }, // 若い男性
  'facilitator': { pitch: 1.15, rate: 1.00, voiceName: 'Haruka'  }, // 若い女性
};
 
const State = {
  sessionId: null, topic: '', members: [], facilitator: null,
  selectedMemberIds: [], isStreaming: false, attachedFiles: [], streamingMessages: {},
  avatarImages: {}, addAvatarDataUrl: null, editAvatarDataUrl: null,
  addLearnFiles: [], editLearnFiles: [], deletePendingId: null,
  voiceMode: false, isSpeaking: false, isRecognizing: false,
  recognition: null, jaVoices: [],
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
  editPersonaModal: $('editPersonaModal'), cancelEditPersona: $('cancelEditPersona'),
  confirmEditPersona: $('confirmEditPersona'),
  deleteConfirmOverlay: $('deleteConfirmOverlay'),
  cancelDeleteBtn: $('cancelDeleteBtn'), confirmDeleteBtn: $('confirmDeleteBtn'),
  deleteConfirmText: $('deleteConfirmText'),
  addAvatarPreview: $('addAvatarPreview'), editAvatarPreview: $('editAvatarPreview'),
  learnDataList: $('learnDataList'), editLearnDataList: $('editLearnDataList'),
  learnStatus: $('learnStatus'), editLearnStatus: $('editLearnStatus'),
  memberSelectModal: $('memberSelectModal'),
  cancelMemberSelect: $('cancelMemberSelect'),
  confirmMemberSelect: $('confirmMemberSelect'),
  memberCheckList: $('memberCheckList'),
  summarizeBtn: $('summarizeBtn'),
  minutesBar: $('minutesBar'),
  minutesBtn: $('minutesBtn'),
  voiceModeBtn: $('voiceModeBtn'),
  voiceModeBar: $('voiceModeBar'),
  stopSpeakBtn: $('stopSpeakBtn'),
  micBtn: $('micBtn'),
  topicMicBtn: $('topicMicBtn'),
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
  async put(path, body) {
    const res = await fetch(path, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) { const e = await res.json().catch(() => ({ error: res.statusText })); throw new Error(e.error || res.statusText); }
    return res.json();
  },
};
 
function loadVoices() {
  const voices = window.speechSynthesis.getVoices();
  State.jaVoices = voices.filter(v => v.lang.startsWith('ja'));
}
 
// ★ voiceNameで音声を選択
function selectVoice(personaId) {
  const voices = State.jaVoices;
  if (voices.length === 0) return null;
  const settings = VOICE_SETTINGS[personaId];
  if (settings?.voiceName) {
    const found = voices.find(v => v.name.includes(settings.voiceName));
    if (found) return found;
  }
  return voices[0];
}
 
function speakText(text, personaId, targetEl = null) {
  if (!State.voiceMode || !window.speechSynthesis) return;
  window.speechSynthesis.cancel();
  // ★ 漢字の読み間違いを修正
  const fixedText = text
    .replace(/秀吉/g, 'ひでよし')
    .replace(/孔明/g, 'こうめい')
    .replace(/諸葛/g, 'しょかつ')
    .replace(/ファシリテータ/g, 'ふぁしりてーたー');
  const speakStr = fixedText.length > 500 ? fixedText.slice(0, 500) + '…' : fixedText;
  const utterance = new SpeechSynthesisUtterance(speakStr);
  utterance.lang = 'ja-JP';
  const settings = VOICE_SETTINGS[personaId] || { pitch: 1.0, rate: 1.0 };
  utterance.pitch = settings.pitch;
  utterance.rate = settings.rate;
  const voice = selectVoice(personaId);
  if (voice) utterance.voice = voice;
  utterance.onstart = () => { State.isSpeaking = true; if (targetEl) targetEl.classList.add('voice-speaking'); };
  utterance.onend = () => { State.isSpeaking = false; if (targetEl) targetEl.classList.remove('voice-speaking'); };
  utterance.onerror = () => { State.isSpeaking = false; if (targetEl) targetEl.classList.remove('voice-speaking'); };
  window.speechSynthesis.speak(utterance);
}
 
function stopSpeaking() {
  if (window.speechSynthesis) window.speechSynthesis.cancel();
  State.isSpeaking = false;
  document.querySelectorAll('.voice-speaking').forEach(el => el.classList.remove('voice-speaking'));
}
 
function startVoiceInput(targetInput, micButton) {
  if (State.isRecognizing) {
    if (State.recognition) State.recognition.stop();
    return;
  }
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) { showToast('音声認識はChromeでのみ対応しています', 'error'); return; }
  const recognition = new SpeechRecognition();
  recognition.lang = 'ja-JP';
  recognition.interimResults = true;
  recognition.continuous = false;
  recognition.maxAlternatives = 1;
  State.recognition = recognition;
  State.isRecognizing = true;
  micButton.classList.add('recording');
  micButton.textContent = '⏹';
  recognition.onresult = (event) => {
    targetInput.value = Array.from(event.results).map(r => r[0].transcript).join('');
    if (targetInput.tagName === 'TEXTAREA') {
      targetInput.style.height = 'auto';
      targetInput.style.height = Math.min(targetInput.scrollHeight, 120) + 'px';
    }
  };
  recognition.onend = () => {
    State.isRecognizing = false; State.recognition = null;
    micButton.classList.remove('recording');
    micButton.textContent = '🎤';
  };
  recognition.onerror = (e) => {
    State.isRecognizing = false; State.recognition = null;
    micButton.classList.remove('recording');
    micButton.textContent = '🎤';
    if (e.error !== 'aborted') showToast('音声認識エラー: ' + e.error, 'error');
  };
  recognition.start();
}
 
function toggleVoiceMode() {
  State.voiceMode = !State.voiceMode;
  if (State.voiceMode) {
    DOM.voiceModeBtn.classList.add('active');
    DOM.voiceModeBtn.textContent = '🔊 音声モード ON';
    DOM.voiceModeBar.classList.remove('hidden');
    DOM.topicMicBtn.classList.remove('hidden');
    if (State.sessionId) DOM.micBtn.classList.remove('hidden');
    loadVoices();
    showToast('音声モードON：AIの発言を読み上げます', 'success');
  } else {
    DOM.voiceModeBtn.classList.remove('active');
    DOM.voiceModeBtn.textContent = '🎙️ 音声モード';
    DOM.voiceModeBar.classList.add('hidden');
    DOM.topicMicBtn.classList.add('hidden');
    DOM.micBtn.classList.add('hidden');
    stopSpeaking();
    if (State.isRecognizing && State.recognition) State.recognition.stop();
    showToast('音声モードOFF', 'info');
  }
}
 
async function init() {
  if (window.speechSynthesis) {
    loadVoices();
    window.speechSynthesis.onvoiceschanged = loadVoices;
  }
 
  try {
    const data = await API.get('/api/personas/members');
    State.members = data.members;
    renderMemberList();
  } catch (e) { showToast('ペルソナ読み込み失敗: ' + e.message, 'error'); }
 
  DOM.newMeetingBtn.addEventListener('click', resetMeeting);
  DOM.startMeetingBtn.addEventListener('click', showMemberSelectModal);
  DOM.facilitatorBtn.addEventListener('click', invokeFacilitator);
  DOM.autoDiscussBtn.addEventListener('click', autoDiscuss);
  DOM.sendBtn.addEventListener('click', sendUserMessage);
  DOM.allRespondBtn.addEventListener('click', allRespond);
 
  DOM.cancelMemberSelect.addEventListener('click', () => DOM.memberSelectModal.classList.add('hidden'));
  DOM.confirmMemberSelect.addEventListener('click', startMeetingFromModal);
 
  DOM.summarizeBtn.addEventListener('click', summarizeMeeting);
  DOM.minutesBtn.addEventListener('click', downloadMinutes);
 
  DOM.voiceModeBtn.addEventListener('click', toggleVoiceMode);
  DOM.stopSpeakBtn.addEventListener('click', stopSpeaking);
  DOM.micBtn.addEventListener('click', () => startVoiceInput(DOM.chatInput, DOM.micBtn));
  DOM.topicMicBtn.addEventListener('click', () => startVoiceInput(DOM.topicInput, DOM.topicMicBtn));
 
  DOM.addMemberBtn.addEventListener('click', openAddModal);
  DOM.cancelAddPersona.addEventListener('click', closeAddModal);
  DOM.confirmAddPersona.addEventListener('click', submitAddPersona);
  DOM.cancelEditPersona.addEventListener('click', closeEditModal);
  DOM.confirmEditPersona.addEventListener('click', submitEditPersona);
  DOM.cancelDeleteBtn.addEventListener('click', () => { DOM.deleteConfirmOverlay.classList.add('hidden'); State.deletePendingId = null; });
  DOM.confirmDeleteBtn.addEventListener('click', executeDeletion);
  DOM.fileInput.addEventListener('change', handleFileAttach);
 
  $('pAvatar').addEventListener('input', () => { if (!State.addAvatarDataUrl) DOM.addAvatarPreview.innerHTML = $('pAvatar').value || '👤'; });
  $('addAvatarImageFile').addEventListener('change', (e) => {
    const file = e.target.files[0]; if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => { State.addAvatarDataUrl = ev.target.result; DOM.addAvatarPreview.innerHTML = `<img src="${ev.target.result}" alt="avatar" />`; };
    reader.readAsDataURL(file); e.target.value = '';
  });
  $('eAvatar').addEventListener('input', () => { if (!State.editAvatarDataUrl) DOM.editAvatarPreview.innerHTML = $('eAvatar').value || '👤'; });
  $('editAvatarImageFile').addEventListener('change', (e) => {
    const file = e.target.files[0]; if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => { State.editAvatarDataUrl = ev.target.result; DOM.editAvatarPreview.innerHTML = `<img src="${ev.target.result}" alt="avatar" />`; };
    reader.readAsDataURL(file); e.target.value = '';
  });
  $('learnTextFile').addEventListener('change', (e) => handleLearnFiles(e, 'add', 'text'));
  $('learnImageFile').addEventListener('change', (e) => handleLearnFiles(e, 'add', 'image'));
  $('editLearnTextFile').addEventListener('change', (e) => handleLearnFiles(e, 'edit', 'text'));
  $('editLearnImageFile').addEventListener('change', (e) => handleLearnFiles(e, 'edit', 'image'));
 
  DOM.chatInput.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendUserMessage(); } });
  DOM.chatInput.addEventListener('input', () => {
    DOM.chatInput.style.height = 'auto';
    DOM.chatInput.style.height = Math.min(DOM.chatInput.scrollHeight, 120) + 'px';
  });
}
 
function showMemberSelectModal() {
  const topic = DOM.topicInput.value.trim();
  if (!topic) { showToast('議題を入力してください', 'error'); DOM.topicInput.focus(); return; }
  DOM.memberCheckList.innerHTML = '';
  State.members.forEach(member => {
    const isChecked = State.selectedMemberIds.length === 0 || State.selectedMemberIds.includes(member.id);
    const label = document.createElement('label');
    label.className = 'member-check-item';
    const avatarHtml = State.avatarImages[member.id]
      ? `<img src="${State.avatarImages[member.id]}" style="width:32px;height:32px;border-radius:50%;object-fit:cover;" />`
      : (member.avatar || '👤');
    label.innerHTML = `
      <input type="checkbox" value="${member.id}" ${isChecked ? 'checked' : ''} />
      <div class="member-check-avatar" style="background:${member.color}22">${avatarHtml}</div>
      <div class="member-check-info">
        <div class="member-check-name">${member.name}</div>
        <div class="member-check-role">${member.role || ''}</div>
      </div>`;
    DOM.memberCheckList.appendChild(label);
  });
  DOM.memberSelectModal.classList.remove('hidden');
}
 
async function startMeetingFromModal() {
  const checked = DOM.memberCheckList.querySelectorAll('input[type="checkbox"]:checked');
  if (checked.length === 0) { showToast('最低1人選択してください', 'error'); return; }
  State.selectedMemberIds = Array.from(checked).map(cb => cb.value);
  DOM.memberSelectModal.classList.add('hidden');
  await startMeeting();
}
 
async function summarizeMeeting() {
  if (!State.sessionId || State.isStreaming) return;
  State.isStreaming = true; setStreamingButtons(true);
  DOM.summarizeBtn.disabled = true;
  const typingEl = addTypingIndicator(State.facilitator, true);
  const evtSource = new EventSource(`/api/stream/facilitator/${State.sessionId}`);
  let streamEl = null, fullText = '';
  evtSource.onmessage = (e) => {
    const data = JSON.parse(e.data);
    if (data.type === 'chunk') {
      typingEl?.remove();
      if (!streamEl) streamEl = addFacilitatorBanner();
      appendToFacilitatorBanner(streamEl, data.text);
      fullText += data.text;
    } else if (data.type === 'done') {
      evtSource.close(); State.isStreaming = false; setStreamingButtons(false);
      DOM.minutesBar.classList.remove('hidden');
      scrollToBottom();
      if (State.voiceMode && fullText) speakText(fullText, 'facilitator', streamEl?.querySelector('.facilitator-banner'));
    } else if (data.type === 'error') {
      typingEl?.remove(); streamEl?.remove(); evtSource.close();
      State.isStreaming = false; setStreamingButtons(false);
      DOM.summarizeBtn.disabled = false;
      showToast('まとめエラー: ' + data.message, 'error');
    }
  };
  evtSource.onerror = () => { typingEl?.remove(); evtSource.close(); State.isStreaming = false; setStreamingButtons(false); DOM.summarizeBtn.disabled = false; };
}
 
async function downloadMinutes() {
  if (!State.sessionId) return;
  const btn = DOM.minutesBtn;
  btn.disabled = true; btn.textContent = '⏳ 生成中...';
  try {
    const res = await fetch(`/api/meeting/${State.sessionId}/minutes`, { method: 'POST' });
    if (!res.ok) { const err = await res.json().catch(() => ({ error: '生成失敗' })); throw new Error(err.error || '生成失敗'); }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    const topic = State.topic.slice(0, 20).replace(/[/\\]/g, '_');
    a.download = `議事録_${topic}_${new Date().toISOString().slice(0, 10)}.pdf`;
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showToast('議事録をダウンロードしました', 'success');
  } catch (e) { showToast('ダウンロードエラー: ' + e.message, 'error'); }
  finally { btn.disabled = false; btn.textContent = '📄 議事録をダウンロード（PDF）'; }
}
 
async function handleLearnFiles(e, mode, type) {
  const files = Array.from(e.target.files);
  const listKey = mode === 'add' ? 'addLearnFiles' : 'editLearnFiles';
  const statusEl = mode === 'add' ? DOM.learnStatus : DOM.editLearnStatus;
  for (const file of files) {
    if (State[listKey].find(f => f.name === file.name)) continue;
    statusEl.textContent = `${file.name} を読み込み中...`;
    let content = '', fileType = type;
    if (type === 'text') {
      if (file.name.endsWith('.pdf')) { content = `[PDFファイル: ${file.name}]`; fileType = 'pdf'; }
      else { content = await readFileAsText(file); }
    } else if (type === 'image') { content = await readFileAsDataUrl(file); fileType = 'image'; }
    State[listKey].push({ name: file.name, type: fileType, content });
    statusEl.textContent = `✓ ${file.name} を読み込みました`;
    setTimeout(() => { statusEl.textContent = ''; }, 2000);
  }
  renderLearnDataList(mode); e.target.value = '';
}
 
function readFileAsText(file) {
  return new Promise((resolve) => { const r = new FileReader(); r.onload = (e) => resolve(e.target.result); r.onerror = () => resolve(''); r.readAsText(file, 'UTF-8'); });
}
function readFileAsDataUrl(file) {
  return new Promise((resolve) => { const r = new FileReader(); r.onload = (e) => resolve(e.target.result); r.onerror = () => resolve(''); r.readAsDataURL(file); });
}
 
function renderLearnDataList(mode) {
  const listKey = mode === 'add' ? 'addLearnFiles' : 'editLearnFiles';
  const listEl = mode === 'add' ? DOM.learnDataList : DOM.editLearnDataList;
  const files = State[listKey];
  if (files.length === 0) { listEl.innerHTML = ''; return; }
  listEl.innerHTML = files.map((f, i) => {
    const icon = f.type === 'image' ? '🖼️' : f.type === 'pdf' ? '📕' : '📄';
    return `<div class="learn-data-item">${icon} ${f.name}<span class="remove-learn" data-idx="${i}" data-mode="${mode}">✕</span></div>`;
  }).join('');
  listEl.querySelectorAll('.remove-learn').forEach(btn => {
    btn.addEventListener('click', () => { const k = btn.dataset.mode === 'add' ? 'addLearnFiles' : 'editLearnFiles'; State[k].splice(parseInt(btn.dataset.idx), 1); renderLearnDataList(btn.dataset.mode); });
  });
}
 
function buildBackgroundFromLearnData(existingBackground, learnFiles) {
  if (learnFiles.length === 0) return existingBackground;
  const texts = learnFiles.filter(f => f.type === 'text' || f.type === 'pdf').map(f => f.content).join('\n\n');
  if (!texts) return existingBackground;
  return existingBackground ? existingBackground + '\n\n--- 学習データ ---\n' + texts.slice(0, 2000) : texts.slice(0, 2000);
}
 
function renderMemberList() {
  DOM.memberList.innerHTML = '';
  if (State.selectedMemberIds.length === 0) State.selectedMemberIds = State.members.map(m => m.id);
  State.members.forEach(member => {
    const isSelected = State.selectedMemberIds.includes(member.id);
    const card = document.createElement('div');
    card.className = `member-card ${isSelected ? 'selected' : ''}`; card.dataset.id = member.id;
    const avatarHtml = State.avatarImages[member.id] ? `<img src="${State.avatarImages[member.id]}" alt="${member.name}" />` : member.avatar;
    card.innerHTML = `
      <div class="member-card-main">
        <div class="member-avatar" style="background:${member.color}22;border:2px solid ${member.color}44;">${avatarHtml}</div>
        <div class="member-info">
          <div class="member-name">${member.name}</div>
          <div class="member-role">${(member.description||'').slice(0,28)}${(member.description||'').length>28?'…':''}</div>
        </div>
        <div class="member-status ${State.sessionId ? 'online' : ''}"></div>
      </div>
      <div class="member-card-actions">
        <button class="btn-icon" title="設定" data-action="settings" data-id="${member.id}">⚙</button>
        <button class="btn-icon danger" title="削除" data-action="delete" data-id="${member.id}">🗑</button>
      </div>`;
    card.querySelector('.member-card-main').addEventListener('click', () => toggleMemberSelection(member.id));
    card.querySelector('[data-action="settings"]').addEventListener('click', (e) => { e.stopPropagation(); openEditModal(member.id); });
    card.querySelector('[data-action="delete"]').addEventListener('click', (e) => { e.stopPropagation(); openDeleteConfirm(member.id); });
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
 
function openAddModal() {
  State.addAvatarDataUrl = null; State.addLearnFiles = [];
  DOM.addAvatarPreview.innerHTML = '👤'; $('pAvatar').value = '👤';
  $('pName').value = ''; $('pColor').value = '#8B5CF6';
  $('pDescription').value = ''; $('pPersonality').value = '';
  $('pSpeakingStyle').value = ''; $('pBackground').value = '';
  DOM.learnDataList.innerHTML = ''; DOM.learnStatus.textContent = '';
  DOM.addPersonaModal.classList.remove('hidden');
}
function closeAddModal() { DOM.addPersonaModal.classList.add('hidden'); }
 
function openEditModal(memberId) {
  const member = State.members.find(m => m.id === memberId); if (!member) return;
  State.editAvatarDataUrl = State.avatarImages[memberId] || null; State.editLearnFiles = [];
  $('editPersonaId').value = memberId; $('eAvatar').value = member.avatar || '👤';
  $('eName').value = member.name || ''; $('eColor').value = member.color || '#8B5CF6';
  $('eDescription').value = member.description || ''; $('ePersonality').value = member.personality || '';
  $('eSpeakingStyle').value = member.speaking_style || ''; $('eBackground').value = member.background || '';
  DOM.editLearnDataList.innerHTML = ''; DOM.editLearnStatus.textContent = '';
  DOM.editAvatarPreview.innerHTML = State.editAvatarDataUrl ? `<img src="${State.editAvatarDataUrl}" alt="avatar" />` : (member.avatar || '👤');
  DOM.editPersonaModal.classList.remove('hidden');
}
function closeEditModal() { DOM.editPersonaModal.classList.add('hidden'); State.editAvatarDataUrl = null; State.editLearnFiles = []; }
 
async function submitEditPersona() {
  const memberId = $('editPersonaId').value;
  const name = $('eName').value.trim(), avatar = $('eAvatar').value.trim() || '👤';
  const description = $('eDescription').value.trim(), personality = $('ePersonality').value.trim();
  const speakingStyle = $('eSpeakingStyle').value.trim(), color = $('eColor').value;
  let background = buildBackgroundFromLearnData($('eBackground').value.trim(), State.editLearnFiles);
  if (!name || !description || !personality || !speakingStyle) { showToast('必須項目を入力してください', 'error'); return; }
  if (State.editAvatarDataUrl) State.avatarImages[memberId] = State.editAvatarDataUrl;
  try {
    const data = await API.put(`/api/personas/${memberId}`, { name, avatar, description, personality, speaking_style: speakingStyle, background, color });
    const idx = State.members.findIndex(m => m.id === memberId);
    if (idx >= 0) State.members[idx] = { ...State.members[idx], ...data.persona };
    renderMemberList(); closeEditModal();
    showToast(`${name} の設定を保存しました`, 'success');
  } catch (e) { showToast('保存エラー: ' + e.message, 'error'); }
}
 
function openDeleteConfirm(memberId) {
  const member = State.members.find(m => m.id === memberId); if (!member) return;
  State.deletePendingId = memberId;
  DOM.deleteConfirmText.textContent = `「${member.name}」を参加メンバーから削除してもよろしいですか？`;
  DOM.deleteConfirmOverlay.classList.remove('hidden');
}
 
function executeDeletion() {
  const memberId = State.deletePendingId; if (!memberId) return;
  const member = State.members.find(m => m.id === memberId);
  const memberName = member ? member.name : 'メンバー';
  State.members = State.members.filter(m => m.id !== memberId);
  State.selectedMemberIds = State.selectedMemberIds.filter(id => id !== memberId);
  delete State.avatarImages[memberId];
  if (State.selectedMemberIds.length === 0 && State.members.length > 0) State.selectedMemberIds = [State.members[0].id];
  renderMemberList(); DOM.deleteConfirmOverlay.classList.add('hidden'); State.deletePendingId = null;
  showToast(`${memberName} を削除しました`, 'success');
}
 
async function startMeeting() {
  const topic = DOM.topicInput.value.trim();
  if (!topic) { showToast('議題を入力してください', 'error'); return; }
  if (State.selectedMemberIds.length === 0) { showToast('メンバーを選択してください', 'error'); return; }
  setLoading(true);
  try {
    const data = await API.post('/api/meeting/start', { topic, member_ids: State.selectedMemberIds });
    State.sessionId = data.session_id; State.topic = data.topic;
    State.members = data.members; State.facilitator = data.facilitator;
    DOM.welcomeScreen.classList.add('hidden');
    DOM.chatMessages.classList.remove('hidden'); DOM.chatInputArea.classList.remove('hidden');
    DOM.sessionBar.classList.remove('hidden');
    DOM.sessionInfo.textContent = `会議ID: ${State.sessionId} ・ 議題: ${State.topic}`;
    DOM.facilitatorBtn.disabled = false; DOM.autoDiscussBtn.disabled = false; DOM.summarizeBtn.disabled = false;
    DOM.topicInput.disabled = true; DOM.startMeetingBtn.disabled = true;
    if (State.voiceMode) DOM.micBtn.classList.remove('hidden');
    renderMemberList(); renderMemberTriggers();
    addSystemMessage(`会議を開始しました。議題：${State.topic}`);
    showToast('会議を開始しました！', 'success');
    await invokeFacilitator();
  } catch (e) { showToast('会議開始エラー: ' + e.message, 'error'); }
  finally { setLoading(false); }
}
 
function resetMeeting() {
  if (State.sessionId && !confirm('現在の会議を終了して新しい会議を始めますか？')) return;
  stopSpeaking();
  if (State.isRecognizing && State.recognition) State.recognition.stop();
  State.sessionId = null; State.topic = ''; State.selectedMemberIds = [];
  State.isStreaming = false; State.streamingMessages = {};
  DOM.chatMessages.innerHTML = '';
  DOM.chatMessages.classList.add('hidden'); DOM.chatInputArea.classList.add('hidden');
  DOM.welcomeScreen.classList.remove('hidden'); DOM.sessionBar.classList.add('hidden');
  DOM.minutesBar.classList.add('hidden'); DOM.micBtn.classList.add('hidden');
  DOM.topicInput.disabled = false; DOM.topicInput.value = '';
  DOM.startMeetingBtn.disabled = false; DOM.facilitatorBtn.disabled = true;
  DOM.autoDiscussBtn.disabled = true; DOM.summarizeBtn.disabled = true;
  State.selectedMemberIds = State.members.map(m => m.id);
  renderMemberList();
}
 
async function sendUserMessage() {
  const content = DOM.chatInput.value.trim();
  if (!content || !State.sessionId || State.isStreaming) return;
  if (State.isRecognizing && State.recognition) State.recognition.stop();
  DOM.chatInput.value = ''; DOM.chatInput.style.height = 'auto';
  addMessage({ role: 'user', persona_id: 'user', content, id: 'tmp_' + Date.now() });
  try { await API.post(`/api/meeting/${State.sessionId}/message`, { content }); }
  catch (e) { showToast('送信エラー: ' + e.message, 'error'); }
}
 
async function triggerMemberResponse(personaId, trigger = null) {
  if (!State.sessionId || State.isStreaming) return;
  if (State.voiceMode) stopSpeaking();
  State.isStreaming = true; setStreamingButtons(true);
  const persona = State.members.find(m => m.id === personaId); if (!persona) return;
  const typingEl = addTypingIndicator(persona);
  setMemberSpeaking(personaId, true);
  let url = `/api/stream/member/${State.sessionId}/${personaId}`;
  if (trigger) url += `?trigger=${encodeURIComponent(trigger)}`;
  const evtSource = new EventSource(url);
  let streamEl = null, fullText = '';
  evtSource.onmessage = (e) => {
    const data = JSON.parse(e.data);
    if (data.type === 'chunk') {
      typingEl?.remove();
      if (!streamEl) streamEl = addStreamingBubble(persona);
      appendToStreamingBubble(streamEl, data.text);
      fullText += data.text;
    } else if (data.type === 'done') {
      streamEl?.querySelector('.msg-bubble')?.classList.remove('streaming');
      evtSource.close(); State.isStreaming = false;
      setStreamingButtons(false); setMemberSpeaking(personaId, false); scrollToBottom();
      if (State.voiceMode && fullText) speakText(fullText, personaId, streamEl?.querySelector('.msg-bubble'));
    } else if (data.type === 'error') {
      typingEl?.remove(); streamEl?.remove(); evtSource.close();
      State.isStreaming = false; setStreamingButtons(false); setMemberSpeaking(personaId, false);
      showToast('エラー: ' + data.message, 'error');
    }
  };
  evtSource.onerror = () => { typingEl?.remove(); evtSource.close(); State.isStreaming = false; setStreamingButtons(false); setMemberSpeaking(personaId, false); };
}
 
async function invokeFacilitator() {
  if (!State.sessionId || State.isStreaming) return;
  if (State.voiceMode) stopSpeaking();
  State.isStreaming = true; setStreamingButtons(true);
  const typingEl = addTypingIndicator(State.facilitator, true);
  const evtSource = new EventSource(`/api/stream/facilitator/${State.sessionId}`);
  let streamEl = null, fullText = '';
  evtSource.onmessage = (e) => {
    const data = JSON.parse(e.data);
    if (data.type === 'chunk') {
      typingEl?.remove();
      if (!streamEl) streamEl = addFacilitatorBanner();
      appendToFacilitatorBanner(streamEl, data.text);
      fullText += data.text;
    } else if (data.type === 'done') {
      evtSource.close(); State.isStreaming = false; setStreamingButtons(false); scrollToBottom();
      if (State.voiceMode && fullText) speakText(fullText, 'facilitator', streamEl?.querySelector('.facilitator-banner'));
    } else if (data.type === 'error') {
      typingEl?.remove(); streamEl?.remove(); evtSource.close();
      State.isStreaming = false; setStreamingButtons(false);
      showToast('ファシリテーターエラー: ' + data.message, 'error');
    }
  };
  evtSource.onerror = () => { typingEl?.remove(); evtSource.close(); State.isStreaming = false; setStreamingButtons(false); };
}
 
async function allRespond() {
  if (!State.sessionId || State.isStreaming) return;
  for (const member of State.members.filter(m => State.selectedMemberIds.includes(m.id))) {
    await triggerMemberResponse(member.id);
    await waitForStreamEnd();
    if (State.voiceMode) await waitForSpeakEnd();
  }
}
 
async function autoDiscuss() {
  if (!State.sessionId || State.isStreaming) return;
  for (const member of State.members.filter(m => State.selectedMemberIds.includes(m.id))) {
    await triggerMemberResponse(member.id);
    await waitForStreamEnd();
    if (State.voiceMode) await waitForSpeakEnd();
  }
}
 
function waitForStreamEnd() {
  return new Promise(resolve => { const c = setInterval(() => { if (!State.isStreaming) { clearInterval(c); resolve(); } }, 100); });
}
function waitForSpeakEnd() {
  return new Promise(resolve => {
    let count = 0;
    const c = setInterval(() => { count++; if (!State.isSpeaking || count > 300) { clearInterval(c); resolve(); } }, 100);
  });
}
 
async function submitAddPersona() {
  const name = $('pName').value.trim(), avatar = $('pAvatar').value.trim() || '👤';
  const description = $('pDescription').value.trim(), personality = $('pPersonality').value.trim();
  const speakingStyle = $('pSpeakingStyle').value.trim(), color = $('pColor').value;
  let background = buildBackgroundFromLearnData($('pBackground').value.trim(), State.addLearnFiles);
  if (!name || !description || !personality || !speakingStyle) { showToast('必須項目を入力してください', 'error'); return; }
  try {
    const data = await API.post('/api/personas/add', { name, avatar, description, personality, speaking_style: speakingStyle, background, role: 'member', color });
    if (State.addAvatarDataUrl) State.avatarImages[data.persona.id] = State.addAvatarDataUrl;
    State.members.push(data.persona); State.selectedMemberIds.push(data.persona.id);
    renderMemberList(); closeAddModal();
    showToast(`${name} を追加しました`, 'success');
  } catch (e) { showToast('追加エラー: ' + e.message, 'error'); }
}
 
function handleFileAttach(e) {
  Array.from(e.target.files).forEach(file => { if (!State.attachedFiles.find(f => f.name === file.name)) State.attachedFiles.push(file); });
  renderAttachments(); e.target.value = '';
}
 
function renderAttachments() {
  if (State.attachedFiles.length === 0) { DOM.attachmentsBar.style.display = 'none'; return; }
  DOM.attachmentsBar.style.display = 'flex';
  DOM.attachmentsBar.innerHTML = State.attachedFiles.map((f, i) =>
    `<div class="attachment-preview">📎 ${f.name}<span class="remove-btn" data-idx="${i}">✕</span></div>`
  ).join('');
  DOM.attachmentsBar.querySelectorAll('.remove-btn').forEach(btn => {
    btn.addEventListener('click', () => { State.attachedFiles.splice(parseInt(btn.dataset.idx), 1); renderAttachments(); });
  });
}
 
function addMessage(msg) {
  const persona = msg.persona_id === 'user' ? { name: 'あなた', avatar: '👤', color: '#2563EB' }
    : (State.members.find(m => m.id === msg.persona_id) || State.facilitator || {});
  const row = document.createElement('div');
  row.className = `message-row ${msg.role}`; row.dataset.msgId = msg.id;
  if (msg.role === 'facilitator') {
    row.innerHTML = `<div class="facilitator-banner"><div class="facilitator-label">🎯 ファシリテーター</div><div class="facilitator-text">${escapeHtml(msg.content)}</div></div>`;
  } else {
    const avatarContent = (msg.persona_id !== 'user' && State.avatarImages[msg.persona_id])
      ? `<img src="${State.avatarImages[msg.persona_id]}" alt="${persona.name}" />` : (persona.avatar || '👤');
    row.innerHTML = `
      <div class="msg-avatar" style="background:${persona.color||'#888'}22;border:2px solid ${persona.color||'#888'}44;">${avatarContent}</div>
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
    row.innerHTML = `<div class="facilitator-banner"><div class="facilitator-label">🎯 ファシリテーター</div>${dots}</div>`;
  } else {
    const avatarContent = (persona && State.avatarImages[persona.id])
      ? `<img src="${State.avatarImages[persona.id]}" alt="${persona?.name}" />` : (persona?.avatar || '👤');
    row.innerHTML = `
      <div class="msg-avatar" style="background:${persona?.color||'#888'}22;border:2px solid ${persona?.color||'#888'}44;">${avatarContent}</div>
      <div class="msg-body"><div class="msg-name">${persona?.name||'メンバー'}</div>${dots}</div>`;
  }
  DOM.chatMessages.appendChild(row); scrollToBottom(); return row;
}
 
function addStreamingBubble(persona) {
  const row = document.createElement('div'); row.className = 'message-row member';
  const avatarContent = State.avatarImages[persona.id] ? `<img src="${State.avatarImages[persona.id]}" alt="${persona.name}" />` : persona.avatar;
  row.innerHTML = `
    <div class="msg-avatar" style="background:${persona.color}22;border:2px solid ${persona.color}44;">${avatarContent}</div>
    <div class="msg-body"><div class="msg-name">${persona.name}</div><div class="msg-bubble streaming"></div></div>`;
  DOM.chatMessages.appendChild(row); scrollToBottom(); return row;
}
 
function appendToStreamingBubble(row, text) {
  const bubble = row.querySelector('.msg-bubble');
  if (bubble) { bubble.textContent += text; scrollToBottom(); }
}
 
function addFacilitatorBanner() {
  const row = document.createElement('div'); row.className = 'message-row facilitator';
  row.innerHTML = `<div class="facilitator-banner"><div class="facilitator-label">🎯 ファシリテーター</div><div class="facilitator-text"></div></div>`;
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
 