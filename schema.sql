-- Clinic EMR & Billing System — SQLite schema
-- Kept deliberately flat and simple: no ORM, one file, easy to read and back up.

PRAGMA foreign_keys = ON;

-- Free-form key/value store for small persistent settings
-- (session secret key, local hostname, backup folder path, install id, etc.)
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- ---------- Users, roles (multi-role per account) ----------

CREATE TABLE IF NOT EXISTS users (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    username               TEXT UNIQUE NOT NULL,
    password_hash          TEXT NOT NULL,
    full_name              TEXT NOT NULL,
    active                 INTEGER NOT NULL DEFAULT 1,
    created_at             TEXT NOT NULL DEFAULT (datetime('now')),
    terms_accepted_version TEXT,  -- Terms of Use version this user has agreed to (see terms.py); NULL = not yet
    terms_accepted_at      TEXT
);

CREATE TABLE IF NOT EXISTS roles (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL  -- Reception, Clinician, Pharmacy, Lab, Admin
);

CREATE TABLE IF NOT EXISTS user_roles (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, role_id)
);

-- ---------- Clinic profile / letterhead branding ----------

CREATE TABLE IF NOT EXISTS clinic_profile (
    id               INTEGER PRIMARY KEY CHECK (id = 1),
    name             TEXT NOT NULL DEFAULT '',
    logo_path        TEXT,
    address          TEXT,
    phone            TEXT,
    phone2           TEXT,
    website          TEXT,
    motto            TEXT,
    currency         TEXT NOT NULL DEFAULT 'UGX',  -- prefixed on every billed/printed amount
    social_facebook  TEXT,
    social_instagram TEXT,
    social_whatsapp  TEXT,
    social_twitter   TEXT,
    social_other     TEXT
);
INSERT OR IGNORE INTO clinic_profile (id, name) VALUES (1, '');

-- ---------- Patients ----------

