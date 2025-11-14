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
        Import REVIT file directly using headless REVIT API.
        Works without REVIT UI - uses REVIT API DLLs directly via Python.NET.
        
        Returns:
            List of Building objects
        """
        try:
            from .revit_headless import RevitHeadlessExtractor
            
            # Use headless extractor
            with RevitHeadlessExtractor(self.file_path) as extractor:
                building = extractor.extract_building()
                return [building]
                
        except NotImplementedError as e:
            # REVIT API not available - provide helpful error message
            raise NotImplementedError(
                f"{str(e)}\n\n"
                "Alternative: Export REVIT model to IFC format and import IFC file instead."
            )
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error importing REVIT file directly: {e}", exc_info=True)
            raise RuntimeError(
                f"Failed to import REVIT file: {str(e)}\n\n"
                "Please ensure:\n"
                "1. REVIT is installed (required for API DLLs)\n"
                "2. Python.NET is installed: pip install pythonnet\n"
                "3. File is a valid .rvt file\n\n"
                "Alternative: Export REVIT model to IFC format and import IFC file."
            )
    
    def extract_windows(self) -> List[Window]:
        """
        Extract all windows from REVIT model.
        Uses IFC importer if file is IFC format.
        Uses headless REVIT extractor if file is .rvt format.
        """
        if self.file_extension == '.ifc':
            ifc_importer = IFCImporter(self.file_path)
            return ifc_importer.extract_windows()
        elif self.file_extension == '.rvt':
            try:
                from .revit_headless import RevitHeadlessExtractor
                with RevitHeadlessExtractor(self.file_path) as extractor:
                    return extractor.extract_windows()
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Error extracting windows from REVIT: {e}")
                return []
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
        
        # TODO: Extract from REVIT element parameters
        # REVIT elements have Parameters property that can be queried
        
        return props

