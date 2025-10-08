'use strict';

const chatEl = document.getElementById('chat');
const chatInput = document.getElementById('chatInput');
const sendBtn = document.getElementById('sendBtn');
const copyBtn = document.getElementById('copyBtn');
let currentTabId = null;
let lastUrlInActiveTab = null;
let panelVisible = true;
const defaultPlaceholder = (document.getElementById('chatInput')?.getAttribute('placeholder')) || 'Спросите ИИ… (Shift+Enter — новая строка)';
let ttsActive = false;
let ttsUtterance = null;
let ttsEngine = null; // 'chrome' | 'speech' | null
let ttsQueue = [];
let ttsIndex = 0;
let sberAudio = null; // HTMLAudioElement for Sber playback

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

function setBusy(busy, label) {
  const ttsBtn = document.getElementById('ttsBtn');
  const exportBtn = document.getElementById('exportBtn');
  const copyMdBtn = document.getElementById('copyMdBtn');
  if (busy) {
    sendBtn.disabled = true;
    chatInput.disabled = true;
    chatInput.setAttribute('placeholder', label || 'Занято…');
    if (exportBtn) exportBtn.disabled = true;
    if (copyMdBtn) copyMdBtn.disabled = true;
  } else {
    sendBtn.disabled = false;
    chatInput.disabled = false;
    chatInput.setAttribute('placeholder', defaultPlaceholder);
    if (exportBtn) exportBtn.disabled = false;
    if (copyMdBtn) copyMdBtn.disabled = false;
  }
}

function pushMsg(role, text, opts) {
  const wrap = document.createElement('div');
  const classes = ['msg', (role === 'user' ? 'user' : 'assistant')];
  if (role !== 'user' && opts && opts.className) classes.push(opts.className);
  wrap.className = classes.join(' ');
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
    chrome.storage.local.get({ backendBaseUrl: 'http://127.0.0.1:8090' }, (res) => {
      resolve((res.backendBaseUrl || 'http://127.0.0.1:8090').replace(/\/$/, ''));
    });
  });
}

