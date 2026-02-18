const isDesktop = Boolean(window.__TAURI__);

function setConnectivityState() {
  document.documentElement.dataset.connectivity = navigator.onLine ? 'online' : 'offline';
}

async function syncNow() {
  const response = await fetch('/api/sync/trigger', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

async function getSyncStatus() {
  const response = await fetch('/api/sync/status');
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

window.__OVC_DESKTOP_ADAPTER = {
  enabled: isDesktop,
  syncNow,
  getSyncStatus,
};

window.__DESKTOP_MODE = isDesktop || window.__DESKTOP_MODE === true;

window.addEventListener('online', setConnectivityState);
window.addEventListener('offline', setConnectivityState);
setConnectivityState();
