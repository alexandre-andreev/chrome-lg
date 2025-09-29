'use strict';

chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.get({ backendBaseUrl: 'http://localhost:8000' }, (res) => {
    if (!res.backendBaseUrl) {
      chrome.storage.local.set({ backendBaseUrl: 'http://localhost:8000' });
    }
  });
});

chrome.action.onClicked.addListener(async (tab) => {
  if (!tab?.id) return;
  try {
    await chrome.sidePanel.open({ windowId: tab.windowId });
    await chrome.sidePanel.setOptions({
      tabId: tab.id,
      path: 'sidepanel.html',
      enabled: true,
    });
  } catch (e) {
    console.error('Side panel open error', e);
  }
});

// Keep side panel enabled when switching tabs or updating URLs
chrome.tabs.onActivated.addListener(async ({ tabId, windowId }) => {
  try {
    await chrome.sidePanel.open({ windowId });
    await chrome.sidePanel.setOptions({ tabId, path: 'sidepanel.html', enabled: true });
  } catch (_) {}
});

chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  if (changeInfo.status === 'complete') {
    try {
      if (tab.windowId != null) {
        await chrome.sidePanel.open({ windowId: tab.windowId });
      }
      await chrome.sidePanel.setOptions({ tabId, path: 'sidepanel.html', enabled: true });
    } catch (_) {}
  }
});

// Relay latest page context from content script to storage
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg && msg.type === 'PAGE_CONTEXT' && sender.tab?.id) {
    const ctx = {
      tabId: sender.tab.id,
      url: msg.url || sender.tab.url || null,
      title: msg.title || sender.tab.title || null,
      text: msg.text || '',
      ts: Date.now()
    };
    chrome.storage.local.get({ pageContextByTabId: {} }, (res) => {
      const map = res.pageContextByTabId || {};
      map[String(sender.tab.id)] = ctx;
      chrome.storage.local.set({ pageContextByTabId: map, lastPageContext: ctx });
    });
  }
});

// Cleanup cache when tabs close
chrome.tabs.onRemoved.addListener((tabId) => {
  chrome.storage.local.get({ pageContextByTabId: {} }, (res) => {
    const map = res.pageContextByTabId || {};
    if (map[String(tabId)]) {
      delete map[String(tabId)];
      chrome.storage.local.set({ pageContextByTabId: map });
    }
  });
});