function renderSettingsForm(container, cfg, opts) {
  container.innerHTML = '';
  // Local connection settings (always shown)
  const sectionConn = document.createElement('div');
  sectionConn.style.marginBottom = '12px';
  const hConn = document.createElement('div');
  hConn.textContent = 'Подключение';
  hConn.style.fontWeight = '600';
  hConn.style.marginBottom = '6px';
  const rowConn = document.createElement('label');
  rowConn.style.display = 'flex';
  rowConn.style.alignItems = 'center';
  rowConn.style.justifyContent = 'space-between';
  rowConn.style.gap = '8px';
  const spanConn = document.createElement('span');
  spanConn.textContent = 'backendBaseUrl';
  spanConn.style.fontSize = '12px';
  spanConn.style.color = '#4a5b76';
  const inputConn = document.createElement('input');
  inputConn.type = 'text';
  inputConn.id = 'local_backendBaseUrl';
  inputConn.style.width = '220px';
  inputConn.placeholder = 'http://127.0.0.1:8090';
  rowConn.appendChild(spanConn);
  rowConn.appendChild(inputConn);
  sectionConn.appendChild(hConn);
  sectionConn.appendChild(rowConn);
  container.appendChild(sectionConn);
  // Load current baseUrl
  try {
    chrome.storage.local.get({ backendBaseUrl: 'http://127.0.0.1:8090' }, (res) => {
      inputConn.value = (res.backendBaseUrl || 'http://127.0.0.1:8090').replace(/\/$/, '');
    });
  } catch (_) {}
  if (!cfg || typeof cfg !== 'object') {
    const warn = document.createElement('div');
    warn.textContent = 'Не удалось загрузить параметры сервера (/config). Проверьте backendBaseUrl и повторите.';
    warn.style.fontSize = '12px';
    warn.style.color = '#a33';
    warn.style.marginTop = '8px';
    container.appendChild(warn);
    return;
  }
  const fields = [
    ['STREAMING_ENABLED', 'checkbox', 'Стриминг (/chat_stream).\nВкл: интерактивно, быстрее видны токены; может падать при сетевых сбоях.\nВыкл: стабильнее, ответ одним JSON.'],
    ['GEMINI_MODEL', 'text', 'Модель Gemini.\nБолее “тяжёлая” (например, 2.5‑flash) — качественнее, медленнее.\n“Лёгкая” (2.0‑flash‑lite) — быстрее, короче.'],
    ['RAG_ENABLED', 'checkbox', 'Локальный RAG (индекс по хосту).\nВкл: подмешиваем релевантные чанки из индекса.\nВыкл: только текст страницы + поиск EXA.'],
    ['RAG_TOP_K', 'number', 'Сколько RAG‑чанков в промпт.\nБольше: выше полнота, больше токенов и шум.\nМеньше: компактнее, риск недочитать.'],
    ['RAG_DEBUG', 'checkbox', 'Отладка RAG (upserted/retrieved) в ответе.'],
    ['LG_CHUNK_SIZE', 'number', 'Размер чанка страницы.\nБольше: меньше чанков, внутри больше контекста.\nМеньше: точнее локализация фактов, больше чанков.'],
    ['LG_CHUNK_OVERLAP', 'number', 'Перекрытие чанков.\nБольше: лучше связность, дороже по вычислениям.\nМеньше: быстрее, возможны “обрывы” контекста.'],
    ['LG_CHUNK_MIN_TOTAL', 'number', 'Порог длины для разбиения.\n0: авто (≈2×CHUNK_SIZE).\nМеньше: чаще режем. Больше: реже режем.'],
    ['LG_CHUNK_NOTES_MAX_CHUNKS', 'number', 'Сколько чанков использовать для заметок.\nБольше: богаче заметки, выше стоимость.'],
    ['LG_NOTES_MAX', 'number', 'Максимум заметок, которые генерируем.\nБольше: шире покрытие, возможен “шум”.'],
    ['LG_NOTES_SHOW_MAX', 'number', 'Сколько заметок включаем в промпт.\nБольше: больше фактов, больше токенов.'],
    ['LG_SEARCH_MIN_CONTEXT_CHARS', 'number', 'Порог включения EXA.\nМеньше: поиск срабатывает чаще.\nБольше: реже зовём поиск.'],
    ['LG_PROMPT_TEXT_CHARS', 'number', 'Максимум символов TEXT в промпте.\nБольше: LLM “видит” больше страницы, дороже.'],
    ['LG_EXA_TIME_BUDGET_S', 'number', 'Лимит времени EXA.\nБольше: шанс лучше найти, медленнее ответ.'],
    ['LG_SEARCH_RESULTS_MAX', 'number', 'Сколько EXA‑сниппетов в промпт.\nБольше: шире контекст, больше токенов/шум.'],
    ['LG_SEARCH_SNIPPET_CHARS', 'number', 'Длина EXA‑сниппета.\nБольше: информативнее, дороже по токенам.'],
    ['LG_ANSWER_MAX_SENTENCES', 'number', 'Ограничитель длины ответа.\n0: без лимита. >0: обрезаем до N предложений.'],
    ['LG_SEARCH_HEURISTICS', 'checkbox', 'Эвристики “найди в интернете…”.\nВкл: явные формулировки форсят поиск.'],
    // EXA tuning
    ['EXA_NUM_RESULTS', 'number', 'Сколько результатов искать. Больше = шире охват, медленнее.'],
    ['EXA_GET_CONTENTS_N', 'number', 'Сколько топ-URL догружать полным текстом.'],
    ['EXA_SUBPAGES', 'number', 'Глубина субстраниц при dogruzke contents (0/1).'],
    ['EXA_EXTRAS_LINKS', 'checkbox', 'Тянуть ссылки из contents (для расширения контекста).'],
    ['EXA_TEXT_MAX_CHARS', 'number', 'Максимум символов текста на источник.'],
    ['EXA_LANG', 'text', 'Язык для поиска (auto/ru/en).'],
    ['EXA_EXCLUDE_DOMAINS', 'text', 'Черный список доменов (через запятую).'],
    ['EXA_TIMEOUT_S', 'number', 'Таймаут запроса Exa, сек.'],
    ['EXA_RESEARCH_ENABLED', 'checkbox', 'Разрешить research fallback (когда поиска не хватает).'],
    ['EXA_RESEARCH_TIMEOUT_S', 'number', 'Таймаут research, сек.'],
    ['EXA_SUMMARY_ENABLED', 'checkbox', 'Разрешить summary (серверная выжимка Exa)'],
  ];
  for (const [key, type] of fields) {
    const row = document.createElement('label');
    row.style.display = 'flex';
    row.style.alignItems = 'center';
    row.style.justifyContent = 'space-between';
    row.style.gap = '8px';
    const span = document.createElement('span');
    span.textContent = key;
    span.style.fontSize = '12px';
    span.style.color = '#4a5b76';
    const input = document.createElement('input');
    input.id = 'cfg_' + key;
    // tooltip
    const def = fields.find(f => f[0] === key);
    if (def && def[2]) { span.title = def[2]; input.title = def[2]; row.title = def[2]; }

    if (type === 'checkbox') {
      input.type = 'checkbox';
      input.checked = ['1','true','yes'].includes(String(cfg?.[key] || '').toLowerCase());
    } else {
      input.type = (type === 'text' ? 'text' : 'number');
      input.value = cfg?.[key] ?? '';
      input.style.width = (type === 'text' ? '180px' : '110px');
    }
    row.appendChild(span);
    row.appendChild(input);
    container.appendChild(row);
  }
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
  // Fallbacks if text is empty/too short
  if (!pageText || pageText.length < 50) {
    try {
      const [{ result }] = await chrome.scripting.executeScript({
        target: { tabId: currentTabId },
        func: () => ({
          text: (document.body && document.body.innerText ? document.body.innerText : '').slice(0, 30000),
          title: document.title,
          url: location.href,
        })
      });
      if (result) {
        pageText = result.text || pageText;
        pageTitle = result.title || pageTitle;
        pageUrl = result.url || pageUrl;
      }
    } catch (_) {}
    if (!pageText || pageText.length < 50) {
      try {
        const cached = await new Promise(resolve => chrome.storage.local.get({ lastPageContext: null }, r => resolve(r.lastPageContext)));
        if (cached && cached.text) {
          pageText = cached.text;
          pageTitle = cached.title || pageTitle;
          pageUrl = cached.url || pageUrl;
        }
      } catch (_) {}
    }
  }

  lastUrlInActiveTab = pageUrl;

  setBusy(true, 'ИИ думает…');
  try {
    // Try streaming endpoint first
    try {
      const resp = await fetch(baseUrl + '/chat_stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, page_url: pageUrl, page_title: pageTitle, page_text: pageText, force_search: !!document.getElementById('forceSearchToggle')?.checked })
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
        // After stream ends, detect sources marker and highlight if search was used
        try {
          const txt = body.textContent || '';
          const markerIdx = txt.lastIndexOf('\n\nИсточники:\n');
          let usedSearch = false;
          let urls = [];
          if (markerIdx !== -1) {
            usedSearch = true;
            const lines = txt.substring(markerIdx + 13).split('\n');
            urls = lines.map(s => s.trim()).filter(s => /^https?:\/\//i.test(s));
            // strip sources marker from the main streamed bubble
            const before = txt.substring(0, markerIdx).trimEnd();
            body.textContent = before;
            // mark streamed bubble as EXA-used
            if (wrap && !wrap.className.includes('exa')) {
              wrap.className = 'msg assistant exa';
            }
            // render clickable sources bubble similar to non-streaming path
            if (urls.length) {
              const sWrap = document.createElement('div');
              sWrap.className = 'msg assistant exa';
              const meta = document.createElement('div');
              meta.className = 'meta';
              meta.textContent = 'Источники';
              const bodyDiv = document.createElement('div');
              const list = document.createElement('div');
              urls.slice(0, 6).forEach(u => {
                const a = document.createElement('a');
                a.href = u;
                a.target = '_blank';
                a.rel = 'noopener noreferrer';
                a.textContent = u;
                const line = document.createElement('div');
                line.appendChild(a);
                list.appendChild(line);
              });
              bodyDiv.appendChild(list);
              sWrap.appendChild(meta);
              sWrap.appendChild(bodyDiv);
              chatEl.appendChild(sWrap);
              chatEl.scrollTop = chatEl.scrollHeight;
            }
          }
          // remove id to avoid reuse next time
          if (wrap) {
            wrap.removeAttribute('id');
            if (body) body.removeAttribute('id');
          }
          return { streamed: true, answer: txt, used_search: usedSearch, sources: urls.map(u => ({ url: u })) };
        } catch (_) {
          // remove id to avoid reuse next time
          if (wrap) {
            wrap.removeAttribute('id');
            if (body) body.removeAttribute('id');
          }
          return { streamed: true, answer: body.textContent, used_search: false, sources: [] };
        }
      }
    } catch (_) { /* fall back below */ }

    // Fallback to non-streaming
    const resp = await fetch(baseUrl + '/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, page_url: pageUrl, page_title: pageTitle, page_text: pageText, force_search: !!document.getElementById('forceSearchToggle')?.checked })
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

// Export current page to Markdown (file)
async function exportCurrentPageToMarkdown() {
  const baseUrl = await getBackendBaseUrl();
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const currentTabIdLocal = tab?.id;
  if (!currentTabIdLocal) {
    pushMsg('assistant', 'Не удалось определить активную вкладку.');
    return;
  }
  setBusy(true, 'Идёт экспорт…');
  let pageData = null;
  try {
    pageData = await new Promise((resolve) => {
      chrome.tabs.sendMessage(currentTabIdLocal, { type: 'REQUEST_CONTEXT' }, (resp) => {
        if (chrome.runtime.lastError) return resolve(null);
        resolve(resp || null);
      });
    });
  } catch (_) {}
  const pageUrl = pageData?.url || tab.url;
  const pageTitle = pageData?.title || tab.title;
  let pageText = pageData?.text || '';
  // Fallback when content script is blocked or returns too short text
  if (!pageText || pageText.length < 50) {
    try {
      const [{ result }] = await chrome.scripting.executeScript({
        target: { tabId: currentTabIdLocal },
        func: () => ({
          text: (document.body && document.body.innerText ? document.body.innerText : '').slice(0, 30000),
          title: document.title,
          url: location.href,
        })
      });
      if (result && result.text) pageText = result.text;
    } catch (_) {}
    if (!pageText || pageText.length < 50) {
      try {
        const cached = await new Promise(resolve => chrome.storage.local.get({ lastPageContext: null }, r => resolve(r.lastPageContext)));
        if (cached && cached.text) pageText = cached.text;
      } catch (_) {}
    }
  }
  try {
    const resp = await fetch(baseUrl + '/export_md', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ page_url: pageUrl, page_title: pageTitle, page_text: pageText })
    });
    if (!resp.ok) throw new Error('Ошибка сервера: ' + resp.status);
    const data = await resp.json();
    if (data?.filename && data?.content) {
      const blob = new Blob([data.content], { type: 'text/markdown;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = data.filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      pushMsg('assistant', 'Экспортировано: ' + data.filename);
    } else {
      pushMsg('assistant', 'Не удалось получить Markdown.');
    }
  } catch (e) {
    pushMsg('assistant', 'Ошибка экспорта: ' + (e?.message || String(e)));
  }
  setBusy(false);
}

// Copy current page to clipboard (Markdown)
async function copyCurrentPageMarkdownToClipboard() {
  const baseUrl = await getBackendBaseUrl();
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const currentTabIdLocal = tab?.id;
  if (!currentTabIdLocal) {
    pushMsg('assistant', 'Не удалось определить активную вкладку.');
    return;
  }
  setBusy(true, 'Идёт копирование в буфер обмена…');
  let pageData = null;
  try {
    pageData = await new Promise((resolve) => {
      chrome.tabs.sendMessage(currentTabIdLocal, { type: 'REQUEST_CONTEXT' }, (resp) => {
        if (chrome.runtime.lastError) return resolve(null);
        resolve(resp || null);
      });
    });
  } catch (_) {}
  const pageUrl = pageData?.url || tab.url;
  const pageTitle = pageData?.title || tab.title;
  let pageText = pageData?.text || '';
  if (!pageText || pageText.length < 50) {
    try {
      const [{ result }] = await chrome.scripting.executeScript({
        target: { tabId: currentTabIdLocal },
        func: () => ({
          text: (document.body && document.body.innerText ? document.body.innerText : '').slice(0, 30000),
          title: document.title,
          url: location.href,
        })
      });
      if (result && result.text) pageText = result.text;
    } catch (_) {}
    if (!pageText || pageText.length < 50) {
      try {
        const cached = await new Promise(resolve => chrome.storage.local.get({ lastPageContext: null }, r => resolve(r.lastPageContext)));
        if (cached && cached.text) pageText = cached.text;
      } catch (_) {}
    }
  }

  try {
    const resp = await fetch(baseUrl + '/export_md', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ page_url: pageUrl, page_title: pageTitle, page_text: pageText })
    });
    if (!resp.ok) throw new Error('Ошибка сервера: ' + resp.status);
    const data = await resp.json();
    if (data?.content) {
      await navigator.clipboard.writeText(data.content);
      pushMsg('assistant', 'Скопировано в буфер обмена (Markdown)');
    } else {
      pushMsg('assistant', 'Не удалось получить Markdown.');
    }
  } catch (e) {
    pushMsg('assistant', 'Ошибка копирования: ' + (e?.message || String(e)));
  }
  setBusy(false);
}

