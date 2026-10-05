import json
import os
from pathlib import Path
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, send_from_directory, abort
from werkzeug.utils import secure_filename
from auth import login_required, role_required, hash_password
from db import get_db, BASE_DIR, RESOURCES_DIR, get_setting, set_setting
from backup import run_backup
from mdns_advertise import get_lan_ip

SERVER_PORT = 8080

bp = Blueprint("admin", __name__, url_prefix="/admin")

UPLOAD_DIR = BASE_DIR / "static" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_STATUS_PATH = BASE_DIR / "instance" / "backup_status.json"


# ---------- Users & roles ----------

@bp.route("/users")
@login_required
@role_required("Admin")
def users():
    conn = get_db()
    rows = conn.execute("SELECT * FROM users ORDER BY full_name").fetchall()
    user_roles = {}
    for u in rows:
        roles = conn.execute(
            "SELECT r.name FROM roles r JOIN user_roles ur ON ur.role_id=r.id WHERE ur.user_id=?",
            (u["id"],),
        ).fetchall()
        user_roles[u["id"]] = [r["name"] for r in roles]
    all_roles = conn.execute("SELECT * FROM roles ORDER BY name").fetchall()
    conn.close()
    return render_template("admin/users.html", users=rows, user_roles=user_roles, all_roles=all_roles)


@bp.route("/users/new", methods=["GET", "POST"])
@login_required
@role_required("Admin")
def new_user():
    conn = get_db()
    all_roles = conn.execute("SELECT * FROM roles ORDER BY name").fetchall()
    if request.method == "POST":
        username = request.form["username"].strip()
        full_name = request.form["full_name"].strip()
        password = request.form["password"]
        role_ids = request.form.getlist("role_ids")
        existing = conn.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone()
        if existing:
            flash("That username is already taken.", "error")
        elif not role_ids:
            flash("Select at least one role.", "error")
        else:
            cur = conn.execute(
                "INSERT INTO users (username, password_hash, full_name) VALUES (?, ?, ?)",
                (username, hash_password(password), full_name),
            )
            user_id = cur.lastrowid
            for rid in role_ids:
                conn.execute(
                    "INSERT INTO user_roles (user_id, role_id) VALUES (?, ?)", (user_id, rid)
                )
            conn.commit()
            conn.close()
            flash(f"User {username} created.", "success")
            return redirect(url_for("admin.users"))
    conn.close()
    return render_template("admin/user_form.html", all_roles=all_roles, user=None, current_role_ids=[])


@bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
@role_required("Admin")
def edit_user(user_id):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if user is None:
        conn.close()
        flash("User not found.", "error")
        return redirect(url_for("admin.users"))
    all_roles = conn.execute("SELECT * FROM roles ORDER BY name").fetchall()
    current_roles = conn.execute(
        "SELECT role_id FROM user_roles WHERE user_id=?", (user_id,)
    ).fetchall()
    current_role_ids = [str(r["role_id"]) for r in current_roles]

    if request.method == "POST":
        full_name = request.form["full_name"].strip()
        active = 1 if request.form.get("active") == "1" else 0
        role_ids = request.form.getlist("role_ids")
        new_password = request.form.get("new_password", "").strip()

        conn.execute("UPDATE users SET full_name=?, active=? WHERE id=?", (full_name, active, user_id))
        conn.execute("DELETE FROM user_roles WHERE user_id=?", (user_id,))
        for rid in role_ids:
            conn.execute("INSERT INTO user_roles (user_id, role_id) VALUES (?, ?)", (user_id, rid))
        if new_password:
            conn.execute(
                "UPDATE users SET password_hash=? WHERE id=?", (hash_password(new_password), user_id)
            )
            flash("Password reset.", "success")
        conn.commit()
        conn.close()
        flash("User updated.", "success")
        return redirect(url_for("admin.users"))

    conn.close()
    return render_template(
        "admin/user_form.html", all_roles=all_roles, user=user, current_role_ids=current_role_ids
    )


# ---------- Billables catalogue ----------

