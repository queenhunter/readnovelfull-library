# Portable one-folder Windows package for ReadNovelFull Library.
# PyInstaller's PySide6 hooks collect Qt plugins and Qt WebEngine runtime assets.
a = Analysis(
    ["ReadNovelFull_GUI.py"],
    pathex=[],
    binaries=[],
    datas=[("Read_Novel_Full_V2_8.py", "."), ("Novel Hall V1.0.py", ".")],
    hiddenimports=[
        # The downloader is imported dynamically from a bundled source file.
        "requests",
        "bs4",
        # Keep browser modules explicit so PyInstaller applies their standard hooks.
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtPrintSupport",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "test", "unittest"],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ReadNovelFull",
    icon="ReadNovelFull_Icon.ico",
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
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ReadNovelFull",
)
