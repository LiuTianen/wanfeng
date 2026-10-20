// ── 晚风 · 笔记数据 & 列表渲染 ──

async function load() {
  loadLocal();
  const key = getApiKey();
  if (!key) { updateStatus('local'); return; }

  if (notes.length === 0) renderSkeleton();
  updateStatus('syncing');
  try {
    const data = await apiFetch('/notes');
    notes = dropTombstoned(mergeNotes(data.notes || [], notes));
    saveLocal();
    animateNext = true;
    render();
    await syncPending();
    fetchGroups();
    fetchTags();
  } catch (e) {
    handleLoadError(e);
  }
}

function loadLocal() {
  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
    notes = Array.isArray(parsed) ? parsed.map(normNote) : [];
  } catch {
    notes = [];
  }
  notes = dropTombstoned(notes).sort(compareNotes);
  render();
  updateStatus(getApiKey() ? 'syncing' : 'local');
}

function handleLoadError(e) {
  if (e && e.status === 401) {
    updateStatus('unauth');
    toast('密钥无效，请重新连接');
    return;
  }
  updateStatus('offline');
  toast('离线模式：改动会先存在本地');
}

// 把本地 pending 的改动推给服务端；返回是否成功
async function syncPending() {
  if (!getApiKey()) { updateStatus('local'); return false; }
  if (!hasPending()) { updateStatus('online'); return true; }
  updateStatus('pending');
  try {
    const data = await flushQueue();
    render();
    updateStatus('online');
    if (data && data.skipped) toast(data.skipped + ' 条改动未能同步');
    return true;
  } catch (e) {
    if (e && e.status === 401) { updateStatus('unauth'); toast('密钥无效'); return false; }
    updateStatus('offline');
    toast('同步失败，已保存到本地');
    return false;
  }
}

function saveLocal() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(notes));
  } catch {
    toast('本地存储已满，请导出备份');
  }
}

async function fetchGroups() {
  if (!getApiKey()) return;
  try {
    const data = await apiFetch('/groups');
    groups = data.groups || [];
  } catch { /* 保留上一次的分组，不要闪空 */ }
  renderGroupBar();
}

async function fetchTags() {
  if (!getApiKey()) return;
  try {
    const data = await apiFetch('/tags');
    allTags = data.tags || [];
  } catch { /* 同上 */ }
  renderGroupBar();
}

function renderGroupBar() {
  const bar = document.getElementById('group-bar');
  if (!bar) return;
  const allCount = notes.length;
  const noGroupCount = notes.filter(n => !n.group).length;
  let html = `<span class="group-chip${!activeGroup && !activeTag ? ' active' : ''}" data-type="group" data-group="">全部 <span class="chip-count">${allCount}</span></span>`;
  if (noGroupCount > 0) html += `<span class="group-chip${activeGroup === '!' ? ' active' : ''}" data-type="group" data-group="!">未分组 <span class="chip-count">${noGroupCount}</span></span>`;
  for (const g of groups) html += `<span class="group-chip${activeGroup === g.name ? ' active' : ''}" data-type="group" data-group="${esc(g.name)}">${ICONS.folder}${esc(g.name)} <span class="chip-count">${g.count}</span></span>`;
  if (allTags.length > 0) {
    for (const t of allTags) html += `<span class="group-chip${activeTag === t.name ? ' active' : ''}" data-type="tag" data-tag="${esc(t.name)}">${ICONS.tag}${esc(t.name)} <span class="chip-count">${t.count}</span></span>`;
  }
  bar.innerHTML = html;
  bar.querySelectorAll('.group-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      if (chip.dataset.type === 'tag') { activeTag = chip.dataset.tag; activeGroup = ''; }
      else { activeGroup = chip.dataset.group; activeTag = ''; }
      renderGroupBar();
      render(searchEl.value);
    });
  });
}

async function pinNote(id) {
  if (!getApiKey()) { toast('请先连接服务器'); return null; }
  try {
    const res = await apiFetch('/notes/' + encodeURIComponent(id) + '/pin', { method: 'POST' });
    const n = notes.find(x => x.id === id);
    if (n) { n.pinned = true; n.pinned_ts = res.pinned_at ? Date.parse(res.pinned_at) || Date.now() : Date.now(); }
    notes.sort(compareNotes);
    saveLocal();
    render(searchEl.value);
    return res;
  } catch (e) {
    toast('置顶失败: ' + (e.message || e));
    return null;
  }
}

async function unpinNote(id) {
  if (!getApiKey()) { toast('请先连接服务器'); return null; }
  try {
    await apiFetch('/notes/' + encodeURIComponent(id) + '/unpin', { method: 'POST' });
    const n = notes.find(x => x.id === id);
    if (n) { n.pinned = false; n.pinned_ts = 0; }
    notes.sort(compareNotes);
    saveLocal();
    render(searchEl.value);
    return true;
  } catch (e) {
    toast('取消置顶失败: ' + (e.message || e));
    return null;
  }
}

