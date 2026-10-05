import json
from flask import Blueprint, render_template, request, redirect, url_for, g, flash, jsonify
from auth import login_required, role_required
from db import get_db
from billing_logic import add_invoice_item

bp = Blueprint("visits", __name__, url_prefix="/visits")

# Priority ordering used to sort the waiting list (lower number = seen first)
PRIORITY_ORDER = "CASE priority WHEN 'Emergency' THEN 0 WHEN 'Urgent' THEN 1 ELSE 2 END"


@bp.route("/queue")
@login_required
def queue():
    conn = get_db()
    rows = conn.execute(
        "SELECT v.*, p.full_name, p.patient_code FROM visits v "
        "JOIN patients p ON p.id = v.patient_id "
        "WHERE v.status IN ('waiting', 'in_progress', 'admitted') "
        f"ORDER BY {PRIORITY_ORDER}, v.visit_date ASC"
    ).fetchall()
    conn.close()
    return render_template("visits/queue.html", visits=rows)


@bp.route("/checkin/<int:patient_id>", methods=["GET", "POST"])
@login_required
@role_required("Reception")
def checkin(patient_id):
    conn = get_db()
    patient = conn.execute("SELECT * FROM patients WHERE id=?", (patient_id,)).fetchone()
    if patient is None:
        conn.close()
        flash("Patient not found.", "error")
        return redirect(url_for("patients.index"))

    consultations = conn.execute(
        "SELECT * FROM billables WHERE category='consultation' AND active=1 ORDER BY name"
    ).fetchall()

    if request.method == "POST":
        billable_id = request.form.get("billable_id")
        priority = request.form.get("priority") or "Routine"
        if priority not in ("Emergency", "Urgent", "Routine"):
            priority = "Routine"
        complaint_text = (request.form.get("complaint") or "").strip()

        cur = conn.execute(
            "INSERT INTO visits (patient_id, created_by, status, priority) VALUES (?, ?, 'waiting', ?)",
            (patient_id, g.user["id"], priority),
        )
        visit_id = cur.lastrowid

        if complaint_text:
            conn.execute(
                "INSERT INTO complaints (visit_id, recorded_by, text) VALUES (?, ?, ?)",
                (visit_id, g.user["id"], complaint_text),
            )

        # Triage vitals — only recorded if the receptionist entered at least
        # one value, so an empty triage doesn't clutter the vitals log.
        vitals_fields = {
            "bp": request.form.get("bp") or None,
            "pulse": request.form.get("pulse") or None,
            "temp_c": request.form.get("temp_c") or None,
            "resp_rate": request.form.get("resp_rate") or None,
            "spo2": request.form.get("spo2") or None,
            "weight_kg": request.form.get("weight_kg") or None,
            "height_cm": request.form.get("height_cm") or None,
            "rbs": request.form.get("rbs") or None,
            "other": (request.form.get("vitals_other") or "").strip() or None,
        }
        if any(vitals_fields.values()):
            conn.execute(
                "INSERT INTO vitals_records (visit_id, recorded_by, bp, pulse, temp_c, resp_rate, "
                "spo2, weight_kg, height_cm, rbs, other) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    visit_id, g.user["id"], vitals_fields["bp"], vitals_fields["pulse"],
                    vitals_fields["temp_c"], vitals_fields["resp_rate"], vitals_fields["spo2"],
                    vitals_fields["weight_kg"], vitals_fields["height_cm"], vitals_fields["rbs"],
                    vitals_fields["other"],
                ),
            )

        if billable_id:
            billable = conn.execute("SELECT * FROM billables WHERE id=?", (billable_id,)).fetchone()
            if billable:
                add_invoice_item(conn, visit_id, billable["name"], "consultation", 1, billable["price"])

        conn.commit()
        conn.close()
        flash(f"{patient['full_name']} added to the waiting list.", "success")
        return redirect(url_for("visits.queue"))

    conn.close()
    return render_template("visits/checkin.html", patient=patient, consultations=consultations)


