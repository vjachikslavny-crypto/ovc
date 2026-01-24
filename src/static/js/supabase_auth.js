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

/**
 * Initialize Supabase client.
 */
function initSupabase() {
  if (!SUPABASE_URL || !SUPABASE_ANON_KEY) {
    console.warn('[Supabase] Not configured');
    return false;
  }
  
  if (typeof supabase === 'undefined') {
    console.error('[Supabase] supabase-js library not loaded');
    return false;
  }
  
  supabaseClient = supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
  console.log('[Supabase] Client initialized');
  
  // Listen for auth state changes
  supabaseClient.auth.onAuthStateChange((event, session) => {
    console.log('[Supabase] Auth state changed:', event);
    if (session?.access_token) {
      supabaseAccessToken = session.access_token;
      window.__supabaseAccessToken = supabaseAccessToken;
      console.log('[Supabase] Access token updated');
    } else {
      supabaseAccessToken = null;
      window.__supabaseAccessToken = null;
    }
  });
  
  // Check for existing session
  supabaseClient.auth.getSession().then(({ data: { session } }) => {
    if (session?.access_token) {
      supabaseAccessToken = session.access_token;
      window.__supabaseAccessToken = supabaseAccessToken;
      console.log('[Supabase] Existing session found');
    }
  });
  
  return true;
}

/**
 * Sign up with email and password via Supabase.
 */
async function supabaseSignUp(email, password) {
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
  
  console.log('[Supabase] Sign up successful');
  return data;
}

/**
 * Sign in with email and password via Supabase.
 */
async function supabaseSignIn(email, password) {
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
    window.__supabaseAccessToken = supabaseAccessToken;
  }
  
  console.log('[Supabase] Sign in successful');
  return data;
}

/**
 * Sign out from Supabase.
 */
async function supabaseSignOut() {
  if (!supabaseClient) {
    return;
  }
  
  const { error } = await supabaseClient.auth.signOut();
  if (error) {
    console.error('[Supabase] Sign out error:', error);
  }
  
  supabaseAccessToken = null;
  window.__supabaseAccessToken = null;
  console.log('[Supabase] Signed out');
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
    window.__supabaseAccessToken = supabaseAccessToken;
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