function updateStatus(s) {
  if (s) connState = s;
  const el = document.getElementById('status-dot');
  if (!el) return;
  const titles = {
    online: '已连接服务器',
    syncing: '同步中…',
    offline: '离线：改动会先存在本地',
    local: '仅本地模式（未连接）',
    unauth: '密钥无效',
    pending: '有改动待同步',
  };
  el.className = 'status-dot ' + connState;
  el.title = titles[connState] || '';
}

function render(filter = '') {
  if (showCalendar) { renderCalendar(); return; }
  if (calView) calView.classList.remove('active');
  listEl.classList.remove('hidden');

  const q = (filter || '').trim().toLowerCase();
  let filtered = notes;
  if (activeGroup === '!') filtered = filtered.filter(n => !n.group);
  else if (activeGroup) filtered = filtered.filter(n => n.group === activeGroup);
  if (activeTag) filtered = filtered.filter(n => safeTags(n.tags).includes(activeTag));
  if (q) {
    filtered = filtered.filter(n =>
      (n.body || '').toLowerCase().includes(q) ||
      (n.title || '').toLowerCase().includes(q) ||
      safeTags(n.tags).some(t => t.toLowerCase().includes(q)));
  }
  filtered = filtered.slice().sort(compareNotes);

  renderGroupBar();
  if (countEl) countEl.textContent = notes.length + ' 篇';

  const animate = animateNext;
  animateNext = false;

  if (filtered.length === 0) {
    listEl.classList.remove('desktop-masonry');
    listEl.style.gap = '';
    if (notes.length === 0) {
      listEl.innerHTML = `<div class="empty-state">
        <div class="illustration">${ICONS.moon}</div>
        <div class="hint">万物藏于心</div>
        <div class="sub">还没有写下任何片段</div>
        <button class="empty-action" type="button">写下此刻</button>
      </div>`;
    } else {
      listEl.innerHTML = `<div class="empty-state">
        <div class="hint">没有找到匹配的笔记</div>
        <div class="sub">换个词，或者清空搜索</div>
      </div>`;
    }
    const action = listEl.querySelector('.empty-action');
    if (action) action.addEventListener('click', () => openEditor());
    return;
  }

  const isDesktop = window.innerWidth >= 600;
  const numCols = window.innerWidth >= 1400 ? 4 : window.innerWidth >= 900 ? 3 : 2;

  if (isDesktop) {
    const colGap = window.innerWidth >= 900 ? 16 : 14;
    const colWidth = (window.innerWidth - 64 - (numCols - 1) * colGap) / numCols;
    listEl.classList.add('desktop-masonry');
    listEl.style.gap = colGap + 'px';

    // 先按列宽渲染成一列，量出每张卡的真实高度，再分配到最短列
    listEl.innerHTML = `<div class="masonry-col" style="flex:none;width:${colWidth}px;gap:0">` +
      filtered.map((n, i) => buildCardHTML(n, i, animate)).join('') +
      '</div>';
    const cards = Array.from(listEl.querySelectorAll('.card'));
    const cols = Array.from({ length: numCols }, () => {
      const el = document.createElement('div');
      el.className = 'masonry-col';
      el.style.gap = colGap + 'px';
      return { el, height: 0 };
    });
    for (const card of cards) {
      let shortest = 0;
      for (let i = 1; i < numCols; i++) {
        if (cols[i].height < cols[shortest].height) shortest = i;
      }
      cols[shortest].height += card.getBoundingClientRect().height + colGap;
      cols[shortest].el.appendChild(card);
    }
    listEl.innerHTML = '';
    cols.forEach(col => listEl.appendChild(col.el));
  } else {
    listEl.classList.remove('desktop-masonry');
    listEl.style.gap = '';
    listEl.innerHTML = filtered.map((n, i) => buildCardHTML(n, i, animate)).join('');
  }

  bindCardEvents();
}

// 首屏骨架：本地没缓存、服务端还没回包时撑住版面
function renderSkeleton() {
  listEl.classList.remove('desktop-masonry');
  listEl.style.gap = '';
  listEl.innerHTML = Array.from({ length: 3 }, () => `
    <div class="skeleton-card">
      <div class="sk-line w40"></div>
      <div class="sk-line w90"></div>
      <div class="sk-line w70"></div>
      <div class="sk-line w40"></div>
    </div>`).join('');
}

