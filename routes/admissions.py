from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, g, flash
from auth import login_required, role_required
from db import get_db
from billing_logic import add_invoice_item

bp = Blueprint("admissions", __name__, url_prefix="/admissions")


@bp.route("/")
@login_required
@role_required("Reception", "Nurse", "Clinician")
def inpatients():
    conn = get_db()
    rows = conn.execute(
        "SELECT a.*, v.id AS visit_id, p.id AS patient_id, p.full_name, p.patient_code, "
        "w.name AS ward_name, b.name AS bed_name "
        "FROM admissions a "
        "JOIN visits v ON v.id = a.visit_id "
        "JOIN patients p ON p.id = v.patient_id "
        "JOIN wards w ON w.id = a.ward_id "
        "JOIN beds b ON b.id = a.bed_id "
        "WHERE a.status='admitted' "
        "ORDER BY a.admitted_at ASC"
    ).fetchall()
    conn.close()
    return render_template("admissions/inpatients.html", admissions=rows)


@bp.route("/admit/<int:visit_id>", methods=["POST"])
@login_required
@role_required("Reception", "Nurse", "Clinician")
def admit(visit_id):
    conn = get_db()
    visit = conn.execute("SELECT * FROM visits WHERE id=?", (visit_id,)).fetchone()
    if visit is None:
        conn.close()
        flash("Visit not found.", "error")
        return redirect(url_for("visits.queue"))

    existing = conn.execute(
        "SELECT * FROM admissions WHERE visit_id=? AND status='admitted'", (visit_id,)
    ).fetchone()
    if existing:
        conn.close()
        flash("This patient is already admitted.", "error")
        return redirect(url_for("visits.detail", visit_id=visit_id))

    bed_id = request.form.get("bed_id")
    bed = conn.execute("SELECT * FROM beds WHERE id=? AND status='available'", (bed_id,)).fetchone() if bed_id else None
    if bed is None:
        conn.close()
        flash("Select an available bed.", "error")
        return redirect(url_for("visits.detail", visit_id=visit_id))

    conn.execute(
        "INSERT INTO admissions (visit_id, ward_id, bed_id, admitted_by) VALUES (?, ?, ?, ?)",
        (visit_id, bed["ward_id"], bed["id"], g.user["id"]),
    )
    conn.execute("UPDATE beds SET status='occupied' WHERE id=?", (bed["id"],))
    conn.execute("UPDATE visits SET status='admitted' WHERE id=?", (visit_id,))
    conn.commit()
    conn.close()
    flash("Patient admitted.", "success")
    return redirect(url_for("visits.detail", visit_id=visit_id))


def _nights_stayed(admitted_at: str, discharged_at: str) -> int:
    """Number of nights to bill: calendar-day difference between admission
    and discharge, with a one-night minimum (a same-day discharge still
    used a bed for the night's charge purposes)."""
    fmt = "%Y-%m-%d %H:%M:%S"
    admitted_dt = datetime.strptime(admitted_at[:19], fmt)
    discharged_dt = datetime.strptime(discharged_at[:19], fmt)
    nights = (discharged_dt.date() - admitted_dt.date()).days
    return max(1, nights)


