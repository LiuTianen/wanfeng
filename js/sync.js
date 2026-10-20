// ── 晚风 · 离线队列 / 墓碑 / 合并 ──
// 设计：本地先写，标记 pending；登录后把「待上传 + 待删除」一次性 sync 给服务端，
// 服务端返回合并后的全量数据，以此为准。删除用墓碑记录，避免别的设备把笔记复活。

function compareNotes(a, b) {
  if (!!a.pinned !== !!b.pinned) return a.pinned ? -1 : 1;
  if (a.pinned && b.pinned) return (b.pinned_ts || 0) - (a.pinned_ts || 0);
  return (b.created_ts || b.ts || 0) - (a.created_ts || a.ts || 0);
}

function loadTombstones() {
  try {
    const raw = JSON.parse(localStorage.getItem(TOMBSTONE_KEY) || '{}');
    return raw && typeof raw === 'object' && !Array.isArray(raw) ? raw : {};
  } catch { return {}; }
}

function saveTombstones(map) {
  if (Object.keys(map).length === 0) localStorage.removeItem(TOMBSTONE_KEY);
  else localStorage.setItem(TOMBSTONE_KEY, JSON.stringify(map));
}

function addTombstone(id) {
  const map = loadTombstones();
  map[id] = Date.now();
  saveTombstones(map);
}

function removeTombstone(id) {
  const map = loadTombstones();
  if (id in map) { delete map[id]; saveTombstones(map); }
}

function normNote(raw) {
  const source = raw && typeof raw === 'object' ? raw : {};
  const ts = Number(source.ts) || (source.updated_at ? Date.parse(source.updated_at) : 0) || Date.now();
  const created = Number(source.created_ts) || (source.created_at ? Date.parse(source.created_at) : 0) || ts;
  return {
    id: typeof source.id === 'string' ? source.id : '',
    body: typeof source.body === 'string' ? source.body : '',
    title: typeof source.title === 'string' ? source.title : '',
    group: typeof source.group === 'string' ? source.group : '',
    tags: safeTags(source.tags),
    images: (Array.isArray(source.images) ? source.images : []).map(safeImage).filter(Boolean),
    shared: !!source.shared,
    pinned: !!source.pinned,
    pinned_ts: Number(source.pinned_ts) || (source.pinned_at ? Date.parse(source.pinned_at) || 0 : 0),
    ts,
    created_ts: created,
    created_at: source.created_at || '',
    updated_at: source.updated_at || '',
    pending: source.pending === 'create' || source.pending === 'update' ? source.pending : undefined,
  };
}

// 服务端数据与本地数据合并：本地有未同步改动且更新时，保本地
function mergeNotes(serverNotes, localNotes) {
  const map = new Map();
  for (const n of localNotes || []) map.set(n.id, n);
  for (const raw of serverNotes || []) {
    const server = normNote(raw);
    const local = map.get(server.id);
    if (local && local.pending && (local.ts || 0) > (server.ts || 0)) {
      map.set(server.id, local);
    } else {
      map.set(server.id, server);
    }
  }
  return Array.from(map.values()).sort(compareNotes);
}

function dropTombstoned(list) {
  const tombstones = loadTombstones();
  return list.filter(n => !(n.id in tombstones));
}

function hasPending() {
  return notes.some(n => n.pending) || Object.keys(loadTombstones()).length > 0;
}

// 把本地待上传的改动和待删除的 id 一次性提交；成功返回服务端全量数据
async function flushQueue() {
  if (!getApiKey()) return null;
  const pending = notes.filter(n => n.pending);
  const tombstones = loadTombstones();
  const deleted = Object.keys(tombstones);
  if (pending.length === 0 && deleted.length === 0) return null;

  const payload = {
    notes: pending.map(n => ({
      id: n.id,
      body: n.body,
      title: n.title || '',
      group: n.group || '',
      tags: safeTags(n.tags),
      images: (n.images || []).filter(safeImage),
      shared: !!n.shared,
      // 注意：不带 pinned —— 置顶只走 /pin 接口，避免一次普通保存把置顶清掉
      created_at: n.created_at || new Date(n.created_ts || Date.now()).toISOString(),
    })),
    deleted,
  };

  const data = await apiFetch('/notes/sync', { method: 'POST', body: JSON.stringify(payload) });
  const serverNotes = (data.notes || []).map(normNote);
  const returned = new Set(serverNotes.map(n => n.id));
  // 服务端跳过的（例如数据不合法）保留在本地并继续 pending，绝不静默丢弃
  const leftovers = notes.filter(n => n.pending && !returned.has(n.id));
  notes = serverNotes.concat(leftovers).sort(compareNotes);
  deleted.forEach(removeTombstone);
  saveLocal();
  return data;
}
