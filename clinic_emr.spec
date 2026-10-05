# PyInstaller build spec for the Clinic EMR server.
#
# This produces ONE Windows executable (ClinicEMR.exe) that contains the
# whole Python app and all its dependencies, so the clinic never has to
# install Python. It must be built ON WINDOWS (PyInstaller does not
# cross-compile) with a normal Windows machine or laptop, using the
# instructions in packaging/README.md.
#
# Build with:
#     pyinstaller clinic_emr.spec
#
# The finished exe appears in dist\ClinicEMR\ClinicEMR.exe

import sys
from pathlib import Path

block_cipher = None
project_dir = Path(SPECPATH)

a = Analysis(
    ["app.py"],
    pathex=[str(project_dir)],
    binaries=[],
    datas=[
        (str(project_dir / "templates"), "templates"),
        (str(project_dir / "static"), "static"),
        (str(project_dir / "schema.sql"), "."),
        (str(project_dir / "icd10_codes.tsv"), "."),
        (str(project_dir / "packaging" / "make_ip_static.ps1"), "packaging"),
    ],
    hiddenimports=[
        "zeroconf",
        "zeroconf._utils.ipaddress",
        "zeroconf._handlers.answers",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ClinicEMR",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ClinicEMR",
    # PyInstaller 6.0+ defaults to tucking bundled files into a
    # "_internal" subfolder next to the exe. This app's code (db.py's
    # BASE_DIR, used to find schema.sql/templates/static and to decide
    # where to keep the live database) expects the older flat layout —
    # everything directly beside ClinicEMR.exe — so pin that behavior
    # here rather than relying on whatever PyInstaller version happens
    # to be installed on the build machine.
    contents_directory=".",
)
