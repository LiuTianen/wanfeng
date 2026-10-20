// ── 晚风 · 发现页（拾光）──

async function loadDiscover() {
  discoverList.innerHTML = '<div class="empty-state"><div class="icon">🕯️</div><div class="hint">沿着晚风…</div></div>';
  try {
    const headers = {};
    const key = getApiKey();
    if (key) headers['Authorization'] = 'Bearer ' + key;
    const res = await fetch(API_BASE + '/discover?_t=' + Date.now(), { headers });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const data = await res.json();
    const items = Array.isArray(data.notes) ? data.notes : [];
    if (items.length === 0) {
      discoverList.innerHTML = '<div class="empty-state"><div class="icon">🌙</div><div class="hint">光迹尚浅</div></div>';
      discoverFooter.textContent = '';
      return;
    }

    discoverList.innerHTML = items.map(n => {
      const date = new Date(n.created_ts || n.ts);
      const timeStr = isNaN(date.getTime()) ? '' :
        date.toLocaleDateString('zh-CN', { month: 'long', day: 'numeric' }) + ' ' +
        date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
      const bodyHTML = esc(n.body).replace(/\*(\S[^*\n]*\S|\S)\*/g, '<em>$1</em>');
      const imgs = (Array.isArray(n.images) ? n.images : []).map(safeImage).filter(Boolean);
      const imgHtml = imgs.length
        ? '<div class="dc-images">' + imgs.map(f =>
            `<img src="/uploads/${esc(f)}" alt="" loading="lazy" data-img="${esc(f)}">`).join('') + '</div>'
        : '';
      const tags = safeTags(n.tags);
      return '<div class="discover-card">' +
        (n.pinned ? '<div style="font-size:11px;color:var(--accent);margin-bottom:6px">📌 置顶</div>' : '') +
        (n.title ? '<div class="dc-title">' + esc(n.title) + '</div>' : '') +
        '<div class="dc-body">' + bodyHTML + '</div>' +
        (tags.length ? '<div class="card-tags" style="margin-top:8px">' +
          tags.map(t => '<span class="card-tag">' + esc(t) + '</span>').join('') + '</div>' : '') +
        imgHtml +
        '<div class="dc-meta"><span>' + esc(timeStr) + '</span>' +
        (n.group ? '<span class="dc-group">' + esc(n.group) + '</span>' : '') + '</div>' +
        '</div>';
    }).join('');

    // 事件委托 + data 属性，替换掉原来的内联 onclick 字符串拼接
    discoverList.querySelectorAll('.dc-images img').forEach(img => {
      img.addEventListener('click', () => openLightbox(img.dataset.img));
    });
    discoverFooter.textContent = (data.authenticated ? '已连接 · 听见晚风 · ' : '拾光 · ') + items.length + ' 则';
  } catch (e) {
    console.error('discover failed:', e);
    discoverList.innerHTML = '<div class="empty-state"><div class="icon">💫</div><div class="hint">风暂歇…</div></div>';
    discoverFooter.textContent = '';
  }
}