function cleanForSpeech(text) {
  let t = String(text || '')
    .replace(/\s+/g, ' ')
    .replace(/\[[^\]]+\]/g, '')
    .replace(/https?:\/\/\S+/g, '')
    .replace(/\|/g, ', ')
    .trim();
  t = t.replace(/([.!?]){2,}/g, '$1 ');
  return t;
}

async function getCleanPageTextForSpeech() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) throw new Error('Нет активной вкладки');
  let pageData = null;
  try {
    pageData = await new Promise(resolve => chrome.tabs.sendMessage(tab.id, { type: 'REQUEST_CONTEXT' }, resp => resolve(resp || null)));
  } catch (_) {}
  let text = pageData?.text || '';
  if (!text || text.length < 200) {
    try {
      const [{ result }] = await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: () => {
        const sel = document.querySelector('main,[role="main"],article,.article__content,.tm-article-body,.post__text,.post-content,.entry-content,.content');
        const raw = (sel?.innerText || document.body?.innerText || '');
        return raw.slice(0, 30000);
      }});
      if (result) text = result;
    } catch (_) {}
  }
  // Send to server for logging/cleaning parity
  try {
    const baseUrl = await getBackendBaseUrl();
    // Try summarize endpoint first (speech-friendly text via Gemini)
    let resp = await fetch(baseUrl + '/tts_summarize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ page_url: tab.url, page_title: tab.title, page_text: text })
    });
    if (!resp.ok) {
      // Fallback to simple prepare endpoint
      resp = await fetch(baseUrl + '/tts_prepare', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ page_url: tab.url, page_title: tab.title, page_text: text })
      });
    }
    if (resp.ok) {
      const data = await resp.json();
      if (data && typeof data.text === 'string') {
        return String(data.text || '').slice(0, 8000);
      }
    }
  } catch (_) {}
  return cleanForSpeech(text).slice(0, 8000);
}

