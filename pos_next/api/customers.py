"""
POS Next Customer API
Handles customer search, creation, and management for POS operations
"""

import frappe
from frappe import _


@frappe.whitelist()
def get_customers(search_term="", pos_profile=None, limit=20, modified_since=None):

    """
    Search customers for inline customer selection in POS.

    Args:
        search_term (str): Search query (name, mobile, or customer ID)
        pos_profile (str): POS Profile to filter by customer group
        limit (int): Maximum number of results to return
        modified_since (str): Fetch customers modified after this timestamp (ISO format)

    Returns:
        list: List of customer dictionaries with name, customer_name, mobile_no, email_id, disabled
    """
    try:
        frappe.logger().debug(
            f"get_customers called with search_term={search_term}, pos_profile={pos_profile}, limit={limit}, modified_since={modified_since}"
        )

        filters = {}
        or_filters = []

        # Filter by POS Profile customer group if specified
        if pos_profile:
            frappe.logger().debug(f"Loading POS Profile: {pos_profile}")
            profile_doc = frappe.get_cached_doc("POS Profile", pos_profile)
            # Check if customer_group field exists (it may not exist in all versions)
            if hasattr(profile_doc, "customer_group") and profile_doc.customer_group:
                filters["customer_group"] = profile_doc.customer_group
                frappe.logger().debug(f"Filtering by customer_group: {profile_doc.customer_group}")

        if modified_since:
            # Delta sync: include disabled customers so frontend can purge them
            filters["modified"] = [">=", modified_since]
        else:
            # Full fetch: only active customers
            filters["disabled"] = 0

        search_term = (search_term or "").strip()
        if search_term:
            like_term = f"%{search_term}%"
            or_filters = [
                ["Customer", "name", "like", like_term],
                ["Customer", "customer_name", "like", like_term],
                ["Customer", "mobile_no", "like", like_term],
                ["Customer", "email_id", "like", like_term],
            ]

        customer_limit = limit if limit not in (None, 0) else frappe.db.count("Customer", filters)
        result = frappe.get_all(
            "Customer",
            filters=filters,
            or_filters=or_filters or None,
            fields=["name", "customer_name", "mobile_no", "email_id", "disabled"],
            limit=customer_limit,
            order_by="customer_name asc",
        )
        frappe.logger().debug(f"get_customers returned {len(result)} customers")
        return result
    except Exception as e:
        frappe.logger().error(f"Error in get_customers: {str(e)}")
        frappe.logger().error(frappe.get_traceback())
        frappe.throw(_("Error fetching customers: {0}").format(str(e)))


@frappe.whitelist()
def create_customer(
    customer_name,
    mobile_no=None,
    email_id=None,
    customer_group="Individual",
    territory="All Territories",
    company=None,
    pos_profile=None,
):
    """
    Create a new customer from POS.

    Args:
        customer_name (str): Customer name (required)
        mobile_no (str): Mobile number (optional)
        email_id (str): Email address (optional)
        customer_group (str): Customer group (default: Individual)
        territory (str): Territory (default: All Territories)
        company (str): Company (optional, used to auto-assign loyalty program)
        pos_profile (str): POS Profile (optional, preferred for context-aware loyalty assignment)

    Returns:
        dict: Created customer document
    """
    # Check if user has permission to create customers
    if not frappe.has_permission("Customer", "create"):
        frappe.throw(_("You don't have permission to create customers"), frappe.PermissionError)

    if not customer_name:
        frappe.throw(_("Customer name is required"))

    loyalty_program = get_default_loyalty_program_from_settings(
        company=company,
        pos_profile=pos_profile,
    )

    customer = frappe.get_doc(
        {
            "doctype": "Customer",
            "customer_name": customer_name,
            "customer_type": "Individual",
            "customer_group": customer_group or "Individual",
            "territory": territory or "All Territories",
            "mobile_no": mobile_no or "",
            "email_id": email_id or "",
            "loyalty_program": loyalty_program,
        }
    )

    frappe.flags.pos_next_customer_company = company
    frappe.flags.pos_next_customer_pos_profile = pos_profile
    try:
        customer.insert()
    finally:
        frappe.flags.pos_next_customer_company = None
        frappe.flags.pos_next_customer_pos_profile = None

    return customer.as_dict()


def get_default_loyalty_program(company):
    """
    Get the default loyalty program for a company.
    Prefers programs with auto_opt_in enabled.

    Args:
        company (str): Company name

    Returns:
        str: Loyalty program name or None
    """
    # First try to find a loyalty program with auto_opt_in for the company
    loyalty_program = frappe.db.get_value(
        "Loyalty Program",
        {"company": company, "auto_opt_in": 1},
        "name"
    )

    if loyalty_program:
        return loyalty_program

    # Fallback: any loyalty program for the company
    loyalty_program = frappe.db.get_value(
        "Loyalty Program",
        {"company": company},
        "name"
    )

    return loyalty_program


def auto_assign_loyalty_program(doc, method=None):
    """
    Auto-assign loyalty program to newly created customers.
    Called as after_insert hook on Customer doctype.

    Uses the default_loyalty_program from POS Settings.
    If no loyalty program is configured in POS Settings, no auto-assignment occurs.

    Args:
        doc: Customer document
        method: Hook method name (not used)
    """
    # Skip if customer already has a loyalty program
    if doc.loyalty_program:
        return

    company, pos_profile = _get_customer_assignment_context()
    loyalty_program = get_default_loyalty_program_from_settings(
        company=company,
        pos_profile=pos_profile,
    )

    if loyalty_program:
        # Use db_set to avoid triggering validate hooks again
        doc.db_set("loyalty_program", loyalty_program, update_modified=False)
        frappe.logger().info(
            f"Auto-assigned loyalty program '{loyalty_program}' to customer '{doc.name}'"
        )