def gather_encounter(conn, visit_id):
    """Assemble every tab's data for the encounter record page."""
    admission = conn.execute(
        "SELECT a.*, w.name AS ward_name, w.nightly_rate, b.name AS bed_name, "
        "u1.full_name AS admitted_by_name, u2.full_name AS discharged_by_name "
        "FROM admissions a JOIN wards w ON w.id=a.ward_id JOIN beds b ON b.id=a.bed_id "
        "LEFT JOIN users u1 ON u1.id=a.admitted_by LEFT JOIN users u2 ON u2.id=a.discharged_by "
        "WHERE a.visit_id=?",
        (visit_id,),
    ).fetchone()

    vitals = conn.execute(
        "SELECT vr.*, u.full_name AS recorded_by_name FROM vitals_records vr "
        "LEFT JOIN users u ON u.id=vr.recorded_by WHERE vr.visit_id=? ORDER BY vr.recorded_at DESC",
        (visit_id,),
    ).fetchall()
    complaints = conn.execute(
        "SELECT c.*, u.full_name AS recorded_by_name FROM complaints c "
        "LEFT JOIN users u ON u.id=c.recorded_by WHERE c.visit_id=? ORDER BY c.recorded_at DESC",
        (visit_id,),
    ).fetchall()
    history = conn.execute(
        "SELECT h.*, u.full_name AS recorded_by_name FROM history_records h "
        "LEFT JOIN users u ON u.id=h.recorded_by WHERE h.visit_id=? ORDER BY h.recorded_at DESC",
        (visit_id,),
    ).fetchall()
    examinations = conn.execute(
        "SELECT e.*, u.full_name AS recorded_by_name FROM examination_records e "
        "LEFT JOIN users u ON u.id=e.recorded_by WHERE e.visit_id=? ORDER BY e.recorded_at DESC",
        (visit_id,),
    ).fetchall()
    diagnoses = conn.execute(
        "SELECT d.*, u.full_name AS recorded_by_name FROM diagnoses d "
        "LEFT JOIN users u ON u.id=d.recorded_by WHERE d.visit_id=? ORDER BY d.recorded_at DESC",
        (visit_id,),
    ).fetchall()
    notes = conn.execute(
        "SELECT n.*, u.full_name AS author_name FROM encounter_notes n "
        "LEFT JOIN users u ON u.id=n.author_id WHERE n.visit_id=? ORDER BY n.recorded_at DESC",
        (visit_id,),
    ).fetchall()
    lab_orders = conn.execute(
        "SELECT lo.*, b.name AS billable_name FROM lab_orders lo "
        "JOIN billables b ON b.id=lo.billable_id WHERE lo.visit_id=? ORDER BY lo.ordered_at DESC",
        (visit_id,),
    ).fetchall()
    radiology_requests = conn.execute(
        "SELECT rr.*, b.name AS billable_name FROM radiology_requests rr "
        "JOIN billables b ON b.id=rr.billable_id WHERE rr.visit_id=? ORDER BY rr.requested_at DESC",
        (visit_id,),
    ).fetchall()

    orders = conn.execute(
        "SELECT * FROM treatment_orders WHERE visit_id=? ORDER BY ordered_at DESC", (visit_id,)
    ).fetchall()
    treatment_orders = []
    for o in orders:
        dose_rows = conn.execute(
            "SELECT da.*, u.full_name AS administered_by_name, "
            "i.name AS item_name, i.unit AS item_unit, b.name AS billable_name "
            "FROM dose_administrations da "
            "LEFT JOIN users u ON u.id=da.administered_by "
            "LEFT JOIN inventory_items i ON i.id=da.inventory_item_id "
            "LEFT JOIN billables b ON b.id=da.billable_id "
            "WHERE da.treatment_order_id=? ORDER BY da.administered_at DESC",
            (o["id"],),
        ).fetchall()
        doses = []
        for d in dose_rows:
            dose_materials = conn.execute(
                "SELECT dm.*, i.name AS item_name, i.unit AS item_unit FROM dose_materials dm "
                "JOIN inventory_items i ON i.id=dm.inventory_item_id "
                "WHERE dm.dose_administration_id=?",
                (d["id"],),
            ).fetchall()
            doses.append({"dose": d, "materials": dose_materials})
        treatment_orders.append({"order": o, "doses": doses, "dose_count": len(doses)})

    drugs = conn.execute(
        "SELECT * FROM inventory_items WHERE active=1 AND item_type='drug' ORDER BY name"
    ).fetchall()
    procedure_billables = conn.execute(
        "SELECT * FROM billables WHERE category='procedure' AND active=1 ORDER BY name"
    ).fetchall()
    materials = conn.execute(
        "SELECT * FROM inventory_items WHERE active=1 ORDER BY name"
    ).fetchall()

    available_beds = conn.execute(
        "SELECT b.*, w.name AS ward_name, w.nightly_rate FROM beds b "
        "JOIN wards w ON w.id=b.ward_id WHERE b.status='available' AND w.active=1 "
        "ORDER BY w.name, b.name"
    ).fetchall()

    complaint_options = conn.execute(
        "SELECT text FROM complaint_master WHERE active=1 ORDER BY text"
    ).fetchall()

    drugs_json = json.dumps(
        [{"id": d["id"], "name": d["name"], "unit": d["unit"], "stock_qty": d["stock_qty"]} for d in drugs]
    )

    return {
        "admission": admission,
        "vitals": vitals,
        "complaints": complaints,
        "history": history,
        "examinations": examinations,
        "diagnoses": diagnoses,
        "notes": notes,
        "lab_orders": lab_orders,
        "radiology_requests": radiology_requests,
        "treatment_orders": treatment_orders,
        "drugs": drugs,
        "procedure_billables": procedure_billables,
        "materials": materials,
        "available_beds": available_beds,
        "complaint_options": complaint_options,
        "drugs_json": drugs_json,
    }


