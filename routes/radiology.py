from flask import Blueprint, render_template, request, redirect, url_for, g, flash
from auth import login_required, role_required
from db import get_db
from billing_logic import add_invoice_item

bp = Blueprint("radiology", __name__, url_prefix="/radiology")


@bp.route("/request/<int:visit_id>", methods=["GET", "POST"])
@login_required
@role_required("Clinician")
def request_imaging(visit_id):
    conn = get_db()
    visit = conn.execute("SELECT * FROM visits WHERE id=?", (visit_id,)).fetchone()
    if visit is None:
        conn.close()
        flash("Visit not found.", "error")
        return redirect(url_for("visits.queue"))
    patient = conn.execute("SELECT * FROM patients WHERE id=?", (visit["patient_id"],)).fetchone()
    imaging_types = conn.execute(
        "SELECT * FROM billables WHERE category='radiology' AND active=1 ORDER BY name"
    ).fetchall()

    if request.method == "POST":
        billable_id = int(request.form["billable_id"])
        reason = request.form.get("reason", "")
        billable = conn.execute("SELECT * FROM billables WHERE id=?", (billable_id,)).fetchone()
        if billable:
            conn.execute(
                "INSERT INTO radiology_requests (visit_id, billable_id, reason, ordered_by) "
                "VALUES (?, ?, ?, ?)",
                (visit_id, billable_id, reason, g.user["id"]),
            )
            add_invoice_item(conn, visit_id, billable["name"], "radiology", 1, billable["price"])
            conn.commit()
            flash(f"{billable['name']} requested.", "success")

    requests_ = conn.execute(
        "SELECT rr.*, b.name AS imaging_name FROM radiology_requests rr "
        "JOIN billables b ON b.id = rr.billable_id "
        "WHERE rr.visit_id=? ORDER BY rr.requested_at DESC",
        (visit_id,),
    ).fetchall()
    conn.close()
    return render_template(
        "radiology/request.html", visit=visit, patient=patient,
        imaging_types=imaging_types, requests=requests_,
    )


@bp.route("/done/<int:request_id>", methods=["POST"])
@login_required
@role_required("Clinician")
def mark_done(request_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM radiology_requests WHERE id=?", (request_id,)).fetchone()
    if row is None:
        conn.close()
        flash("Request not found.", "error")
        return redirect(url_for("visits.queue"))
    findings = request.form.get("findings_text", "")
    conn.execute(
        "UPDATE radiology_requests SET status='done', findings_text=?, done_at=datetime('now') WHERE id=?",
        (findings, request_id),
    )
    conn.commit()
    visit_id = row["visit_id"]
    conn.close()
    flash("Marked done.", "success")
    return redirect(url_for("radiology.request_imaging", visit_id=visit_id))
