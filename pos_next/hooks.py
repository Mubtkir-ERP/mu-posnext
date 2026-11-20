from pos_next.utils import get_build_version

app_name = "pos_next"
app_title = "POS Next"
app_publisher = "BrainWise"
app_description = "POS built on ERPNext that brings together real-time billing, stock management, multi-user access, offline mode, and direct ERP integration. Run your store or restaurant with confidence and control, while staying 100% open source."
app_email = "support@brainwise.me"
app_license = "agpl-3.0"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "pos_next",
# 		"logo": "/assets/pos_next/logo.png",
# 		"title": "POS Next",
# 		"route": "/pos_next",
# 		"has_permission": "pos_next.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# Get unique build version for cache busting
_asset_version = get_build_version()

# include js, css files in header of desk.html
# app_include_css = f"/assets/pos_next/css/pos_next.css?v={_asset_version}"
# app_include_js = f"/assets/pos_next/js/pos_next.js?v={_asset_version}"

# include js, css files in header of web template
# web_include_css = "/assets/pos_next/css/pos_next.css"
# web_include_js = "/assets/pos_next/js/pos_next.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "pos_next/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

doctype_js = {
    "Customer": "public/js/customer_branch_qr.js",
    "Address": "public/js/address_branch_qr.js",
}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "pos_next/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "pos_next.utils.jinja_methods",
# 	"filters": "pos_next.utils.jinja_filters"
# }

