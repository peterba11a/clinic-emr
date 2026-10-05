; Inno Setup script for Clinic EMR
;
; Produces a single ClinicEMR-Setup.exe that a clinic can double-click and
; click "Next" through, with no other software to install first. It:
;   1. Copies the built ClinicEMR app (from PyInstaller's dist\ClinicEMR
;      folder) into Program Files.
;   2. Puts a shortcut to the watchdog launcher in the Windows Startup
;      folder, so the server starts automatically every time the computer
;      turns on (and restarts itself if it ever crashes).
;   3. Pins this computer's current network address so it never changes
;      after a reboot (recommended, ticked by default) — this is what lets
;      other devices in the clinic reach it reliably without anyone
;      reconfiguring anything later, and it's the main reason this is
;      handled at install time rather than left as a thing Admin has to
;      remember to do. It needs administrator rights (changing network
;      settings always does), so it triggers its own one-time Windows
;      permission prompt, separate from — and regardless of — this
;      installer, which deliberately never requires admin rights itself.
;   4. Optionally starts the app immediately after installation finishes.
;
; This script must be compiled ON WINDOWS using Inno Setup
; (https://jrsoftware.org/isinfo.php, free) — see packaging/README.md for
; the full build walkthrough. It cannot be compiled in a Linux environment.

#define MyAppName "Clinic EMR"
#define MyAppVersion "1.0"
#define MyAppPublisher "Clinic EMR"
#define MyAppExeName "ClinicEMR.exe"

[Setup]
AppId={{6F5B6E6E-2C1B-4B7A-9C3D-CLINICEMR001}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\ClinicEMR
DefaultGroupName=Clinic EMR
DisableProgramGroupPage=yes
; No admin rights required to install into the user's own Program Files
; area — keeps setup to a single click with no UAC prompt on most machines.
PrivilegesRequired=lowest
OutputBaseFilename=ClinicEMR-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
; Ticked by default — this is what makes the clinic's other devices able to
; reach this computer reliably without anyone needing to redo anything
; later. See the [Run] section below for why it's safe to leave on.
Name: "setstaticip"; Description: "Make this computer's network address permanent (recommended)"; GroupDescription: "After installation:"; Flags: checked
Name: "startnow"; Description: "Start Clinic EMR now"; GroupDescription: "After installation:"; Flags: unchecked

[Files]
; Everything PyInstaller collected into dist\ClinicEMR (the exe plus its
; bundled Python runtime, templates, and static files — this already
; includes packaging\make_ip_static.ps1, bundled via clinic_emr.spec).
Source: "..\dist\ClinicEMR\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; The watchdog script that keeps the server running.
Source: "watchdog.vbs"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Clinic EMR"; Filename: "{app}\{#MyAppExeName}"
; This normally already ran once automatically during setup (see [Run]
; below). This shortcut is for redoing it later — e.g. the checkbox was
; unticked during install, or the server moved to a different network.
Name: "{group}\Make this computer's address permanent (redo)"; Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\packaging\make_ip_static.ps1"""; WorkingDir: "{app}\packaging"
Name: "{group}\Uninstall Clinic EMR"; Filename: "{uninstallexe}"
; This is the important one: a shortcut in the current user's Startup
; folder pointing at the watchdog, not the exe directly, so the app both
; launches on boot and auto-restarts if it ever crashes while the PC is on.
Name: "{userstartup}\Clinic EMR (auto-start)"; Filename: "wscript.exe"; Parameters: """{app}\watchdog.vbs"""; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"

[Run]
; Pin this computer's current network address so it never changes after a
; reboot (ticked by default above). The script is idempotent (safe if run
; more than once) and self-elevating — it requests its own administrator
; prompt the moment it starts, independent of this installer, which stays
; at PrivilegesRequired=lowest so the rest of setup needs no UAC prompt at
; all. Runs before "start now" below so the address is already fixed by
; the time the app opens for the first time.
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\packaging\make_ip_static.ps1"""; WorkingDir: "{app}\packaging"; Flags: skipifsilent; Tasks: setstaticip
; Kick off the watchdog (not the exe directly) right after install if the
; clinic ticked "start now", so the very first run behaves identically to
; every boot afterwards.
Filename: "wscript.exe"; Parameters: """{app}\watchdog.vbs"""; WorkingDir: "{app}"; Flags: nowait skipifsilent; Tasks: startnow

[UninstallDelete]
; Remove the auto-start shortcut on uninstall. The clinic's data
; (instance\clinic.db) is deliberately left untouched — uninstalling the
; program must never delete patient records.
Type: files; Name: "{userstartup}\Clinic EMR (auto-start).lnk"
