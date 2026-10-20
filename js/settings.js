// ── 晚风 · 设置 & 管理 ──

(async function restoreAdmin() {
  const key = getApiKey();
  if (!key) return;
  try {
    const res = await fetch(API_BASE + '/auth/verify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key }),
    });
    const data = await res.json();
    if (data.valid) currentKeyIsAdmin = !!data.is_admin;
  } catch { /* 离线时忽略，设置面板会显示未连接 */ }
})();

function promptConnection() {
  const key = getApiKey();
  const overlay = document.createElement('div');
  overlay.className = 'overlay';
  overlay.style.alignItems = 'center';
  overlay.style.padding = '20px';
  overlay.innerHTML = `
    <div class="editor" style="border-radius:12px;max-width:400px">
      <div style="text-align:center;color:var(--accent);font-family:var(--serif);font-size:18px;margin-bottom:12px">连接服务器</div>
      <input type="password" id="apikey-input" placeholder="粘贴 API Key…" value="${esc(key)}" style="width:100%;padding:12px 16px;background:var(--bg);border:1px solid var(--border);border-radius:10px;color:var(--text);font-size:14px;font-family:var(--font);outline:none">
      <div class="btn-row" style="margin-top:14px">
        <button class="btn btn-ghost" id="conn-cancel" type="button">关闭</button>
        <button class="btn btn-save" id="conn-save" type="button">连接</button>
      </div></div>`;
  document.body.appendChild(overlay);
  const input = overlay.querySelector('#apikey-input');
  input.focus();
  overlay.querySelector('#conn-cancel').addEventListener('click', () => overlay.remove());
  overlay.querySelector('#conn-save').addEventListener('click', async () => {
    const val = input.value.trim();
    if (!val) return;
    try {
      const res = await fetch(API_BASE + '/auth/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key: val }),
      });
      const data = await res.json();
      if (data.valid) {
        localStorage.setItem(API_KEY_STORAGE, val);
        apiKey = val;
        currentKeyIsAdmin = !!data.is_admin;
        overlay.remove();
        toast('已连接 ✓');
        load();
      } else {
        toast('密钥无效，请重试');
      }
    } catch {
      toast('无法连接服务器');
    }
  });
  overlay.addEventListener('click', e => { if (e.target === overlay) overlay.remove(); });
}