async function toggleSpeakCurrentPage() {
  const btn = document.getElementById('ttsBtn');
  if (ttsActive) {
    try {
      if (ttsEngine === 'chrome' && chrome?.tts?.stop) {
        chrome.tts.stop();
      } else {
        window.speechSynthesis.cancel();
      }
    } catch (_) {}
    ttsActive = false;
    ttsQueue = [];
    ttsIndex = 0;
    if (btn) {
      btn.textContent = '🔊';
      const def = btn.dataset.defaultTitle || 'Озвучка (прочитать страницу)';
      btn.setAttribute('title', def);
      btn.setAttribute('aria-label', 'Озвучка');
    }
    pushMsg('assistant', 'Озвучивание остановлено', { className: 'local' });
    setBusy(false);
    return;
  }
  try {
    setBusy(true, 'Идёт озвучивание текста…');
    const text = await getCleanPageTextForSpeech();
    if (!text || text.length < 50) {
      pushMsg('assistant', 'Нет текста для озвучки.', { className: 'local' });
      setBusy(false);
      return;
    }
    // Prefer Chrome TTS API if available (often более стабильна)
    if (chrome?.tts?.speak) {
      ttsEngine = 'chrome';
      // Build chunk queue (≈1200-1500 chars, по предложениям)
      ttsQueue = buildChunks(text, 1400);
      ttsIndex = 0;
      console.log('[TTS] chrome.tts queue size:', ttsQueue.length);
      if (!ttsQueue.length) {
        setBusy(false);
        pushMsg('assistant', 'Нет текста для озвучки.', { className: 'local' });
        return;
      }
      ttsActive = true;
      if (btn) {
        if (!btn.dataset.defaultTitle) btn.dataset.defaultTitle = btn.getAttribute('title') || 'Озвучка (прочитать страницу)';
        btn.textContent = '🔊';
        btn.setAttribute('title', 'Остановить озвучивание');
        btn.setAttribute('aria-label', 'Остановить озвучивание');
      }
      try { chrome.tts.stop?.(); } catch (_) {}
      speakNextChromeChunk();
      pushMsg('assistant', 'Озвучиваю страницу… (Chrome TTS)', { className: 'local' });
      return;
    }

    // Fallback: Web Speech API
    ttsEngine = 'speech';
    ttsQueue = buildChunks(text, 1200);
    ttsIndex = 0;
    console.log('[TTS] speech queue size:', ttsQueue.length);
    if (!ttsQueue.length) {
      setBusy(false);
      pushMsg('assistant', 'Нет текста для озвучки.', { className: 'local' });
      return;
    }
    ttsActive = true;
    if (btn) {
      if (!btn.dataset.defaultTitle) btn.dataset.defaultTitle = btn.getAttribute('title') || 'Озвучка (прочитать страницу)';
      btn.textContent = '🔊';
      btn.setAttribute('title', 'Остановить озвучивание');
      btn.setAttribute('aria-label', 'Остановить озвучивание');
    }
    speakNextSpeechChunk();
    pushMsg('assistant', 'Озвучиваю страницу… (Web Speech)', { className: 'local' });
  } catch (e) {
    pushMsg('assistant', 'Ошибка озвучки: ' + (e?.message || String(e)));
    setBusy(false);
  }
}

