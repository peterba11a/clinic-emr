import re
import sys
import requests

BASE = "http://127.0.0.1:8080"
s = requests.Session()


def check(label, resp, expect=200):
    ok = resp.status_code == expect
    print(f"{'OK ' if ok else 'FAIL'} {label}: {resp.status_code} {resp.url}")
    if not ok:
        print(resp.text[:800])
        sys.exit(1)
    return resp


# 1. login
r = check("login page", s.get(f"{BASE}/login"))
r = check("login submit", s.post(f"{BASE}/login", data={"username": "admin", "password": "admin123"}, allow_redirects=True))
assert "Terms of Use" in r.text, "first login should gate on Terms of Use acceptance"
r = check("decline terms (unchecked)", s.post(f"{BASE}/terms", data={}, allow_redirects=True))
assert "check the box" in r.text.lower(), "submitting without agreeing should be rejected"
r = check("accept terms", s.post(f"{BASE}/terms", data={"agree": "1"}, allow_redirects=True))
assert "Welcome" in r.text or "Dashboard" in r.text or "Waiting list" in r.text or "admin" in r.text.lower()
r = check("terms not shown again this version", s.get(f"{BASE}/visits/queue"))
assert "Terms of Use" not in r.text

# 1b. setup reminder banners: fresh DB has no clinic name and no backup
# folder configured, so an Admin should see both "don't show again" nudges
# on any ordinary page.
r = check("reminders visible before setup", s.get(f"{BASE}/visits/queue"))
assert "letterhead isn't set up" in r.text, "clinic profile reminder missing"
assert "backups aren't pointed" in r.text, "backup reminder missing"

# 2. register patient
r = check("new patient form", s.get(f"{BASE}/patients/new"))
r = check("submit patient", s.post(f"{BASE}/patients/new", data={
    "full_name": "Test Patient", "dob": "", "age_years": "34", "sex": "F",
    "phone": "0771234567", "village": "Kiruddu"
}, allow_redirects=True))
m = re.search(r"/patients/(\d+)", r.url)
patient_id = int(m.group(1))
print("patient_id", patient_id)

# 2b. patient code format: CC-LLL-NNN (clinic prefix - 3 random letters - 3 random digits)
r = check("patient view (code format)", s.get(f"{BASE}/patients/{patient_id}"))
code_match = re.search(r"\(([A-Z]{2}-[A-Z]{3}-\d{3})\)", r.text)
assert code_match, "patient code not in CC-LLL-NNN format"
print("patient_code", code_match.group(1))

# 3. checkin with triage (priority + vitals)
r = check("checkin form", s.get(f"{BASE}/visits/checkin/{patient_id}"))
bm = re.search(r'<option value="(\d+)">General consultation', r.text)
consult_billable_id = bm.group(1)
r = check("checkin submit (triage)", s.post(f"{BASE}/visits/checkin/{patient_id}", data={
    "billable_id": consult_billable_id, "complaint": "Fever and headache", "priority": "Urgent",
    "bp": "120/80", "pulse": "88", "temp_c": "38.2", "resp_rate": "18", "spo2": "97",
    "weight_kg": "60", "height_cm": "165", "rbs": "5.4", "vitals_other": "",
}, allow_redirects=True))

r = check("queue", s.get(f"{BASE}/visits/queue"))
assert "Urgent" in r.text, "priority badge missing from queue"
m = re.search(r"/visits/(\d+)", r.text)
visit_id = int(m.group(1))
print("visit_id", visit_id)

# 4. tabbed encounter record: complaint, history, examination, extra vitals, diagnosis, notes
r = check("visit detail get", s.get(f"{BASE}/visits/{visit_id}"))
for tab in ["Vitals", "Complaints", "History", "Examination", "Investigation", "Diagnoses", "Treatments", "Notes"]:
    assert tab in r.text, f"tab '{tab}' missing from encounter page"

