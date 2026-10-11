"""Fresh-install setup.

`bench install-app` marks every patch as completed without running it, so the default
data that the patches create on existing sites (platforms, rules, categories, dashboard,
relation types, trademark classes, archive template, sidebar links) is created here.
All seed functions are idempotent.
"""

import frappe


def after_install():
    from accounting_firms.patches.v1_0 import (
        create_accounting_dashboard,
        create_default_tax_platforms,
        seed_archive_template,
        seed_relation_types_and_trademark_classes,
        seed_tax_notification_defaults,
        seed_tax_notification_rules_v2,
    )

    for patch in (
        create_default_tax_platforms,
        seed_tax_notification_defaults,
        seed_tax_notification_rules_v2,
        seed_relation_types_and_trademark_classes,
        seed_archive_template,
        create_accounting_dashboard,
    ):
        patch.execute()
        frappe.db.commit()