@bp.route("/api/diagnoses-search")
@login_required
def diagnoses_search():
    """JSON search over the diagnosis reference list (ICD-10 + custom) for
    the search-as-you-type box in the Diagnoses tab. Served from the server
    rather than embedded in the page since ICD-10 alone is ~12,000 entries."""
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify([])
    conn = get_db()
    prefix = f"{q}%"
    contains = f"%{q}%"
    rows = conn.execute(
        "SELECT code, text FROM diagnosis_master WHERE active=1 "
        "AND (text LIKE ? OR code LIKE ?) "
        "ORDER BY CASE WHEN text LIKE ? OR code LIKE ? THEN 0 ELSE 1 END, text "
        "LIMIT 20",
        (contains, contains, prefix, prefix),
    ).fetchall()
    conn.close()
    return jsonify([{"code": r["code"], "text": r["text"]} for r in rows])


@bp.route("/<int:visit_id>")
@login_required
@role_required("Reception", "Nurse", "Clinician")
def detail(visit_id):
    conn = get_db()
    visit = conn.execute("SELECT * FROM visits WHERE id=?", (visit_id,)).fetchone()
    if visit is None:
        conn.close()
        flash("Visit not found.", "error")
        return redirect(url_for("visits.queue"))
    patient = conn.execute("SELECT * FROM patients WHERE id=?", (visit["patient_id"],)).fetchone()
    ctx = gather_encounter(conn, visit_id)
    conn.close()
    return render_template("visits/detail.html", visit=visit, patient=patient, **ctx)


@bp.route("/<int:visit_id>/vitals", methods=["POST"])
@login_required
@role_required("Nurse", "Clinician")
def add_vitals(visit_id):
    conn = get_db()
    conn.execute(
        "INSERT INTO vitals_records (visit_id, recorded_by, bp, pulse, temp_c, resp_rate, "
        "spo2, weight_kg, height_cm, rbs, other) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            visit_id, g.user["id"],
            request.form.get("bp") or None,
            request.form.get("pulse") or None,
            request.form.get("temp_c") or None,
            request.form.get("resp_rate") or None,
            request.form.get("spo2") or None,
            request.form.get("weight_kg") or None,
            request.form.get("height_cm") or None,
            request.form.get("rbs") or None,
            (request.form.get("other") or "").strip() or None,
        ),
    )
    conn.commit()
    conn.close()
    flash("Vitals recorded.", "success")
    return redirect(url_for("visits.detail", visit_id=visit_id) + "#vitals")


@bp.route("/<int:visit_id>/complaint", methods=["POST"])
@login_required
@role_required("Clinician")
def add_complaint(visit_id):
    text = (request.form.get("text") or "").strip()
    duration = (request.form.get("duration") or "").strip() or None
    if text:
        conn = get_db()
        conn.execute(
            "INSERT INTO complaints (visit_id, recorded_by, text, duration) VALUES (?, ?, ?, ?)",
            (visit_id, g.user["id"], text, duration),
        )
        conn.commit()
        conn.close()
        flash("Complaint added.", "success")
    return redirect(url_for("visits.detail", visit_id=visit_id) + "#complaints")


@bp.route("/<int:visit_id>/history", methods=["POST"])
@login_required
@role_required("Clinician")
def add_history(visit_id):
    text = (request.form.get("text") or "").strip()
    if text:
        conn = get_db()
        conn.execute(
            "INSERT INTO history_records (visit_id, recorded_by, text) VALUES (?, ?, ?)",
            (visit_id, g.user["id"], text),
        )
        conn.commit()
        conn.close()
        flash("History added.", "success")
    return redirect(url_for("visits.detail", visit_id=visit_id) + "#history")