# Fixtures
# --------
fixtures = [
    {"dt": "Custom Field", "filters": [["name", "in", ['POS Profile-posa_block_sale_beyond_available_qty', 'POS Profile-posa_cash_mode_of_payment', 'POS Profile-mu_allow_item_discount', 'POS Profile-mu_allow_additional_discount', 'POS Profile-mu_max_discount_percent', 'POS Profile-mu_use_percentage_discount', 'POS Profile-mu_cfg_col_a', 'POS Profile-mu_cfg_col_b', 'POS Profile-mu_customer_section', 'POS Profile-mu_top_col_3', 'POS Profile-mu_print_col_2', 'POS Profile-mu_default_print_method', 'POS Profile-mu_thermal_print_format', 'POS Profile-mu_cashier_printer', 'POS Profile-mu_print_col_3', 'POS Profile-mu_a4_print_format', 'POS Profile-mu_closing_print_format', 'POS Profile-mu_allow_whatsapp_invoice', 'POS Profile-mu_posnext_cash_section', 'POS Profile-mu_allow_cash_expense', 'POS Profile-mu_cash_expense_limit', 'POS Profile-mu_cash_expense_account', 'POS Profile-mu_posnext_cash_section_col_2', 'POS Profile-mu_cash_otp_enabled', 'POS Profile-mu_cash_otp_mobile', 'POS Profile-mu_otp_message_templates', 'POS Profile-mu_posnext_cash_section_col_3', 'POS Profile-mu_shift_whatsapp_enabled', 'POS Profile-mu_shift_whatsapp_mobile', 'POS Profile-mu_shift_whatsapp_print_format', 'POS Profile-mu_kitchen_section', 'POS Profile-mu_kitchen_printers', 'POS Profile-mu_posnext_voucher_section', 'POS Profile-mu_voucher_redeem_item', 'POS Profile-mu_voucher_warehouse', 'POS Profile-mu_posnext_voucher_col_2', 'POS Profile-mu_voucher_daily_limit', 'POS Profile-mu_cash_sweeping_section', 'POS Profile-mu_auto_sweep_cash', 'POS Profile-mu_driver_cash_account', 'POS Profile-mu_cash_sweeping_section_col_2', 'POS Profile-mu_shop_cash_account', 'POS Profile-mu_main_cash_account', 'POS Profile-mu_cash_sweeping_section_col_3', 'POS Profile-mu_cash_difference_account', 'POS Profile-mu_van_stock_section', 'POS Profile-mu_enable_van_stock_cycle', 'POS Profile-mu_van_stock_section_col_2', 'POS Profile-mu_shop_warehouse', 'POS Profile-mu_van_stock_section_col_3', 'POS Profile-mu_van_warehouse', 'POS Profile-mu_non_taxable_section', 'POS Profile-mu_enable_non_taxable_charges', 'POS Profile-mu_non_taxable_section_col_2', 'POS Profile-mu_non_taxable_income_account', 'POS Profile-mu_non_taxable_section_col_3', 'POS Profile-mu_closing_controls_section', 'POS Profile-mu_hide_closing_taxes', 'POS Profile-mu_closing_controls_section_col_2', 'POS Profile-mu_hide_closing_vouchers', 'POS Profile-mu_closing_controls_section_col_3', 'POS Profile-mu_hide_closing_reconciliation', 'POS Profile-mu_section_break_customer_display', 'POS Profile-customer_display_enabled', 'POS Profile-customer_display_company_name', 'POS Profile-customer_display_welcome_text', 'POS Profile-customer_display_pos_location', 'POS Profile-mu_section_break_customer_display_col_2', 'POS Profile-customer_display_theme', 'POS Profile-customer_display_size_mode', 'POS Profile-customer_display_currency_label', 'POS Profile-customer_display_idle_mode', 'POS Profile-mu_section_break_customer_display_col_3', 'POS Profile-customer_display_thank_you_duration', 'POS Profile-customer_display_idle_image', 'POS Profile-customer_display_idle_video', 'POS Profile-mu_section_break_customer_display_visibility', 'POS Profile-cd_show_company_name', 'POS Profile-cd_show_welcome_text', 'POS Profile-cd_show_pos_location', 'POS Profile-cd_show_pos_number', 'POS Profile-cd_show_product_image', 'POS Profile-cd_show_item_name', 'POS Profile-mu_section_break_customer_display_visibility_col_2', 'POS Profile-cd_show_barcode', 'POS Profile-cd_show_quantity', 'POS Profile-cd_show_original_price', 'POS Profile-cd_show_discount_amount', 'POS Profile-cd_show_discount_percentage', 'POS Profile-mu_section_break_customer_display_visibility_col_3', 'POS Profile-cd_show_final_price', 'POS Profile-cd_show_running_qty', 'POS Profile-cd_show_subtotal', 'POS Profile-cd_show_total_discount', 'POS Profile-cd_show_grand_total', 'POS Profile-mu_section_break_customer_display_customer_payment', 'POS Profile-cd_show_customer_name', 'POS Profile-cd_customer_name_mode', 'POS Profile-cd_show_loyalty_points', 'POS Profile-cd_show_loyalty_earned', 'POS Profile-cd_show_customer_credit', 'POS Profile-mu_section_break_customer_display_customer_payment_col_2', 'POS Profile-cd_show_payment_method', 'POS Profile-cd_show_amount_paid', 'POS Profile-cd_show_remaining_balance', 'POS Profile-cd_show_change', 'POS Profile-mu_section_break_customer_display_customer_payment_col_3', 'POS Profile-cd_show_invoice_number', 'POS Profile-cd_enable_thank_you', 'POS Profile-customer_display_thank_you_title', 'POS Profile-customer_display_thank_you_message', 'POS Profile-mu_section_break_customer_display_overlay', 'POS Profile-customer_display_overlay_enabled', 'POS Profile-customer_display_overlay_text', 'POS Profile-customer_display_overlay_type', 'POS Profile-customer_display_overlay_on', 'POS Profile-mu_section_break_customer_display_overlay_col_2', 'POS Profile-customer_display_overlay_position', 'POS Profile-customer_display_overlay_text_color', 'POS Profile-customer_display_overlay_background_color', 'POS Profile-mu_section_break_customer_display_overlay_col_3', 'POS Profile-customer_display_overlay_opacity', 'POS Profile-customer_display_overlay_font_size', 'POS Profile-customer_display_overlay_scroll_speed', 'POS Profile-mu_tax_inclusive', 'Item-mu_is_voucher_item', 'Item-mu_voucher_units', 'Item-mu_voucher_validity_days', 'Item-mu_restaurant_section', 'Item-mu_kitchen_station', 'Item-mu_modifier_groups', 'Item Group-custom_kitchen_station', 'Sales Invoice-mu_order_number', 'Sales Invoice-mu_order_type']]]},
    {"dt": "Property Setter", "filters": [["name", "in", ['POS Profile-print_format-hidden', 'POS Profile-hide_unavailable_items-hidden', 'POS Profile-print_receipt_on_order_complete-hidden', 'POS Profile-column_break_21-hidden', 'POS Profile-section_break_14-label', 'POS Profile-section_break_14-collapsible', 'POS Profile-section_break_16-label', 'POS Profile-section_break_16-collapsible', 'POS Profile-section_break_19-collapsible', 'POS Profile-section_break_23-collapsible', 'POS Profile-customer_groups-insert_after', 'POS Profile-accounting_dimensions_section-collapsible']]]},
	{
		"dt": "Print Format",
		"filters": [
			[
				"name",
				"in",
				[
					"POS Next Receipt"
				]
			]
		]
	},
    {
        "dt": "Role",
        "filters": [
            ["role_name", "in", ["POSNext Cashier","Nexus POS Manager"]]
        ]
    },
    {
        "dt": "Custom DocPerm",
        "filters": [
            ["role", "in", ["POSNext Cashier"]]
        ]
    }
]

