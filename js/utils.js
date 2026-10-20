// ── 晚风 · 工具函数 ──

const STORAGE_KEY = 'wanfeng_notes';
const API_KEY_STORAGE = 'wanfeng_apikey';
const TOMBSTONE_KEY = 'wanfeng_deleted';
const API_BASE = '/api';
const APP_VERSION = '17';

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
