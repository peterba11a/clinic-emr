from flask import Blueprint, render_template, request, redirect, url_for, g, flash
from auth import login_required, role_required
from db import get_db
from billing_logic import get_or_create_invoice, invoice_totals, refresh_invoice_status

bp = Blueprint("billing", __name__, url_prefix="/billing")


@bp.route("/invoice/<int:visit_id>")
@login_required
def invoice(visit_id):
    conn = get_db()
    visit = conn.execute("SELECT * FROM visits WHERE id=?", (visit_id,)).fetchone()
    if visit is None:
        conn.close()
        flash("Visit not found.", "error")
        return redirect(url_for("visits.queue"))
    patient = conn.execute("SELECT * FROM patients WHERE id=?", (visit["patient_id"],)).fetchone()
    invoice_id = get_or_create_invoice(conn, visit_id)
    conn.commit()
    items = conn.execute(
        "SELECT * FROM invoice_items WHERE invoice_id=? ORDER BY created_at", (invoice_id,)
    ).fetchall()
    payments = conn.execute(
        "SELECT p.*, u.full_name FROM payments p LEFT JOIN users u ON u.id = p.recorded_by "
        "WHERE invoice_id=? ORDER BY paid_at", (invoice_id,)
    ).fetchall()
    total, paid, balance = invoice_totals(conn, invoice_id)
    conn.close()
    return render_template(
        "billing/invoice.html", visit=visit, patient=patient, items=items,
        payments=payments, total=total, paid=paid, balance=balance, invoice_id=invoice_id,
    )


@bp.route("/pay/<int:invoice_id>", methods=["POST"])
@login_required
@role_required("Reception")
def pay(invoice_id):
    conn = get_db()
    inv = conn.execute("SELECT * FROM invoices WHERE id=?", (invoice_id,)).fetchone()
    if inv is None:
        conn.close()
        flash("Invoice not found.", "error")
        return redirect(url_for("visits.queue"))
    amount = float(request.form.get("amount") or 0)
    method = request.form.get("method", "cash")
    if amount > 0:
        conn.execute(
            "INSERT INTO payments (invoice_id, amount, method, recorded_by) VALUES (?, ?, ?, ?)",
            (invoice_id, amount, method, g.user["id"]),
        )
        refresh_invoice_status(conn, invoice_id)
        conn.commit()
        flash(f"Payment of {amount:,.0f} recorded.", "success")
    conn.close()
    return redirect(url_for("billing.invoice", visit_id=inv["visit_id"]))
