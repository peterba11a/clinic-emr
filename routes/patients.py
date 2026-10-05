from flask import Blueprint, render_template, request, redirect, url_for, g, flash
from auth import login_required, role_required
from db import get_db, generate_patient_code

bp = Blueprint("patients", __name__, url_prefix="/patients")


@bp.route("/")
@login_required
def index():
    q = request.args.get("q", "").strip()
    conn = get_db()
    if q:
        like = f"%{q}%"
        rows = conn.execute(
            "SELECT * FROM patients WHERE full_name LIKE ? OR patient_code LIKE ? "
            "ORDER BY full_name LIMIT 50",
            (like, like),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM patients ORDER BY created_at DESC LIMIT 25"
        ).fetchall()
    conn.close()
    return render_template("patients/index.html", patients=rows, q=q)


@bp.route("/new", methods=["GET", "POST"])
@login_required
@role_required("Reception")
def new():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        dob = request.form.get("dob") or None
        age_years = request.form.get("age_years") or None
        sex = request.form.get("sex") or None
        phone = request.form.get("phone") or None
        village = request.form.get("village") or None

        if not full_name:
            flash("Patient name is required.", "error")
            return render_template("patients/new.html", form=request.form)

        conn = get_db()
        code = generate_patient_code(conn)
        cur = conn.execute(
            "INSERT INTO patients (patient_code, full_name, dob, age_years, sex, phone, village) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (code, full_name, dob, age_years, sex, phone, village),
        )
        patient_id = cur.lastrowid
        conn.commit()
        conn.close()
        flash(f"Patient registered as {code}.", "success")
        return redirect(url_for("patients.view", patient_id=patient_id))

    return render_template("patients/new.html", form={})


@bp.route("/<int:patient_id>")
@login_required
def view(patient_id):
    conn = get_db()
    patient = conn.execute("SELECT * FROM patients WHERE id=?", (patient_id,)).fetchone()
    if patient is None:
        conn.close()
        flash("Patient not found.", "error")
        return redirect(url_for("patients.index"))
    visits = conn.execute(
        "SELECT v.*, u.full_name AS seen_by_name, "
        "(SELECT text FROM complaints WHERE visit_id=v.id ORDER BY recorded_at DESC LIMIT 1) AS latest_complaint, "
        "(SELECT text FROM diagnoses WHERE visit_id=v.id ORDER BY recorded_at DESC LIMIT 1) AS latest_diagnosis "
        "FROM visits v "
        "LEFT JOIN users u ON u.id = v.seen_by "
        "WHERE v.patient_id=? ORDER BY v.visit_date DESC",
        (patient_id,),
    ).fetchall()
    conn.close()
    return render_template("patients/view.html", patient=patient, visits=visits)