@bp.route("/<int:visit_id>/examination", methods=["POST"])
@login_required
@role_required("Clinician")
def add_examination(visit_id):
    text = (request.form.get("text") or "").strip()
    if text:
        conn = get_db()
        conn.execute(
            "INSERT INTO examination_records (visit_id, recorded_by, text) VALUES (?, ?, ?)",
            (visit_id, g.user["id"], text),
        )
        conn.commit()
        conn.close()
        flash("Examination findings added.", "success")
    return redirect(url_for("visits.detail", visit_id=visit_id) + "#examination")


@bp.route("/<int:visit_id>/diagnosis", methods=["POST"])
@login_required
@role_required("Clinician")
def add_diagnosis(visit_id):
    text = (request.form.get("text") or "").strip()
    icd10_code = (request.form.get("icd10_code") or "").strip() or None
    status = request.form.get("status") or "Preliminary"
    if status not in ("Preliminary", "Confirmed"):
        status = "Preliminary"
    if text:
        conn = get_db()
        conn.execute(
            "INSERT INTO diagnoses (visit_id, recorded_by, text, icd10_code, status) VALUES (?, ?, ?, ?, ?)",
            (visit_id, g.user["id"], text, icd10_code, status),
        )
        conn.commit()
        conn.close()
        flash("Diagnosis added.", "success")
    return redirect(url_for("visits.detail", visit_id=visit_id) + "#diagnoses")


@bp.route("/<int:visit_id>/note", methods=["POST"])
@login_required
@role_required("Nurse", "Clinician")
def add_note(visit_id):
    text = (request.form.get("text") or "").strip()
    note_type = request.form.get("note_type") or "nursing"
    if note_type not in ("nursing", "doctor"):
        note_type = "nursing"
    if text:
        conn = get_db()
        conn.execute(
            "INSERT INTO encounter_notes (visit_id, author_id, note_type, text) VALUES (?, ?, ?, ?)",
            (visit_id, g.user["id"], note_type, text),
        )
        conn.commit()
        conn.close()
        flash("Note added.", "success")
    return redirect(url_for("visits.detail", visit_id=visit_id) + "#notes")


@bp.route("/<int:visit_id>/treatment", methods=["POST"])
@login_required
@role_required("Clinician")
def add_treatment_order(visit_id):
    order_type = request.form.get("order_type") or "drug"
    conn = get_db()

    if order_type == "drug":
        drug_name = (request.form.get("drug_name") or "").strip()
        inventory_item_id = request.form.get("inventory_item_id") or None
        route = (request.form.get("route") or "").strip() or None
        dose = (request.form.get("dose") or "").strip() or None
        frequency = (request.form.get("frequency") or "").strip()
        if frequency == "Other":
            frequency = (request.form.get("frequency_other") or "").strip()
        frequency = frequency or None
        duration = (request.form.get("duration") or "").strip() or None
        instructions = (request.form.get("instructions") or "").strip() or None

        if inventory_item_id:
            item = conn.execute(
                "SELECT id FROM inventory_items WHERE id=?", (inventory_item_id,)
            ).fetchone()
            if item is None:
                inventory_item_id = None

        if not drug_name:
            conn.close()
            flash("Enter a drug name.", "error")
            return redirect(url_for("visits.detail", visit_id=visit_id) + "#treatments")

        conn.execute(
            "INSERT INTO treatment_orders (visit_id, order_type, inventory_item_id, description, "
            "route, dose, frequency, duration, instructions, ordered_by) VALUES (?, 'drug', ?, ?, ?, ?, ?, ?, ?, ?)",
            (visit_id, inventory_item_id, drug_name, route, dose, frequency, duration, instructions, g.user["id"]),
        )
        conn.commit()
        conn.close()
        flash("Treatment ordered.", "success")
    else:
        billable_id = request.form.get("billable_id") or None
        billable = conn.execute("SELECT * FROM billables WHERE id=?", (billable_id,)).fetchone() if billable_id else None
        if billable is None:
            conn.close()
            flash("Select a procedure from the list.", "error")
            return redirect(url_for("visits.detail", visit_id=visit_id) + "#treatments")
        conn.execute(
            "INSERT INTO treatment_orders (visit_id, order_type, billable_id, description, ordered_by) "
            "VALUES (?, 'procedure', ?, ?, ?)",
            (visit_id, billable["id"], billable["name"], g.user["id"]),
        )
        conn.commit()
        conn.close()
        flash("Treatment ordered.", "success")

    return redirect(url_for("visits.detail", visit_id=visit_id) + "#treatments")