function buildChunks(text, maxLen) {
  const chunks = [];
  const sents = (String(text || '')).split(/(?<=[.!?])\s+/);
  let buf = '';
  for (const s of sents) {
    const seg = s.trim();
    if (!seg) continue;
    if (seg.length > maxLen) {
      // hard split long sentence
      for (let i = 0; i < seg.length; i += maxLen) {
        const piece = seg.slice(i, i + maxLen);
        if (buf) { chunks.push(buf); buf = ''; }
        chunks.push(piece);
      }
      continue;
    }
    if ((buf + ' ' + seg).trim().length > maxLen) {
      if (buf) chunks.push(buf);
      buf = seg;
    } else {
      buf = buf ? (buf + ' ' + seg) : seg;
    }
  }
  if (buf) chunks.push(buf);
  return chunks;
}

async function playSberTTS() {
  // Summarize text first (same as local TTS)
  setBusy(true, 'Идёт подготовка озвучки (Sber)…');
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id) throw new Error('Нет активной вкладки');
    // Reuse summarization pipeline
    let pageData = null;
    try { pageData = await new Promise(resolve => chrome.tabs.sendMessage(tab.id, { type: 'REQUEST_CONTEXT' }, resp => resolve(resp || null))); } catch (_) {}
    let text = pageData?.text || '';
    if (!text || text.length < 200) {
      try {
        const [{ result }] = await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: () => {
          const sel = document.querySelector('main,[role="main"],article,.article__content,.tm-article-body,.post__text,.post-content,.entry-content,.content');
          const raw = (sel?.innerText || document.body?.innerText || '');
          return raw.slice(0, 30000);
        }});
        if (result) text = result;
      } catch (_) {}
    }
    const baseUrl = await getBackendBaseUrl();
    // 1) server summarize (gemini)
    let resp = await fetch(baseUrl + '/tts_summarize', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ page_url: tab.url, page_title: tab.title, page_text: text }) });
    let speakText = '';
    if (resp.ok) { const data = await resp.json(); speakText = String((data && data.text) || '').slice(0, 8000); }
    if (!speakText) {
      // Fallback to prepare
      resp = await fetch(baseUrl + '/tts_prepare', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ page_url: tab.url, page_title: tab.title, page_text: text }) });
      if (resp.ok) { const data = await resp.json(); speakText = String((data && data.text) || '').slice(0, 8000); }
    }
    if (!speakText) throw new Error('Не удалось подготовить текст для озвучки');
    // 2) request audio from Sber
    const audioResp = await fetch(baseUrl + '/tts_sber_synthesize', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: speakText }) });
    if (!audioResp.ok) throw new Error('Синтез речи (Sber) завершился ошибкой: ' + audioResp.status);
    const blob = await audioResp.blob();
    const url = URL.createObjectURL(blob);
    // stop previous
    try { if (sberAudio) { sberAudio.pause(); URL.revokeObjectURL(sberAudio.src); } } catch (_) {}
    sberAudio = new Audio(url);
    sberAudio.onended = () => {
      try { URL.revokeObjectURL(url); } catch (_) {}
      sberAudio = null;
      const b = document.getElementById('sberTtsBtn');
      if (b) { b.setAttribute('title', 'Озвучка (Sber)'); b.setAttribute('aria-label', 'Озвучка (Sber)'); }
    };
    sberAudio.onerror = () => {
      try { URL.revokeObjectURL(url); } catch (_) {}
      sberAudio = null;
      const b = document.getElementById('sberTtsBtn');
      if (b) { b.setAttribute('title', 'Озвучка (Sber)'); b.setAttribute('aria-label', 'Озвучка (Sber)'); }
    };
    await sberAudio.play();
    const b = document.getElementById('sberTtsBtn');
    if (b) { b.setAttribute('title', 'Остановить озвучивание (Sber)'); b.setAttribute('aria-label', 'Остановить озвучивание (Sber)'); }
    pushMsg('assistant', 'Озвучиваю страницу… (Sber)', { className: 'local' });
  } finally {
    setBusy(false);
  }
}

