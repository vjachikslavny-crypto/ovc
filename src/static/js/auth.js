let accessToken = null;
let refreshPromise = null;

// Auth mode is injected by template
const AUTH_MODE = window.__AUTH_MODE || 'local';

function getCookie(name) {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

async function refreshAccessToken() {
  const hasSupabase = window.supabaseAuth && (AUTH_MODE === 'supabase' || AUTH_MODE === 'both');

  if (hasSupabase) {
    const existing = window.supabaseAuth.getAccessToken();
    if (existing) {
      accessToken = existing;
      window.__accessToken = accessToken;
      return accessToken;
    }
  }
  
  // For local or both modes, try local refresh first
  const csrf = getCookie('csrf_token');
  console.log('[AUTH] refreshAccessToken called, csrf:', csrf ? 'present' : 'missing');
  if (!csrf) {
    // No local session, try Supabase refresh if available
    if (hasSupabase) {
      const token = await window.supabaseAuth.refreshSession();
      if (token) {
        accessToken = token;
        window.__accessToken = accessToken;
        return accessToken;
      }
    }
    console.log('[AUTH] No csrf_token cookie, cannot refresh');
    return null;
  }
  const res = await fetch('/auth/refresh', {
    method: 'POST',
    headers: { 'X-CSRF-Token': csrf },
  });
  console.log('[AUTH] /auth/refresh response:', res.status, res.ok);
  if (!res.ok) {
    // Local refresh failed, try Supabase refresh if available
    if (hasSupabase) {
      const token = await window.supabaseAuth.refreshSession();
      if (token) {
        accessToken = token;
        window.__accessToken = accessToken;
        return accessToken;
      }
    }
    return null;
  }
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
  // Check for Supabase token first if available
  if ((AUTH_MODE === 'supabase' || AUTH_MODE === 'both') && window.supabaseAuth) {
    const sbToken = window.supabaseAuth.getAccessToken();
    if (sbToken) {
      accessToken = sbToken;
      window.__accessToken = accessToken;
      return accessToken;
    }
  }
  
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
  const options = { ...init };
  const inputUrl = typeof input === 'string' ? input : (input && input.url ? input.url : '');
  let resolvedUrl = null;

  try {
    resolvedUrl = new URL(inputUrl, window.location.href);
  } catch (e) {
    console.error('[AUTH] Failed to parse URL:', inputUrl);
  }

  if (resolvedUrl && resolvedUrl.origin !== window.location.origin) {
    return originalFetch(input, init);
  }

  const path = resolvedUrl ? resolvedUrl.pathname : inputUrl;
  const isApi = path.startsWith('/api')
    || path.startsWith('/auth')
    || path.startsWith('/users')
    || path.startsWith('/files');
  const isRefresh = path.startsWith('/auth/refresh');
  const isAuthBootstrap = path.startsWith('/auth/login')
    || path.startsWith('/auth/register')
    || path.startsWith('/auth/forgot')
    || path.startsWith('/auth/reset');

  const headers = new Headers();
  if (input && input.headers) {
    new Headers(input.headers).forEach((value, key) => headers.set(key, value));
  }
  if (options.headers) {
    new Headers(options.headers).forEach((value, key) => headers.set(key, value));
  }
  const method = (options.method || 'GET').toUpperCase();

  if (isApi && !isAuthBootstrap) {
    // Для /auth/refresh не запрашиваем access токен, чтобы не попасть в рекурсию.
    if (!isRefresh) {
      const token = await ensureAccessToken();
      console.log('[AUTH] Request to', path, '- token:', token ? 'present' : 'missing');
      if (token) {
        headers.set('Authorization', `Bearer ${token}`);
      } else {
        console.warn('[AUTH] No access token available for', path);
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
      console.log('[AUTH] Token refreshed, retrying request to', path);
      const retryHeaders = new Headers(options.headers);
      retryHeaders.set('Authorization', `Bearer ${newToken}`);
      const retryOptions = { ...options, headers: retryHeaders, _retry: true };
      return originalFetch(input, retryOptions);
    } else {
      console.log('[AUTH] Failed to refresh token');
    }
  }
  
  if (response.status === 401 && isApi && !path.startsWith('/auth')) {
    console.log('[AUTH] Redirecting to login due to 401');
    window.location.href = '/login';
  }
  
  return response;
};

async function handleLogout(event) {
  event.preventDefault();
  if ((AUTH_MODE === 'supabase' || AUTH_MODE === 'both') && window.supabaseAuth) {
    try {
      await window.supabaseAuth.signOut();
    } catch (e) {
      console.warn('[AUTH] Supabase sign out failed:', e);
    }
  }
  await fetch('/auth/logout', { method: 'POST' });
  window.location.href = '/login';
}

async function updateNavForSession() {
  if (!(AUTH_MODE === 'supabase' || AUTH_MODE === 'both')) return;
  if (!document.getElementById('nav-login') && !document.getElementById('nav-register')) {
    return;
  }
  
  const token = await ensureAccessToken();
  if (!token) return;
  
  try {
    const res = await fetch('/api/users/me');
    if (!res.ok) return;
    const user = await res.json();
    const navLogin = document.getElementById('nav-login');
    const navRegister = document.getElementById('nav-register');
    const navUser = document.getElementById('nav-user');
    const navLogout = document.getElementById('auth-logout');
    const navPassword = document.getElementById('nav-password');
    
    if (navLogin) navLogin.style.display = 'none';
    if (navRegister) navRegister.style.display = 'none';
    if (navUser) {
      navUser.textContent = user.email || user.username || 'Аккаунт';
      navUser.style.display = 'inline-flex';
    }
    if (navLogout) navLogout.style.display = 'inline-flex';
    if (navPassword && AUTH_MODE === 'supabase') {
      navPassword.style.display = 'none';
    }
  } catch (e) {
    console.warn('[AUTH] Failed to update nav from /users/me');
  }
}

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('auth-logout')?.addEventListener('click', handleLogout);
  ensureAccessToken();
  updateNavForSession();
});

async function extractError(res) {
  const contentType = res.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    const data = await res.json();
    return data.detail || data.message || JSON.stringify(data);
  }
  return res.text();
}
