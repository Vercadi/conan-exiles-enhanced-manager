# -*- mode: python ; coding: utf-8 -*-
"""One-file PyInstaller spec for Nexus Mods upload packaging."""
from __future__ import annotations

import os
from pathlib import Path

import customtkinter
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

ctk_path = os.path.dirname(customtkinter.__file__)
asset_datas = []
if Path("assets").is_dir():
    asset_datas.append(("assets", "assets"))
dnd_datas = []
try:
    dnd_datas = collect_data_files("tkinterdnd2")
except Exception:
    dnd_datas = []

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=[],
    datas=[(ctk_path, "customtkinter")] + asset_datas + dnd_datas,
    hiddenimports=["customtkinter", "tkinterdnd2", "tkinterdnd2.TkinterDnD"],
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="Conan Exiles Enhanced Manager",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/app_icon.ico",
)