CREATE TABLE IF NOT EXISTS patients (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_code TEXT UNIQUE NOT NULL,   -- e.g. P-000123
    full_name    TEXT NOT NULL,
    dob          TEXT,                   -- ISO date, nullable
    age_years    INTEGER,                -- used when dob unknown
    sex          TEXT,                   -- M / F / Other
    phone        TEXT,
    village      TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------- Visits (a visit begins at check-in with status 'waiting') ----------

CREATE TABLE IF NOT EXISTS visits (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id      INTEGER NOT NULL REFERENCES patients(id),
    created_by      INTEGER REFERENCES users(id),
    status          TEXT NOT NULL DEFAULT 'waiting',  -- waiting / in_progress / admitted / completed
    priority        TEXT NOT NULL DEFAULT 'Routine',  -- Emergency / Urgent / Routine (set at triage)
    visit_date      TEXT NOT NULL DEFAULT (datetime('now')),
    -- The fields below are kept for backward compatibility with visits
    -- recorded before the tabbed clinical record (vitals_records,
    -- complaints, history_records, examination_records, diagnoses below)
    -- existed. New code reads/writes those tables instead.
    complaint       TEXT,
    temp_c          REAL,
    bp              TEXT,
    pulse           INTEGER,
    weight_kg       REAL,
    diagnosis       TEXT,
    treatment_notes TEXT,
    follow_up_date  TEXT,
    seen_by         INTEGER REFERENCES users(id),
    completed_at    TEXT
);

-- ---------- Inventory: drugs and procedure materials share one table ----------

CREATE TABLE IF NOT EXISTS inventory_items (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    name              TEXT UNIQUE NOT NULL,
    item_type         TEXT NOT NULL DEFAULT 'drug',  -- drug / material
    unit              TEXT NOT NULL DEFAULT 'unit',
    unit_price        REAL NOT NULL DEFAULT 0,
    stock_qty         REAL NOT NULL DEFAULT 0,
    expiry_date       TEXT,
    reorder_threshold REAL NOT NULL DEFAULT 0,
    active            INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS dispenses (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    visit_id         INTEGER NOT NULL REFERENCES visits(id),
    inventory_item_id INTEGER NOT NULL REFERENCES inventory_items(id),
    quantity         REAL NOT NULL,
    unit_price       REAL NOT NULL,     -- price snapshot at time of dispensing
    dispensed_by     INTEGER REFERENCES users(id),
    dispensed_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------- Billables catalogue (consultation / procedure / lab / radiology) ----------

CREATE TABLE IF NOT EXISTS billables (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    name     TEXT NOT NULL,
    category TEXT NOT NULL,   -- consultation / procedure / lab / radiology
    price    REAL NOT NULL DEFAULT 0,
    active   INTEGER NOT NULL DEFAULT 1
);

-- ---------- Procedures (flat billable + optional itemized materials) ----------

CREATE TABLE IF NOT EXISTS procedure_records (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    visit_id      INTEGER NOT NULL REFERENCES visits(id),
    billable_id   INTEGER NOT NULL REFERENCES billables(id),
    performed_by  INTEGER REFERENCES users(id),
    performed_at  TEXT NOT NULL DEFAULT (datetime('now')),
    notes         TEXT
);

CREATE TABLE IF NOT EXISTS procedure_materials (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    procedure_record_id INTEGER NOT NULL REFERENCES procedure_records(id) ON DELETE CASCADE,
    inventory_item_id   INTEGER NOT NULL REFERENCES inventory_items(id),
    quantity            REAL NOT NULL,
    unit_price          REAL NOT NULL   -- price snapshot at time of use
);

-- ---------- Lightweight lab ----------

CREATE TABLE IF NOT EXISTS lab_orders (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    visit_id     INTEGER NOT NULL REFERENCES visits(id),
    billable_id  INTEGER NOT NULL REFERENCES billables(id),
    ordered_by   INTEGER REFERENCES users(id),
    ordered_at   TEXT NOT NULL DEFAULT (datetime('now')),
    result_text  TEXT,
    resulted_at  TEXT
);

-- ---------- Lightweight radiology ----------

CREATE TABLE IF NOT EXISTS radiology_requests (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    visit_id      INTEGER NOT NULL REFERENCES visits(id),
    billable_id   INTEGER NOT NULL REFERENCES billables(id),
    reason        TEXT,
    ordered_by    INTEGER REFERENCES users(id),
    requested_at  TEXT NOT NULL DEFAULT (datetime('now')),
    status        TEXT NOT NULL DEFAULT 'requested',  -- requested / done
    findings_text TEXT,
    done_at       TEXT
);

-- ---------- Billing: one invoice per visit, line items snapshot price ----------

CREATE TABLE IF NOT EXISTS invoices (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    visit_id     INTEGER UNIQUE NOT NULL REFERENCES visits(id),
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    status       TEXT NOT NULL DEFAULT 'open'  -- open / partial / paid
);

CREATE TABLE IF NOT EXISTS invoice_items (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id   INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    description  TEXT NOT NULL,
    category     TEXT NOT NULL,  -- consultation / procedure / material / drug / lab / radiology
    quantity     REAL NOT NULL DEFAULT 1,
    unit_price   REAL NOT NULL,
    line_total   REAL NOT NULL,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS payments (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id   INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    amount       REAL NOT NULL,
    method       TEXT NOT NULL DEFAULT 'cash',
    recorded_by  INTEGER REFERENCES users(id),
    paid_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------- Wards & beds (inpatient) ----------

CREATE TABLE IF NOT EXISTS wards (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT UNIQUE NOT NULL,
    nightly_rate REAL NOT NULL DEFAULT 0,
    active       INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS beds (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ward_id INTEGER NOT NULL REFERENCES wards(id) ON DELETE CASCADE,
    name    TEXT NOT NULL,
    status  TEXT NOT NULL DEFAULT 'available',  -- available / occupied
    UNIQUE (ward_id, name)
);

-- ---------- Admissions: an inpatient stay layered on top of a visit ----------
-- (the same visit_id already used for billing/procedures/lab/radiology —
-- an admission just means that visit stays open across multiple days,
-- with vitals/notes/treatments recorded against it over time.)

CREATE TABLE IF NOT EXISTS admissions (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    visit_id              INTEGER UNIQUE NOT NULL REFERENCES visits(id),
    ward_id               INTEGER NOT NULL REFERENCES wards(id),
    bed_id                INTEGER NOT NULL REFERENCES beds(id),
    admitted_by           INTEGER REFERENCES users(id),
    admitted_at           TEXT NOT NULL DEFAULT (datetime('now')),
    discharged_by         INTEGER REFERENCES users(id),
    discharged_at         TEXT,
    discharge_summary     TEXT,
    follow_up_date        TEXT,  -- when the patient should come back, if advised
    discharge_medications TEXT,  -- take-home medication instructions, separate from in-stay prescribing
    status                TEXT NOT NULL DEFAULT 'admitted'  -- admitted / discharged
);

-- ---------- Tabbed clinical record ----------
-- Each of these is a repeatable, timestamped log against a visit (not a
-- single fixed field), since an admission needs many entries over several
-- days while an outpatient visit usually just has one.

CREATE TABLE IF NOT EXISTS vitals_records (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    visit_id    INTEGER NOT NULL REFERENCES visits(id),
    recorded_by INTEGER REFERENCES users(id),
    recorded_at TEXT NOT NULL DEFAULT (datetime('now')),
    bp          TEXT,
    pulse       INTEGER,
    temp_c      REAL,
    resp_rate   INTEGER,
    spo2        INTEGER,
    weight_kg   REAL,
    height_cm   REAL,
    rbs         REAL,
    other       TEXT
);

CREATE TABLE IF NOT EXISTS complaints (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    visit_id    INTEGER NOT NULL REFERENCES visits(id),
    recorded_by INTEGER REFERENCES users(id),
    recorded_at TEXT NOT NULL DEFAULT (datetime('now')),
    text        TEXT NOT NULL,
    duration    TEXT   -- e.g. "3 days" — how long the complaint has been present
);

-- Admin-editable master list that powers the complaint typeahead in the
-- Complaints tab (see complaint suggestions seeded below).
CREATE TABLE IF NOT EXISTS complaint_master (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    text   TEXT UNIQUE NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS history_records (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    visit_id    INTEGER NOT NULL REFERENCES visits(id),
    recorded_by INTEGER REFERENCES users(id),
    recorded_at TEXT NOT NULL DEFAULT (datetime('now')),
    text        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS examination_records (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    visit_id    INTEGER NOT NULL REFERENCES visits(id),
    recorded_by INTEGER REFERENCES users(id),
    recorded_at TEXT NOT NULL DEFAULT (datetime('now')),
    text        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS diagnoses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    visit_id    INTEGER NOT NULL REFERENCES visits(id),
    recorded_by INTEGER REFERENCES users(id),
    recorded_at TEXT NOT NULL DEFAULT (datetime('now')),
    text        TEXT NOT NULL,
    icd10_code  TEXT,                              -- set when picked from the ICD-10 list, blank if free text
    status      TEXT NOT NULL DEFAULT 'Preliminary' -- Preliminary / Confirmed
);

-- Diagnosis reference list: seeded from the full WHO ICD-10 category and
-- subcategory list (~12,000 entries, source='icd10', see icd10_codes.tsv
-- loaded by db.py), plus whatever clinic-specific entries Admin adds
-- (source='custom'). Powers the search-as-you-type box in the Diagnoses tab.
CREATE TABLE IF NOT EXISTS diagnosis_master (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    code   TEXT,                            -- ICD-10 code, NULL for a custom entry with no code
    text   TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'custom',  -- icd10 / custom
    active INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_diagnosis_master_text ON diagnosis_master(text);
CREATE INDEX IF NOT EXISTS idx_diagnosis_master_code ON diagnosis_master(code);

-- A single chronological notes feed per visit/admission, tagged by type so
-- nursing notes and doctor's notes are both visible but distinguishable.
CREATE TABLE IF NOT EXISTS encounter_notes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    visit_id    INTEGER NOT NULL REFERENCES visits(id),
    author_id   INTEGER REFERENCES users(id),
    note_type   TEXT NOT NULL DEFAULT 'doctor',  -- doctor / nursing
    recorded_at TEXT NOT NULL DEFAULT (datetime('now')),
    text        TEXT NOT NULL
);

-- ---------- Treatment orders + dose administration ----------
-- A treatment (drug or procedure/intervention) is ordered once, then
-- administered/given possibly many times; each administration is its own
-- stock-deduction + billing event rather than one lump charge up front.

CREATE TABLE IF NOT EXISTS treatment_orders (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    visit_id          INTEGER NOT NULL REFERENCES visits(id),
    order_type        TEXT NOT NULL DEFAULT 'drug',  -- drug / procedure
    inventory_item_id INTEGER REFERENCES inventory_items(id),  -- set when the drug was picked from pharmacy stock
    billable_id       INTEGER REFERENCES billables(id),  -- set when the procedure was picked from the billables catalog (procedure orders)
    description       TEXT NOT NULL,                -- drug name, or the procedure/intervention name
    route             TEXT,       -- route of administration, e.g. "Oral", "IV", "IM" (drug orders only)
    dose              TEXT,       -- e.g. "500mg", "2 tablets"
    frequency         TEXT,       -- e.g. "BD", "TDS", "PRN"
    duration          TEXT,       -- e.g. "5 days"
    instructions      TEXT,       -- e.g. "after meals", "avoid alcohol"
    ordered_by        INTEGER REFERENCES users(id),
    ordered_at        TEXT NOT NULL DEFAULT (datetime('now')),
    status            TEXT NOT NULL DEFAULT 'active'  -- active / stopped
);

CREATE TABLE IF NOT EXISTS dose_administrations (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    treatment_order_id INTEGER NOT NULL REFERENCES treatment_orders(id) ON DELETE CASCADE,
    inventory_item_id  INTEGER REFERENCES inventory_items(id),  -- set for drug orders
    billable_id        INTEGER REFERENCES billables(id),        -- set for procedure orders
    quantity           REAL NOT NULL DEFAULT 1,
    unit_price         REAL NOT NULL DEFAULT 0,  -- price snapshot at time of administration
    administered_by    INTEGER REFERENCES users(id),
    administered_at    TEXT NOT NULL DEFAULT (datetime('now')),
    notes              TEXT  -- free notes, or "procedure notes" when the order is a procedure
);

-- Consumable billables used while giving a specific dose/administration
-- (syringe, cotton swabs, gloves, etc.) — same idea as procedure_materials,
-- but scoped to one administration event rather than one procedure record.
CREATE TABLE IF NOT EXISTS dose_materials (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    dose_administration_id INTEGER NOT NULL REFERENCES dose_administrations(id) ON DELETE CASCADE,
    inventory_item_id       INTEGER NOT NULL REFERENCES inventory_items(id),
    quantity                REAL NOT NULL,
    unit_price              REAL NOT NULL  -- price snapshot at time of use
);
CREATE INDEX IF NOT EXISTS idx_dose_materials_dose ON dose_materials(dose_administration_id);

-- ---------- Referrals ----------

CREATE TABLE IF NOT EXISTS referrals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    visit_id    INTEGER NOT NULL REFERENCES visits(id),
    destination TEXT NOT NULL,
    reason      TEXT,
    created_by  INTEGER REFERENCES users(id),
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Take-home medications given at discharge. Structured the same way a drug
-- is ordered in the Treatments tab (pharmacy-stock-aware, with route/dose/
-- frequency/duration/instructions) rather than free text, and billed +
-- deducted from stock immediately at discharge (a one-time take-home
-- dispense, unlike treatment_orders which are administered/dosed over
-- time during the stay).
CREATE TABLE IF NOT EXISTS discharge_medications (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    admission_id      INTEGER NOT NULL REFERENCES admissions(id),
    inventory_item_id INTEGER REFERENCES inventory_items(id),  -- set when picked from pharmacy stock
    drug_name         TEXT NOT NULL,
    route             TEXT,
    dose              TEXT,
    frequency         TEXT,
    duration          TEXT,
    instructions      TEXT,
    quantity          REAL NOT NULL DEFAULT 0,  -- quantity dispensed take-home (0 if not in stock / not dispensed)
    unit_price        REAL NOT NULL DEFAULT 0,  -- price snapshot at time of discharge
    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_visits_patient ON visits(patient_id);
CREATE INDEX IF NOT EXISTS idx_visits_status ON visits(status);
CREATE INDEX IF NOT EXISTS idx_patients_name ON patients(full_name);
CREATE INDEX IF NOT EXISTS idx_invoice_items_invoice ON invoice_items(invoice_id);
CREATE INDEX IF NOT EXISTS idx_beds_ward ON beds(ward_id);
CREATE INDEX IF NOT EXISTS idx_admissions_status ON admissions(status);
CREATE INDEX IF NOT EXISTS idx_vitals_visit ON vitals_records(visit_id);
CREATE INDEX IF NOT EXISTS idx_complaints_visit ON complaints(visit_id);
CREATE INDEX IF NOT EXISTS idx_history_visit ON history_records(visit_id);
CREATE INDEX IF NOT EXISTS idx_examination_visit ON examination_records(visit_id);
CREATE INDEX IF NOT EXISTS idx_diagnoses_visit ON diagnoses(visit_id);
CREATE INDEX IF NOT EXISTS idx_notes_visit ON encounter_notes(visit_id);
CREATE INDEX IF NOT EXISTS idx_treatment_orders_visit ON treatment_orders(visit_id);
CREATE INDEX IF NOT EXISTS idx_dose_admin_order ON dose_administrations(treatment_order_id);

-- ---------- Starter presenting-complaints list (admin-editable) ----------
INSERT OR IGNORE INTO complaint_master (text) VALUES
    ('Fever'), ('Cough'), ('Cough with blood (haemoptysis)'), ('Difficulty breathing'),
    ('Chest pain'), ('Palpitations'), ('Headache'), ('Dizziness'), ('Loss of consciousness'),
    ('Convulsions/seizures'), ('Confusion'), ('Numbness or tingling'), ('Limb weakness'),
    ('Visual disturbance'), ('Ear pain or discharge'), ('Sore throat'),
    ('Runny or blocked nose'), ('Toothache'), ('Difficulty swallowing'),
    ('Abdominal pain'), ('Nausea'), ('Vomiting'), ('Diarrhoea'), ('Constipation'),
    ('Loss of appetite'), ('Weight loss'), ('Yellowing of eyes/skin (jaundice)'),
    ('Blood in stool'), ('Frequent urination'), ('Painful urination'), ('Blood in urine'),
    ('Missed menses'), ('Vaginal bleeding'), ('Vaginal discharge'), ('Pregnancy-related complaint'),
    ('Joint pain'), ('Back pain'), ('Body aches'), ('Muscle weakness'), ('Swelling (oedema)'),
    ('Skin rash'), ('Itching'), ('Wound'), ('Burns'), ('Trauma/injury'),
    ('Animal or snake bite'), ('Poisoning/ingestion'), ('Fatigue/weakness'), ('Night sweats'),
    ('Insomnia'), ('Anxiety or low mood'), ('Allergic reaction'), ('Follow-up visit'),
    ('Routine check-up');
