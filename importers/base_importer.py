"""
Base importer class for BIM models.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from models.building import Building, Window


class BaseImporter(ABC):
    """Base class for all BIM model importers."""
    
    def __init__(self, file_path: str):
        """
        Initialize importer.
        
        Args:
            file_path: Path to BIM model file
        """
        self.file_path = file_path
        self.buildings: List[Building] = []
    
    @abstractmethod
    def import_model(self) -> List[Building]:
        """
        Import building model from file.
        
        Returns:
            List of Building objects
        """
        pass
    
    @abstractmethod
    def extract_windows(self) -> List[Window]:
        """
        Extract windows from model.
        
        Returns:
            List of Window objects
        """
        pass
    
    def recognize_window_type(self, window_element) -> Dict:
        """
        Recognize window type and properties from BIM element.
        
        Args:
            window_element: Window element from BIM model
        
        Returns:
            Dictionary with window properties (type, transmittance, etc.)
        """
        # Default implementation - to be overridden by specific importers
        return {
            'window_type': 'unknown',
            'glass_thickness': 4.0,
            'transmittance': 0.75,
            'frame_factor': 0.70
        }
    

