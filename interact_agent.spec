# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path

# Resolve base path
block_cipher = None

# We want to bundle agent.cfg next to the executable if not present.
# In the spec, we can copy agent.cfg into the build folder or datas, 
# but load_config() resolves CONFIG_FILE_PATH relative to sys.executable's dir (or __file__'s parent).
# We add it to datas to bundle it inside _MEIPASS or write a post-build instruction.
# To ensure it's copied next to the EXE during packaging, the release checklist will document it,
# or we can specify it as a datafile. Let's include agent.cfg in datas so it is always present inside the bundle if needed,
# and also provide it next to the EXE.
datas = [
    ('agent.cfg', '.'),
    ('agent_version.py', '.'),
]

hidden_imports = [
    'pynput.keyboard._win32',
    'pynput.mouse._win32',
    'websockets.legacy',
    'websockets.legacy.server',
    'websockets.legacy.client',
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
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
    name='InterActAgent',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