@bp.route("/treatment/<int:order_id>/administer", methods=["POST"])
@login_required
@role_required("Nurse", "Clinician")
def administer_dose(order_id):
    conn = get_db()
    order = conn.execute("SELECT * FROM treatment_orders WHERE id=?", (order_id,)).fetchone()
    if order is None:
        conn.close()
        flash("Treatment order not found.", "error")
        return redirect(url_for("visits.queue"))

    visit_id = order["visit_id"]
    quantity = float(request.form.get("quantity") or 1)
    notes = (request.form.get("notes") or "").strip() or None
    dose_id = None

    if order["order_type"] == "drug":
        item_id = request.form.get("inventory_item_id")
        item = conn.execute("SELECT * FROM inventory_items WHERE id=?", (item_id,)).fetchone() if item_id else None
        if item is None:
            flash("Select which inventory item this dose used.", "error")
        elif quantity <= 0:
            flash("Quantity must be greater than zero.", "error")
        elif item["stock_qty"] < quantity:
            flash(f"Not enough stock of {item['name']} (only {item['stock_qty']} {item['unit']} left).", "error")
        else:
            cur = conn.execute(
                "INSERT INTO dose_administrations (treatment_order_id, inventory_item_id, quantity, "
                "unit_price, administered_by, notes) VALUES (?, ?, ?, ?, ?, ?)",
                (order_id, item["id"], quantity, item["unit_price"], g.user["id"], notes),
            )
            dose_id = cur.lastrowid
            conn.execute("UPDATE inventory_items SET stock_qty = stock_qty - ? WHERE id=?", (quantity, item["id"]))
            add_invoice_item(conn, visit_id, f"{item['name']} (dose)", "drug", quantity, item["unit_price"])
            flash(f"Dose recorded: {quantity} {item['unit']} of {item['name']}.", "success")
    else:
        # The order itself carries the billable now (picked from the admin's
        # procedure catalog when ordered) — fall back to the submitted
        # billable_id only for older orders recorded before that existed.
        billable_id = order["billable_id"] or request.form.get("billable_id")
        billable = conn.execute("SELECT * FROM billables WHERE id=?", (billable_id,)).fetchone() if billable_id else None
        if billable is None:
            flash("Select which billable this administration used.", "error")
        else:
            cur = conn.execute(
                "INSERT INTO dose_administrations (treatment_order_id, billable_id, quantity, "
                "unit_price, administered_by, notes) VALUES (?, ?, ?, ?, ?, ?)",
                (order_id, billable["id"], quantity, billable["price"], g.user["id"], notes),
            )
            dose_id = cur.lastrowid
            add_invoice_item(conn, visit_id, f"{billable['name']} (given)", "procedure", quantity, billable["price"])
            flash(f"Administration recorded: {billable['name']}.", "success")

    # Consumable billables used while giving this dose (syringe, cotton swabs,
    # gloves...) — each one is billed and deducted from stock, same pattern
    # as materials used in a procedure record.
    if dose_id:
        item_ids = request.form.getlist("material_item_id")
        quantities = request.form.getlist("material_quantity")
        for item_id_raw, qty_raw in zip(item_ids, quantities):
            if not item_id_raw or not qty_raw:
                continue
            qty = float(qty_raw)
            if qty <= 0:
                continue
            mat = conn.execute("SELECT * FROM inventory_items WHERE id=?", (int(item_id_raw),)).fetchone()
            if mat is None:
                continue
            if mat["stock_qty"] < qty:
                flash(f"Not enough stock of {mat['name']} — skipped.", "error")
                continue
            conn.execute(
                "INSERT INTO dose_materials (dose_administration_id, inventory_item_id, quantity, unit_price) "
                "VALUES (?, ?, ?, ?)",
                (dose_id, mat["id"], qty, mat["unit_price"]),
            )
            conn.execute("UPDATE inventory_items SET stock_qty = stock_qty - ? WHERE id=?", (qty, mat["id"]))
            add_invoice_item(conn, visit_id, f"{mat['name']} (used)", "material", qty, mat["unit_price"])

    conn.commit()
    conn.close()
    return redirect(url_for("visits.detail", visit_id=visit_id) + "#treatments")


@bp.route("/<int:visit_id>/finalize", methods=["POST"])
@login_required
@role_required("Clinician")
def finalize(visit_id):
    conn = get_db()
    admission = conn.execute("SELECT * FROM admissions WHERE visit_id=? AND status='admitted'", (visit_id,)).fetchone()
    if admission:
        conn.close()
        flash("This patient is currently admitted — discharge them first to complete the encounter.", "error")
        return redirect(url_for("visits.detail", visit_id=visit_id))
    conn.execute(
        "UPDATE visits SET status='completed', seen_by=?, completed_at=datetime('now') WHERE id=?",
        (g.user["id"], visit_id),
    )
    conn.commit()
    conn.close()
    flash("Visit completed.", "success")
    return redirect(url_for("visits.queue"))
