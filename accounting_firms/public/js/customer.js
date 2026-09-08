frappe.ui.form.on('Customer', {
	refresh: function (frm) {
		const is_new = frm.is_new();
		frm.set_df_property('custom_custom_number', 'read_only', !is_new);
		frm.refresh_field('custom_custom_number');
	},
	before_save: function (frm) {
		if (!frm.is_new() && !frm.doc.custom_custom_number) {
			frappe.throw(__('custom_custom_number is required.'));
		}
	}
});

frappe.ui.form.on('Tax Email', {
	show_password(frm, cdt, cdn) {
		const grid = frm.grids
			.map((table_field) => table_field.grid)
			.find((table_grid) => table_grid.grid_rows_by_docname?.[cdn]);
		const grid_row = grid?.grid_rows_by_docname?.[cdn];
		const password_field = grid_row?.get_field('email_password');
		const button_field = grid_row?.get_field('show_password');
		const input = password_field?.$input ||
			grid_row?.row?.find('[data-fieldname="email_password"] input');

		if (!input?.length) {
			return;
		}

		const is_visible = input.attr('type') === 'text';
		if (is_visible) {
			input.attr('type', 'password');
			button_field?.set_label(__('Show Password'));
			return;
		}

		frappe.call({
			method: 'accounting_firms.accounting_firms.doctype.tax_email.tax_email.get_password',
			args: { name: cdn },
			btn: button_field?.$input,
			callback: (response) => {
				if (response.message) {
					input.attr('type', 'text').val(response.message);
					button_field?.set_label(__('Hide Password'));
				}
			}
		});
	}
});
