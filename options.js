'use strict';

document.addEventListener('DOMContentLoaded', () => {
  const input = document.getElementById('backendBaseUrl');
  const saveBtn = document.getElementById('saveBtn');
  const statusEl = document.getElementById('status');

  // Load current value
  chrome.storage.local.get({ backendBaseUrl: 'http://127.0.0.1:8010' }, (res) => {
    if (input) input.value = (res.backendBaseUrl || '').replace(/\/$/, '');
  });

  saveBtn?.addEventListener('click', () => {
    const raw = (input?.value || '').trim();
    const val = (raw || input?.placeholder || 'http://127.0.0.1:8010').replace(/\/$/, '');
    chrome.storage.local.set({ backendBaseUrl: val }, () => {
      if (statusEl) {
        statusEl.textContent = 'Сохранено';
        setTimeout(() => { statusEl.textContent = ''; }, 1200);
      }
    });
  });
});



