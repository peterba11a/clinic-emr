from flask import Blueprint, render_template, request, redirect, url_for, g, flash
from auth import login_required, role_required
from db import get_db
from billing_logic import add_invoice_item

bp = Blueprint("procedures", __name__, url_prefix="/procedures")


@bp.route("/record/<int:visit_id>", methods=["GET", "POST"])
@login_required
@role_required("Clinician")
def record(visit_id):
    conn = get_db()
    visit = conn.execute("SELECT * FROM visits WHERE id=?", (visit_id,)).fetchone()
    if visit is None:
        conn.close()
        flash("Visit not found.", "error")
        return redirect(url_for("visits.queue"))
    patient = conn.execute("SELECT * FROM patients WHERE id=?", (visit["patient_id"],)).fetchone()
    procedure_types = conn.execute(
        "SELECT * FROM billables WHERE category='procedure' AND active=1 ORDER BY name"
    ).fetchall()
    materials = conn.execute(
        "SELECT * FROM inventory_items WHERE active=1 ORDER BY name"
    ).fetchall()

    if request.method == "POST":
        billable_id = int(request.form["billable_id"])
        notes = request.form.get("notes", "")
        billable = conn.execute("SELECT * FROM billables WHERE id=?", (billable_id,)).fetchone()
        if billable is None:
            flash("Select a valid procedure.", "error")
        else:
            cur = conn.execute(
                "INSERT INTO procedure_records (visit_id, billable_id, performed_by, notes) "
                "VALUES (?, ?, ?, ?)",
                (visit_id, billable_id, g.user["id"], notes),
            )
            procedure_record_id = cur.lastrowid
            add_invoice_item(conn, visit_id, billable["name"], "procedure", 1, billable["price"])

            item_ids = request.form.getlist("material_item_id")
            quantities = request.form.getlist("material_quantity")
            for item_id_raw, qty_raw in zip(item_ids, quantities):
                if not item_id_raw or not qty_raw:
                    continue
                qty = float(qty_raw)
                if qty <= 0:
                    continue
                item = conn.execute(
                    "SELECT * FROM inventory_items WHERE id=?", (int(item_id_raw),)
                ).fetchone()
                if item is None:
                    continue
                if item["stock_qty"] < qty:
                    flash(f"Not enough stock of {item['name']} — skipped.", "error")
                    continue
                conn.execute(
                    "INSERT INTO procedure_materials (procedure_record_id, inventory_item_id, quantity, unit_price) "
                    "VALUES (?, ?, ?, ?)",
                    (procedure_record_id, item["id"], qty, item["unit_price"]),
                )
                conn.execute(
                    "UPDATE inventory_items SET stock_qty = stock_qty - ? WHERE id=?",
                    (qty, item["id"]),
                )
                add_invoice_item(conn, visit_id, f"{item['name']} (used in {billable['name']})",
                                  "material", qty, item["unit_price"])

            conn.commit()
            flash(f"{billable['name']} recorded.", "success")

    history = conn.execute(
        "SELECT pr.*, b.name AS billable_name, b.price FROM procedure_records pr "
        "JOIN billables b ON b.id = pr.billable_id "
        "WHERE pr.visit_id=? ORDER BY pr.performed_at DESC",
        (visit_id,),
    ).fetchall()
    conn.close()
    return render_template(
        "procedures/record.html", visit=visit, patient=patient,
        procedure_types=procedure_types, materials=materials, history=history,
    )