@bp.route("/billables", methods=["GET", "POST"])
@login_required
@role_required("Admin")
def billables():
    conn = get_db()
    if request.method == "POST":
        conn.execute(
            "INSERT INTO billables (name, category, price) VALUES (?, ?, ?)",
            (request.form["name"].strip(), request.form["category"], float(request.form["price"])),
        )
        conn.commit()
        flash("Billable added.", "success")
        return redirect(url_for("admin.billables"))
    rows = conn.execute("SELECT * FROM billables ORDER BY category, name").fetchall()
    conn.close()
    print_price_per_page = get_setting("print_price_per_page", "0")
    return render_template("admin/billables.html", billables=rows, print_price_per_page=print_price_per_page)


@bp.route("/billables/<int:billable_id>/edit", methods=["POST"])
@login_required
@role_required("Admin")
def edit_billable(billable_id):
    conn = get_db()
    active = 1 if request.form.get("active") == "1" else 0
    conn.execute(
        "UPDATE billables SET name=?, category=?, price=?, active=? WHERE id=?",
        (request.form["name"].strip(), request.form["category"], float(request.form["price"]), active, billable_id),
    )
    conn.commit()
    conn.close()
    flash("Billable updated.", "success")
    return redirect(url_for("admin.billables"))


@bp.route("/printing-price", methods=["POST"])
@login_required
@role_required("Admin")
def printing_price():
    """Price per page charged automatically to a visit's bill every time a
    patient document (prescription, referral, visit summary, complete
    record, discharge summary, receipt) is printed. 0 (the default) turns
    the feature off — nothing is billed for printing until this is set."""
    try:
        price = max(0.0, float(request.form.get("price_per_page") or 0))
    except ValueError:
        price = 0.0
    set_setting("print_price_per_page", str(price))
    flash("Printing price updated.", "success")
    return redirect(url_for("admin.billables"))


# ---------- Clinic profile / letterhead ----------

@bp.route("/clinic-profile", methods=["GET", "POST"])
@login_required
@role_required("Admin")
def clinic_profile():
    conn = get_db()
    if request.method == "POST":
        logo_path = None
        file = request.files.get("logo")
        if file and file.filename:
            ext = os.path.splitext(file.filename)[1].lower()
            if ext in (".png", ".jpg", ".jpeg"):
                filename = "clinic_logo" + ext
                file.save(UPLOAD_DIR / filename)
                logo_path = f"uploads/{filename}"

        currency = request.form.get("currency", "").strip()
        if currency == "__other__":
            currency = request.form.get("currency_other", "").strip()
        fields = {
            "name": request.form.get("name", "").strip(),
            "address": request.form.get("address", "").strip(),
            "phone": request.form.get("phone", "").strip(),
            "phone2": request.form.get("phone2", "").strip(),
            "website": request.form.get("website", "").strip(),
            "motto": request.form.get("motto", "").strip(),
            "currency": currency or "UGX",
            "social_facebook": request.form.get("social_facebook", "").strip(),
            "social_instagram": request.form.get("social_instagram", "").strip(),
            "social_whatsapp": request.form.get("social_whatsapp", "").strip(),
            "social_twitter": request.form.get("social_twitter", "").strip(),
            "social_other": request.form.get("social_other", "").strip(),
        }
        if logo_path:
            conn.execute(
                "UPDATE clinic_profile SET name=?, address=?, phone=?, phone2=?, website=?, motto=?, currency=?, "
                "social_facebook=?, social_instagram=?, social_whatsapp=?, social_twitter=?, social_other=?, "
                "logo_path=? WHERE id=1",
                (*fields.values(), logo_path),
            )
        else:
            conn.execute(
                "UPDATE clinic_profile SET name=?, address=?, phone=?, phone2=?, website=?, motto=?, currency=?, "
                "social_facebook=?, social_instagram=?, social_whatsapp=?, social_twitter=?, social_other=? "
                "WHERE id=1",
                tuple(fields.values()),
            )
        conn.commit()
        conn.close()
        flash("Clinic profile updated.", "success")
        return redirect(url_for("admin.clinic_profile"))

    profile = conn.execute("SELECT * FROM clinic_profile WHERE id=1").fetchone()
    conn.close()
    return render_template("admin/clinic_profile.html", profile=profile)


# ---------- Setup reminders ("don't show again" banners) ----------

@bp.route("/dismiss-reminder/<key>", methods=["POST"])
@login_required
@role_required("Admin")
def dismiss_reminder(key):
    if key not in ("profile", "backup"):
        abort(404)
    set_setting(f"hide_{key}_reminder", "1")
    return redirect(request.referrer or url_for("dashboard"))