# printing must be available mid-visit, not just once the encounter is
# marked "completed" — the visit is still 'waiting'/'in_progress' here
assert "badge-completed" not in r.text, "visit unexpectedly already shows as completed"
assert f"/print/prescription/{visit_id}" in r.text, "prescription print link hidden mid-visit"
assert f"/print/visit-summary/{visit_id}" in r.text, "visit summary print link hidden mid-visit"
assert f"/print/complete-record/{patient_id}" in r.text, "complete record print link hidden mid-visit"
check("print prescription mid-visit (not completed)", s.get(f"{BASE}/print/prescription/{visit_id}"))
check("print visit summary mid-visit (not completed)", s.get(f"{BASE}/print/visit-summary/{visit_id}"))

r = check("add complaint", s.post(f"{BASE}/visits/{visit_id}/complaint", data={"text": "Also reports chills", "duration": "2 days"}, allow_redirects=True))
assert "duration: 2 days" in r.text
r = check("add history", s.post(f"{BASE}/visits/{visit_id}/history", data={"text": "No significant past medical history"}, allow_redirects=True))
r = check("add examination", s.post(f"{BASE}/visits/{visit_id}/examination", data={"text": "Mildly pale conjunctiva, no jaundice"}, allow_redirects=True))
r = check("add extra vitals", s.post(f"{BASE}/visits/{visit_id}/vitals", data={
    "bp": "118/76", "pulse": "84", "temp_c": "37.8", "resp_rate": "16", "spo2": "98",
    "weight_kg": "60", "height_cm": "165", "rbs": "5.1", "other": ""
}, allow_redirects=True))

# diagnosis search API (ICD-10 typeahead) before recording the actual diagnosis
r = check("diagnosis search api", s.get(f"{BASE}/visits/api/diagnoses-search?q=malaria"))
dx_results = r.json()
assert dx_results and any("malaria" in d["text"].lower() for d in dx_results), "ICD-10 search returned no malaria match"
malaria_code = next(d["code"] for d in dx_results if "malaria" in d["text"].lower())
print("malaria icd10 sample code", malaria_code)

r = check("add diagnosis", s.post(f"{BASE}/visits/{visit_id}/diagnosis", data={
    "text": "Malaria", "icd10_code": malaria_code, "status": "Preliminary"
}, allow_redirects=True))
assert "Preliminary" in r.text and malaria_code in r.text
r = check("add nursing note", s.post(f"{BASE}/visits/{visit_id}/note", data={"note_type": "nursing", "text": "Patient comfortable, vitals stable"}, allow_redirects=True))
r = check("add doctor's note", s.post(f"{BASE}/visits/{visit_id}/note", data={"note_type": "doctor", "text": "Continue current management"}, allow_redirects=True))
assert "Nursing note" in r.text and "Doctor&#39;s note" in r.text or "Doctor's note" in r.text

# 5. pharmacy: add inventory item, then dispense
r = check("pharmacy new item form", s.get(f"{BASE}/pharmacy/new"))
r = check("add drug", s.post(f"{BASE}/pharmacy/new", data={
    "name": "Coartem", "item_type": "drug", "unit": "tablet", "unit_price": "500",
    "stock_qty": "200", "expiry_date": "2027-01-01", "reorder_threshold": "20"
}, allow_redirects=True))
r = check("add material", s.post(f"{BASE}/pharmacy/new", data={
    "name": "Dressing pack", "item_type": "material", "unit": "pack", "unit_price": "3000",
    "stock_qty": "50", "expiry_date": "", "reorder_threshold": "5"
}, allow_redirects=True))

r = check("dispense form", s.get(f"{BASE}/pharmacy/dispense/{visit_id}"))
im = re.search(r'<option value="(\d+)">Coartem', r.text)
coartem_id = im.group(1)
r = check("dispense submit", s.post(f"{BASE}/pharmacy/dispense/{visit_id}", data={
    "item_id": coartem_id, "quantity": "24"
}, allow_redirects=True))
assert "Dispensed 24.0" in r.text or "Dispensed 24" in r.text, "dispense confirmation missing"

# 6. procedure with material breakdown
r = check("procedure form", s.get(f"{BASE}/procedures/record/{visit_id}"))
pm = re.search(r'<option value="(\d+)">Wound dressing', r.text)
wound_billable_id = pm.group(1)
mm = re.search(r'<option value="(\d+)">Dressing pack', r.text)
material_id = mm.group(1)
r = check("procedure submit", s.post(f"{BASE}/procedures/record/{visit_id}", data={
    "billable_id": wound_billable_id, "notes": "Cleaned and dressed",
    "material_item_id": [material_id], "material_quantity": ["1"]
}, allow_redirects=True))

