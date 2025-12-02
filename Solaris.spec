# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['run_gui.py'],
    pathex=[],
    binaries=[],
    datas=[('D:\\Github\\goTech007\\solaris/config.yaml', '.'), ('D:\\Github\\goTech007\\solaris/ui/translations.py', 'ui'), ('D:\\Github\\goTech007\\solaris/ui/styles.py', 'ui')],
    hiddenimports=['PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets', 'PyQt6.QtOpenGL', 'PyQt6.QtOpenGLWidgets', 'numpy', 'scipy', 'matplotlib', 'matplotlib.backends.backend_qt5agg', 'reportlab', 'ifcopenshell', 'trimesh', 'shapely', 'astral', 'pytz', 'yaml', 'docx', 'PIL', 'pygltflib', 'workflow', 'core', 'core.insolation_calculator', 'core.keo_calculator', 'core.sun_position', 'core.loggia_handler', 'models', 'models.building', 'models.calculation_result', 'importers', 'importers.ifc_importer', 'importers.glb_importer', 'importers.revit_importer', 'importers.bim_validator', 'reports', 'reports.report_generator', 'reports.diagram_generator', 'ui', 'ui.main_window', 'ui.translations', 'ui.styles', 'utils', 'utils.config_loader', 'utils.geometry_utils'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib.tests', 'numpy.tests', 'scipy.tests'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Solaris',
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
