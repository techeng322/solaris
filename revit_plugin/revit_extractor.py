"""
REVIT data extractor.
Extracts building, rooms, and windows directly from REVIT models.
"""

from typing import List, Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

try:
    from Autodesk.Revit import DB
    from Autodesk.Revit.DB import (
        FilteredElementCollector, BuiltInCategory, BuiltInParameter,
        SpatialElement, FamilyInstance, Element
    )
    REVIT_API_AVAILABLE = True
except ImportError:
    REVIT_API_AVAILABLE = False
    logger.warning("REVIT API not available - REVIT plugin features disabled")


if REVIT_API_AVAILABLE:
    from models.building import Building, Window
    
    class RevitExtractor:
        """Extract building data directly from REVIT document."""
        
        def __init__(self, doc):
            """
            Initialize REVIT extractor.
            
            Args:
                doc: REVIT Document object
            """
            self.doc = doc
        
        def extract_building(self) -> Building:
            """
            Extract building from REVIT document.
            
            Returns:
                Building object with windows
            """
            logger.info("Extracting building from REVIT document...")
            
            # Get project information
            project_info = self.doc.ProjectInformation
            building_name = project_info.Name if project_info else "Building 1"
            building_id = project_info.Number if project_info else "Building_1"
            
            # Get location (from project location or site location)
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
        
        def extract_windows(self) -> List[Window]:
            """
            Extract all windows from REVIT document.
            Uses REVIT's native window elements (FamilyInstance with Window category).
            
            Returns:
                List of Window objects
            """
            logger.info("Extracting windows from REVIT document...")
            windows = []
            
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
        
        def _extract_window_from_element(self, window_elem: FamilyInstance) -> Optional[Window]:
            """
            Extract window properties from REVIT FamilyInstance element.
            
            Args:
                window_elem: REVIT FamilyInstance element (window)
            
            Returns:
                Window object or None if extraction fails
            """
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
                depth = abs(bbox.Max.Y - bbox.Min.Y)
                
                # Use width/height, skip if too small
                if width < 0.1 or height < 0.1:
                    logger.debug(f"Window {window_id} too small: {width}x{height}, skipping")
                    return None
                
                # Get normal vector (window orientation)
                # Try to get from wall or use default
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
        
        def extract_rooms(self) -> List[Dict]:
            """
            Extract rooms from REVIT document.
            
            Returns:
                List of room dictionaries with geometry and properties
            """
            logger.info("Extracting rooms from REVIT document...")
            rooms = []
            
            try:
                # Get all room elements
                collector = FilteredElementCollector(self.doc)
                room_elements = collector.OfCategory(BuiltInCategory.OST_Rooms)\
                    .WhereElementIsNotElementType()\
                    .ToElements()
                
                logger.info(f"Found {len(list(room_elements))} room(s) in REVIT")
                
                for room_elem in room_elements:
                    try:
                        room_data = self._extract_room_data(room_elem)
                        if room_data:
                            rooms.append(room_data)
                    except Exception as e:
                        logger.warning(f"Error extracting room {room_elem.Id}: {e}")
                
                logger.info(f"Successfully extracted {len(rooms)} room(s)")
            except Exception as e:
                logger.error(f"Error extracting rooms: {e}", exc_info=True)
            
            return rooms
        
        def _extract_room_data(self, room_elem: SpatialElement) -> Optional[Dict]:
            """Extract room data from REVIT SpatialElement."""
            try:
                room_id = f"Room_{room_elem.Id.IntegerValue}"
                room_name = room_elem.get_Parameter(BuiltInParameter.ROOM_NAME).AsString() if room_elem.get_Parameter(BuiltInParameter.ROOM_NAME) else f"Room {room_elem.Id}"
                
                # Get room area
                area_param = room_elem.get_Parameter(BuiltInParameter.ROOM_AREA)
                area = area_param.AsDouble() if area_param else 0.0
                
                # Get room level/floor
                level = room_elem.Level
                floor_number = level.Elevation if level else 0.0
                
                # Get bounding box
                bbox = room_elem.get_BoundingBox(None)
                geometry = None
                if bbox:
                    geometry = {
                        'min': (bbox.Min.X, bbox.Min.Y, bbox.Min.Z),
                        'max': (bbox.Max.X, bbox.Max.Y, bbox.Max.Z),
                        'center': (
                            (bbox.Min.X + bbox.Max.X) / 2,
                            (bbox.Min.Y + bbox.Max.Y) / 2,
                            (bbox.Min.Z + bbox.Max.Z) / 2
                        )
                    }
                
                return {
                    'id': room_id,
                    'name': room_name,
                    'area': area,
                    'floor_number': floor_number,
                    'geometry': geometry,
                    'element_id': room_elem.Id.IntegerValue
                }
            except Exception as e:
                logger.warning(f"Error extracting room data: {e}")
                return None

else:
    # Fallback when REVIT API not available
    class RevitExtractor:
        """Placeholder when REVIT API not available."""
        def __init__(self, doc):
            raise NotImplementedError("REVIT API not available. Install REVIT and REVIT API to use this feature.")
        
        def extract_building(self):
            raise NotImplementedError("REVIT API not available")
        
        def extract_windows(self):
            raise NotImplementedError("REVIT API not available")

