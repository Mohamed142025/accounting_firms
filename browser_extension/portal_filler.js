// Runs on every page. Asks the background worker whether credentials are waiting
// for this tab; if so, fills the login form (selectors from the Tax Platform record,
// otherwise heuristics) and optionally submits it.
(() => {
  if (window.__accountingFirmsFillerLoaded) return;
  window.__accountingFirmsFillerLoaded = true;

  const WAIT_FOR_PAYLOAD_MS = 20000;
  const WAIT_FOR_FIELDS_MS = 45000;
  const POLL_MS = 500;

  const isVisible = (el) => {
    if (!el) return false;
    const style = window.getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden") return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };

  const query = (selector) => {
    if (!selector) return null;
    try {
      const el = document.querySelector(selector);
      return isVisible(el) ? el : null;
    } catch (e) {
      return null;
    }
  };

  const findPassword = (selector) =>
    query(selector) || [...document.querySelectorAll('input[type="password"]')].find(isVisible) || null;

  const findUsername = (selector, passwordEl) => {
    const bySelector = query(selector);
    if (bySelector) return bySelector;
    const candidates = [...document.querySelectorAll('input[type="email"], input[type="text"], input[type="tel"], input:not([type])')]
      .filter(isVisible)
      .filter((el) => !/search|captcha|otp|code/i.test(`${el.name} ${el.id} ${el.placeholder}`));
    if (!candidates.length) return null;
    // prefer an input that lives in the same form as the password field
    if (passwordEl?.form) {
      const sameForm = candidates.find((el) => el.form === passwordEl.form);
      if (sameForm) return sameForm;
    }
    const hinted = candidates.find((el) => /user|email|login|mail|tax|rin|name/i.test(`${el.name} ${el.id} ${el.placeholder} ${el.autocomplete}`));
    return hinted || candidates[0];
  };

  const findSubmit = (selector, anchorEl) => {
    const bySelector = query(selector);
    if (bySelector) return bySelector;
    const form = anchorEl?.form;
    const scope = form || document;
    const buttons = [...scope.querySelectorAll('button[type="submit"], input[type="submit"], button')].filter(isVisible);
    return (
      buttons.find((b) => b.type === "submit") ||
      buttons.find((b) => /login|sign in|دخول|تسجيل/i.test(b.textContent || b.value || "")) ||
      null
    );
  };

  // React/Angular keep their own state, so set the value through the native setter and fire events
  const setValue = (el, value) => {
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")?.set;
    el.focus();
    if (setter) setter.call(el, value);
    else el.value = value;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    el.dispatchEvent(new KeyboardEvent("keyup", { bubbles: true }));
  };

  const toast = (text) => {
    const box = document.createElement("div");
    box.textContent = text;
    Object.assign(box.style, {
      position: "fixed", top: "12px", left: "50%", transform: "translateX(-50%)", zIndex: 2147483647,
      background: "#1f6f43", color: "#fff", padding: "8px 16px", borderRadius: "6px",
      font: "14px sans-serif", direction: "rtl", boxShadow: "0 2px 8px rgba(0,0,0,.3)",
    });
    document.body.appendChild(box);
    setTimeout(() => box.remove(), 4000);
  };

  const send = (message) =>
    new Promise((resolve) => {
      try {
        chrome.runtime.sendMessage(message, (response) => resolve(chrome.runtime.lastError ? null : response));
      } catch (e) {
        resolve(null);
      }
    });

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  async function waitForPayload() {
    const deadline = Date.now() + WAIT_FOR_PAYLOAD_MS;
    while (Date.now() < deadline) {
      const payload = await send({ type: "GET_PENDING" });
      if (payload) return payload;
      await sleep(POLL_MS);
    }
    return null;
  }

  async function fill(payload) {
    const deadline = Date.now() + WAIT_FOR_FIELDS_MS;
    let usernameDone = false;
    let passwordDone = false;

    while (Date.now() < deadline && !(usernameDone && passwordDone)) {
      const passwordEl = findPassword(payload.password_selector);
      const usernameEl = findUsername(payload.username_selector, passwordEl);

      if (usernameEl && !usernameDone && payload.username) {
        setValue(usernameEl, payload.username);
        usernameDone = true;
      }
      if (passwordEl && !passwordDone && payload.password) {
        setValue(passwordEl, payload.password);
        passwordDone = true;
      }

      // multi-step logins (username first, password on the next screen)
      if (usernameDone && !passwordEl && !passwordDone) {
        if (payload.auto_submit) {
          const next = findSubmit(payload.submit_selector, usernameEl);
          if (next) {
            next.click();
            return "partial";
          }
        }
        return "partial";
      }

      if (usernameDone && passwordDone) break;
      await sleep(POLL_MS);
    }

    if (!usernameDone && !passwordDone) return "none";

    if (passwordDone && payload.auto_submit) {
      await sleep(300);
      const submit = findSubmit(payload.submit_selector, findPassword(payload.password_selector));
      if (submit) submit.click();
    }
    return passwordDone ? "done" : "partial";
  }

  (async () => {
    const payload = await waitForPayload();
    if (!payload) return;

    const result = await fill(payload);
    if (result === "done") {
      await send({ type: "CLEAR_PENDING" });
      toast("تم ملء بيانات الدخول تلقائيًا");
    } else if (result === "partial") {
      toast("تم ملء اسم المستخدم، في انتظار صفحة كلمة المرور");
      // keep pending so the next page in this tab can fill the password
    } else if (!payload.password) {
      toast("تم فتح المنصة. كلمة المرور غير متاحة لصلاحياتك");
    }
  })();
})();
