from flask import Blueprint, render_template, abort
from auth import login_required
from db import get_db
from billing_logic import invoice_totals, bill_printing
from routes.visits import gather_encounter

bp = Blueprint("printing", __name__, url_prefix="/print")


def _referrals_for_visit(conn, visit_id):
    return conn.execute(
        "SELECT r.*, u.full_name AS created_by_name FROM referrals r "
        "LEFT JOIN users u ON u.id=r.created_by WHERE r.visit_id=? ORDER BY r.created_at",
        (visit_id,),
    ).fetchall()


@bp.route("/prescription/<int:visit_id>")
@login_required
def prescription(visit_id):
    conn = get_db()
    visit = conn.execute(
        "SELECT v.*, u.full_name AS clinician_name FROM visits v "
        "LEFT JOIN users u ON u.id = v.seen_by WHERE v.id=?", (visit_id,)
    ).fetchone()
    if visit is None:
        conn.close()
        abort(404)
    patient = conn.execute("SELECT * FROM patients WHERE id=?", (visit["patient_id"],)).fetchone()
    diagnoses = conn.execute(
        "SELECT text, icd10_code, status FROM diagnoses WHERE visit_id=? ORDER BY recorded_at", (visit_id,)
    ).fetchall()
    drug_orders = conn.execute(
        "SELECT * FROM treatment_orders WHERE visit_id=? AND order_type='drug' ORDER BY ordered_at",
        (visit_id,),
    ).fetchall()
    # Administration log (MAR) per drug order, so a multi-day admission's
    # printed medication record shows what was actually given, not just
    # what was ordered.
    doses_by_order = {}
    for o in drug_orders:
        doses_by_order[o["id"]] = conn.execute(
            "SELECT da.*, u.full_name AS administered_by_name FROM dose_administrations da "
            "LEFT JOIN users u ON u.id=da.administered_by WHERE da.treatment_order_id=? "
            "ORDER BY da.administered_at",
            (o["id"],),
        ).fetchall()
    dispensed = conn.execute(
        "SELECT d.*, i.name, i.unit FROM dispenses d JOIN inventory_items i ON i.id = d.inventory_item_id "
        "WHERE d.visit_id=? ORDER BY d.dispensed_at", (visit_id,)
    ).fetchall()
    bill_printing(conn, visit_id, "Prescription")
    conn.commit()
    conn.close()
    return render_template(
        "print/prescription.html", visit=visit, patient=patient, dispensed=dispensed,
        diagnoses=diagnoses, drug_orders=drug_orders, doses_by_order=doses_by_order,
    )


@bp.route("/referral/<int:referral_id>")
@login_required
def referral(referral_id):
    conn = get_db()
    ref = conn.execute(
        "SELECT r.*, u.full_name AS clinician_name FROM referrals r "
        "LEFT JOIN users u ON u.id = r.created_by WHERE r.id=?", (referral_id,)
    ).fetchone()
    if ref is None:
        conn.close()
        abort(404)
    visit = conn.execute("SELECT * FROM visits WHERE id=?", (ref["visit_id"],)).fetchone()
    patient = conn.execute("SELECT * FROM patients WHERE id=?", (visit["patient_id"],)).fetchone()
    bill_printing(conn, ref["visit_id"], "Referral letter")
    conn.commit()
    conn.close()
    return render_template("print/referral.html", ref=ref, visit=visit, patient=patient)


@bp.route("/visit-summary/<int:visit_id>")
@login_required
def visit_summary(visit_id):
    conn = get_db()
    visit = conn.execute(
        "SELECT v.*, u.full_name AS clinician_name FROM visits v "
        "LEFT JOIN users u ON u.id = v.seen_by WHERE v.id=?", (visit_id,)
    ).fetchone()
    if visit is None:
        conn.close()
        abort(404)
    patient = conn.execute("SELECT * FROM patients WHERE id=?", (visit["patient_id"],)).fetchone()
    ctx = gather_encounter(conn, visit_id)
    referrals = _referrals_for_visit(conn, visit_id)
    bill_printing(conn, visit_id, "Visit summary")
    conn.commit()
    conn.close()
    return render_template(
        "print/visit_summary.html", visit=visit, patient=patient, referrals=referrals, **ctx
    )


