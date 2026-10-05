# Building the Windows installer

This app is plain Python + Flask, and it runs perfectly well straight from
source on any computer with Python installed (see the main `README.md`).
This folder is only needed if you want to turn it into a single
`ClinicEMR-Setup.exe` that a clinic can install with one click, with no
Python knowledge required on their end.

**Both steps below must be done on a Windows computer.** PyInstaller
builds an executable for whatever operating system you run it on, and Inno
Setup itself only runs on Windows — neither can be produced on Linux/Mac,
which is why this project ships as source plus these build scripts rather
than as a ready-made `.exe`.

## What you need on the Windows build machine

1. Python 3.10 or later (from python.org — tick "Add Python to PATH"
   during install).
2. [Inno Setup](https://jrsoftware.org/isinfo.php) (free) — only needed for
   step 3 below.

## Step 1 — Install the project's dependencies

Open Command Prompt in the `clinic-emr` folder (the one containing
`app.py`) and run:

```
pip install -r requirements.txt
```

## Step 2 — Build the executable with PyInstaller

Still in the `clinic-emr` folder:

```
pyinstaller clinic_emr.spec
```

This creates `dist\ClinicEMR\ClinicEMR.exe` along with everything it needs
alongside it in that same folder. You can test it right now by
double-clicking `dist\ClinicEMR\ClinicEMR.exe` — it should open your
browser to the login page.

## Step 3 — Build the one-click installer with Inno Setup

Open `packaging\clinic_emr_installer.iss` in Inno Setup and click
**Build → Compile** (or press Ctrl+F9). It reads the `dist\ClinicEMR`
folder from step 2 and produces:

```
packaging\Output\ClinicEMR-Setup.exe
```

That single file is what you hand to the clinic. Running it:

- Installs the app into the clinic's Program Files.
- Adds a shortcut in the Windows Startup folder pointing at
  `watchdog.vbs`, so the server starts automatically every time the
  computer turns on, and restarts itself automatically if it ever crashes
  while the computer stays on.
- Optionally launches the app immediately (there's a checkbox for this in
  the installer).

## Re-building after you change the code

Just repeat steps 2 and 3 — you don't need to reinstall dependencies again
unless `requirements.txt` changed. A clinic that already has the app
installed can simply run the new `ClinicEMR-Setup.exe` over the old
installation; their `instance\clinic.db` (all patient data) is left alone
either way.

## A note on the server device's local network name

The installer pins the server's network address automatically (a checkbox
in the installer, ticked by default, runs `make_ip_static.ps1` once right
after install) so every other device in the clinic can reach it forever at
a plain numeric address like `http://192.168.1.50:8080`, with nothing to
reconfigure later even after the server computer restarts.

The app also advertises itself as `clinicserver.local` on the clinic's
WiFi/LAN, which is a nicer name than a numeric address when it works — but
it depends on mDNS/Bonjour support that Windows generally does **not**
have out of the box (unlike macOS, iOS, Android, and modern Linux, which
resolve `.local` names natively). A Windows machine only resolves it if
Apple's Bonjour is also installed (bundled with iTunes, or installable on
its own as "Bonjour Print Services"), which a typical clinic PC won't
have. Treat `.local` as a bonus, not something to rely on — the pinned
numeric address is the one guaranteed to work everywhere with nothing
extra installed, which is exactly why the installer sets it up
automatically rather than leaving it as a manual fallback.

If the checkbox was unticked during install, or the server later moves to
a different network, `make_ip_static.ps1` (in this folder) can be re-run
any time — see the main `README.md`'s "Keeping the server's address from
changing" section and that script's own comments for what it does. It's
bundled into the built exe automatically (via `clinic_emr.spec`), installed
to the Start Menu by the Inno Setup script below as "Make this computer's
address permanent (redo)", and is also downloadable from Admin → Connect a
device inside the running app.
