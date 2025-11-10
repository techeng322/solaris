"""
REVIT model importer.
Supports import via IFC export or direct REVIT file processing.
"""

from typing import List, Dict, Optional
import os

from .base_importer import BaseImporter
from .ifc_importer import IFCImporter
from models.building import Building, Window


class RevitImporter(BaseImporter):
    """
    Importer for REVIT models.
    Can work with IFC exports from REVIT or direct REVIT files.
    """
    
    def __init__(self, file_path: str):
        super().__init__(file_path)
        self.file_extension = os.path.splitext(file_path)[1].lower()
    
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
            # Direct REVIT file - requires special handling
            return self._import_rvt_direct()
        else:
            raise ValueError(f"Unsupported file format: {self.file_extension}")
    
    def _import_rvt_direct(self) -> List[Building]:
        """
        Import REVIT file directly.
        Note: Direct RVT import requires REVIT API or third-party libraries.
        For now, this is a placeholder that would need REVIT API integration.
        
        Returns:
            List of Building objects
        """
        # TODO: Implement direct REVIT import
        # This would require:
        # 1. REVIT API access (Autodesk.Revit.dll)
        # 2. Or use of third-party libraries like pyrevit
        # 3. Or conversion to IFC first
        
        raise NotImplementedError(
            "Direct REVIT import requires REVIT API. "
            "Please export REVIT model to IFC format first."
        )
    
    def extract_windows(self) -> List[Window]:
        """
        Extract all windows from REVIT model.
        Uses IFC importer if file is IFC format.
        """
        if self.file_extension == '.ifc':
            ifc_importer = IFCImporter(self.file_path)
            return ifc_importer.extract_windows()
        else:
            # Direct REVIT import - not implemented yet
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
        
        # TODO: Extract from REVIT element parameters
        # REVIT elements have Parameters property that can be queried
        
        return props

