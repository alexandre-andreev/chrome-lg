'use strict';

const chatEl = document.getElementById('chat');
const chatInput = document.getElementById('chatInput');
const sendBtn = document.getElementById('sendBtn');
const copyBtn = document.getElementById('copyBtn');
let currentTabId = null;
let lastUrlInActiveTab = null;
let panelVisible = true;
const defaultPlaceholder = (document.getElementById('chatInput')?.getAttribute('placeholder')) || 'Спросите ИИ… (Shift+Enter — новая строка)';

function sanitizeForDisplay(text) {
  if (!text) return text;
  let t = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
  // Remove markdown bold/italics markers but keep text
  t = t.replace(/\*\*([^*]+)\*\*/g, '$1');
  t = t.replace(/\*([^*]+)\*/g, '$1');
  t = t.replace(/__([^_]+)__/g, '$1');
  t = t.replace(/_([^_]+)_/g, '$1');
  // Remove inline code markers
  t = t.replace(/`([^`]+)`/g, '$1');
  // Collapse multiple blank lines
  t = t.replace(/\n{3,}/g, '\n\n');
  return t;
}

function setBusy(busy) {
  if (busy) {
    sendBtn.disabled = true;
    chatInput.disabled = true;
    chatInput.setAttribute('placeholder', 'ИИ думает…');
  } else {
    sendBtn.disabled = false;
    chatInput.disabled = false;
    chatInput.setAttribute('placeholder', defaultPlaceholder);
  }
}

function pushMsg(role, text) {
  const wrap = document.createElement('div');
  wrap.className = 'msg ' + (role === 'user' ? 'user' : 'assistant');
  const meta = document.createElement('div');
  meta.className = 'meta';
  meta.textContent = role === 'user' ? 'Вы' : 'ИИ';
  const body = document.createElement('div');
  body.textContent = sanitizeForDisplay(text);
  wrap.appendChild(meta);
  wrap.appendChild(body);
  chatEl.appendChild(wrap);
  chatEl.scrollTop = chatEl.scrollHeight;
}

async function getBackendBaseUrl() {
  return new Promise(resolve => {
    chrome.storage.local.get({ backendBaseUrl: 'http://127.0.0.1:8010' }, (res) => {
      resolve(res.backendBaseUrl.replace(/\/$/, ''));
    });
  });
}

async function sendChat(message) {
  const baseUrl = await getBackendBaseUrl();
  if (!/^https?:\/\//i.test(baseUrl)) {
    throw new Error('Некорректный URL бэкенда в настройках');
  }
  let pageUrl = null, pageTitle = null, pageText = null;

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  currentTabId = tab?.id;

  if (!currentTabId) {
    pushMsg('assistant', 'Не удалось определить активную вкладку.');
    return;
  }

  let pageData = null;
  try {
    pageData = await new Promise((resolve) => {
      chrome.tabs.sendMessage(currentTabId, { type: 'REQUEST_CONTEXT' }, (resp) => {
        if (chrome.runtime.lastError) return resolve(null);
        resolve(resp || null);
      });
    });
  } catch (_) {}

  pageUrl = pageData?.url || tab.url;
  pageTitle = pageData?.title || tab.title;
  pageText = pageData?.text || '';

  lastUrlInActiveTab = pageUrl;

  setBusy(true);
  try {
    // Try streaming endpoint first
    try {
      const resp = await fetch(baseUrl + '/chat_stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, page_url: pageUrl, page_title: pageTitle, page_text: pageText })
      });
      if (resp.ok && (resp.headers.get('content-type') || '').includes('text/plain')) {
        // Create a single assistant bubble once and append chunks there
        let wrap = document.getElementById('streaming-answer');
        let body;
        if (!wrap) {
          wrap = document.createElement('div');
          wrap.className = 'msg assistant';
          wrap.id = 'streaming-answer';
          const meta = document.createElement('div');
          meta.className = 'meta';
          meta.textContent = 'ИИ';
          body = document.createElement('div');
          body.id = 'streaming-answer-body';
          body.textContent = '';
          wrap.appendChild(meta);
          wrap.appendChild(body);
          chatEl.appendChild(wrap);
          chatEl.scrollTop = chatEl.scrollHeight;
        } else {
          body = document.getElementById('streaming-answer-body') || wrap;
        }

        const reader = resp.body.getReader();
        const decoder = new TextDecoder('utf-8');
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          const chunk = decoder.decode(value, { stream: true });
          body.textContent = sanitizeForDisplay(body.textContent + chunk);
          chatEl.scrollTop = chatEl.scrollHeight;
        }
        // remove id to avoid reuse next time
        if (wrap) {
          wrap.removeAttribute('id');
          if (body) body.removeAttribute('id');
        }
        return { streamed: true, answer: body.textContent, used_search: false, sources: [] };
      }
    } catch (_) { /* fall back below */ }

    // Fallback to non-streaming
    const resp = await fetch(baseUrl + '/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, page_url: pageUrl, page_title: pageTitle, page_text: pageText })
    });
    if (!resp.ok) throw new Error('Ошибка сервера: ' + resp.status);
    const data = await resp.json();
    if (data && typeof data.answer === 'string') {
      data.answer = sanitizeForDisplay(data.answer);
    }
    return data;
  } finally {
    setBusy(false);
  }
}

function hasExplicitSearchIntent(text) {
  const t = (text || '').toLowerCase();
  return /\b(найди|ищи|поиск|в интернете|посмотри в интернете|где находится|адрес|контакт|кто еще|кто ещё|альтернатив|конкурент)\b/.test(t);
}

// Send on button click
sendBtn?.addEventListener('click', async () => {
  const text = (chatInput.value || '').trim();
  if (!text) return;
  chatInput.value = '';
  pushMsg('user', text);
  try {
    const data = await sendChat(text);
    if (data?.answer && !data?.streamed) pushMsg('assistant', data.answer);
    // Render external sources only if search was used AND user explicitly asked to search
    if (hasExplicitSearchIntent(text) && data?.used_search && Array.isArray(data?.sources) && data.sources.length) {
      try {
        const baseHost = new URL(lastUrlInActiveTab || '').hostname;
        const links = data.sources
          .map(s => s?.url)
          .filter(u => {
            if (!u || typeof u !== 'string') return false;
            try { return new URL(u).hostname !== baseHost; } catch { return false; }
          });
        if (links.length) {
          pushMsg('assistant', 'Внешние источники:\n' + links.join('\n'));
        }
      } catch (_) {}
    }
  } catch (e) {
    pushMsg('assistant', 'Ошибка: ' + (e?.message || String(e)));
  }
});

// Enter handling: Shift+Enter -> newline; Enter -> send
chatInput?.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') {
    if (e.shiftKey) {
      // allow newline
      return;
    }
    e.preventDefault();
    sendBtn?.click();
  }
});

// Copy chat content
copyBtn?.addEventListener('click', async () => {
  try {
    const lines = Array.from(chatEl.querySelectorAll('.msg')).map(w => {
      const who = w.querySelector('.meta')?.textContent || '';
      const text = w.querySelector('div:nth-child(2)')?.textContent || '';
      return (who ? who + ': ' : '') + text;
    });
    const blob = new Blob([lines.join('\n\n')], { type: 'text/plain' });
    await navigator.clipboard.writeText(await blob.text());
    copyBtn.textContent = 'Скопировано';
    setTimeout(() => { copyBtn.textContent = 'Копировать'; }, 1500);
  } catch (e) {
    copyBtn.textContent = 'Ошибка';
    setTimeout(() => { copyBtn.textContent = 'Копировать'; }, 1500);
  }
});

// Refresh context on tab changes while the side panel is open
chrome.tabs.onActivated.addListener(async ({ tabId }) => {
  if (currentTabId !== tabId) {
    currentTabId = tabId;
    if (chatEl) chatEl.innerHTML = '';
    try {
      const tab = await chrome.tabs.get(tabId);
      lastUrlInActiveTab = tab.url;
    } catch (e) {
      lastUrlInActiveTab = null;
    }
  }
});

chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  if (changeInfo.status === 'complete' && currentTabId === tabId) {
    const newUrl = tab.url;
    let shouldClear = true;
    if (lastUrlInActiveTab && newUrl) {
      try {
        const prev = new URL(lastUrlInActiveTab);
        const next = new URL(newUrl);
        if (prev.hostname === next.hostname) {
          shouldClear = false;
        }
      } catch (e) {
        shouldClear = true;
      }
    }

    if (shouldClear) {
      if (chatEl) chatEl.innerHTML = '';
    }
    lastUrlInActiveTab = newUrl;
  }
});

document.addEventListener('DOMContentLoaded', async () => {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    currentTabId = tab?.id;
    lastUrlInActiveTab = tab?.url;
  } catch (_) {}
});



