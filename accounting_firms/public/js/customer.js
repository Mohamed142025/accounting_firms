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
