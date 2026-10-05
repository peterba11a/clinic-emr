from datetime import date
from flask import Blueprint, render_template
from auth import login_required, role_required
from db import get_db

bp = Blueprint("reports", __name__, url_prefix="/reports")


@bp.route("/")
@login_required
@role_required("Admin", "Reception", "Clinician")
def index():
    conn = get_db()
    today = date.today().isoformat()
    month = today[:7]

    patients_today = conn.execute(
        "SELECT COUNT(*) c FROM visits WHERE date(visit_date)=?", (today,)
    ).fetchone()["c"]
    patients_month = conn.execute(
        "SELECT COUNT(*) c FROM visits WHERE strftime('%Y-%m', visit_date)=?", (month,)
    ).fetchone()["c"]
    common_diagnoses = conn.execute(
        "SELECT diagnosis, COUNT(*) c FROM visits "
        "WHERE diagnosis IS NOT NULL AND diagnosis != '' AND strftime('%Y-%m', visit_date)=? "
        "GROUP BY diagnosis ORDER BY c DESC LIMIT 10",
        (month,),
    ).fetchall()

    revenue_today = conn.execute(
        "SELECT COALESCE(SUM(amount),0) t FROM payments WHERE date(paid_at)=?", (today,)
    ).fetchone()["t"]
    revenue_month = conn.execute(
        "SELECT COALESCE(SUM(amount),0) t FROM payments WHERE strftime('%Y-%m', paid_at)=?", (month,)
    ).fetchone()["t"]
    revenue_by_category = conn.execute(
        "SELECT ii.category, COALESCE(SUM(ii.line_total),0) t FROM invoice_items ii "
        "WHERE strftime('%Y-%m', ii.created_at)=? GROUP BY ii.category ORDER BY t DESC",
        (month,),
    ).fetchall()

    low_stock = conn.execute(
        "SELECT * FROM inventory_items WHERE active=1 AND stock_qty <= reorder_threshold ORDER BY name"
    ).fetchall()
    expiring_soon = conn.execute(
        "SELECT * FROM inventory_items WHERE active=1 AND expiry_date IS NOT NULL "
        "AND date(expiry_date) <= date('now', '+60 day') ORDER BY expiry_date"
    ).fetchall()

    conn.close()
    return render_template(
        "reports/index.html",
        patients_today=patients_today, patients_month=patients_month,
        common_diagnoses=common_diagnoses, revenue_today=revenue_today,
        revenue_month=revenue_month, revenue_by_category=revenue_by_category,
        low_stock=low_stock, expiring_soon=expiring_soon,
    )
