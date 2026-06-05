// ── 晚风 · 设置 & 管理 ──

let currentKeyIsAdmin = false;

(async function restoreAdmin() {
  const key = getApiKey();
  if (!key) return;
  try {
    const res = await fetch(API_BASE + '/auth/verify', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ key }) });
    const data = await res.json();
    if (data.valid) currentKeyIsAdmin = data.is_admin || false;
  } catch {}
})();

function promptConnection() {
  const key = getApiKey();
  const overlay = document.createElement('div');
  overlay.className = 'overlay';
  overlay.style.alignItems = 'center'; overlay.style.padding = '20px';
  overlay.innerHTML = `
    <div class="editor" style="border-radius:12px;max-width:400px">
      <div style="text-align:center;color:var(--accent);font-family:var(--serif);font-size:18px;margin-bottom:12px">连接服务器</div>
      <input type="password" id="apikey-input" placeholder="粘贴 API Key…" value="${esc(key || '')}" style="width:100%;padding:12px 16px;background:var(--bg);border:1px solid var(--border);border-radius:10px;color:var(--text);font-size:14px;font-family:var(--font);outline:none">
      <div class="btn-row" style="margin-top:14px">
        <button class="btn btn-ghost" id="conn-cancel">关闭</button>
        <button class="btn btn-save" id="conn-save">连接</button>
      </div></div>`;
  document.body.appendChild(overlay);
  const input = overlay.querySelector('#apikey-input'); input.focus();
  overlay.querySelector('#conn-cancel').addEventListener('click', () => overlay.remove());
  overlay.querySelector('#conn-save').addEventListener('click', async () => {
    const val = input.value.trim(); if (!val) return;
    try {
      const res = await fetch(API_BASE + '/auth/verify', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ key: val }) });
      const data = await res.json();
      if (data.valid) {
        localStorage.setItem(API_KEY_STORAGE, val); apiKey = val;
        currentKeyIsAdmin = data.is_admin || false;
        overlay.remove(); toast('已连接 ✓'); load();
      } else toast('密钥无效，请重试');
    } catch { toast('无法连接服务器'); }
  });
  overlay.addEventListener('click', e => { if (e.target === overlay) overlay.remove(); });
}

