"""
Quick test script to verify installation and basic functionality.
Run this to check if all dependencies are installed correctly.
"""

import sys

def test_imports():
    """Test if all required modules can be imported."""
    print("Testing imports...")
    
    errors = []
    check = "[OK]"
    cross = "[FAIL]"
    
    # Core Python modules
    try:
        import yaml
        print(f"{check} yaml")
    except ImportError as e:
        errors.append(f"{cross} yaml: {e}")
        print(f"{cross} yaml")
    
    # Scientific computing
    try:
        import numpy
        print(f"{check} numpy")
    except ImportError as e:
        errors.append(f"{cross} numpy: {e}")
        print(f"{cross} numpy")
    
    try:
        import scipy
        print(f"{check} scipy")
    except ImportError as e:
        errors.append(f"{cross} scipy: {e}")
        print(f"{cross} scipy")
    
    try:
        import pandas
        print(f"{check} pandas")
    except ImportError as e:
        errors.append(f"{cross} pandas: {e}")
        print(f"{cross} pandas")
    
    # 3D geometry
    try:
        import shapely
        print(f"{check} shapely")
    except ImportError as e:
        errors.append(f"{cross} shapely: {e}")
        print(f"{cross} shapely")
    
    try:
        import trimesh
        print(f"{check} trimesh")
    except ImportError as e:
        errors.append(f"{cross} trimesh: {e}")
        print(f"{cross} trimesh")
    
    try:
        import pyproj
        print(f"{check} pyproj")
    except ImportError as e:
        errors.append(f"{cross} pyproj: {e}")
        print(f"{cross} pyproj")
    
    # GUI
    try:
        import PyQt6
        print(f"{check} PyQt6")
    except ImportError as e:
        errors.append(f"{cross} PyQt6: {e}")
        print(f"{cross} PyQt6")
        print("  Note: GUI will not work without PyQt6")
    
    # Report generation
    try:
        import matplotlib
        print(f"{check} matplotlib")
    except ImportError as e:
        errors.append(f"{cross} matplotlib: {e}")
        print(f"{cross} matplotlib")
    
    try:
        import reportlab
        print(f"{check} reportlab")
    except ImportError as e:
        errors.append(f"{cross} reportlab: {e}")
        print(f"{cross} reportlab")
    
    try:
        from PIL import Image
        print(f"{check} pillow")
    except ImportError as e:
        errors.append(f"{cross} pillow: {e}")
        print(f"{cross} pillow")
    
    # BIM support
    try:
        import ifcopenshell
        print(f"{check} ifcopenshell")
    except ImportError as e:
        errors.append(f"{cross} ifcopenshell: {e}")
        print(f"{cross} ifcopenshell")
        print("  Note: IFC import will not work without ifcopenshell")
    
    # Date/time
    try:
        import astral
        print(f"{check} astral")
    except ImportError as e:
        errors.append(f"{cross} astral: {e}")
        print(f"{cross} astral")
    
    try:
        import pytz
        print(f"{check} pytz")
    except ImportError as e:
        errors.append(f"{cross} pytz: {e}")
        print(f"{cross} pytz")
    
    # Project modules
    print("\nTesting project modules...")
    try:
        from core import InsolationCalculator, KEOCalculator
        print(f"{check} core modules")
    except ImportError as e:
        errors.append(f"{cross} core modules: {e}")
        print(f"{cross} core modules")
    
    try:
        from models import Building, Room, Window
        print(f"{check} models")
    except ImportError as e:
        errors.append(f"{cross} models: {e}")
        print(f"{cross} models")
    
    try:
        from importers import IFCImporter
        print(f"{check} importers")
    except ImportError as e:
        errors.append(f"{cross} importers: {e}")
        print(f"{cross} importers")
    
    try:
        from reports import ReportGenerator
        print(f"{check} reports")
    except ImportError as e:
        errors.append(f"{cross} reports: {e}")
        print(f"{cross} reports")
    
    return errors


def test_basic_functionality():
    """Test basic calculation functionality."""
    print("\nTesting basic functionality...")
    
    try:
        from core.sun_position import SunPositionCalculator
        from datetime import datetime
        
        calc = SunPositionCalculator(55.7558, 37.6173)  # Moscow
        dt = datetime(2024, 6, 21, 12, 0, 0)
        azimuth, elevation = calc.get_sun_position(dt)
        
        print(f"[OK] Sun position calculation: azimuth={azimuth:.1f}deg, elevation={elevation:.1f}deg")
        return True
    except Exception as e:
        print(f"[FAIL] Sun position calculation failed: {e}")
        return False


def main():
    """Run all tests."""
    print("=" * 50)
    print("Solaris Installation Test")
    print("=" * 50)
    print(f"Python version: {sys.version}")
    print()
    
    # Test imports
    errors = test_imports()
    
    # Test basic functionality
    func_ok = test_basic_functionality()
    
    # Summary
    print("\n" + "=" * 50)
    print("Test Summary")
    print("=" * 50)
    
    if errors:
        print(f"\n[WARNING] Found {len(errors)} import error(s):")
        for error in errors:
            print(f"  {error}")
        print("\nTo fix, run: pip install -r requirements.txt")
    else:
        print("\n[OK] All imports successful!")
    
    if func_ok:
        print("[OK] Basic functionality test passed!")
    else:
        print("[WARNING] Basic functionality test failed")
    
    if not errors and func_ok:
        print("\n[SUCCESS] Installation is complete and working!")
        print("\nYou can now run the application:")
        print("  python run_gui.py")
    else:
        print("\n[WARNING] Please fix the errors above before using the application")
    
    print("=" * 50)


if __name__ == '__main__':
    main()

