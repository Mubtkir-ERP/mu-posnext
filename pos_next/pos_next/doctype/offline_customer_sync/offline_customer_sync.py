import frappe
from frappe.model.document import Document


class OfflineCustomerSync(Document):
    """Maps a stable offline customer ID to an ERPNext Customer."""
    pass
