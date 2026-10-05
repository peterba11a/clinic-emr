"""Terms of Use that every user must accept before using Clinic EMR.

Acceptance is tracked per user (users.terms_accepted_version /
terms_accepted_at — see db.py's migration and routes/terms.py), not per
device or per session, so it follows a staff member even if they log in from
a different computer. Bump TERMS_VERSION whenever the wording changes in any
way that matters (not for typo fixes) — every user, including ones who
accepted an older version, will be shown the new text and have to accept it
again before they can do anything else.
"""

TERMS_VERSION = "1.0"

TERMS_PARAGRAPHS = [
    "Clinic EMR is a tool for recording and billing patient care, provided "
    "\"as is\", without warranty of any kind. The clinic that installs and "
    "operates it — through its Administrator and staff, not the software's "
    "developer — is solely responsible for the completeness, accuracy, "
    "privacy, and security of all data entered into or stored by it, "
    "including patient records, billing information, user accounts, and "
    "backups.",

    "This clinic is the data controller for every patient record kept in "
    "this system and is responsible for complying with any data protection "
    "law that applies to it (including Uganda's Data Protection and Privacy "
    "Act, 2019, where applicable), for obtaining any patient consent that "
    "is required, and for keeping this data confidential and secure — "
    "including deciding who gets a login, keeping passwords private, and "
    "checking that backups are actually running.",

    "Clinic EMR is a record-keeping and billing aid. It does not practice "
    "medicine and does not check the clinical accuracy of anything entered "
    "into it. It is not a substitute for the judgment of a qualified "
    "clinician. Every diagnosis, prescription, treatment, and clinical "
    "decision remains the responsibility of the clinician who makes it.",

    "To the fullest extent permitted by law, the developer of this software "
    "is not liable for any loss, damage, clinical outcome, data loss, or "
    "other harm arising from its use, misuse, or inability to use.",

    "By continuing, you confirm that you have read and understood this, "
    "and that you are using this system on behalf of, and in line with the "
    "policies of, this clinic.",
]
