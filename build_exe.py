"""
Build script for creating Solaris executable using PyInstaller.

This script creates a Windows executable (.exe) from the Solaris application.

Usage:
    python build_exe.py
"""

import PyInstaller.__main__
import os
import sys
from pathlib import Path

# Get the project root directory
project_root = Path(__file__).parent.absolute()

# PyInstaller options
options = [
    'run_gui.py',  # Main script
    '--name=Solaris',  # Name of the executable
    '--onefile',  # Create a single executable file
    '--windowed',  # No console window (GUI application)
    '--clean',  # Clean PyInstaller cache before building
    '--noconfirm',  # Overwrite output directory without asking
    
    # Include data files
    '--add-data', f'{project_root}/config.yaml;.',  # Include config.yaml in root
    '--add-data', f'{project_root}/ui/translations.py;ui',  # Include translations
    '--add-data', f'{project_root}/ui/styles.py;ui',  # Include styles
    
    # Hidden imports (packages that PyInstaller might miss)
    '--hidden-import=PyQt6.QtCore',
    '--hidden-import=PyQt6.QtGui',
    '--hidden-import=PyQt6.QtWidgets',
    '--hidden-import=PyQt6.QtOpenGL',
    '--hidden-import=PyQt6.QtOpenGLWidgets',
    '--hidden-import=numpy',
    '--hidden-import=scipy',
    '--hidden-import=matplotlib',
    '--hidden-import=matplotlib.backends.backend_qt5agg',
    '--hidden-import=reportlab',
    '--hidden-import=ifcopenshell',
    '--hidden-import=trimesh',
    '--hidden-import=shapely',
    '--hidden-import=astral',
    '--hidden-import=pytz',
    '--hidden-import=yaml',
    '--hidden-import=docx',
    '--hidden-import=PIL',
    '--hidden-import=pygltflib',
    
    # Include local modules explicitly
    '--hidden-import=workflow',  # Our local workflow.py module
    '--hidden-import=core',
    '--hidden-import=core.insolation_calculator',
    '--hidden-import=core.keo_calculator',
    '--hidden-import=core.sun_position',
    '--hidden-import=core.loggia_handler',
    '--hidden-import=models',
    '--hidden-import=models.building',
    '--hidden-import=models.calculation_result',
    '--hidden-import=importers',
    '--hidden-import=importers.ifc_importer',
    '--hidden-import=importers.glb_importer',
    '--hidden-import=importers.revit_importer',
    '--hidden-import=importers.bim_validator',
    '--hidden-import=reports',
    '--hidden-import=reports.report_generator',
    '--hidden-import=reports.diagram_generator',
    '--hidden-import=ui',
    '--hidden-import=ui.main_window',
    '--hidden-import=ui.translations',
    '--hidden-import=ui.styles',
    '--hidden-import=utils',
    '--hidden-import=utils.config_loader',
    '--hidden-import=utils.geometry_utils',
    
    # Exclude unnecessary packages to reduce size
    '--exclude-module=tkinter',
    '--exclude-module=matplotlib.tests',
    '--exclude-module=numpy.tests',
    '--exclude-module=scipy.tests',
    
    # Icon (if you have one)
    # '--icon=icon.ico',
    
    # Output directory
    '--distpath', str(project_root / 'dist'),
    '--workpath', str(project_root / 'build'),
    '--specpath', str(project_root),
]

print("Building Solaris executable...")
print(f"Project root: {project_root}")
print(f"Python: {sys.executable}")
print(f"Python version: {sys.version}")
print("\nStarting PyInstaller...\n")

# Use spec file instead of command line (better control over hooks)
print("\nUsing spec file for better hook control...")
spec_file = project_root / 'Solaris.spec'

try:
    # Build using spec file
    PyInstaller.__main__.run([
        str(spec_file),
        '--clean',
        '--noconfirm',
    ])
    print("\n✅ Build completed successfully!")
    print(f"Executable location: {project_root / 'dist' / 'Solaris.exe'}")
except Exception as e:
    print(f"\n❌ Build failed with error: {e}")
    print("\nTrying alternative build method...")
    # Fallback: try direct command line build
    try:
        PyInstaller.__main__.run(options)
        print("\n✅ Build completed successfully!")
        print(f"Executable location: {project_root / 'dist' / 'Solaris.exe'}")
    except Exception as e2:
        print(f"\n❌ Alternative build also failed: {e2}")
        sys.exit(1)

