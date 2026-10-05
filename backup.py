"""Automatic encrypted backup.

Design (per the agreed spec): a full snapshot of the local database is
encrypted and written into a folder that Google Drive for Desktop is
watching under the clinic's own Google account. Google's own client
uploads it whenever the internet happens to be available — this script
never talks to Google's servers itself. The encryption key rides along in
the same folder for convenience, as decided: signing into the clinic's
Google account is, on its own, enough to recover everything later.

Kept deliberately simple: one function, no external scheduler, no
verification step beyond "did the file get written" — called
periodically by a background thread in app.py so nothing extra needs to
be installed or configured on the server machine.
"""
import json
import shutil
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path

from cryptography.fernet import Fernet

from db import DB_PATH, INSTANCE_DIR, get_setting

KEY_PATH = INSTANCE_DIR / "backup_key.key"
STATUS_PATH = INSTANCE_DIR / "backup_status.json"
KEEP_LAST_N = 7


def _get_backup_folder() -> Path:
    """Where Google Drive for Desktop is watching. Configured by Admin during
    setup (see routes/admin.py); falls back to a local folder so the app
    still runs sensibly if it hasn't been configured yet."""
    configured = get_setting("backup_folder_path")
    folder = Path(configured) if configured else (INSTANCE_DIR / "backup_pending")
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _get_or_create_key() -> bytes:
    if KEY_PATH.exists():
        return KEY_PATH.read_bytes()
    key = Fernet.generate_key()
    KEY_PATH.write_bytes(key)
    return key


def _write_status(success, snapshot_filename=None, error=None):
    STATUS_PATH.write_text(json.dumps({
        "ran_at": datetime.now().isoformat(timespec="seconds"),
        "success": success,
        "snapshot_filename": snapshot_filename,
        "error": error,
    }))


def _snapshot_db_to(tmp_path: Path):
    """Uses SQLite's own backup API rather than a raw file copy, so a
    snapshot is safe to take even while the app is live and writing."""
    src = sqlite3.connect(DB_PATH)
    dst = sqlite3.connect(tmp_path)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()


def run_backup():
    try:
        folder = _get_backup_folder()
        key = _get_or_create_key()
        fernet = Fernet(key)

        # Keep a copy of the key in the same folder — convenience over a
        # separate physical key, per the agreed trade-off. Two-factor
        # authentication on the Google account is what protects this.
        (folder / "clinic_recovery_key.key").write_bytes(key)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_db = Path(tmp) / "snapshot.db"
            _snapshot_db_to(tmp_db)
            encrypted = fernet.encrypt(tmp_db.read_bytes())

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"clinic_backup_{timestamp}.enc"
        (folder / filename).write_bytes(encrypted)

        # Logo rides along too, so a restore brings the letterhead back, not
        # just patient data.
        logo_dir = Path(__file__).resolve().parent / "static" / "uploads"
        if logo_dir.exists():
            for logo_file in logo_dir.glob("clinic_logo.*"):
                shutil.copy2(logo_file, folder / f"clinic_logo_backup{logo_file.suffix}")

        _prune_old_backups(folder)
        _write_status(True, snapshot_filename=filename)
        return True
    except Exception as e:  # noqa: BLE001 - a failed backup should never crash the app
        _write_status(False, error=str(e))
        return False


def _prune_old_backups(folder: Path):
    backups = sorted(folder.glob("clinic_backup_*.enc"), key=lambda p: p.name, reverse=True)
    for old in backups[KEEP_LAST_N:]:
        old.unlink(missing_ok=True)


if __name__ == "__main__":
    ok = run_backup()
    print("Backup succeeded" if ok else "Backup failed — see instance/backup_status.json")
