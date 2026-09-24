app_name = "nsa_import"
app_title = "NSA Import"
app_publisher = "NSA"
app_description = "Local / Import Purchase Order, Letter of Credit, Shipping Documents, Customs Clearance and Landed Cost"
app_email = "erp@nsa.local"
app_license = "mit"
required_apps = ["erpnext"]

after_install = "nsa_import.install.after_install"
after_migrate = "nsa_import.install.after_migrate"
before_uninstall = "nsa_import.install.before_uninstall"

doctype_js = {
    "Purchase Order": "public/js/purchase_order.js",
    "Purchase Receipt": "public/js/purchase_receipt.js",
}

doc_events = {
    "Purchase Order": {
        "validate": "nsa_import.overrides.purchase_order.validate",
    },
    "Purchase Receipt": {
        "validate": "nsa_import.overrides.purchase_receipt.validate",
        "on_submit": "nsa_import.overrides.purchase_receipt.on_submit",
        "on_cancel": "nsa_import.overrides.purchase_receipt.on_cancel",
    },
    "Purchase Invoice": {
        "validate": "nsa_import.overrides.purchase_receipt.validate",
    },
    "Journal Entry": {
        "on_submit": "nsa_import.overrides.journal_entry.on_submit",
        "on_cancel": "nsa_import.overrides.journal_entry.on_cancel",
    },
}

override_doctype_dashboards = {
    "Purchase Order": "nsa_import.overrides.dashboard.purchase_order_dashboard",
}

scheduler_events = {
    "daily": ["nsa_import.tasks.mark_expired_lcs"],
}
