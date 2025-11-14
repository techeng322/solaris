"""
Headless REVIT data extractor for standalone application.
Uses REVIT API DLLs directly without requiring REVIT UI to be running.
"""

from typing import List, Dict, Optional, Tuple
import logging
import os
import sys

logger = logging.getLogger(__name__)

# Try to import REVIT API using Python.NET
REVIT_API_AVAILABLE = False
REVIT_DLL_PATH = None

try:
    import clr  # Python.NET
    REVIT_API_AVAILABLE = True
except ImportError:
    logger.warning("Python.NET (clr) not available - install with: pip install pythonnet")
    REVIT_API_AVAILABLE = False

if REVIT_API_AVAILABLE:
    try:
        # Find REVIT installation directory
        revit_versions = ['2025', '2024', '2023', '2022', '2021', '2020', '2019']
        for version in revit_versions:
            possible_paths = [
                f"C:\\Program Files\\Autodesk\\Revit {version}\\RevitAPI.dll",
                f"C:\\Program Files (x86)\\Autodesk\\Revit {version}\\RevitAPI.dll",
            ]
            for path in possible_paths:
                if os.path.exists(path):
                    REVIT_DLL_PATH = path
                    clr.AddReference(path)
                    logger.info(f"Found REVIT API: {path}")
                    break
            if REVIT_DLL_PATH:
                break
        
        if REVIT_DLL_PATH:
            from Autodesk.Revit import DB
            from Autodesk.Revit.DB import (
                Document, Application, FilteredElementCollector,
                BuiltInCategory, BuiltInParameter, SpatialElement,
                FamilyInstance, Element, Transaction, OpenOptions
            )
            REVIT_API_AVAILABLE = True
            logger.info("REVIT API loaded successfully")
        else:
            REVIT_API_AVAILABLE = False
            logger.warning("REVIT API DLL not found - REVIT may not be installed")
    except Exception as e:
        REVIT_API_AVAILABLE = False
        logger.warning(f"Could not load REVIT API: {e}")


