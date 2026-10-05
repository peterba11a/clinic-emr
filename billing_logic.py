"""Shared helpers so every module (visits, pharmacy, procedures, lab, radiology)
adds to a patient's bill the same way, instead of each reimplementing invoicing."""

from db import get_setting


def get_or_create_invoice(conn, visit_id):
    row = conn.execute("SELECT * FROM invoices WHERE visit_id=?", (visit_id,)).fetchone()
    if row:
        return row["id"]
    cur = conn.execute("INSERT INTO invoices (visit_id) VALUES (?)", (visit_id,))
    return cur.lastrowid


def add_invoice_item(conn, visit_id, description, category, quantity, unit_price):
    invoice_id = get_or_create_invoice(conn, visit_id)
    line_total = round(quantity * unit_price, 2)
    conn.execute(
        "INSERT INTO invoice_items (invoice_id, description, category, quantity, unit_price, line_total) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (invoice_id, description, category, quantity, unit_price, line_total),
    )
    return invoice_id


def bill_printing(conn, visit_id, document_label):
    """Charges the Admin-configured price-per-page (Admin -> Billables ->
    Printing) to a visit's invoice every time a patient document is
    printed. Every printed document counts as a flat 1 page, and every
    print bills again — printing the same thing twice bills twice, same as
    giving the same dose twice bills twice. A no-op until Admin sets a
    price above zero, so this stays invisible to clinics that don't want
    it rather than adding a stray 0-cost line to every invoice."""
    price = float(get_setting("print_price_per_page", "0") or 0)
    if price <= 0:
        return
    add_invoice_item(conn, visit_id, f"Printing — {document_label}", "printing", 1, price)


def invoice_totals(conn, invoice_id):
    total = conn.execute(
        "SELECT COALESCE(SUM(line_total), 0) t FROM invoice_items WHERE invoice_id=?",
        (invoice_id,),
    ).fetchone()["t"]
    paid = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) p FROM payments WHERE invoice_id=?",
        (invoice_id,),
    ).fetchone()["p"]
    return round(total, 2), round(paid, 2), round(total - paid, 2)


def refresh_invoice_status(conn, invoice_id):
    total, paid, balance = invoice_totals(conn, invoice_id)
    if total <= 0:
        status = "open"
    elif balance <= 0:
        status = "paid"
    elif paid > 0:
        status = "partial"
    else:
        status = "open"
    conn.execute("UPDATE invoices SET status=? WHERE id=?", (status, invoice_id))
    return status
