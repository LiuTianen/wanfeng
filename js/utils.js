// ── 晚风 · 工具函数 ──

const STORAGE_KEY = 'wanfeng_notes';
const API_KEY_STORAGE = 'wanfeng_apikey';
const TOMBSTONE_KEY = 'wanfeng_deleted';
const THEME_KEY = 'wanfeng_theme';
const API_BASE = '/api';
const APP_VERSION = '18';

// 分组栏用到的小图标（避免 emoji 在不同系统里粗细不一）
const ICONS = {
  folder: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3.5 7.5A1.5 1.5 0 0 1 5 6h3.6l1.8 2.2H19a1.5 1.5 0 0 1 1.5 1.5v8.8A1.5 1.5 0 0 1 19 20H5a1.5 1.5 0 0 1-1.5-1.5z"/></svg>',
  tag: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 4h6.6a2 2 0 0 1 1.4.6l7.4 7.4a2 2 0 0 1 0 2.8l-4.6 4.6a2 2 0 0 1-2.8 0L4.6 12A2 2 0 0 1 4 10.6z"/><circle cx="8.4" cy="8.4" r="1.3"/></svg>',
  moon: '<svg viewBox="0 0 96 96" aria-hidden="true"><path d="M62 20a30 30 0 1 0 14 44 24 24 0 0 1-14-44z"/><path d="M22 34h10M17 48h8M24 62h9"/><circle cx="70" cy="30" r="1.4"/><circle cx="78" cy="44" r="1"/></svg>',
  image: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3.5" y="4.5" width="17" height="15" rx="2.5"/><circle cx="9" cy="10" r="1.6"/><path d="m4.5 17 4.6-4.6a1.4 1.4 0 0 1 2 0l3.2 3.2 2-2a1.4 1.4 0 0 1 2 0L20 15"/></svg>',
};

// ── 外观 ──
function getThemeMode() {
  try { return localStorage.getItem(THEME_KEY) || 'system'; } catch { return 'system'; }
}

function resolvedTheme(mode) {
  if (mode === 'light' || mode === 'dark') return mode;
  return window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
}

function applyTheme(mode) {
  const m = mode || getThemeMode();
  const resolved = resolvedTheme(m);
  const root = document.documentElement;
  if (m === 'system') root.removeAttribute('data-theme');
  else root.setAttribute('data-theme', m);
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute('content', resolved === 'light' ? '#faf7f0' : '#1a1a1a');
  if (typeof applyBackground === 'function') applyBackground();
  return resolved;
}

function setThemeMode(mode) {
  try { localStorage.setItem(THEME_KEY, mode); } catch { /* 存不进去也不影响本次生效 */ }
  applyTheme(mode);
}

// 完整的 HTML 转义：漏掉引号就等于给属性注入留门
function esc(value) {
  if (value === null || value === undefined) return '';
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function safeTags(t) {
  let raw = [];
  if (Array.isArray(t)) raw = t;
  else if (typeof t === 'string') {
    try {
      const parsed = JSON.parse(t);
      if (Array.isArray(parsed)) raw = parsed;
    } catch { /* 旧数据可能不是 JSON，忽略 */ }
  }
  const out = [];
  for (const item of raw) {
    if (typeof item === 'string' && item && !out.includes(item)) out.push(item);
  }
  return out;
}

// 只接受服务端生成的图片名，避免把任意字符串拼进 src
const IMAGE_NAME_RE = /^[A-Za-z0-9_.-]{1,80}\.(png|jpe?g|gif|webp|bmp|svg)$/i;
function safeImage(name) {
  return typeof name === 'string' && IMAGE_NAME_RE.test(name) ? name : '';
}

function openLightbox(src) {
  const safe = safeImage(String(src || '').replace(/^\/uploads\//, ''));
  if (!safe) return;
  const lb = document.createElement('div');
  lb.className = 'lightbox';
  const img = document.createElement('img');
  img.src = '/uploads/' + safe;
  img.alt = '';
  lb.appendChild(img);
  const close = () => {
    lb.remove();
    document.removeEventListener('keydown', onKey);
  };
  const onKey = e => { if (e.key === 'Escape') close(); };
  lb.addEventListener('click', close);
  document.addEventListener('keydown', onKey);
  document.body.appendChild(lb);
}

function toast(msg) {
  const t = document.createElement('div');
  t.className = 'toast';
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 2000);
}

function genId() {
  return 'n_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 8);
}