if REVIT_API_AVAILABLE:
    from models.building import Building, Window
    
    class RevitHeadlessExtractor:
        """
        Extract building data from REVIT files without REVIT UI.
        Uses REVIT API DLLs directly via Python.NET.
        """
        
        def __init__(self, rvt_file_path: str):
            """
            Initialize headless REVIT extractor.
            
            Args:
                rvt_file_path: Path to .rvt file
            """
            self.rvt_file_path = rvt_file_path
            self.doc = None
            self.app = None
        
        def open_document(self) -> bool:
            """
            Open REVIT document in headless mode.
            
            Returns:
                True if document opened successfully
            """
            try:
                # Create REVIT application (headless)
                self.app = Application()
                
                # Open document with OpenOptions
                open_options = OpenOptions()
                open_options.DetachFromCentralOption = DB.DetachFromCentralOption.DetachAndPreserveWorksets
                
                # Open document
                model_path = DB.ModelPathUtils.ConvertUserVisiblePathToModelPath(self.rvt_file_path)
                self.doc = self.app.OpenDocumentFile(model_path, open_options)
                
                if self.doc:
                    logger.info(f"Opened REVIT document: {self.rvt_file_path}")
                    return True
                else:
                    logger.error("Failed to open REVIT document")
                    return False
                    
            except Exception as e:
                logger.error(f"Error opening REVIT document: {e}", exc_info=True)
                return False
        
        def close_document(self):
            """Close REVIT document."""
            try:
                if self.doc:
                    self.doc.Close(False)  # Don't save changes
                    self.doc = None
                    logger.info("Closed REVIT document")
            except Exception as e:
                logger.warning(f"Error closing REVIT document: {e}")
        
        def extract_building(self) -> Building:
            """
            Extract building from REVIT document.
            
            Returns:
                Building object with windows
            """
            if not self.doc:
                if not self.open_document():
                    raise RuntimeError("Could not open REVIT document")
            
            try:
                logger.info("Extracting building from REVIT document...")
                
                # Get project information
                project_info = self.doc.ProjectInformation
                building_name = project_info.Name if project_info else "Building 1"
                building_id = project_info.Number if project_info else "Building_1"
                
                # Get location
                location = self._extract_location()
                
                # Create building
                building = Building(
                    id=building_id,
                    name=building_name,
                    location=location
                )
                
                # Extract windows
                windows = self.extract_windows()
                for window in windows:
                    building.add_window(window)
                
                logger.info(f"Extracted building: {building.name} with {len(windows)} windows")
                return building
                
            except Exception as e:
                logger.error(f"Error extracting building: {e}", exc_info=True)
                raise
        
        def extract_windows(self) -> List[Window]:
            """
            Extract all windows from REVIT document.
            
            Returns:
                List of Window objects
            """
            if not self.doc:
                if not self.open_document():
                    return []
            
            logger.info("Extracting windows from REVIT document...")
            windows = []
            
            try:
                # Get all window family instances
                collector = FilteredElementCollector(self.doc)
                window_elements = collector.OfCategory(BuiltInCategory.OST_Windows)\
                    .WhereElementIsNotElementType()\
                    .ToElements()
                
                logger.info(f"Found {len(list(window_elements))} window element(s) in REVIT")
                
                for window_elem in window_elements:
                    try:
                        window = self._extract_window_from_element(window_elem)
                        if window:
                            windows.append(window)
                            logger.debug(f"Extracted window: {window.id}")
                    except Exception as e:
                        logger.warning(f"Error extracting window {window_elem.Id}: {e}")
                
                logger.info(f"Successfully extracted {len(windows)} window(s)")
                return windows
                
            except Exception as e:
                logger.error(f"Error extracting windows: {e}", exc_info=True)
                return []
        
        def _extract_window_from_element(self, window_elem: FamilyInstance) -> Optional[Window]:
            """Extract window properties from REVIT FamilyInstance element."""
            try:
                # Get window ID
                window_id = f"Window_{window_elem.Id.IntegerValue}"
                
                # Get location point
                location = window_elem.Location
                if location and hasattr(location, 'Point'):
                    point = location.Point
                    center = (point.X, point.Y, point.Z)
                else:
                    # Fallback: use bounding box center
                    bbox = window_elem.get_BoundingBox(None)
                    if bbox:
                        center = (
                            (bbox.Min.X + bbox.Max.X) / 2,
                            (bbox.Min.Y + bbox.Max.Y) / 2,
                            (bbox.Min.Z + bbox.Max.Z) / 2
                        )
                    else:
                        logger.warning(f"Window {window_id} has no location or bounding box")
                        return None
                
                # Get size from bounding box
                bbox = window_elem.get_BoundingBox(None)
                if not bbox:
                    logger.warning(f"Window {window_id} has no bounding box")
                    return None
                
                # Calculate dimensions
                width = abs(bbox.Max.X - bbox.Min.X)
                height = abs(bbox.Max.Z - bbox.Min.Z)
                
                # Use width/height, skip if too small
                if width < 0.1 or height < 0.1:
                    logger.debug(f"Window {window_id} too small: {width}x{height}, skipping")
                    return None
                
                # Get normal vector (window orientation)
                normal = self._get_window_normal(window_elem)
                
                # Extract window properties from REVIT parameters
                properties = self._extract_window_properties(window_elem)
                
                # Get window type
                window_type = self._get_window_type(window_elem)
                
                # Get transmittance and frame factor from parameters
                transmittance = self._get_parameter_value(
                    window_elem, 
                    ["Glass_Transmittance", "Transmittance", "Light_Transmittance"],
                    0.75
                )
                frame_factor = self._get_parameter_value(
                    window_elem,
                    ["Frame_Factor", "Frame_Reduction", "Frame_Area_Factor"],
                    0.70
                )
                glass_thickness = self._get_parameter_value(
                    window_elem,
                    ["Glass_Thickness", "Thickness"],
                    4.0
                )
                
                # Create Window object
                window = Window(
                    id=window_id,
                    center=center,
                    normal=normal,
                    size=(width, height),
                    window_type=window_type,
                    glass_thickness=glass_thickness,
                    transmittance=transmittance,
                    frame_factor=frame_factor,
                    properties=properties
                )
                
                return window
                
            except Exception as e:
                logger.error(f"Error extracting window from element: {e}", exc_info=True)
                return None
        
        def _get_window_normal(self, window_elem: FamilyInstance) -> Tuple[float, float, float]:
            """Get window normal vector (direction window faces)."""
            try:
                # Try to get from wall host
                if window_elem.Host and hasattr(window_elem.Host, 'FacingOrientation'):
                    facing = window_elem.Host.FacingOrientation
                    return (facing.X, facing.Y, facing.Z)
                
                # Fallback: use transform
                transform = window_elem.GetTransform()
                if transform:
                    # Y-axis of transform is typically the window normal
                    basis_y = transform.BasisY
                    return (basis_y.X, basis_y.Y, basis_y.Z)
                
                # Default: outward facing
                return (0.0, 1.0, 0.0)
            except:
                return (0.0, 1.0, 0.0)
        
        def _get_window_type(self, window_elem: FamilyInstance) -> Optional[str]:
            """Get window type from REVIT element."""
            try:
                # Get family type name
                if window_elem.Symbol:
                    return window_elem.Symbol.FamilyName
                return None
            except:
                return None
        
        def _get_parameter_value(self, element: Element, param_names: List[str], default: float) -> float:
            """Get parameter value from REVIT element."""
            for param_name in param_names:
                try:
                    param = element.LookupParameter(param_name)
                    if param and param.HasValue:
                        if param.StorageType == DB.StorageType.Double:
                            return param.AsDouble()
                        elif param.StorageType == DB.StorageType.Integer:
                            return float(param.AsInteger())
                        elif param.StorageType == DB.StorageType.String:
                            try:
                                return float(param.AsString())
                            except:
                                pass
                except:
                    continue
            return default
        
        def _extract_window_properties(self, window_elem: FamilyInstance) -> Dict:
            """Extract all properties from REVIT window element."""
            properties = {}
            
            try:
                # Get all parameters
                for param in window_elem.Parameters:
                    if param and param.HasValue:
                        param_name = param.Definition.Name
                        try:
                            if param.StorageType == DB.StorageType.Double:
                                properties[param_name] = param.AsDouble()
                            elif param.StorageType == DB.StorageType.Integer:
                                properties[param_name] = param.AsInteger()
                            elif param.StorageType == DB.StorageType.String:
                                properties[param_name] = param.AsString()
                            elif param.StorageType == DB.StorageType.ElementId:
                                properties[param_name] = param.AsElementId().IntegerValue
                        except:
                            pass
                
                # Add REVIT-specific properties
                properties['RevitElementId'] = window_elem.Id.IntegerValue
                if window_elem.Symbol:
                    properties['FamilyName'] = window_elem.Symbol.FamilyName
                    properties['TypeName'] = window_elem.Symbol.Name
                
            except Exception as e:
                logger.warning(f"Error extracting window properties: {e}")
            
            return properties
        
        def _extract_location(self) -> Tuple[float, float]:
            """Extract building location (latitude, longitude) from REVIT project."""
            try:
                # Try to get from project location
                project_location = self.doc.SiteLocation
                if project_location:
                    latitude = project_location.Latitude
                    longitude = project_location.Longitude
                    return (latitude, longitude)
            except:
                pass
            
            # Default to Moscow
            return (55.7558, 37.6173)
        
        def __enter__(self):
            """Context manager entry."""
            self.open_document()
            return self
        
        def __exit__(self, exc_type, exc_val, exc_tb):
            """Context manager exit."""
            self.close_document()

else:
    # Fallback when REVIT API not available
    class RevitHeadlessExtractor:
        """Placeholder when REVIT API not available."""
        def __init__(self, rvt_file_path: str):
            raise NotImplementedError(
                "REVIT API not available. "
                "To use headless REVIT import:\n"
                "1. Install REVIT (required for DLLs)\n"
                "2. Install Python.NET: pip install pythonnet\n"
                "3. REVIT API DLLs will be loaded automatically"
            )
        
        def open_document(self):
            raise NotImplementedError("REVIT API not available")
        
        def extract_building(self):
            raise NotImplementedError("REVIT API not available")
        
        def extract_windows(self):
            raise NotImplementedError("REVIT API not available")