# ---------- Backup status ----------

@bp.route("/backup-status", methods=["GET", "POST"])
@login_required
@role_required("Admin")
def backup_status():
    if request.method == "POST":
        folder_path = request.form.get("backup_folder_path", "").strip()
        if folder_path:
            set_setting("backup_folder_path", folder_path)
            flash("Backup folder saved. Point this at the folder Google Drive for Desktop syncs.", "success")
        return redirect(url_for("admin.backup_status"))

    status = None
    if BACKUP_STATUS_PATH.exists():
        with open(BACKUP_STATUS_PATH) as f:
            status = json.load(f)
    current_folder = get_setting("backup_folder_path", "")
    return render_template("admin/backup_status.html", status=status, current_folder=current_folder)


@bp.route("/backup-status/run-now", methods=["POST"])
@login_required
@role_required("Admin")
def run_backup_now():
    ok = run_backup()
    flash("Backup completed." if ok else "Backup failed — check the status below.", "success" if ok else "error")
    return redirect(url_for("admin.backup_status"))


# ---------- Connect a device ----------

@bp.route("/connect-device")
@login_required
@role_required("Admin")
def connect_device():
    hostname = get_setting("mdns_hostname", "clinicserver")
    script_path = RESOURCES_DIR / "packaging" / "make_ip_static.ps1"
    return render_template(
        "admin/connect_device.html",
        hostname_url=f"http://{hostname}.local:{SERVER_PORT}",
        ip_url=f"http://{get_lan_ip()}:{SERVER_PORT}",
        static_ip_script_available=script_path.exists(),
    )


@bp.route("/connect-device/make-ip-static-script")
@login_required
@role_required("Admin")
def download_static_ip_script():
    """Serves the PowerShell script that converts this computer's current
    (DHCP-assigned) IP address into a permanent static one, as a downloable
    fallback to the clinicserver.local mDNS name for networks/devices that
    don't resolve .local names reliably. See that script's own comments for
    exactly what it does; it is not run by the web app itself because
    changing network adapter settings needs Windows administrator rights,
    which this app deliberately does not run with."""
    script_dir = RESOURCES_DIR / "packaging"
    script_name = "make_ip_static.ps1"
    if not (script_dir / script_name).exists():
        abort(404)
    return send_from_directory(script_dir, script_name, as_attachment=True)


# ---------- Wards & beds (inpatient) ----------

@bp.route("/wards", methods=["GET", "POST"])
@login_required
@role_required("Admin")
def wards():
    conn = get_db()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        rate = float(request.form.get("nightly_rate") or 0)
        if name:
            conn.execute("INSERT INTO wards (name, nightly_rate) VALUES (?, ?)", (name, rate))
            conn.commit()
            flash("Ward added.", "success")
        return redirect(url_for("admin.wards"))

    ward_rows = conn.execute("SELECT * FROM wards ORDER BY name").fetchall()
    wards_with_beds = []
    for w in ward_rows:
        beds = conn.execute("SELECT * FROM beds WHERE ward_id=? ORDER BY name", (w["id"],)).fetchall()
        wards_with_beds.append({"ward": w, "beds": beds})
    conn.close()
    return render_template("admin/wards.html", wards_with_beds=wards_with_beds)


@bp.route("/wards/<int:ward_id>/edit", methods=["POST"])
@login_required
@role_required("Admin")
def edit_ward(ward_id):
    conn = get_db()
    active = 1 if request.form.get("active") == "1" else 0
    conn.execute(
        "UPDATE wards SET name=?, nightly_rate=?, active=? WHERE id=?",
        (request.form["name"].strip(), float(request.form.get("nightly_rate") or 0), active, ward_id),
    )
    conn.commit()
    conn.close()
    flash("Ward updated.", "success")
    return redirect(url_for("admin.wards"))


@bp.route("/wards/<int:ward_id>/beds", methods=["POST"])
@login_required
@role_required("Admin")
def add_bed(ward_id):
    name = request.form.get("name", "").strip()
    if name:
        conn = get_db()
        conn.execute("INSERT INTO beds (ward_id, name) VALUES (?, ?)", (ward_id, name))
        conn.commit()
        conn.close()
        flash("Bed added.", "success")
    return redirect(url_for("admin.wards"))


# ---------- Presenting complaints list (typeahead source) ----------

