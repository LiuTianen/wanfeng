// ── 晚风 · 编辑器 ──

function openEditor(id = null) {
  editId = id;
  const note = id ? notes.find(n => n.id === id) : null;

  const overlay = document.createElement('div');
  overlay.className = 'overlay';
  overlay.innerHTML = `
    <div class="editor" role="dialog" aria-modal="true">
      <input type="text" id="note-title" class="note-title-input" placeholder="标题（选填）…" value="${note ? esc(note.title) : ''}" autocomplete="off" maxlength="200">
      <div class="group-input-row" style="position:relative">
        <label>📁</label>
        <input type="text" id="note-group" placeholder="分组（点选或输入）…" value="${note ? esc(note.group) : ''}" autocomplete="off" maxlength="64">
        <div class="group-dropdown" id="group-dropdown"></div>
      </div>
      <div class="tag-input-row" id="tag-input-row" style="position:relative">
        <label>🏷️</label>
        <input type="text" id="tag-input" placeholder="输入标签后点 + 或回车…" autocomplete="off" maxlength="32">
        <button id="tag-add-btn" type="button" style="background:var(--accent-dim);border:1px solid var(--accent);color:var(--accent);border-radius:50%;width:28px;height:28px;font-size:18px;cursor:pointer;flex-shrink:0;display:flex;align-items:center;justify-content:center;padding:0">+</button>
        <div class="group-dropdown" id="tag-dropdown"></div>
      </div>
      <div class="img-upload-row">
        <label>🖼️</label>
        <button class="btn-img-upload" id="btn-pick-image" type="button">+ 添加图片</button>
        <input type="file" id="file-input" accept="image/*" multiple style="display:none">
        <span class="img-upload-progress" id="upload-progress"></span>
      </div>
      <div class="img-preview-wrap" id="img-preview-wrap"></div>
      <div class="share-toggle-row" style="margin-bottom:2px">
        <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-size:12px;color:var(--text-muted)">
          <input type="checkbox" id="note-shared" style="accent-color:var(--accent)">
          <span>🌐 公开此笔记</span>
        </label>
      </div>
      <textarea id="note-body" placeholder="此刻想写点什么…" maxlength="100000">${note ? esc(note.body) : ''}</textarea>
      <div class="btn-row">
        <button class="btn btn-ghost" id="btn-cancel" type="button">取消</button>
        <button class="btn btn-save" id="btn-save" type="button">保存</button>
      </div></div>`;
  document.body.appendChild(overlay);

  const textarea = overlay.querySelector('#note-body');
  const groupInput = overlay.querySelector('#note-group');
  const tagInput = overlay.querySelector('#tag-input');
  const tagRow = overlay.querySelector('#tag-input-row');
  const groupDropdown = overlay.querySelector('#group-dropdown');
  const tagDropdown = overlay.querySelector('#tag-dropdown');
  const fileInput = overlay.querySelector('#file-input');
  const imgPreview = overlay.querySelector('#img-preview-wrap');
  const uploadProgress = overlay.querySelector('#upload-progress');

  textarea.focus();
  if (note) overlay.querySelector('#note-shared').checked = !!note.shared;
  let currentTags = note ? safeTags(note.tags).slice() : [];
  let currentImages = note ? (note.images || []).map(safeImage).filter(Boolean) : [];

  /* ── 分组下拉 ── */
  function populateGroupDropdown() {
    if (groups.length === 0) { groupDropdown.classList.remove('show'); return; }
    groupDropdown.innerHTML = groups.map(g => `<div class="group-dropdown-item">${esc(g.name)}</div>`).join('');
    groupDropdown.classList.add('show');
    groupDropdown.querySelectorAll('.group-dropdown-item').forEach(item => {
      item.addEventListener('mousedown', e => {
        e.preventDefault();
        groupInput.value = item.textContent;
        groupDropdown.classList.remove('show');
      });
    });
  }
  groupInput.addEventListener('focus', async () => {
    if (groups.length === 0) await fetchGroups();
    populateGroupDropdown();
  });
  groupInput.addEventListener('input', () => {
    const val = groupInput.value.toLowerCase();
    groupDropdown.querySelectorAll('.group-dropdown-item').forEach(item => {
      item.style.display = item.textContent.toLowerCase().includes(val) ? '' : 'none';
    });
  });
  groupInput.addEventListener('blur', () => setTimeout(() => groupDropdown.classList.remove('show'), 150));

  /* ── 标签 ── */
  function addTagFromInput() {
    const val = tagInput.value.trim();
    if (val && !currentTags.includes(val) && currentTags.length < 20) {
      currentTags.push(val);
      renderTagChips();
    }
    tagInput.value = '';
  }
  function renderTagChips() {
    tagRow.querySelectorAll('.tag-chip').forEach(c => c.remove());
    for (const t of currentTags) {
      const chip = document.createElement('span');
      chip.className = 'tag-chip';
      chip.innerHTML = `${esc(t)}<span class="tag-x" data-tag="${esc(t)}">×</span>`;
      tagRow.insertBefore(chip, tagInput);
    }
    tagRow.querySelectorAll('.tag-x').forEach(x => {
      x.addEventListener('click', () => {
        currentTags = currentTags.filter(t => t !== x.dataset.tag);
        renderTagChips();
      });
    });
  }
  tagInput.addEventListener('keydown', e => {
    if (e.isComposing || e.keyCode === 229) return;
    if (e.key === 'Enter') { e.preventDefault(); addTagFromInput(); }
  });
  tagInput.addEventListener('compositionend', () => setTimeout(() => {
    if (/[\s，,]$/.test(tagInput.value)) addTagFromInput();
  }, 50));
  overlay.querySelector('#tag-add-btn').addEventListener('click', () => {
    addTagFromInput();
    tagInput.focus();
  });
  renderTagChips();

  /* ── 标签下拉 ── */
  function populateTagDropdown() {
    const available = allTags.filter(t => !currentTags.includes(t.name));
    if (available.length === 0) { tagDropdown.classList.remove('show'); return; }
    tagDropdown.innerHTML = available.map(t =>
      `<div class="group-dropdown-item" data-tag="${esc(t.name)}">🏷 ${esc(t.name)}<span style="color:var(--text-muted);font-size:10px;margin-left:6px">${t.count}</span></div>`
    ).join('');
    tagDropdown.classList.add('show');
    tagDropdown.querySelectorAll('.group-dropdown-item').forEach(item => {
      item.addEventListener('mousedown', e => {
        e.preventDefault();
        const name = item.dataset.tag;
        if (name && !currentTags.includes(name)) { currentTags.push(name); renderTagChips(); }
        tagInput.value = '';
        tagDropdown.classList.remove('show');
      });
    });
  }
  tagInput.addEventListener('focus', () => populateTagDropdown());
  tagInput.addEventListener('input', () => {
    const val = tagInput.value.toLowerCase();
    tagDropdown.querySelectorAll('.group-dropdown-item').forEach(item => {
      item.style.display = item.dataset.tag.toLowerCase().includes(val) ? '' : 'none';
    });
    if (!val) populateTagDropdown();
    else if (!tagDropdown.classList.contains('show')) tagDropdown.classList.add('show');
  });
  tagInput.addEventListener('blur', () => setTimeout(() => tagDropdown.classList.remove('show'), 150));

  /* ── 图片 ── */
  function renderImgPreview() {
    imgPreview.innerHTML = currentImages.map(f => `
      <div class="img-preview-item">
        <img src="/uploads/${esc(f)}" alt="">
        <button class="img-remove" type="button" data-file="${esc(f)}" title="移除">×</button>
      </div>`).join('');
    imgPreview.querySelectorAll('.img-remove').forEach(btn => btn.addEventListener('click', () => {
      currentImages = currentImages.filter(f => f !== btn.dataset.file);
      renderImgPreview();
    }));
  }
  renderImgPreview();

  overlay.querySelector('#btn-pick-image').addEventListener('click', () => fileInput.click());
  fileInput.addEventListener('change', async () => {
    const files = Array.from(fileInput.files || []);
    if (!files.length) return;
    if (!getApiKey()) { toast('请先连接服务器再上传图片'); fileInput.value = ''; return; }
    let failed = 0;
    for (const f of files) {
      uploadProgress.textContent = '上传中…';
      try {
        const result = await uploadImage(f);
        if (result && result.filename) {
          currentImages.push(result.filename);
          renderImgPreview();
        }
      } catch (e) {
        failed++;
        console.error('upload failed', e);
      }
    }
    uploadProgress.textContent = '';
    fileInput.value = '';
    if (failed) toast(failed + ' 张图片上传失败');
  });

  /* ── 键盘适配 ── */
  let vvHandler = null;
  const origBodyHeight = document.body.style.height || '';
  const origBodyOverflow = document.body.style.overflow || '';
  if (window.visualViewport) {
    vvHandler = () => {
      const vh = window.visualViewport.height;
      if (vh < window.innerHeight - 80) {
        document.body.style.height = vh + 'px';
        document.body.style.overflow = 'hidden';
        textarea.scrollIntoView({ block: 'nearest' });
      }
    };
    window.visualViewport.addEventListener('resize', vvHandler);
  }

  const onKey = e => { if (e.key === 'Escape') close(); };
  const close = () => {
    if (vvHandler) window.visualViewport.removeEventListener('resize', vvHandler);
    document.removeEventListener('keydown', onKey);
    document.body.style.height = origBodyHeight;
    document.body.style.overflow = origBodyOverflow;
    overlay.remove();
    editId = null;
  };
  document.addEventListener('keydown', onKey);
  overlay.addEventListener('click', e => { if (e.target === overlay) close(); });
  overlay.querySelector('#btn-cancel').addEventListener('click', close);

  overlay.querySelector('#btn-save').addEventListener('click', async () => {
    const body = textarea.value.trim();
    if (!body) { toast('内容不能为空哦～'); return; }
    if (body.length > 100000) { toast('内容太长了'); return; }

    const wasEdit = !!editId;
    const titleVal = (overlay.querySelector('#note-title').value || '').trim().slice(0, 200);
    const shared = overlay.querySelector('#note-shared').checked;
    const groupVal = groupInput.value.trim().slice(0, 64);
    const tags = currentTags.slice();
    const images = currentImages.slice();

    if (wasEdit) {
      const n = notes.find(x => x.id === editId);
      if (n) {
        Object.assign(n, { body, title: titleVal, group: groupVal, tags, images, shared });
        n.ts = Date.now();
        n.pending = 'update';
      }
    } else {
      notes.unshift({
        id: genId(), body, title: titleVal, group: groupVal, tags, images, shared,
        ts: Date.now(), created_ts: Date.now(), created_at: '', updated_at: '',
        pinned: false, pinned_ts: 0, pending: 'create',
      });
    }
    notes.sort(compareNotes);
    saveLocal();
    close();
    render(searchEl.value);
    toast(wasEdit ? '已更新 ✓' : '已保存 ✓');
    syncPending().then(() => {
      render(searchEl.value);
      fetchGroups();
      fetchTags();
    });
  });
}

async function deleteNote(id) {
  if (!confirm('确定删除这条笔记吗？')) return;
  notes = notes.filter(n => n.id !== id);
  addTombstone(id);
  saveLocal();
  render(searchEl.value);
  toast('已删除');

  if (!getApiKey()) { updateStatus('local'); return; }
  try {
    await apiFetch('/notes/' + encodeURIComponent(id), { method: 'DELETE' });
    removeTombstone(id);
    updateStatus('online');
  } catch (e) {
    if (e && e.status === 404) { removeTombstone(id); updateStatus('online'); }
    else if (e && e.status === 401) updateStatus('unauth');
    else updateStatus('offline');   // 墓碑保留，下次联网继续同步删除
  }
  fetchGroups();
  fetchTags();
}
