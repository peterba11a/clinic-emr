import random
import re
import sqlite3
import os
import string
import sys
import secrets
from pathlib import Path
from werkzeug.security import generate_password_hash

if getattr(sys, "frozen", False):
    # Running as a PyInstaller-built exe.
    #
    # BASE_DIR is where the app keeps things IT writes (the live database,
    # an uploaded clinic logo): always right next to the real .exe, so they
    # survive reinstalls/upgrades and are easy for the clinic to find.
    BASE_DIR = Path(sys.executable).resolve().parent
    # RESOURCES_DIR is where PyInstaller actually put the READ-ONLY files it
    # bundled (templates, schema.sql, the default stylesheet). sys._MEIPASS
    # is PyInstaller's own documented way of pointing at this location, and
    # using it means the app works correctly whether a given PyInstaller
    # build/version places bundled files directly beside the exe or inside
    # a "_internal" subfolder — we don't have to guess or fight its layout.
    RESOURCES_DIR = Path(getattr(sys, "_MEIPASS", BASE_DIR))
else:
    BASE_DIR = Path(__file__).resolve().parent
    RESOURCES_DIR = BASE_DIR
INSTANCE_DIR = BASE_DIR / "instance"
INSTANCE_DIR.mkdir(exist_ok=True)
DB_PATH = INSTANCE_DIR / "clinic.db"
SCHEMA_PATH = RESOURCES_DIR / "schema.sql"
ICD10_PATH = RESOURCES_DIR / "icd10_codes.tsv"

DEFAULT_ROLES = ["Admin", "Reception", "Clinician", "Nurse", "Pharmacy", "Lab"]

DEFAULT_BILLABLES = [
    ("General consultation", "consultation", 10000),
    ("Wound dressing", "procedure", 5000),
    ("Suturing", "procedure", 15000),
    ("Injection administration", "procedure", 3000),
    ("Malaria RDT", "lab", 5000),
    ("Urinalysis", "lab", 4000),
    ("Hemoglobin (HB)", "lab", 6000),
    ("X-ray request", "radiology", 20000),
    ("Ultrasound request", "radiology", 25000),
]


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")  # allows concurrent readers while one writer commits
    return conn