function speakNextChromeChunk() {
  if (!ttsActive) return;
  if (ttsIndex >= ttsQueue.length) {
    // done
    ttsActive = false;
    setBusy(false);
    const b = document.getElementById('ttsBtn');
    if (b) {
      b.textContent = '🔊';
      const def = b.dataset.defaultTitle || 'Озвучка (прочитать страницу)';
      b.setAttribute('title', def);
      b.setAttribute('aria-label', 'Озвучка');
    }
    console.log('[TTS] chrome done');
    return;
  }
  const text = ttsQueue[ttsIndex];
  const isFirst = (ttsIndex === 0);
  console.log('[TTS] chrome speak chunk', ttsIndex + 1, '/', ttsQueue.length, 'len=', text.length);
  chrome.tts.speak(text, {
    enqueue: !isFirst,
    lang: (navigator.language || 'ru-RU'),
    rate: 1.0,
    pitch: 1.0,
    volume: 1.0,
    onEvent: (ev) => {
      if (!ttsActive) return;
      if (ev?.type === 'end') {
        ttsIndex += 1;
        speakNextChromeChunk();
      }
      if (ev?.type === 'interrupted' || ev?.type === 'cancelled' || ev?.type === 'error') {
        console.warn('[TTS] chrome event', ev?.type, 'at chunk', ttsIndex);
        ttsActive = false;
        setBusy(false);
        const b = document.getElementById('ttsBtn');
        if (b) {
          b.textContent = '🔊';
          const def = b.dataset.defaultTitle || 'Озвучка (прочитать страницу)';
          b.setAttribute('title', def);
          b.setAttribute('aria-label', 'Озвучка');
        }
      }
    }
  });
}

