// ── 晚风 · API 通信层 ──

class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

function getApiKey() {
  if (apiKey) return apiKey;
  apiKey = localStorage.getItem(API_KEY_STORAGE) || '';
  return apiKey;
}

async function readError(res) {
  let msg = 'HTTP ' + res.status;
  try {
    const data = await res.json();
    if (data && typeof data.error === 'string') msg = data.error;
  } catch { /* 非 JSON 响应，保留状态码 */ }
  return new ApiError(msg, res.status);
}

async function apiFetch(path, opts = {}) {
  const key = getApiKey();
  const headers = { ...(opts.headers || {}) };
  if (key) headers['Authorization'] = 'Bearer ' + key;
  // FormData 必须让浏览器自己带 boundary
  if (!(opts.body instanceof FormData)) headers['Content-Type'] = 'application/json';

  let url = API_BASE + path;
  if (!opts.method || opts.method === 'GET') {
    url += (path.includes('?') ? '&' : '?') + '_t=' + Date.now();
  }

  const res = await fetch(url, { ...opts, headers });
  if (res.status === 401) {
    apiKey = null;
    localStorage.removeItem(API_KEY_STORAGE);
    throw new ApiError('unauthorized', 401);
  }
  if (!res.ok) throw await readError(res);
  return res.json();
}

async function uploadImage(file) {
  const form = new FormData();
  form.append('file', file);
  const key = getApiKey();
  if (!key) throw new ApiError('unauthorized', 401);
  const res = await fetch(API_BASE + '/upload', {
    method: 'POST',
    headers: { 'Authorization': 'Bearer ' + key },
    body: form,
  });
  if (!res.ok) throw await readError(res);
  return res.json();
}

async function adminApiFetch(path, opts = {}) {
  const headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer ' + getApiKey(),
  };
  let url = API_BASE + path;
  if (!opts.method || opts.method === 'GET') {
    url += (path.includes('?') ? '&' : '?') + '_t=' + Date.now();
  }
  const res = await fetch(url, { ...opts, headers });
  if (res.status === 401) {
    apiKey = null;
    localStorage.removeItem(API_KEY_STORAGE);
    throw new ApiError('unauthorized', 401);
  }
  if (!res.ok) throw await readError(res);
  return res.json();
}