# 7. lab order + result
r = check("lab form", s.get(f"{BASE}/lab/order/{visit_id}"))
lm = re.search(r'<option value="(\d+)">Malaria RDT', r.text)
lab_billable_id = lm.group(1)
r = check("lab order submit", s.post(f"{BASE}/lab/order/{visit_id}", data={"billable_id": lab_billable_id}, allow_redirects=True))
om = re.search(r"/lab/result/(\d+)", r.text)
lab_order_id = om.group(1)
r = check("lab result submit", s.post(f"{BASE}/lab/result/{lab_order_id}", data={"result_text": "Positive"}, allow_redirects=True))

# 8. radiology request + done
r = check("radiology form", s.get(f"{BASE}/radiology/request/{visit_id}"))
rm = re.search(r'<option value="(\d+)">X-ray request', r.text)
xray_billable_id = rm.group(1)
r = check("radiology submit", s.post(f"{BASE}/radiology/request/{visit_id}", data={
    "billable_id": xray_billable_id, "reason": "Rule out pneumonia"
}, allow_redirects=True))
dm = re.search(r"/radiology/done/(\d+)", r.text)
rad_id = dm.group(1)
r = check("radiology mark done", s.post(f"{BASE}/radiology/done/{rad_id}", data={"findings_text": "No consolidation"}, allow_redirects=True))

# 9. admission: admit, verify inpatients list, block finalize while admitted, treat + administer dose, discharge
r = check("visit detail (before admit)", s.get(f"{BASE}/visits/{visit_id}"))
bedm = re.search(r'<option value="(\d+)">General Ward — Bed 1', r.text)
bed_id = bedm.group(1)
r = check("admit patient", s.post(f"{BASE}/admissions/admit/{visit_id}", data={"bed_id": bed_id}, allow_redirects=True))
assert "Admitted" in r.text

r = check("inpatients list", s.get(f"{BASE}/admissions/"))
assert "Test Patient" in r.text, "admitted patient missing from inpatients list"

r = check("finalize blocked while admitted", s.post(f"{BASE}/visits/{visit_id}/finalize", data={}, allow_redirects=True))
assert "discharge them first" in r.text.lower()

r = check("order treatment", s.post(f"{BASE}/visits/{visit_id}/treatment", data={
    "order_type": "drug", "drug_name": "Coartem", "inventory_item_id": coartem_id,
    "route": "IV", "dose": "4 tablets", "frequency": "BD", "duration": "3 days",
    "instructions": "Take with food",
}, allow_redirects=True))
assert "4 tablets" in r.text and "Take with food" in r.text and "IV" in r.text
adm_order = re.search(r"/visits/treatment/(\d+)/administer", r.text)
order_id = adm_order.group(1)
r = check("administer dose", s.post(f"{BASE}/visits/treatment/{order_id}/administer", data={
    "inventory_item_id": coartem_id, "quantity": "4", "notes": "Morning dose"
}, allow_redirects=True))
assert "Dose recorded" in r.text

# logging a dose with billables used (syringe/cotton-swab style consumables)
r = check("administer dose with billables used", s.post(f"{BASE}/visits/treatment/{order_id}/administer", data={
    "inventory_item_id": coartem_id, "quantity": "4", "notes": "Evening dose",
    "material_item_id": [material_id], "material_quantity": ["2"],
}, allow_redirects=True))
assert "Dose recorded" in r.text
r = check("visit detail shows billables used", s.get(f"{BASE}/visits/{visit_id}"))
assert "Also used" in r.text and "Dressing pack" in r.text, "materials used during dose administration not shown"

