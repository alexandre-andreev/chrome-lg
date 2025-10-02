'use strict';

function safeText(node) {
	try {
		if (!node) return '';
		// Try innerText first (formatted), fallback to textContent (raw)
		let text = node.innerText || node.textContent || '';
		return text.trim();
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

function extractAttrPairsFromDom(root) {
    const pairs = [];
    try {
        // dl/dt/dd
        const dls = Array.from(root.querySelectorAll('dl'));
        for (const dl of dls) {
            const dts = Array.from(dl.querySelectorAll('dt'));
            for (const dt of dts) {
                const dd = dt.nextElementSibling && dt.nextElementSibling.tagName && dt.nextElementSibling.tagName.toLowerCase() === 'dd' ? dt.nextElementSibling : null;
                if (!dd) continue;
                const k = safeText(dt);
                const v = safeText(dd);
                if (k && v) pairs.push([k, v]);
            }
        }
        // tables
        const rows = Array.from(root.querySelectorAll('table tr'));
        for (const tr of rows) {
            const tds = Array.from(tr.querySelectorAll('td,th'));
            if (tds.length >= 2) {
                const k = safeText(tds[0]);
                const v = safeText(tds[1]);
                if (k && v) pairs.push([k, v]);
            }
        }
        // common list-based specs
        const lis = Array.from(root.querySelectorAll('.specs li, .characteristics li, .params li, .product-params li'));
        for (const li of lis) {
            let k = '';
            let v = '';
            const b = li.querySelector('b, strong, .key, .label');
            if (b) {
                k = safeText(b);
                v = safeText(li).replace(k, '').trim().replace(/^[:\-\s]+/, '');
            } else {
                const txt = safeText(li);
                const m = txt.match(/^([^:]+):\s*(.+)$/);
                if (m) { k = m[1].trim(); v = m[2].trim(); }
            }
            if (k && v) pairs.push([k, v]);
        }
    } catch (_) {}
    return pairs;
}

function normalizeAttrKey(k) {
    const key = (k || '').toLowerCase();
    if (/(материал|material)/.test(key)) return 'MATERIAL';
    if (/(состав)/.test(key)) return 'COMPOSITION';
    if (/(цвет|color)/.test(key)) return 'COLOR';
    if (/(размер|size)/.test(key)) return 'SIZE';
    if (/(страна|country)/.test(key)) return 'COUNTRY';
    if (/(производител|brand|бренд)/.test(key)) return 'BRAND';
    if (/(модель|model)/.test(key)) return 'MODEL';
    if (/(артикул|sku|код товара)/.test(key)) return 'SKU';
    if (/(категор|category)/.test(key)) return 'CATEGORY';
    return '';
}

function collectPageContext() {
	try {
		const url = location.href || '';
		const title = document.title || '';
		const ogTitle = firstContent('meta[property="og:title"]') || firstContent('meta[name="twitter:title"]');
		const ogDesc = firstContent('meta[property="og:description"]') || firstContent('meta[name="description"]') || firstContent('meta[name="twitter:description"]');

		// Prefer main/article/product containers for page text
		// Add site-specific selectors for various content sites
        let mainEl = document.querySelector(
			// Common HTML5
			'main,[role="main"],article,[role="article"],' +
			// Blog platforms
			'.article__content,.tm-article-body,.post__text,' + // Habr
			'.post-content,.entry-content,.content,' + // Medium, WordPress
			// Documentation & Atlassian
			'.wiki-content,.article-content,.page-content,' + // Confluence
			'[data-testid="page-content"],.ak-renderer-document,' + // Atlassian
			// E-commerce
			'.product-page,.product,.product-card,.product-item'
		);
        let mainText = safeText(mainEl);
        
        // Debug: log what selector matched
        if (mainEl) {
			console.log('[Chrome-bot] Main content selector matched:', mainEl.className || mainEl.tagName);
        }
        
        if (!mainText) {
			// Try article body directly
			const article = document.querySelector('article');
			if (article) {
				mainText = safeText(article);
				console.log('[Chrome-bot] Fallback to <article>, length:', mainText.length);
			}
        }
        
        if (!mainText || mainText.length < 200) {
			// Try removing scripts, styles, nav, footer first
			const clone = document.body.cloneNode(true);
			const remove = clone.querySelectorAll('script,style,nav,header,footer,[role="navigation"],[role="banner"]');
			remove.forEach(el => el.remove());
			mainText = safeText(clone);
			console.log('[Chrome-bot] Fallback to cleaned body, length:', mainText.length);
        }
        
        if (!mainText || mainText.length < 100) {
            // Last resort: full document
            mainText = safeText(document.documentElement);
            console.log('[Chrome-bot] Last resort: documentElement, length:', mainText.length);
        }
        
		// Clean up text: remove excessive whitespace, DIAG markers, etc.
		mainText = (mainText || '')
			.replace(/DIAG[\s\S]*?(?=\n|$)/g, '') // Remove DIAG lines
			.replace(/\n{3,}/g, '\n\n') // Max 2 newlines
			.replace(/[ \t]{2,}/g, ' ') // Collapse spaces
			.trim()
			.slice(0, 30000);
		
		console.log('[Chrome-bot] Final text length:', mainText.length);
		
		// Warn if text is suspiciously short
		if (mainText.length < 200) {
			console.warn('[Chrome-bot] WARNING: Very short text extracted:', mainText.length, 'chars');
			console.warn('[Chrome-bot] URL:', url);
			console.warn('[Chrome-bot] Sample:', mainText.slice(0, 100));
		}

        // Extract product data from JSON-LD if present
		const products = parseJsonLdProducts();
		let productLine = '';
		let priceLine = '';
		let brandLine = '';
        let materialLine = '';
        let colorLine = '';
        let sizeLine = '';
        let compositionLine = '';
		if (products.length) {
			const p = products[0];
			const name = (p.name || '').toString().trim();
			const brand = (typeof p.brand === 'string' ? p.brand : (p.brand && p.brand.name)) || '';
			const offers = Array.isArray(p.offers) ? p.offers[0] : p.offers;
			const price = offers && (offers.price || offers.lowPrice || offers.highPrice);
			const currency = offers && (offers.priceCurrency || offers.priceCurrencyCode);
            const material = (p.material || '').toString().trim();
            const color = (p.color || '').toString().trim();
            if (material) materialLine = `MATERIAL: ${material}`;
            if (color) colorLine = `COLOR: ${color}`;
			if (name) productLine = `PRODUCT: ${name}`;
			if (brand) brandLine = `BRAND: ${brand}`;
			if (price) priceLine = `PRICE: ${price}${currency ? ' ' + currency : ''}`;
		}

		const pieces = [];
		if (ogTitle) pieces.push(`TITLE: ${ogTitle}`); else if (title) pieces.push(`TITLE: ${title}`);
		if (brandLine) pieces.push(brandLine);
		if (productLine) pieces.push(productLine);
		if (priceLine) pieces.push(priceLine);
        if (materialLine) pieces.push(materialLine);
        if (colorLine) pieces.push(colorLine);
        if (sizeLine) pieces.push(sizeLine);
        if (compositionLine) pieces.push(compositionLine);
        // Extract attributes from DOM
        const attrs = extractAttrPairsFromDom(document);
        const seen = new Set();
        for (const [k, v] of attrs) {
            const NK = normalizeAttrKey(k);
            if (!NK) continue;
            const key = `${NK}: ${v}`;
            if (seen.has(key)) continue;
            seen.add(key);
            pieces.push(`${NK}: ${v}`);
        }
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
    console.log('[content.js] sendContext: text_len=', ctx.text?.length || 0, 'url=', ctx.url);
    sendMessageSafe({ type: 'PAGE_CONTEXT', ...ctx });
}

// Initial send with slight delay to allow dynamic content load
setTimeout(sendContext, 500);

// Re-send after 1.5s for slow-loading SPA content (Habr, Medium, etc.)
setTimeout(sendContext, 1500);

// Re-send when URL changes (SPA and history API)
let lastHref = location.href;
const notifyIfChanged = () => {
	const href = location.href;
	if (href !== lastHref) {
		lastHref = href;
        setTimeout(sendContext, 300);
        setTimeout(sendContext, 1500); // Also resend after delay for SPA
	}
};

let mainContentSent = false;
const observer = new MutationObserver(() => {
    // If main content appears later, resend context (but only once)
    if (mainContentSent) return;
    const mainEl = document.querySelector(
		'main,[role="main"],article,' +
		'.article__content,.tm-article-body,.post__text,' +
		'.post-content,.entry-content,.content,' +
		'.product-page,.product,.product-card,.product-item'
	);
    if (mainEl && safeText(mainEl)) {
        mainContentSent = true;
        setTimeout(sendContext, 300);
    }
});
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


