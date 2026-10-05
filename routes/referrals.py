from flask import Blueprint, render_template, request, redirect, url_for, g, flash
from auth import login_required, role_required
from db import get_db

bp = Blueprint("referrals", __name__, url_prefix="/referrals")


@bp.route("/new/<int:visit_id>", methods=["GET", "POST"])
@login_required
@role_required("Clinician")
def new(visit_id):
    conn = get_db()
    visit = conn.execute("SELECT * FROM visits WHERE id=?", (visit_id,)).fetchone()
    if visit is None:
        conn.close()
        flash("Visit not found.", "error")
        return redirect(url_for("visits.queue"))
    patient = conn.execute("SELECT * FROM patients WHERE id=?", (visit["patient_id"],)).fetchone()

    if request.method == "POST":
        destination = request.form["destination"].strip()
        reason = request.form.get("reason", "")
        cur = conn.execute(
            "INSERT INTO referrals (visit_id, destination, reason, created_by) VALUES (?, ?, ?, ?)",
            (visit_id, destination, reason, g.user["id"]),
        )
        referral_id = cur.lastrowid
        conn.commit()
        conn.close()
        flash("Referral created.", "success")
        return redirect(url_for("printing.referral", referral_id=referral_id))

    referrals = conn.execute(
        "SELECT * FROM referrals WHERE visit_id=? ORDER BY created_at DESC", (visit_id,)
    ).fetchall()
    conn.close()
    return render_template("referrals/new.html", visit=visit, patient=patient, referrals=referrals)