function promptSettings() {
  const overlay = document.createElement('div');
  overlay.className = 'overlay';
  overlay.style.alignItems = 'center'; overlay.style.padding = '20px';
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
          <button class="btn-img-upload" id="btn-bg-upload" style="font-size:12px">📷 自定义图片</button>
          <button class="btn btn-ghost" id="btn-bg-reset" style="font-size:12px;padding:6px 14px">恢复默认</button>
          <input type="file" id="bg-file-input" accept="image/*" style="display:none">
        </div>
      </div>
      <div id="admin-panel" style="display:none;margin-top:20px;border-top:1px solid var(--border);padding-top:16px"></div>
      <div style="margin-top:16px;border-top:1px solid var(--border);padding-top:16px">
        <div style="font-size:14px;color:var(--accent);margin-bottom:12px">📦 数据</div>
        <div style="display:flex;gap:10px">
          <button class="btn btn-ghost" id="settings-export" style="font-size:12px;padding:8px 16px">📤 导出 JSON</button>
          <button class="btn btn-ghost" id="settings-import" style="font-size:12px;padding:8px 16px">📥 导入 JSON</button>
        </div>
        <input type="file" id="settings-import-file" accept=".json" style="display:none">
      </div>
      <div class="btn-row" style="margin-top:16px">
        <button class="btn btn-ghost" id="settings-close">关闭</button>
      </div></div>`;
  document.body.appendChild(overlay);
  overlay.querySelector('#settings-close').addEventListener('click', () => overlay.remove());
  // 导出
  overlay.querySelector('#settings-export').addEventListener('click', () => {
    if (notes.length === 0) { toast('没有可导出的笔记'); return; }
    const blob = new Blob([JSON.stringify(notes, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = 'wanfeng-backup-' + new Date().toISOString().slice(0,10) + '.json';
    a.click(); URL.revokeObjectURL(url); toast('导出成功 ✓');
  });
  // 导入
  overlay.querySelector('#settings-import').addEventListener('click', () => overlay.querySelector('#settings-import-file').click());
  overlay.querySelector('#settings-import-file').addEventListener('change', async e => {
    const file = e.target.files[0]; if (!file) return;
    try {
      const text = await file.text();
      const imported = JSON.parse(text);
      if (!Array.isArray(imported)) { toast('格式错误'); return; }
      notes = imported; notes.sort((a,b) => b.ts - a.ts); saveLocal();
      overlay.remove(); render(); toast('导入 ' + imported.length + ' 条 ✓');
    } catch { toast('JSON 解析失败'); }
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
    const file = e.target.files[0]; if (!file) return;
    const reader = new FileReader();
    reader.onload = () => { setBackground(reader.result); bgPresets.querySelectorAll('.bg-swatch').forEach(s => s.classList.remove('active')); };
    reader.readAsDataURL(file);
  });
  overlay.querySelector('#btn-bg-reset').addEventListener('click', () => {
    setBackground(''); bgPresets.querySelectorAll('.bg-swatch').forEach(s => s.classList.toggle('active', s.dataset.bg === ''));
  });

  if (currentKeyIsAdmin) renderAdminPanel(overlay.querySelector('#admin-panel'));
}

function setBackground(bg) {
  localStorage.setItem('wanfeng_bg', bg || '');
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

async function renderAdminPanel(panel) {
  panel.style.display = 'block';
  panel.innerHTML = '<div style="text-align:center;color:var(--text-muted);font-size:13px">加载中…</div>';
  try {
    const data = await adminApiFetch('/admin/keys');
    const keys = data.keys || [];
    let html = '<div style="font-size:14px;color:var(--accent);margin-bottom:12px">Key 管理 · ' + keys.length + ' 个</div>';
    html += '<div style="max-height:200px;overflow-y:auto;margin-bottom:12px">';
    for (const k of keys) {
      html += `<div style="display:flex;align-items:center;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border);font-size:13px">
        <span><span style="color:var(--text)">${esc(k.label)}</span>${k.is_admin ? ' <span style="color:var(--accent);font-size:10px">admin</span>' : ''}
        <span style="color:var(--text-muted);font-size:10px;margin-left:6px">${esc(k.key_preview)}</span>${k.revoked ? ' <span style="color:#d47272;font-size:10px">已撤销</span>' : ''}</span>
        ${!k.is_admin && !k.revoked ? `<button data-id="${esc(k.id)}" style="background:none;border:none;color:#d47272;cursor:pointer;font-size:12px" class="btn-revoke">撤销</button>` : '<span style="width:32px"></span>'}
      </div>`;
    }
    html += '</div>';
    html += `<div style="display:flex;gap:8px">
      <input type="text" id="new-key-label" placeholder="用户标签（如：小明）" style="flex:1;padding:8px 12px;background:var(--bg);border:1px solid var(--border);border-radius:8px;color:var(--text);font-size:13px;font-family:var(--font);outline:none">
      <button class="btn btn-save" id="btn-gen-key" style="padding:8px 16px;font-size:13px">生成</button>
    </div>`;
    html += '<div id="new-key-result" style="margin-top:8px;font-size:12px"></div>';
    panel.innerHTML = html;

    panel.querySelectorAll('.btn-revoke').forEach(btn => {
      btn.addEventListener('click', async () => {
        if (!confirm('确定撤销这个 Key？')) return;
        try { await adminApiFetch('/admin/keys/' + btn.dataset.id, { method: 'DELETE' }); renderAdminPanel(panel); toast('已撤销'); }
        catch { toast('操作失败'); }
      });
    });

    panel.querySelector('#btn-gen-key').addEventListener('click', async () => {
      const label = panel.querySelector('#new-key-label').value.trim() || '用户';
      try {
        const result = await adminApiFetch('/admin/keys', { method: 'POST', body: JSON.stringify({ label }) });
        const resultEl = panel.querySelector('#new-key-result');
        resultEl.innerHTML = `<div style="background:var(--accent-dim);padding:10px;border-radius:8px;border:1px solid var(--accent)">
          <div style="font-size:11px;color:var(--text-muted);margin-bottom:4px">新 Key（仅显示一次，请立即复制！）</div>
          <div style="font-size:12px;word-break:break-all;color:var(--accent);cursor:pointer" id="copy-key">${esc(result.apikey)}</div>
          <div style="font-size:10px;color:var(--text-muted);margin-top:4px">标签：${esc(result.label)}</div></div>`;
        resultEl.querySelector('#copy-key').addEventListener('click', function() {
          navigator.clipboard.writeText(this.textContent).then(() => toast('已复制 ✓'));
        });
        panel.querySelector('#new-key-label').value = '';
        renderAdminPanel(panel);
      } catch { toast('生成失败'); }
    });
  } catch {
    panel.innerHTML = '<div style="text-align:center;color:var(--text-muted);font-size:13px">加载失败（需要管理员权限）</div>';
  }
}
