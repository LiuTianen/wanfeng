// 晚风 · 主题预置（必须在样式表之前同步执行）
// 只做一件事：把上次选择的外观写到 <html data-theme>，避免暗色页面闪白。
(function () {
  try {
    var mode = localStorage.getItem('wanfeng_theme') || 'system';
    if (mode === 'light' || mode === 'dark') {
      document.documentElement.setAttribute('data-theme', mode);
    }
  } catch (e) {
    /* 隐私模式下 localStorage 会抛异常，忽略即可 */
  }
})();
