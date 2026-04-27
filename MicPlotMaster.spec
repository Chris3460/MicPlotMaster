# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules

hiddenimports = (
    collect_submodules('ui_desktop') +
    collect_submodules('core') +
    collect_submodules('exports') +
    collect_submodules('imports') +
    collect_submodules('utils')
)

a = Analysis(
    ['app.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('icon.png', '.'),
        ('icon.ico', '.'),
        ('Help', 'Help'),
        ('Demo CSVs', 'Demo CSVs'),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='MicPlotMaster',
    debug=False,
    strip=False,
    upx=True,
    console=False,
    icon='icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name='MicPlotMaster',
)