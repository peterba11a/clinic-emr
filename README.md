# Clinic EMR

A free, offline-first electronic medical record and billing system built
for small clinics — no IT staff, no server room, and no ongoing costs.
Runs entirely on one ordinary Windows computer in the clinic; other
devices on the same WiFi/network just open it in a browser.

## What it does

- **Patients** — register, search, and a walk-in waiting queue that sorts
  by triage priority (Emergency/Urgent/Routine), then arrival time. Every
  patient gets an auto-generated code in the form `CC-LLL-NNN` (two letters
  from the clinic's name, three random letters, three random digits — e.g.
  `KC-XQP-482`), so no one has to think one up or risk a duplicate.
- **Triage** — Reception records a chief complaint, core vitals, and a
  priority level at check-in, so the clinician sees it without re-asking.
- **The clinical record** — a tabbed encounter for every visit (outpatient
  or inpatient): Vitals, Complaints, History, Examination, Investigation
  (links straight to that visit's Lab/Radiology orders), Diagnoses,
  Treatments, and a combined Nursing/Doctor's notes feed. Vitals include
  BP, pulse, temperature, respiratory rate, SpO2, weight, height, and RBS,
  plus a free-text field for anything else.
- **Presenting complaints** — a searchable, admin-editable list (seeded
  with ~50 common ones) that suggests matches as the clinician types in the
  Complaints tab, each with its own duration field.
- **Diagnoses** — searched from the full WHO ICD-10 code list (~12,000
  entries, bundled — no internet needed) as the clinician types, plus
  whatever clinic-specific terms Admin adds on top; each diagnosis is
  marked Confirmed or Preliminary.
- **Prescribing** — ordering a drug in the Treatments tab searches live
  pharmacy stock as you type and shows the quantity on hand, with separate
  fields for route (Oral, IV, IM, SC, etc.), dose, frequency (a dropdown of
  standard shorthand — OD, BD, TDS, PRN, etc. — with a custom option),
  duration, and instructions. A drug not carried in pharmacy stock can
  still be typed in freely.
- **Admissions** — Reception, Nurse, or Clinician can admit a patient to a
  ward/bed; the stay gets its own running vitals/notes/treatment log.
  Discharge is a popup (so it doesn't clutter the inpatient's page) with a
  required discharge summary, an optional follow-up date, and take-home
  medications picked from pharmacy stock the same way a drug is ordered in
  Treatments — each one is billed and deducted from stock the moment the
  patient is discharged. Discharge also frees the bed and automatically
  bills the nights stayed at that ward's nightly rate.
- **Treatments** — a prescribed drug or procedure is an order that can be
  administered multiple times (a dose/administration log), each dose
  deducting stock and billing automatically — built for multi-day
  admissions as much as single-visit prescriptions. A procedure order is
  picked from the same billables price list Admin maintains (not typed
  freely), so every administration of it bills correctly and consistently.
  Logging a dose opens a form for any consumable billables used alongside
  it (syringe, cotton swabs, gloves...), each billed and deducted from
  stock individually; a procedure-type treatment gets a dedicated
  procedure-notes field.
- **Pharmacy** — a stock/inventory list with expiry dates; dispensing a
  drug against a visit automatically deducts stock and adds it to that
  visit's bill.
- **Procedures** — a flat catalog charge per procedure, with an *optional*
  itemized breakdown of materials used (drawn from the same inventory as
  pharmacy) that also deducts stock and bills automatically.
- **Lab** — lightweight order + result recording (no instrument
  integration).
- **Radiology** — lightweight request + mark-done + optional findings note
  (no image storage/PACS).
- **Billing** — a shared price catalog (billables) behind consultations,
  procedures, lab and radiology; a running per-visit invoice that
  aggregates every charge automatically (including inpatient bed charges
  and per-dose treatment charges); checkout with support for partial
  payments; printable receipts. No insurance/claims processing.
- **Referrals** — a simple printable referral letter.
- **Printing** — the prescription, visit summary, complete patient record,
  referral, discharge summary, and receipt are all available to print at
  any point during a visit (including while admitted), not just once it's
  marked complete. The visit summary and complete patient record pull
  together everything recorded for the visit — complaints, history,
  examination, vitals, investigations (lab/radiology, with results),
  diagnoses, every treatment ordered and dose given, notes, referrals, and
  discharge details — rather than a one-line summary. The prescription
  print includes a medication administration record (every dose actually
  given, when, and by whom), useful for a multi-day admission as much as a
  one-off prescription. Every printed document shows who printed it with
  space to sign. Admin can optionally set a price per printed page (Admin →
  Billables → Printing, 0 by default = off); once set, printing any of
  these documents bills that charge to the patient's visit automatically —
  printing the same document again bills again, same as any other repeated
  action in the system.
- **Admin** — user accounts with one or more roles each (Reception,
  Clinician, Nurse, Pharmacy, Lab, Admin), the billables price list, wards
  and beds with nightly rates, the presenting-complaints and custom-diagnosis
  lists, a "Connect a device" page with step-by-step instructions (and the
  right address to use, plus an alternative one-time script for networks
  where that address doesn't resolve — see "Keeping the server's address
  from changing" below) for adding another computer/laptop to the clinic's
  system, clinic branding (logo, name, address, contacts, motto, currency —
  appears automatically on every prescription, referral, visit summary,
  complete record, discharge summary, and receipt), and backup status. A
  dismissible reminder nudges Admin to finish clinic-profile and backup
  setup if either hasn't been done yet.
- **Accounts** — every user, including Admin, can change their own password
  at any time from the "Change password" link next to their name (separate
  from Admin resetting someone else's password without knowing it). Every
  user also has to accept a one-time Terms of Use on their first login (and
  again if it's ever updated) before they can do anything else — it states
  that the clinic, not the developer, is solely responsible for the
  completeness, accuracy, privacy, and security of the data it enters and
  stores. See `terms.py` to review or edit the wording, and the disclaimer
  note below.
- **Reports** — a simple activity/revenue overview.

## Running it

### Option A — the installed Windows app (recommended for a clinic)

If you were given `ClinicEMR-Setup.exe`, just run it and click through the
installer. The app starts automatically every time the computer boots (and
restarts itself if it ever crashes while the computer is on) — nobody at
the clinic needs to open anything by hand day to day. It opens
`http://clinicserver.local:8080` (or `http://127.0.0.1:8080` on the server
machine itself) in a browser automatically.

The very first login is:

```
Username: admin
Password: admin123
```

**Change this password immediately** (Admin → Users → edit the admin
account) before putting any real patient data in.

Other devices in the clinic (e.g. a consultation-room laptop) reach the
same shared data by opening a browser and going to
`http://clinicserver.local:8080` — nothing needs to be installed on them.

### Option B — running from source (any OS, for development/testing)

```
pip install -r requirements.txt
python app.py
```

This starts the server on port 8080 and opens your browser to it
automatically. Press Ctrl+C in the terminal to stop it.

### Building the one-click Windows installer yourself

See `packaging/README.md`. This must be done on a Windows machine — it
cannot be produced from this Linux environment.

## Keeping the server's address from changing

The app advertises itself as `clinicserver.local` so other devices keep
working even if the router hands the server computer a new numeric IP
address after a reboot (standard mDNS — the same trick a network printer
uses). This works out of the box on Windows 10/11, macOS, iOS, Android,
and modern Linux, but a few older Windows machines or routers that block
multicast traffic won't resolve `.local` names.

If that happens at your clinic, Admin → Connect a device offers two
fixes, without needing to touch the app's code or reinstall anything:

1. Ask whoever manages the clinic's router to set a fixed ("static" or
   "reserved") address for the server computer, or
2. Run `packaging\make_ip_static.ps1` once, directly on the server
   computer (also installed to its Start Menu as "Make this computer's
   address permanent"). It takes whatever IP address the computer
   currently has and makes it permanent — no router access needed, and it
   doesn't change how the computer connects to anything. It needs an
   administrator prompt to run (changing network settings requires that),
   which is why it's a separate script rather than a button inside the
   app itself — Clinic EMR deliberately runs without admin rights day to
   day.

Either fix is a one-time thing; you don't need both.

## Backups

Every night, the app automatically makes an encrypted snapshot of the
clinic's data and writes it to a local folder — point that folder at a
Google Drive for Desktop synced folder (Admin → Backup status) and Google
Drive's own sync client uploads it whenever the internet is available.
Nothing about this requires the clinic (or you) to touch Google's API,
sign in to anything from inside the app, or manage tokens — it's just
files being written to a folder like any other.

**There is no Google sign-in inside Clinic EMR.** The one-time setup is:
install Google Drive for Desktop on the server computer, sign in there
(in Google's own app, not this one) with a Google account the clinic
owns, then paste the path of the folder it syncs into Admin → Backup
status. Admin → Backup status walks through this step by step, and until
it's done, a reminder banner says so on every page (dismissible once
you've set it up, or if you'd rather not use Google Drive for backups).

The decryption key is written into that same backup folder for
convenience (this is a deliberate choice — see the spec document,
section 3.2). This means the security of the clinic's backups rests
entirely on the security of that Google account, so:

- Use a Google account owned by the clinic itself, not a personal one.
- Turn on 2-factor authentication on it.

To restore onto a freshly installed machine (disaster recovery), once
Google Drive for Desktop has finished syncing that backup folder onto the
new machine:

```
ClinicEMR.exe --restore "C:\Users\Clinic\Google Drive\My Drive\ClinicBackups"
```

(or, running from source: `python app.py --restore <path to the folder>`)

Then start the app normally.

## Terms of Use / disclaimer

Every user has to tick a box agreeing to a short Terms of Use the first
time they log in (and again if the wording is ever updated) before the
system lets them do anything else — see `templates/terms.html` for what's
shown and `terms.py` for the text and version number. In short, it puts
responsibility for the data entered into the system — its completeness,
accuracy, privacy, and security — on the clinic operating it, not on
whoever wrote the software, and makes clear this is a record-keeping/
billing aid rather than a substitute for clinical judgement.

This isn't a substitute for proper legal advice. If you're distributing
this to a clinic handling real patient data, it's worth having a lawyer
(ideally one familiar with Uganda's Data Protection and Privacy Act, 2019)
look over the wording in `terms.py` before it goes live, especially if
you plan to charge for it, support it commercially, or use it outside
Uganda.

## Project website (GitHub Pages)

`docs/` contains a small, plain HTML/CSS website — a home page, an install
guide, and a role-by-role user guide — meant to be published with GitHub
Pages once this project is pushed to a GitHub repo: Settings → Pages →
"Deploy from a branch" → branch `main`, folder `/docs`. GitHub gives it a
free URL (`https://<your-username>.github.io/<repo-name>/`) with no server
to run and no extra cost. The "Download" links in `docs/*.html` point at a
placeholder (`https://github.com/`) — update them to your repo's Releases
page once the installer is uploaded there (see "Terms of Use / disclaimer"
above for how to distribute the `.exe` itself).

## Project layout

```
app.py              Flask app factory + entry point
db.py                SQLite connection/init helpers
auth.py              Login, sessions, role-based access control
backup.py            Nightly encrypted backup logic
scheduler.py         Background thread that triggers backup.py
restore.py           Disaster-recovery restore (--restore CLI mode)
mdns_advertise.py    Advertises this machine as clinicserver.local
billing_logic.py     Shared invoice helpers
routes/              One module per feature area (patients, visits, ...)
templates/           HTML templates (Jinja2), including print/ layouts
static/              CSS and uploaded clinic logo
schema.sql           Full database schema
icd10_codes.tsv      Bundled WHO ICD-10 code list (diagnosis picker data)
smoke_test.py        End-to-end test script covering the whole workflow
clinic_emr.spec      PyInstaller build spec (see packaging/README.md)
packaging/           Windows installer build scripts (Inno Setup, watchdog,
                     the optional static-IP fix script)
```

## Testing

With the app running (`python app.py`), in another terminal:

```
python smoke_test.py
```

This exercises the full workflow end to end (patient → visit → pharmacy →
procedure → lab → radiology → referral → billing → admin → printing) and
prints `ALL SMOKE TESTS PASSED` if everything works.

## What this deliberately does not do

- No insurance/claims processing.
- No lab-instrument or radiology-image (PACS) integration — lab and
  radiology are request/result tracking only.
- No cloud hosting, accounts, or subscription of any kind — everything
  runs on the clinic's own computer and its own Google Drive.
- No developer access to clinic data, ever. Backups go to a Google account
  the clinic owns and controls, not to any server run by whoever built
  this.
