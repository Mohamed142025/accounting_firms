frappe.ui.form.on("Tax Notification Rule", {
  refresh(frm) {
    frm.add_custom_button(__("جرّب القاعدة"), () => testRule(frm));
  },
});

function testRule(frm) {
  frappe
    .call({
      method: "accounting_firms.tax_email.rules.test_rule",
      args: { rule: frm.doc },
      freeze: true,
      freeze_message: __("جاري تجربة القاعدة على الإشعارات..."),
    })
    .then(({ message }) => {
      const esc = frappe.utils.escape_html;
      const rows = (message.rows || [])
        .map(
          (r) => `<tr>
            <td><a href="/app/tax-notification/${encodeURIComponent(r.name)}" target="_blank">${esc(r.name)}</a></td>
            <td>${esc(r.subject || "")}</td>
            <td>${esc(r.customer || "")}</td>
            <td>${r.received_at ? frappe.datetime.str_to_user(r.received_at) : ""}</td>
            <td>${esc(r.current_rule || "—")}</td>
            <td>${r.decides ? `<span class="indicator-pill green">${__("القاعدة دي")}</span>` : esc(r.deciding_rule || "")}</td>
          </tr>`,
        )
        .join("");
      const summary = __("اتجربت على آخر {0} إشعار: القاعدة بتنطبق على {1}، وهي اللي بتحدد التصنيف في {2} منهم.", [
        message.checked,
        message.matched,
        message.deciding,
      ]);
      const note = frm.is_dirty() ? `<p class="text-muted">${__("التجربة على القيم المكتوبة دلوقتي، حتى لو لسه ما اتحفظتش.")}</p>` : "";
      const table = rows
        ? `<div style="max-height:60vh;overflow:auto"><table class="table table-bordered table-sm">
            <thead><tr><th>${__("الإشعار")}</th><th>${__("العنوان")}</th><th>${__("العميل")}</th><th>${__("تاريخ الاستلام")}</th>
            <th>${__("القاعدة الحالية")}</th><th>${__("القاعدة اللي هتحدد")}</th></tr></thead><tbody>${rows}</tbody></table></div>`
        : `<p>${__("مفيش إشعارات بتنطبق عليها القاعدة.")}</p>`;
      const dialog = new frappe.ui.Dialog({ title: __("تجربة القاعدة"), size: "extra-large" });
      dialog.$body.html(`<p>${summary}</p>${note}${table}`);
      dialog.show();
    });
}
