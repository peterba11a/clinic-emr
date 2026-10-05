from flask import Blueprint, render_template, request, redirect, url_for, session, flash, g
from werkzeug.security import check_password_hash
from auth import authenticate, login_required, hash_password
from db import get_db

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = authenticate(username, password)
        if user:
            session.clear()
            session["user_id"] = user["id"]
            next_url = request.args.get("next") or url_for("dashboard")
            return redirect(next_url)
        flash("Incorrect username or password.", "error")
    return render_template("login.html")


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


@bp.route("/account/password", methods=["GET", "POST"])
@login_required
def change_password():
    """Self-service password change for any logged-in user, including
    Admin — separate from Admin -> Staff accounts, which lets an Admin
    reset someone ELSE's password without knowing their current one."""
    if request.method == "POST":
        current = request.form.get("current_password", "")
        new = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")
        if not check_password_hash(g.user["password_hash"], current):
            flash("Current password is incorrect.", "error")
        elif len(new) < 6:
            flash("New password must be at least 6 characters.", "error")
        elif new != confirm:
            flash("New password and confirmation don't match.", "error")
        else:
            conn = get_db()
            conn.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(new), g.user["id"]))
            conn.commit()
            conn.close()
            flash("Password changed.", "success")
            return redirect(url_for("dashboard"))
    return render_template("account/change_password.html")