# Installation
# ------------

# before_install = "pos_next.install.before_install"
after_install = "pos_next.install.after_install"
after_migrate = "pos_next.install.after_migrate"

# Uninstallation
# ------------

before_uninstall = "pos_next.uninstall.before_uninstall"
# after_uninstall = "pos_next.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "pos_next.utils.before_app_install"
# after_app_install = "pos_next.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "pos_next.utils.before_app_uninstall"
# after_app_uninstall = "pos_next.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "pos_next.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Standard Queries
# ----------------
# Custom query for company-aware item filtering
standard_queries = {
	"Item": "pos_next.validations.item_query"
}

# DocType Class
# ---------------
# Override standard doctype classes

override_doctype_class = {
	"Sales Invoice": "pos_next.overrides.sales_invoice.CustomSalesInvoice"
}

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"Item": {
		"validate": "pos_next.validations.validate_item"
	},
	"Customer": {
		"after_insert": [
			"pos_next.api.customers.auto_assign_loyalty_program",
			"pos_next.realtime_events.emit_customer_event",
			"pos_next.api.wallet.create_wallet_on_customer_insert"
		],
		"on_update": "pos_next.realtime_events.emit_customer_event",
		"on_trash": "pos_next.realtime_events.emit_customer_event"
	},
	"Sales Invoice": {
		"validate": [
			"pos_next.api.sales_invoice_hooks.validate",
			"pos_next.api.payment_security.validate_and_pin_invoice_payments",
			"pos_next.api.wallet.validate_wallet_payment"
		],
		"before_cancel": "pos_next.api.sales_invoice_hooks.before_cancel",
		"on_submit": [
			"pos_next.realtime_events.emit_stock_update_event",
			"pos_next.api.wallet.process_loyalty_to_wallet",
			"pos_next.api.voucher.on_sales_invoice_submit"
		],
		"on_cancel": [
			"pos_next.realtime_events.emit_stock_update_event",
			"pos_next.api.sales_invoice_hooks.on_cancel_coupon",
			"pos_next.api.voucher.on_sales_invoice_cancel"
		],
		"after_insert": "pos_next.realtime_events.emit_invoice_created_event"
	},
	"Sales Order": {
		"on_cancel": "pos_next.api.sales_invoice_hooks.on_cancel_coupon"
	},
	"POS Profile": {
		"on_update": "pos_next.realtime_events.emit_pos_profile_updated_event"
	},
	"Promotional Scheme": {
		"on_update": "pos_next.overrides.pricing_rule.sync_pos_only_to_pricing_rules"
	},
	"POS Closing Shift": {
		"on_submit": [
			"pos_next.api.shift_whatsapp.notify_shift_close",
			"pos_next.operations.shift_operations.on_closing_shift_submit"
		]
	}
}

# Scheduled Tasks
# ---------------

scheduler_events = {
	"hourly": [
		"pos_next.tasks.branding_monitor.monitor_branding_integrity",
	],
	"daily": [
		"pos_next.tasks.cleanup_expired_promotions.cleanup_expired_promotions",
		"pos_next.tasks.branding_monitor.validate_all_active_sessions",
		"pos_next.api.voucher.process_voucher_expiries",
	],
	"monthly": [
		"pos_next.tasks.branding_monitor.reset_tampering_counter",
	],
}

# Testing
# -------

# before_tests = "pos_next.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "pos_next.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "pos_next.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["pos_next.utils.before_request"]
# after_request = ["pos_next.utils.after_request"]

# Job Events
# ----------
# before_job = ["pos_next.utils.before_job"]
# after_job = ["pos_next.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"pos_next.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }


website_route_rules = [{'from_route': '/pos/<path:app_path>', 'to_route': 'pos'},]