// 晚风 · Service Worker
// 策略：API 完全不拦截；上传图片网络优先；静态资源缓存优先 + 后台更新

const CACHE_NAME = 'wanfeng-v17';

const PRECACHE = [
  './',
  'index.html',
  'manifest.json',
  'css/style.css?v=17',
  'js/utils.js?v=17',
  'js/api.js?v=17',
  'js/state.js?v=17',
  'js/sync.js?v=17',
  'js/notes.js?v=17',
  'js/calendar.js?v=17',
  'js/discover.js?v=17',
  'js/editor.js?v=17',
  'js/settings.js?v=17',
  'js/app.js?v=17',
  'icons/icon-192.png',
  'icons/icon-512.png',
  'icons/apple-touch-icon.png',
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache =>
      // 单个资源失败不影响整体安装（例如某个图标还没部署）
      Promise.all(PRECACHE.map(url => cache.add(url).catch(() => null)))
    )
  );
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('message', event => {
  if (event.data === 'skip-waiting') self.skipWaiting();
});

self.addEventListener('fetch', event => {
  const request = event.request;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // ── API 请求：完全不拦截 ──
  // 关键：不能 respondWith(fetch(event.request))，否则 iOS Safari
  // 会丢失 multipart/form-data 的 body，图片上传会 400 "no file"
  if (url.pathname.startsWith('/api/')) return;

  // ── 原始照片归档目录：不缓存，直连（服务端也已禁止公开访问）──
  if (url.pathname.startsWith('/uploads/originals/')) return;

  // ── 上传的图片：网络优先，离线时用缓存 ──
  if (url.pathname.startsWith('/uploads/')) {
    event.respondWith(
      fetch(request)
        .then(response => {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(request, clone));
          return response;
        })
        .catch(() => caches.match(request))
    );
    return;
  }

  // ── 页面导航：缓存优先 + 后台更新，断网也能打开 ──
  if (request.mode === 'navigate') {
    event.respondWith(
      caches.match(request).then(cached => {
        const network = fetch(request)
          .then(response => {
            const clone = response.clone();
            caches.open(CACHE_NAME).then(cache => cache.put(request, clone));
            return response;
          })
          .catch(() => cached || caches.match('index.html'));
        return cached || network;
      })
    );
    return;
  }

  // ── 其余静态资源：缓存优先 + 后台更新 ──
  event.respondWith(
    caches.match(request).then(cached => {
      const network = fetch(request)
        .then(response => {
          if (response && response.status === 200) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then(cache => cache.put(request, clone));
          }
          return response;
        })
        .catch(() => cached);
      return cached || network;
    })
  );
});