@bp.route("/complete-record/<int:patient_id>")
@login_required
def complete_record(patient_id):
    conn = get_db()
    patient = conn.execute("SELECT * FROM patients WHERE id=?", (patient_id,)).fetchone()
    if patient is None:
        conn.close()
        abort(404)
    visit_rows = conn.execute(
        "SELECT v.*, u.full_name AS clinician_name FROM visits v "
        "LEFT JOIN users u ON u.id = v.seen_by WHERE v.patient_id=? ORDER BY v.visit_date",
        (patient_id,),
    ).fetchall()

    # Full encounter detail for every visit this patient has ever had — the
    # same data the clinician sees in each tab of the encounter page, not
    # just a one-line summary — so this one document is a complete chart.
    visits = []
    for v in visit_rows:
        ctx = gather_encounter(conn, v["id"])
        ctx["referrals"] = _referrals_for_visit(conn, v["id"])
        ctx["visit"] = v
        visits.append(ctx)

    # This document spans the patient's whole history rather than one
    # visit, so there's no single invoice it naturally belongs to — bill it
    # to their most recent visit. A patient with no visits yet has nothing
    # to bill it to, so it's simply not billed.
    if visit_rows:
        bill_printing(conn, visit_rows[-1]["id"], "Complete patient record")
        conn.commit()
    conn.close()
    return render_template("print/complete_record.html", patient=patient, visits=visits)


@bp.route("/discharge-summary/<int:admission_id>")
@login_required
def discharge_summary(admission_id):
    conn = get_db()
    admission = conn.execute(
        "SELECT a.*, w.name AS ward_name, w.nightly_rate, b.name AS bed_name, "
        "u1.full_name AS admitted_by_name, u2.full_name AS discharged_by_name "
        "FROM admissions a "
        "JOIN wards w ON w.id=a.ward_id JOIN beds b ON b.id=a.bed_id "
        "LEFT JOIN users u1 ON u1.id=a.admitted_by LEFT JOIN users u2 ON u2.id=a.discharged_by "
        "WHERE a.id=?",
        (admission_id,),
    ).fetchone()
    if admission is None:
        conn.close()
        abort(404)
    visit = conn.execute("SELECT * FROM visits WHERE id=?", (admission["visit_id"],)).fetchone()
    patient = conn.execute("SELECT * FROM patients WHERE id=?", (visit["patient_id"],)).fetchone()
    diagnoses = conn.execute(
        "SELECT text FROM diagnoses WHERE visit_id=? ORDER BY recorded_at", (visit["id"],)
    ).fetchall()
    bill_printing(conn, admission["visit_id"], "Discharge summary")
    conn.commit()
    conn.close()
    return render_template(
        "print/discharge_summary.html", admission=admission, visit=visit, patient=patient,
        diagnoses=[d["text"] for d in diagnoses],
    )


@bp.route("/receipt/<int:invoice_id>")
@login_required
def receipt(invoice_id):
    conn = get_db()
    inv = conn.execute("SELECT * FROM invoices WHERE id=?", (invoice_id,)).fetchone()
    if inv is None:
        conn.close()
        abort(404)
    visit = conn.execute("SELECT * FROM visits WHERE id=?", (inv["visit_id"],)).fetchone()
    patient = conn.execute("SELECT * FROM patients WHERE id=?", (visit["patient_id"],)).fetchone()
    # Bill before reading items/totals so the receipt being printed right
    # now also reflects its own printing charge, same as any other charge.
    bill_printing(conn, inv["visit_id"], "Receipt")
    conn.commit()
    items = conn.execute(
        "SELECT * FROM invoice_items WHERE invoice_id=? ORDER BY created_at", (invoice_id,)
    ).fetchall()
    payments = conn.execute(
        "SELECT * FROM payments WHERE invoice_id=? ORDER BY paid_at", (invoice_id,)
    ).fetchall()
    total, paid, balance = invoice_totals(conn, invoice_id)
    conn.close()
    return render_template(
        "print/receipt.html", visit=visit, patient=patient, items=items,
        payments=payments, total=total, paid=paid, balance=balance, invoice=inv,
    )
