"""
REVIT model importer.
Supports import via IFC export or direct REVIT file processing using REVIT API.
"""

from typing import List, Dict, Optional, Tuple
import os
import logging
from pathlib import Path

from .base_importer import BaseImporter
from .ifc_importer import IFCImporter
from models.building import Building, Window

logger = logging.getLogger(__name__)

# Try to import pythonnet for REVIT API access
try:
    import clr
    PYTHONNET_AVAILABLE = True
except ImportError:
    PYTHONNET_AVAILABLE = False
    logger.warning("pythonnet not available - REVIT API access disabled. Install with: pip install pythonnet")


class RevitImporter(BaseImporter):
    """
    Importer for REVIT models.
    Can work with IFC exports from REVIT or direct REVIT files using REVIT API.
    """
    
    def __init__(self, file_path: str):
        super().__init__(file_path)
        self.file_extension = os.path.splitext(file_path)[1].lower()
        self.revit_app = None
        self.revit_doc = None
    
    def import_model(self) -> List[Building]:
        """
        Import REVIT model.
        If file is IFC format, delegates to IFC importer.
        Otherwise, attempts direct REVIT import.
        
        Returns:
            List of Building objects
        """
        if self.file_extension == '.ifc':
            # REVIT model exported as IFC
            ifc_importer = IFCImporter(self.file_path)
            return ifc_importer.import_model()
        elif self.file_extension == '.rvt':
            # Direct REVIT file - use REVIT API
            return self._import_rvt_direct()
        else:
            raise ValueError(f"Unsupported file format: {self.file_extension}")
    
    def _import_rvt_direct(self) -> List[Building]:
        """
        Import REVIT file directly using REVIT API.
        
        RVT files are proprietary Autodesk format. This method attempts to:
        1. Use REVIT API if REVIT is installed and pythonnet is available
        2. Provide helpful error messages with conversion instructions
        
        Returns:
            List of Building objects
        """
        # Check if pythonnet is available
        if not PYTHONNET_AVAILABLE:
            raise RuntimeError(
                "REVIT (.RVT) file import requires additional setup.\n\n"
                "OPTION 1 (Recommended): Export to IFC format\n"
                "1. Open your RVT file in Autodesk REVIT\n"
                "2. Go to: File > Export > IFC\n"
                "3. Save the IFC file\n"
                "4. Import the IFC file in Solaris\n\n"
                "OPTION 2: Install pythonnet for REVIT API access\n"
                "1. Install: pip install pythonnet\n"
                "2. Ensure Autodesk REVIT is installed\n"
                "3. Note: REVIT API requires REVIT to be running\n\n"
                "For now, please export your REVIT model to IFC format."
            )
        
        # Check if REVIT is installed
        revit_api_paths = self._find_revit_api_paths()
        if not revit_api_paths:
            raise RuntimeError(
                "Autodesk REVIT is not installed or not found.\n\n"
                "REVIT (.RVT) files require Autodesk REVIT to be installed.\n\n"
                "SOLUTION: Export to IFC format\n"
                "1. Open your RVT file in Autodesk REVIT\n"
                "2. Go to: File > Export > IFC\n"
                "3. Choose IFC export settings\n"
                "4. Save the IFC file\n"
                "5. Import the IFC file in Solaris\n\n"
                "IFC format is an open standard and works perfectly with Solaris."
            )
        
        # Try to import using REVIT API
        try:
            return self._import_rvt_with_api()
        except Exception as e:
            logger.error(f"Failed to import RVT file: {e}", exc_info=True)
            
            # Provide comprehensive error message
            error_msg = (
                f"Cannot import RVT file directly: {str(e)}\n\n"
                "REVIT (.RVT) files are proprietary and require special handling.\n\n"
                "RECOMMENDED SOLUTION: Export to IFC format\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "1. Open your RVT file in Autodesk REVIT\n"
                "2. Go to: File > Export > IFC\n"
                "3. In IFC Export Options:\n"
                "   - Set 'Space Boundaries' to '2nd Level'\n"
                "   - Enable 'Export Rooms in View'\n"
                "   - Enable 'Export Base Quantities'\n"
                "4. Click OK and save the IFC file\n"
                "5. Import the IFC file in Solaris\n\n"
                "IFC format is an open standard and provides all data needed for calculations.\n"
                "Solaris fully supports IFC files with complete window and room information."
            )
            
            raise RuntimeError(error_msg) from e
    
    def _import_rvt_with_api(self) -> List[Building]:
        """
        Import RVT file using REVIT API directly.
        
        Note: REVIT API requires REVIT application to be running.
        This is a limitation of Autodesk's REVIT API architecture.
        """
        import clr
        
        # Load REVIT API assemblies
        revit_api_paths = self._find_revit_api_paths()
        for dll_path in revit_api_paths:
            if os.path.exists(dll_path):
                try:
                    clr.AddReference(dll_path)
                    logger.info(f"Loaded REVIT API: {os.path.basename(dll_path)}")
                except Exception as e:
                    logger.warning(f"Could not load {dll_path}: {e}")
        
        # Try to import REVIT API namespaces
        try:
            from Autodesk.Revit.DB import Document, FilteredElementCollector, BuiltInCategory
            from Autodesk.Revit.DB import FamilyInstance
            from Autodesk.Revit.DB import OpenOptions, DetachFromCentralOption
            from Autodesk.Revit.ApplicationServices import Application
            from Autodesk.Revit.DB import XYZ
        except ImportError as e:
            raise RuntimeError(
                f"Could not import REVIT API: {e}\n\n"
                "This usually means REVIT is not installed or the API version doesn't match.\n\n"
                "SOLUTION: Export to IFC format in REVIT and import the IFC file instead."
            )
        
        # REVIT API limitation: Requires REVIT application instance
        # We cannot open RVT files without REVIT running
        # This is a fundamental limitation of Autodesk's REVIT API
        
        raise RuntimeError(
            "REVIT API requires Autodesk REVIT application to be running.\n\n"
            "REVIT (.RVT) files are proprietary and cannot be opened without REVIT running.\n"
            "This is a limitation of Autodesk's REVIT API architecture.\n\n"
            "RECOMMENDED SOLUTION: Export to IFC format\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "1. Open your RVT file in Autodesk REVIT\n"
            "2. Go to: File > Export > IFC\n"
            "3. Configure IFC export settings:\n"
            "   - Space Boundaries: 2nd Level\n"
            "   - Export Rooms in View: Enabled\n"
            "   - Export Base Quantities: Enabled\n"
            "4. Save the IFC file\n"
            "5. Import the IFC file in Solaris\n\n"
            "IFC is an open standard and works perfectly with Solaris.\n"
            "All window and room data will be preserved in IFC format."
        )
    
    def _find_revit_api_paths(self) -> List[str]:
        """Find REVIT API DLL paths."""
        possible_paths = []
        
        # Common REVIT installation paths
        program_files = os.environ.get('ProgramFiles', 'C:\\Program Files')
        program_files_x86 = os.environ.get('ProgramFiles(x86)', 'C:\\Program Files (x86)')
        
        # Check multiple REVIT versions (2020-2025)
        for year in range(2020, 2026):
            for base_path in [program_files, program_files_x86]:
                revit_path = os.path.join(base_path, f'Autodesk\\Revit {year}')
                api_dll = os.path.join(revit_path, 'RevitAPI.dll')
                if os.path.exists(api_dll):
                    possible_paths.append(api_dll)
                    # Also add UI DLL
                    ui_dll = os.path.join(revit_path, 'RevitAPIUI.dll')
                    if os.path.exists(ui_dll):
                        possible_paths.append(ui_dll)
        
        return possible_paths
    
    def extract_windows(self) -> List[Window]:
        """
        Extract all windows from REVIT model.
        Uses IFC importer if file is IFC format.
        """
        if self.file_extension == '.ifc':
            ifc_importer = IFCImporter(self.file_path)
            return ifc_importer.extract_windows()
        elif self.file_extension == '.rvt':
            # Extract windows from RVT
            buildings = self.import_model()
            windows = []
            for building in buildings:
                windows.extend(building.windows)
            return windows
        else:
            return []
    
    def recognize_window_type(self, window_element) -> Dict:
        """
        Recognize window type from REVIT element.
        REVIT elements have specific parameter structures.
        """
        props = {
            'window_type': 'unknown',
            'glass_thickness': 4.0,
            'transmittance': 0.75,
            'frame_factor': 0.70
        }
        
        if not PYTHONNET_AVAILABLE or window_element is None:
            return props
        
        try:
            import clr
            from Autodesk.Revit.DB import FamilyInstance, Parameter
            
            # Extract window type from REVIT element
            if hasattr(window_element, 'Symbol'):
                symbol = window_element.Symbol
                if symbol and hasattr(symbol, 'FamilyName'):
                    family_name = symbol.FamilyName.lower()
                    
                    # Recognize common window types
                    if 'single' in family_name or 'однокамерный' in family_name:
                        props['window_type'] = 'single_glazed'
                        props['glass_thickness'] = 4.0
                        props['transmittance'] = 0.85
                        props['frame_factor'] = 0.75
                    elif 'double' in family_name or 'двухкамерный' in family_name:
                        props['window_type'] = 'double_glazed'
                        props['glass_thickness'] = 6.0
                        props['transmittance'] = 0.75
                        props['frame_factor'] = 0.70
                    elif 'triple' in family_name or 'трехкамерный' in family_name:
                        props['window_type'] = 'triple_glazed'
                        props['glass_thickness'] = 8.0
                        props['transmittance'] = 0.65
                        props['frame_factor'] = 0.65
            
            # Try to extract from parameters
            if hasattr(window_element, 'ParametersMap'):
                params = window_element.ParametersMap
                
                # Look for transmittance parameter
                for param_key in params.Keys:
                    param = params[param_key]
                    if param and param.HasValue:
                        param_name = param.Definition.Name.lower()
                        if 'transmittance' in param_name or 'transmission' in param_name:
                            try:
                                props['transmittance'] = float(param.AsValueString() or param.AsDouble())
                            except:
                                pass
                        elif 'frame' in param_name and 'factor' in param_name:
                            try:
                                props['frame_factor'] = float(param.AsValueString() or param.AsDouble())
                            except:
                                pass
                        elif 'glass' in param_name and 'thickness' in param_name:
                            try:
                                props['glass_thickness'] = float(param.AsValueString() or param.AsDouble())
                            except:
                                pass
        except Exception as e:
            logger.debug(f"Error extracting window properties from REVIT element: {e}")
        
        return props