@bp.route("/<int:admission_id>/discharge", methods=["POST"])
@login_required
@role_required("Nurse", "Clinician")
def discharge(admission_id):
    conn = get_db()
    admission = conn.execute("SELECT * FROM admissions WHERE id=?", (admission_id,)).fetchone()
    if admission is None or admission["status"] != "admitted":
        conn.close()
        flash("Admission not found or already discharged.", "error")
        return redirect(url_for("admissions.inpatients"))

    summary = (request.form.get("discharge_summary") or "").strip()
    follow_up_date = (request.form.get("follow_up_date") or "").strip() or None
    if not summary:
        conn.close()
        flash("A discharge summary is required.", "error")
        return redirect(url_for("visits.detail", visit_id=admission["visit_id"]))

    visit_id = admission["visit_id"]

    # Take-home medications: each row is picked the same way a drug is
    # ordered in the Treatments tab (pharmacy-stock-aware), and is billed +
    # deducted from stock immediately, since this is a one-time take-home
    # dispense rather than an administered-over-time order.
    drug_names = request.form.getlist("med_drug_name")
    item_ids = request.form.getlist("med_inventory_item_id")
    routes = request.form.getlist("med_route")
    doses = request.form.getlist("med_dose")
    frequencies = request.form.getlist("med_frequency")
    durations = request.form.getlist("med_duration")
    instructions_list = request.form.getlist("med_instructions")
    quantities = request.form.getlist("med_quantity")

    med_summaries = []
    for drug_name, item_id_raw, route, dose, frequency, duration, instructions, qty_raw in zip(
        drug_names, item_ids, routes, doses, frequencies, durations, instructions_list, quantities
    ):
        drug_name = (drug_name or "").strip()
        if not drug_name:
            continue
        route = (route or "").strip() or None
        dose = (dose or "").strip() or None
        frequency = (frequency or "").strip() or None
        duration = (duration or "").strip() or None
        instructions = (instructions or "").strip() or None
        qty = float(qty_raw) if qty_raw else 0.0

        item = conn.execute("SELECT * FROM inventory_items WHERE id=?", (item_id_raw,)).fetchone() if item_id_raw else None
        unit_price = 0.0
        dispensed_qty = 0.0
        if item is not None and qty > 0:
            if item["stock_qty"] < qty:
                flash(f"Not enough stock of {item['name']} for the take-home prescription (only {item['stock_qty']} {item['unit']} left) — recorded without dispensing.", "error")
            else:
                conn.execute("UPDATE inventory_items SET stock_qty = stock_qty - ? WHERE id=?", (qty, item["id"]))
                add_invoice_item(conn, visit_id, f"{item['name']} (discharge medication)", "drug", qty, item["unit_price"])
                unit_price = item["unit_price"]
                dispensed_qty = qty

        conn.execute(
            "INSERT INTO discharge_medications (admission_id, inventory_item_id, drug_name, route, dose, "
            "frequency, duration, instructions, quantity, unit_price) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (admission_id, item["id"] if item else None, drug_name, route, dose, frequency, duration,
             instructions, dispensed_qty, unit_price),
        )
        parts = [p for p in [dose, route, frequency, (f"x {duration}" if duration else None)] if p]
        line = drug_name + (" " + " ".join(parts) if parts else "")
        if instructions:
            line += f" — {instructions}"
        med_summaries.append(line)

    discharge_medications = "; ".join(med_summaries) or None

    ward = conn.execute("SELECT * FROM wards WHERE id=?", (admission["ward_id"],)).fetchone()

    conn.execute(
        "UPDATE admissions SET status='discharged', discharged_by=?, discharged_at=datetime('now'), "
        "discharge_summary=?, follow_up_date=?, discharge_medications=? WHERE id=?",
        (g.user["id"], summary, follow_up_date, discharge_medications, admission_id),
    )
    conn.execute("UPDATE beds SET status='available' WHERE id=?", (admission["bed_id"],))
    conn.execute("UPDATE visits SET status='completed', completed_at=datetime('now'), seen_by=? WHERE id=?",
                 (g.user["id"], admission["visit_id"]))

    # Re-read admitted_at/discharged_at as stored, then bill the stay.
    refreshed = conn.execute("SELECT * FROM admissions WHERE id=?", (admission_id,)).fetchone()
    nights = _nights_stayed(refreshed["admitted_at"], refreshed["discharged_at"])
    add_invoice_item(
        conn, admission["visit_id"], f"Bed charge — {ward['name']}", "ward", nights, ward["nightly_rate"]
    )

    conn.commit()
    conn.close()
    flash(f"Patient discharged. {nights} night(s) billed for {ward['name']}.", "success")
    return redirect(url_for("printing.discharge_summary", admission_id=admission_id))
