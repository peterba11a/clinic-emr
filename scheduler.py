"""Runs the backup on a simple timer inside the app's own process —
deliberately not a separate Windows Scheduled Task, since the app is
already running continuously (started by the Windows Startup shortcut),
and a plain background thread is one less moving part to install or
misconfigure."""
import threading
import time

from backup import run_backup

BACKUP_INTERVAL_SECONDS = 24 * 60 * 60  # nightly
STARTUP_DELAY_SECONDS = 60  # give the app a minute to finish starting first


def _loop():
    time.sleep(STARTUP_DELAY_SECONDS)
    while True:
        run_backup()
        time.sleep(BACKUP_INTERVAL_SECONDS)


def start_backup_scheduler():
    thread = threading.Thread(target=_loop, daemon=True)
    thread.start()
    return thread
