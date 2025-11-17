"""
IFC (Industry Foundation Classes) model importer.
Extracts building information (rooms, windows, properties) from IFC files
using semantic data and relationships, avoiding heavy geometry processing.
"""

from typing import List, Dict, Optional, Tuple
import logging

# Try to import ifcopenshell (required for IFC file import)
try:
    import ifcopenshell
    from ifcopenshell import geom
    IFC_AVAILABLE = True
except ImportError:
    IFC_AVAILABLE = False
    ifcopenshell = None
    geom = None

import numpy as np

from .base_importer import BaseImporter
from models.building import Building, Window

# Try to import trimesh for mesh generation
try:
    import trimesh
    TRIMESH_AVAILABLE = True
except ImportError:
    TRIMESH_AVAILABLE = False

logger = logging.getLogger(__name__)

if not IFC_AVAILABLE:
    logger.warning("ifcopenshell not available - IFC file import disabled. Install with: pip install ifcopenshell (requires Python 3.8-3.12)")


class IFCImporter(BaseImporter):
    """
    Importer for IFC format BIM models.
    Extracts semantic data (rooms, windows, properties) using IFC relationships
    and properties, avoiding heavy geometry processing for better performance.
    """
    
    def __init__(self, file_path: str, lightweight: bool = True):
        """
        Initialize IFC importer.
        
        Args:
            file_path: Path to IFC file
            lightweight: If True, extract only semantic data without full geometry processing
        """
        super().__init__(file_path)
        self.ifc_file = None
        self.lightweight = lightweight
        self.schema_version: Optional[str] = None
        self.mesh = None  # 3D mesh for viewer display
        self.ifc_elements = {}  # Store IFC elements for tree viewer (spaces, storeys, walls, etc.)
    
    def import_model(self) -> List[Building]:
        """
        Import IFC model.
        
        Returns:
            List of Building objects
        """
        if not IFC_AVAILABLE:
            error_msg = (
                "ifcopenshell is not available. IFC file import requires ifcopenshell, "
                "which only supports Python 3.8-3.12.\n\n"
                "To use IFC files:\n"
                "1. Install Python 3.12 from: https://www.python.org/downloads/release/python-31211/\n"
                "2. Run: .\\setup_python312_env.ps1\n"
                "3. Or manually: py -3.12 -m venv venv312 && pip install ifcopenshell\n\n"
                "Note: GLB files work fine with Python 3.14."
            )
            logger.error(error_msg)
            raise ImportError(error_msg)
        
        try:
            logger.info(f"Opening IFC file: {self.file_path}")
            try:
                self.ifc_file = ifcopenshell.open(self.file_path)
                logger.info("IFC file opened successfully")
            except FileNotFoundError:
                error_msg = f"IFC file not found: {self.file_path}"
                logger.error(error_msg)
                raise ValueError(error_msg)
            except Exception as e:
                error_msg = f"Failed to open IFC file '{self.file_path}': {str(e)}\n\nPossible causes:\n- File is corrupted or incomplete\n- Unsupported IFC schema version\n- File is not a valid IFC file"
                logger.error(error_msg, exc_info=True)
                raise ValueError(error_msg)
            
            # Detect and log IFC schema version
            try:
                self.schema_version = self.ifc_file.schema
                logger.info(f"IFC Schema Version: {self.schema_version}")
                
                # Log schema-specific information
                if self.schema_version:
                    if 'IFC2X3' in self.schema_version:
                        logger.info("Using IFC2X3 schema (older format)")
                    elif 'IFC4' in self.schema_version:
                        logger.info("Using IFC4 schema (modern format)")
                    elif 'IFC4X3' in self.schema_version:
                        logger.info("Using IFC4X3 schema (latest format)")
            except Exception as e:
                logger.warning(f"Could not detect IFC schema version: {e}")
                self.schema_version = None
        except ValueError:
            # Re-raise ValueError as-is (already has user-friendly message)
            raise
        except Exception as e:
            logger.error(f"Unexpected error opening IFC file: {e}", exc_info=True)
            raise ValueError(f"Failed to open IFC file: {e}")
        
        # Extract buildings
        buildings = []
        
        # Get all building elements
        try:
            buildings_elements = self.ifc_file.by_type("IfcBuilding")
            logger.info(f"Found {len(buildings_elements)} IfcBuilding element(s)")
        except Exception as e:
            logger.error(f"Error getting building elements: {e}", exc_info=True)
            buildings_elements = []
        
        for building_elem in buildings_elements:
            try:
                building = self._extract_building(building_elem)
                if building:
                    buildings.append(building)
                    logger.info(f"Successfully extracted building: {building.name} with {building.get_total_windows()} windows")
                else:
                    logger.warning(f"Failed to extract building {building_elem.id()}")
            except Exception as e:
                logger.error(f"Error extracting building {building_elem.id()}: {e}", exc_info=True)
        
        # If no buildings found, create a default building
        if not buildings:
            logger.warning("No IfcBuilding elements found, creating default building")
            building = Building(
                id="Building_1",
                name="Building 1",
                location=(55.7558, 37.6173)  # Default to Moscow
            )
            # Extract windows directly
            try:
                windows = self.extract_windows()
                logger.info(f"Extracted {len(windows)} window(s) for default building")
                for window in windows:
                    building.add_window(window)
                buildings.append(building)
            except Exception as e:
                logger.error(f"Error extracting windows for default building: {e}", exc_info=True)
                # Still add building even if no windows
                buildings.append(building)
        
        if not buildings:
            raise ValueError("No buildings could be extracted from IFC file")
        
        # Extract IFC elements for object tree viewer
        try:
            self._extract_ifc_elements_for_tree()
        except Exception as e:
            logger.warning(f"Error extracting IFC elements for tree: {e}")
        
        # Generate 3D mesh for viewer display (always try, even in lightweight mode)
        # Mesh generation is needed for 3D visualization
        try:
            logger.info("Generating 3D mesh for viewer (this may take a moment for large files)...")
            self.mesh = self._generate_mesh_for_viewer()
            if self.mesh:
                logger.info(f"✓ Generated 3D mesh for viewer: {len(self.mesh.vertices):,} vertices, {len(self.mesh.faces):,} faces")
                logger.info("Mesh is ready for 3D viewer display")
            else:
                logger.warning("⚠ Could not generate 3D mesh for viewer - geometry may not be available in 3D viewer")
                logger.info("Note: Building data and calculations will still work, but 3D visualization may be limited")
                logger.info("Possible reasons: IFC file has no geometry, unsupported geometry format, or geometry extraction failed")
        except Exception as e:
            logger.warning(f"Error generating mesh for viewer: {e}")
            logger.info("Note: Building data and calculations will still work, but 3D visualization may be limited")
            import traceback
            logger.debug(f"Mesh generation error details: {traceback.format_exc()}")
            self.mesh = None
        
        logger.info(f"Import complete: {len(buildings)} building(s) extracted")
        return buildings
    
    def _extract_ifc_elements_for_tree(self):
        """Extract IFC elements (spaces, storeys, walls, etc.) for object tree display."""
        try:
            self.ifc_elements = {
                'spaces': [],
                'storeys': [],
                'walls': [],
                'doors': [],
                'openings': [],
                'slabs': [],
                'columns': [],
                'beams': []
            }
            
            # Extract spaces (rooms)
            try:
                spaces = self.ifc_file.by_type("IfcSpace")
                for space in spaces:
                    space_info = {
                        'id': space.GlobalId if hasattr(space, 'GlobalId') else str(space.id()),
                        'name': space.Name if hasattr(space, 'Name') else f"Space {space.id()}",
                        'element': space
                    }
                    self.ifc_elements['spaces'].append(space_info)
                logger.info(f"Extracted {len(spaces)} space(s) for object tree")
            except Exception as e:
                logger.debug(f"Error extracting spaces: {e}")
            
            # Extract storeys (floors)
            try:
                storeys = self.ifc_file.by_type("IfcBuildingStorey")
                for storey in storeys:
                    storey_info = {
                        'id': storey.GlobalId if hasattr(storey, 'GlobalId') else str(storey.id()),
                        'name': storey.Name if hasattr(storey, 'Name') else f"Storey {storey.id()}",
                        'element': storey
                    }
                    self.ifc_elements['storeys'].append(storey_info)
                logger.info(f"Extracted {len(storeys)} storey(s) for object tree")
            except Exception as e:
                logger.debug(f"Error extracting storeys: {e}")
            
            # Extract walls
            try:
                walls = self.ifc_file.by_type("IfcWall") + self.ifc_file.by_type("IfcWallStandardCase")
                for wall in walls:
                    wall_info = {
                        'id': wall.GlobalId if hasattr(wall, 'GlobalId') else str(wall.id()),
                        'name': wall.Name if hasattr(wall, 'Name') else f"Wall {wall.id()}",
                        'element': wall
                    }
                    self.ifc_elements['walls'].append(wall_info)
                logger.info(f"Extracted {len(walls)} wall(s) for object tree")
            except Exception as e:
                logger.debug(f"Error extracting walls: {e}")
            
            # Extract doors
            try:
                doors = self.ifc_file.by_type("IfcDoor")
                for door in doors:
                    door_info = {
                        'id': door.GlobalId if hasattr(door, 'GlobalId') else str(door.id()),
                        'name': door.Name if hasattr(door, 'Name') else f"Door {door.id()}",
                        'element': door
                    }
                    self.ifc_elements['doors'].append(door_info)
                logger.info(f"Extracted {len(doors)} door(s) for object tree")
            except Exception as e:
                logger.debug(f"Error extracting doors: {e}")
            
            # Extract openings
            try:
                openings = self.ifc_file.by_type("IfcOpeningElement")
                for opening in openings:
                    opening_info = {
                        'id': opening.GlobalId if hasattr(opening, 'GlobalId') else str(opening.id()),
                        'name': opening.Name if hasattr(opening, 'Name') else f"Opening {opening.id()}",
                        'element': opening
                    }
                    self.ifc_elements['openings'].append(opening_info)
                logger.info(f"Extracted {len(openings)} opening(s) for object tree")
            except Exception as e:
                logger.debug(f"Error extracting openings: {e}")
            
            # Extract slabs (floors/ceilings)
            try:
                slabs = self.ifc_file.by_type("IfcSlab")
                for slab in slabs:
                    slab_info = {
                        'id': slab.GlobalId if hasattr(slab, 'GlobalId') else str(slab.id()),
                        'name': slab.Name if hasattr(slab, 'Name') else f"Slab {slab.id()}",
                        'element': slab
                    }
                    self.ifc_elements['slabs'].append(slab_info)
                logger.info(f"Extracted {len(slabs)} slab(s) for object tree")
            except Exception as e:
                logger.debug(f"Error extracting slabs: {e}")
            
        except Exception as e:
            logger.error(f"Error extracting IFC elements for tree: {e}", exc_info=True)
    
    def _extract_building(self, building_elem) -> Optional[Building]:
        """Extract building from IFC element."""
        building_id = building_elem.GlobalId if hasattr(building_elem, 'GlobalId') else str(building_elem.id())
        building_name = building_elem.Name if hasattr(building_elem, 'Name') else f"Building {building_id}"
        
        building = Building(
            id=building_id,
            name=building_name
        )
        
        # Extract windows that belong to this building using spatial relationships
        windows = self._extract_windows_for_building(building_elem)
        for window in windows:
            building.add_window(window)
        
        logger.info(f"Building '{building_name}': {len(windows)} window(s)")
        
        return building
    
    def extract_windows(self) -> List[Window]:
        """
        Extract all windows from IFC model.
        Checks multiple window representations:
        - IfcWindow (direct window elements)
        - IfcOpeningElement (openings that might be windows)
        - Windows embedded in walls
        
        Returns:
            List of Window objects
        """
        windows = []
        
        # Method 1: Get all direct window elements
        try:
            window_elements = self.ifc_file.by_type("IfcWindow")
            logger.info(f"Found {len(window_elements)} IfcWindow element(s) in IFC file")
            
            for window_elem in window_elements:
                try:
                    window = self._extract_window(window_elem)
                    if window:
                        windows.append(window)
                    else:
                        logger.warning(f"Failed to extract window {window_elem.id()}")
                except Exception as e:
                    logger.error(f"Error extracting window {window_elem.id()}: {e}", exc_info=True)
        except Exception as e:
            logger.warning(f"Error getting IfcWindow elements: {e}")
        
        # Method 2: Extract windows from openings (IfcOpeningElement)
        # Check openings even if we found some windows (files may have both)
        logger.info("Checking for IfcOpeningElement (openings that might be windows)...")
        try:
            opening_elements = self.ifc_file.by_type("IfcOpeningElement")
            logger.info(f"Found {len(opening_elements)} IfcOpeningElement(s)")
            
            opening_windows = []
            for opening_elem in opening_elements:
                try:
                    window = self._extract_window_from_opening(opening_elem)
                    if window:
                        opening_windows.append(window)
                except Exception as e:
                    logger.debug(f"Error extracting window from opening {opening_elem.id()}: {e}")
            
            if opening_windows:
                windows.extend(opening_windows)
                logger.info(f"Extracted {len(opening_windows)} window(s) from openings")
        except Exception as e:
            logger.warning(f"Error getting IfcOpeningElement: {e}")
        
        # Method 3: Extract windows from walls (openings in walls)
        # Check walls even if we found some windows
        logger.info("Checking walls for window openings...")
        try:
            wall_windows = self._extract_windows_from_walls()
            if wall_windows:
                windows.extend(wall_windows)
                logger.info(f"Extracted {len(wall_windows)} window(s) from walls")
        except Exception as e:
            logger.warning(f"Error extracting windows from walls: {e}")
        
        logger.info(f"Successfully extracted {len(windows)} window(s) total")
        return windows
    
    def _extract_windows_for_building(self, building_elem) -> List[Window]:
        """
        Extract windows that belong to a specific building using spatial relationships.
        
        Args:
            building_elem: IFC building element
            
        Returns:
            List of Window objects belonging to this building
        """
        windows = []
        
        try:
            # Method 1: Use IfcRelContainedInSpatialStructure to find windows in this building
            contained_rels = self.ifc_file.by_type("IfcRelContainedInSpatialStructure")
            
            # Get all storeys in this building
            building_storeys = []
            for rel in contained_rels:
                if rel.RelatingStructure == building_elem:
                    for elem in rel.RelatedElements:
                        if elem.is_a("IfcBuildingStorey"):
                            building_storeys.append(elem)
            
            # Get all spaces in this building (through storeys)
            building_spaces = []
            for storey in building_storeys:
                for rel in contained_rels:
                    if rel.RelatingStructure == storey:
                        for elem in rel.RelatedElements:
                            if elem.is_a("IfcSpace"):
                                building_spaces.append(elem)
            
            # Find windows contained in this building's spaces or storeys
            window_ids_in_building = set()
            for rel in contained_rels:
                # Check if window is directly in building
                if rel.RelatingStructure == building_elem:
                    for elem in rel.RelatedElements:
                        if elem.is_a("IfcWindow"):
                            window_ids_in_building.add(elem.id())
                
                # Check if window is in building's storeys
                if rel.RelatingStructure in building_storeys:
                    for elem in rel.RelatedElements:
                        if elem.is_a("IfcWindow"):
                            window_ids_in_building.add(elem.id())
                
                # Check if window is in building's spaces
                if rel.RelatingStructure in building_spaces:
                    for elem in rel.RelatedElements:
                        if elem.is_a("IfcWindow"):
                            window_ids_in_building.add(elem.id())
            
            # Extract windows that belong to this building
            all_windows = self.ifc_file.by_type("IfcWindow")
            for window_elem in all_windows:
                if window_elem.id() in window_ids_in_building:
                    window = self._extract_window(window_elem)
                    if window:
                        windows.append(window)
            
            # If no windows found via relationships, try to find windows by spatial proximity
            if not windows:
                logger.info(f"No windows found via relationships for building {building_elem.id()}, extracting all windows as fallback")
                # Fallback: extract all windows (for files without proper relationships)
                try:
                    all_extracted = self.extract_windows()
                    windows.extend(all_extracted)
                    logger.info(f"Fallback: Added {len(all_extracted)} window(s) to building")
                except Exception as e:
                    logger.error(f"Error in fallback window extraction: {e}", exc_info=True)
                
        except Exception as e:
            logger.warning(f"Error extracting windows for building {building_elem.id()}: {e}")
            # Fallback: extract all windows
            windows = self.extract_windows()
        
        return windows
    
    def _extract_window(self, window_elem) -> Optional[Window]:
        """Extract window from IFC window element."""
        try:
            window_id = window_elem.GlobalId if hasattr(window_elem, 'GlobalId') else str(window_elem.id())
            logger.debug(f"Extracting window {window_id}")
            
            # Extract geometry
            geometry = self._extract_geometry(window_elem)
            
            # Extract center and size
            try:
                center, normal, size = self._extract_window_geometry(window_elem)
                logger.debug(f"Window {window_id}: center={center}, size={size}, normal={normal}")
            except Exception as e:
                logger.error(f"Failed to extract geometry for window {window_id}: {e}", exc_info=True)
                # Use defaults
                center = (0.0, 0.0, 1.5)
                normal = (0.0, 1.0, 0.0)
                size = (1.5, 1.2)
            
            # Extract all properties (enhanced - supports all IFC property types)
            try:
                all_properties = self._extract_properties(window_elem)
            except Exception as e:
                logger.warning(f"Error extracting properties for window {window_id}: {e}")
                all_properties = {}
            
            # Extract material properties
            try:
                material_props = self._extract_material_properties(window_elem)
                if material_props:
                    all_properties['material'] = material_props
            except Exception as e:
                logger.debug(f"Error extracting material properties for window {window_id}: {e}")
            
            # Recognize window type and properties
            try:
                window_props = self.recognize_window_type(window_elem)
            except Exception as e:
                logger.warning(f"Error recognizing window type for window {window_id}: {e}")
                window_props = {
                    'window_type': 'unknown',
                    'glass_thickness': 4.0,
                    'transmittance': 0.75,
                    'frame_factor': 0.70
                }
            
            # Merge all properties
            window_props.update(all_properties)
            
            # Validate window data
            if size[0] <= 0 or size[1] <= 0:
                logger.warning(f"Invalid window size {size} for window {window_id}, using defaults")
                size = (1.5, 1.2)
            
            window = Window(
                id=window_id,
                center=center,
                normal=normal,
                size=size,
                window_type=window_props.get('window_type'),
                glass_thickness=window_props.get('glass_thickness', 4.0),
                transmittance=window_props.get('transmittance', 0.75),
                frame_factor=window_props.get('frame_factor', 0.70),
                properties=window_props
            )
            
            logger.debug(f"Successfully extracted window {window_id}: size={size}, center={center}")
            return window
            
        except Exception as e:
            logger.error(f"Failed to extract window {window_elem.id()}: {e}", exc_info=True)
            return None
    
    def recognize_window_type(self, window_element) -> Dict:
        """
        Recognize window type from IFC element properties.
        
        Args:
            window_element: IFC window element
        
        Returns:
            Dictionary with window properties
        """
        props = {
            'window_type': 'unknown',
            'glass_thickness': 4.0,
            'transmittance': 0.75,
            'frame_factor': 0.70
        }
        
        # Try to extract properties from IFC element
        if hasattr(window_element, 'IsTypedBy') and window_element.IsTypedBy:
            type_elem = window_element.IsTypedBy[0].RelatingType
            if hasattr(type_elem, 'Name'):
                type_name = type_elem.Name.lower()
                
                # Recognize common window types
                if 'single' in type_name or 'однокамерный' in type_name:
                    props['window_type'] = 'single_glazed'
                    props['glass_thickness'] = 4.0
                    props['transmittance'] = 0.85
                    props['frame_factor'] = 0.75
                elif 'double' in type_name or 'двухкамерный' in type_name:
                    props['window_type'] = 'double_glazed'
                    props['glass_thickness'] = 6.0
                    props['transmittance'] = 0.75
                    props['frame_factor'] = 0.70
                elif 'triple' in type_name or 'трехкамерный' in type_name:
                    props['window_type'] = 'triple_glazed'
                    props['glass_thickness'] = 8.0
                    props['transmittance'] = 0.65
                    props['frame_factor'] = 0.65
        
        return props
    
    def _extract_window_from_opening(self, opening_elem) -> Optional[Window]:
        """
        Extract window from IfcOpeningElement.
        Openings in IFC can represent windows, doors, or other openings.
        
        Args:
            opening_elem: IFC IfcOpeningElement
            
        Returns:
            Window object or None if not a window
        """
        try:
            opening_id = opening_elem.GlobalId if hasattr(opening_elem, 'GlobalId') else str(opening_elem.id())
            opening_name = opening_elem.Name if hasattr(opening_elem, 'Name') else ""
            
            # Check if this opening is actually a window (not a door)
            # Look for window-related keywords in name or properties
            is_window = False
            if opening_name:
                name_lower = opening_name.lower()
                if any(keyword in name_lower for keyword in ['window', 'окно', 'fenetre', 'fenster', 'glazing', 'glass']):
                    is_window = True
                elif any(keyword in name_lower for keyword in ['door', 'дверь', 'porte', 'tür']):
                    is_window = False  # Explicitly a door
                else:
                    # If name doesn't indicate door, assume it might be a window
                    # (many IFC files don't properly distinguish)
                    is_window = True
            
            # Also check properties
            properties = self._extract_properties(opening_elem)
            if 'Window' in str(properties) or 'window' in str(properties).lower():
                is_window = True
            elif 'Door' in str(properties) or 'door' in str(properties).lower():
                is_window = False
            
            if not is_window:
                logger.debug(f"Opening {opening_id} is not a window (likely a door)")
                return None
            
            logger.info(f"Extracting window from opening {opening_id}: {opening_name}")
            
            # Extract geometry
            try:
                center, normal, size = self._extract_window_geometry(opening_elem)
            except Exception as e:
                logger.warning(f"Failed to extract geometry from opening {opening_id}: {e}")
                # Use defaults
                center = (0.0, 0.0, 1.5)
                normal = (0.0, 1.0, 0.0)
                size = (1.5, 1.2)
            
            # Extract properties
            window_props = {
                'window_type': 'unknown',
                'glass_thickness': 4.0,
                'transmittance': 0.75,
                'frame_factor': 0.70
            }
            window_props.update(properties)
            
            window = Window(
                id=f"Opening_{opening_id}",
                center=center,
                normal=normal,
                size=size,
                window_type=window_props.get('window_type'),
                glass_thickness=window_props.get('glass_thickness', 4.0),
                transmittance=window_props.get('transmittance', 0.75),
                frame_factor=window_props.get('frame_factor', 0.70),
                properties=window_props
            )
            
            logger.debug(f"Successfully extracted window from opening {opening_id}")
            return window
            
        except Exception as e:
            logger.error(f"Error extracting window from opening {opening_elem.id()}: {e}", exc_info=True)
            return None
    
    def _extract_windows_from_walls(self) -> List[Window]:
        """
        Extract windows from walls by finding openings.
        Checks IfcWall elements for openings that might be windows.
        
        Returns:
            List of Window objects
        """
        windows = []
        
        try:
            # Get all walls
            walls = self.ifc_file.by_type("IfcWall")
            logger.info(f"Found {len(walls)} IfcWall element(s)")
            
            # Check each wall for openings
            for wall in walls:
                try:
                    # Check if wall has openings
                    if hasattr(wall, 'HasOpenings') and wall.HasOpenings:
                        for rel_opening in wall.HasOpenings:
                            if hasattr(rel_opening, 'RelatedOpeningElement'):
                                opening = rel_opening.RelatedOpeningElement
                                if opening and opening.is_a("IfcOpeningElement"):
                                    window = self._extract_window_from_opening(opening)
                                    if window:
                                        windows.append(window)
                except Exception as e:
                    logger.debug(f"Error checking wall {wall.id()} for openings: {e}")
            
        except Exception as e:
            logger.warning(f"Error extracting windows from walls: {e}")
        
        return windows
    
    def _extract_geometry(self, element) -> Dict:
        """
        Extract lightweight geometry reference from IFC element.
        Stores only element ID and type - full geometry loaded on demand if needed.
        """
        geometry = {
            'type': 'ifc_element',
            'element_id': str(element.id()),
            'element_type': element.is_a()
        }
        
        # Store GlobalId if available for reference
        if hasattr(element, 'GlobalId'):
            geometry['global_id'] = element.GlobalId
        
        return geometry
    
    def _extract_properties(self, element) -> Dict:
        """
        Extract all properties from IFC element.
        Supports all IFC property types:
        - IfcPropertySingleValue
        - IfcPropertyBoundedValue
        - IfcPropertyEnumeratedValue
        - IfcPropertyListValue
        - IfcPropertyTableValue
        - IfcPropertyReferenceValue
        Uses IfcPropertySet and IfcElementQuantity to get semantic data.
        """
        properties = {}
        
        try:
            # Method 1: Extract from IfcPropertySet (supports all property types)
            if hasattr(element, 'IsDefinedBy'):
                for rel in element.IsDefinedBy:
                    if rel.is_a("IfcRelDefinesByProperties"):
                        prop_set = rel.RelatingPropertyDefinition
                        if prop_set.is_a("IfcPropertySet"):
                            for prop in prop_set.HasProperties:
                                prop_name = prop.Name if hasattr(prop, 'Name') else None
                                if not prop_name:
                                    continue
                                
                                # Handle different property types
                                prop_type = prop.is_a()
                                
                                if prop_type == "IfcPropertySingleValue":
                                    # Single value property
                                    if hasattr(prop, 'NominalValue') and prop.NominalValue:
                                        prop_value = prop.NominalValue
                                        if hasattr(prop_value, 'wrappedValue'):
                                            properties[prop_name] = prop_value.wrappedValue
                                        else:
                                            properties[prop_name] = prop_value
                                
                                elif prop_type == "IfcPropertyBoundedValue":
                                    # Bounded value property (min/max range)
                                    bounded_value = {}
                                    if hasattr(prop, 'UpperBoundValue') and prop.UpperBoundValue:
                                        if hasattr(prop.UpperBoundValue, 'wrappedValue'):
                                            bounded_value['max'] = prop.UpperBoundValue.wrappedValue
                                        else:
                                            bounded_value['max'] = prop.UpperBoundValue
                                    if hasattr(prop, 'LowerBoundValue') and prop.LowerBoundValue:
                                        if hasattr(prop.LowerBoundValue, 'wrappedValue'):
                                            bounded_value['min'] = prop.LowerBoundValue.wrappedValue
                                        else:
                                            bounded_value['min'] = prop.LowerBoundValue
                                    if bounded_value:
                                        properties[prop_name] = bounded_value
                                
                                elif prop_type == "IfcPropertyEnumeratedValue":
                                    # Enumerated value property
                                    if hasattr(prop, 'EnumerationValues') and prop.EnumerationValues:
                                        enum_values = []
                                        for enum_val in prop.EnumerationValues:
                                            if hasattr(enum_val, 'wrappedValue'):
                                                enum_values.append(enum_val.wrappedValue)
                                            else:
                                                enum_values.append(enum_val)
                                        properties[prop_name] = enum_values
                                
                                elif prop_type == "IfcPropertyListValue":
                                    # List value property
                                    if hasattr(prop, 'ListValues') and prop.ListValues:
                                        list_values = []
                                        for list_val in prop.ListValues:
                                            if hasattr(list_val, 'wrappedValue'):
                                                list_values.append(list_val.wrappedValue)
                                            else:
                                                list_values.append(list_val)
                                        properties[prop_name] = list_values
                                
                                elif prop_type == "IfcPropertyTableValue":
                                    # Table value property
                                    if hasattr(prop, 'DefiningValues') and hasattr(prop, 'DefinedValues'):
                                        table_data = {
                                            'defining': [],
                                            'defined': []
                                        }
                                        if prop.DefiningValues:
                                            for val in prop.DefiningValues:
                                                if hasattr(val, 'wrappedValue'):
                                                    table_data['defining'].append(val.wrappedValue)
                                                else:
                                                    table_data['defining'].append(val)
                                        if prop.DefinedValues:
                                            for val in prop.DefinedValues:
                                                if hasattr(val, 'wrappedValue'):
                                                    table_data['defined'].append(val.wrappedValue)
                                                else:
                                                    table_data['defined'].append(val)
                                        if table_data['defining'] or table_data['defined']:
                                            properties[prop_name] = table_data
                                
                                elif prop_type == "IfcPropertyReferenceValue":
                                    # Reference value property
                                    if hasattr(prop, 'PropertyReference'):
                                        properties[prop_name] = str(prop.PropertyReference)
            
            # Method 2: Extract from IfcElementQuantity (quantities)
            if hasattr(element, 'IsDefinedBy'):
                for rel in element.IsDefinedBy:
                    if rel.is_a("IfcRelDefinesByProperties"):
                        qty_set = rel.RelatingPropertyDefinition
                        if qty_set.is_a("IfcElementQuantity"):
                            for qty in qty_set.Quantities:
                                qty_name = qty.Name if hasattr(qty, 'Name') else None
                                if not qty_name:
                                    continue
                                
                                # Handle different quantity types
                                qty_type = qty.is_a()
                                
                                if qty_type == "IfcQuantityLength":
                                    if hasattr(qty, 'LengthValue') and qty.LengthValue is not None:
                                        properties[qty_name] = float(qty.LengthValue)
                                elif qty_type == "IfcQuantityArea":
                                    if hasattr(qty, 'AreaValue') and qty.AreaValue is not None:
                                        properties[qty_name] = float(qty.AreaValue)
                                elif qty_type == "IfcQuantityVolume":
                                    if hasattr(qty, 'VolumeValue') and qty.VolumeValue is not None:
                                        properties[qty_name] = float(qty.VolumeValue)
                                elif qty_type == "IfcQuantityWeight":
                                    if hasattr(qty, 'WeightValue') and qty.WeightValue is not None:
                                        properties[qty_name] = float(qty.WeightValue)
                                elif qty_type == "IfcQuantityCount":
                                    if hasattr(qty, 'CountValue') and qty.CountValue is not None:
                                        properties[qty_name] = int(qty.CountValue)
                                elif qty_type == "IfcQuantityTime":
                                    if hasattr(qty, 'TimeValue') and qty.TimeValue is not None:
                                        properties[qty_name] = float(qty.TimeValue)
            
            # Method 3: Extract common attributes directly
            if hasattr(element, 'OverallWidth'):
                properties['OverallWidth'] = float(element.OverallWidth)
            if hasattr(element, 'OverallHeight'):
                properties['OverallHeight'] = float(element.OverallHeight)
            if hasattr(element, 'OverallDepth'):
                properties['OverallDepth'] = float(element.OverallDepth)
                
        except Exception as e:
            logger.debug(f"Error extracting properties: {e}")
        
        return properties
    
    def _extract_window_geometry(self, window_elem) -> Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float]]:
        """
        Extract window center, normal, and size from IFC element.
        Uses properties first, then lightweight geometry extraction if needed.
        """
        # Try to extract from properties first (fastest)
        properties = self._extract_properties(window_elem)
        
        # Extract size from properties (try multiple property names)
        width = properties.get('OverallWidth') or properties.get('Width') or properties.get('NominalWidth')
        height = properties.get('OverallHeight') or properties.get('Height') or properties.get('NominalHeight')
        
        # Try to convert to float if they're strings
        try:
            if width is not None:
                width = float(width)
        except (ValueError, TypeError):
            width = None
        
        try:
            if height is not None:
                height = float(height)
        except (ValueError, TypeError):
            height = None
        
        # If properties don't have size, try geometry extraction
        if width is None or height is None or width <= 0 or height <= 0:
            logger.debug(f"Window size not found in properties, trying geometry extraction")
            if not self.lightweight:
                try:
                    geom_center, geom_normal, geom_size = self._extract_geometry_from_ifc(window_elem)
                    if geom_size[0] > 0 and geom_size[1] > 0:
                        logger.debug(f"Using geometry-extracted size: {geom_size}")
                        # Use geometry-extracted values
                        return geom_center, geom_normal, geom_size
                except Exception as e:
                    logger.debug(f"Geometry extraction failed: {e}")
            else:
                logger.debug("Lightweight mode: skipping geometry extraction")
        
        # Use properties or defaults
        width = float(width) if width and width > 0 else 1.5
        height = float(height) if height and height > 0 else 1.2
        size = (width, height)
        logger.debug(f"Using size from properties/defaults: {size}")
        
        # Extract position from properties or placement
        center = self._extract_window_position(window_elem, properties)
        
        # Extract normal (direction window faces) from placement
        normal = self._extract_window_normal(window_elem, properties)
        
        # Validate extracted values
        if not all(isinstance(c, (int, float)) and abs(c) < 1e6 for c in center):
            logger.warning(f"Invalid window center coordinates: {center}, using default")
            center = (0.0, 0.0, 1.5)
        
        if not all(isinstance(n, (int, float)) and abs(n) <= 1.0 for n in normal):
            logger.warning(f"Invalid window normal: {normal}, using default")
            normal = (0.0, 1.0, 0.0)
        
        return center, normal, size
    
    def _extract_window_position(self, window_elem, properties: Dict) -> Tuple[float, float, float]:
        """
        Extract window position from IFC element placement or properties.
        Handles hierarchical placements (relative to parent elements).
        """
        # Try to get from ObjectPlacement (handles relative placements)
        try:
            if hasattr(window_elem, 'ObjectPlacement') and window_elem.ObjectPlacement:
                placement = window_elem.ObjectPlacement
                coords = self._get_absolute_coordinates(placement)
                if coords:
                    return coords
        except Exception as e:
            logger.debug(f"Error extracting window position from placement: {e}")
        
        # Try geometry extraction if not lightweight
        if not self.lightweight:
            try:
                geom_center, _, _ = self._extract_geometry_from_ifc(window_elem)
                if geom_center and all(abs(c) < 1e6 for c in geom_center):  # Sanity check
                    return geom_center
            except Exception as e:
                logger.debug(f"Error extracting window position from geometry: {e}")
        
        # Fallback: use properties or default
        x = properties.get('X', properties.get('LocationX', 0.0))
        y = properties.get('Y', properties.get('LocationY', 0.0))
        z = properties.get('SillHeight', properties.get('Z', properties.get('LocationZ', 1.5)))
        return (float(x), float(y), float(z))
    
    def _get_absolute_coordinates(self, placement) -> Optional[Tuple[float, float, float]]:
        """
        Get absolute coordinates from IFC placement, handling relative placements.
        
        Args:
            placement: IFC ObjectPlacement element
            
        Returns:
            Tuple of (x, y, z) coordinates or None if extraction fails
        """
        try:
            # Handle IfcLocalPlacement (relative placement)
            if placement.is_a("IfcLocalPlacement"):
                if hasattr(placement, 'RelativePlacement') and placement.RelativePlacement:
                    rel_placement = placement.RelativePlacement
                    if hasattr(rel_placement, 'Location') and rel_placement.Location:
                        location = rel_placement.Location
                        if hasattr(location, 'Coordinates'):
                            coords = location.Coordinates
                            if len(coords) >= 3:
                                base_coords = [float(coords[0]), float(coords[1]), float(coords[2])]
                                
                                # If placement is relative to parent, need to transform
                                if hasattr(placement, 'PlacementRelTo') and placement.PlacementRelTo:
                                    parent_coords = self._get_absolute_coordinates(placement.PlacementRelTo)
                                    if parent_coords:
                                        # Add parent coordinates (simplified - should use transformation matrix)
                                        return (
                                            base_coords[0] + parent_coords[0],
                                            base_coords[1] + parent_coords[1],
                                            base_coords[2] + parent_coords[2]
                                        )
                                
                                return tuple(base_coords)
            
            # Handle IfcGridPlacement (grid-based placement)
            elif placement.is_a("IfcGridPlacement"):
                # Grid placements are more complex - would need grid definition
                logger.debug("IfcGridPlacement not fully supported, using default position")
                return None
                
        except Exception as e:
            logger.debug(f"Error getting absolute coordinates: {e}")
        
        return None
    
    def _extract_window_normal(self, window_elem, properties: Dict) -> Tuple[float, float, float]:
        """Extract window normal (direction) from IFC element placement."""
        # Try to get from ObjectPlacement rotation
        try:
            if hasattr(window_elem, 'ObjectPlacement') and window_elem.ObjectPlacement:
                placement = window_elem.ObjectPlacement
                if hasattr(placement, 'RelativePlacement') and placement.RelativePlacement:
                    axis = placement.RelativePlacement.Axis
                    if axis and hasattr(axis, 'DirectionRatios'):
                        ratios = axis.DirectionRatios
                        if len(ratios) >= 3:
                            return (float(ratios[0]), float(ratios[1]), float(ratios[2]))
        except Exception as e:
            logger.debug(f"Error extracting window normal: {e}")
        
        # Fallback: use properties or default (facing north)
        direction = properties.get('Direction', 'North')
        direction_map = {
            'North': (0.0, 1.0, 0.0),
            'South': (0.0, -1.0, 0.0),
            'East': (1.0, 0.0, 0.0),
            'West': (-1.0, 0.0, 0.0)
        }
        return direction_map.get(direction, (0.0, 1.0, 0.0))
    
    def _extract_geometry_from_ifc(self, element) -> Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float]]:
        """
        Extract geometry from IFC element using ifcopenshell.geom.
        Only used when lightweight=False for accurate geometry.
        Handles coordinate transformations properly.
        """
        try:
            settings = geom.settings()
            # Use world coordinates (if available in this version)
            try:
                if hasattr(settings, 'USE_WORLD_COORDS'):
                    settings.set(settings.USE_WORLD_COORDS, True)
            except:
                pass  # Some versions don't have this setting
            shape = geom.create_shape(settings, element)
            geometry = shape.geometry
            
            # Get bounding box
            bbox = geometry.bbox
            if bbox is None or len(bbox) < 2:
                raise ValueError("Invalid bounding box")
            
            min_bounds = bbox[0]
            max_bounds = bbox[1]
            
            # Calculate center
            center = (
                float((min_bounds[0] + max_bounds[0]) / 2),
                float((min_bounds[1] + max_bounds[1]) / 2),
                float((min_bounds[2] + max_bounds[2]) / 2)
            )
            
            # Calculate size (width, height, depth)
            width = abs(max_bounds[0] - min_bounds[0])
            depth = abs(max_bounds[1] - min_bounds[1])
            height = abs(max_bounds[2] - min_bounds[2])
            
            # For windows, size is typically (width, height)
            # Use the two largest dimensions
            dims = sorted([width, depth, height], reverse=True)
            size = (float(dims[0]), float(dims[1]))  # width, height
            
            # Extract normal from transformation matrix if available
            normal = (0.0, 1.0, 0.0)  # Default facing north
            try:
                if hasattr(shape, 'transformation') and shape.transformation:
                    # Extract Z-axis from transformation matrix (window normal)
                    matrix = shape.transformation.matrix.data
                    if len(matrix) >= 12:
                        # Z-axis is typically columns 8, 9, 10 (0-indexed: 8, 9, 10)
                        normal = (
                            float(matrix[8]),
                            float(matrix[9]),
                            float(matrix[10])
                        )
                        # Normalize
                        norm_length = (normal[0]**2 + normal[1]**2 + normal[2]**2)**0.5
                        if norm_length > 0:
                            normal = (normal[0]/norm_length, normal[1]/norm_length, normal[2]/norm_length)
            except Exception as e:
                logger.debug(f"Could not extract normal from transformation: {e}")
            
            # Validate extracted values
            if not all(isinstance(c, (int, float)) and abs(c) < 1e6 for c in center):
                raise ValueError(f"Invalid center coordinates: {center}")
            
            if size[0] <= 0 or size[1] <= 0:
                raise ValueError(f"Invalid size: {size}")
            
            return center, normal, size
        except Exception as e:
            logger.warning(f"Failed to extract geometry from IFC element {element.id()}: {e}")
            raise
    
    def _extract_dimensions(self, space_elem, properties: Optional[Dict] = None) -> Tuple[float, float, float]:
        """
        Extract room dimensions from IFC properties or geometry.
        Uses properties first (fast), falls back to geometry if needed.
        """
        if properties is None:
            properties = self._extract_properties(space_elem)
        
        # Try to extract from properties
        depth = properties.get('Depth', properties.get('Length', None))
        width = properties.get('Width', properties.get('Breadth', None))
        height = properties.get('Height', properties.get('CeilingHeight', None))
        
        # If properties available, use them
        if depth is not None and width is not None and height is not None:
            return (float(depth), float(width), float(height))
        
        # Fallback: extract from geometry (lightweight - just bounding box)
        if not self.lightweight:
            try:
                settings = geom.settings()
                shape = geom.create_shape(settings, space_elem)
                geometry = shape.geometry
                bbox = geometry.bbox
                
                depth = abs(bbox[1][0] - bbox[0][0])
                width = abs(bbox[1][1] - bbox[0][1])
                height = abs(bbox[1][2] - bbox[0][2])
                
                if depth > 0 and width > 0 and height > 0:
                    return (float(depth), float(width), float(height))
            except Exception as e:
                logger.debug(f"Geometry extraction failed: {e}")
        
        # Default values if extraction fails
        return (5.0, 4.0, 3.0)
    
    def _extract_floor_area(self, space_elem, properties: Dict, depth: float, width: float) -> float:
        """Extract floor area from properties or calculate from dimensions."""
        # Try to get from properties first
        floor_area = properties.get('GrossFloorArea', properties.get('FloorArea', None))
        if floor_area is not None:
            return float(floor_area)
        
        # Calculate from dimensions
        if depth > 0 and width > 0:
            return depth * width
        
        return 0.0
    
    def _extract_floor_number(self, space_elem) -> int:
        """
        Extract floor number from IFC space element using relationships.
        Uses IfcRelContainedInSpatialStructure to find which storey contains the space.
        """
        try:
            # Method 1: Check IfcRelContainedInSpatialStructure relationship
            contained_rels = self.ifc_file.by_type("IfcRelContainedInSpatialStructure")
            for rel in contained_rels:
                if space_elem in rel.RelatedElements:
                    container = rel.RelatingStructure
                    if container and container.is_a("IfcBuildingStorey"):
                        # Extract floor number from storey name or elevation
                        storey_name = container.Name if hasattr(container, 'Name') else ""
                        # Try to parse floor number from name (e.g., "Level 1", "Floor 2")
                        import re
                        match = re.search(r'(\d+)', storey_name)
                        if match:
                            return int(match.group(1))
                        
                        # Try elevation
                        if hasattr(container, 'Elevation'):
                            elevation = container.Elevation
                            # Assume 3m per floor
                            floor_number = max(1, int(elevation / 3.0) + 1)
                            return floor_number
        except Exception as e:
            logger.debug(f"Error extracting floor number from relationships: {e}")
        
        # Method 2: Extract from space elevation
        try:
            if hasattr(space_elem, 'ElevationOfRefHeight'):
                elevation = space_elem.ElevationOfRefHeight
                # Assume 3m per floor
                floor_number = max(1, int(elevation / 3.0) + 1)
                return floor_number
        except Exception as e:
            logger.debug(f"Error extracting floor number from elevation: {e}")
        
        # Default
        return 1
    
    def _extract_loggia(self, space_elem, room_id: str):
        """Extract loggia information if present."""
        # Check if space is a loggia or has loggia attached
        # Simplified - would need more complex logic
        return None
    
    def _extract_material_properties(self, element) -> Dict:
        """
        Extract material properties from IFC element.
        Uses IfcRelAssociatesMaterial relationship.
        
        Returns:
            Dictionary with material properties (name, type, thermal properties, etc.)
        """
        material_props = {}
        
        try:
            # Get material association
            if hasattr(element, 'HasAssociations'):
                for assoc in element.HasAssociations:
                    if assoc.is_a("IfcRelAssociatesMaterial"):
                        material_select = assoc.RelatingMaterial
                        
                        # Handle different material types
                        if material_select.is_a("IfcMaterial"):
                            material = material_select
                            material_props['name'] = material.Name if hasattr(material, 'Name') else None
                            material_props['type'] = 'IfcMaterial'
                            
                            # Get material properties
                            if hasattr(material, 'HasProperties'):
                                for prop in material.HasProperties:
                                    if hasattr(prop, 'Name') and hasattr(prop, 'NominalValue'):
                                        prop_name = prop.Name
                                        prop_value = prop.NominalValue
                                        if prop_value and hasattr(prop_value, 'wrappedValue'):
                                            material_props[prop_name] = prop_value.wrappedValue
                        
                        elif material_select.is_a("IfcMaterialList"):
                            # List of materials
                            materials = []
                            for mat in material_select.Materials:
                                if hasattr(mat, 'Name'):
                                    materials.append(mat.Name)
                            material_props['materials'] = materials
                            material_props['type'] = 'IfcMaterialList'
                        
                        elif material_select.is_a("IfcMaterialLayerSet"):
                            # Layered material
                            layers = []
                            for layer in material_select.MaterialLayers:
                                layer_info = {}
                                if hasattr(layer, 'Material') and layer.Material:
                                    if hasattr(layer.Material, 'Name'):
                                        layer_info['name'] = layer.Material.Name
                                if hasattr(layer, 'LayerThickness'):
                                    layer_info['thickness'] = float(layer.LayerThickness)
                                layers.append(layer_info)
                            material_props['layers'] = layers
                            material_props['type'] = 'IfcMaterialLayerSet'
                        
                        break  # Only process first material association
        
        except Exception as e:
            logger.debug(f"Error extracting material properties: {e}")
        
        return material_props
    
    def _generate_mesh_for_viewer(self):
        """
        Generate 3D mesh from IFC geometry for viewer display.
        Combines geometry from walls, spaces, and other building elements.
        
        Returns:
            trimesh.Trimesh object or None if generation fails
        """
        if not TRIMESH_AVAILABLE:
            logger.warning("trimesh not available - cannot generate mesh for viewer")
            return None
        
        try:
            logger.info("Generating 3D mesh from IFC geometry...")
            meshes = []
            
            # Get all building elements that have geometry
            element_types = [
                "IfcWall",
                "IfcWallStandardCase",
                "IfcSlab",  # Floors/ceilings
                "IfcRoof",
                "IfcSpace",  # Rooms
                "IfcColumn",
                "IfcBeam",
                "IfcDoor",
                "IfcWindow",
                "IfcOpeningElement"
            ]
            
            settings = geom.settings()
            # Use world coordinates
            try:
                if hasattr(settings, 'USE_WORLD_COORDS'):
                    settings.set(settings.USE_WORLD_COORDS, True)
            except:
                pass
            
            total_elements = 0
            successful_elements = 0
            
            for element_type in element_types:
                try:
                    elements = self.ifc_file.by_type(element_type)
                    total_elements += len(elements)
                    
                    for element in elements:
                        try:
                            # Create shape from element
                            shape = geom.create_shape(settings, element)
                            if not shape:
                                continue
                            
                            # Get geometry from shape
                            geometry = shape.geometry
                            if not geometry:
                                continue
                            
                            # Convert ifcopenshell geometry to trimesh
                            # Standard ifcopenshell API: geometry.verts and geometry.faces
                            try:
                                vertices = None
                                faces = None
                                
                                # Primary method: Direct access to geometry.verts and geometry.faces
                                # This is the standard ifcopenshell API
                                if hasattr(geometry, 'verts') and hasattr(geometry, 'faces'):
                                    try:
                                        verts = geometry.verts
                                        faces_data = geometry.faces
                                        
                                        # Convert to numpy arrays
                                        vertices = np.array(verts, dtype=np.float64)
                                        # Ensure vertices are in shape (n, 3)
                                        if len(vertices.shape) == 1:
                                            if len(vertices) % 3 == 0:
                                                vertices = vertices.reshape(-1, 3)
                                            else:
                                                logger.debug(f"Invalid vertex count: {len(vertices)} (not divisible by 3)")
                                                continue
                                        elif len(vertices.shape) == 2 and vertices.shape[1] != 3:
                                            logger.debug(f"Invalid vertex shape: {vertices.shape}")
                                            continue
                                        
                                        faces = np.array(faces_data, dtype=np.int32)
                                        # Ensure faces are in shape (n, 3)
                                        if len(faces.shape) == 1:
                                            if len(faces) % 3 == 0:
                                                faces = faces.reshape(-1, 3)
                                            else:
                                                logger.debug(f"Invalid face count: {len(faces)} (not divisible by 3)")
                                                continue
                                        elif len(faces.shape) == 2 and faces.shape[1] != 3:
                                            logger.debug(f"Invalid face shape: {faces.shape}")
                                            continue
                                        
                                        # Validate data
                                        if len(vertices) == 0 or len(faces) == 0:
                                            logger.debug(f"Empty geometry: {len(vertices)} vertices, {len(faces)} faces")
                                            continue
                                        
                                        # Check face indices are valid
                                        if len(faces) > 0:
                                            max_vertex_idx = np.max(faces)
                                            if max_vertex_idx >= len(vertices):
                                                logger.debug(f"Face indices out of range: max index {max_vertex_idx}, but only {len(vertices)} vertices")
                                                continue
                                    except Exception as e:
                                        logger.debug(f"Failed to extract geometry using standard API: {e}")
                                        vertices = None
                                        faces = None
                                
                                # Method 2: Use shape's geometry data directly
                                if vertices is None or faces is None:
                                    try:
                                        # Try accessing shape's geometry data
                                        # ifcopenshell shape has geometry with id() method
                                        if hasattr(shape, 'geometry') and shape.geometry:
                                            geom_obj = shape.geometry
                                            # Try to get tessellation using id
                                            try:
                                                geom_id = geom_obj.id()
                                                # Access tessellation through ifcopenshell
                                                # Note: This may vary by ifcopenshell version
                                                if hasattr(geom_obj, 'tessellation'):
                                                    tess = geom_obj.tessellation()
                                                    if tess and isinstance(tess, tuple) and len(tess) >= 2:
                                                        vertices = np.array(tess[0], dtype=np.float64)
                                                        faces_data = tess[1]
                                                        faces = np.array(faces_data, dtype=np.int32)
                                                        if len(faces.shape) == 1 and len(faces) % 3 == 0:
                                                            faces = faces.reshape(-1, 3)
                                            except:
                                                pass
                                            
                                            # Alternative: try to get data from geometry object attributes
                                            if vertices is None:
                                                # Some versions use different attribute names
                                                for attr_name in ['id', 'data', 'tess', 'tessellation']:
                                                    if hasattr(geom_obj, attr_name):
                                                        try:
                                                            attr_val = getattr(geom_obj, attr_name)
                                                            if callable(attr_val):
                                                                attr_val = attr_val()
                                                            # Try to extract vertices/faces from attribute
                                                            if isinstance(attr_val, tuple) and len(attr_val) >= 2:
                                                                vertices = np.array(attr_val[0], dtype=np.float64)
                                                                faces_data = attr_val[1]
                                                                faces = np.array(faces_data, dtype=np.int32)
                                                                if len(faces.shape) == 1 and len(faces) % 3 == 0:
                                                                    faces = faces.reshape(-1, 3)
                                                                break
                                                        except:
                                                            continue
                                    except Exception as e:
                                        logger.debug(f"Shape geometry method failed: {e}")
                                
                                # Method 3: Try accessing geometry data directly
                                if vertices is None or faces is None:
                                    try:
                                        # Some versions store data differently
                                        if hasattr(geometry, 'data'):
                                            data = geometry.data
                                            if hasattr(data, 'verts') and hasattr(data, 'faces'):
                                                vertices = np.array(data.verts, dtype=np.float64)
                                                faces_data = data.faces
                                                faces = np.array(faces_data, dtype=np.int32)
                                                if len(faces.shape) == 1 and len(faces) % 3 == 0:
                                                    faces = faces.reshape(-1, 3)
                                    except Exception as e:
                                        logger.debug(f"Data access method failed: {e}")
                                
                                # Create mesh if we have valid data
                                if vertices is not None and faces is not None and len(vertices) > 0 and len(faces) > 0:
                                    try:
                                        mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
                                        # Validate the created mesh
                                        if len(mesh.vertices) > 0 and len(mesh.faces) > 0:
                                            meshes.append(mesh)
                                            successful_elements += 1
                                        else:
                                            logger.debug(f"Created mesh is empty: {len(mesh.vertices)} vertices, {len(mesh.faces)} faces")
                                    except Exception as mesh_error:
                                        logger.debug(f"Failed to create trimesh from geometry: {mesh_error}")
                                        continue
                                else:
                                    logger.debug(f"Could not extract valid geometry for {element_type} {element.id()}")
                            except Exception as geom_error:
                                logger.debug(f"Error converting geometry for {element_type} {element.id()}: {geom_error}")
                                continue
                        except Exception as e:
                            logger.debug(f"Error processing {element_type} {element.id()}: {e}")
                            continue
                except Exception as e:
                    logger.debug(f"Error getting {element_type} elements: {e}")
                    continue
            
            logger.info(f"Processed {successful_elements}/{total_elements} elements for mesh generation")
            
            if not meshes:
                logger.warning("No valid meshes generated from IFC geometry")
                logger.warning("This could mean:")
                logger.warning("  - IFC file has no geometry data")
                logger.warning("  - Geometry extraction failed for all elements")
                logger.warning("  - IFC file uses unsupported geometry representation")
                return None
            
            # Combine all meshes into one
            if len(meshes) == 1:
                combined_mesh = meshes[0]
                logger.info(f"Using single mesh: {len(combined_mesh.vertices):,} vertices, {len(combined_mesh.faces):,} faces")
            else:
                logger.info(f"Combining {len(meshes)} meshes into single mesh...")
                try:
                    combined_mesh = trimesh.util.concatenate(meshes)
                    logger.info(f"Successfully combined {len(meshes)} meshes")
                except Exception as e:
                    logger.error(f"Failed to combine meshes: {e}")
                    # Try to use the first mesh as fallback
                    if meshes:
                        logger.warning("Using first mesh as fallback")
                        combined_mesh = meshes[0]
                    else:
                        return None
            
            # Clean up mesh (remove duplicate vertices, etc.)
            try:
                if hasattr(combined_mesh, 'process'):
                    logger.debug("Processing mesh (removing duplicates, etc.)...")
                    combined_mesh.process()
            except Exception as e:
                logger.warning(f"Mesh processing failed (continuing anyway): {e}")
            
            logger.info(f"✓ Mesh generation complete: {len(combined_mesh.vertices):,} vertices, {len(combined_mesh.faces):,} faces")
            logger.info(f"Mesh bounds: {combined_mesh.bounds}")
            return combined_mesh
            
        except Exception as e:
            logger.error(f"Error generating mesh from IFC: {e}", exc_info=True)
            return None