def _get_customer_assignment_context():
    """Get company/profile context for customer auto-assignment from the current request."""
    company = getattr(frappe.flags, "pos_next_customer_company", None)
    pos_profile = getattr(frappe.flags, "pos_next_customer_pos_profile", None)

    form_dict = getattr(frappe.local, "form_dict", None)
    if form_dict:
        company = company or form_dict.get("company")
        pos_profile = pos_profile or form_dict.get("pos_profile")

    return company, pos_profile


def get_default_loyalty_program_from_settings(company=None, pos_profile=None):
    """
    Get the default loyalty program from POS Settings using explicit context.
    Returns a program only when the company/profile context is clear enough to avoid
    assigning the wrong loyalty program.

    Returns:
        str: Loyalty program name or None if not configured
    """
    if pos_profile:
        pos_settings = frappe.db.get_value(
            "POS Settings",
            {"enabled": 1, "pos_profile": pos_profile},
            "default_loyalty_program",
        )
        return pos_settings or None

    if not company:
        return None

    pos_settings = frappe.get_all(
        "POS Settings",
        filters={"enabled": 1, "default_loyalty_program": ["is", "set"]},
        fields=["pos_profile", "default_loyalty_program"],
        order_by="modified desc",
    )

    company_programs = []
    for row in pos_settings:
        profile_company = frappe.get_cached_value("POS Profile", row.pos_profile, "company")
        if profile_company == company:
            company_programs.append(row.default_loyalty_program)

    unique_programs = list(dict.fromkeys(program for program in company_programs if program))
    if len(unique_programs) == 1:
        return unique_programs[0]

    return None


@frappe.whitelist()
def get_customer_details(customer):
    """
    Get detailed customer information.

    Args:
        customer (str): Customer ID

    Returns:
        dict: Customer details
    """
    if not customer:
        frappe.throw(_("Customer is required"))

    return frappe.get_cached_doc("Customer", customer).as_dict()


@frappe.whitelist()
def update_customer(
    customer,
    customer_name=None,
    mobile_no=None,
    email_id=None,
    customer_group=None,
    territory=None,
    tax_id=None,
):
    """
    Update an existing customer from POS.

    Args:
        customer (str): Customer ID (required)
        customer_name (str): Customer name
        mobile_no (str): Mobile number
        email_id (str): Email address
        customer_group (str): Customer group
        territory (str): Territory
        tax_id (str): Tax ID

    Returns:
        dict: Updated customer document
    """
    if not customer:
        frappe.throw(_("Customer is required"))

    if not frappe.has_permission("Customer", "write", customer):
        frappe.throw(_("You don't have permission to update customers"), frappe.PermissionError)

    doc = frappe.get_doc("Customer", customer)

    if customer_name:
        doc.customer_name = customer_name
    if customer_group:
        doc.customer_group = customer_group
    if territory:
        doc.territory = territory
    if tax_id is not None:
        doc.tax_id = tax_id

    # ERPNext stores mobile_no and email_id in the Primary Contact document
    # via child tables (phone_nos and email_ids). The fields on Customer are
    # Read Only and fetched from the Contact. We must update the Contact.
    if doc.get("customer_primary_contact"):
        contact = frappe.get_doc("Contact", doc.customer_primary_contact)
        contact_updated = False

        # --- Update mobile number ---
        if mobile_no is not None:
            # Find existing primary mobile row
            primary_phone_row = None
            for row in contact.phone_nos:
                if row.is_primary_mobile_no:
                    primary_phone_row = row
                    break

            if primary_phone_row:
                if not mobile_no:
                    contact.phone_nos.remove(primary_phone_row)
                    contact_updated = True
                elif primary_phone_row.phone != mobile_no:
                    primary_phone_row.phone = mobile_no
                    contact_updated = True
            elif mobile_no:
                # No primary mobile yet – add one
                contact.append("phone_nos", {
                    "phone": mobile_no,
                    "is_primary_mobile_no": 1,
                    "is_primary_phone": 0,
                })
                contact_updated = True

        # --- Update email ---
        if email_id is not None:
            # Find existing primary email row
            primary_email_row = None
            for row in contact.email_ids:
                if row.is_primary:
                    primary_email_row = row
                    break

            if primary_email_row:
                if not email_id:
                    contact.email_ids.remove(primary_email_row)
                    contact_updated = True
                elif primary_email_row.email_id != email_id:
                    primary_email_row.email_id = email_id
                    contact_updated = True
            elif email_id:
                # No primary email yet – add one
                contact.append("email_ids", {
                    "email_id": email_id,
                    "is_primary": 1,
                })
                contact_updated = True

        if contact_updated:
            contact.flags.ignore_permissions = True
            contact.save(ignore_permissions=True)
    else:
        # No linked Contact – set directly (works when fields are not fetched)
        if mobile_no is not None:
            doc.mobile_no = mobile_no
        if email_id is not None:
            doc.email_id = email_id

    doc.save(ignore_permissions=True)
    frappe.db.commit()

    return doc.as_dict()
