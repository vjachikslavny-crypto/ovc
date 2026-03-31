let accessToken = null;
let refreshPromise = null;

// Auth mode is injected by template
const AUTH_MODE = window.__AUTH_MODE || 'local';

function getCookie(name) {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

function persistAccessCookie(token) {
  if (!token) return;
  const secure = window.location.protocol === 'https:' ? '; Secure' : '';
  document.cookie = `ovc_access_token=${encodeURIComponent(token)}; Path=/; SameSite=Lax${secure}`;
}

function clearAccessCookie() {
  const secure = window.location.protocol === 'https:' ? '; Secure' : '';
  document.cookie = `ovc_access_token=; Path=/; Max-Age=0; SameSite=Lax${secure}`;
}

async function refreshAccessToken() {
  const hasSupabase = window.supabaseAuth && (AUTH_MODE === 'supabase' || AUTH_MODE === 'both');

  // For local and both modes prioritize local cookie refresh first.
  if (AUTH_MODE === 'local' || AUTH_MODE === 'both' || AUTH_MODE === 'none') {
    const refreshCookie = getCookie('refresh_token');
    if (refreshCookie) {
      const csrf = getCookie('csrf_token');
      if (csrf) {
        const res = await fetch('/auth/refresh', {
          method: 'POST',
          headers: { 'X-CSRF-Token': csrf },
        });
        if (res.ok) {
          const data = await res.json();
          accessToken = data.accessToken;
          persistAccessCookie(accessToken);
          return accessToken;
        }
      }
    }
  }

  if (hasSupabase) {
    const existing = window.supabaseAuth.getAccessToken();
    if (existing) {
      accessToken = existing;
      persistAccessCookie(accessToken);
      return accessToken;
    }
    const refreshed = await window.supabaseAuth.refreshSession();
    if (refreshed) {
      accessToken = refreshed;
      persistAccessCookie(accessToken);
      return accessToken;
    }
  }

  return null;
}

// Делаем функцию глобальной для использования в формах
window.refreshAccessToken = refreshAccessToken;

async function ensureAccessToken() {
  if (accessToken) return accessToken;

  // In local/both mode prefer local refresh-token session.
  if (AUTH_MODE === 'local' || AUTH_MODE === 'both' || AUTH_MODE === 'none') {
    const refreshCookie = getCookie('refresh_token');
    if (refreshCookie) {
      if (!refreshPromise) {
        refreshPromise = refreshAccessToken().finally(() => {
          refreshPromise = null;
        });
      }
      return refreshPromise;
    }
  }

  // Fallback to Supabase token (for supabase mode or when local cookie absent).
  if ((AUTH_MODE === 'supabase' || AUTH_MODE === 'both') && window.supabaseAuth) {
    const sbToken = window.supabaseAuth.getAccessToken();
    if (sbToken) {
      accessToken = sbToken;
      persistAccessCookie(accessToken);
      return accessToken;
    }
  }

  if (!refreshPromise) {
    refreshPromise = refreshAccessToken().finally(() => {
      refreshPromise = null;
    });
  }
  return refreshPromise;
}

window.ensureAccessToken = ensureAccessToken;

const originalFetch = window.fetch.bind(window);
window.fetch = async (input, init = {}) => {
  const options = { ...init };
  const inputUrl = typeof input === 'string' ? input : (input && input.url ? input.url : '');
  let resolvedUrl = null;

  try {
    resolvedUrl = new URL(inputUrl, window.location.href);
  } catch (_) {
    // malformed URL — pass through without auth headers
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
      if (token) {
        headers.set('Authorization', `Bearer ${token}`);
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
    const newToken = await refreshAccessToken();
    if (newToken) {
      const retryHeaders = new Headers(options.headers);
      retryHeaders.set('Authorization', `Bearer ${newToken}`);
      const retryOptions = { ...options, headers: retryHeaders, _retry: true };
      return originalFetch(input, retryOptions);
    }
  }
  
  if (response.status === 401 && isApi && !path.startsWith('/auth')) {
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
  clearAccessCookie();
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
    let res = await fetch('/api/users/me');
    if (!res.ok && res.status === 404) {
      res = await fetch('/users/me');
    }
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
  window.addEventListener('ovc:supabase-auth', () => {
    updateNavForSession();
  });
});

async function extractError(res) {
  const contentType = res.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    const data = await res.json();
    return data.detail || data.message || JSON.stringify(data);
  }
  return res.text();
}
