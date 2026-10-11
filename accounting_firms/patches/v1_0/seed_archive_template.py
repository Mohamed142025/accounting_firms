import frappe

from accounting_firms.archive.api import ensure_customer_tree

# default archive structure (name -> children)
TEMPLATE = {
    "الملف الدائم": [
        "إقرارات المحاسب", "صحيفة التأسيس وتعديلاتها", "السجل التجاري", "محاضر مجالس الإدارة", "محاضر الجمعيات العامة",
        "الشهادات والعقود", "خطابات وإخطارات", "بطاقة ضريبية - وثيقة بيانات - شهادة قيمة مضافة", "استمارات ونماذج",
        "المنظومة الإلكترونية", "الرقم القومي وجواز السفر", "التوكيلات", "عقود الإيجار وسندات الحيازة", "كشوفات",
        "الإيصالات", "الغرف التجارية والصناعية", "منوعات أخرى",
    ],
    "SAP Documents": [],
    "المراجعة": ["ملفات المراجعة", "قوائم المركز المالي", "ملفات أخرى مراجعة"],
    "الضرائب المكتبي": {
        "ضريبة أجور ومرتبات": ["إقرارات الأجور والمرتبات"],
        "ضريبة خصم وإضافة": [], "ضريبة الدخل": [], "ضريبة قيمة مضافة": [], "ضريبة دمغة": [],
        "نموذج المستثمر الأجنبي": [], "ضرائب مكتبي (تجهيز الفحص)": [],
    },
    "ملفات العميل": [],
    "أرشيف البوسطة": ["ضرائب مكتبي", "العميل", "ضرائب ميداني", "سكرتارية", "الإجراءات والشئون الخارجية"],
    "محاسبة": ["ميزانيات الضرائب", "ميزانيات فعلية", "ميزانيات بنوك", "ميزانيات لأغراض أخرى"],
    "الضرائب الميداني": [
        "نماذج وطعون", "طلباتي", "محاضر الأعمال", "مذكرات وتقارير الفحص", "موافقات الفحص واللجان",
        "مذكرات لجان الطعن والخبراء", "قرارات لجان الطعن والخبراء", "حالات المثل الضريبي", "الموقف الضريبي", "منوعات أخرى",
    ],
    "أرشيف المادة التعليمية": ["محاسبة", "ضرائب", "مراجعة", "دراسات جدوى", "قوانين", "تعليمات وقرارات وزارية"],
}


def ensure_template_node(folder_name, parent=None):
    filters = {"folder_name": folder_name, "parent_archive_folder_template": parent if parent else ["in", ["", None]]}
    name = frappe.db.get_value("Archive Folder Template", filters)
    if name:
        return name
    doc = frappe.get_doc({"doctype": "Archive Folder Template", "folder_name": folder_name, "parent_archive_folder_template": parent})
    doc.insert(ignore_permissions=True)
    return doc.name


def seed(children, parent=None):
    items = children.items() if isinstance(children, dict) else [(c, []) for c in children]
    for folder_name, sub in items:
        node = ensure_template_node(folder_name, parent)
        if sub:
            seed(sub, node)


def execute():
    for doctype in ("archive_folder_template", "customer_archive_folder", "customer_document"):
        frappe.reload_doc("accounting_firms", "doctype", doctype)
    seed(TEMPLATE)
    for customer in frappe.get_all("Customer", pluck="name"):
        ensure_customer_tree(customer)
