// ── 晚风 · 笔记数据 & 列表渲染 ──

async function load() {
  try { notes = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]'); notes.sort((a,b) => b.ts - a.ts); } catch { notes = []; }
  render();
  updateStatus('local');
  const key = getApiKey(); if (!key) { updateStatus('local'); return; }
  updateStatus(); // 显示连接中（无参数 = local 样式）
  try {
    const data = await apiFetch('/notes');
    notes = mergeNotes(data.notes || [], notes);
    saveLocal(); render(); updateStatus('online'); fetchGroups(); fetchTags();
  } catch (e) {
    console.error('load failed:', e.message || e);
    if (e.message === 'unauthorized') { updateStatus('unauth'); toast('密钥无效'); return; }
    toast('连接失败: ' + (e.message || e));
    // SW 缓存可能返回旧错误 — 3秒后重试一次
    setTimeout(async () => {
      try {
        const data = await apiFetch('/notes');
        notes = mergeNotes(data.notes || [], notes);
        saveLocal(); render(); updateStatus('online'); fetchGroups(); fetchTags();
        toast('已连接');
      } catch (e2) {
        console.error('retry failed:', e2.message || e2);
        updateStatus('offline');
        toast('重试失败: ' + (e2.message || e2));
      }
    }, 3000);
    updateStatus('offline');
  }
}
function mergeNotes(serverNotes, localNotes) {
  const map = new Map();
  for (const n of localNotes) map.set(n.id, n);
  for (const n of serverNotes) {
    const localNote = map.get(n.id);
    map.set(n.id, {
      id: n.id, body: n.body, title: n.title || '', group: n.group || '', tags: safeTags(n.tags), shared: n.shared || false,
      images: (n.images && n.images.length) ? n.images : (localNote ? (localNote.images || []) : []), ts: n.ts || Date.now(),
      created_ts: n.created_ts || n.ts || Date.now(), updated_at: n.updated_at, pinned: n.pinned || false, pinned_at: n.pinned_at || null
    });
  }
  return Array.from(map.values()).sort((a, b) => (b.created_ts || b.ts) - (a.created_ts || a.ts));
}
function saveLocal() { localStorage.setItem(STORAGE_KEY, JSON.stringify(notes)); }
async function fetchGroups() {
  try { const data = await apiFetch('/groups'); groups = data.groups || []; } catch { groups = []; }
  renderGroupBar();
}
async function fetchTags() {
  try { const data = await apiFetch('/tags'); allTags = data.tags || []; } catch { allTags = []; }
  renderGroupBar();
}
function renderGroupBar() {
  const bar = document.getElementById('group-bar');
  const allCount = notes.length;
  const noGroupCount = notes.filter(n => !n.group).length;
  let html = `<span class="group-chip${!activeGroup && !activeTag ? ' active' : ''}" data-type="group" data-group="">全部 <span style="color:var(--text-muted)">${allCount}</span></span>`;
  if (noGroupCount > 0) html += `<span class="group-chip${activeGroup === '!' ? ' active' : ''}" data-type="group" data-group="!">未分组 <span style="color:var(--text-muted)">${noGroupCount}</span></span>`;
  for (const g of groups) html += `<span class="group-chip${activeGroup === g.name ? ' active' : ''}" data-type="group" data-group="${esc(g.name)}">📁 ${esc(g.name)} <span style="color:var(--text-muted)">${g.count}</span></span>`;
  if (allTags.length > 0) {
    html += '<span style="color:var(--border);margin:0 2px;font-size:12px;line-height:28px">│</span>';
    for (const t of allTags) html += `<span class="group-chip${activeTag === t.name ? ' active' : ''}" data-type="tag" data-tag="${esc(t.name)}">🏷 ${esc(t.name)} <span style="color:var(--text-muted)">${t.count}</span></span>`;
  }
  bar.innerHTML = html;
  bar.querySelectorAll('.group-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      if (chip.dataset.type === 'tag') { activeTag = chip.dataset.tag; activeGroup = ''; }
      else { activeGroup = chip.dataset.group; activeTag = ''; }
      renderGroupBar(); render(searchEl.value);
    });
  });
}
async function saveToServer(note) {
  if (!getApiKey()) return null;
  try { return await apiFetch('/notes', { method: 'POST', body: JSON.stringify({ id: note.id, body: note.body, title: note.title || '', group: note.group || '', tags: safeTags(note.tags), images: note.images || [], shared: note.shared || false }) }); } catch { return null; }
}
async function updateOnServer(note) {
  if (!getApiKey()) return null;
  try { return await apiFetch('/notes/' + note.id, { method: 'PUT', body: JSON.stringify({ body: note.body, title: note.title || '', group: note.group || '', tags: safeTags(note.tags), images: note.images || [], shared: note.shared || false }) }); } catch { return null; }
}
async function deleteOnServer(id) {
  if (!getApiKey()) return null;
  try { return await apiFetch('/notes/' + id, { method: 'DELETE' }); } catch { return null; }
}
async function pinNote(id) {
  if (!getApiKey()) return null;
  try {
    const res = await apiFetch('/notes/' + id + '/pin', { method: 'POST' });
    const n = notes.find(n => n.id === id);
    if (n) { n.pinned = true; n.pinned_at = res.pinned_at; }
    saveLocal(); render(searchEl.value);
    return res;
  } catch (e) { toast('置顶失败: ' + (e.message || e)); return null; }
}
async function unpinNote(id) {
  if (!getApiKey()) return null;
  try {
    await apiFetch('/notes/' + id + '/unpin', { method: 'POST' });
    const n = notes.find(n => n.id === id);
    if (n) { n.pinned = false; n.pinned_at = null; }
    saveLocal(); render(searchEl.value);
    return true;
  } catch (e) { toast('取消置顶失败: ' + (e.message || e)); return null; }
}
function updateStatus(s) {
  const el = document.getElementById('status-dot');
  if (!el) return;
  el.className = 'status-dot ' + (s || 'local');
  el.title = { online: '已连接服务器', offline: '离线', local: '本地模式', unauth: '未配置密钥' }[s || 'local'] || '';
}
function render(filter = '') {
  if (showCalendar) { renderCalendar(); return; }
  calView.classList.remove('active');
  listEl.classList.remove('hidden');

  const q = filter.trim().toLowerCase();
  let filtered = notes;
  if (activeGroup === '!') filtered = filtered.filter(n => !n.group);
  else if (activeGroup) filtered = filtered.filter(n => n.group === activeGroup);
  if (activeTag) filtered = filtered.filter(n => safeTags(n.tags).includes(activeTag));
  if (q) filtered = filtered.filter(n => n.body.toLowerCase().includes(q));

  renderGroupBar();
  countEl.textContent = notes.length + ' 条';

  if (filtered.length === 0) {
    listEl.classList.remove('desktop-masonry');
    listEl.innerHTML = notes.length === 0
      ? `<div class="empty-state"><span class="icon">🍃</span><span class="hint">万物藏于心</span></div>`
      : `<div class="empty-state"><span class="hint">没有找到匹配的笔记</span></div>`;
    return;
  }

  const isDesktop = window.innerWidth >= 600;
  const numCols = window.innerWidth >= 900 ? 4 : 3;

  if (isDesktop) {
    listEl.classList.add('desktop-masonry');
    // JS 瀑布流：每张卡片塞进最短的列
    const cols = Array.from({ length: numCols }, () => []);
    for (const n of filtered) {
      let shortest = 0;
      for (let i = 1; i < numCols; i++) {
        if (cols[i].length < cols[shortest].length) shortest = i;
      }
      cols[shortest].push(n);
    }
    const colGap = window.innerWidth >= 900 ? 16 : 14;
    listEl.style.gap = colGap + 'px';
    listEl.innerHTML = cols.map(colCards =>
      `<div class="masonry-col" style="gap:${colGap}px">` +
      colCards.map(n => buildCardHTML(n)).join('') +
      '</div>'
    ).join('');
  } else {
    listEl.classList.remove('desktop-masonry');
    listEl.style.gap = '';
    listEl.innerHTML = filtered.map(n => buildCardHTML(n)).join('');
  }

  // event bindings
  listEl.querySelectorAll('.card').forEach(card => card.addEventListener('click', e => {
    if (e.target.closest('button') || e.target.closest('img')) return;
    const bodyEl = card.querySelector('.body');
    const hintEl = card.querySelector('.expand-hint');
    if (bodyEl.classList.contains('expanded')) { bodyEl.classList.remove('expanded'); if (hintEl) hintEl.textContent = '点击展开全文…'; }
    else { bodyEl.classList.add('expanded'); if (hintEl) hintEl.textContent = '收起'; }
  }));
  listEl.querySelectorAll('.edit-btn').forEach(btn => btn.addEventListener('click', e => { e.stopPropagation(); openEditor(btn.dataset.id); }));
  listEl.querySelectorAll('.del-btn').forEach(btn => btn.addEventListener('click', e => { e.stopPropagation(); deleteNote(btn.dataset.id); }));
  listEl.querySelectorAll('.pin-btn').forEach(btn => btn.addEventListener('click', e => {
    e.stopPropagation();
    const n = notes.find(n => n.id === btn.dataset.id);
    if (!n) return;
    if (n.pinned) unpinNote(btn.dataset.id);
    else pinNote(btn.dataset.id);
  }));
  listEl.querySelectorAll('.expand-hint').forEach(hint => hint.addEventListener('click', e => {
    e.stopPropagation();
    const card = listEl.querySelector(`.card[data-id="${hint.dataset.id}"]`);
    if (!card) return;
    const bodyEl = card.querySelector('.body');
    if (bodyEl.classList.contains('expanded')) { bodyEl.classList.remove('expanded'); hint.textContent = '点击展开全文…'; }
    else { bodyEl.classList.add('expanded'); hint.textContent = '收起'; }
  }));
  listEl.querySelectorAll('.card-images img').forEach(img => img.addEventListener('click', e => {
    e.stopPropagation(); openLightbox(img.dataset.img);
  }));
}
function buildCardHTML(n) {
  const date = new Date(n.created_ts || n.ts);
  const dateStr = date.toLocaleDateString('zh-CN', { month:'short', day:'numeric' });
  const isLong = n.body.length > 200;
  const imgs = n.images || [];
  const imgHtml = imgs.length ? `<div class="card-images">${imgs.map(f => `<img src="/uploads/${esc(f)}" alt="" loading="lazy" data-img="/uploads/${esc(f)}">`).join('')}</div>` : '';
  const bodyHTML = esc(n.body).replace(/\*(\S[^*\n]*\S|\S)\*/g, '<em>$1</em>');
  const pinnedClass = n.pinned ? ' pinned' : '';
  // 格式化完整时间（ISO → 中文可读）
  function fmtISO(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    if (isNaN(d.getTime())) return '';
    const pad = n => String(n).padStart(2,'0');
    return d.getFullYear()+'年'+(d.getMonth()+1)+'月'+d.getDate()+'日 '+pad(d.getHours())+':'+pad(d.getMinutes());
  }
  const createdFull = fmtISO(n.created_at);
  const updatedFull = n.updated_at && n.updated_at !== n.created_at ? fmtISO(n.updated_at) : '';
  return `<div class="card${pinnedClass}" data-id="${n.id}">
      <div class="meta"><span class="time">${n.pinned ? '📌 ' : ''}${dateStr}</span><span class="actions"><button class="pin-btn" data-id="${n.id}">${n.pinned ? '取消置顶' : '置顶'}</button><button class="edit-btn" data-id="${n.id}">编辑</button><button class="del-btn" data-id="${n.id}">删除</button></span></div>
      ${n.title ? '<div class="title">'+esc(n.title)+(n.shared ? ' <span style="font-size:10px;opacity:.6;font-weight:400">🌐</span>' : '')+'</div>' : ''}
      <div class="body ${isLong ? '' : 'short'}" data-id="${n.id}">${n.group ? '<span class="group-badge">'+esc(n.group)+'</span>' : ''}${bodyHTML}</div>
      ${(() => { const tg = safeTags(n.tags); return tg.length ? '<div class="card-tags">'+tg.map(t => '<span class="card-tag">'+esc(t)+'</span>').join('')+'</div>' : ''; })()}
      ${imgHtml}
      ${isLong ? '<div class="expand-hint" data-id="'+n.id+'">点击展开全文…</div>' : ''}
      <div class="card-footer">${createdFull ? '创建于 '+createdFull : ''}${updatedFull ? ' · 更新于 '+updatedFull : ''}</div>
    </div>`;
}
