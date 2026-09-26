const isDesktop = Boolean(window.__TAURI__);
const syncIndicatorEl = document.getElementById('sync-status-indicator');
let syncInFlight = false;

function setConnectivityState() {
  document.documentElement.dataset.connectivity = navigator.onLine ? 'online' : 'offline';
}

function setSyncIndicator(text, state = 'idle') {
  if (!syncIndicatorEl) return;
  syncIndicatorEl.textContent = text;
  syncIndicatorEl.dataset.state = state;
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

async function refreshSyncIndicator() {
  if (!isDesktop) {
    setSyncIndicator('');
    return;
  }
  if (!navigator.onLine) {
    setSyncIndicator('Sync: нет сети', 'offline');
    return;
  }
  try {
    const status = await getSyncStatus();
    if (!status.enabled || !status.remoteConfigured) {
      setSyncIndicator('Sync: не подключен', 'disconnected');
      return;
    }
    if (status.authRequired) {
      setSyncIndicator('Sync: требуется повторный вход', 'error');
      return;
    }
    if (status.failed > 0) {
      setSyncIndicator(`Sync: ошибка (${status.failed})`, 'error');
      return;
    }
    if (status.lastError) {
      setSyncIndicator('Sync: ошибка соединения или конфигурации', 'error');
      return;
    }
    if (status.relationConflicts > 0) {
      setSyncIndicator(`Sync: конфликты связей (${status.relationConflicts})`, 'error');
      return;
    }
    if (status.pending > 0) {
      setSyncIndicator(`Sync: в очереди ${status.pending}`, 'pending');
      return;
    }
    if (status.conflicts > 0) {
      setSyncIndicator(`Sync: сохранены копии конфликтов (${status.conflicts})`, 'error');
      return;
    }
    if (status.quarantinedLegacy > 0) {
      setSyncIndicator(`Sync: старая очередь изолирована (${status.quarantinedLegacy})`, 'pending');
      return;
    }
    setSyncIndicator('Sync: подключен', 'connected');
  } catch (_) {
    setSyncIndicator('Sync: ошибка', 'error');
  }
}

async function runSyncCycle() {
  if (!isDesktop) {
    setSyncIndicator('');
    return;
  }
  if (!navigator.onLine) {
    setSyncIndicator('Sync: нет сети', 'offline');
    return;
  }
  if (!syncInFlight) {
    syncInFlight = true;
    try {
      await syncNow();
    } catch (_) {
      // status renderer below will show error state
    } finally {
      syncInFlight = false;
    }
  }
  await refreshSyncIndicator();
}

window.__OVC_DESKTOP_ADAPTER = {
  enabled: isDesktop,
  syncNow,
  getSyncStatus,
  refreshSyncIndicator,
};

window.__DESKTOP_MODE = isDesktop || window.__DESKTOP_MODE === true;

window.addEventListener('online', setConnectivityState);
window.addEventListener('offline', setConnectivityState);
setConnectivityState();
runSyncCycle();
if (isDesktop) {
  window.setInterval(runSyncCycle, 15000);
}