def init_db():
    first_run = not DB_PATH.exists()
    conn = get_db()
    with open(SCHEMA_PATH, "r") as f:
        conn.executescript(f.read())

    # Upgrade path for databases created before the "priority" column
    # existed on visits (CREATE TABLE IF NOT EXISTS above won't add columns
    # to an already-existing table).
    existing_cols = {row["name"] for row in conn.execute("PRAGMA table_info(visits)")}
    if "priority" not in existing_cols:
        conn.execute("ALTER TABLE visits ADD COLUMN priority TEXT NOT NULL DEFAULT 'Routine'")

    # Upgrade path for databases created before presenting-complaint
    # duration, diagnosis ICD-10/status, and structured prescribing fields
    # existed on their respective tables.
    complaint_cols = {row["name"] for row in conn.execute("PRAGMA table_info(complaints)")}
    if "duration" not in complaint_cols:
        conn.execute("ALTER TABLE complaints ADD COLUMN duration TEXT")

    diagnosis_cols = {row["name"] for row in conn.execute("PRAGMA table_info(diagnoses)")}
    if "icd10_code" not in diagnosis_cols:
        conn.execute("ALTER TABLE diagnoses ADD COLUMN icd10_code TEXT")
    if "status" not in diagnosis_cols:
        conn.execute("ALTER TABLE diagnoses ADD COLUMN status TEXT NOT NULL DEFAULT 'Preliminary'")

    order_cols = {row["name"] for row in conn.execute("PRAGMA table_info(treatment_orders)")}
    for col, ddl in (
        ("inventory_item_id", "ALTER TABLE treatment_orders ADD COLUMN inventory_item_id INTEGER REFERENCES inventory_items(id)"),
        ("route", "ALTER TABLE treatment_orders ADD COLUMN route TEXT"),
        ("dose", "ALTER TABLE treatment_orders ADD COLUMN dose TEXT"),
        ("frequency", "ALTER TABLE treatment_orders ADD COLUMN frequency TEXT"),
        ("duration", "ALTER TABLE treatment_orders ADD COLUMN duration TEXT"),
        ("instructions", "ALTER TABLE treatment_orders ADD COLUMN instructions TEXT"),
        ("billable_id", "ALTER TABLE treatment_orders ADD COLUMN billable_id INTEGER REFERENCES billables(id)"),
    ):
        if col not in order_cols:
            conn.execute(ddl)

    # Upgrade path for databases created before discharge follow-up date /
    # take-home medications existed on admissions.
    admission_cols = {row["name"] for row in conn.execute("PRAGMA table_info(admissions)")}
    for col, ddl in (
        ("follow_up_date", "ALTER TABLE admissions ADD COLUMN follow_up_date TEXT"),
        ("discharge_medications", "ALTER TABLE admissions ADD COLUMN discharge_medications TEXT"),
    ):
        if col not in admission_cols:
            conn.execute(ddl)

    # Upgrade path for databases created before the clinic's currency was
    # configurable (used to prefix every billed/printed amount).
    profile_cols = {row["name"] for row in conn.execute("PRAGMA table_info(clinic_profile)")}
    if "currency" not in profile_cols:
        conn.execute("ALTER TABLE clinic_profile ADD COLUMN currency TEXT NOT NULL DEFAULT 'UGX'")

    # Upgrade path for databases created before the Terms of Use gate
    # existed — every existing user starts as "not yet accepted" (NULL) and
    # sees it on their next login, same as a brand-new user would.
    user_cols = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
    for col, ddl in (
        ("terms_accepted_version", "ALTER TABLE users ADD COLUMN terms_accepted_version TEXT"),
        ("terms_accepted_at", "ALTER TABLE users ADD COLUMN terms_accepted_at TEXT"),
    ):
        if col not in user_cols:
            conn.execute(ddl)

    # seed roles
    for name in DEFAULT_ROLES:
        conn.execute("INSERT OR IGNORE INTO roles (name) VALUES (?)", (name,))

    # seed a session secret key if missing
    row = conn.execute("SELECT value FROM settings WHERE key='secret_key'").fetchone()
    if not row:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('secret_key', ?)",
            (secrets.token_hex(32),),
        )

    # seed a default admin account on first run only
    admin_exists = conn.execute(
        "SELECT 1 FROM users WHERE username = 'admin'"
    ).fetchone()
    if not admin_exists:
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, full_name) VALUES (?, ?, ?)",
            ("admin", generate_password_hash("admin123"), "Administrator"),
        )
        admin_id = cur.lastrowid
        admin_role_id = conn.execute(
            "SELECT id FROM roles WHERE name='Admin'"
        ).fetchone()["id"]
        conn.execute(
            "INSERT OR IGNORE INTO user_roles (user_id, role_id) VALUES (?, ?)",
            (admin_id, admin_role_id),
        )

    # seed a starter billables catalogue so the system isn't empty on first run
    existing = conn.execute("SELECT COUNT(*) c FROM billables").fetchone()["c"]
    if existing == 0:
        conn.executemany(
            "INSERT INTO billables (name, category, price) VALUES (?, ?, ?)",
            DEFAULT_BILLABLES,
        )

    # seed a starter ward with a couple of beds so admissions aren't blocked
    # on Admin setting this up before it can even be demonstrated
    ward_count = conn.execute("SELECT COUNT(*) c FROM wards").fetchone()["c"]
    if ward_count == 0:
        cur = conn.execute(
            "INSERT INTO wards (name, nightly_rate) VALUES (?, ?)",
            ("General Ward", 20000),
        )
        ward_id = cur.lastrowid
        conn.executemany(
            "INSERT INTO beds (ward_id, name) VALUES (?, ?)",
            [(ward_id, "Bed 1"), (ward_id, "Bed 2"), (ward_id, "Bed 3")],
        )

    # seed the ICD-10 diagnosis reference list from the bundled data file
    # (one-time — this runs on every startup but is a no-op once loaded)
    icd10_count = conn.execute(
        "SELECT COUNT(*) c FROM diagnosis_master WHERE source='icd10'"
    ).fetchone()["c"]
    if icd10_count == 0 and ICD10_PATH.exists():
        rows = []
        with open(ICD10_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n")
                if not line or "\t" not in line:
                    continue
                code, text = line.split("\t", 1)
                rows.append((code, text))
        conn.executemany(
            "INSERT INTO diagnosis_master (code, text, source, active) VALUES (?, ?, 'icd10', 1)",
            rows,
        )

    conn.commit()
    conn.close()
    return first_run


def _clinic_code_prefix(conn):
    """Two-letter prefix for auto-generated patient codes, derived from the
    clinic's name (Admin -> Clinic Profile): first letters of the first two
    words, e.g. "Kiruddu Clinic" -> "KC". Falls back to "CE" if the name is
    blank, has no letters, or is a single short word."""
    row = conn.execute("SELECT name FROM clinic_profile WHERE id=1").fetchone()
    name = (row["name"] if row else "") or ""
    words = re.findall(r"[A-Za-z]+", name)
    if len(words) >= 2:
        prefix = (words[0][0] + words[1][0]).upper()
    elif len(words) == 1 and len(words[0]) >= 2:
        prefix = words[0][:2].upper()
    else:
        prefix = "CE"
    return prefix


def generate_patient_code(conn):
    """Auto-generated patient code: CC-LLL-NNN, where CC is the two-letter
    clinic prefix, LLL is three random letters, and NNN is three random
    digits. Retries on the astronomically unlikely chance of a collision."""
    prefix = _clinic_code_prefix(conn)
    for _ in range(50):
        letters = "".join(random.choices(string.ascii_uppercase, k=3))
        digits = "".join(random.choices(string.digits, k=3))
        code = f"{prefix}-{letters}-{digits}"
        exists = conn.execute(
            "SELECT 1 FROM patients WHERE patient_code=?", (code,)
        ).fetchone()
        if not exists:
            return code
    raise RuntimeError("Could not generate a unique patient code after 50 attempts")


def get_setting(key, default=None):
    conn = get_db()
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key, value):
    conn = get_db()
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    conn.commit()
    conn.close()
