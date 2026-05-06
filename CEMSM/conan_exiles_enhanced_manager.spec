# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Conan Exiles Enhanced Manager."""
from __future__ import annotations

import os
from pathlib import Path

import customtkinter

block_cipher = None

ctk_path = os.path.dirname(customtkinter.__file__)
asset_datas = []
if Path("assets").is_dir():
    asset_datas.append(("assets", "assets"))

# Runtime folders are intentionally not included in datas:
# data/, backups/, logs/, steamcmd/, tmp/, and docs/.

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=[],
    datas=[(ctk_path, "customtkinter")] + asset_datas,
    hiddenimports=["customtkinter"],
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
    name="Conan Exiles Enhanced Manager",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Conan Exiles Enhanced Manager",
)