# a procedure-type treatment order: picked from the admin's billables
# catalog (not free text) so every administration bills the same, correct
# item automatically — administer with procedure notes + billables used
r = check("order treatment (procedure)", s.post(f"{BASE}/visits/{visit_id}/treatment", data={
    "order_type": "procedure", "billable_id": wound_billable_id
}, allow_redirects=True))
assert "Wound dressing" in r.text
proc_match = re.search(
    r'/visits/treatment/(\d+)/administer">\s*<h3>Log dose .*?Wound dressing', r.text
)
assert proc_match, "could not find the procedure order's administer form"
proc_order_id = proc_match.group(1)
# note: no billable_id in this POST — it must be inherited from the order itself
r = check("administer procedure dose with notes+materials", s.post(f"{BASE}/visits/treatment/{proc_order_id}/administer", data={
    "quantity": "1",
    "notes": "Wound clean, no discharge, redressed with sterile gauze",
    "material_item_id": [material_id], "material_quantity": ["1"],
}, allow_redirects=True))
assert "Administration recorded" in r.text
r = check("visit detail shows procedure notes", s.get(f"{BASE}/visits/{visit_id}"))
assert "Wound clean, no discharge" in r.text, "procedure notes not shown"
assert "Billed as:</strong> Wound dressing" in r.text, "order's locked-in billable not shown in dose dialog"

# treatment order with a drug not in pharmacy stock (no inventory_item_id) — should still be recorded
r = check("order treatment (not in stock)", s.post(f"{BASE}/visits/{visit_id}/treatment", data={
    "order_type": "drug", "drug_name": "Patient's own supply of Metformin",
    "dose": "500mg", "frequency": "OD", "duration": "ongoing",
}, allow_redirects=True))
assert "Patient&#39;s own supply of Metformin" in r.text or "Patient's own supply of Metformin" in r.text

# stock level right before discharge, so we can confirm the take-home
# medication below actually gets deducted
r = check("pharmacy stock before discharge", s.get(f"{BASE}/pharmacy/"))
stock_before = float(re.search(r'Coartem</td>\s*<td>drug</td>\s*<td>tablet</td>\s*<td>[^<]*</td>\s*<td>\s*([\d.]+)', r.text, re.S).group(1))

admm = re.search(r'/admissions/(\d+)/discharge', r.text) or re.search(r'/admissions/(\d+)/discharge', s.get(f"{BASE}/visits/{visit_id}").text)
admission_id = admm.group(1)
# discharge medications are picked from pharmacy stock, the same way a drug
# is ordered in Treatments — and must be billed + deducted from stock
r = check("discharge patient", s.post(f"{BASE}/admissions/{admission_id}/discharge", data={
    "discharge_summary": "Afebrile, tolerating oral meds. Follow up in clinic in 1 week.",
    "follow_up_date": "2026-10-20",
    "med_drug_name": ["Coartem"],
    "med_inventory_item_id": [coartem_id],
    "med_route": ["Oral"],
    "med_dose": ["4 tablets"],
    "med_frequency": ["BD"],
    "med_duration": ["3 days"],
    "med_instructions": ["Take with food"],
    "med_quantity": ["10"],
}, allow_redirects=True))
assert "Discharge summary" in r.text  # redirected straight to the printable discharge summary

r = check("print discharge summary", s.get(f"{BASE}/print/discharge-summary/{admission_id}"))
assert "Discharge summary" in r.text
assert "Coartem" in r.text and "4 tablets" in r.text and "BD" in r.text, "discharge medications missing from printed discharge summary"
assert "2026-10-20" in r.text, "follow-up date missing from printed discharge summary"
assert "Printed by" in r.text and "Signature:" in r.text, "signature footer missing from discharge summary"

r = check("pharmacy stock after discharge", s.get(f"{BASE}/pharmacy/"))
stock_after = float(re.search(r'Coartem</td>\s*<td>drug</td>\s*<td>tablet</td>\s*<td>[^<]*</td>\s*<td>\s*([\d.]+)', r.text, re.S).group(1))
assert stock_after == stock_before - 10, f"discharge medication did not deduct stock ({stock_before} -> {stock_after})"

r = check("invoice shows discharge medication charge", s.get(f"{BASE}/billing/invoice/{visit_id}"))
assert "discharge medication" in r.text.lower(), "discharge medication not billed to invoice"

# 10. referral
r = check("referral form", s.get(f"{BASE}/referrals/new/{visit_id}"))
r = check("referral submit", s.post(f"{BASE}/referrals/new/{visit_id}", data={
    "destination": "Kiruddu National Referral Hospital", "reason": "Further workup"
}, allow_redirects=True))
refm = re.search(r"/print/referral/(\d+)", r.url)
referral_id = int(refm.group(1))

