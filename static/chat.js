const messagesEl = document.getElementById('messages');
const emptyStateEl = document.getElementById('emptyState');
const chatScrollEl = document.getElementById('chatScroll');
const composerForm = document.getElementById('composerForm');
const messageInput = document.getElementById('messageInput');
const sendBtn = document.getElementById('sendBtn');
const newChatBtn = document.getElementById('newChatBtn');
const chatHistoryEl = document.getElementById('chatHistory');

// In-memory session state (per browser tab)
let conversations = {};      // id -> { title, turns: [{role, content}] }
let activeId = null;
let isStreaming = false;

function uid() {
  return 'c_' + Math.random().toString(36).slice(2, 10);
}

function createConversation() {
  const id = uid();
  conversations[id] = { title: 'New chat', turns: [] };
  activeId = id;
  renderHistory();
  clearMessages();
  return id;
}

function clearMessages() {
  messagesEl.innerHTML = '';
  emptyStateEl.classList.remove('hidden');
}

function renderHistory() {
  chatHistoryEl.innerHTML = '';
  Object.entries(conversations).forEach(([id, convo]) => {
    if (convo.turns.length === 0) return;
    const item = document.createElement('div');
    item.className = 'chat-history-item' + (id === activeId ? ' active' : '');
    item.textContent = convo.title;
    item.addEventListener('click', () => switchConversation(id));
    chatHistoryEl.appendChild(item);
  });
}

function switchConversation(id) {
  activeId = id;
  renderHistory();
  clearMessages();
  const convo = conversations[id];
  if (convo.turns.length > 0) {
    emptyStateEl.classList.add('hidden');
    convo.turns.forEach(turn => {
      if (turn.role === 'user') {
        appendUserMessage(turn.content);
      } else {
        appendAssistantMessage(turn.content, turn.sources || []);
      }
    });
  }
}

function appendUserMessage(text) {
  emptyStateEl.classList.add('hidden');
  const wrap = document.createElement('div');
  wrap.className = 'msg msg-user';
  const bubble = document.createElement('div');
  bubble.className = 'msg-bubble-user';
  bubble.textContent = text;
  wrap.appendChild(bubble);
  messagesEl.appendChild(wrap);
  scrollToBottom();
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function simpleMarkdownToHtml(text) {
  // Minimal, safe rendering: escape first, then handle paragraphs, code spans, bold.
  const escaped = escapeHtml(text);
  const withCode = escaped.replace(/`([^`]+)`/g, '<code>$1</code>');
  const withBold = withCode.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  return withBold
    .split(/\n{2,}/)
    .map(p => `<p>${p.replace(/\n/g, '<br>')}</p>`)
    .join('');
}

function appendAssistantMessage(initialText, sources) {
  const wrap = document.createElement('div');
  wrap.className = 'msg msg-assistant';

  const avatarRow = document.createElement('div');
  avatarRow.className = 'msg-avatar-row';
  avatarRow.innerHTML = `<span class="assistant-mark"></span><span class="assistant-name">Second Brain</span>`;
  wrap.appendChild(avatarRow);

  const content = document.createElement('div');
  content.className = 'msg-assistant-content';
  content.innerHTML = simpleMarkdownToHtml(initialText || '');
  wrap.appendChild(content);

  if (sources && sources.length > 0) {
    wrap.appendChild(buildSourcesPanel(sources));
  }

  messagesEl.appendChild(wrap);
  scrollToBottom();
  return { wrap, content };
}

function buildSourcesPanel(sources) {
  const panel = document.createElement('div');
  panel.className = 'sources-panel';

  const toggle = document.createElement('button');
  toggle.type = 'button';
  toggle.className = 'sources-toggle';
  toggle.innerHTML = `<span>${sources.length} source${sources.length !== 1 ? 's' : ''} from your notes</span><span class="chevron">›</span>`;
  toggle.addEventListener('click', () => panel.classList.toggle('open'));
  panel.appendChild(toggle);

  const list = document.createElement('div');
  list.className = 'sources-list';
  sources.forEach(s => {
    const item = document.createElement('div');
    item.className = 'source-item';
    item.innerHTML = `
      <div class="source-item-header">
        <span class="source-index">[${s.index}]</span>
        <span class="source-path">${escapeHtml(s.file_path)}</span>
      </div>
      <div class="source-section">${escapeHtml(s.header)}</div>
      <p class="source-snippet">${escapeHtml(s.snippet)}</p>
      <div class="source-score">RRF score ${s.score}</div>
    `;
    list.appendChild(item);
  });
  panel.appendChild(list);
  return panel;
}

function scrollToBottom() {
  chatScrollEl.scrollTop = chatScrollEl.scrollHeight;
}

function autoResize() {
  messageInput.style.height = 'auto';
  messageInput.style.height = Math.min(messageInput.scrollHeight, 200) + 'px';
}

function updateSendState() {
  sendBtn.disabled = messageInput.value.trim().length === 0 || isStreaming;
}

messageInput.addEventListener('input', () => {
  autoResize();
  updateSendState();
});

messageInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    composerForm.requestSubmit();
  }
});

newChatBtn.addEventListener('click', () => {
  if (isStreaming) return;
  createConversation();
});

composerForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const text = messageInput.value.trim();
  if (!text || isStreaming) return;

  if (!activeId) createConversation();
  const convo = conversations[activeId];

  if (convo.turns.length === 0) {
    convo.title = text.slice(0, 40) + (text.length > 40 ? '…' : '');
  }
  convo.turns.push({ role: 'user', content: text });
  renderHistory();

  appendUserMessage(text);
  messageInput.value = '';
  autoResize();
  isStreaming = true;
  updateSendState();

  const assistantTurn = { role: 'assistant', content: '', sources: [] };
  convo.turns.push(assistantTurn);

  const { content: contentEl, wrap } = appendAssistantMessage('', []);
  const cursor = document.createElement('span');
  cursor.className = 'cursor-blink';
  contentEl.appendChild(cursor);

  let fullText = '';
  let sourcesRendered = false;

  try {
    const resp = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: text,
        history: convo.turns.slice(0, -1).map(t => ({ role: t.role, content: t.content }))
      })
    });

    if (!resp.ok || !resp.body) {
      throw new Error('Server error: ' + resp.status);
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const events = buffer.split('\n\n');
      buffer = events.pop(); // keep incomplete chunk

      for (const evt of events) {
        const line = evt.trim();
        if (!line.startsWith('data:')) continue;
        const payload = JSON.parse(line.slice(5).trim());

        if (payload.type === 'sources') {
          assistantTurn.sources = payload.sources;
          if (!sourcesRendered && payload.sources.length > 0) {
            wrap.appendChild(buildSourcesPanel(payload.sources));
            sourcesRendered = true;
          }
        } else if (payload.type === 'token') {
          fullText += payload.content;
          assistantTurn.content = fullText;
          contentEl.innerHTML = simpleMarkdownToHtml(fullText);
          contentEl.appendChild(cursor);
          scrollToBottom();
        } else if (payload.type === 'error') {
          const err = document.createElement('div');
          err.className = 'error-banner';
          err.textContent = payload.error;
          wrap.appendChild(err);
        } else if (payload.type === 'done') {
          cursor.remove();
        }
      }
    }
  } catch (err) {
    cursor.remove();
    const errBanner = document.createElement('div');
    errBanner.className = 'error-banner';
    errBanner.textContent = 'Connection error: ' + err.message;
    wrap.appendChild(errBanner);
  } finally {
    isStreaming = false;
    updateSendState();
  }
});

// Boot
createConversation();
updateSendState();