function speakNextSpeechChunk() {
  if (!ttsActive) return;
  if (ttsIndex >= ttsQueue.length) {
    ttsActive = false;
    setBusy(false);
    const b = document.getElementById('ttsBtn');
    if (b) {
      b.textContent = '🔊';
      const def = b.dataset.defaultTitle || 'Озвучка (прочитать страницу)';
      b.setAttribute('title', def);
      b.setAttribute('aria-label', 'Озвучка');
    }
    console.log('[TTS] speech done');
    return;
  }
  const text = ttsQueue[ttsIndex];
  console.log('[TTS] speech speak chunk', ttsIndex + 1, '/', ttsQueue.length, 'len=', text.length);
  const u = new SpeechSynthesisUtterance(text);
  u.lang = (navigator.language || 'ru-RU');
  try {
    const pickVoice = () => {
      const voices = window.speechSynthesis.getVoices() || [];
      const ru = voices.find(v => (v.lang || '').toLowerCase().startsWith('ru'));
      if (ru) u.voice = ru;
    };
    pickVoice();
    if (!u.voice) {
      window.speechSynthesis.onvoiceschanged = () => { pickVoice(); };
    }
  } catch (_) {}
  u.rate = 1.0;
  u.pitch = 1.0;
  u.onend = () => {
    if (!ttsActive) return;
    ttsIndex += 1;
    speakNextSpeechChunk();
  };
  u.onerror = () => {
    console.warn('[TTS] speech error at chunk', ttsIndex);
    ttsActive = false;
    setBusy(false);
    const b = document.getElementById('ttsBtn');
    if (b) {
      b.textContent = '🔊';
      const def = b.dataset.defaultTitle || 'Озвучка (прочитать страницу)';
      b.setAttribute('title', def);
      b.setAttribute('aria-label', 'Озвучка');
    }
  };
  try { window.speechSynthesis.cancel(); } catch (_) {}
  window.speechSynthesis.speak(u);
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
    if (data?.answer && !data?.streamed) {
      const cls = (data?.used_search ? 'exa' : 'local');
      pushMsg('assistant', data.answer, { className: cls });
    }
    // RAG debug (non-streaming)
    if (!data?.streamed && data?.debug && data.debug.rag) {
      const r = data.debug.rag;
      const info = `RAG: ${r?.enabled ? 'on' : 'off'}; upserted=${r?.upserted ?? 0}; retrieved=${r?.retrieved_count ?? 0}`;
      pushMsg('assistant', info, { className: 'local' });
    }
    // Render external sources when search was used (clickable)
    if (!data?.streamed && data?.used_search && Array.isArray(data?.sources) && data.sources.length) {
      try {
        const urls = data.sources
          .map(s => ({ url: s?.url, title: s?.title }))
          .filter(x => x && x.url && typeof x.url === 'string');
        if (urls.length) {
          const wrap = document.createElement('div');
          wrap.className = 'msg assistant exa';
          const meta = document.createElement('div');
          meta.className = 'meta';
          meta.textContent = 'Источники';
          const body = document.createElement('div');
          const list = document.createElement('div');
          urls.slice(0, 6).forEach(it => {
            const a = document.createElement('a');
            a.href = it.url;
            a.target = '_blank';
            a.rel = 'noopener noreferrer';
            a.textContent = (it.title && typeof it.title === 'string' ? it.title : it.url);
            const line = document.createElement('div');
            line.appendChild(a);
            list.appendChild(line);
          });
          body.appendChild(list);
          wrap.appendChild(meta);
          wrap.appendChild(body);
          chatEl.appendChild(wrap);
          chatEl.scrollTop = chatEl.scrollHeight;
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

// Remove copy chat button handler if exists (feature removed)
if (copyBtn) {
  if (copyBtn.parentElement) copyBtn.parentElement.removeChild(copyBtn);
}

// Bind header icon buttons
document.addEventListener('DOMContentLoaded', async () => {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    currentTabId = tab?.id;
    lastUrlInActiveTab = tab?.url;
  } catch (_) {}
  const exportBtn = document.getElementById('exportBtn');
  if (exportBtn) {
    exportBtn.addEventListener('click', async () => {
      const orig = exportBtn.textContent;
      exportBtn.disabled = true;
      try { await exportCurrentPageToMarkdown(); }
      finally {
        exportBtn.disabled = false;
      }
    });
  }
  const copyMdBtn = document.getElementById('copyMdBtn');
  if (copyMdBtn) {
    copyMdBtn.addEventListener('click', async () => {
      copyMdBtn.disabled = true;
      try { await copyCurrentPageMarkdownToClipboard(); }
      finally {
        copyMdBtn.disabled = false;
      }
    });
  }
  const ttsBtn = document.getElementById('ttsBtn');
  if (ttsBtn) {
    ttsBtn.addEventListener('click', async () => {
      try { await toggleSpeakCurrentPage(); } catch (_) {}
    });
  }

  const sberTtsBtn = document.getElementById('sberTtsBtn');
  if (sberTtsBtn) {
    sberTtsBtn.addEventListener('click', async () => {
      try {
        // Toggle: stop if currently playing
        if (sberAudio && !sberAudio.paused) {
          try { sberAudio.pause(); } catch (_) {}
          try { URL.revokeObjectURL(sberAudio.src); } catch (_) {}
          sberAudio = null;
          // restore tooltip
          sberTtsBtn.setAttribute('title', 'Озвучка (Sber)');
          sberTtsBtn.setAttribute('aria-label', 'Озвучка (Sber)');
          pushMsg('assistant', 'Озвучивание остановлено (Sber)', { className: 'local' });
          return;
        }
        await playSberTTS();
      } catch (e) {
        pushMsg('assistant', 'Ошибка Sber TTS: ' + (e?.message || String(e)));
      }
    });
  }

  const settingsBtn = document.getElementById('settingsBtn');
  const modal = document.getElementById('settingsModal');
  const body = document.getElementById('settingsBody');
  const btnCancel = document.getElementById('settingsCancel');
  const btnSave = document.getElementById('settingsSave');
  if (settingsBtn && modal && body && btnCancel && btnSave) {
    settingsBtn.addEventListener('click', async () => {
      try {
        const baseUrl = await getBackendBaseUrl();
        const resp = await fetch(baseUrl + '/config');
        const cfg = await resp.json();
        renderSettingsForm(body, cfg);
        modal.style.display = 'block';
      } catch (e) {
        // Render at least local connection settings
        try { renderSettingsForm(body, null); } catch (_) {}
        modal.style.display = 'block';
      }
    });
    btnCancel.addEventListener('click', () => { modal.style.display = 'none'; });
    btnSave.addEventListener('click', async () => {
      try {
        // Save local baseUrl first
        const localUrl = (document.getElementById('local_backendBaseUrl')?.value || '').trim().replace(/\/$/, '');
        if (localUrl) {
          await new Promise(resolve => chrome.storage.local.set({ backendBaseUrl: localUrl }, resolve));
        }
        const baseUrl = localUrl || (await getBackendBaseUrl());
        const payload = {};
        body.querySelectorAll('input[id^="cfg_"]').forEach(inp => {
          const key = inp.id.replace('cfg_', '');
          if (inp.type === 'checkbox') {
            payload[key] = inp.checked ? '1' : '0';
          } else {
            if (inp.value !== '') payload[key] = inp.value;
          }
        });
        if (Object.keys(payload).length) {
          const resp = await fetch(baseUrl + '/config', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
          if (!resp.ok) throw new Error('HTTP ' + resp.status);
        }
        modal.style.display = 'none';
        pushMsg('assistant', 'Параметры применены', { className: 'local' });
      } catch (e) {
        pushMsg('assistant', 'Ошибка применения настроек: ' + (e?.message || String(e)));
      }
    });
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



