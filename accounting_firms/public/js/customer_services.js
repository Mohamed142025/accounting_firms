// Customer services tab: the office services as a tree of item groups, a checkbox on each
// service the customer deals in. Checking adds a row to "office_services" (saved with the
// customer, so the change shows in its history); unchecking removes it.
(function () {
  const esc = frappe.utils.escape_html;
  const TABLE = "office_services";

  class CustomerServices {
    constructor(frm) {
      this.frm = frm;
      this.customer = frm.doc.name;
      this.expanded = new Set();
      this.search = "";
      this.only_checked = false;
      this.$wrapper = frm.fields_dict.services_html.$wrapper;
      this.render_shell();
      this.load();
    }

    render_shell() {
      this.$wrapper.html(`
        <style>
          .af-svc { border: 1px solid var(--border-color); border-radius: var(--border-radius-md); }
          .af-svc-bar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; padding: 8px; border-bottom: 1px solid var(--border-color); }
          .af-svc-bar input[type=search] { max-width: 240px; }
          .af-svc-total { margin-inline-start: auto; color: var(--text-muted); font-size: var(--text-sm); }
          .af-svc-body { max-height: 560px; overflow: auto; padding: 6px 8px; }
          .af-svc ul { list-style: none; margin: 0; padding-inline-start: 22px; }
          .af-svc-body > ul { padding-inline-start: 0; }
          .af-svc-row { display: flex; align-items: center; gap: 8px; padding: 4px 6px; border-radius: 4px; min-height: 30px; }
          .af-svc-row:hover { background: var(--bg-light-gray); }
          .af-svc-row.group { font-weight: 600; }
          .af-svc-caret { width: 16px; text-align: center; cursor: pointer; color: var(--text-muted); flex: none; }
          .af-svc-row input[type=checkbox] { margin: 0; flex: none; }
          .af-svc-label { cursor: pointer; }
          .af-svc-row.service.checked .af-svc-label { color: var(--text-color); }
          .af-svc-row.service:not(.checked) .af-svc-label { color: var(--text-muted); }
          .af-svc-row.paused .af-svc-label { text-decoration: line-through; }
          .af-svc-count { font-size: 11px; color: var(--text-muted); font-weight: normal; }
          .af-svc-meta { margin-inline-start: auto; display: flex; gap: 6px; align-items: center; font-size: 11px; color: var(--text-muted); }
          .af-svc-empty { padding: 24px; text-align: center; color: var(--text-muted); }
        </style>
        <div class="af-svc">
          <div class="af-svc-bar">
            <input type="search" class="form-control input-xs" placeholder="${__("بحث في الخدمات...")}">
            <div class="btn-group btn-group-sm" role="group">
              <button class="btn btn-default btn-xs af-svc-filter active" data-only="0">${__("الكل")}</button>
              <button class="btn btn-default btn-xs af-svc-filter" data-only="1">${__("المتعلّم فقط")}</button>
            </div>
            <button class="btn btn-default btn-xs af-svc-expand">${__("فتح الكل")}</button>
            <button class="btn btn-default btn-xs af-svc-collapse">${__("طي الكل")}</button>
            <span class="af-svc-total"></span>
          </div>
          <div class="af-svc-body"></div>
        </div>`);
      this.$body = this.$wrapper.find(".af-svc-body");
      this.$total = this.$wrapper.find(".af-svc-total");
      this.$wrapper.find("input[type=search]").on("input", frappe.utils.debounce((e) => {
        this.search = (e.target.value || "").trim().toLowerCase();
        this.render();
      }, 200));
      this.$wrapper.find(".af-svc-filter").on("click", (e) => {
        this.only_checked = $(e.currentTarget).data("only") == 1;
        this.$wrapper.find(".af-svc-filter").removeClass("active");
        $(e.currentTarget).addClass("active");
        this.render();
      });
      this.$wrapper.find(".af-svc-expand").on("click", () => {
        this.groups.forEach((g) => this.expanded.add(g.name));
        this.render();
      });
      this.$wrapper.find(".af-svc-collapse").on("click", () => {
        this.expanded.clear();
        this.render();
      });
    }

    async load() {
      const data = await frappe.xcall("accounting_firms.office_services.api.get_service_tree", {
        customer: this.frm.is_new() ? null : this.frm.doc.name,
      });
      this.groups = data.groups;
      this.services = data.services;
      this.stats = data.stats || {};
      this.children = {};
      this.groups.forEach((g) => (this.children[g.parent || ""] ||= []).push(g));
      this.services_of = {};
      this.services.forEach((s) => (this.services_of[s.item_group] ||= []).push(s));
      // the first time: the top levels open, and every group holding a checked service
      if (!this.loaded_once) {
        (this.children[""] || []).forEach((g) => {
          this.expanded.add(g.name);
          (this.children[g.name] || []).forEach((c) => this.expanded.add(c.name));
        });
        const parent_of = {};
        this.groups.forEach((g) => (parent_of[g.name] = g.parent));
        const checked = this.rows();
        this.services.filter((s) => checked[s.name]).forEach((s) => {
          for (let g = s.item_group; g; g = parent_of[g]) this.expanded.add(g);
        });
      }
      this.loaded_once = true;
      this.render();
    }

    rows() {
      const map = {};
      (this.frm.doc[TABLE] || []).forEach((r) => r.service && (map[r.service] = r));
      return map;
    }

    can_edit() {
      return !!this.frm.perm?.[0]?.write;
    }

    // every service under a group, nested groups included
    all_services(group) {
      const out = [...(this.services_of[group] || [])];
      (this.children[group] || []).forEach((g) => out.push(...this.all_services(g.name)));
      return out;
    }

    matches(service) {
      if (this.only_checked && !this.checked[service.name]) return false;
      if (!this.search) return true;
      return `${service.item_name} ${service.name}`.toLowerCase().includes(this.search);
    }

    render() {
      if (!this.groups) return;
      this.checked = this.rows();
      const total = Object.keys(this.checked).length;
      this.$total.text(__("{0} خدمة متعلّم عليها", [total]));
      const filtering = this.search || this.only_checked;
      const html = this.render_level("", filtering);
      this.$body.html(html || `<div class="af-svc-empty">${filtering ? __("مفيش خدمات مطابقة.") : __("مفيش خدمات مكتب. علّم «خدمة مكتب» في شاشة الصنف.")}</div>`);
      this.bind();
    }

    render_level(parent, filtering) {
      const items = [];
      (this.children[parent] || []).forEach((g) => {
        const all = this.all_services(g.name);
        const visible = all.filter((s) => this.matches(s));
        if (!visible.length) return;
        const done = all.filter((s) => this.checked[s.name]).length;
        const open = filtering || this.expanded.has(g.name);
        items.push(`<li>
          <div class="af-svc-row group" data-group="${esc(g.name)}">
            <span class="af-svc-caret">${open ? "▾" : "▸"}</span>
            <input type="checkbox" class="af-svc-group-check" ${done && done === all.length ? "checked" : ""} ${this.can_edit() ? "" : "disabled"}
              data-indeterminate="${done && done < all.length ? 1 : 0}">
            <span class="af-svc-label af-svc-toggle">${esc(g.name)}</span>
            <span class="af-svc-count">(${done}/${all.length})</span>
          </div>
          ${open ? `<ul>${this.render_level(g.name, filtering)}${this.render_services(g.name)}</ul>` : ""}
        </li>`);
      });
      return items.length ? (parent ? items.join("") : `<ul>${items.join("")}</ul>`) : "";
    }

    render_services(group) {
      return (this.services_of[group] || [])
        .filter((s) => this.matches(s))
        .map((s) => {
          const row = this.checked[s.name];
          const stat = this.stats[s.name] || {};
          const meta = [];
          if (row?.recurrence && row.recurrence !== "مرة واحدة") meta.push(esc(__(row.recurrence)));
          if (stat.open) meta.push(`<span class="indicator-pill orange">${__("{0} مفتوحة", [stat.open])}</span>`);
          if (stat.last_done) meta.push(__("آخر تنفيذ {0}", [frappe.datetime.str_to_user(stat.last_done)]));
          if (row && row.status !== "موقوفة" && !this.frm.is_new() && typeof window.af_new_service_task === "function") {
            meta.push(`<button class="btn btn-xs btn-default af-svc-task" data-service="${esc(s.name)}">+ ${__("مهمة")}</button>`);
          }
          return `<li><div class="af-svc-row service ${row ? "checked" : ""} ${row?.status === "موقوفة" ? "paused" : ""}" data-service="${esc(s.name)}">
            <span class="af-svc-caret"></span>
            <input type="checkbox" class="af-svc-check" ${row ? "checked" : ""} ${this.can_edit() ? "" : "disabled"}>
            <span class="af-svc-label af-svc-open" title="${esc(s.name)}">${esc(s.item_name)}</span>
            <span class="af-svc-meta">${meta.join(" ")}</span>
          </div></li>`;
        })
        .join("");
    }

    bind() {
      this.$body.find(".af-svc-group-check").each((_i, el) => {
        el.indeterminate = el.dataset.indeterminate === "1";
      });
      this.$body.find(".af-svc-toggle, .af-svc-row.group .af-svc-caret").on("click", (e) => {
        const g = $(e.currentTarget).closest(".af-svc-row").data("group");
        this.expanded.has(g) ? this.expanded.delete(g) : this.expanded.add(g);
        this.render();
      });
      this.$body.find(".af-svc-check").on("change", (e) => {
        const service = $(e.currentTarget).closest(".af-svc-row").data("service");
        this.set_checked([this.services.find((s) => s.name == service)], e.currentTarget.checked);
      });
      this.$body.find(".af-svc-group-check").on("change", (e) => {
        const g = $(e.currentTarget).closest(".af-svc-row").data("group");
        this.set_checked(this.all_services(g), e.currentTarget.checked);
      });
      this.$body.find(".af-svc-open").on("click", (e) => {
        const service = $(e.currentTarget).closest(".af-svc-row").data("service");
        const row = this.checked[service];
        if (row) this.frm.fields_dict[TABLE].grid.grid_rows_by_docname[row.name]?.show_form();
      });
      this.$body.find(".af-svc-task").on("click", (e) => {
        e.stopPropagation();
        window.af_new_service_task(this.frm, $(e.currentTarget).data("service"));
      });
    }

    set_checked(services, on) {
      if (!this.can_edit()) return;
      const current = this.rows();
      if (on) {
        services.filter((s) => !current[s.name]).forEach((s) => {
          const row = this.frm.add_child(TABLE);
          Object.assign(row, { service: s.name, service_name: s.item_name, service_group: s.item_group });
        });
      } else {
        const remove = new Set(services.map((s) => s.name));
        const open = services.filter((s) => (this.stats[s.name] || {}).open).map((s) => s.item_name);
        if (open.length) {
          frappe.show_alert({ message: __("خدمات عليها مهام مفتوحة اتشالت من العميل: {0}", [open.join("، ")]), indicator: "orange" }, 7);
        }
        this.frm.doc[TABLE] = (this.frm.doc[TABLE] || []).filter((r) => !remove.has(r.service));
        this.frm.doc[TABLE].forEach((r, i) => (r.idx = i + 1));
      }
      this.frm.refresh_field(TABLE);
      this.frm.dirty();
      this.render();
    }
  }

  frappe.ui.form.on("Customer", {
    refresh(frm) {
      if (!frm.fields_dict.services_html) return;
      // same customer after a save: keep the open groups, search and filter
      const current = frm.af_services;
      if (current && current.customer === frm.doc.name && current.$wrapper.find(".af-svc").length) {
        current.load();
        return;
      }
      frm.af_services = new CustomerServices(frm);
    },
    office_services_remove(frm) {
      frm.af_services?.render();
    },
  });

  frappe.ui.form.on("Customer Office Service", {
    service(frm) {
      frm.af_services?.render();
    },
    status(frm) {
      frm.af_services?.render();
    },
    recurrence(frm) {
      frm.af_services?.render();
    },
  });
})();