@bp.route("/complaints", methods=["GET", "POST"])
@login_required
@role_required("Admin")
def complaints_master():
    conn = get_db()
    if request.method == "POST":
        text = request.form.get("text", "").strip()
        if text:
            conn.execute("INSERT OR IGNORE INTO complaint_master (text) VALUES (?)", (text,))
            conn.commit()
            flash("Complaint added to the list.", "success")
        else:
            flash("Enter the complaint text.", "error")
        conn.close()
        return redirect(url_for("admin.complaints_master"))
    rows = conn.execute("SELECT * FROM complaint_master ORDER BY text").fetchall()
    conn.close()
    return render_template("admin/complaints_master.html", complaints=rows)


@bp.route("/complaints/<int:complaint_id>/edit", methods=["POST"])
@login_required
@role_required("Admin")
def edit_complaint_master(complaint_id):
    conn = get_db()
    active = 1 if request.form.get("active") == "1" else 0
    text = request.form.get("text", "").strip()
    if text:
        conn.execute(
            "UPDATE complaint_master SET text=?, active=? WHERE id=?",
            (text, active, complaint_id),
        )
        conn.commit()
        flash("Complaint updated.", "success")
    conn.close()
    return redirect(url_for("admin.complaints_master"))


# ---------- Diagnoses list (ICD-10 reference + admin-added custom terms) ----------

@bp.route("/diagnoses", methods=["GET", "POST"])
@login_required
@role_required("Admin")
def diagnoses_master():
    conn = get_db()
    if request.method == "POST":
        text = request.form.get("text", "").strip()
        code = (request.form.get("code") or "").strip().upper() or None
        if text:
            conn.execute(
                "INSERT INTO diagnosis_master (code, text, source, active) VALUES (?, ?, 'custom', 1)",
                (code, text),
            )
            conn.commit()
            flash("Custom diagnosis added.", "success")
        else:
            flash("Enter the diagnosis text.", "error")
        conn.close()
        return redirect(url_for("admin.diagnoses_master"))

    q = request.args.get("q", "").strip()
    custom_rows = conn.execute(
        "SELECT * FROM diagnosis_master WHERE source='custom' ORDER BY text"
    ).fetchall()
    search_results = []
    if q:
        like = f"%{q}%"
        search_results = conn.execute(
            "SELECT * FROM diagnosis_master WHERE (text LIKE ? OR code LIKE ?) "
            "ORDER BY source, text LIMIT 50",
            (like, like),
        ).fetchall()
    icd10_count = conn.execute(
        "SELECT COUNT(*) c FROM diagnosis_master WHERE source='icd10'"
    ).fetchone()["c"]
    conn.close()
    return render_template(
        "admin/diagnoses_master.html", custom=custom_rows, q=q,
        search_results=search_results, icd10_count=icd10_count,
    )


@bp.route("/diagnoses/<int:diagnosis_id>/edit", methods=["POST"])
@login_required
@role_required("Admin")
def edit_diagnosis_master(diagnosis_id):
    conn = get_db()
    active = 1 if request.form.get("active") == "1" else 0
    text = request.form.get("text", "").strip()
    code = (request.form.get("code") or "").strip().upper() or None
    if text:
        conn.execute(
            "UPDATE diagnosis_master SET text=?, code=?, active=? WHERE id=? AND source='custom'",
            (text, code, active, diagnosis_id),
        )
        conn.commit()
        flash("Diagnosis updated.", "success")
    conn.close()
    return redirect(url_for("admin.diagnoses_master"))


@bp.route("/beds/<int:bed_id>/edit", methods=["POST"])
@login_required
@role_required("Admin")
def edit_bed(bed_id):
    conn = get_db()
    bed = conn.execute("SELECT * FROM beds WHERE id=?", (bed_id,)).fetchone()
    if bed is None:
        conn.close()
        flash("Bed not found.", "error")
        return redirect(url_for("admin.wards"))
    status = request.form.get("status", "available")
    if status not in ("available", "occupied", "maintenance"):
        status = "available"
    conn.execute(
        "UPDATE beds SET name=?, status=? WHERE id=?",
        (request.form.get("name", bed["name"]).strip() or bed["name"], status, bed_id),
    )
    conn.commit()
    conn.close()
    flash("Bed updated.", "success")
    return redirect(url_for("admin.wards"))
