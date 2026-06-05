// ── 晚风 · API 通信层 ──

function getApiKey() {
  if (apiKey) return apiKey;
  apiKey = localStorage.getItem(API_KEY_STORAGE) || '';
  return apiKey;
}

async function apiFetch(path, opts = {}) {
  const key = getApiKey();
  const headers = { ...(opts.headers || {}) };
  if (key) headers['Authorization'] = 'Bearer ' + key;
  // Don't set Content-Type for FormData (upload)
  if (!(opts.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }
  const res = await fetch(API_BASE + path, { ...opts, headers });
  if (res.status === 401) { apiKey = null; localStorage.removeItem(API_KEY_STORAGE); throw new Error('unauthorized'); }
  if (!res.ok) throw new Error('API error: ' + res.status);
  return res.json();
}

async function uploadImage(file) {
  const form = new FormData();
  form.append('file', file);
  try {
    const key = getApiKey();
    const res = await fetch(API_BASE + '/upload', {
      method: 'POST', headers: { 'Authorization': 'Bearer ' + key }, body: form
    });
    if (res.ok) return await res.json();
  } catch(e) { console.error('upload failed', e); }
  return null;
}

async function adminApiFetch(path, opts = {}) {
  const k = getApiKey();
  const headers = { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + k };
  const res = await fetch(API_BASE + path, { ...opts, headers });
  if (!res.ok) throw new Error('Admin API error: ' + res.status);
  return res.json();
}
