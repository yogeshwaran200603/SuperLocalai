# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller specification for SuperLocal Desktop Windows Application.
Produces a clean one-folder distribution in dist/SuperLocal.
"""

from pathlib import Path
import os

block_cipher = None

datas = [
    ('assets', 'assets'),
    ('shortcuts.json', '.'),
]

if os.path.exists('skills'):
    datas.append(('skills', 'skills'))

if os.path.exists('autopilot/recipes'):
    datas.append(('autopilot/recipes', 'autopilot/recipes'))

hiddenimports = [
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
    'keyring',
    'keyring.backends.Windows',
    'psutil',
    'rich',
    'dotenv',
    'sounddevice',
    'core',
    'core.engine',
    'core.events',
    'superlocal',
    'superlocal.core.credentials',
    'superlocal.ui.theme',
    'superlocal.ui.main_window',
    'superlocal.ui.pages.chat_page',
    'superlocal.ui.pages.tasks_page',
    'superlocal.ui.pages.voice_page',
    'superlocal.ui.pages.games_page',
    'superlocal.ui.pages.optimizer_page',
    'superlocal.ui.pages.skills_page',
    'superlocal.ui.pages.history_page',
    'superlocal.ui.pages.settings_page',
    'superlocal.ui.pages.wizard',
    'tools',
    'providers',
    'voice',
    'autopilot',
    'optimizer',
    'poki',
    'openfront',
]

a = Analysis(
    ['superlocal/gui.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'webrtcvad'],
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
    name='SuperLocal',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='SuperLocal',
)