# 11. billing: view invoice (should include bed charge + dose + everything else), pay
r = check("invoice view", s.get(f"{BASE}/billing/invoice/{visit_id}"))
assert "Bed charge" in r.text, "bed charge missing from invoice"
invm = re.search(r"/billing/pay/(\d+)", r.text)
invoice_id = int(invm.group(1))
r = check("record payment", s.post(f"{BASE}/billing/pay/{invoice_id}", data={"amount": "10000", "method": "cash"}, allow_redirects=True))
assert "Balance" in r.text

# 12. print remaining documents — every one of these must show who printed
# it with space to sign, and the comprehensive ones must actually be
# comprehensive (not just complaint/latest-vitals/diagnosis as before).
r = check("print prescription", s.get(f"{BASE}/print/prescription/{visit_id}"))
assert "Printed by" in r.text and "Signature:" in r.text
assert "Medication administration record" in r.text, "dose administration log (MAR) missing from prescription print"
assert "Morning dose" in r.text and "Evening dose" in r.text, "individual doses given missing from MAR"

r = check("print referral", s.get(f"{BASE}/print/referral/{referral_id}"))
assert "Printed by" in r.text and "Signature:" in r.text

r = check("print visit summary", s.get(f"{BASE}/print/visit-summary/{visit_id}"))
assert "Printed by" in r.text and "Signature:" in r.text
for must_have in [
    "Also reports chills",              # complaint
    "No significant past medical history",  # history
    "Mildly pale conjunctiva",          # examination
    "Positive",                         # lab result
    "No consolidation",                 # radiology finding
    "Coartem",                          # treatment/drug order
    "Patient comfortable, vitals stable",  # nursing note
    "Kiruddu National Referral Hospital",  # referral
    "4 tablets Oral BD x 3 days",       # discharge medications (structured, pharmacy-linked)
]:
    assert must_have in r.text, f"visit summary missing '{must_have}' — not comprehensive"

r = check("print complete record", s.get(f"{BASE}/print/complete-record/{patient_id}"))
assert "Printed by" in r.text and "Signature:" in r.text
for must_have in ["Also reports chills", "Coartem", "Positive", "No consolidation", "Malaria"]:
    assert must_have in r.text, f"complete record missing '{must_have}' — not comprehensive"

r = check("print receipt", s.get(f"{BASE}/print/receipt/{invoice_id}"))
assert "Printed by" in r.text and "Signature:" in r.text

# 13. admin: wards & beds, multi-role user (incl. new Nurse role), billables, clinic profile, backup status
r = check("wards page", s.get(f"{BASE}/admin/wards"))
assert "General Ward" in r.text
r = check("add ward", s.post(f"{BASE}/admin/wards", data={"name": "Maternity Ward", "nightly_rate": "25000"}, allow_redirects=True))
assert "Maternity Ward" in r.text
wardm = re.search(r"edit_ward', ward_id=(\d+)", r.text) or re.search(r"/admin/wards/(\d+)/edit", r.text)
new_ward_id = None
for wm in re.finditer(r'action="/admin/wards/(\d+)/beds"', r.text):
    new_ward_id = wm.group(1)
assert new_ward_id, "could not find newly added ward's bed-add form"
r = check("add bed to new ward", s.post(f"{BASE}/admin/wards/{new_ward_id}/beds", data={"name": "Bed A"}, allow_redirects=True))
assert "Bed A" in r.text

r = check("admin users page", s.get(f"{BASE}/admin/users"))
r = check("new user form", s.get(f"{BASE}/admin/users/new"))
role_pairs = re.findall(r'<input type="checkbox" name="role_ids" value="(\d+)"[^>]*>\s*\n?\s*(\w+)', r.text)
name_to_id = {v: k for k, v in role_pairs}
assert "Nurse" in name_to_id, "Nurse role not offered on user creation form"
r = check("create multi-role user", s.post(f"{BASE}/admin/users/new", data={
    "username": "jane", "full_name": "Jane Doe", "password": "pass1234",
    "role_ids": [name_to_id["Pharmacy"], name_to_id["Lab"]],
}, allow_redirects=True))
assert "created" in r.text.lower() or "Staff accounts" in r.text, r.text[:500]
r = check("create nurse user", s.post(f"{BASE}/admin/users/new", data={
    "username": "grace", "full_name": "Grace Nurse", "password": "pass1234",
    "role_ids": [name_to_id["Nurse"]],
}, allow_redirects=True))

