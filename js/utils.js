// ── 晚风 · 工具函数 ──

const STORAGE_KEY = 'wanfeng_notes';
const API_KEY_STORAGE = 'wanfeng_apikey';
const API_BASE = '/api';

function safeTags(t) {
  if (Array.isArray(t)) return t;
  if (typeof t === 'string') { try { const p = JSON.parse(t); if (Array.isArray(p)) return p; } catch {} }
  return [];
}

function openLightbox(src) {
  const lb = document.createElement('div');
  lb.className = 'lightbox';
  lb.innerHTML = `<img src="${src}">`;
  lb.addEventListener('click', () => lb.remove());
  document.body.appendChild(lb);
}

function esc(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function toast(msg) { const t = document.createElement('div'); t.className = 'toast'; t.textContent = msg; document.body.appendChild(t); setTimeout(() => t.remove(), 2000); }

function genId() { return 'n_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 8); }
