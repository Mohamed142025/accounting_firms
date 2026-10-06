// Runs on every page (the ERPNext site among them).
// Receives the login payload that customer.js posts when the user clicks "فتح المنصة"
// and forwards it to the background worker, which attaches it to the portal tab.
(() => {
  // let the ERPNext page know the extension is installed
  document.documentElement.dataset.accountingFirmsExtension = chrome.runtime.getManifest().version;

  window.addEventListener("message", (event) => {
    if (event.source !== window) return;
    const data = event.data;
    if (!data || data.type !== "ACCOUNTING_FIRMS_AUTOLOGIN" || !data.payload) return;
    chrome.runtime.sendMessage({ type: "AUTOLOGIN_PAYLOAD", payload: data.payload });
  });
})();