r = check("billables page", s.get(f"{BASE}/admin/billables"))
assert 'name="price_per_page" value="0"' in r.text, "printing price should default to 0 (off)"

# 13a. per-page printing charge: off by default (the 6 prints done above
# added nothing to the bill), then turn it on and confirm every print type
# bills the visit automatically, with a reprint billing again each time.
r = check("invoice before any printing price was ever set", s.get(f"{BASE}/billing/invoice/{visit_id}"))
assert "Printing —" not in r.text, "printing charges appeared before a price was ever configured"

r = check("set printing price", s.post(f"{BASE}/admin/printing-price", data={"price_per_page": "500"}, allow_redirects=True))
assert "Printing price updated" in r.text

check("billed print: prescription", s.get(f"{BASE}/print/prescription/{visit_id}"))
check("billed print: prescription again (reprint bills again)", s.get(f"{BASE}/print/prescription/{visit_id}"))
check("billed print: referral", s.get(f"{BASE}/print/referral/{referral_id}"))
check("billed print: visit summary", s.get(f"{BASE}/print/visit-summary/{visit_id}"))
check("billed print: complete record", s.get(f"{BASE}/print/complete-record/{patient_id}"))
check("billed print: discharge summary", s.get(f"{BASE}/print/discharge-summary/{admission_id}"))
check("billed print: receipt", s.get(f"{BASE}/print/receipt/{invoice_id}"))

r = check("invoice reflects printing charges", s.get(f"{BASE}/billing/invoice/{visit_id}"))
assert r.text.count("Printing — Prescription") == 2, "reprinting the same document should bill again each time"
for label in [
    "Printing — Referral letter", "Printing — Visit summary", "Printing — Complete patient record",
    "Printing — Discharge summary", "Printing — Receipt",
]:
    assert label in r.text, f"'{label}' charge missing from invoice after printing it"

r = check("receipt shows its own printing charge", s.get(f"{BASE}/print/receipt/{invoice_id}"))
assert "Printing — Receipt" in r.text, "receipt print should reflect its own printing charge on itself"

# turning the price back to 0 should stop further charges without touching
# charges already billed
r = check("turn printing price back off", s.post(f"{BASE}/admin/printing-price", data={"price_per_page": "0"}, allow_redirects=True))
check("print prescription with price back at 0", s.get(f"{BASE}/print/prescription/{visit_id}"))
r = check("no new printing charge once price is back to 0", s.get(f"{BASE}/billing/invoice/{visit_id}"))
assert r.text.count("Printing — Prescription") == 2, "no new printing charge should be added once price is back to 0"

r = check("connect device page", s.get(f"{BASE}/admin/connect-device"))
assert "clinicserver.local:8080" in r.text, "primary connection address missing"
assert "8080" in r.text
assert "Download the script" in r.text, "static-IP fallback script not offered"
r = check("download static-ip script", s.get(f"{BASE}/admin/connect-device/make-ip-static-script"))
assert "Administrator" in r.text and "New-NetIPAddress" in r.text, "static-ip script content looks wrong"

# 13b. admin: presenting complaints list + diagnoses list (ICD-10 + custom)
r = check("complaints master page", s.get(f"{BASE}/admin/complaints"))
assert "Fever" in r.text, "seeded complaint list missing"
r = check("add custom complaint", s.post(f"{BASE}/admin/complaints", data={"text": "Excessive thirst"}, allow_redirects=True))
assert "Excessive thirst" in r.text

r = check("diagnoses master page", s.get(f"{BASE}/admin/diagnoses"))
assert "bundled ICD-10 codes" in r.text
r = check("add custom diagnosis", s.post(f"{BASE}/admin/diagnoses", data={
    "code": "", "text": "Suspected witchcraft-related illness (local term)"
}, allow_redirects=True))
assert "Suspected witchcraft-related illness" in r.text
r = check("diagnoses master search", s.get(f"{BASE}/admin/diagnoses?q=malaria"))
assert "Malaria" in r.text

