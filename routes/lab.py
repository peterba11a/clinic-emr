from flask import Blueprint, render_template, request, redirect, url_for, g, flash
from auth import login_required, role_required
from db import get_db
from billing_logic import add_invoice_item

bp = Blueprint("lab", __name__, url_prefix="/lab")


@bp.route("/order/<int:visit_id>", methods=["GET", "POST"])
@login_required
@role_required("Clinician", "Lab")
def order(visit_id):
    conn = get_db()
    visit = conn.execute("SELECT * FROM visits WHERE id=?", (visit_id,)).fetchone()
    if visit is None:
        conn.close()
        flash("Visit not found.", "error")
        return redirect(url_for("visits.queue"))
    patient = conn.execute("SELECT * FROM patients WHERE id=?", (visit["patient_id"],)).fetchone()
    test_types = conn.execute(
        "SELECT * FROM billables WHERE category='lab' AND active=1 ORDER BY name"
    ).fetchall()

    if request.method == "POST":
        billable_id = int(request.form["billable_id"])
        billable = conn.execute("SELECT * FROM billables WHERE id=?", (billable_id,)).fetchone()
        if billable:
            conn.execute(
                "INSERT INTO lab_orders (visit_id, billable_id, ordered_by) VALUES (?, ?, ?)",
                (visit_id, billable_id, g.user["id"]),
            )
            add_invoice_item(conn, visit_id, billable["name"], "lab", 1, billable["price"])
            conn.commit()
            flash(f"{billable['name']} ordered.", "success")

    orders = conn.execute(
        "SELECT lo.*, b.name AS test_name FROM lab_orders lo "
        "JOIN billables b ON b.id = lo.billable_id "
        "WHERE lo.visit_id=? ORDER BY lo.ordered_at DESC",
        (visit_id,),
    ).fetchall()
    conn.close()
    return render_template("lab/order.html", visit=visit, patient=patient, test_types=test_types, orders=orders)


@bp.route("/result/<int:order_id>", methods=["POST"])
@login_required
@role_required("Clinician", "Lab")
def result(order_id):
    conn = get_db()
    order_row = conn.execute("SELECT * FROM lab_orders WHERE id=?", (order_id,)).fetchone()
    if order_row is None:
        conn.close()
        flash("Lab order not found.", "error")
        return redirect(url_for("visits.queue"))
    result_text = request.form.get("result_text", "")
    conn.execute(
        "UPDATE lab_orders SET result_text=?, resulted_at=datetime('now') WHERE id=?",
        (result_text, order_id),
    )
    conn.commit()
    visit_id = order_row["visit_id"]
    conn.close()
    flash("Result recorded.", "success")
    return redirect(url_for("lab.order", visit_id=visit_id))