function promptSettings() {
  const overlay = document.createElement('div');
  overlay.className = 'overlay';
  overlay.style.alignItems = 'center';
  overlay.style.padding = '20px';
  overlay.innerHTML = `<div class="editor" id="settings-panel" style="border-radius:12px;max-width:480px">
      <div style="text-align:center;color:var(--accent);font-family:var(--serif);font-size:18px;margin-bottom:8px">设置</div>
      <div style="text-align:center;font-size:12px;color:var(--text-muted);margin-bottom:12px">${currentKeyIsAdmin ? '管理员' : '用户'} · ${getApiKey() ? '已连接' : '未连接'}</div>
      <div id="bg-panel" style="margin-top:16px;border-top:1px solid var(--border);padding-top:16px">
        <div style="font-size:14px;color:var(--accent);margin-bottom:12px">🎨 背景设置</div>
        <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap" id="bg-presets">
          <div class="bg-swatch active" data-bg="" style="background:#141414;border:2px solid var(--accent)" title="默认"></div>
          <div class="bg-swatch" data-bg="linear-gradient(135deg,#0f0c29,#302b63,#24243e)" style="background:linear-gradient(135deg,#0f0c29,#302b63,#24243e)" title="深邃紫"></div>
          <div class="bg-swatch" data-bg="linear-gradient(135deg,#1a1a2e,#16213e,#0f3460)" style="background:linear-gradient(135deg,#1a1a2e,#16213e,#0f3460)" title="墨蓝"></div>
          <div class="bg-swatch" data-bg="linear-gradient(135deg,#2d1b2e,#1a1a1a,#0d1b2a)" style="background:linear-gradient(135deg,#2d1b2e,#1a1a1a,#0d1b2a)" title="暗夜紫"></div>
          <div class="bg-swatch" data-bg="linear-gradient(180deg,#1b1b2f,#162447,#1f4068)" style="background:linear-gradient(180deg,#1b1b2f,#162447,#1f4068)" title="夜空蓝"></div>
          <div class="bg-swatch" data-bg="linear-gradient(135deg,#0d1117,#161b22,#21262d)" style="background:linear-gradient(135deg,#0d1117,#161b22,#21262d)" title="GitHub Dark"></div>
          <div class="bg-swatch" data-bg="linear-gradient(160deg,#1a1a1a,#2d1b00)" style="background:linear-gradient(160deg,#1a1a1a,#2d1b00)" title="暖暗金"></div>
        </div>
        <div style="display:flex;gap:8px;align-items:center">
          <button class="btn-img-upload" id="btn-bg-upload" style="font-size:12px" type="button">📷 自定义图片</button>
          <button class="btn btn-ghost" id="btn-bg-reset" style="font-size:12px;padding:6px 14px" type="button">恢复默认</button>
          <input type="file" id="bg-file-input" accept="image/*" style="display:none">
        </div>
      </div>
      <div id="admin-panel" style="display:none;margin-top:20px;border-top:1px solid var(--border);padding-top:16px"></div>
      <div style="margin-top:16px;border-top:1px solid var(--border);padding-top:16px">
        <div style="font-size:14px;color:var(--accent);margin-bottom:12px">📦 数据</div>
        <div style="display:flex;gap:10px;flex-wrap:wrap">
          <button class="btn btn-ghost" id="settings-export" style="font-size:12px;padding:8px 16px" type="button">📤 导出 JSON</button>
          <button class="btn btn-ghost" id="settings-import" style="font-size:12px;padding:8px 16px" type="button">📥 导入 JSON</button>
          <button class="btn btn-ghost" id="settings-disconnect" style="font-size:12px;padding:8px 16px;color:#d47272" type="button">🔌 断开连接</button>
        </div>
        <input type="file" id="settings-import-file" accept=".json" style="display:none">
      </div>
      <div class="btn-row" style="margin-top:16px">
        <button class="btn btn-ghost" id="settings-close" type="button">关闭</button>
      </div></div>`;
  document.body.appendChild(overlay);
  overlay.querySelector('#settings-close').addEventListener('click', () => overlay.remove());

  // 导出
  overlay.querySelector('#settings-export').addEventListener('click', () => {
    if (notes.length === 0) { toast('没有可导出的笔记'); return; }
    const blob = new Blob([JSON.stringify(notes, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'wanfeng-backup-' + new Date().toISOString().slice(0, 10) + '.json';
    a.click();
    URL.revokeObjectURL(url);
    toast('导出成功 ✓');
  });

  // 导入：按 id 合并（不再整表覆盖），随后自动同步
  overlay.querySelector('#settings-import').addEventListener('click', () => overlay.querySelector('#settings-import-file').click());
  overlay.querySelector('#settings-import-file').addEventListener('change', async e => {
    const file = e.target.files[0];
    if (!file) return;
    try {
      const imported = JSON.parse(await file.text());
      if (!Array.isArray(imported)) { toast('格式错误'); return; }
      if (!confirm(`导入 ${imported.length} 条笔记？会与本地合并并尝试同步到服务器。`)) return;
      const map = new Map(notes.map(n => [n.id, n]));
      for (const raw of imported) {
        const norm = normNote(raw);
        if (!norm.id) norm.id = genId();
        norm.pending = map.has(norm.id) ? 'update' : 'create';
        map.set(norm.id, norm);
      }
      notes = Array.from(map.values()).sort(compareNotes);
      saveLocal();
      overlay.remove();
      render();
      toast('已导入 ' + imported.length + ' 条');
      syncPending().then(() => { render(); fetchGroups(); fetchTags(); });
    } catch {
      toast('JSON 解析失败');
    }
  });

  // 断开连接：清掉本机缓存的别人的日记，避免多人共设备时串号
  overlay.querySelector('#settings-disconnect').addEventListener('click', async () => {
    if (!getApiKey()) { toast('当前未连接'); return; }
    if (hasPending()) await syncPending();
    if (!confirm('断开后将清除本机缓存（服务器上的笔记不受影响），确定吗？')) return;
    localStorage.removeItem(API_KEY_STORAGE);
    localStorage.removeItem(STORAGE_KEY);
    localStorage.removeItem(TOMBSTONE_KEY);
    apiKey = null;
    currentKeyIsAdmin = false;
    notes = [];
    groups = [];
    allTags = [];
    overlay.remove();
    render();
    updateStatus('local');
    toast('已断开');
  });

  overlay.addEventListener('click', e => { if (e.target === overlay) overlay.remove(); });

  // 背景设置
  const bgPresets = overlay.querySelector('#bg-presets');
  const currentBg = localStorage.getItem('wanfeng_bg') || '';
  bgPresets.querySelectorAll('.bg-swatch').forEach(s => s.classList.toggle('active', s.dataset.bg === currentBg));
  bgPresets.addEventListener('click', e => {
    const swatch = e.target.closest('.bg-swatch');
    if (!swatch) return;
    setBackground(swatch.dataset.bg);
    bgPresets.querySelectorAll('.bg-swatch').forEach(s => s.classList.remove('active'));
    swatch.classList.add('active');
  });
  overlay.querySelector('#btn-bg-upload').addEventListener('click', () => overlay.querySelector('#bg-file-input').click());
  overlay.querySelector('#bg-file-input').addEventListener('change', e => {
    const file = e.target.files[0];
    if (!file) return;
    if (file.size > 3 * 1024 * 1024) { toast('背景图片请小于 3MB'); return; }
    const reader = new FileReader();
    reader.onload = () => {
      setBackground(reader.result);
      bgPresets.querySelectorAll('.bg-swatch').forEach(s => s.classList.remove('active'));
    };
    reader.readAsDataURL(file);
  });
  overlay.querySelector('#btn-bg-reset').addEventListener('click', () => {
    setBackground('');
    bgPresets.querySelectorAll('.bg-swatch').forEach(s => s.classList.toggle('active', s.dataset.bg === ''));
  });

  if (currentKeyIsAdmin) renderAdminPanel(overlay.querySelector('#admin-panel'));
}

function setBackground(bg) {
  try {
    localStorage.setItem('wanfeng_bg', bg || '');
  } catch {
    toast('背景太大，无法保存');
    return;
  }
  applyBackground();
}

function applyBackground() {
  const bg = localStorage.getItem('wanfeng_bg') || '';
  if (bg) {
    if (bg.startsWith('data:') || bg.startsWith('http')) {
      document.body.style.backgroundImage = `url(${bg})`;
      document.body.style.backgroundSize = 'cover';
      document.body.style.backgroundPosition = 'center';
      document.body.style.backgroundAttachment = 'fixed';
      document.body.style.background = `${document.body.style.backgroundImage} ${document.body.style.backgroundSize} ${document.body.style.backgroundPosition} ${document.body.style.backgroundAttachment}`;
    } else {
      document.body.style.background = bg;
      document.body.style.backgroundAttachment = 'fixed';
    }
  } else {
    document.body.style.background = '';
    document.body.style.backgroundImage = '';
    document.body.style.backgroundSize = '';
    document.body.style.backgroundAttachment = '';
  }
}

/* ── Admin: Key 管理 ── */
async function renderAdminPanel(panel) {
  panel.style.display = 'block';
  panel.innerHTML = '<div style="text-align:center;color:var(--text-muted);font-size:13px">加载中…</div>';
  try {
    const data = await adminApiFetch('/admin/keys');
    const keys = data.keys || [];
    panel.innerHTML = `
      <div style="font-size:14px;color:var(--accent);margin-bottom:12px">Key 管理 · <span id="key-count">${keys.length}</span> 个</div>
      <div id="key-list" style="max-height:200px;overflow-y:auto;margin-bottom:12px"></div>
      <div style="display:flex;gap:8px">
        <input type="text" id="new-key-label" placeholder="用户标签（如：小明）" maxlength="40" style="flex:1;padding:8px 12px;background:var(--bg);border:1px solid var(--border);border-radius:8px;color:var(--text);font-size:13px;font-family:var(--font);outline:none">
        <button class="btn btn-save" id="btn-gen-key" type="button" style="padding:8px 16px;font-size:13px">生成</button>
      </div>
      <div id="new-key-slot" style="margin-top:8px;font-size:12px"></div>`;

    renderKeyList(panel, keys);
    bindKeyListEvents(panel);

    panel.querySelector('#btn-gen-key').addEventListener('click', async () => {
      const label = panel.querySelector('#new-key-label').value.trim() || '用户';
      const btn = panel.querySelector('#btn-gen-key');
      btn.disabled = true;
      try {
        const result = await adminApiFetch('/admin/keys', {
          method: 'POST',
          body: JSON.stringify({ label }),
        });
        // 关键：把结果写进独立插槽，不再重渲染整个面板（否则 Key 会瞬间消失）
        showNewKey(panel, result);
        panel.querySelector('#new-key-label').value = '';
        const fresh = await adminApiFetch('/admin/keys');
        renderKeyList(panel, fresh.keys || []);
        bindKeyListEvents(panel);
      } catch (e) {
        toast(e.message === 'unauthorized' ? '登录已失效' : '生成失败: ' + e.message);
      } finally {
        btn.disabled = false;
      }
    });
  } catch (e) {
    panel.innerHTML = `<div style="text-align:center;color:var(--text-muted);font-size:13px">加载失败（${e.status === 403 ? '需要管理员权限' : '网络错误'}）</div>`;
  }
}

function renderKeyList(panel, keys) {
  const list = panel.querySelector('#key-list');
  if (!list) return;
  if (keys.length === 0) {
    list.innerHTML = '<div style="color:var(--text-muted);font-size:12px;padding:8px 0">还没有子 Key</div>';
    return;
  }
  list.innerHTML = keys.map(k => `
    <div style="display:flex;align-items:center;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border);font-size:13px">
      <span>
        <span style="color:var(--text)">${esc(k.label)}</span>${k.is_admin ? ' <span style="color:var(--accent);font-size:10px">admin</span>' : ''}
        <span style="color:var(--text-muted);font-size:10px;margin-left:6px">${esc(k.key_preview)}</span>
        ${k.revoked ? ' <span style="color:#d47272;font-size:10px">已撤销</span>' : ''}
      </span>
      ${!k.is_admin && !k.revoked ? `<button data-id="${esc(k.id)}" type="button" class="btn-revoke" style="background:none;border:none;color:#d47272;cursor:pointer;font-size:12px">撤销</button>` : '<span style="width:32px"></span>'}
    </div>`).join('');
  const counter = panel.querySelector('#key-count');
  if (counter) counter.textContent = keys.length;
}

function bindKeyListEvents(panel) {
  panel.querySelectorAll('.btn-revoke').forEach(btn => {
    btn.addEventListener('click', async () => {
      if (!confirm('确定撤销这个 Key？')) return;
      try {
        await adminApiFetch('/admin/keys/' + encodeURIComponent(btn.dataset.id), { method: 'DELETE' });
        const fresh = await adminApiFetch('/admin/keys');
        renderKeyList(panel, fresh.keys || []);
        bindKeyListEvents(panel);
        toast('已撤销');
      } catch (e) {
        toast('操作失败: ' + e.message);
      }
    });
  });
}

function showNewKey(panel, result) {
  const slot = panel.querySelector('#new-key-slot');
  if (!slot) return;
  slot.innerHTML = `
    <div style="background:var(--accent-dim);padding:14px;border-radius:10px;border:1px solid var(--accent)">
      <div style="font-size:11px;color:var(--text-muted);margin-bottom:8px">🔑 新 Key（仅显示一次，请立即复制！）</div>
      <div style="display:flex;gap:8px;align-items:stretch">
        <code id="copy-key" style="flex:1;background:var(--bg);padding:10px 14px;border-radius:8px;font-size:12px;word-break:break-all;color:var(--accent);font-family:monospace;border:1px solid var(--border);line-height:1.6;user-select:all">${esc(result.apikey)}</code>
        <button id="btn-copy-key" type="button" style="flex-shrink:0;background:var(--accent);color:#141414;border:none;border-radius:8px;padding:8px 16px;font-size:13px;font-weight:600;cursor:pointer;font-family:var(--font);white-space:nowrap">📋 复制</button>
      </div>
      <div style="font-size:10px;color:var(--text-muted);margin-top:8px">标签：${esc(result.label)}</div>
    </div>`;
  const btn = slot.querySelector('#btn-copy-key');
  const code = slot.querySelector('#copy-key');
  btn.addEventListener('click', async () => {
    const text = code.textContent;
    let ok = false;
    try {
      await navigator.clipboard.writeText(text);
      ok = true;
    } catch {
      // http 环境没有 clipboard API，退回选中文本
      const range = document.createRange();
      range.selectNodeContents(code);
      const sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
      ok = true;
    }
    if (ok) {
      btn.textContent = '✅ 已复制';
      setTimeout(() => { btn.textContent = '📋 复制'; }, 2000);
      toast('已复制到剪贴板 ✓');
    }
  });
}
