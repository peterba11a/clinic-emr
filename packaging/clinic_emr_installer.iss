; Inno Setup script for Clinic EMR
;
; Produces a single ClinicEMR-Setup.exe that a clinic can double-click and
; click "Next" through, with no other software to install first. It:
;   1. Copies the built ClinicEMR app (from PyInstaller's dist\ClinicEMR
;      folder) into Program Files.
;   2. Puts a shortcut to the watchdog launcher in the Windows Startup
;      folder, so the server starts automatically every time the computer
;      turns on (and restarts itself if it ever crashes).
;   3. Optionally starts the app immediately after installation finishes.
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
; Optional one-time fix for clinicserver.local not resolving on some
; networks — see that script's own comments. Not run automatically.
Name: "{group}\Make this computer's address permanent (optional)"; Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\packaging\make_ip_static.ps1"""; WorkingDir: "{app}\packaging"
Name: "{group}\Uninstall Clinic EMR"; Filename: "{uninstallexe}"
; This is the important one: a shortcut in the current user's Startup
; folder pointing at the watchdog, not the exe directly, so the app both
; launches on boot and auto-restarts if it ever crashes while the PC is on.
Name: "{userstartup}\Clinic EMR (auto-start)"; Filename: "wscript.exe"; Parameters: """{app}\watchdog.vbs"""; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"

[Run]
; Kick off the watchdog (not the exe directly) right after install if the
; clinic ticked "start now", so the very first run behaves identically to
; every boot afterwards.
Filename: "wscript.exe"; Parameters: """{app}\watchdog.vbs"""; WorkingDir: "{app}"; Flags: nowait skipifsilent; Tasks: startnow

[UninstallDelete]
; Remove the auto-start shortcut on uninstall. The clinic's data
; (instance\clinic.db) is deliberately left untouched — uninstalling the
; program must never delete patient records.
Type: files; Name: "{userstartup}\Clinic EMR (auto-start).lnk"
