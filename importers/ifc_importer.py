"""
IFC (Industry Foundation Classes) model importer.
Extracts building information (rooms, windows, properties) from IFC files
using semantic data and relationships, avoiding heavy geometry processing.
"""

from typing import List, Dict, Optional, Tuple
import logging
import ifcopenshell
from ifcopenshell import geom
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
        # AGGRESSIVE: Extract ALL openings as potential windows unless explicitly doors
        logger.info("Checking for IfcOpeningElement (openings that might be windows)...")
        try:
            opening_elements = self.ifc_file.by_type("IfcOpeningElement")
            logger.info(f"Found {len(opening_elements)} IfcOpeningElement(s)")
            
            opening_windows = []
            for opening_elem in opening_elements:
                try:
                    # Check if this opening is already filled by an IfcWindow
                    is_filled_by_window = False
                    if hasattr(opening_elem, 'HasFillings'):
                        for filling_rel in opening_elem.HasFillings:
                            if hasattr(filling_rel, 'RelatedBuildingElement'):
                                if filling_rel.RelatedBuildingElement.is_a("IfcWindow"):
                                    is_filled_by_window = True
                                    break
                    
                    # Only extract if not already filled by a window (to avoid duplicates)
                    if not is_filled_by_window:
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
        
        # Method 2b: Extract windows from glazing panels (IfcPlate)
        # Many IFC files store windows as IfcPlate elements (glazing panels)
        logger.info("Checking for IfcPlate elements (glazing panels that might be windows)...")
        try:
            plates = self.ifc_file.by_type("IfcPlate")
            logger.info(f"Found {len(plates)} IfcPlate element(s)")
            
            plate_windows = []
            for plate in plates:
                try:
                    # Check if plate might be a window (glazing panel)
                    plate_name = plate.Name if hasattr(plate, 'Name') else ""
                    plate_name_lower = plate_name.lower() if plate_name else ""
                    
                    # Check for window-related keywords
                    is_window_like = any(keyword in plate_name_lower for keyword in [
                        'window', 'окно', 'glazing', 'glass', 'fenetre', 'fenster',
                        'pane', 'panel', 'vitrage'
                    ])
                    
                    # Also check material - if it's glass or transparent, likely a window
                    material_props = self._extract_material_properties(plate)
                    is_glass = False
                    if material_props:
                        material_name = material_props.get('name', '').lower() if material_props.get('name') else ''
                        is_glass = any(keyword in material_name for keyword in [
                            'glass', 'glazing', 'verre', 'стекло', 'vitrage'
                        ])
                    
                    # Extract if it looks like a window
                    if is_window_like or is_glass:
                        window = self._extract_window_from_plate(plate)
                        if window:
                            plate_windows.append(window)
                            logger.info(f"Extracted window from plate '{plate_name}' (ID: {plate.id()})")
                except Exception as e:
                    logger.debug(f"Error extracting window from plate {plate.id()}: {e}")
            
            if plate_windows:
                windows.extend(plate_windows)
                logger.info(f"Extracted {len(plate_windows)} window(s) from glazing panels")
        except Exception as e:
            logger.warning(f"Error getting IfcPlate elements: {e}")
        
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
        
        # Method 4: Geometry-based window detection (for elements that look like windows)
        # This catches windows that aren't properly classified in IFC
        logger.info("Performing geometry-based window detection...")
        try:
            # Get all building elements that might be windows
            potential_window_types = [
                "IfcPlate",  # Glazing panels
                "IfcMember",  # Window frames (sometimes windows are just frames)
                "IfcBuildingElementProxy"  # Generic elements that might be windows
            ]
            
            geometry_windows = []
            for elem_type in potential_window_types:
                try:
                    elements = self.ifc_file.by_type(elem_type)
                    for elem in elements:
                        try:
                            # Check if element looks like a window based on geometry
                            if self._is_window_like_geometry(elem):
                                window = self._extract_window_from_geometry(elem)
                                if window:
                                    geometry_windows.append(window)
                                    logger.info(f"Detected window from {elem_type} {elem.id()} using geometry analysis")
                        except Exception as e:
                            logger.debug(f"Error checking {elem_type} {elem.id()} for window geometry: {e}")
                except Exception as e:
                    logger.debug(f"Error getting {elem_type} elements: {e}")
            
            if geometry_windows:
                windows.extend(geometry_windows)
                logger.info(f"Extracted {len(geometry_windows)} window(s) using geometry-based detection")
        except Exception as e:
            logger.warning(f"Error in geometry-based window detection: {e}")
        
        # Remove duplicates based on position and size
        windows = self._remove_duplicate_windows(windows)
        
        logger.info(f"Successfully extracted {len(windows)} window(s) total (after deduplication)")
        return windows
    
    def _is_window_like_geometry(self, element) -> bool:
        """
        Check if an element has window-like geometry characteristics.
        Windows are typically:
        - Flat (thin in one dimension)
        - Reasonable size (0.3m - 5m width, 0.3m - 4m height)
        - Positioned on building facade
        
        Args:
            element: IFC element to check
        
        Returns:
            True if element looks like a window based on geometry
        """
        try:
            # Try to extract geometry
            try:
                center, normal, size = self._extract_window_geometry(element)
            except:
                return False
            
            width, height = size
            
            # Check size constraints (reasonable window dimensions)
            min_size = 0.3  # 30cm minimum
            max_width = 5.0  # 5m maximum width
            max_height = 4.0  # 4m maximum height
            
            if width < min_size or height < min_size:
                return False
            if width > max_width or height > max_height:
                return False
            
            # Check if element has transparent/glass material (strong indicator)
            material_props = self._extract_material_properties(element)
            if material_props:
                material_name = material_props.get('name', '').lower() if material_props.get('name') else ''
                if any(keyword in material_name for keyword in ['glass', 'glazing', 'verre', 'стекло']):
                    return True
            
            # Check name for window-related keywords
            element_name = element.Name if hasattr(element, 'Name') else ''
            if element_name:
                name_lower = element_name.lower()
                if any(keyword in name_lower for keyword in ['window', 'окно', 'glazing', 'glass', 'pane']):
                    return True
            
            # If size is reasonable and in typical window range, consider it
            # Windows are typically 0.5m - 2m wide and 0.5m - 2m high
            if 0.5 <= width <= 2.5 and 0.5 <= height <= 2.5:
                return True
            
            return False
        except Exception as e:
            logger.debug(f"Error checking if element {element.id()} is window-like: {e}")
            return False
    
    def _extract_window_from_geometry(self, element) -> Optional[Window]:
        """
        Extract window from element using geometry analysis.
        
        Args:
            element: IFC element that looks like a window
        
        Returns:
            Window object or None if extraction fails
        """
        try:
            element_id = element.GlobalId if hasattr(element, 'GlobalId') else str(element.id())
            element_name = element.Name if hasattr(element, 'Name') else f"Element_{element_id}"
            element_type = element.is_a()
            
            logger.info(f"Extracting window from {element_type} {element_id}: {element_name}")
            
            # Extract geometry
            try:
                center, normal, size = self._extract_window_geometry(element)
            except Exception as e:
                logger.warning(f"Failed to extract geometry from {element_type} {element_id}: {e}")
                return None
            
            # Extract properties
            properties = self._extract_properties(element)
            
            # Extract material properties
            try:
                material_props = self._extract_material_properties(element)
                if material_props:
                    properties['material'] = material_props
            except Exception as e:
                logger.debug(f"Error extracting material properties: {e}")
            
            # Extract color/style
            try:
                color_style = self._extract_color_and_style(element)
                if color_style:
                    properties['color_style'] = color_style
            except Exception as e:
                logger.debug(f"Error extracting color/style: {e}")
            
            # Set window properties
            window_props = {
                'window_type': 'double_glazed',  # Default
                'glass_thickness': 6.0,
                'transmittance': 0.75,
                'frame_factor': 0.70,
                'source': element_type  # Mark source element type
            }
            window_props.update(properties)
            
            window = Window(
                id=f"{element_type}_{element_id}",
                center=center,
                normal=normal,
                size=size,
                window_type=window_props.get('window_type'),
                glass_thickness=window_props.get('glass_thickness', 6.0),
                transmittance=window_props.get('transmittance', 0.75),
                frame_factor=window_props.get('frame_factor', 0.70),
                properties=window_props
            )
            
            return window
            
        except Exception as e:
            logger.error(f"Error extracting window from geometry: {e}", exc_info=True)
            return None
    
    def _remove_duplicate_windows(self, windows: List[Window]) -> List[Window]:
        """
        Remove duplicate windows based on position and size.
        Windows are considered duplicates if they're very close (within 0.5m) and have similar size.
        
        Args:
            windows: List of Window objects
        
        Returns:
            List of unique Window objects
        """
        if len(windows) <= 1:
            return windows
        
        unique_windows = []
        for window in windows:
            is_duplicate = False
            for existing in unique_windows:
                # Check if windows are very close (within 0.5m)
                distance = np.sqrt(
                    sum((a - b) ** 2 for a, b in zip(window.center, existing.center))
                )
                
                # Check if sizes are similar (within 10%)
                size_diff = abs(window.size[0] - existing.size[0]) + abs(window.size[1] - existing.size[1])
                size_avg = (window.size[0] + window.size[1] + existing.size[0] + existing.size[1]) / 4
                
                if distance < 0.5 and size_diff < size_avg * 0.1:
                    is_duplicate = True
                    logger.debug(f"Removed duplicate window {window.id} (close to {existing.id})")
                    break
            
            if not is_duplicate:
                unique_windows.append(window)
        
        if len(unique_windows) < len(windows):
            logger.info(f"Removed {len(windows) - len(unique_windows)} duplicate window(s)")
        
        return unique_windows
    
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
            
            # Extract material properties (comprehensive extraction)
            try:
                material_props = self._extract_material_properties(window_elem)
                if material_props:
                    all_properties['material'] = material_props
                    # Log material information
                    material_name = material_props.get('name', 'Unknown')
                    material_type = material_props.get('type', 'Unknown')
                    logger.info(f"Window {window_id}: Found material '{material_name}' (type: {material_type})")
                    
                    # If material has color, use it for color extraction
                    if 'color_style' in material_props and 'color' in material_props['color_style']:
                        logger.info(f"Window {window_id}: Material has color information")
                else:
                    logger.debug(f"Window {window_id}: No material found")
            except Exception as e:
                logger.warning(f"Error extracting material properties for window {window_id}: {e}", exc_info=True)
            
            # Extract color and style information
            try:
                color_style = self._extract_color_and_style(window_elem)
                if color_style:
                    all_properties['color_style'] = color_style
                    logger.debug(f"Window {window_id}: extracted color/style - {color_style.get('style_type', 'unknown')}")
            except Exception as e:
                logger.debug(f"Error extracting color/style for window {window_id}: {e}")
            
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
            
            # AGGRESSIVE: Check if this opening is a door (exclude doors, include everything else as windows)
            # Default to treating as window unless explicitly marked as door
            is_door = False
            
            # Check name for door keywords
            if opening_name:
                name_lower = opening_name.lower()
                if any(keyword in name_lower for keyword in ['door', 'дверь', 'porte', 'tür', 'entrance', 'вход']):
                    is_door = True
            
            # Check properties for door indication
            properties = self._extract_properties(opening_elem)
            if 'Door' in str(properties) or 'door' in str(properties).lower():
                is_door = True
            
            # Check if opening is filled by a door
            if hasattr(opening_elem, 'HasFillings'):
                for filling_rel in opening_elem.HasFillings:
                    if hasattr(filling_rel, 'RelatedBuildingElement'):
                        elem = filling_rel.RelatedBuildingElement
                        if elem.is_a("IfcDoor"):
                            is_door = True
                            break
            
            # Exclude only if explicitly a door
            if is_door:
                logger.debug(f"Opening {opening_id} is a door, skipping")
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
    
    def _extract_window_from_plate(self, plate_elem) -> Optional[Window]:
        """
        Extract window from IfcPlate element (glazing panel).
        Many IFC files store windows as glazing panels instead of IfcWindow.
        
        Args:
            plate_elem: IFC IfcPlate element (glazing panel)
            
        Returns:
            Window object or None if extraction fails
        """
        try:
            plate_id = plate_elem.GlobalId if hasattr(plate_elem, 'GlobalId') else str(plate_elem.id())
            plate_name = plate_elem.Name if hasattr(plate_elem, 'Name') else f"Plate_{plate_id}"
            logger.info(f"Extracting window from glazing panel {plate_id}: {plate_name}")
            
            # Extract geometry
            try:
                center, normal, size = self._extract_window_geometry(plate_elem)
            except Exception as e:
                logger.warning(f"Failed to extract geometry from plate {plate_id}: {e}")
                # Use defaults
                center = (0.0, 0.0, 1.5)
                normal = (0.0, 1.0, 0.0)
                size = (1.5, 1.2)
            
            # Extract properties
            properties = self._extract_properties(plate_elem)
            
            # Extract material properties (important for glazing panels)
            try:
                material_props = self._extract_material_properties(plate_elem)
                if material_props:
                    properties['material'] = material_props
            except Exception as e:
                logger.debug(f"Error extracting material properties for plate {plate_id}: {e}")
            
            # Extract color/style
            try:
                color_style = self._extract_color_and_style(plate_elem)
                if color_style:
                    properties['color_style'] = color_style
            except Exception as e:
                logger.debug(f"Error extracting color/style for plate {plate_id}: {e}")
            
            # Set window properties (glazing panels are typically double-glazed)
            window_props = {
                'window_type': 'double_glazed',
                'glass_thickness': 6.0,
                'transmittance': 0.75,
                'frame_factor': 0.70,
                'source': 'IfcPlate'  # Mark as extracted from plate
            }
            window_props.update(properties)
            
            window = Window(
                id=f"Plate_{plate_id}",
                center=center,
                normal=normal,
                size=size,
                window_type=window_props.get('window_type'),
                glass_thickness=window_props.get('glass_thickness', 6.0),
                transmittance=window_props.get('transmittance', 0.75),
                frame_factor=window_props.get('frame_factor', 0.70),
                properties=window_props
            )
            
            logger.debug(f"Successfully extracted window from glazing panel {plate_id}")
            return window
            
        except Exception as e:
            logger.error(f"Error extracting window from plate {plate_elem.id()}: {e}", exc_info=True)
            return None
    
    def _extract_windows_from_walls(self) -> List[Window]:
        """
        Extract windows from walls by finding openings.
        AGGRESSIVE: Extracts ALL openings from walls as potential windows.
        Checks IfcWall elements for openings that might be windows.
        
        Returns:
            List of Window objects
        """
        windows = []
        processed_openings = set()  # Track processed openings to avoid duplicates
        
        try:
            # Get all walls
            walls = self.ifc_file.by_type("IfcWall") + self.ifc_file.by_type("IfcWallStandardCase")
            logger.info(f"Found {len(walls)} wall element(s)")
            
            # Check each wall for openings
            for wall in walls:
                try:
                    # Check if wall has openings
                    if hasattr(wall, 'HasOpenings') and wall.HasOpenings:
                        for rel_opening in wall.HasOpenings:
                            if hasattr(rel_opening, 'RelatedOpeningElement'):
                                opening = rel_opening.RelatedOpeningElement
                                if opening and opening.is_a("IfcOpeningElement"):
                                    opening_id = opening.id()
                                    
                                    # Skip if already processed
                                    if opening_id in processed_openings:
                                        continue
                                    processed_openings.add(opening_id)
                                    
                                    # Extract window from opening (aggressive - treats all as windows unless doors)
                                    window = self._extract_window_from_opening(opening)
                                    if window:
                                        windows.append(window)
                                        logger.info(f"Extracted window from wall opening {opening_id}")
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
        Extract material properties from IFC element comprehensively.
        Uses IfcRelAssociatesMaterial relationship and checks multiple sources.
        
        For windows specifically, also checks:
        - Window type materials
        - Window part materials (panes, frames)
        - Material constituent sets
        
        Returns:
            Dictionary with material properties (name, type, thermal properties, etc.)
        """
        material_props = {}
        all_materials = []  # Store all materials found (not just first)
        
        try:
            # Method 1: Get material association directly from element
            if hasattr(element, 'HasAssociations'):
                for assoc in element.HasAssociations:
                    if assoc.is_a("IfcRelAssociatesMaterial"):
                        material_select = assoc.RelatingMaterial
                        material_info = self._extract_single_material(material_select)
                        if material_info:
                            all_materials.append(material_info)
                            # Use first material as primary
                            if not material_props:
                                material_props = material_info
            
            # Method 2: For windows, check window type for materials
            if element.is_a("IfcWindow") and not material_props:
                if hasattr(element, 'IsTypedBy') and element.IsTypedBy:
                    for type_rel in element.IsTypedBy:
                        if hasattr(type_rel, 'RelatingType') and type_rel.RelatingType:
                            window_type = type_rel.RelatingType
                            # Extract materials from window type
                            if hasattr(window_type, 'HasAssociations'):
                                for assoc in window_type.HasAssociations:
                                    if assoc.is_a("IfcRelAssociatesMaterial"):
                                        material_select = assoc.RelatingMaterial
                                        material_info = self._extract_single_material(material_select)
                                        if material_info:
                                            all_materials.append(material_info)
                                            if not material_props:
                                                material_props = material_info
                                                logger.debug(f"Found material for window {element.id()} via window type")
            
            # Method 3: Check for material constituent sets (different materials for different parts)
            if hasattr(element, 'HasAssociations'):
                for assoc in element.HasAssociations:
                    if assoc.is_a("IfcRelAssociatesMaterial"):
                        material_select = assoc.RelatingMaterial
                        if material_select.is_a("IfcMaterialConstituentSet"):
                            # Material constituent set - different materials for different parts
                            constituents = []
                            if hasattr(material_select, 'MaterialConstituents'):
                                for constituent in material_select.MaterialConstituents:
                                    if hasattr(constituent, 'Material') and constituent.Material:
                                        mat = constituent.Material
                                        mat_info = {
                                            'name': mat.Name if hasattr(mat, 'Name') else None,
                                            'category': constituent.Category if hasattr(constituent, 'Category') else None
                                        }
                                        constituents.append(mat_info)
                            if constituents:
                                material_props['constituents'] = constituents
                                material_props['type'] = 'IfcMaterialConstituentSet'
                                logger.debug(f"Found material constituent set for element {element.id()}")
            
            # Store all materials if multiple found
            if len(all_materials) > 1:
                material_props['all_materials'] = all_materials
                logger.debug(f"Found {len(all_materials)} material(s) for element {element.id()}")
        
        except Exception as e:
            logger.debug(f"Error extracting material properties for element {element.id()}: {e}", exc_info=True)
        
        return material_props
    
    def _extract_single_material(self, material_select) -> Dict:
        """
        Extract properties from a single material entity.
        
        Args:
            material_select: IFC material entity (IfcMaterial, IfcMaterialList, etc.)
        
        Returns:
            Dictionary with material properties
        """
        material_props = {}
        
        try:
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
                    mat_info = {}
                    if hasattr(mat, 'Name'):
                        mat_info['name'] = mat.Name
                    # Extract properties from each material in list
                    if hasattr(mat, 'HasProperties'):
                        mat_info['properties'] = {}
                        for prop in mat.HasProperties:
                            if hasattr(prop, 'Name') and hasattr(prop, 'NominalValue'):
                                prop_name = prop.Name
                                prop_value = prop.NominalValue
                                if prop_value and hasattr(prop_value, 'wrappedValue'):
                                    mat_info['properties'][prop_name] = prop_value.wrappedValue
                    materials.append(mat_info)
                material_props['materials'] = materials
                material_props['type'] = 'IfcMaterialList'
            
            elif material_select.is_a("IfcMaterialLayerSet"):
                # Layered material
                layers = []
                for layer in material_select.MaterialLayers:
                    layer_info = {}
                    if hasattr(layer, 'Material') and layer.Material:
                        mat = layer.Material
                        if hasattr(mat, 'Name'):
                            layer_info['name'] = mat.Name
                        # Extract properties from layer material
                        if hasattr(mat, 'HasProperties'):
                            layer_info['properties'] = {}
                            for prop in mat.HasProperties:
                                if hasattr(prop, 'Name') and hasattr(prop, 'NominalValue'):
                                    prop_name = prop.Name
                                    prop_value = prop.NominalValue
                                    if prop_value and hasattr(prop_value, 'wrappedValue'):
                                        layer_info['properties'][prop_name] = prop_value.wrappedValue
                    if hasattr(layer, 'LayerThickness'):
                        layer_info['thickness'] = float(layer.LayerThickness)
                    if hasattr(layer, 'Category'):
                        layer_info['category'] = layer.Category
                    layers.append(layer_info)
                material_props['layers'] = layers
                material_props['type'] = 'IfcMaterialLayerSet'
            
            elif material_select.is_a("IfcMaterialProfileSet"):
                # Profile-based material (for frames, etc.)
                profiles = []
                if hasattr(material_select, 'MaterialProfiles'):
                    for profile in material_select.MaterialProfiles:
                        profile_info = {}
                        if hasattr(profile, 'Material') and profile.Material:
                            mat = profile.Material
                            if hasattr(mat, 'Name'):
                                profile_info['name'] = mat.Name
                        if hasattr(profile, 'Category'):
                            profile_info['category'] = profile.Category
                        profiles.append(profile_info)
                material_props['profiles'] = profiles
                material_props['type'] = 'IfcMaterialProfileSet'
            
            # Try to extract color/style from material representation
            try:
                color_style = self._extract_color_from_material(material_select)
                if color_style:
                    material_props['color_style'] = color_style
            except Exception as e:
                logger.debug(f"Error extracting color/style from material: {e}")
        
        except Exception as e:
            logger.debug(f"Error extracting single material: {e}")
        
        return material_props
    
    def _extract_color_and_style(self, element) -> Dict:
        """
        Extract color and style information from IFC element.
        Comprehensive extraction using 9 different methods (in priority order):
        
        1. IfcStyledItem relationships (standard IFC way - most common)
        2. IfcPresentationStyleAssignment (older IFC versions)
        3. Material-based styles (through material associations)
        4. Type-based color extraction (elements inherit from their type)
        5. IfcMappedItem resolution (mapped representations)
        6. Global IfcStyledItem search (styles stored separately)
        7. Direct style associations (fallback)
        8. Material properties color extraction
        9. ifcopenshell style API (if available)
        
        This comprehensive approach ensures colors are found even if stored in
        non-standard ways or in different parts of the IFC hierarchy.
        
        Returns:
            Dictionary with color and style information:
            - color: (R, G, B) tuple (0.0-1.0 range)
            - transparency: float (0.0-1.0)
            - reflectance_method: str
            - diffuse_color: (R, G, B) tuple
            - specular_color: (R, G, B) tuple
            - style_type: str (e.g., 'IfcSurfaceStyleShading', 'IfcSurfaceStyleRendering')
            - textures: list of texture information
        """
        style_info = {}
        
        try:
            # Method 1: IfcStyledItem relationships (proper IFC way - most common)
            # This is the standard way IFC stores style information
            if hasattr(element, 'Representation') and element.Representation:
                for representation in element.Representation.Representations:
                    if hasattr(representation, 'Items'):
                        for item in representation.Items:
                            # Check for IfcStyledItem (newer IFC versions use this)
                            if hasattr(item, 'StyledByItem') and item.StyledByItem:
                                for styled_item in item.StyledByItem:
                                    if hasattr(styled_item, 'Styles') and styled_item.Styles:
                                        for style_assignment in styled_item.Styles:
                                            color = self._extract_color_from_style(style_assignment)
                                            if color:
                                                style_info.update(color)
                                                logger.debug(f"Found color via IfcStyledItem for element {element.id()}")
                                                break
                                    if style_info:
                                        break
                            
                            # Check for HasStyledItem (alternative relationship name)
                            if not style_info and hasattr(item, 'HasStyledItem') and item.HasStyledItem:
                                for styled_item in item.HasStyledItem:
                                    if hasattr(styled_item, 'Styles') and styled_item.Styles:
                                        for style_assignment in styled_item.Styles:
                                            color = self._extract_color_from_style(style_assignment)
                                            if color:
                                                style_info.update(color)
                                                logger.debug(f"Found color via HasStyledItem for element {element.id()}")
                                                break
                                    if style_info:
                                        break
                            
                            if style_info:
                                break
                    if style_info:
                        break
            
            # Method 2: IfcPresentationStyleAssignment (older IFC versions)
            if not style_info and hasattr(element, 'HasAssociations'):
                for assoc in element.HasAssociations:
                    if assoc.is_a("IfcRelAssociates"):
                        # Check if it's a style association
                        if hasattr(assoc, 'RelatedObjects') and element in assoc.RelatedObjects:
                            if hasattr(assoc, 'RelatingStyle') and assoc.RelatingStyle:
                                color = self._extract_color_from_style(assoc.RelatingStyle)
                                if color:
                                    style_info.update(color)
                                    logger.debug(f"Found color via IfcRelAssociates for element {element.id()}")
                                    break
            
            # Method 3: Material-based styles (through material associations)
            if not style_info and hasattr(element, 'HasAssociations'):
                for assoc in element.HasAssociations:
                    if assoc.is_a("IfcRelAssociatesMaterial"):
                        material_select = assoc.RelatingMaterial
                        
                        # Check if material has representation with styles
                        if hasattr(material_select, 'HasRepresentation'):
                            for material_rep in material_select.HasRepresentation:
                                if hasattr(material_rep, 'Representations'):
                                    for rep in material_rep.Representations:
                                        if hasattr(rep, 'Items'):
                                            for item in rep.Items:
                                                # Check for styled items in material representation
                                                if hasattr(item, 'StyledByItem') and item.StyledByItem:
                                                    for styled_item in item.StyledByItem:
                                                        if hasattr(styled_item, 'Styles') and styled_item.Styles:
                                                            for style_assignment in styled_item.Styles:
                                                                color = self._extract_color_from_style(style_assignment)
                                                                if color:
                                                                    style_info.update(color)
                                                                    logger.debug(f"Found color via material representation for element {element.id()}")
                                                                    break
                                                        if style_info:
                                                            break
                                                if style_info:
                                                    break
                                        if style_info:
                                            break
                                if style_info:
                                    break
                        if style_info:
                            break
            
            # Method 4: Type-based color extraction (elements inherit from their type)
            if not style_info:
                # Check if element has a type that might have colors
                if hasattr(element, 'IsTypedBy') and element.IsTypedBy:
                    for type_rel in element.IsTypedBy:
                        if hasattr(type_rel, 'RelatingType') and type_rel.RelatingType:
                            type_obj = type_rel.RelatingType
                            # Extract color from type's representation
                            type_color = self._extract_color_and_style(type_obj)
                            if type_color and 'color' in type_color:
                                style_info.update(type_color)
                                logger.debug(f"Found color via type definition for element {element.id()}")
                                break
            
            # Method 5: IfcMappedItem - resolve mapped representations
            if not style_info and hasattr(element, 'Representation') and element.Representation:
                for representation in element.Representation.Representations:
                    if hasattr(representation, 'Items'):
                        for item in representation.Items:
                            # Check if item is a mapped item (references shared geometry)
                            if item.is_a("IfcMappedItem"):
                                if hasattr(item, 'MappingSource') and item.MappingSource:
                                    mapping_source = item.MappingSource
                                    if hasattr(mapping_source, 'MappedRepresentation') and mapping_source.MappedRepresentation:
                                        mapped_rep = mapping_source.MappedRepresentation
                                        # Extract colors from mapped representation
                                        if hasattr(mapped_rep, 'Items'):
                                            for mapped_item in mapped_rep.Items:
                                                if hasattr(mapped_item, 'StyledByItem') and mapped_item.StyledByItem:
                                                    for styled_item in mapped_item.StyledByItem:
                                                        if hasattr(styled_item, 'Styles') and styled_item.Styles:
                                                            for style_assignment in styled_item.Styles:
                                                                color = self._extract_color_from_style(style_assignment)
                                                                if color:
                                                                    style_info.update(color)
                                                                    logger.debug(f"Found color via IfcMappedItem for element {element.id()}")
                                                                    break
                                                        if style_info:
                                                            break
                                                if style_info:
                                                    break
                                    if style_info:
                                        break
                            if style_info:
                                break
                    if style_info:
                        break
            
            # Method 6: Check all IfcStyledItem relationships globally (some IFC files store styles separately)
            if not style_info:
                try:
                    # Get all IfcStyledItem entities and check if they reference this element
                    all_styled_items = self.ifc_file.by_type("IfcStyledItem")
                    for styled_item in all_styled_items:
                        # Check if styled item references this element's representation items
                        if hasattr(styled_item, 'Item') and styled_item.Item:
                            item = styled_item.Item
                            # Check if this item belongs to our element's representation
                            if hasattr(element, 'Representation') and element.Representation:
                                for representation in element.Representation.Representations:
                                    if hasattr(representation, 'Items') and item in representation.Items:
                                        if hasattr(styled_item, 'Styles') and styled_item.Styles:
                                            for style_assignment in styled_item.Styles:
                                                color = self._extract_color_from_style(style_assignment)
                                                if color:
                                                    style_info.update(color)
                                                    logger.debug(f"Found color via global IfcStyledItem search for element {element.id()}")
                                                    break
                                        if style_info:
                                            break
                                if style_info:
                                    break
                except Exception as e:
                    logger.debug(f"Error in global IfcStyledItem search: {e}")
            
            # Method 7: Direct style extraction from element (fallback)
            if not style_info:
                # Try to get styles directly from element if it has them
                if hasattr(element, 'HasAssociations'):
                    for assoc in element.HasAssociations:
                        # Check for any style-related associations
                        if hasattr(assoc, 'RelatingStyle'):
                            color = self._extract_color_from_style(assoc.RelatingStyle)
                            if color:
                                style_info.update(color)
                                logger.debug(f"Found color via direct style association for element {element.id()}")
                                break
            
            # Method 8: Check material properties for color information
            if not style_info:
                try:
                    material_props = self._extract_material_properties(element)
                    if material_props and 'color_style' in material_props:
                        color_style = material_props['color_style']
                        if color_style and 'color' in color_style:
                            style_info.update(color_style)
                            logger.debug(f"Found color via material properties for element {element.id()}")
                except Exception as e:
                    logger.debug(f"Error extracting color from material properties: {e}")
            
            # Method 9: Use ifcopenshell's style API directly (if available)
            if not style_info:
                try:
                    # Try to use ifcopenshell's style API
                    import ifcopenshell.api.style
                    # Get all styled items for this element
                    if hasattr(element, 'Representation') and element.Representation:
                        for representation in element.Representation.Representations:
                            if hasattr(representation, 'Items'):
                                for item in representation.Items:
                                    # Try to get surface style using ifcopenshell API
                                    try:
                                        # Some ifcopenshell versions have get_surface_style function
                                        if hasattr(ifcopenshell.api.style, 'get_surface_style'):
                                            surface_style = ifcopenshell.api.style.get_surface_style(self.ifc_file, item)
                                            if surface_style:
                                                color = self._extract_color_from_style(surface_style)
                                                if color:
                                                    style_info.update(color)
                                                    logger.debug(f"Found color via ifcopenshell style API for element {element.id()}")
                                                    break
                                    except Exception as e:
                                        logger.debug(f"ifcopenshell style API not available or failed: {e}")
                                    if style_info:
                                        break
                            if style_info:
                                break
                except ImportError:
                    logger.debug("ifcopenshell.api.style not available")
                except Exception as e:
                    logger.debug(f"Error using ifcopenshell style API: {e}")
        
        except Exception as e:
            logger.debug(f"Error extracting color/style for element {element.id()}: {e}", exc_info=True)
        
        return style_info
    
    def _extract_window_specific_color(self, window_elem) -> Dict:
        """
        Extract color specifically for windows using 6 window-specific methods.
        
        Windows in IFC files often have colors stored in non-standard locations:
        1. Window type definitions (IfcWindowType) - most common
        2. Opening elements that contain the window
        3. Window panes/panels (IfcPlate for glazing)
        4. Window frames (IfcMember)
        5. Wall that contains the window opening
        6. Material associations specific to windows
        
        This method is called AFTER standard color extraction fails, providing
        additional window-specific fallback methods.
        
        Args:
            window_elem: IFC window element (IfcWindow)
        
        Returns:
            Dictionary with color/style information, or empty dict if not found
        """
        style_info = {}
        
        try:
            # Method 1: Check window type for colors (windows often inherit from type)
            if hasattr(window_elem, 'IsTypedBy') and window_elem.IsTypedBy:
                for type_rel in window_elem.IsTypedBy:
                    if hasattr(type_rel, 'RelatingType') and type_rel.RelatingType:
                        window_type = type_rel.RelatingType
                        # Extract color from window type
                        type_color = self._extract_color_and_style(window_type)
                        if type_color and 'color' in type_color:
                            style_info.update(type_color)
                            logger.debug(f"Found window color via window type for {window_elem.id()}")
                            return style_info
            
            # Method 2: Check opening element that contains this window
            # Windows are often placed in openings, and the opening might have the color
            try:
                # Find opening that contains this window
                openings = self.ifc_file.by_type("IfcOpeningElement")
                for opening in openings:
                    # Check if window fills this opening
                    if hasattr(opening, 'HasFillings'):
                        for filling_rel in opening.HasFillings:
                            if hasattr(filling_rel, 'RelatedBuildingElement'):
                                if filling_rel.RelatedBuildingElement == window_elem:
                                    # Extract color from opening
                                    opening_color = self._extract_color_and_style(opening)
                                    if opening_color and 'color' in opening_color:
                                        style_info.update(opening_color)
                                        logger.debug(f"Found window color via opening element for {window_elem.id()}")
                                        return style_info
            except Exception as e:
                logger.debug(f"Error checking opening elements for window {window_elem.id()}: {e}")
            
            # Method 3: Check for window panes/panels (IfcPlate - glazing)
            # Windows often have glazing panels with their own colors
            try:
                # Check if window has parts (panes, frames, etc.)
                if hasattr(window_elem, 'IsDecomposedBy') and window_elem.IsDecomposedBy:
                    for decomp_rel in window_elem.IsDecomposedBy:
                        if hasattr(decomp_rel, 'RelatedObjects'):
                            for part in decomp_rel.RelatedObjects:
                                # Check for glazing panels (IfcPlate)
                                if part.is_a("IfcPlate") or part.is_a("IfcMember"):
                                    part_color = self._extract_color_and_style(part)
                                    if part_color and 'color' in part_color:
                                        style_info.update(part_color)
                                        logger.debug(f"Found window color via window part ({part.is_a()}) for {window_elem.id()}")
                                        return style_info
            except Exception as e:
                logger.debug(f"Error checking window parts for {window_elem.id()}: {e}")
            
            # Method 4: Check for window in wall (wall opening might have color)
            try:
                # Find walls that have openings containing this window
                walls = self.ifc_file.by_type("IfcWall") + self.ifc_file.by_type("IfcWallStandardCase")
                for wall in walls:
                    if hasattr(wall, 'HasOpenings'):
                        for opening_rel in wall.HasOpenings:
                            if hasattr(opening_rel, 'RelatedOpeningElement'):
                                opening = opening_rel.RelatedOpeningElement
                                if opening and opening.is_a("IfcOpeningElement"):
                                    # Check if this opening is filled by our window
                                    if hasattr(opening, 'HasFillings'):
                                        for filling_rel in opening.HasFillings:
                                            if hasattr(filling_rel, 'RelatedBuildingElement'):
                                                if filling_rel.RelatedBuildingElement == window_elem:
                                                    # Try to get color from opening first (more specific)
                                                    opening_color = self._extract_color_and_style(opening)
                                                    if opening_color and 'color' in opening_color:
                                                        style_info.update(opening_color)
                                                        logger.debug(f"Found window color via opening element for {window_elem.id()}")
                                                        return style_info
                                                    
                                                    # Try to get color from wall (some IFC files assign window color via wall)
                                                    wall_color = self._extract_color_and_style(wall)
                                                    if wall_color and 'color' in wall_color:
                                                        # Use wall color as fallback, but prefer window-specific
                                                        if not style_info:
                                                            style_info.update(wall_color)
                                                            logger.debug(f"Found window color via wall for {window_elem.id()}")
            except Exception as e:
                logger.debug(f"Error checking wall openings for window {window_elem.id()}: {e}")
            
            # Method 5: Check all IfcPlate elements (glazing panels) and see if they're related to this window
            try:
                # Check using IfcRelContainedInSpatialStructure relationship
                contained_rels = self.ifc_file.by_type("IfcRelContainedInSpatialStructure")
                for rel in contained_rels:
                    if hasattr(rel, 'RelatingStructure') and rel.RelatingStructure == window_elem:
                        if hasattr(rel, 'RelatedElements'):
                            for elem in rel.RelatedElements:
                                # Check if it's a plate (glazing) or member (frame)
                                if elem.is_a("IfcPlate") or elem.is_a("IfcMember"):
                                    elem_color = self._extract_color_and_style(elem)
                                    if elem_color and 'color' in elem_color:
                                        style_info.update(elem_color)
                                        logger.debug(f"Found window color via contained element ({elem.is_a()}) for {window_elem.id()}")
                                        return style_info
                
                # Also check plates that might be spatially near the window
                plates = self.ifc_file.by_type("IfcPlate")
                for plate in plates:
                    # Check if plate is in same space/storey as window (might be window glazing)
                    plate_color = self._extract_color_and_style(plate)
                    if plate_color and 'color' in plate_color:
                        # If we don't have a color yet, use plate color as potential match
                        if not style_info:
                            style_info.update(plate_color)
                            logger.debug(f"Using glazing plate color as potential window color for {window_elem.id()}")
            except Exception as e:
                logger.debug(f"Error checking glazing plates for window {window_elem.id()}: {e}")
            
            # Method 6: Check window's material more thoroughly
            try:
                # First check direct material associations
                if hasattr(window_elem, 'HasAssociations'):
                    for assoc in window_elem.HasAssociations:
                        if assoc.is_a("IfcRelAssociatesMaterial"):
                            material_select = assoc.RelatingMaterial
                            # Try to extract color from material more thoroughly
                            material_color = self._extract_color_from_material(material_select)
                            if material_color and 'color' in material_color:
                                style_info.update(material_color)
                                logger.debug(f"Found window color via material association for {window_elem.id()}")
                                return style_info
                            
                            # Check if material has color_style in properties
                            material_props = self._extract_single_material(material_select)
                            if material_props and 'color_style' in material_props:
                                color_style = material_props['color_style']
                                if color_style and 'color' in color_style:
                                    style_info.update(color_style)
                                    logger.debug(f"Found window color via material properties for {window_elem.id()}")
                                    return style_info
                
                # Also check window type materials
                if hasattr(window_elem, 'IsTypedBy') and window_elem.IsTypedBy:
                    for type_rel in window_elem.IsTypedBy:
                        if hasattr(type_rel, 'RelatingType') and type_rel.RelatingType:
                            window_type = type_rel.RelatingType
                            if hasattr(window_type, 'HasAssociations'):
                                for assoc in window_type.HasAssociations:
                                    if assoc.is_a("IfcRelAssociatesMaterial"):
                                        material_select = assoc.RelatingMaterial
                                        material_color = self._extract_color_from_material(material_select)
                                        if material_color and 'color' in material_color:
                                            style_info.update(material_color)
                                            logger.debug(f"Found window color via window type material for {window_elem.id()}")
                                            return style_info
            except Exception as e:
                logger.debug(f"Error checking window material associations for {window_elem.id()}: {e}")
            
            # Method 7: Check window parts (panes, frames) for materials
            try:
                # Check for decomposed window parts
                if hasattr(window_elem, 'IsDecomposedBy') and window_elem.IsDecomposedBy:
                    for decomp_rel in window_elem.IsDecomposedBy:
                        if hasattr(decomp_rel, 'RelatedObjects'):
                            for part in decomp_rel.RelatedObjects:
                                # Extract material from window part
                                part_material = self._extract_material_properties(part)
                                if part_material and 'color_style' in part_material:
                                    color_style = part_material['color_style']
                                    if color_style and 'color' in color_style:
                                        style_info.update(color_style)
                                        logger.debug(f"Found window color via window part material ({part.is_a()}) for {window_elem.id()}")
                                        return style_info
            except Exception as e:
                logger.debug(f"Error checking window parts for materials: {e}")
        
        except Exception as e:
            logger.debug(f"Error in window-specific color extraction for {window_elem.id()}: {e}", exc_info=True)
        
        return style_info
    
    def _extract_color_from_material(self, material_select) -> Dict:
        """
        Extract color and style information from IFC material.
        Materials can have representation with styles attached.
        
        Args:
            material_select: IFC material (IfcMaterial, IfcMaterialList, etc.)
        
        Returns:
            Dictionary with color/style information
        """
        style_info = {}
        
        try:
            # Check if material has representation with styles
            if hasattr(material_select, 'HasRepresentation'):
                for material_rep in material_select.HasRepresentation:
                    if hasattr(material_rep, 'Representations'):
                        for rep in material_rep.Representations:
                            if hasattr(rep, 'Items'):
                                for item in rep.Items:
                                    if hasattr(item, 'Styles') and item.Styles:
                                        for style_assignment in item.Styles:
                                            color = self._extract_color_from_style(style_assignment)
                                            if color:
                                                style_info.update(color)
                                                break
                                    if style_info:
                                        break
                            if style_info:
                                break
                    if style_info:
                        break
        except Exception as e:
            logger.debug(f"Error extracting color from material: {e}")
        
        return style_info
    
    def _extract_color_from_style(self, style_assignment) -> Dict:
        """
        Extract color from IFC style assignment.
        Handles multiple IFC style types recursively.
        
        Args:
            style_assignment: IFC style assignment (IfcPresentationStyleAssignment, IfcSurfaceStyle, etc.)
        
        Returns:
            Dictionary with color information
        """
        style_info = {}
        
        try:
            # Handle IfcPresentationStyleAssignment
            if style_assignment.is_a("IfcPresentationStyleAssignment"):
                if hasattr(style_assignment, 'Styles') and style_assignment.Styles:
                    for style in style_assignment.Styles:
                        result = self._extract_color_from_style(style)
                        if result:
                            style_info.update(result)
            
            # Handle IfcSurfaceStyle
            elif style_assignment.is_a("IfcSurfaceStyle"):
                if hasattr(style_assignment, 'Styles') and style_assignment.Styles:
                    for style in style_assignment.Styles:
                        result = self._extract_color_from_style(style)
                        if result:
                            style_info.update(result)
            
            # Handle IfcSurfaceStyleShading (basic color)
            elif style_assignment.is_a("IfcSurfaceStyleShading"):
                # Try SurfaceColour first (IFC4)
                if hasattr(style_assignment, 'SurfaceColour') and style_assignment.SurfaceColour:
                    colour = style_assignment.SurfaceColour
                    # IFC4 uses ColourComponents
                    if hasattr(colour, 'ColourComponents'):
                        components = colour.ColourComponents
                        if len(components) >= 3:
                            style_info['color'] = (
                                float(components[0]),
                                float(components[1]),
                                float(components[2])
                            )
                            style_info['style_type'] = 'IfcSurfaceStyleShading'
                    # IFC2X3 uses Red, Green, Blue attributes
                    elif hasattr(colour, 'Red') and hasattr(colour, 'Green') and hasattr(colour, 'Blue'):
                        style_info['color'] = (
                            float(colour.Red),
                            float(colour.Green),
                            float(colour.Blue)
                        )
                        style_info['style_type'] = 'IfcSurfaceStyleShading'
            
            # Handle IfcSurfaceStyleRendering (advanced rendering with transparency, reflectance)
            elif style_assignment.is_a("IfcSurfaceStyleRendering"):
                # Try SurfaceColour first (IFC4)
                if hasattr(style_assignment, 'SurfaceColour') and style_assignment.SurfaceColour:
                    colour = style_assignment.SurfaceColour
                    # IFC4 uses ColourComponents
                    if hasattr(colour, 'ColourComponents'):
                        components = colour.ColourComponents
                        if len(components) >= 3:
                            style_info['color'] = (
                                float(components[0]),
                                float(components[1]),
                                float(components[2])
                            )
                            style_info['style_type'] = 'IfcSurfaceStyleRendering'
                    # IFC2X3 uses Red, Green, Blue attributes
                    elif hasattr(colour, 'Red') and hasattr(colour, 'Green') and hasattr(colour, 'Blue'):
                        style_info['color'] = (
                            float(colour.Red),
                            float(colour.Green),
                            float(colour.Blue)
                        )
                        style_info['style_type'] = 'IfcSurfaceStyleRendering'
                
                # Extract transparency (0.0 = opaque, 1.0 = fully transparent)
                if hasattr(style_assignment, 'Transparency'):
                    style_info['transparency'] = float(style_assignment.Transparency)
                
                # Extract reflectance method
                if hasattr(style_assignment, 'ReflectanceMethod'):
                    style_info['reflectance_method'] = str(style_assignment.ReflectanceMethod)
                
                # Extract diffuse color (if different from surface color)
                if hasattr(style_assignment, 'DiffuseColour'):
                    diffuse = style_assignment.DiffuseColour
                    if hasattr(diffuse, 'ColourComponents'):
                        components = diffuse.ColourComponents
                        if len(components) >= 3:
                            style_info['diffuse_color'] = (
                                float(components[0]),
                                float(components[1]),
                                float(components[2])
                            )
                
                # Extract specular color
                if hasattr(style_assignment, 'SpecularColour'):
                    specular = style_assignment.SpecularColour
                    if hasattr(specular, 'ColourComponents'):
                        components = specular.ColourComponents
                        if len(components) >= 3:
                            style_info['specular_color'] = (
                                float(components[0]),
                                float(components[1]),
                                float(components[2])
                            )
            
            # Handle IfcSurfaceStyleWithTextures (texture-based)
            elif style_assignment.is_a("IfcSurfaceStyleWithTextures"):
                if hasattr(style_assignment, 'Textures'):
                    textures = []
                    for texture in style_assignment.Textures:
                        texture_info = {}
                        if hasattr(texture, 'RepeatS'):
                            texture_info['repeat_s'] = bool(texture.RepeatS)
                        if hasattr(texture, 'RepeatT'):
                            texture_info['repeat_t'] = bool(texture.RepeatT)
                        if hasattr(texture, 'Mode'):
                            texture_info['mode'] = str(texture.Mode)
                        # Texture reference (IfcImageTexture, IfcPixelTexture, etc.)
                        if hasattr(texture, 'TextureMap'):
                            texture_info['texture_map'] = str(texture.TextureMap)
                        # Extract texture coordinates if available
                        if hasattr(texture, 'TextureCoordinates'):
                            texture_info['texture_coordinates'] = str(texture.TextureCoordinates)
                        textures.append(texture_info)
                    if textures:
                        style_info['textures'] = textures
                        style_info['style_type'] = 'IfcSurfaceStyleWithTextures'
        
        except Exception as e:
            logger.debug(f"Error extracting color from style: {e}")
        
        return style_info
    
    @staticmethod
    def color_to_rgb(color_tuple: Tuple[float, float, float]) -> Tuple[int, int, int]:
        """
        Convert IFC color (0.0-1.0 range) to RGB (0-255 range).
        
        Args:
            color_tuple: (R, G, B) tuple in 0.0-1.0 range
        
        Returns:
            (R, G, B) tuple in 0-255 range
        """
        return (
            int(max(0, min(255, color_tuple[0] * 255))),
            int(max(0, min(255, color_tuple[1] * 255))),
            int(max(0, min(255, color_tuple[2] * 255)))
        )
    
    def _generate_mesh_for_viewer(self):
        """
        Generate 3D mesh from IFC geometry for viewer display with colors and styles.
        
        This method:
        1. Extracts geometry from all building elements (walls, windows, doors, etc.)
        2. Extracts color/style information for each element using multiple methods:
           - Direct extraction from ifcopenshell shape styles
           - Extraction from IFC element representation (IfcStyledItem)
           - Extraction from material associations
        3. Applies colors to mesh faces in RGBA format (0-255 range)
        4. Combines all meshes while preserving colors
        5. Returns a single Trimesh object ready for visualization
        
        Color extraction methods (in order of priority):
        - ifcopenshell shape.styles (most reliable, extracted during geometry creation)
        - IfcStyledItem relationships (standard IFC way)
        - Material representation styles
        - Direct style associations
        
        Returns:
            trimesh.Trimesh object with colors applied, or None if generation fails
        """
        if not TRIMESH_AVAILABLE:
            logger.warning("trimesh not available - cannot generate mesh for viewer")
            return None
        
        try:
            logger.info("Generating 3D mesh from IFC geometry...")
            meshes = []
            
            # Get all building elements that have geometry
            # Note: Process windows FIRST to ensure they get proper color extraction
            element_types = [
                "IfcWindow",  # Process windows first for better color extraction
                "IfcOpeningElement",  # Openings often contain windows
                "IfcWall",
                "IfcWallStandardCase",
                "IfcSlab",  # Floors/ceilings
                "IfcRoof",
                "IfcSpace",  # Rooms
                "IfcColumn",
                "IfcBeam",
                "IfcDoor"
            ]
            
            settings = geom.settings()
            # Use world coordinates
            try:
                if hasattr(settings, 'USE_WORLD_COORDS'):
                    settings.set(settings.USE_WORLD_COORDS, True)
            except:
                pass
            
            # Configure settings for better geometry and color extraction
            try:
                # Enable BREP data for better geometry quality
                if hasattr(settings, 'USE_BREP_DATA'):
                    settings.set(settings.USE_BREP_DATA, True)
                # Disable Python OpenCASCADE if causing issues (use C++ version)
                if hasattr(settings, 'USE_PYTHON_OPENCASCADE'):
                    settings.set(settings.USE_PYTHON_OPENCASCADE, False)
                # Enable edge colors if available
                if hasattr(settings, 'SEW_SHELLS'):
                    settings.set(settings.SEW_SHELLS, True)
            except:
                pass
            
            logger.info("IFC geometry settings configured for color extraction")
            
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
                                            # Extract and apply color/style from IFC element
                                            try:
                                                color_style = {}
                                                
                                                # Method 1: Try extracting from ifcopenshell shape (most reliable)
                                                # ifcopenshell may have already extracted colors during shape creation
                                                color_from_shape = None
                                                try:
                                                    # Check if shape has styles attribute (list of styles)
                                                    if hasattr(shape, 'styles') and shape.styles:
                                                        for style in shape.styles:
                                                            # Try SurfaceColour (IFC4)
                                                            if hasattr(style, 'SurfaceColour') and style.SurfaceColour:
                                                                colour = style.SurfaceColour
                                                                if hasattr(colour, 'ColourComponents'):
                                                                    components = colour.ColourComponents
                                                                    if len(components) >= 3:
                                                                        color_from_shape = (
                                                                            float(components[0]),
                                                                            float(components[1]),
                                                                            float(components[2])
                                                                        )
                                                                        logger.debug(f"Extracted color from ifcopenshell shape.styles for {element_type} {element.id()}: {color_from_shape}")
                                                                        break
                                                                # Try Red/Green/Blue (IFC2X3)
                                                                elif hasattr(colour, 'Red') and hasattr(colour, 'Green') and hasattr(colour, 'Blue'):
                                                                    color_from_shape = (
                                                                        float(colour.Red),
                                                                        float(colour.Green),
                                                                        float(colour.Blue)
                                                                    )
                                                                    logger.debug(f"Extracted color from ifcopenshell shape.styles (IFC2X3) for {element_type} {element.id()}")
                                                                    break
                                                            
                                                            # Try to extract from style's internal structure
                                                            if not color_from_shape:
                                                                # Some styles have colors in different attributes
                                                                for attr_name in ['DiffuseColour', 'SurfaceColour', 'Colour']:
                                                                    if hasattr(style, attr_name):
                                                                        color_obj = getattr(style, attr_name)
                                                                        if color_obj:
                                                                            if hasattr(color_obj, 'ColourComponents'):
                                                                                components = color_obj.ColourComponents
                                                                                if len(components) >= 3:
                                                                                    color_from_shape = (
                                                                                        float(components[0]),
                                                                                        float(components[1]),
                                                                                        float(components[2])
                                                                                    )
                                                                                    logger.debug(f"Extracted color from style.{attr_name} for {element_type} {element.id()}")
                                                                                    break
                                                                            elif hasattr(color_obj, 'Red'):
                                                                                color_from_shape = (
                                                                                    float(color_obj.Red),
                                                                                    float(color_obj.Green),
                                                                                    float(color_obj.Blue)
                                                                                )
                                                                                logger.debug(f"Extracted color from style.{attr_name} (IFC2X3) for {element_type} {element.id()}")
                                                                                break
                                                                    if color_from_shape:
                                                                        break
                                                    
                                                    # Alternative: Check if shape has material with color
                                                    if not color_from_shape and hasattr(shape, 'material') and shape.material:
                                                        material = shape.material
                                                        # Try diffuse color first
                                                        if hasattr(material, 'diffuse') and material.diffuse:
                                                            diffuse = material.diffuse
                                                            if len(diffuse) >= 3:
                                                                r, g, b = diffuse[0], diffuse[1], diffuse[2]
                                                                # Normalize to 0-1 range if needed
                                                                if r > 1.0 or g > 1.0 or b > 1.0:
                                                                    r, g, b = r/255.0, g/255.0, b/255.0
                                                                color_from_shape = (float(r), float(g), float(b))
                                                                logger.debug(f"Extracted color from shape.material.diffuse for {element_type} {element.id()}")
                                                        
                                                        # Try other material color attributes
                                                        if not color_from_shape:
                                                            for attr_name in ['ambient', 'specular', 'emissive']:
                                                                if hasattr(material, attr_name):
                                                                    color_attr = getattr(material, attr_name)
                                                                    if color_attr and len(color_attr) >= 3:
                                                                        r, g, b = color_attr[0], color_attr[1], color_attr[2]
                                                                        if r > 1.0 or g > 1.0 or b > 1.0:
                                                                            r, g, b = r/255.0, g/255.0, b/255.0
                                                                        color_from_shape = (float(r), float(g), float(b))
                                                                        logger.debug(f"Extracted color from shape.material.{attr_name} for {element_type} {element.id()}")
                                                                        break
                                                except Exception as e:
                                                    logger.debug(f"Could not extract color from ifcopenshell shape for {element_type} {element.id()}: {e}")
                                                
                                                # Method 2: Extract from element representation/material (comprehensive extraction)
                                                # This now includes 9 different extraction methods
                                                if not color_from_shape:
                                                    color_style = self._extract_color_and_style(element)
                                                    if color_style and 'color' in color_style:
                                                        color_from_shape = color_style['color']
                                                        logger.debug(f"Extracted color from element representation for {element_type} {element.id()}")
                                                
                                                # Method 2b: For windows specifically, try additional window-specific extraction
                                                if not color_from_shape and element_type == "IfcWindow":
                                                    window_color = self._extract_window_specific_color(element)
                                                    if window_color and 'color' in window_color:
                                                        color_from_shape = window_color['color']
                                                        color_style = window_color
                                                        logger.debug(f"Extracted color using window-specific method for {element.id()}")
                                                
                                                # Method 2c: Check material properties for color (especially for windows)
                                                if not color_from_shape:
                                                    try:
                                                        material_props = self._extract_material_properties(element)
                                                        if material_props:
                                                            # Check if material has color_style
                                                            if 'color_style' in material_props:
                                                                mat_color_style = material_props['color_style']
                                                                if mat_color_style and 'color' in mat_color_style:
                                                                    color_from_shape = mat_color_style['color']
                                                                    color_style = mat_color_style
                                                                    logger.debug(f"Extracted color from material properties for {element_type} {element.id()}")
                                                            
                                                            # Also check all_materials if multiple materials found
                                                            if not color_from_shape and 'all_materials' in material_props:
                                                                for mat in material_props['all_materials']:
                                                                    if 'color_style' in mat and 'color' in mat['color_style']:
                                                                        color_from_shape = mat['color_style']['color']
                                                                        color_style = mat['color_style']
                                                                        logger.debug(f"Extracted color from one of multiple materials for {element_type} {element.id()}")
                                                                        break
                                                    except Exception as e:
                                                        logger.debug(f"Error checking material properties for color: {e}")
                                                
                                                # Method 3: Try extracting from ifcopenshell's material API (if available)
                                                if not color_from_shape:
                                                    try:
                                                        # Some ifcopenshell versions expose material colors directly
                                                        if hasattr(shape, 'material') and shape.material:
                                                            material = shape.material
                                                            # Check for various material color attributes
                                                            for attr_name in ['diffuse', 'ambient', 'specular', 'emissive']:
                                                                if hasattr(material, attr_name):
                                                                    color_attr = getattr(material, attr_name)
                                                                    if color_attr and len(color_attr) >= 3:
                                                                        # Material colors might be in 0-1 or 0-255 range
                                                                        r, g, b = color_attr[0], color_attr[1], color_attr[2]
                                                                        # Normalize to 0-1 range if needed
                                                                        if r > 1.0 or g > 1.0 or b > 1.0:
                                                                            r, g, b = r/255.0, g/255.0, b/255.0
                                                                        color_from_shape = (float(r), float(g), float(b))
                                                                        logger.debug(f"Extracted color from shape material.{attr_name} for {element_type} {element.id()}")
                                                                        break
                                                    except Exception as e:
                                                        logger.debug(f"Could not extract color from shape material API: {e}")
                                                
                                                # Apply color if found
                                                if color_from_shape:
                                                    # Use color from shape if available, otherwise use element color
                                                    if not color_style or 'color' not in color_style:
                                                        color_style = {'color': color_from_shape, 'style_type': 'from_shape'}
                                                    
                                                # Apply color to mesh
                                                if color_style and 'color' in color_style:
                                                    # Get color (IFC format: 0.0-1.0 range)
                                                    r, g, b = color_style['color']
                                                    
                                                    # Get transparency (0.0 = opaque, 1.0 = fully transparent)
                                                    transparency = color_style.get('transparency', 0.0)
                                                    
                                                    # For windows, check material for transparency/glass properties
                                                    if element_type == "IfcWindow" or element.is_a("IfcPlate"):
                                                        # Check material properties for glass/transparent indication
                                                        try:
                                                            material_props = self._extract_material_properties(element)
                                                            if material_props:
                                                                material_name = material_props.get('name', '').lower() if material_props.get('name') else ''
                                                                # If material is glass/glazing, make it semi-transparent
                                                                if any(keyword in material_name for keyword in ['glass', 'glazing', 'verre', 'стекло', 'vitrage']):
                                                                    # Windows should be semi-transparent (alpha ~0.7-0.9)
                                                                    transparency = 0.2  # 20% transparent = 80% opaque
                                                                    logger.debug(f"Applied transparency to {element_type} {element.id()} (glass material)")
                                                        except:
                                                            pass
                                                    
                                                    alpha = 1.0 - transparency  # Convert to alpha (1.0 = opaque)
                                                    
                                                    # Trimesh expects colors in 0-255 range for uint8 or 0.0-1.0 for float
                                                    # Use 0-255 range (uint8) for better compatibility
                                                    color_rgba = np.array([
                                                        int(r * 255),
                                                        int(g * 255),
                                                        int(b * 255),
                                                        int(alpha * 255)
                                                    ], dtype=np.uint8)
                                                    
                                                    # Apply color to all faces (per-face coloring)
                                                    num_faces = len(mesh.faces)
                                                    face_colors = np.tile(color_rgba, (num_faces, 1))
                                                    mesh.visual.face_colors = face_colors
                                                    
                                                    logger.debug(f"✓ Applied color to {element_type} {element.id()}: RGB({r*255:.0f}, {g*255:.0f}, {b*255:.0f}), alpha={alpha:.2f}")
                                                else:
                                                    # No color found - use default light gray
                                                    default_color = np.array([200, 200, 200, 255], dtype=np.uint8)
                                                    num_faces = len(mesh.faces)
                                                    face_colors = np.tile(default_color, (num_faces, 1))
                                                    mesh.visual.face_colors = face_colors
                                                    # Log which element is missing color for debugging
                                                    element_name = getattr(element, 'Name', 'Unnamed')
                                                    element_id = getattr(element, 'GlobalId', element.id())
                                                    if element_type == "IfcWindow":
                                                        logger.info(f"⚠ Window '{element_name}' (ID: {element_id}) has no color - tried all extraction methods")
                                                    else:
                                                        logger.debug(f"⚠ No color found for {element_type} '{element_name}' (ID: {element_id}), using default gray")
                                            except Exception as color_error:
                                                logger.warning(f"Error applying color to {element_type} {element.id()}: {color_error}")
                                                # Use default gray if color extraction fails
                                                default_color = np.array([200, 200, 200, 255], dtype=np.uint8)
                                                num_faces = len(mesh.faces)
                                                face_colors = np.tile(default_color, (num_faces, 1))
                                                mesh.visual.face_colors = face_colors
                                            
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
            
            # Count meshes with colors (check if colors are not default gray)
            colored_meshes = 0
            for m in meshes:
                if hasattr(m.visual, 'face_colors') and m.visual.face_colors is not None and len(m.visual.face_colors) > 0:
                    # Check if color is not default gray (200, 200, 200)
                    first_color = m.visual.face_colors[0]
                    if not (first_color[0] == 200 and first_color[1] == 200 and first_color[2] == 200):
                        colored_meshes += 1
            
            logger.info(f"✓ Meshes with extracted colors: {colored_meshes}/{len(meshes)}")
            if colored_meshes == 0:
                logger.warning("⚠ No colors extracted from IFC file - all elements will display as gray")
                logger.info("This may mean:")
                logger.info("  - IFC file has no color/style information")
                logger.info("  - Colors are stored in an unsupported format")
                logger.info("  - Try opening the IFC file in other software to verify colors exist")
            elif colored_meshes < len(meshes):
                missing_count = len(meshes) - colored_meshes
                logger.info(f"ℹ {missing_count} element(s) are missing colors (using default gray)")
                logger.info("This is normal if some elements don't have style definitions in the IFC file")
            
            # Combine all meshes into one
            if len(meshes) == 1:
                combined_mesh = meshes[0]
                logger.info(f"Using single mesh: {len(combined_mesh.vertices):,} vertices, {len(combined_mesh.faces):,} faces")
                if hasattr(combined_mesh.visual, 'face_colors') and combined_mesh.visual.face_colors is not None:
                    logger.info(f"Mesh has colors applied: {len(combined_mesh.visual.face_colors)} face colors")
            else:
                logger.info(f"Combining {len(meshes)} meshes into single mesh...")
                try:
                    # trimesh.util.concatenate preserves visual properties including colors
                    combined_mesh = trimesh.util.concatenate(meshes)
                    logger.info(f"Successfully combined {len(meshes)} meshes")
                    if hasattr(combined_mesh.visual, 'face_colors') and combined_mesh.visual.face_colors is not None:
                        logger.info(f"Combined mesh has colors: {len(combined_mesh.visual.face_colors)} face colors")
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

