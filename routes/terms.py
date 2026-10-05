from flask import Blueprint, render_template, request, redirect, url_for, g, flash
from auth import login_required
from db import get_db
from terms import TERMS_VERSION, TERMS_PARAGRAPHS

bp = Blueprint("terms", __name__)


@bp.route("/terms", methods=["GET", "POST"])
@login_required
def accept():
    next_url = request.values.get("next") or url_for("dashboard")
    # Never bounce back into a loop, and never forward anyone to another
    # site via this field.
    if not next_url.startswith("/"):
        next_url = url_for("dashboard")

    if request.method == "POST":
        if not request.form.get("agree"):
            flash("Please check the box to confirm you've read and agree before continuing.", "error")
        else:
            conn = get_db()
            conn.execute(
                "UPDATE users SET terms_accepted_version=?, terms_accepted_at=datetime('now') WHERE id=?",
                (TERMS_VERSION, g.user["id"]),
            )
            conn.commit()
            conn.close()
            return redirect(next_url)

    return render_template("terms.html", paragraphs=TERMS_PARAGRAPHS, next_url=next_url)
