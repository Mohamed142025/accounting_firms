// Keeps the credentials that should be filled in a portal tab.
// State lives in chrome.storage.session so it survives service-worker restarts
// and is wiped when the browser closes.
const PENDING_TTL_MS = 3 * 60 * 1000;

const log = (...args) => console.log("[AF AutoLogin/bg]", ...args);

async function getState() {
  const { pending = {}, lastStatus = null } = await chrome.storage.session.get(["pending", "lastStatus"]);
  const now = Date.now();
  for (const key of Object.keys(pending)) {
    if (now - pending[key].created > PENDING_TTL_MS) delete pending[key];
  }
  return { pending, lastStatus };
}

async function setStatus(text) {
  await chrome.storage.session.set({ lastStatus: { text, at: new Date().toLocaleTimeString() } });
  log(text);
}

function hostOf(url) {
  try {
    return new URL(url).hostname;
  } catch (e) {
    return "";
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
  (async () => {
    const { pending } = await getState();

    if (message.type === "AUTOLOGIN_PAYLOAD") {
      const payload = message.payload;
      let tab = sender.tab ? await findPortalTab(sender.tab.id) : null;
      if (!tab && payload.login_url) {
        tab = await chrome.tabs.create({ url: payload.login_url, active: true });
      }
      const item = { payload, created: Date.now(), tabId: tab ? tab.id : null, host: hostOf(payload.login_url) };
      if (tab) pending[`tab:${tab.id}`] = item;
      if (item.host) pending[`host:${item.host}`] = item;
      await chrome.storage.session.set({ pending });
      await setStatus(`استلمت بيانات ${payload.platform} (مستخدم: ${payload.username || "-"}, كلمة مرور: ${payload.password ? "نعم" : "لا"}) للتاب ${tab ? tab.id : "?"}`);
      sendResponse({ ok: Boolean(tab) });
      return;
    }

    if (message.type === "GET_PENDING") {
      const tabId = sender.tab ? sender.tab.id : null;
      const host = hostOf(sender.url || sender.tab?.url || "");
      const item = pending[`tab:${tabId}`] || pending[`host:${host}`] || null;
      sendResponse(item ? item.payload : null);
      return;
    }

    if (message.type === "CLEAR_PENDING") {
      const tabId = sender.tab ? sender.tab.id : null;
      const item = pending[`tab:${tabId}`];
      delete pending[`tab:${tabId}`];
      if (item?.host) delete pending[`host:${item.host}`];
      await chrome.storage.session.set({ pending });
      sendResponse({ ok: true });
      return;
    }

    if (message.type === "STATUS") {
      await setStatus(message.text);
      sendResponse({ ok: true });
      return;
    }

    sendResponse(null);
  })();
  return true;
});

chrome.runtime.onInstalled.addListener(() => setStatus("تم تسطيب الإضافة. أعد تحميل صفحة ERPNext."));
