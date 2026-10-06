// Keeps, per portal tab, the credentials that should be filled in that tab.
const PENDING_TTL_MS = 3 * 60 * 1000;
const pending = new Map(); // tabId -> { payload, created }

function cleanup() {
  const now = Date.now();
  for (const [tabId, item] of pending) {
    if (now - item.created > PENDING_TTL_MS) pending.delete(tabId);
  }
}

async function findPortalTab(openerTabId) {
  // customer.js opens the portal with window.open() right before sending the payload,
  // so the newest tab opened by the ERPNext tab is the portal tab.
  const tabs = await chrome.tabs.query({ openerTabId });
  if (!tabs.length) return null;
  return tabs.reduce((latest, tab) => (tab.id > latest.id ? tab : latest));
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  cleanup();

  if (message.type === "AUTOLOGIN_PAYLOAD") {
    (async () => {
      let tab = sender.tab ? await findPortalTab(sender.tab.id) : null;
      if (!tab && message.payload.login_url) {
        // popup was blocked: open the portal ourselves
        tab = await chrome.tabs.create({ url: message.payload.login_url, active: true });
      }
      if (tab) pending.set(tab.id, { payload: message.payload, created: Date.now() });
      sendResponse({ ok: Boolean(tab) });
    })();
    return true;
  }

  if (message.type === "GET_PENDING") {
    const item = sender.tab ? pending.get(sender.tab.id) : null;
    sendResponse(item ? item.payload : null);
    return false;
  }

  if (message.type === "CLEAR_PENDING") {
    if (sender.tab) pending.delete(sender.tab.id);
    sendResponse({ ok: true });
    return false;
  }
});

chrome.tabs.onRemoved.addListener((tabId) => pending.delete(tabId));
