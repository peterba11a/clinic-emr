from datetime import date, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, g, flash
from auth import login_required, role_required
from db import get_db
from billing_logic import add_invoice_item

bp = Blueprint("pharmacy", __name__, url_prefix="/pharmacy")

EXPIRY_WARNING_DAYS = 60


@bp.route("/")
@login_required
@role_required("Pharmacy")
def index():
    conn = get_db()
    items = conn.execute(
        "SELECT * FROM inventory_items WHERE active=1 ORDER BY item_type, name"
    ).fetchall()
    conn.close()
    soon = (date.today() + timedelta(days=EXPIRY_WARNING_DAYS)).isoformat()
    return render_template("pharmacy/index.html", items=items, soon=soon, today=date.today().isoformat())


@bp.route("/new", methods=["GET", "POST"])
@login_required
@role_required("Pharmacy")
def new():
    if request.method == "POST":
        conn = get_db()
        conn.execute(
            "INSERT INTO inventory_items (name, item_type, unit, unit_price, stock_qty, expiry_date, reorder_threshold) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                request.form["name"].strip(),
                request.form.get("item_type", "drug"),
                request.form.get("unit", "unit"),
                float(request.form.get("unit_price") or 0),
                float(request.form.get("stock_qty") or 0),
                request.form.get("expiry_date") or None,
                float(request.form.get("reorder_threshold") or 0),
            ),
        )
        conn.commit()
        conn.close()
        flash("Item added to inventory.", "success")
        return redirect(url_for("pharmacy.index"))
    return render_template("pharmacy/new.html")


@bp.route("/<int:item_id>/edit", methods=["GET", "POST"])
@login_required
@role_required("Pharmacy")
def edit(item_id):
    conn = get_db()
    item = conn.execute("SELECT * FROM inventory_items WHERE id=?", (item_id,)).fetchone()
    if item is None:
        conn.close()
        flash("Item not found.", "error")
        return redirect(url_for("pharmacy.index"))
    if request.method == "POST":
        conn.execute(
            "UPDATE inventory_items SET name=?, item_type=?, unit=?, unit_price=?, stock_qty=?, "
            "expiry_date=?, reorder_threshold=? WHERE id=?",
            (
                request.form["name"].strip(),
                request.form.get("item_type", "drug"),
                request.form.get("unit", "unit"),
                float(request.form.get("unit_price") or 0),
                float(request.form.get("stock_qty") or 0),
                request.form.get("expiry_date") or None,
                float(request.form.get("reorder_threshold") or 0),
                item_id,
            ),
        )
        conn.commit()
        conn.close()
        flash("Item updated.", "success")
        return redirect(url_for("pharmacy.index"))
    conn.close()
    return render_template("pharmacy/edit.html", item=item)


@bp.route("/dispense/<int:visit_id>", methods=["GET", "POST"])
@login_required
@role_required("Pharmacy")
def dispense(visit_id):
    conn = get_db()
    visit = conn.execute("SELECT * FROM visits WHERE id=?", (visit_id,)).fetchone()
    if visit is None:
        conn.close()
        flash("Visit not found.", "error")
        return redirect(url_for("visits.queue"))
    patient = conn.execute("SELECT * FROM patients WHERE id=?", (visit["patient_id"],)).fetchone()

    if request.method == "POST":
        item_id = int(request.form["item_id"])
        quantity = float(request.form["quantity"])
        item = conn.execute("SELECT * FROM inventory_items WHERE id=?", (item_id,)).fetchone()
        if item is None:
            flash("Item not found.", "error")
        elif quantity <= 0:
            flash("Quantity must be greater than zero.", "error")
        elif item["stock_qty"] < quantity:
            flash(f"Not enough stock of {item['name']} (only {item['stock_qty']} {item['unit']} left).", "error")
        else:
            conn.execute(
                "INSERT INTO dispenses (visit_id, inventory_item_id, quantity, unit_price, dispensed_by) "
                "VALUES (?, ?, ?, ?, ?)",
                (visit_id, item_id, quantity, item["unit_price"], g.user["id"]),
            )
            conn.execute(
                "UPDATE inventory_items SET stock_qty = stock_qty - ? WHERE id=?",
                (quantity, item_id),
            )
            add_invoice_item(conn, visit_id, item["name"], "drug", quantity, item["unit_price"])
            conn.commit()
            flash(f"Dispensed {quantity} {item['unit']} of {item['name']}.", "success")

    items = conn.execute(
        "SELECT * FROM inventory_items WHERE active=1 AND item_type='drug' ORDER BY name"
    ).fetchall()
    history = conn.execute(
        "SELECT d.*, i.name, i.unit FROM dispenses d "
        "JOIN inventory_items i ON i.id = d.inventory_item_id "
        "WHERE d.visit_id=? ORDER BY d.dispensed_at DESC",
        (visit_id,),
    ).fetchall()
    conn.close()
    return render_template(
        "pharmacy/dispense.html", visit=visit, patient=patient, items=items, history=history
    )
