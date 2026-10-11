// Customer archive tab: per-customer folder tree + documents grid.
(function () {
  const API = "accounting_firms.archive.api";
  const call = (method, args) => frappe.xcall(`${API}.${method}`, args);
  const esc = frappe.utils.escape_html;

  class CustomerArchive {
    constructor(frm) {
      this.frm = frm;
      this.customer = frm.doc.name;
      this.selected = null;
      this.expanded = new Set();
      this.search = "";
      this.year = "";
      this.$wrapper = frm.fields_dict.archive_html.$wrapper;
      this.render_shell();
      this.refresh();
    }

    render_shell() {
      this.$wrapper.html(`
        <style>
          .af-archive { display: flex; gap: 12px; min-height: 420px; }
          .af-tree { flex: 0 0 300px; border: 1px solid var(--border-color); border-radius: var(--border-radius-md); padding: 8px; overflow: auto; max-height: 600px; }
          .af-files { flex: 1; min-width: 0; }
          .af-tree ul { list-style: none; padding-right: 16px; margin: 0; }
          .af-tree > ul { padding-right: 0; }
          .af-node { display: flex; align-items: center; gap: 6px; padding: 3px 6px; border-radius: 4px; cursor: pointer; white-space: nowrap; }
          .af-node:hover { background: var(--bg-light-gray); }
          .af-node.selected { background: var(--primary-color); color: #fff; }
          .af-node .af-caret { width: 14px; display: inline-block; text-align: center; color: var(--text-muted); }
          .af-node.selected .af-caret, .af-node.selected .af-count { color: #fff; }
          .af-count { font-size: 11px; color: var(--text-muted); margin-right: auto; }
          .af-toolbar { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; align-items: center; }
          .af-toolbar input { max-width: 180px; }
          .af-table { width: 100%; }
          .af-table th, .af-table td { padding: 6px 8px; border-bottom: 1px solid var(--border-color); vertical-align: middle; }
          .af-table tbody tr:hover { background: var(--bg-light-gray); }
          .af-empty { padding: 24px; text-align: center; color: var(--text-muted); }
          .af-path { font-size: 12px; color: var(--text-muted); margin-bottom: 6px; }
          @media (max-width: 768px) { .af-archive { flex-direction: column; } .af-tree { flex-basis: auto; } }
        </style>
        <div class="af-archive">
          <div class="af-tree"><div class="af-tree-actions"></div><div class="af-tree-body"></div></div>
          <div class="af-files">
            <div class="af-toolbar"></div>
            <div class="af-path"></div>
            <div class="af-table-wrapper"></div>
          </div>
        </div>`);
      this.$tree = this.$wrapper.find(".af-tree-body");
      this.$tree_actions = this.$wrapper.find(".af-tree-actions");
      this.$toolbar = this.$wrapper.find(".af-toolbar");
      this.$path = this.$wrapper.find(".af-path");
      this.$table = this.$wrapper.find(".af-table-wrapper");
    }

    async refresh() {
      this.tree = await call("get_tree", { customer: this.customer });
      this.by_name = {};
      this.tree.folders.forEach((f) => (this.by_name[f.name] = f));
      if (!this.selected || !this.by_name[this.selected]) {
        this.selected = (this.tree.folders.find((f) => f.is_root) || {}).name;
        if (this.selected) this.expanded.add(this.selected);
      }
      this.render_tree();
      this.render_toolbar();
      await this.load_files();
    }

    children(parent) {
      return this.tree.folders.filter((f) => f.parent === parent);
    }

    subtree_count(folder) {
      return this.children(folder.name).reduce((sum, c) => sum + this.subtree_count(c), folder.file_count || 0);
    }

    render_tree() {
      const build = (parent) => {
        const items = this.children(parent);
        if (!items.length) return "";
        return `<ul>${items.map((f) => this.node_html(f)).join("")}</ul>`;
      };
      const root = this.tree.folders.find((f) => f.is_root);
      this.$tree.html(root ? `<ul>${this.node_html(root)}</ul>` : `<div class="af-empty">${__("لا يوجد أرشيف")}</div>`);
      this.$tree.find(".af-node").on("click", (e) => {
        const name = $(e.currentTarget).data("name");
        if ($(e.target).hasClass("af-caret")) {
          this.expanded.has(name) ? this.expanded.delete(name) : this.expanded.add(name);
          this.render_tree();
          return;
        }
        this.selected = name;
        this.expanded.add(name);
        this.render_tree();
        this.render_toolbar();
        this.load_files();
      });
      this.$tree_actions.html(`
        <div class="af-toolbar">
          <button class="btn btn-xs btn-default af-new-folder">${frappe.utils.icon("add", "xs")} ${__("مجلد جديد")}</button>
          <button class="btn btn-xs btn-default af-rename-folder">${__("إعادة تسمية")}</button>
          ${this.tree.can_delete ? `<button class="btn btn-xs btn-danger af-delete-folder">${__("حذف المجلد")}</button>` : ""}
          <button class="btn btn-xs btn-default af-apply-template" title="${__("إضافة المجلدات الناقصة من الهيكل الافتراضي")}">${__("الهيكل الافتراضي")}</button>
        </div>`);
      this.$tree_actions.find(".af-new-folder").on("click", () => this.new_folder());
      this.$tree_actions.find(".af-rename-folder").on("click", () => this.rename_folder());
      this.$tree_actions.find(".af-delete-folder").on("click", () => this.delete_folder());
      this.$tree_actions.find(".af-apply-template").on("click", () => this.apply_template());
    }

    node_html(f) {
      const kids = this.children(f.name);
      const open = this.expanded.has(f.name);
      const caret = kids.length ? (open ? "▾" : "◂") : "";
      const count = this.subtree_count(f);
      const selected = f.name === this.selected ? "selected" : "";
      return `<li>
        <div class="af-node ${selected}" data-name="${f.name}">
          <span class="af-caret">${caret}</span>
          <span>${frappe.utils.icon(f.is_root ? "folder-open" : "folder-normal", "sm")}</span>
          <span class="af-label">${esc(f.folder_name)}</span>
          <span class="af-count">${count || ""}</span>
        </div>
        ${kids.length && open ? `<ul>${kids.map((c) => this.node_html(c)).join("")}</ul>` : ""}
      </li>`;
    }

    folder_path(name) {
      const parts = [];
      let cur = this.by_name[name];
      while (cur) {
        parts.unshift(cur.folder_name);
        cur = this.by_name[cur.parent];
      }
      return parts.join(" / ");
    }

    render_toolbar() {
      const can_delete = this.tree.can_delete;
      const years = [""].concat(Array.from({ length: 12 }, (_, i) => new Date().getFullYear() - i));
      this.$toolbar.html(`
        <button class="btn btn-sm btn-primary af-upload">${frappe.utils.icon("upload", "sm")} ${__("رفع ملفات")}</button>
        <button class="btn btn-sm btn-default af-download">${__("تنزيل المحدد")}</button>
        <button class="btn btn-sm btn-default af-move">${__("نقل المحدد")}</button>
        ${can_delete ? `<button class="btn btn-sm btn-danger af-delete">${__("حذف المحدد")}</button>` : ""}
        <select class="form-control input-sm af-year" style="max-width:110px">${years.map((y) => `<option value="${y}" ${String(y) === String(this.year) ? "selected" : ""}>${y || __("كل السنوات")}</option>`).join("")}</select>
        <input class="form-control input-sm af-search" placeholder="${__("بحث بالاسم أو الوصف")}" value="${esc(this.search)}">
        <label class="small text-muted" style="margin:0"><input type="checkbox" class="af-subfolders" ${this.include_subfolders ? "checked" : ""}> ${__("شامل المجلدات الفرعية")}</label>
      `);
      this.$toolbar.find(".af-upload").on("click", () => this.upload());
      this.$toolbar.find(".af-download").on("click", () => this.download());
      this.$toolbar.find(".af-move").on("click", () => this.move());
      this.$toolbar.find(".af-delete").on("click", () => this.delete_files());
      this.$toolbar.find(".af-year").on("change", (e) => { this.year = e.target.value; this.load_files(); });
      this.$toolbar.find(".af-search").on("keyup", frappe.utils.debounce((e) => { this.search = e.target.value; this.load_files(); }, 300));
      this.$toolbar.find(".af-subfolders").on("change", (e) => { this.include_subfolders = e.target.checked ? 1 : 0; this.load_files(); });
    }

    async load_files() {
      if (!this.selected) return;
      this.$path.text(this.folder_path(this.selected));
      this.files = await call("get_documents", {
        customer: this.customer, folder: this.selected, year: this.year || null, search: this.search || null, include_subfolders: this.include_subfolders ? 1 : 0,
      });
      if (!this.files.length) {
        this.$table.html(`<div class="af-empty">${__("لا توجد ملفات في هذا المجلد")}</div>`);
        return;
      }
      const rows = this.files.map((d) => `
        <tr data-name="${d.name}">
          <td><input type="checkbox" class="af-check"></td>
          <td><a href="${d.file}" target="_blank" rel="noopener">${frappe.utils.icon(this.file_icon(d.file_name), "sm")} ${esc(d.file_name || d.file)}</a>
              ${this.include_subfolders ? `<div class="small text-muted">${esc(d.folder_name || "")}</div>` : ""}</td>
          <td>${d.document_date ? frappe.datetime.str_to_user(d.document_date) : ""}</td>
          <td>${d.year ? `${d.year}${d.month ? " / " + d.month : ""}` : ""}</td>
          <td>${frappe.form.formatters.FileSize(d.file_size || 0)}</td>
          <td>${esc(d.description || "")}</td>
          <td class="small text-muted">${esc(frappe.user.full_name(d.uploaded_by))}<br>${d.uploaded_on ? frappe.datetime.prettyDate(d.uploaded_on) : ""}</td>
          <td><a class="af-open" href="/app/customer-document/${encodeURIComponent(d.name)}" title="${__("فتح السجل")}">${frappe.utils.icon("edit", "sm")}</a></td>
        </tr>`);
      this.$table.html(`
        <table class="af-table">
          <thead><tr>
            <th><input type="checkbox" class="af-check-all"></th>
            <th>${__("اسم الملف")}</th><th>${__("تاريخ المستند")}</th><th>${__("الفترة")}</th><th>${__("الحجم")}</th><th>${__("الوصف")}</th><th>${__("رفعه")}</th><th></th>
          </tr></thead>
          <tbody>${rows.join("")}</tbody>
        </table>`);
      this.$table.find(".af-check-all").on("change", (e) => this.$table.find(".af-check").prop("checked", e.target.checked));
    }

    file_icon(name) {
      const ext = (name || "").split(".").pop().toLowerCase();
      if (["pdf"].includes(ext)) return "file";
      if (["png", "jpg", "jpeg", "gif", "webp"].includes(ext)) return "image";
      if (["xls", "xlsx", "csv"].includes(ext)) return "list";
      return "file";
    }

    checked() {
      return this.$table.find(".af-check:checked").map((_, el) => $(el).closest("tr").data("name")).get();
    }

    require_checked() {
      const names = this.checked();
      if (!names.length) frappe.msgprint(__("حدد ملفًا واحدًا على الأقل."));
      return names;
    }

    // ---------------------------------------------------------- folder actions
    new_folder() {
      frappe.prompt(
        [{ fieldname: "folder_name", fieldtype: "Data", label: __("اسم المجلد"), reqd: 1 }],
        async ({ folder_name }) => {
          const name = await call("add_folder", { customer: this.customer, parent: this.selected, folder_name });
          this.expanded.add(this.selected);
          this.selected = name;
          this.refresh();
        },
        __("مجلد جديد داخل: {0}", [this.folder_path(this.selected)]),
      );
    }

    rename_folder() {
      const folder = this.by_name[this.selected];
      if (!folder || folder.is_root) return frappe.msgprint(__("اختر مجلدًا غير المجلد الرئيسي."));
      frappe.prompt(
        [{ fieldname: "folder_name", fieldtype: "Data", label: __("اسم المجلد"), reqd: 1, default: folder.folder_name }],
        async ({ folder_name }) => { await call("rename_folder", { name: folder.name, folder_name }); this.refresh(); },
        __("إعادة تسمية"),
      );
    }

    delete_folder() {
      const folder = this.by_name[this.selected];
      if (!folder || folder.is_root) return frappe.msgprint(__("اختر مجلدًا غير المجلد الرئيسي."));
      frappe.confirm(__("حذف المجلد {0}؟ (يجب أن يكون فارغًا)", [esc(folder.folder_name)]), async () => {
        await call("delete_folder", { name: folder.name });
        this.selected = folder.parent;
        this.refresh();
      });
    }

    async apply_template() {
      const created = await call("apply_template", { customer: this.customer });
      frappe.show_alert({ message: __("تمت إضافة {0} مجلد", [created]), indicator: "green" });
      this.refresh();
    }

    // ---------------------------------------------------------- file actions
    upload() {
      const folder = this.by_name[this.selected];
      if (!folder) return;
      const dialog = new frappe.ui.Dialog({
        title: __("رفع ملفات إلى: {0}", [this.folder_path(folder.name)]),
        fields: [
          { fieldname: "year", fieldtype: "Int", label: __("السنة"), default: new Date().getFullYear() },
          { fieldname: "month", fieldtype: "Select", label: __("الشهر"), options: ["", 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12] },
          { fieldtype: "Column Break" },
          { fieldname: "document_date", fieldtype: "Date", label: __("تاريخ المستند") },
          { fieldname: "description", fieldtype: "Small Text", label: __("الوصف (لكل الملفات)") },
          { fieldtype: "Section Break" },
          { fieldname: "uploader", fieldtype: "HTML" },
        ],
      });
      dialog.show();
      let done = 0;
      new frappe.ui.FileUploader({
        wrapper: dialog.fields_dict.uploader.$wrapper,
        doctype: "Customer",
        docname: this.customer,
        allow_multiple: true,
        make_attachments_public: false,
        on_success: async (file_doc) => {
          const v = dialog.get_values(true) || {};
          await call("register_upload", {
            customer: this.customer, folder: folder.name, file_name: file_doc.name,
            year: v.year, month: v.month, document_date: v.document_date, description: v.description,
          });
          done += 1;
          frappe.show_alert({ message: __("تم حفظ {0}", [file_doc.file_name]), indicator: "green" });
          this.refresh();
        },
      });
      dialog.$wrapper.on("hidden.bs.modal", () => { if (done) this.refresh(); });
    }

    download() {
      const names = this.require_checked();
      if (!names.length) return;
      if (names.length === 1) {
        const d = this.files.find((f) => f.name === names[0]);
        window.open(d.file, "_blank");
        return;
      }
      window.open(`/api/method/${API}.download_zip?names=${encodeURIComponent(JSON.stringify(names))}`, "_blank");
    }

    move() {
      const names = this.require_checked();
      if (!names.length) return;
      const options = this.tree.folders.filter((f) => !f.is_root).map((f) => ({ label: this.folder_path(f.name), value: f.name }));
      frappe.prompt(
        [{ fieldname: "folder", fieldtype: "Select", label: __("إلى المجلد"), options, reqd: 1 }],
        async ({ folder }) => {
          const moved = await call("move_documents", { names, folder });
          frappe.show_alert({ message: __("تم نقل {0} ملف", [moved]), indicator: "green" });
          this.refresh();
        },
        __("نقل {0} ملف", [names.length]),
      );
    }

    delete_files() {
      const names = this.require_checked();
      if (!names.length) return;
      frappe.confirm(__("حذف {0} ملف نهائيًا؟", [names.length]), async () => {
        await call("delete_documents", { names });
        this.refresh();
      });
    }
  }

  frappe.ui.form.on("Customer", {
    refresh(frm) {
      if (frm.is_new() || !frm.fields_dict.archive_html) return;
      if (!frm.__archive || frm.__archive.customer !== frm.doc.name) {
        frm.__archive = new CustomerArchive(frm);
      }
    },
  });
})();
