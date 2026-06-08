// ── 晚风 · 应用入口 ──

// ── 注册 Service Worker（自修复版）──
if ("serviceWorker" in navigator) {
  async function initSW() {
    const reg = await navigator.serviceWorker.getRegistration();
    if (reg) {
      // 已有 SW — 强制检查更新
      await reg.update();
      // 如果不是最新版，等新 SW 激活后刷新
      if (reg.waiting) {
        reg.waiting.postMessage('skip-waiting');
        navigator.serviceWorker.addEventListener('controllerchange', () => {
          window.location.reload();
        });
      }
    }
    // 注册（或重新注册）
    navigator.serviceWorker.register('/sw.js?v=v12').catch(() => {});
    navigator.serviceWorker.addEventListener('controllerchange', () => {
      window.location.reload();
    });
  }
  initSW();
}

document.querySelectorAll('.nav-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    const view = tab.dataset.view;
    if (view === currentView) return;
    document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    currentView = view;
    const groupBar = document.getElementById('group-bar');
    if (view === 'discover') {
      listEl.classList.add('hidden');
      if (calView) calView.classList.add('hidden-view');
      searchWrap.style.display = 'none';
      if (groupBar) groupBar.style.display = 'none';
      headerBtns.style.display = 'none';
      discoverView.style.display = 'flex';
      loadDiscover();
    } else {
      listEl.classList.remove('hidden');
      if (calView) calView.classList.remove('hidden-view');
      searchWrap.style.display = '';
      if (groupBar) groupBar.style.display = '';
      headerBtns.style.display = '';
      discoverView.style.display = 'none';
      render(searchEl.value);
    }
  });
});

document.getElementById('btn-conn').addEventListener('click', promptConnection);
document.getElementById('btn-settings').addEventListener('click', promptSettings);

/* ── 新建笔记 ── */
document.getElementById('btn-add').addEventListener('click', () => openEditor());

/* ── 搜索 ── */
// collapsible search
const searchWrap = document.querySelector('.search-wrap');
document.getElementById('btn-search').addEventListener('click', () => {
  const open = searchWrap.classList.toggle('open');
  if (open) { searchEl.focus(); }
  else { searchEl.value = ''; render(); }
});
searchEl.addEventListener('input', () => render(searchEl.value));

/* ── 启动 ── */
applyBackground();
load();

// 窗口缩放时重排瀑布流（仅在晚风页生效）
let resizeTimer;
window.addEventListener('resize', () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => {
    if (currentView === 'discover') return;  // 拾光页不触发重排
    if (!showCalendar) render(searchEl.value);
  }, 200);
});
