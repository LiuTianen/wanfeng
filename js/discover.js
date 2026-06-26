// ── 晚风 · 发现页 ──

async function loadDiscover() {
  discoverList.innerHTML = '<div class="empty-state"><div class="icon">🕯️</div><div class="hint">沿着晚风…</div></div>';
  try {
    const headers = {};
    if (apiKey) headers['Authorization'] = 'Bearer ' + apiKey;
    const res = await fetch(API_BASE + '/discover', { headers });
    const data = await res.json();
    if (!data.notes || data.notes.length === 0) {
      discoverList.innerHTML = '<div class="empty-state"><div class="icon">🌙</div><div class="hint">光迹尚浅</div></div>';
      discoverFooter.textContent = '';
      return;
    }
    let html = '';
    for (const n of data.notes) {
      const date = new Date(n.ts);
      const timeStr = date.toLocaleDateString('zh-CN', { month:'long', day:'numeric' }) + ' ' + date.toLocaleTimeString('zh-CN', { hour:'2-digit', minute:'2-digit' });
      const bodyHTML = esc(n.body).replace(/\*(\S[^*\n]*\S|\S)\*/g, '<em>$1</em>');
      const imgs = n.images || [];
      const imgHtml = imgs.length ? '<div class="dc-images">' + imgs.map(f => '<img src="/uploads/' + esc(f) + '" alt="" loading="lazy" onclick="openLightbox(\'/uploads/' + esc(f) + '\')">').join('') + '</div>' : '';
      html += '<div class="discover-card">' +
        (n.pinned ? '<div style="font-size:11px;color:var(--accent);margin-bottom:6px">📌 置顶</div>' : '') +
        (n.title ? '<div class="dc-title">' + esc(n.title) + '</div>' : '') +
        '<div class="dc-body">' + bodyHTML + '</div>' +
        (n.tags && n.tags.length ? '<div class="card-tags" style="margin-top:8px">' + n.tags.map(t => '<span class="card-tag">' + esc(t) + '</span>').join('') + '</div>' : '') +
        imgHtml +
        '<div class="dc-meta"><span>' + timeStr + '</span>' + (n.group ? '<span class="dc-group">' + esc(n.group) + '</span>' : '') + '</div>' +
        '</div>';
    }
    discoverList.innerHTML = html;
    discoverFooter.textContent = data.authenticated ? '已连接 · 听见晚风' : (data.has_more ? '连接后，听见更远的风' : '未连接 · 只拾得近处的光');
  } catch (e) {
    discoverList.innerHTML = '<div class="empty-state"><div class="icon">💫</div><div class="hint">风暂歇…</div></div>';
    discoverFooter.textContent = '';
  }
}
