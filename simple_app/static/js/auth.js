let accessToken = null;
let refreshPromise = null;

function getCookie(name) {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

async function refreshAccessToken() {
  const csrf = getCookie('csrf_token');
  console.log('[AUTH] refreshAccessToken called, csrf:', csrf ? 'present' : 'missing');
  if (!csrf) {
    console.log('[AUTH] No csrf_token cookie, cannot refresh');
    return null;
  }
  const res = await fetch('/auth/refresh', {
    method: 'POST',
    headers: { 'X-CSRF-Token': csrf },
  });
  console.log('[AUTH] /auth/refresh response:', res.status, res.ok);
  if (!res.ok) return null;
  const data = await res.json();
  console.log('[AUTH] Refresh response data:', data);
  accessToken = data.accessToken;
  window.__accessToken = accessToken;
  console.log('[AUTH] Access token saved:', accessToken ? 'YES' : 'NO');
  return accessToken;
}

// Делаем функцию глобальной для использования в формах
window.refreshAccessToken = refreshAccessToken;

async function ensureAccessToken() {
  if (accessToken) return accessToken;
  if (!refreshPromise) {
    refreshPromise = refreshAccessToken().finally(() => {
      refreshPromise = null;
    });
  }
  return refreshPromise;
}

const originalFetch = window.fetch.bind(window);
window.fetch = async (input, init = {}) => {
  // Получаем путь из URL (обрабатываем и строки, и полные URL)
  let url = typeof input === 'string' ? input : (input.url || '');
  // Если это полный URL, извлекаем только путь
  if (url.startsWith('http://') || url.startsWith('https://')) {
    try {
      url = new URL(url).pathname;
    } catch (e) {
      console.error('[AUTH] Failed to parse URL:', url);
    }
  }

  const isApi = url.startsWith('/api') || url.startsWith('/auth') || url.startsWith('/users');
  const isRefresh = url.startsWith('/auth/refresh');
  const isAuthBootstrap = url.startsWith('/auth/login')
    || url.startsWith('/auth/register')
    || url.startsWith('/auth/forgot')
    || url.startsWith('/auth/reset');

  const options = { ...init };
  const headers = new Headers(options.headers || {});
  const method = (options.method || 'GET').toUpperCase();

  if (isApi && !isAuthBootstrap) {
    // Для /auth/refresh не запрашиваем access токен, чтобы не попасть в рекурсию.
    if (!isRefresh) {
      const token = await ensureAccessToken();
      console.log('[AUTH] Request to', url, '- token:', token ? 'present' : 'missing');
      if (token) {
        headers.set('Authorization', `Bearer ${token}`);
      } else {
        console.warn('[AUTH] No access token available for', url);
      }
    }
    if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
      const csrf = getCookie('csrf_token');
      if (csrf) {
        headers.set('X-CSRF-Token', csrf);
      }
    }
  }

  options.headers = headers;
  const response = await originalFetch(input, options);
  
  if (response.status === 401 && isApi && !options._retry && !isRefresh) {
    console.log('[AUTH] Got 401, attempting to refresh token...');
    const newToken = await refreshAccessToken();
    if (newToken) {
      console.log('[AUTH] Token refreshed, retrying request to', url);
      const retryHeaders = new Headers(options.headers);
      retryHeaders.set('Authorization', `Bearer ${newToken}`);
      const retryOptions = { ...options, headers: retryHeaders, _retry: true };
      return originalFetch(input, retryOptions);
    } else {
      console.log('[AUTH] Failed to refresh token');
    }
  }
  
  if (response.status === 401 && isApi && !url.startsWith('/auth')) {
    console.log('[AUTH] Redirecting to login due to 401');
    window.location.href = '/login';
  }
  
  return response;
};

async function handleLogout(event) {
  event.preventDefault();
  await fetch('/auth/logout', { method: 'POST' });
  window.location.href = '/login';
}

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('auth-logout')?.addEventListener('click', handleLogout);
  ensureAccessToken();
});

async function extractError(res) {
  const contentType = res.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    const data = await res.json();
    return data.detail || data.message || JSON.stringify(data);
  }
  return res.text();
}
