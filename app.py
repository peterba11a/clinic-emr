import shutil
import sys as _sys
from datetime import datetime

from flask import Flask, g, render_template, redirect, url_for, request
from jinja2 import pass_context
from db import init_db, get_db, get_setting, BASE_DIR, RESOURCES_DIR
from auth import load_logged_in_user
from scheduler import start_backup_scheduler
from terms import TERMS_VERSION

from routes import auth_routes, patients, visits, pharmacy, procedures, lab, radiology, billing, admin, reports, printing, referrals, admissions, terms as terms_routes


def _ensure_writable_static():
    """When frozen, static/ needs to be a real, writable folder next to the
    exe (it holds the admin-uploaded clinic logo), but the default
    stylesheet is bundled as a read-only resource that may live elsewhere
    (see RESOURCES_DIR in db.py). Copy the bundled CSS into the writable
    folder on every startup (cheap, keeps it in sync with the build) and
    make sure the uploads folder exists, without ever touching anything a
    user has already uploaded there."""
    if not getattr(_sys, "frozen", False):
        return
    uploads_dir = BASE_DIR / "static" / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    css_dir = BASE_DIR / "static" / "css"
    css_dir.mkdir(parents=True, exist_ok=True)
    bundled_css = RESOURCES_DIR / "static" / "css" / "style.css"
    if bundled_css.exists():
        try:
            shutil.copy2(bundled_css, css_dir / "style.css")
        except shutil.SameFileError:
            pass


def create_app():
    _ensure_writable_static()
    # Templates are read-only bundled resources (RESOURCES_DIR, which
    # resolves correctly whether PyInstaller places them beside the exe or
    # inside a "_internal" folder). static_folder stays writable, next to
    # the exe itself, since the clinic's uploaded logo lives there.
    app = Flask(
        __name__,
        template_folder=str(RESOURCES_DIR / "templates"),
        static_folder=str(BASE_DIR / "static"),
    )

    first_run = init_db()
    app.secret_key = get_setting("secret_key")
    app.config["FIRST_RUN"] = first_run

    app.register_blueprint(auth_routes.bp)
    app.register_blueprint(patients.bp)
    app.register_blueprint(visits.bp)
    app.register_blueprint(pharmacy.bp)
    app.register_blueprint(procedures.bp)
    app.register_blueprint(lab.bp)
    app.register_blueprint(radiology.bp)
    app.register_blueprint(billing.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(reports.bp)
    app.register_blueprint(printing.bp)
    app.register_blueprint(referrals.bp)
    app.register_blueprint(admissions.bp)
    app.register_blueprint(terms_routes.bp)

    start_backup_scheduler()

    @app.before_request
    def before_request():
        load_logged_in_user()

    @app.before_request
    def require_terms_acceptance():
        # Every user — new or existing, any role, including Admin — must
        # accept the current Terms of Use before doing anything else. This
        # runs on every request once logged in, so clicking a nav link
        # instead of accepting just bounces back here.
        if g.user is None:
            return None
        if request.endpoint in ("terms.accept", "auth.logout", "static"):
            return None
        if g.user["terms_accepted_version"] != TERMS_VERSION:
            return redirect(url_for("terms.accept", next=request.path))
        return None

    @app.context_processor
    def inject_globals():
        conn = get_db()
        profile = conn.execute("SELECT * FROM clinic_profile WHERE id=1").fetchone()
        conn.close()
        roles = g.get("roles", [])

        def has_role(*names):
            # Admin can see and do everything every other role can.
            return "Admin" in roles or any(n in roles for n in names)

        is_admin = has_role("Admin")
        show_profile_reminder = (
            is_admin
            and not (profile["name"] if profile else "").strip()
            and get_setting("hide_profile_reminder") != "1"
        )
        show_backup_reminder = (
            is_admin
            and not get_setting("backup_folder_path", "")
            and get_setting("hide_backup_reminder") != "1"
        )

        return {
            "current_user": g.get("user"),
            "current_roles": roles,
            "clinic": profile,
            "has_role": has_role,
            "now": datetime.now(),
            "show_profile_reminder": show_profile_reminder,
            "show_backup_reminder": show_backup_reminder,
        }

    @app.template_filter("money")
    @pass_context
    def format_money(ctx, amount):
        """Formats an amount with the clinic's configured currency code/symbol
        (Admin -> Clinic profile), e.g. 15000 -> "UGX 15,000". Falls back to
        UGX if the clinic profile hasn't loaded for some reason."""
        clinic = ctx.get("clinic")
        currency = "UGX"
        if clinic is not None:
            try:
                currency = clinic["currency"] or "UGX"
            except (IndexError, KeyError):
                pass
        try:
            return f"{currency} {float(amount):,.0f}"
        except (TypeError, ValueError):
            return f"{currency} {amount}"

    @app.route("/")
    def dashboard():
        if g.user is None:
            return redirect(url_for("auth.login"))
        return render_template("dashboard.html")

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("error.html", code=403, message="You don't have access to that page."), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("error.html", code=404, message="That page doesn't exist."), 404

    return app


app = create_app()


def _open_browser_soon(url):
    import threading
    import time
    import webbrowser

    def _open():
        time.sleep(1.5)
        try:
            webbrowser.open(url)
        except Exception:
            pass

    threading.Thread(target=_open, daemon=True).start()


if __name__ == "__main__":
    import sys

    if len(sys.argv) >= 3 and sys.argv[1] == "--restore":
        from restore import restore_from
        restore_from(sys.argv[2])
        sys.exit(0)

    from mdns_advertise import advertise_hostname

    port = 8080
    hostname = get_setting("mdns_hostname", "clinicserver")
    advertise_hostname(hostname, port)

    if "--no-browser" not in sys.argv:
        _open_browser_soon(f"http://127.0.0.1:{port}/")

    # Bind to all interfaces so other devices on the clinic LAN can reach it.
    app.run(host="0.0.0.0", port=port, debug=False)
