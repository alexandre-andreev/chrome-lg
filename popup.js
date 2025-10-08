'use strict';

const chatEl = document.getElementById('chat');
const statusEl = document.getElementById('status');
const chatInput = document.getElementById('chatInput');
const sendBtn = document.getElementById('sendBtn');
const usePageBtn = document.getElementById('usePageBtn');

function pushMsg(role, text) {
  const wrap = document.createElement('div');
  wrap.style.marginBottom = '8px';
  const who = document.createElement('div');
  who.className = 'muted';
  who.textContent = role === 'user' ? 'Вы' : 'ИИ';
  const msg = document.createElement('div');
  msg.textContent = text;
  wrap.appendChild(who);
  wrap.appendChild(msg);
  chatEl.appendChild(wrap);
  chatEl.scrollTop = chatEl.scrollHeight;
}

async function getBackendBaseUrl() {
  return new Promise(resolve => {
    chrome.storage.local.get({ backendBaseUrl: 'http://127.0.0.1:8090' }, (res) => {
      resolve((res.backendBaseUrl || 'http://127.0.0.1:8090').replace(/\/$/, ''));
    });
  });
}

usePageBtn?.addEventListener('click', async () => {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id) throw new Error('Нет активной вкладки');
    const [{ result: pageData }] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => ({
        text: (document.body && document.body.innerText ? document.body.innerText : '').slice(0, 20000),
        title: document.title,
        url: location.href,
      })
    });
    chatInput.value = `Проанализируй страницу: ${pageData.title}\nURL: ${pageData.url}\nТекст (фрагмент):\n${pageData.text.slice(0, 2000)}`;
    chatInput.focus();
  } catch (e) {
    statusEl.textContent = 'Ошибка вставки контекста: ' + (e?.message || String(e));
  }
});

async function sendChat(message) {
  const baseUrl = await getBackendBaseUrl();
  if (!/^https?:\/\//i.test(baseUrl)) {
    throw new Error('Некорректный URL бэкенда в настройках');
  }
  const resp = await fetch(baseUrl + '/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message })
  });
  if (!resp.ok) throw new Error('Ошибка сервера: ' + resp.status);
  const data = await resp.json();
  return data;
}

sendBtn?.addEventListener('click', async () => {
  const text = (chatInput.value || '').trim();
  if (!text) return;
  chatInput.value = '';
  pushMsg('user', text);
  statusEl.textContent = 'Генерация…';
  try {
    const data = await sendChat(text);
    if (data?.answer) pushMsg('assistant', data.answer);
    if (Array.isArray(data?.sources) && data.sources.length) {
      pushMsg('assistant', 'Источники:');
      data.sources.forEach(s => pushMsg('assistant', `${s.title || s.url} — ${s.url}`));
    }
  } catch (e) {
    pushMsg('assistant', 'Ошибка: ' + (e?.message || String(e)));
  } finally {
    statusEl.textContent = '';
  }
});


