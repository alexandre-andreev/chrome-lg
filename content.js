'use strict';

function safeText(node) {
	try {
		return (node && node.innerText ? node.innerText : '').trim();
	} catch (_) { return ''; }
}

function firstContent(selector) {
	try {
		const el = document.querySelector(selector);
		return (el && el.content) ? String(el.content).trim() : '';
	} catch (_) { return ''; }
}

function parseJsonLdProducts() {
	const products = [];
	try {
		const scripts = Array.from(document.querySelectorAll('script[type="application/ld+json"]'));
		for (const s of scripts) {
			let txt = s && s.textContent ? s.textContent.trim() : '';
			if (!txt) continue;
			try {
				const data = JSON.parse(txt);
				const items = Array.isArray(data) ? data : [data];
				for (const it of items) {
					const type = Array.isArray(it['@type']) ? it['@type'] : [it['@type']];
					if (type && type.some(t => String(t).toLowerCase().includes('product'))) {
						products.push(it);
					}
				}
			} catch (_) { /* ignore bad JSON */ }
		}
	} catch (_) { /* ignore */ }
	return products;
}

function collectPageContext() {
	try {
		const url = location.href || '';
		const title = document.title || '';
		const ogTitle = firstContent('meta[property="og:title"]') || firstContent('meta[name="twitter:title"]');
		const ogDesc = firstContent('meta[property="og:description"]') || firstContent('meta[name="description"]') || firstContent('meta[name="twitter:description"]');

		// Prefer main/article/product containers for page text
		let mainEl = document.querySelector('main,[role="main"],article,.product-page,.product,.product-card,.product-item');
		let mainText = safeText(mainEl);
		if (!mainText) {
			// fallback to body but trimmed
			mainText = safeText(document.body);
		}
		mainText = (mainText || '').slice(0, 30000);

		// Extract product data from JSON-LD if present
		const products = parseJsonLdProducts();
		let productLine = '';
		let priceLine = '';
		let brandLine = '';
		if (products.length) {
			const p = products[0];
			const name = (p.name || '').toString().trim();
			const brand = (typeof p.brand === 'string' ? p.brand : (p.brand && p.brand.name)) || '';
			const offers = Array.isArray(p.offers) ? p.offers[0] : p.offers;
			const price = offers && (offers.price || offers.lowPrice || offers.highPrice);
			const currency = offers && (offers.priceCurrency || offers.priceCurrencyCode);
			if (name) productLine = `PRODUCT: ${name}`;
			if (brand) brandLine = `BRAND: ${brand}`;
			if (price) priceLine = `PRICE: ${price}${currency ? ' ' + currency : ''}`;
		}

		const pieces = [];
		if (ogTitle) pieces.push(`TITLE: ${ogTitle}`); else if (title) pieces.push(`TITLE: ${title}`);
		if (brandLine) pieces.push(brandLine);
		if (productLine) pieces.push(productLine);
		if (priceLine) pieces.push(priceLine);
		if (ogDesc) pieces.push(`SUMMARY: ${ogDesc}`);
		if (mainText) pieces.push(`PAGE: ${mainText}`);
		const text = pieces.join('\n');

		return { text, title: ogTitle || title, url };
	} catch (_) {
		return { text: '', title: document.title || '', url: location.href || '' };
	}
}

function sendMessageSafe(message, attempt) {
    const tries = typeof attempt === 'number' ? attempt : 0;
    try {
        chrome.runtime.sendMessage(message, () => {
            const err = chrome.runtime && chrome.runtime.lastError ? chrome.runtime.lastError : null;
            if (err && /context invalidated|Receiving end does not exist/i.test(String(err.message || ''))) {
                if (tries < 3) setTimeout(() => sendMessageSafe(message, tries + 1), 500 * (tries + 1));
            }
        });
    } catch (_) {
        if (tries < 3) setTimeout(() => sendMessageSafe(message, tries + 1), 500 * (tries + 1));
    }
}

function sendContext() {
    const ctx = collectPageContext();
    sendMessageSafe({ type: 'PAGE_CONTEXT', ...ctx });
}

// Initial send
sendContext();

// Re-send when URL changes (SPA and history API)
let lastHref = location.href;
const notifyIfChanged = () => {
	const href = location.href;
	if (href !== lastHref) {
		lastHref = href;
		sendContext();
	}
};

const observer = new MutationObserver(notifyIfChanged);
observer.observe(document, { subtree: true, childList: true });

const wrap = (fnName) => {
	const orig = history[fnName];
	if (typeof orig === 'function') {
		history[fnName] = function() {
			const ret = orig.apply(this, arguments);
			setTimeout(notifyIfChanged, 0);
			return ret;
		};
	}
};

wrap('pushState');
wrap('replaceState');
window.addEventListener('popstate', notifyIfChanged);

document.addEventListener('visibilitychange', () => {
	if (!document.hidden) sendContext();
});

// Respond to on-demand context requests from side panel
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg && msg.type === 'REQUEST_CONTEXT') {
		const ctx = collectPageContext();
		// Also push to background cache
        sendMessageSafe({ type: 'PAGE_CONTEXT', ...ctx });
		try { sendResponse(ctx); } catch (_) {}
		return true;
	}
});