function bindCardEvents() {
  listEl.querySelectorAll('.card').forEach(card => card.addEventListener('click', e => {
    if (e.target.closest('button') || e.target.closest('img')) return;
    const bodyEl = card.querySelector('.body');
    const hintEl = card.querySelector('.expand-hint');
    if (!bodyEl) return;
    if (bodyEl.classList.contains('expanded')) {
      bodyEl.classList.remove('expanded');
      if (hintEl) hintEl.textContent = '点击展开全文…';
    } else {
      bodyEl.classList.add('expanded');
      if (hintEl) hintEl.textContent = '收起';
    }
  }));
  listEl.querySelectorAll('.edit-btn').forEach(btn => btn.addEventListener('click', e => {
    e.stopPropagation();
    openEditor(btn.dataset.id);
  }));
  listEl.querySelectorAll('.del-btn').forEach(btn => btn.addEventListener('click', e => {
    e.stopPropagation();
    deleteNote(btn.dataset.id);
  }));
  listEl.querySelectorAll('.pin-btn').forEach(btn => btn.addEventListener('click', e => {
    e.stopPropagation();
    const n = notes.find(x => x.id === btn.dataset.id);
    if (!n) return;
    if (n.pinned) unpinNote(btn.dataset.id);
    else pinNote(btn.dataset.id);
  }));
  listEl.querySelectorAll('.expand-hint').forEach(hint => hint.addEventListener('click', e => {
    e.stopPropagation();
    const card = hint.closest('.card');
    if (!card) return;
    const bodyEl = card.querySelector('.body');
    if (!bodyEl) return;
    if (bodyEl.classList.contains('expanded')) {
      bodyEl.classList.remove('expanded');
      hint.textContent = '点击展开全文…';
    } else {
      bodyEl.classList.add('expanded');
      hint.textContent = '收起';
    }
  }));
  listEl.querySelectorAll('.card-images img').forEach(img => img.addEventListener('click', e => {
    e.stopPropagation();
    openLightbox(img.dataset.img);
  }));

  // 正文没超过 6 行就不截断、不显示「展开」；超过才露出提示
  listEl.querySelectorAll('.card').forEach(card => {
    const bodyEl = card.querySelector('.body');
    if (!bodyEl) return;
    const hint = card.querySelector('.expand-hint');
    const overflows = bodyEl.scrollHeight > bodyEl.clientHeight + 2;
    if (overflows) {
      if (hint) hint.hidden = false;
    } else {
      bodyEl.classList.add('short');
      if (hint) hint.hidden = true;
    }
  });
}

function fmtISO(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '';
  const pad = v => String(v).padStart(2, '0');
  return d.getFullYear() + '年' + (d.getMonth() + 1) + '月' + d.getDate() + '日 ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
}

function buildCardHTML(n, idx = 0, animate = false) {
  const id = esc(n.id);
  const date = new Date(n.created_ts || n.ts);
  const dateStr = isNaN(date.getTime()) ? '' : date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
  const body = n.body || '';
  const imgs = (n.images || []).map(safeImage).filter(Boolean);
  const imgHtml = imgs.length
    ? `<div class="card-images">${imgs.map(f => `<img src="/uploads/${esc(f)}" alt="" loading="lazy" data-img="${esc(f)}">`).join('')}</div>`
    : '';
  const bodyHTML = esc(body).replace(/\*(\S[^*\n]*\S|\S)\*/g, '<em>$1</em>');
  const tags = safeTags(n.tags);
  const createdFull = fmtISO(n.created_at);
  const updatedFull = n.updated_at && n.updated_at !== n.created_at ? fmtISO(n.updated_at) : '';
  return `<div class="card${n.pinned ? ' pinned' : ''}${animate ? ' anim' : ''}" data-id="${id}" style="--i:${Math.min(idx, 10)}">
      <div class="meta"><span class="time">${dateStr}${n.shared ? '<span class="shared-badge">公开</span>' : ''}${n.pending ? '<span class="pending-badge">待同步</span>' : ''}</span><span class="actions"><button class="pin-btn" data-id="${id}" type="button">${n.pinned ? '取消置顶' : '置顶'}</button><button class="edit-btn" data-id="${id}" type="button">编辑</button><button class="del-btn" data-id="${id}" type="button">删除</button></span></div>
      ${n.title ? '<div class="title">' + esc(n.title) + '</div>' : ''}
      <div class="body" data-id="${id}">${n.group ? '<span class="group-badge">' + esc(n.group) + '</span>' : ''}${bodyHTML}</div>
      ${tags.length ? '<div class="card-tags">' + tags.map(t => '<span class="card-tag">' + esc(t) + '</span>').join('') + '</div>' : ''}
      ${imgHtml}
      <div class="expand-hint" data-id="${id}" hidden>点击展开全文…</div>
      <div class="card-footer">${createdFull ? '创建于 ' + createdFull : ''}${updatedFull ? ' · 更新于 ' + updatedFull : ''}</div>
    </div>`;
}