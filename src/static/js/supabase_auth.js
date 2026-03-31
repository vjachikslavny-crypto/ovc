/**
 * Supabase Auth integration for OVC.
 * 
 * This module provides Supabase authentication when AUTH_MODE includes "supabase".
 * It uses the Supabase JS client for auth operations and stores the access token
 * for API calls.
 */

// Supabase config is injected by the template
const SUPABASE_URL = window.__SUPABASE_URL || '';
const SUPABASE_ANON_KEY = window.__SUPABASE_ANON_KEY || '';

let supabaseClient = null;
let supabaseAccessToken = null;
let initPromise = null;
let bridgedToken = null;

function persistAccessCookie(token) {
  if (!token) return;
  const secure = window.location.protocol === 'https:' ? '; Secure' : '';
  document.cookie = `ovc_access_token=${encodeURIComponent(token)}; Path=/; SameSite=Lax${secure}`;
}

function clearAccessCookie() {
  const secure = window.location.protocol === 'https:' ? '; Secure' : '';
  document.cookie = `ovc_access_token=; Path=/; Max-Age=0; SameSite=Lax${secure}`;
  bridgedToken = null;
}

async function bridgeBackendSession(token) {
  if (!token || token === bridgedToken) {
    return true;
  }
  try {
    const response = await fetch('/auth/supabase/session', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });
    if (!response.ok) {
      const text = await response.text();
      console.warn('[Supabase] Backend session bridge failed:', response.status, text);
      return false;
    }
    bridgedToken = token;
    return true;
  } catch (error) {
    console.warn('[Supabase] Backend session bridge request failed:', error);
    return false;
  }
}

/**
 * Initialize Supabase client.
 */
function initSupabase() {
  if (initPromise) {
    return initPromise;
  }

  initPromise = (async () => {
  if (!SUPABASE_URL || !SUPABASE_ANON_KEY) {
    console.warn('[Supabase] Not configured');
    return false;
  }
  
  if (typeof supabase === 'undefined') {
    console.error('[Supabase] supabase-js library not loaded');
    return false;
  }
  
  supabaseClient = supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
  
  // Listen for auth state changes
  supabaseClient.auth.onAuthStateChange((event, session) => {
    if (session?.access_token) {
      supabaseAccessToken = session.access_token;
      persistAccessCookie(supabaseAccessToken);
      bridgeBackendSession(supabaseAccessToken);
    } else {
      supabaseAccessToken = null;
      clearAccessCookie();
    }
    window.dispatchEvent(new CustomEvent('ovc:supabase-auth', {
      detail: { event, hasSession: Boolean(session?.access_token) },
    }));
  });
  
  // Check for existing session
  const { data: { session } } = await supabaseClient.auth.getSession();
  if (session?.access_token) {
    supabaseAccessToken = session.access_token;
    persistAccessCookie(supabaseAccessToken);
    await bridgeBackendSession(supabaseAccessToken);
  }
  
  return true;
  })();

  return initPromise;
}

/**
 * Sign up with email and password via Supabase.
 */
async function supabaseSignUp(email, password) {
  await initSupabase();
  if (!supabaseClient) {
    throw new Error('Supabase not initialized');
  }
  
  const { data, error } = await supabaseClient.auth.signUp({
    email,
    password,
  });
  
  if (error) {
    console.error('[Supabase] Sign up error:', error);
    throw new Error(error.message);
  }
  
  return data;
}

/**
 * Sign in with email and password via Supabase.
 */
async function supabaseSignIn(email, password) {
  await initSupabase();
  if (!supabaseClient) {
    throw new Error('Supabase not initialized');
  }
  
  const { data, error } = await supabaseClient.auth.signInWithPassword({
    email,
    password,
  });
  
  if (error) {
    console.error('[Supabase] Sign in error:', error);
    throw new Error(error.message);
  }
  
  if (data.session?.access_token) {
    supabaseAccessToken = data.session.access_token;
    persistAccessCookie(supabaseAccessToken);
    await bridgeBackendSession(supabaseAccessToken);
  }
  return data;
}

/**
 * Sign out from Supabase.
 */
async function supabaseSignOut() {
  await initSupabase();
  if (!supabaseClient) {
    return;
  }
  
  const { error } = await supabaseClient.auth.signOut();
  if (error) {
    console.error('[Supabase] Sign out error:', error);
  }
  
  supabaseAccessToken = null;
  clearAccessCookie();
}

/**
 * Get current Supabase access token.
 */
function getSupabaseAccessToken() {
  return supabaseAccessToken;
}

/**
 * Refresh Supabase session.
 */
async function refreshSupabaseSession() {
  await initSupabase();
  if (!supabaseClient) {
    return null;
  }
  
  const { data, error } = await supabaseClient.auth.refreshSession();
  if (error) {
    console.error('[Supabase] Session refresh error:', error);
    return null;
  }
  
  if (data.session?.access_token) {
    supabaseAccessToken = data.session.access_token;
    persistAccessCookie(supabaseAccessToken);
    await bridgeBackendSession(supabaseAccessToken);
  }
  
  return supabaseAccessToken;
}

// Export to window for use in templates
window.supabaseAuth = {
  init: initSupabase,
  signUp: supabaseSignUp,
  signIn: supabaseSignIn,
  signOut: supabaseSignOut,
  getAccessToken: getSupabaseAccessToken,
  refreshSession: refreshSupabaseSession,
};

// Auto-initialize if config is present
document.addEventListener('DOMContentLoaded', () => {
  if (SUPABASE_URL && SUPABASE_ANON_KEY) {
    initSupabase();
  }
});
