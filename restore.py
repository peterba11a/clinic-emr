"""Restore from an encrypted backup \u2014 run this on a freshly installed
machine (or a freshly installed clinic-emr folder) before starting the
app for the first time, once the clinic has signed in to Google Drive for
Desktop under its usual account so the synced backup folder is present
on this machine.

Usage:
    python restore.py "C:\\Users\\Clinic\\Google Drive\\My Drive\\ClinicBackups"

Finds the newest snapshot in that folder, decrypts it using the recovery
key stored alongside it (no separate key to type in \u2014 that was the whole
point of the convenience-first choice), and writes it into instance/clinic.db.
"""
import sys
import shutil
from pathlib import Path

from cryptography.fernet import Fernet

from db import DB_PATH, INSTANCE_DIR


def restore_from(folder_str: str):
    folder = Path(folder_str)
    if not folder.exists():
        print(f"Folder not found: {folder}")
        print("Make sure Google Drive for Desktop has finished syncing on this machine first.")
        sys.exit(1)

    key_file = folder / "clinic_recovery_key.key"
    if not key_file.exists():
        print("No recovery key found in that folder \u2014 cannot decrypt any backup found there.")
        sys.exit(1)

    backups = sorted(folder.glob("clinic_backup_*.enc"), key=lambda p: p.name, reverse=True)
    if not backups:
        print("No backup snapshots found in that folder.")
        sys.exit(1)

    latest = backups[0]
    print(f"Restoring from {latest.name} ...")

    fernet = Fernet(key_file.read_bytes())
    decrypted = fernet.decrypt(latest.read_bytes())

    INSTANCE_DIR.mkdir(exist_ok=True)
    if DB_PATH.exists():
        safety_copy = DB_PATH.with_suffix(".db.before-restore")
        shutil.copy2(DB_PATH, safety_copy)
        print(f"Existing database (if any) saved as {safety_copy.name} just in case.")

    DB_PATH.write_bytes(decrypted)
    print("Database restored.")

    for logo_backup in folder.glob("clinic_logo_backup.*"):
        uploads_dir = Path(__file__).resolve().parent / "static" / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)
        dest = uploads_dir / f"clinic_logo{logo_backup.suffix}"
        shutil.copy2(logo_backup, dest)
        print(f"Clinic logo restored ({dest.name}).")

    print("\nDone. Start the app normally now.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python restore.py <path to the Google Drive synced backup folder>")
        sys.exit(1)
    restore_from(sys.argv[1])