r = check("clinic profile page", s.get(f"{BASE}/admin/clinic-profile"))
r = check("clinic profile save", s.post(f"{BASE}/admin/clinic-profile", data={
    "name": "Kiruddu Community Clinic", "address": "Kampala, Uganda", "phone": "0700111222",
    "phone2": "", "website": "www.example.clinic", "motto": "Caring, always.",
    "currency": "KES",
    "social_facebook": "fb.com/kiruddu", "social_instagram": "", "social_whatsapp": "",
    "social_twitter": "", "social_other": ""
}, allow_redirects=True))
assert "updated" in r.text.lower()

# the profile reminder should now be gone (name is set), but the backup
# one should still show since no backup folder has been configured yet
r = check("profile reminder gone after setup", s.get(f"{BASE}/visits/queue"))
assert "letterhead isn't set up" not in r.text, "profile reminder still showing after profile was set"
assert "backups aren't pointed" in r.text, "backup reminder disappeared without being set up or dismissed"

r = check("dismiss backup reminder", s.post(f"{BASE}/admin/dismiss-reminder/backup", allow_redirects=True))
r = check("backup reminder gone after dismiss", s.get(f"{BASE}/visits/queue"))
assert "backups aren't pointed" not in r.text, "backup reminder still showing after being dismissed"

r = check("backup status page", s.get(f"{BASE}/admin/backup-status"))
assert "Connecting Google Drive" in r.text, "Google Drive linkup explanation missing"

# currency now shows on money amounts clinic-wide
r = check("invoice shows currency", s.get(f"{BASE}/billing/invoice/{visit_id}"))
assert "KES" in r.text, "currency not reflected on invoice"
r = check("receipt shows currency", s.get(f"{BASE}/print/receipt/{invoice_id}"))
assert "KES" in r.text, "currency not reflected on printed receipt"

# re-print prescription now that clinic profile has a name, confirm letterhead shows,
# and confirm the Rx table reflects the structured dose/frequency/duration/instructions
r = check("print prescription with letterhead", s.get(f"{BASE}/print/prescription/{visit_id}"))
assert "Kiruddu Community Clinic" in r.text, "letterhead name missing from printed prescription"
assert "Caring, always." in r.text
assert "Coartem" in r.text and "4 tablets" in r.text and "Take with food" in r.text
assert "Malaria" in r.text and "Preliminary" in r.text

# 14. self-service password change — a non-admin user, then admin's own
gs = requests.Session()
check("grace login", gs.post(f"{BASE}/login", data={"username": "grace", "password": "pass1234"}, allow_redirects=True))
check("grace accepts terms", gs.post(f"{BASE}/terms", data={"agree": "1"}, allow_redirects=True))
r = check("grace change-password page", gs.get(f"{BASE}/account/password"))
r = check("grace wrong current password", gs.post(f"{BASE}/account/password", data={
    "current_password": "wrongpass", "new_password": "newpass123", "confirm_password": "newpass123",
}, allow_redirects=True))
assert "incorrect" in r.text.lower()
r = check("grace change password", gs.post(f"{BASE}/account/password", data={
    "current_password": "pass1234", "new_password": "newpass123", "confirm_password": "newpass123",
}, allow_redirects=True))
assert "Password changed" in r.text

gs2 = requests.Session()
r = check("grace old password now fails", gs2.post(f"{BASE}/login", data={"username": "grace", "password": "pass1234"}))
assert "Incorrect username or password" in r.text
r = check("grace new password works", gs2.post(f"{BASE}/login", data={"username": "grace", "password": "newpass123"}, allow_redirects=True))
assert "Grace Nurse" in r.text

# admin can change their own password too, via the same self-service page
# (distinct from Admin -> Staff accounts, which resets someone ELSE's password)
r = check("admin change-password page", s.get(f"{BASE}/account/password"))
r = check("admin change password", s.post(f"{BASE}/account/password", data={
    "current_password": "admin123", "new_password": "adminnew123", "confirm_password": "adminnew123",
}, allow_redirects=True))
assert "Password changed" in r.text
as2 = requests.Session()
r = check("admin new password works", as2.post(f"{BASE}/login", data={"username": "admin", "password": "adminnew123"}, allow_redirects=True))
assert "Administrator" in r.text

print("\nALL SMOKE TESTS PASSED")
