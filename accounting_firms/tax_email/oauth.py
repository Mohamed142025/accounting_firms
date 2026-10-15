"""OAuth (XOAUTH2) sign-in for tax mailboxes on Gmail / Microsoft 365.

The provider's client (client id / secret, authorization and token URLs, scopes) is a
Frappe Connected App. Each mailbox row keeps its own refresh token, so one Connected App
serves any number of customers' mailboxes; Frappe's own Token Cache keeps one token per
user, which does not fit here.

The provider must have this app's redirect URI (`redirect_uri()`) registered. Scopes:
Google `https://mail.google.com/`; Microsoft `https://outlook.office.com/IMAP.AccessAsUser.All`
and `offline_access`.
"""

import os
from urllib.parse import quote

import frappe
import requests
from frappe import _
from frappe.utils import cint
from frappe.utils.password import get_decrypted_password, set_encrypted_password
from requests_oauthlib import OAuth2Session

os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

CALLBACK = "accounting_firms.tax_email.oauth.callback"
TOKEN_FIELD = "oauth_refresh_token"
STATE_TTL = 15 * 60


class OAuthError(Exception):
    pass


def redirect_uri():
    return frappe.utils.get_url(f"/api/method/{CALLBACK}")


def _state_key(state):
    return f"tax_email_oauth_state:{state}"


def _access_key(row_name):
    return f"tax_email_oauth_access:{row_name}"


def has_refresh_token(row_name):
    return bool(
        frappe.db.sql(
            "select 1 from `__Auth` where doctype=%s and name=%s and fieldname=%s and ifnull(password, '') != ''",
            ("Tax Email Configuration", row_name, TOKEN_FIELD),
        )
    )


def _app(name):
    if not name:
        frappe.throw(_("اختار Connected App لصف الإيميل."))
    app = frappe.get_doc("Connected App", name)
    if not (app.client_id and app.authorization_uri and app.token_uri):
        frappe.throw(_("الـ Connected App {0} ناقص: Client ID وAuthorization URI وToken URI مطلوبين.").format(frappe.bold(name)))
    return app


@frappe.whitelist()
def authorize(name, parent):
    """Authorization URL for a mailbox row; the provider sends the user back to `callback`."""
    from accounting_firms.tax_email.fetch import OAUTH, check_customer, get_row

    check_customer(parent)
    row = get_row(name, parent)
    if row.auth_method != OAUTH:
        frappe.throw(_("طريقة الدخول للصف ده مش OAuth. احفظ العميل بعد ما تغيرها."))
    app = _app(row.connected_app)

    session = OAuth2Session(app.client_id, redirect_uri=redirect_uri(), scope=app.get_scopes())
    params = app.get_query_params()
    params.setdefault("login_hint", row.tax_email)
    if "google" in (app.authorization_uri or "").lower():
        # a refresh token is only given with offline access, and again only on consent
        params.setdefault("access_type", "offline")
        params.setdefault("prompt", "consent")
    url, state = session.authorization_url(app.authorization_uri, **params)
    frappe.cache.set_value(
        _state_key(state), {"row": row.name, "parent": parent, "user": frappe.session.user}, expires_in_sec=STATE_TTL
    )
    return url


@frappe.whitelist(methods=["GET"], allow_guest=True)
def callback(code=None, state=None, error=None, error_description=None, **kwargs):
    if frappe.session.user == "Guest":
        frappe.local.response["type"] = "redirect"
        frappe.local.response["location"] = "/login?redirect-to=" + quote(frappe.request.full_path)
        return

    data = frappe.cache.get_value(_state_key(state)) if state else None
    if not data or data.get("user") != frappe.session.user:
        frappe.throw(_("رابط الربط انتهى أو غير صحيح. ارجع لشاشة العميل واضغط «ربط حساب OAuth» تاني."), title=_("OAuth"))
    frappe.cache.delete_value(_state_key(state))
    if error:
        frappe.throw(_("المزود رفض الربط: {0}").format(error_description or error), title=_("OAuth"))

    from accounting_firms.tax_email.fetch import check_customer, get_row

    check_customer(data["parent"])
    row = get_row(data["row"], data["parent"])
    app = _app(row.connected_app)
    session = OAuth2Session(app.client_id, redirect_uri=redirect_uri(), scope=app.get_scopes(), state=state)
    token = session.fetch_token(
        app.token_uri,
        code=code,
        client_secret=app.get_password("client_secret", raise_exception=False),
        include_client_id=True,
    )
    if not token.get("refresh_token"):
        frappe.throw(
            _("المزود ما رجّعش Refresh Token. في Microsoft أضف الـ scope «offline_access»، وفي Google شيل صلاحية التطبيق من الحساب وجرّب تاني."),
            title=_("OAuth"),
        )
    store_token(row.name, token)
    # a mailbox that failed before linking is read on the next run, not after the back-off
    frappe.db.set_value(
        "Tax Mailbox Sync", {"name": row.name, "status": "Failed"}, {"status": "Never", "consecutive_failures": 0}
    )
    frappe.db.commit()

    frappe.local.response["type"] = "redirect"
    frappe.local.response["location"] = f"/app/customer/{quote(row.parent)}?oauth=linked"


def store_token(row_name, token):
    if token.get("refresh_token"):
        set_encrypted_password("Tax Email Configuration", row_name, token["refresh_token"], TOKEN_FIELD)
    if token.get("access_token"):
        frappe.cache.set_value(
            _access_key(row_name), token["access_token"], expires_in_sec=max(cint(token.get("expires_in") or 3600) - 120, 60)
        )


def forget_access_token(row_name):
    frappe.cache.delete_value(_access_key(row_name))


def get_access_token(row):
    """A valid access token for the row, refreshed from its refresh token when needed."""
    cached = frappe.cache.get_value(_access_key(row.name))
    if cached:
        return cached
    refresh = get_decrypted_password("Tax Email Configuration", row.name, TOKEN_FIELD, raise_exception=False)
    if not refresh:
        raise OAuthError(_("حساب OAuth غير مربوط. اضغط «ربط حساب OAuth» في صف الإيميل."))
    app = _app(row.connected_app)
    response = requests.post(
        app.token_uri,
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh,
            "client_id": app.client_id,
            "client_secret": app.get_password("client_secret", raise_exception=False) or "",
        },
        timeout=30,
    )
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if not response.ok or not payload.get("access_token"):
        reason = payload.get("error_description") or payload.get("error") or response.text[:200]
        raise OAuthError(_("تجديد صلاحية OAuth فشل، اربط الحساب تاني: {0}").format(reason))
    store_token(row.name, payload)
    return payload["access_token"]


def xoauth2(email, access_token):
    return f"user={email}\x01auth=Bearer {access_token}\x01\x01".encode()
