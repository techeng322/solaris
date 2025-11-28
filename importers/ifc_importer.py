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

# Window size validation constants (in meters)
# Windows should be reasonable size - typical windows are 0.3m to 5m in each dimension
MIN_WINDOW_WIDTH = 0.1  # Minimum window width (10cm)
MAX_WINDOW_WIDTH = 10.0  # Maximum window width (10m - very large windows)
MIN_WINDOW_HEIGHT = 0.1  # Minimum window height (10cm)
MAX_WINDOW_HEIGHT = 10.0  # Maximum window height (10m - very tall windows)
MIN_WINDOW_AREA = 0.01  # Minimum window area (0.01 m² = 100 cm²)
MAX_WINDOW_AREA = 50.0  # Maximum window area (50 m² - very large windows)


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
        
        # Method 1: Get all direct window elements AND window type instances
        try:
            # 1a: Direct IfcWindow elements
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
            
            # 1b: Window type instances (IfcWindowType)
            # Some IFC files define windows as types, and instances are created from types
            try:
                window_types = self.ifc_file.by_type("IfcWindowType")
                logger.info(f"Found {len(window_types)} IfcWindowType element(s) - checking for instances...")
                for window_type in window_types:
                    # Find all windows that are instances of this type
                    if hasattr(window_type, 'Types') and window_type.Types:
                        for type_rel in window_type.Types:
                            if hasattr(type_rel, 'RelatedObjects'):
                                for instance in type_rel.RelatedObjects:
                                    if instance.is_a("IfcWindow"):
                                        # Check if already extracted
                                        already_extracted = any(
                                            w.properties.get('ifc_element_id') == str(instance.id())
                                            for w in windows
                                        )
                                        if not already_extracted:
                                            window = self._extract_window(instance)
                                            if window:
                                                windows.append(window)
                                                logger.info(f"Extracted window instance from type '{window_type.Name}' (ID: {instance.id()})")
            except Exception as e:
                logger.debug(f"Error checking window types: {e}")
        except Exception as e:
            logger.warning(f"Error getting IfcWindow elements: {e}")
        
        # Method 2: Extract windows from openings (IfcOpeningElement)
        # DEEP ANALYSIS: Check opening properties, relationships, and geometry
        logger.info("Checking for IfcOpeningElement (openings that might be windows)...")
        try:
            opening_elements = self.ifc_file.by_type("IfcOpeningElement")
            logger.info(f"Found {len(opening_elements)} IfcOpeningElement(s)")
            
            opening_windows = []
            for opening_elem in opening_elements:
                try:
                    # DEEP ANALYSIS: Check opening properties to determine if it's a window
                    opening_name = opening_elem.Name if hasattr(opening_elem, 'Name') else ""
                    opening_name_lower = opening_name.lower() if opening_name else ""
                    is_window_opening = any(keyword in opening_name_lower for keyword in [
                        'window', 'окно', 'fenetre', 'fenster', 'glazing', 'glass', 'pane'
                    ])
                    is_door_opening = any(keyword in opening_name_lower for keyword in [
                        'door', 'дверь', 'porte', 'tür'
                    ])
                    
                    # Check opening properties for window indicators
                    opening_props = self._extract_properties(opening_elem)
                    has_window_properties = False
                    for prop_name, prop_value in opening_props.items():
                        prop_name_lower = prop_name.lower() if prop_name else ""
                        if any(keyword in prop_name_lower for keyword in ['window', 'окно', 'glazing', 'glass']):
                            has_window_properties = True
                            break
                    
                    # Check if this opening is already filled by an IfcWindow
                    is_filled_by_window = False
                    filling_window = None
                    is_filled_by_door = False
                    
                    if hasattr(opening_elem, 'HasFillings'):
                        for filling_rel in opening_elem.HasFillings:
                            if hasattr(filling_rel, 'RelatedBuildingElement'):
                                filling_elem = filling_rel.RelatedBuildingElement
                                if filling_elem.is_a("IfcWindow"):
                                    is_filled_by_window = True
                                    filling_window = filling_elem
                                    break
                                elif filling_elem.is_a("IfcDoor"):
                                    is_filled_by_door = True
                                    break
                    
                    # If opening is filled by a window, extract the window (not the opening)
                    if is_filled_by_window and filling_window:
                        # Check if window already extracted
                        already_extracted = any(
                            w.properties.get('ifc_element_id') == str(filling_window.id())
                            for w in windows
                        )
                        if not already_extracted:
                            window = self._extract_window(filling_window)
                            if window:
                                opening_windows.append(window)
                                logger.info(f"Extracted window from opening (window fills opening, ID: {filling_window.id()})")
                    # If opening has window properties or name suggests window, treat as window
                    elif (is_window_opening or has_window_properties) and not is_door_opening and not is_filled_by_door:
                        window = self._extract_window_from_opening(opening_elem)
                        if window:
                            opening_windows.append(window)
                            logger.info(f"Extracted window from opening (window properties/name, ID: {opening_elem.id()})")
                    # If opening is NOT filled by door and NOT filled by window, treat opening as window (fallback)
                    elif not is_filled_by_door and not is_filled_by_window and not is_door_opening:
                        window = self._extract_window_from_opening(opening_elem)
                        if window:
                            opening_windows.append(window)
                            logger.info(f"Extracted window from unfilled opening (ID: {opening_elem.id()})")
                except Exception as e:
                    logger.debug(f"Error extracting window from opening {opening_elem.id()}: {e}")
            
            if opening_windows:
                windows.extend(opening_windows)
                logger.info(f"Extracted {len(opening_windows)} window(s) from openings")
        except Exception as e:
            logger.warning(f"Error getting IfcOpeningElement: {e}")
        
        # Method 2b: Extract windows from glazing panels (IfcPlate) and window members (IfcMember)
        # AGGRESSIVE: Extract ALL IfcPlate and IfcMember elements and validate by size/geometry
        # Many IFC files store windows as IfcPlate elements (glazing) or IfcMember (frames with glazing)
        logger.info("Checking for IfcPlate and IfcMember elements (glazing panels and window members)...")
        try:
            # Check IfcPlate elements (glazing panels)
            plates = self.ifc_file.by_type("IfcPlate")
            logger.info(f"Found {len(plates)} IfcPlate element(s)")
            
            plate_windows = []
            for plate in plates:
                try:
                    # AGGRESSIVE: Try to extract ALL plates as windows, validate by size
                    # Skip only if explicitly marked as non-window (e.g., door, wall panel)
                    plate_name = plate.Name if hasattr(plate, 'Name') else ""
                    plate_name_lower = plate_name.lower() if plate_name else ""
                    
                    # Skip if explicitly NOT a window (door, wall, etc.)
                    is_excluded = any(keyword in plate_name_lower for keyword in [
                        'door', 'дверь', 'wall', 'стена', 'floor', 'пол', 'ceiling', 'потолок',
                        'roof', 'крыша', 'slab', 'плита', 'frame', 'рама', 'mullion', 'стойка'
                    ])
                    
                    if is_excluded:
                        logger.debug(f"Skipping plate '{plate_name}' (ID: {plate.id()}) - explicitly excluded")
                        continue
                    
                    # Try to extract as window - validation will reject if size is wrong
                    window = self._extract_window_from_plate(plate)
                    if window:
                        plate_windows.append(window)
                        logger.info(f"Extracted window from plate '{plate_name}' (ID: {plate.id()})")
                    else:
                        logger.debug(f"Plate '{plate_name}' (ID: {plate.id()}) rejected - invalid size or geometry")
                except Exception as e:
                    logger.debug(f"Error extracting window from plate {plate.id()}: {e}")
            
            if plate_windows:
                windows.extend(plate_windows)
                logger.info(f"Extracted {len(plate_windows)} window(s) from glazing panels")
            
            # Check IfcMember elements (window frames, mullions - sometimes contain glazing)
            members = self.ifc_file.by_type("IfcMember")
            logger.info(f"Found {len(members)} IfcMember element(s)")
            
            member_windows = []
            for member in members:
                try:
                    # Check if member might be a window (glazing in frame)
                    member_name = member.Name if hasattr(member, 'Name') else ""
                    member_name_lower = member_name.lower() if member_name else ""
                    
                    # Check for window-related keywords
                    is_window_like = any(keyword in member_name_lower for keyword in [
                        'window', 'окно', 'glazing', 'glass', 'pane', 'fenetre', 'fenster'
                    ])
                    
                    # Check material for glazing
                    has_glazing = False
                    try:
                        material_props = self._extract_material_properties(member)
                        if material_props:
                            material_name = material_props.get('name', '').lower() if material_props.get('name') else ''
                            has_glazing = any(keyword in material_name for keyword in [
                                'glass', 'glazing', 'verre', 'стекло', 'vitrage'
                            ])
                    except Exception:
                        pass
                    
                    # Extract if it looks like a window
                    if is_window_like or has_glazing:
                        window = self._extract_window_from_geometry(member)
                        if window:
                            member_windows.append(window)
                            logger.info(f"Extracted window from member '{member_name}' (ID: {member.id()})")
                except Exception as e:
                    logger.debug(f"Error extracting window from member {member.id()}: {e}")
            
            if member_windows:
                windows.extend(member_windows)
                logger.info(f"Extracted {len(member_windows)} window(s) from window members")
        except Exception as e:
            logger.warning(f"Error getting IfcPlate/IfcMember elements: {e}")
        
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
        
        # Method 4: Material-based window detection (DEEP material analysis)
        # This is CRITICAL - many windows are identified by their glazing materials
        logger.info("Performing material-based window detection (deep material analysis)...")
        try:
            # Get all building elements that might be windows based on materials
            potential_window_elements = []
            
            # Check all building elements for glazing materials
            element_types_to_check = [
                "IfcPlate",  # Glazing panels
                "IfcMember",  # Window frames
                "IfcBuildingElementProxy",  # Generic elements
                "IfcCurtainWall",  # Curtain walls (often have windows)
                "IfcCurtainWallPanel",  # Curtain wall panels
                "IfcBuildingElementPart"  # Building element parts
            ]
            
            material_based_windows = []
            for elem_type in element_types_to_check:
                try:
                    elements = self.ifc_file.by_type(elem_type)
                    logger.info(f"Checking {len(elements)} {elem_type} element(s) for window materials...")
                    
                    for elem in elements:
                        try:
                            # DEEP material extraction
                            material_props = self._extract_material_properties(elem)
                            
                            # Check if element has glazing/glass materials
                            has_glazing = False
                            
                            # Check primary material
                            if material_props:
                                material_name = material_props.get('name', '').lower() if material_props.get('name') else ''
                                if any(keyword in material_name for keyword in ['glass', 'glazing', 'verre', 'стекло', 'vitrage', 'pane']):
                                    has_glazing = True
                                
                                # Check if material set has glazing
                                if material_props.get('has_glazing') or material_props.get('is_window_material'):
                                    has_glazing = True
                                
                                # Check constituents for glazing
                                if 'constituents' in material_props:
                                    for constituent in material_props['constituents']:
                                        if constituent.get('is_glazing') or constituent.get('constituent_category', '').lower() == 'glazing':
                                            has_glazing = True
                                            break
                                
                                # Check layers for glazing
                                if 'layers' in material_props:
                                    for layer in material_props['layers']:
                                        if layer.get('is_glazing'):
                                            has_glazing = True
                                            break
                            
                            # If element has glazing material, it's likely a window
                            if has_glazing:
                                logger.info(f"Found glazing material in {elem_type} {elem.id()} - treating as window")
                                window = self._extract_window_from_geometry(elem)
                                if window:
                                    # Mark as detected by material
                                    window.properties['detection_method'] = 'material_based'
                                    window.properties['material'] = material_props
                                    material_based_windows.append(window)
                                    logger.info(f"Extracted window from {elem_type} {elem.id()} based on glazing material")
                        except Exception as e:
                            logger.debug(f"Error checking {elem_type} {elem.id()} for materials: {e}")
                except Exception as e:
                    logger.debug(f"Error getting {elem_type} elements: {e}")
            
            if material_based_windows:
                windows.extend(material_based_windows)
                logger.info(f"Extracted {len(material_based_windows)} window(s) using material-based detection")
        except Exception as e:
            logger.warning(f"Error in material-based window detection: {e}")
        
        # Method 5: Geometry-based window detection (AGGRESSIVE - check ALL element types)
        # This catches windows that aren't properly classified in IFC
        logger.info("Performing AGGRESSIVE geometry-based window detection (checking ALL element types)...")
        try:
            # AGGRESSIVE: Check ALL building element types that could potentially be windows
            potential_window_types = [
                "IfcPlate",  # Glazing panels (already checked, but check again for missed ones)
                "IfcMember",  # Window frames, mullions
                "IfcBuildingElementProxy",  # Generic elements
                "IfcCurtainWallPanel",  # Curtain wall panels (often windows)
                "IfcBuildingElementPart",  # Building element parts
                "IfcElementAssembly",  # Element assemblies (window assemblies)
                "IfcRailing",  # Sometimes windows are stored as railings
                "IfcCovering"  # Coverings can sometimes be windows
            ]
            
            geometry_windows = []
            for elem_type in potential_window_types:
                try:
                    elements = self.ifc_file.by_type(elem_type)
                    logger.info(f"Checking {len(elements)} {elem_type} element(s) for window-like geometry...")
                    
                    for elem in elements:
                        try:
                            # Skip if already detected
                            elem_id = elem.GlobalId if hasattr(elem, 'GlobalId') else str(elem.id())
                            already_detected = any(
                                w.id.endswith(elem_id) or 
                                w.properties.get('ifc_element_id') == str(elem.id())
                                for w in windows
                            )
                            
                            if not already_detected:
                                # AGGRESSIVE: Try to extract as window - validation will reject if invalid
                                # Don't pre-filter - let size validation do the filtering
                                # This catches windows that don't have proper naming or materials
                                try:
                                    window = self._extract_window_from_geometry(elem)
                                    if window:
                                        geometry_windows.append(window)
                                        elem_name = elem.Name if hasattr(elem, 'Name') else f"{elem_type}_{elem.id()}"
                                        logger.info(f"✓ Detected window from {elem_type} '{elem_name}' (ID: {elem.id()}) using geometry analysis")
                                except Exception as extract_error:
                                    # Extraction failed (likely invalid size) - skip silently
                                    logger.debug(f"Skipping {elem_type} {elem.id()} - extraction failed: {extract_error}")
                        except Exception as e:
                            logger.debug(f"Error checking {elem_type} {elem.id()} for window geometry: {e}")
                except Exception as e:
                    logger.debug(f"Error getting {elem_type} elements: {e}")
            
            if geometry_windows:
                windows.extend(geometry_windows)
                logger.info(f"Extracted {len(geometry_windows)} window(s) using geometry-based detection")
        except Exception as e:
            logger.warning(f"Error in geometry-based window detection: {e}")
        
        # Method 6: Relationship-based window extraction (DEEP IFC relationship analysis)
        # Extract windows from all IFC relationships: assemblies, decompositions, curtain walls, etc.
        logger.info("Performing DEEP relationship-based window extraction...")
        try:
            relationship_windows = []
            
            # 6a: Extract windows from element assemblies (IfcElementAssembly)
            # Windows can be part of window assemblies
            try:
                assemblies = self.ifc_file.by_type("IfcElementAssembly")
                logger.info(f"Checking {len(assemblies)} IfcElementAssembly element(s) for windows...")
                for assembly in assemblies:
                    try:
                        # Check if assembly name suggests it's a window assembly
                        assembly_name = assembly.Name if hasattr(assembly, 'Name') else ""
                        assembly_name_lower = assembly_name.lower() if assembly_name else ""
                        is_window_assembly = any(keyword in assembly_name_lower for keyword in [
                            'window', 'окно', 'fenetre', 'fenster', 'glazing', 'glass'
                        ])
                        
                        # Check if assembly has decomposed windows
                        if hasattr(assembly, 'IsDecomposedBy') and assembly.IsDecomposedBy:
                            for decomp_rel in assembly.IsDecomposedBy:
                                if hasattr(decomp_rel, 'RelatedObjects'):
                                    for part in decomp_rel.RelatedObjects:
                                        # If part is a window, extract it
                                        if part.is_a("IfcWindow"):
                                            window = self._extract_window(part)
                                            if window:
                                                relationship_windows.append(window)
                                                logger.info(f"Extracted window from assembly '{assembly_name}' (ID: {assembly.id()})")
                                        # If part is a plate and assembly is window-related, treat as window
                                        elif is_window_assembly and part.is_a("IfcPlate"):
                                            window = self._extract_window_from_plate(part)
                                            if window:
                                                relationship_windows.append(window)
                                                logger.info(f"Extracted window plate from window assembly '{assembly_name}'")
                    except Exception as e:
                        logger.debug(f"Error checking assembly {assembly.id()}: {e}")
            except Exception as e:
                logger.debug(f"Error checking element assemblies: {e}")
            
            # 6b: Extract windows from window decompositions (IsDecomposedBy)
            # Windows can be decomposed into panes, frames, etc. - extract the main window
            try:
                window_elements = self.ifc_file.by_type("IfcWindow")
                for window_elem in window_elements:
                    # Check if this window is already extracted
                    already_extracted = any(
                        w.properties.get('ifc_element_id') == str(window_elem.id())
                        for w in windows
                    )
                    if not already_extracted:
                        window = self._extract_window(window_elem)
                        if window:
                            relationship_windows.append(window)
                            logger.info(f"Extracted window from decomposition check (ID: {window_elem.id()})")
            except Exception as e:
                logger.debug(f"Error checking window decompositions: {e}")
            
            # 6c: Extract windows from curtain wall systems (IfcCurtainWall)
            # Curtain walls often contain windows as panels
            try:
                curtain_walls = self.ifc_file.by_type("IfcCurtainWall")
                logger.info(f"Checking {len(curtain_walls)} IfcCurtainWall element(s) for windows...")
                for curtain_wall in curtain_walls:
                    try:
                        # Check if curtain wall has decomposed panels
                        if hasattr(curtain_wall, 'IsDecomposedBy') and curtain_wall.IsDecomposedBy:
                            for decomp_rel in curtain_wall.IsDecomposedBy:
                                if hasattr(decomp_rel, 'RelatedObjects'):
                                    for panel in decomp_rel.RelatedObjects:
                                        # Curtain wall panels can be windows
                                        if panel.is_a("IfcCurtainWallPanel") or panel.is_a("IfcPlate"):
                                            window = self._extract_window_from_geometry(panel)
                                            if window:
                                                relationship_windows.append(window)
                                                logger.info(f"Extracted window from curtain wall panel (ID: {panel.id()})")
                    except Exception as e:
                        logger.debug(f"Error checking curtain wall {curtain_wall.id()}: {e}")
            except Exception as e:
                logger.debug(f"Error checking curtain walls: {e}")
            
            # 6d: Extract windows from FillsVoids relationships
            # Check all FillsVoids relationships to find windows that fill openings
            try:
                fills_voids_rels = self.ifc_file.by_type("IfcRelFillsElement")
                logger.info(f"Checking {len(fills_voids_rels)} IfcRelFillsElement relationship(s) for windows...")
                for rel in fills_voids_rels:
                    try:
                        if hasattr(rel, 'RelatedBuildingElement'):
                            filling_elem = rel.RelatedBuildingElement
                            # If filling element is a window, extract it
                            if filling_elem.is_a("IfcWindow"):
                                window = self._extract_window(filling_elem)
                                if window:
                                    relationship_windows.append(window)
                                    logger.info(f"Extracted window from FillsVoids relationship (ID: {filling_elem.id()})")
                    except Exception as e:
                        logger.debug(f"Error checking FillsVoids relationship: {e}")
            except Exception as e:
                logger.debug(f"Error checking FillsVoids relationships: {e}")
            
            # 6e: Extract windows from spatial structure relationships
            # Check IfcRelContainedInSpatialStructure for windows in spaces/storeys
            try:
                contained_rels = self.ifc_file.by_type("IfcRelContainedInSpatialStructure")
                logger.info(f"Checking {len(contained_rels)} IfcRelContainedInSpatialStructure relationship(s) for windows...")
                for rel in contained_rels:
                    try:
                        if hasattr(rel, 'RelatedElements'):
                            for elem in rel.RelatedElements:
                                # If element is a window, extract it
                                if elem.is_a("IfcWindow"):
                                    window = self._extract_window(elem)
                                    if window:
                                        relationship_windows.append(window)
                                        logger.info(f"Extracted window from spatial structure relationship (ID: {elem.id()})")
                    except Exception as e:
                        logger.debug(f"Error checking spatial structure relationship: {e}")
            except Exception as e:
                logger.debug(f"Error checking spatial structure relationships: {e}")
            
            if relationship_windows:
                windows.extend(relationship_windows)
                logger.info(f"Extracted {len(relationship_windows)} window(s) using relationship-based detection")
        except Exception as e:
            logger.warning(f"Error in relationship-based window extraction: {e}")
        
        # Method 7: Property-based window detection (DEEP property analysis)
        # Check for window-specific property sets (Pset_WindowCommon, etc.) and classification
        logger.info("Performing DEEP property-based window detection...")
        try:
            property_based_windows = []
            
            # Get all elements that might have window properties
            all_products = self.ifc_file.by_type("IfcProduct")
            logger.info(f"Checking {len(all_products)} element(s) for window-specific properties...")
            
            window_property_keywords = [
                'window', 'окно', 'fenetre', 'fenster', 'glazing', 'glass', 'pane',
                'Pset_WindowCommon', 'Pset_Window', 'WindowCommon', 'WindowProperties'
            ]
            
            window_classification_keywords = [
                'window', 'окно', 'fenetre', 'fenster', 'glazing', 'glass'
            ]
            
            for elem in all_products:
                try:
                    # Skip if already detected
                    elem_id = elem.GlobalId if hasattr(elem, 'GlobalId') else str(elem.id())
                    already_detected = any(
                        w.properties.get('ifc_element_id') == str(elem.id())
                        for w in windows
                    )
                    if already_detected:
                        continue
                    
                    # Check property sets for window-specific properties
                    has_window_properties = False
                    try:
                        if hasattr(elem, 'IsDefinedBy'):
                            for rel in elem.IsDefinedBy:
                                if rel.is_a("IfcRelDefinesByProperties"):
                                    prop_set = rel.RelatingPropertyDefinition
                                    if prop_set.is_a("IfcPropertySet"):
                                        prop_set_name = prop_set.Name if hasattr(prop_set, 'Name') else ""
                                        prop_set_name_lower = prop_set_name.lower() if prop_set_name else ""
                                        
                                        # Check if property set name suggests window
                                        if any(keyword in prop_set_name_lower for keyword in window_property_keywords):
                                            has_window_properties = True
                                            logger.info(f"Found window property set '{prop_set_name}' on {elem.is_a()} {elem.id()}")
                                            break
                                        
                                        # Check properties for window-specific values
                                        if hasattr(prop_set, 'HasProperties'):
                                            for prop in prop_set.HasProperties:
                                                prop_name = prop.Name if hasattr(prop, 'Name') else ""
                                                prop_name_lower = prop_name.lower() if prop_name else ""
                                                if any(keyword in prop_name_lower for keyword in window_property_keywords):
                                                    has_window_properties = True
                                                    logger.info(f"Found window property '{prop_name}' on {elem.is_a()} {elem.id()}")
                                                    break
                    except Exception as e:
                        logger.debug(f"Error checking properties for element {elem.id()}: {e}")
                    
                    # Check classification references
                    has_window_classification = False
                    try:
                        if hasattr(elem, 'HasAssignments'):
                            for assignment in elem.HasAssignments:
                                if assignment.is_a("IfcRelAssociatesClassification"):
                                    if hasattr(assignment, 'RelatingClassification'):
                                        classification = assignment.RelatingClassification
                                        if hasattr(classification, 'Name'):
                                            class_name = classification.Name.lower()
                                            if any(keyword in class_name for keyword in window_classification_keywords):
                                                has_window_classification = True
                                                logger.info(f"Found window classification on {elem.is_a()} {elem.id()}")
                    except Exception as e:
                        logger.debug(f"Error checking classification for element {elem.id()}: {e}")
                    
                    # If element has window properties or classification, try to extract as window
                    if has_window_properties or has_window_classification:
                        window = self._extract_window_from_geometry(elem)
                        if window:
                            property_based_windows.append(window)
                            window.properties['detection_method'] = 'property_based'
                            elem_name = elem.Name if hasattr(elem, 'Name') else f"{elem.is_a()}_{elem.id()}"
                            logger.info(f"✓ Extracted window from {elem.is_a()} '{elem_name}' (ID: {elem.id()}) - property-based detection")
                except Exception as e:
                    logger.debug(f"Error in property-based check for element {elem.id()}: {e}")
            
            if property_based_windows:
                windows.extend(property_based_windows)
                logger.info(f"Extracted {len(property_based_windows)} window(s) using property-based detection")
        except Exception as e:
            logger.warning(f"Error in property-based window detection: {e}")
        
        # Method 8: AGGRESSIVE - Scan ALL IfcProduct elements for window-like geometry
        # This is the most comprehensive method - catches windows stored in any element type
        logger.info("Performing COMPREHENSIVE scan of ALL IfcProduct elements for windows...")
        try:
            # Get ALL IfcProduct elements (base class for all geometric elements)
            all_products = self.ifc_file.by_type("IfcProduct")
            logger.info(f"Scanning {len(all_products)} IfcProduct element(s) for windows...")
            
            # Element types we've already checked (skip to avoid duplicates)
            already_checked_types = {
                "IfcWindow", "IfcOpeningElement", "IfcPlate", "IfcMember", 
                "IfcBuildingElementProxy", "IfcCurtainWallPanel", "IfcBuildingElementPart",
                "IfcElementAssembly", "IfcRailing", "IfcCovering", "IfcWall", "IfcWallStandardCase",
                "IfcDoor", "IfcSpace", "IfcBuilding", "IfcBuildingStorey", "IfcSite", "IfcCurtainWall"
            }
            
            comprehensive_windows = []
            checked_count = 0
            for elem in all_products:
                try:
                    elem_type = elem.is_a()
                    
                    # Skip types we've already checked
                    if elem_type in already_checked_types:
                        continue
                    
                    # Skip if already detected
                    elem_id = elem.GlobalId if hasattr(elem, 'GlobalId') else str(elem.id())
                    already_detected = any(
                        w.id.endswith(elem_id) or 
                        w.properties.get('ifc_element_id') == str(elem.id())
                        for w in windows
                    )
                    
                    if already_detected:
                        continue
                    
                    checked_count += 1
                    
                    # AGGRESSIVE: Try to extract as window - validation will reject if invalid
                    try:
                        window = self._extract_window_from_geometry(elem)
                        if window:
                            comprehensive_windows.append(window)
                            elem_name = elem.Name if hasattr(elem, 'Name') else f"{elem_type}_{elem.id()}"
                            logger.info(f"✓ Detected window from {elem_type} '{elem_name}' (ID: {elem.id()}) - comprehensive scan")
                    except Exception as extract_error:
                        # Extraction failed (likely invalid size) - skip silently
                        pass
                        
                except Exception as e:
                    logger.debug(f"Error checking element {elem.id()} in comprehensive scan: {e}")
            
            if comprehensive_windows:
                windows.extend(comprehensive_windows)
                logger.info(f"Extracted {len(comprehensive_windows)} window(s) from comprehensive scan (checked {checked_count} additional element types)")
        except Exception as e:
            logger.warning(f"Error in comprehensive window scan: {e}")
        
        # Method 9: Recursive relationship traversal (ULTRA-DEEP analysis)
        # Traverse ALL relationships recursively to find windows nested in complex structures
        logger.info("Performing ULTRA-DEEP recursive relationship traversal for windows...")
        try:
            recursive_windows = []
            processed_elements = set()  # Track processed elements to avoid infinite loops
            
            def traverse_relationships(element, depth=0, max_depth=5):
                """Recursively traverse relationships to find windows."""
                if depth > max_depth:
                    return
                
                elem_id = element.id()
                if elem_id in processed_elements:
                    return
                processed_elements.add(elem_id)
                
                # Check if element is already extracted as window (check both windows and recursive_windows)
                already_extracted = any(
                    w.properties.get('ifc_element_id') == str(elem_id)
                    for w in windows + recursive_windows
                )
                if already_extracted:
                    return
                
                # Check if element might be a window
                elem_type = element.is_a()
                if elem_type in ["IfcWindow", "IfcPlate", "IfcMember", "IfcOpeningElement"]:
                    try:
                        # Try to extract as window
                        if elem_type == "IfcWindow":
                            window = self._extract_window(element)
                        elif elem_type == "IfcPlate":
                            window = self._extract_window_from_plate(element)
                        elif elem_type == "IfcOpeningElement":
                            window = self._extract_window_from_opening(element)
                        else:
                            window = self._extract_window_from_geometry(element)
                        
                        if window:
                            recursive_windows.append(window)
                            elem_name = element.Name if hasattr(element, 'Name') else f"{elem_type}_{elem_id}"
                            logger.info(f"✓ Found window via recursive traversal: {elem_type} '{elem_name}' (ID: {elem_id}, depth: {depth})")
                    except Exception as e:
                        logger.debug(f"Error extracting window from {elem_type} {elem_id} in recursive traversal: {e}")
                
                # Traverse IsDecomposedBy relationships
                if hasattr(element, 'IsDecomposedBy') and element.IsDecomposedBy:
                    for decomp_rel in element.IsDecomposedBy:
                        if hasattr(decomp_rel, 'RelatedObjects'):
                            for related_obj in decomp_rel.RelatedObjects:
                                traverse_relationships(related_obj, depth + 1, max_depth)
                
                # Traverse IsNestedBy relationships
                if hasattr(element, 'IsNestedBy') and element.IsNestedBy:
                    for nest_rel in element.IsNestedBy:
                        if hasattr(nest_rel, 'RelatedObjects'):
                            for related_obj in nest_rel.RelatedObjects:
                                traverse_relationships(related_obj, depth + 1, max_depth)
                
                # Traverse HasAssignments relationships
                if hasattr(element, 'HasAssignments') and element.HasAssignments:
                    for assign_rel in element.HasAssignments:
                        if hasattr(assign_rel, 'RelatedObjects'):
                            for related_obj in assign_rel.RelatedObjects:
                                if hasattr(related_obj, 'id'):  # Only traverse if it's an element
                                    traverse_relationships(related_obj, depth + 1, max_depth)
                
                # Traverse FillsVoids relationships (windows fill openings)
                if hasattr(element, 'FillsVoids') and element.FillsVoids:
                    for fills_rel in element.FillsVoids:
                        if hasattr(fills_rel, 'RelatingOpeningElement'):
                            opening = fills_rel.RelatingOpeningElement
                            if opening:
                                traverse_relationships(opening, depth + 1, max_depth)
                
                # Traverse IsDefinedBy relationships (property definitions)
                if hasattr(element, 'IsDefinedBy') and element.IsDefinedBy:
                    for def_rel in element.IsDefinedBy:
                        # Check if relationship points to window-related elements
                        if hasattr(def_rel, 'RelatingPropertyDefinition'):
                            prop_def = def_rel.RelatingPropertyDefinition
                            # Property definitions might reference window elements
                            if prop_def and hasattr(prop_def, 'id'):
                                # Don't traverse property definitions, but check if element itself is window-like
                                pass
                
                # Traverse ContainedInStructure relationships (spatial containment)
                if hasattr(element, 'ContainedInStructure') and element.ContainedInStructure:
                    for cont_rel in element.ContainedInStructure:
                        if hasattr(cont_rel, 'RelatingStructure'):
                            structure = cont_rel.RelatingStructure
                            if structure:
                                traverse_relationships(structure, depth + 1, max_depth)
                
                # Traverse HasOpenings relationships (openings might contain windows)
                if hasattr(element, 'HasOpenings') and element.HasOpenings:
                    for opening_rel in element.HasOpenings:
                        if hasattr(opening_rel, 'RelatedOpeningElement'):
                            opening = opening_rel.RelatedOpeningElement
                            if opening:
                                traverse_relationships(opening, depth + 1, max_depth)
                
                # Traverse HasProjections relationships (projections might be windows)
                if hasattr(element, 'HasProjections') and element.HasProjections:
                    for proj_rel in element.HasProjections:
                        if hasattr(proj_rel, 'RelatedFeatureElement'):
                            feature = proj_rel.RelatedFeatureElement
                            if feature:
                                traverse_relationships(feature, depth + 1, max_depth)
            
            # Start traversal from ALL possible building elements (ULTRA-COMPREHENSIVE)
            # Windows can be nested in ANY building element
            building_elements = []
            try:
                building_elements.extend(self.ifc_file.by_type("IfcBuilding"))
                building_elements.extend(self.ifc_file.by_type("IfcBuildingStorey"))
                building_elements.extend(self.ifc_file.by_type("IfcSpace"))
                building_elements.extend(self.ifc_file.by_type("IfcWall"))
                building_elements.extend(self.ifc_file.by_type("IfcWallStandardCase"))
                building_elements.extend(self.ifc_file.by_type("IfcElementAssembly"))
                building_elements.extend(self.ifc_file.by_type("IfcCurtainWall"))
                building_elements.extend(self.ifc_file.by_type("IfcSlab"))
                building_elements.extend(self.ifc_file.by_type("IfcRoof"))
                building_elements.extend(self.ifc_file.by_type("IfcColumn"))
                building_elements.extend(self.ifc_file.by_type("IfcBeam"))
                building_elements.extend(self.ifc_file.by_type("IfcZone"))
                building_elements.extend(self.ifc_file.by_type("IfcGroup"))
                building_elements.extend(self.ifc_file.by_type("IfcSystem"))
            except Exception as e:
                logger.debug(f"Error collecting building elements for traversal: {e}")
            
            logger.info(f"Starting recursive traversal from {len(building_elements)} building element(s)...")
            for building_elem in building_elements:
                try:
                    traverse_relationships(building_elem, depth=0, max_depth=5)
                except Exception as e:
                    logger.debug(f"Error in recursive traversal from {building_elem.id()}: {e}")
            
            if recursive_windows:
                windows.extend(recursive_windows)
                logger.info(f"Extracted {len(recursive_windows)} window(s) using recursive relationship traversal")
        except Exception as e:
            logger.warning(f"Error in recursive relationship traversal: {e}")
        
        # Method 10: ULTRA-DEEP - Check ALL spatial relationships and containers
        # Windows might be in spaces, storeys, zones, or other spatial containers
        logger.info("Performing ULTRA-DEEP spatial relationship analysis for windows...")
        try:
            spatial_windows = []
            
            # Check all spatial structure relationships
            try:
                spatial_rels = self.ifc_file.by_type("IfcRelContainedInSpatialStructure")
                logger.info(f"Found {len(spatial_rels)} spatial containment relationship(s)")
                
                for rel in spatial_rels:
                    if hasattr(rel, 'RelatedElements'):
                        for elem in rel.RelatedElements:
                            # Check if element is already detected
                            elem_id = str(elem.id())
                            already_detected = any(
                                w.properties.get('ifc_element_id') == elem_id or
                                w.properties.get('ifc_global_id') == getattr(elem, 'GlobalId', None)
                                for w in windows
                            )
                            
                            if not already_detected:
                                # Check if element could be a window
                                elem_type = elem.is_a()
                                if elem_type in ["IfcWindow", "IfcPlate", "IfcMember", "IfcBuildingElementProxy"]:
                                    try:
                                        window = self._extract_window_from_geometry(elem)
                                        if window:
                                            spatial_windows.append(window)
                                            window.properties['detection_method'] = 'spatial_relationship'
                                            logger.info(f"✓ Found window in spatial structure: {elem_type} {elem.id()}")
                                    except:
                                        pass
            except Exception as e:
                logger.debug(f"Error checking spatial relationships: {e}")
            
            # Check all zones (IfcZone) - windows might be assigned to zones
            try:
                zones = self.ifc_file.by_type("IfcZone")
                logger.info(f"Found {len(zones)} zone(s) - checking for windows...")
                for zone in zones:
                    # Check if zone has assigned elements
                    if hasattr(zone, 'IsGroupedBy'):
                        for group_rel in zone.IsGroupedBy:
                            if hasattr(group_rel, 'RelatedObjects'):
                                for elem in group_rel.RelatedObjects:
                                    if elem.is_a() in ["IfcWindow", "IfcPlate", "IfcMember"]:
                                        elem_id = str(elem.id())
                                        already_detected = any(
                                            w.properties.get('ifc_element_id') == elem_id
                                            for w in windows
                                        )
                                        if not already_detected:
                                            try:
                                                window = self._extract_window_from_geometry(elem)
                                                if window:
                                                    spatial_windows.append(window)
                                                    window.properties['detection_method'] = 'zone_assignment'
                                                    logger.info(f"✓ Found window in zone: {elem.is_a()} {elem.id()}")
                                            except:
                                                pass
            except Exception as e:
                logger.debug(f"Error checking zones: {e}")
            
            if spatial_windows:
                windows.extend(spatial_windows)
                logger.info(f"Extracted {len(spatial_windows)} window(s) using spatial relationship analysis")
        except Exception as e:
            logger.warning(f"Error in spatial relationship analysis: {e}")
        
        # Method 11: ULTRA-DEEP - Check ALL void relationships (FillsVoids, VoidElements)
        # Windows fill voids in walls, slabs, roofs, etc.
        logger.info("Performing ULTRA-DEEP void relationship analysis for windows...")
        try:
            void_windows = []
            
            # Check all FillsVoids relationships
            try:
                fills_voids_rels = self.ifc_file.by_type("IfcRelFillsElement")
                logger.info(f"Found {len(fills_voids_rels)} IfcRelFillsElement relationship(s)")
                
                for rel in fills_voids_rels:
                    if hasattr(rel, 'RelatedBuildingElement'):
                        filling_elem = rel.RelatedBuildingElement
                        if filling_elem:
                            elem_id = str(filling_elem.id())
                            already_detected = any(
                                w.properties.get('ifc_element_id') == elem_id
                                for w in windows
                            )
                            
                            if not already_detected:
                                elem_type = filling_elem.is_a()
                                # Check if filling element is a window or could be a window
                                if elem_type == "IfcWindow":
                                    try:
                                        window = self._extract_window(filling_elem)
                                        if window:
                                            void_windows.append(window)
                                            window.properties['detection_method'] = 'fills_voids'
                                            logger.info(f"✓ Found window filling void: {elem_type} {filling_elem.id()}")
                                    except:
                                        pass
                                elif elem_type in ["IfcPlate", "IfcMember", "IfcBuildingElementProxy"]:
                                    # Could be a window - check geometry
                                    try:
                                        window = self._extract_window_from_geometry(filling_elem)
                                        if window:
                                            void_windows.append(window)
                                            window.properties['detection_method'] = 'fills_voids_geometry'
                                            logger.info(f"✓ Found potential window filling void: {elem_type} {filling_elem.id()}")
                                    except:
                                        pass
            except Exception as e:
                logger.debug(f"Error checking FillsVoids relationships: {e}")
            
            # Check all void elements (IfcVoidingFeature, IfcOpeningElement)
            # These might have windows that fill them
            try:
                void_elements = self.ifc_file.by_type("IfcOpeningElement")
                logger.info(f"Found {len(void_elements)} void/opening element(s) - checking for windows...")
                for void_elem in void_elements:
                    void_id = str(void_elem.id())
                    already_detected = any(
                        w.properties.get('ifc_element_id') == void_id
                        for w in windows
                    )
                    
                    if not already_detected:
                        # Check if void is filled by a window
                        if hasattr(void_elem, 'HasFillings'):
                            for filling_rel in void_elem.HasFillings:
                                if hasattr(filling_rel, 'RelatedBuildingElement'):
                                    filling = filling_rel.RelatedBuildingElement
                                    if filling.is_a() == "IfcWindow":
                                        try:
                                            window = self._extract_window(filling)
                                            if window:
                                                void_windows.append(window)
                                                window.properties['detection_method'] = 'void_filling'
                                                logger.info(f"✓ Found window filling void {void_id}: {filling.id()}")
                                        except:
                                            pass
            except Exception as e:
                logger.debug(f"Error checking void elements: {e}")
            
            if void_windows:
                windows.extend(void_windows)
                logger.info(f"Extracted {len(void_windows)} window(s) using void relationship analysis")
        except Exception as e:
            logger.warning(f"Error in void relationship analysis: {e}")
        
        # Method 12: ULTRA-DEEP - Check ALL group relationships (IfcGroup, IfcSystem)
        # Windows might be grouped together or part of systems
        logger.info("Performing ULTRA-DEEP group/system relationship analysis for windows...")
        try:
            group_windows = []
            
            # Check all groups
            try:
                groups = self.ifc_file.by_type("IfcGroup")
                logger.info(f"Found {len(groups)} group(s) - checking for windows...")
                for group in groups:
                    if hasattr(group, 'IsGroupedBy'):
                        for group_rel in group.IsGroupedBy:
                            if hasattr(group_rel, 'RelatedObjects'):
                                for elem in group_rel.RelatedObjects:
                                    if elem.is_a() in ["IfcWindow", "IfcPlate", "IfcMember", "IfcBuildingElementProxy"]:
                                        elem_id = str(elem.id())
                                        already_detected = any(
                                            w.properties.get('ifc_element_id') == elem_id
                                            for w in windows
                                        )
                                        if not already_detected:
                                            try:
                                                if elem.is_a() == "IfcWindow":
                                                    window = self._extract_window(elem)
                                                else:
                                                    window = self._extract_window_from_geometry(elem)
                                                if window:
                                                    group_windows.append(window)
                                                    window.properties['detection_method'] = 'group_member'
                                                    logger.info(f"✓ Found window in group: {elem.is_a()} {elem.id()}")
                                            except:
                                                pass
            except Exception as e:
                logger.debug(f"Error checking groups: {e}")
            
            # Check all systems (IfcSystem)
            try:
                systems = self.ifc_file.by_type("IfcSystem")
                logger.info(f"Found {len(systems)} system(s) - checking for windows...")
                for system in systems:
                    if hasattr(system, 'IsGroupedBy'):
                        for group_rel in system.IsGroupedBy:
                            if hasattr(group_rel, 'RelatedObjects'):
                                for elem in group_rel.RelatedObjects:
                                    if elem.is_a() in ["IfcWindow", "IfcPlate", "IfcMember"]:
                                        elem_id = str(elem.id())
                                        already_detected = any(
                                            w.properties.get('ifc_element_id') == elem_id
                                            for w in windows
                                        )
                                        if not already_detected:
                                            try:
                                                if elem.is_a() == "IfcWindow":
                                                    window = self._extract_window(elem)
                                                else:
                                                    window = self._extract_window_from_geometry(elem)
                                                if window:
                                                    group_windows.append(window)
                                                    window.properties['detection_method'] = 'system_member'
                                                    logger.info(f"✓ Found window in system: {elem.is_a()} {elem.id()}")
                                            except:
                                                pass
            except Exception as e:
                logger.debug(f"Error checking systems: {e}")
            
            if group_windows:
                windows.extend(group_windows)
                logger.info(f"Extracted {len(group_windows)} window(s) using group/system relationship analysis")
        except Exception as e:
            logger.warning(f"Error in group/system relationship analysis: {e}")
        
        # Method 13: ULTRA-DEEP - Check ALL connection relationships
        # Windows might be connected to other elements
        logger.info("Performing ULTRA-DEEP connection relationship analysis for windows...")
        try:
            connection_windows = []
            
            # Check all connection relationships
            try:
                connection_types = [
                    "IfcRelConnectsElements",
                    "IfcRelConnectsPathElements",
                    "IfcRelConnectsPortToElement",
                    "IfcRelConnectsStructuralElement"
                ]
                
                for conn_type in connection_types:
                    try:
                        connections = self.ifc_file.by_type(conn_type)
                        logger.info(f"Found {len(connections)} {conn_type} relationship(s)")
                        
                        for conn in connections:
                            # Check both related elements
                            for attr in ['RelatedElement', 'RelatingElement', 'RelatedElement1', 'RelatedElement2']:
                                if hasattr(conn, attr):
                                    elem = getattr(conn, attr)
                                    if elem and elem.is_a() in ["IfcWindow", "IfcPlate", "IfcMember"]:
                                        elem_id = str(elem.id())
                                        already_detected = any(
                                            w.properties.get('ifc_element_id') == elem_id
                                            for w in windows
                                        )
                                        if not already_detected:
                                            try:
                                                if elem.is_a() == "IfcWindow":
                                                    window = self._extract_window(elem)
                                                else:
                                                    window = self._extract_window_from_geometry(elem)
                                                if window:
                                                    connection_windows.append(window)
                                                    window.properties['detection_method'] = 'connection_relationship'
                                                    logger.info(f"✓ Found window in connection: {elem.is_a()} {elem.id()}")
                                            except:
                                                pass
                    except:
                        pass  # Some connection types might not exist in all IFC versions
            except Exception as e:
                logger.debug(f"Error checking connection relationships: {e}")
            
            if connection_windows:
                windows.extend(connection_windows)
                logger.info(f"Extracted {len(connection_windows)} window(s) using connection relationship analysis")
        except Exception as e:
            logger.warning(f"Error in connection relationship analysis: {e}")
        
        # Method 14: ULTRA-DEEP - Check ALL mapped items and shape representations
        # Windows might be defined as mapped items or in different representation contexts
        logger.info("Performing ULTRA-DEEP shape representation analysis for windows...")
        try:
            representation_windows = []
            
            # Get all elements with shape representations
            try:
                all_products = self.ifc_file.by_type("IfcProduct")
                logger.info(f"Checking {len(all_products)} IfcProduct element(s) for window-like representations...")
                
                for elem in all_products:
                    elem_id = str(elem.id())
                    already_detected = any(
                        w.properties.get('ifc_element_id') == elem_id
                        for w in windows
                    )
                    
                    if not already_detected:
                        # Check if element has representation that suggests it's a window
                        if hasattr(elem, 'Representation') and elem.Representation:
                            representation = elem.Representation
                            # Check representation contexts
                            if hasattr(representation, 'Representations'):
                                for repr_item in representation.Representations:
                                    if hasattr(repr_item, 'RepresentationIdentifier'):
                                        repr_id = repr_item.RepresentationIdentifier
                                        # Check for window-related representation identifiers
                                        if repr_id and any(keyword in repr_id.lower() for keyword in ['window', 'glazing', 'glass', 'fenetre', 'окно']):
                                            # This might be a window
                                            try:
                                                window = self._extract_window_from_geometry(elem)
                                                if window:
                                                    representation_windows.append(window)
                                                    window.properties['detection_method'] = 'representation_identifier'
                                                    logger.info(f"✓ Found window by representation identifier '{repr_id}': {elem.is_a()} {elem.id()}")
                                            except:
                                                pass
            except Exception as e:
                logger.debug(f"Error checking shape representations: {e}")
            
            if representation_windows:
                windows.extend(representation_windows)
                logger.info(f"Extracted {len(representation_windows)} window(s) using shape representation analysis")
        except Exception as e:
            logger.warning(f"Error in shape representation analysis: {e}")
        
        # Method 15: ULTRA-DEEP - Final comprehensive scan of ALL remaining elements
        # This is the absolute last resort - check every single element we haven't checked yet
        logger.info("Performing FINAL comprehensive scan of ALL remaining elements for windows...")
        try:
            final_windows = []
            
            # Get ALL IfcProduct elements
            all_products = self.ifc_file.by_type("IfcProduct")
            logger.info(f"Final scan: Checking {len(all_products)} IfcProduct element(s)...")
            
            # Track which element types we've already checked
            checked_types = {
                "IfcWindow", "IfcWindowType", "IfcOpeningElement", "IfcPlate", "IfcMember",
                "IfcWall", "IfcWallStandardCase", "IfcDoor", "IfcSpace", "IfcBuilding",
                "IfcBuildingStorey", "IfcSite", "IfcCurtainWall", "IfcCurtainWallPanel",
                "IfcElementAssembly", "IfcBuildingElementProxy", "IfcBuildingElementPart",
                "IfcRailing", "IfcCovering", "IfcRoof", "IfcSlab", "IfcColumn", "IfcBeam"
            }
            
            for elem in all_products:
                elem_type = elem.is_a()
                elem_id = str(elem.id())
                
                # Skip types we've already checked extensively
                if elem_type in checked_types:
                    continue
                
                # Skip if already detected
                already_detected = any(
                    w.properties.get('ifc_element_id') == elem_id or
                    w.properties.get('ifc_global_id') == getattr(elem, 'GlobalId', None)
                    for w in windows
                )
                
                if not already_detected:
                    # ULTRA-AGGRESSIVE: Try to extract as window using intelligent detection
                    try:
                        elem_name = elem.Name if hasattr(elem, 'Name') else ''
                        name_lower = elem_name.lower() if elem_name else ''
                        
                        # Method 1: Check if name suggests window
                        window_keywords = ['window', 'окно', 'glazing', 'glass', 'pane', 'fenetre', 'fenster', 'vitrage', 'win', 'оконный']
                        name_match = any(keyword in name_lower for keyword in window_keywords)
                        
                        # Method 2: Check if geometry is window-like
                        geometry_match = self._is_window_like_geometry(elem)
                        
                        # Method 3: Check properties for window indicators
                        properties_match = False
                        try:
                            properties = self._extract_properties(elem)
                            if properties:
                                for prop_name, prop_value in properties.items():
                                    prop_str = str(prop_name) + str(prop_value)
                                    if any(keyword in prop_str.lower() for keyword in window_keywords):
                                        properties_match = True
                                        break
                        except:
                            pass
                        
                        # Method 4: Check material for glazing
                        material_match = False
                        try:
                            material_props = self._extract_material_properties(elem)
                            if material_props:
                                material_name = material_props.get('name', '').lower() if material_props.get('name') else ''
                                if any(keyword in material_name for keyword in ['glass', 'glazing', 'verre', 'стекло']):
                                    material_match = True
                                if material_props.get('has_glazing') or material_props.get('is_window_material'):
                                    material_match = True
                        except:
                            pass
                        
                        # If ANY indicator suggests window, try to extract it
                        if name_match or geometry_match or properties_match or material_match:
                            window = self._extract_window_from_geometry(elem)
                            if window:
                                final_windows.append(window)
                                window.properties['detection_method'] = 'final_comprehensive_scan'
                                indicators = []
                                if name_match:
                                    indicators.append('name')
                                if geometry_match:
                                    indicators.append('geometry')
                                if properties_match:
                                    indicators.append('properties')
                                if material_match:
                                    indicators.append('material')
                                logger.info(f"✓ Found window in final scan ({', '.join(indicators)}): {elem_type} '{elem_name}' (ID: {elem.id()})")
                    except Exception as e:
                        logger.debug(f"Error in final scan for element {elem.id()}: {e}")
            
            if final_windows:
                windows.extend(final_windows)
                logger.info(f"Extracted {len(final_windows)} window(s) using final comprehensive scan")
        except Exception as e:
            logger.warning(f"Error in final comprehensive scan: {e}")
        
        # Remove duplicates based on position and size
        windows = self._remove_duplicate_windows(windows)
        
        logger.info(f"Successfully extracted {len(windows)} window(s) total (after deduplication)")
        logger.info(f"Window detection summary:")
        logger.info(f"  - Direct IfcWindow elements: {len([w for w in windows if w.properties.get('source') == 'IfcWindow'])}")
        logger.info(f"  - From openings: {len([w for w in windows if w.properties.get('source') == 'IfcOpeningElement'])}")
        logger.info(f"  - From plates: {len([w for w in windows if w.properties.get('source') == 'IfcPlate'])}")
        logger.info(f"  - From geometry: {len([w for w in windows if w.properties.get('source') not in ['IfcWindow', 'IfcOpeningElement', 'IfcPlate']])}")
        logger.info(f"  - Detection methods used: {set(w.properties.get('detection_method', 'unknown') for w in windows)}")
        return windows
    
    def _is_window_like_geometry(self, element) -> bool:
        """
        Check if an element has window-like geometry characteristics.
        Windows are typically:
        - Flat (thin in one dimension)
        - Reasonable size (0.3m - 5m width, 0.3m - 4m height)
        - Positioned on building facade
        
        ULTRA-DEEP: Also checks:
        - Element name for window keywords
        - Material properties for glazing
        - Classification for window types
        - Properties for window indicators
        
        Args:
            element: IFC element to check
        
        Returns:
            True if element looks like a window based on geometry and other indicators
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
            
            # ULTRA-DEEP: Check multiple indicators (not just geometry)
            window_indicators = 0
            max_indicators = 5
            
            # Indicator 1: Check if element has transparent/glass material (strong indicator)
            try:
                material_props = self._extract_material_properties(element)
                if material_props:
                    material_name = material_props.get('name', '').lower() if material_props.get('name') else ''
                    if any(keyword in material_name for keyword in ['glass', 'glazing', 'verre', 'стекло', 'vitrage', 'pane']):
                        window_indicators += 2  # Strong indicator
                    if material_props.get('has_glazing') or material_props.get('is_window_material'):
                        window_indicators += 2  # Very strong indicator
            except:
                pass
            
            # Indicator 2: Check name for window-related keywords
            element_name = element.Name if hasattr(element, 'Name') else ''
            if element_name:
                name_lower = element_name.lower()
                window_keywords = ['window', 'окно', 'glazing', 'glass', 'pane', 'fenetre', 'fenster', 'vitrage', 'win', 'оконный']
                if any(keyword in name_lower for keyword in window_keywords):
                    window_indicators += 2  # Strong indicator
            
            # Indicator 3: Check properties for window indicators
            try:
                properties = self._extract_properties(element)
                if properties:
                    # Check property set names
                    for prop_name, prop_value in properties.items():
                        prop_name_lower = str(prop_name).lower()
                        prop_value_str = str(prop_value).lower()
                        if any(keyword in prop_name_lower for keyword in ['window', 'окно', 'glazing', 'glass']):
                            window_indicators += 1
                        if any(keyword in prop_value_str for keyword in ['window', 'окно', 'glazing', 'glass']):
                            window_indicators += 1
            except:
                pass
            
            # Indicator 4: Check classification for window types
            try:
                if hasattr(element, 'HasAssignments'):
                    for assignment in element.HasAssignments:
                        if assignment.is_a("IfcRelAssociatesClassification"):
                            if hasattr(assignment, 'RelatingClassification'):
                                classification = assignment.RelatingClassification
                                if hasattr(classification, 'Name'):
                                    class_name = classification.Name.lower()
                                    if any(keyword in class_name for keyword in ['window', 'окно', 'glazing', 'glass', 'fenetre']):
                                        window_indicators += 2  # Strong indicator
            except:
                pass
            
            # Indicator 5: Check element type
            elem_type = element.is_a()
            if elem_type in ["IfcWindow", "IfcPlate", "IfcMember"]:
                window_indicators += 1  # Element type suggests window
            
            # Indicator 6: Check if size is in typical window range (0.5m - 2.5m)
            if 0.5 <= width <= 2.5 and 0.5 <= height <= 2.5:
                window_indicators += 1  # Size suggests window
            
            # If we have multiple indicators, it's likely a window
            # Require at least 2 indicators (or 1 very strong indicator)
            if window_indicators >= 2:
                logger.debug(f"Element {element.id()} has {window_indicators} window indicator(s) - treating as window")
                return True
            
            # If size is reasonable and in typical window range, consider it even with fewer indicators
            # Windows are typically 0.5m - 2m wide and 0.5m - 2m high
            if 0.5 <= width <= 2.5 and 0.5 <= height <= 2.5 and window_indicators >= 1:
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
                # Early validation - reject if size is unreasonable
                if not self._is_valid_window_size(size):
                    area = size[0] * size[1] if size[0] > 0 and size[1] > 0 else 0
                    logger.warning(f"Element {element_id} ({element_type}) has unreasonable size {size} (area: {area:.2f} m²) - REJECTING as invalid window")
                    return None
            except ValueError as e:
                # Geometry extraction raised ValueError due to invalid size
                logger.warning(f"Element {element_id} ({element_type}) rejected due to invalid size: {e}")
                return None
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
            
            # Validate window size - reject unreasonable dimensions
            if not self._is_valid_window_size(size):
                area = size[0] * size[1] if size[0] > 0 and size[1] > 0 else 0
                logger.warning(f"Element {element_id} ({element_type}) has unreasonable size {size} (area: {area:.2f} m²) - REJECTING as invalid window")
                return None
            
            # Set window properties
            window_props = {
                'window_type': 'double_glazed',  # Default
                'glass_thickness': 6.0,
                'transmittance': 0.75,
                'frame_factor': 0.70,
                'source': element_type  # Mark source element type
            }
            window_props.update(properties)
            
            # Store IFC element reference for geometry extraction during highlighting
            window_props['ifc_element_id'] = str(element.id())
            if hasattr(element, 'GlobalId'):
                window_props['ifc_global_id'] = element.GlobalId
            window_props['ifc_element_type'] = element_type
            window_props['ifc_file_path'] = self.file_path
            
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
    
    def _is_valid_window_size(self, size: Tuple[float, float]) -> bool:
        """
        Validate that window size is reasonable.
        
        Args:
            size: Tuple of (width, height) in meters
            
        Returns:
            True if size is valid for a window, False otherwise
        """
        if size[0] <= 0 or size[1] <= 0:
            return False
        
        width, height = size[0], size[1]
        area = width * height
        
        # Check individual dimensions
        if width < MIN_WINDOW_WIDTH or width > MAX_WINDOW_WIDTH:
            logger.debug(f"Window width {width:.2f}m is outside valid range [{MIN_WINDOW_WIDTH}, {MAX_WINDOW_WIDTH}]")
            return False
        
        if height < MIN_WINDOW_HEIGHT or height > MAX_WINDOW_HEIGHT:
            logger.debug(f"Window height {height:.2f}m is outside valid range [{MIN_WINDOW_HEIGHT}, {MAX_WINDOW_HEIGHT}]")
            return False
        
        # Check area
        if area < MIN_WINDOW_AREA or area > MAX_WINDOW_AREA:
            logger.debug(f"Window area {area:.2f}m² is outside valid range [{MIN_WINDOW_AREA}, {MAX_WINDOW_AREA}]")
            return False
        
        return True
    
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
            except ValueError as e:
                # Invalid size - reject this window
                logger.warning(f"Window {window_id} rejected due to invalid size: {e}")
                return None
            except Exception as e:
                logger.error(f"Failed to extract geometry for window {window_id}: {e}", exc_info=True)
                # Use defaults
                center = (0.0, 0.0, 1.5)
                normal = (0.0, 1.0, 0.0)
                size = (1.5, 1.2)
                # Validate defaults too
                if not self._is_valid_window_size(size):
                    logger.warning(f"Window {window_id} default size is invalid - REJECTING")
                    return None
            
            # Extract all properties (enhanced - supports all IFC property types)
            try:
                all_properties = self._extract_properties(window_elem)
            except Exception as e:
                logger.warning(f"Error extracting properties for window {window_id}: {e}")
                all_properties = {}
            
            # Extract material properties (DEEP comprehensive extraction)
            try:
                material_props = self._extract_material_properties(window_elem)
                if material_props:
                    all_properties['material'] = material_props
                    # Log material information
                    material_name = material_props.get('name', 'Unknown')
                    material_type = material_props.get('type', 'Unknown')
                    logger.info(f"Window {window_id}: Found material '{material_name}' (type: {material_type})")
                    
                    # ULTRA-DEEP: Log detailed material information for distinguishing window types
                    if 'constituents' in material_props:
                        logger.info(f"Window {window_id}: Material has {len(material_props['constituents'])} constituent(s)")
                        for i, const in enumerate(material_props['constituents']):
                            const_name = const.get('name', 'Unknown')
                            const_category = const.get('constituent_category', '')
                            is_glazing = const.get('is_glazing', False)
                            is_frame = const.get('is_frame', False)
                            is_panel = const.get('is_panel', False)
                            is_opaque = const.get('is_opaque_panel', False) or const.get('is_opaque', False)
                            transparency = const.get('transparency')
                            
                            const_type = []
                            if is_glazing:
                                const_type.append('GLAZING')
                            if is_frame:
                                const_type.append('FRAME')
                            if is_panel:
                                const_type.append('PANEL')
                            if is_opaque:
                                const_type.append('OPAQUE')
                            
                            type_str = '/'.join(const_type) if const_type else 'UNKNOWN'
                            trans_str = f", transparency={transparency:.2f}" if transparency is not None else ""
                            logger.info(f"  Constituent {i+1}: {const_name} (category: {const_category}, type: {type_str}{trans_str})")
                            
                            # Log material properties if available
                            if 'properties' in const and const['properties']:
                                logger.debug(f"    Properties: {list(const['properties'].keys())}")
                    
                    if 'layers' in material_props:
                        logger.info(f"Window {window_id}: Material has {len(material_props['layers'])} layer(s)")
                        for i, layer in enumerate(material_props['layers']):
                            layer_name = layer.get('name', 'Unknown')
                            is_glazing = layer.get('is_glazing', False)
                            layer_thickness = layer.get('thickness')
                            thickness_str = f", thickness={layer_thickness:.3f}m" if layer_thickness else ""
                            logger.info(f"  Layer {i+1}: {layer_name} (glazing: {is_glazing}{thickness_str})")
                    
                    # ULTRA-DEEP: Classify window type based on material analysis
                    window_type_class = material_props.get('window_type_classification', 'unknown')
                    if window_type_class != 'unknown':
                        logger.info(f"Window {window_id}: Material classification: {window_type_class.upper()}")
                    
                    # Check for glazing materials
                    if material_props.get('has_glazing') or material_props.get('is_window_material'):
                        logger.info(f"Window {window_id}: Material contains glazing - confirmed as window")
                    
                    # ULTRA-DEEP: Distinguish between transparent and opaque windows
                    has_glazing = material_props.get('has_glazing', False)
                    has_opaque_panel = material_props.get('has_opaque_panel', False)
                    if has_glazing and not has_opaque_panel:
                        logger.info(f"Window {window_id}: TRANSPARENT WINDOW (has glazing, no opaque panel)")
                    elif has_opaque_panel and not has_glazing:
                        logger.info(f"Window {window_id}: OPAQUE PANEL (has opaque panel, no glazing)")
                    elif has_glazing and has_opaque_panel:
                        logger.info(f"Window {window_id}: MIXED WINDOW (has both glazing and opaque panel)")
                    
                    # If material has color, use it for color extraction
                    if 'color_style' in material_props and 'color' in material_props['color_style']:
                        logger.info(f"Window {window_id}: Material has color information")
                else:
                    # No material found - this is common for windows, not necessarily a problem
                    # Only log at debug level, not warning
                    logger.debug(f"Window {window_id}: No material properties found (using default/geometry-based detection)")
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
            
            # ULTRA-DEEP: Store material classification in window properties for distinguishing window types
            if 'material' in all_properties and isinstance(all_properties['material'], dict):
                material_props = all_properties['material']
                
                # Store material classification
                if 'window_type_classification' in material_props:
                    window_props['material_classification'] = material_props['window_type_classification']
                    logger.info(f"Window {window_id}: Material classification stored: {material_props['window_type_classification']}")
                
                # Store detailed constituent information
                if 'constituents' in material_props:
                    window_props['material_constituents'] = material_props['constituents']
                    # Count different constituent types
                    glazing_count = sum(1 for c in material_props['constituents'] if c.get('is_glazing', False))
                    frame_count = sum(1 for c in material_props['constituents'] if c.get('is_frame', False))
                    panel_count = sum(1 for c in material_props['constituents'] if c.get('is_panel', False))
                    opaque_count = sum(1 for c in material_props['constituents'] if c.get('is_opaque_panel', False) or c.get('is_opaque', False))
                    
                    window_props['material_summary'] = {
                        'glazing_count': glazing_count,
                        'frame_count': frame_count,
                        'panel_count': panel_count,
                        'opaque_count': opaque_count,
                        'has_glazing': material_props.get('has_glazing', False),
                        'has_opaque_panel': material_props.get('has_opaque_panel', False)
                    }
                    logger.info(f"Window {window_id}: Material summary - glazing: {glazing_count}, frame: {frame_count}, panel: {panel_count}, opaque: {opaque_count}")
            
            # Validate window data - check for reasonable dimensions
            if not self._is_valid_window_size(size):
                area = size[0] * size[1] if size[0] > 0 and size[1] > 0 else 0
                logger.warning(f"Window {window_id} has unreasonable size {size} (area: {area:.2f} m²) - REJECTING as invalid window")
                return None
            
            # Store IFC element reference for geometry extraction during highlighting
            window_props['ifc_element_id'] = str(window_elem.id())
            if hasattr(window_elem, 'GlobalId'):
                window_props['ifc_global_id'] = window_elem.GlobalId
            window_props['ifc_element_type'] = window_elem.is_a()
            window_props['ifc_file_path'] = self.file_path  # Store file path for later geometry extraction
            
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
                # Early validation - reject if size is unreasonable
                if not self._is_valid_window_size(size):
                    area = size[0] * size[1] if size[0] > 0 and size[1] > 0 else 0
                    logger.warning(f"Opening {opening_id} has unreasonable size {size} (area: {area:.2f} m²) - REJECTING as invalid window")
                    return None
            except ValueError as e:
                # Geometry extraction raised ValueError due to invalid size
                logger.warning(f"Opening {opening_id} rejected due to invalid size: {e}")
                return None
            except Exception as e:
                logger.warning(f"Failed to extract geometry from opening {opening_id}: {e}")
                # Use defaults
                center = (0.0, 0.0, 1.5)
                normal = (0.0, 1.0, 0.0)
                size = (1.5, 1.2)
                # Validate defaults too
                if not self._is_valid_window_size(size):
                    logger.warning(f"Opening {opening_id} default size is invalid - REJECTING")
                    return None
            
            # Extract properties
            window_props = {
                'window_type': 'unknown',
                'glass_thickness': 4.0,
                'transmittance': 0.75,
                'frame_factor': 0.70
            }
            window_props.update(properties)
            
            # Validate window size - reject unreasonable dimensions
            if not self._is_valid_window_size(size):
                area = size[0] * size[1] if size[0] > 0 and size[1] > 0 else 0
                logger.warning(f"Opening {opening_id} has unreasonable size {size} (area: {area:.2f} m²) - REJECTING as invalid window")
                return None
            
            # Store IFC element reference for geometry extraction during highlighting
            window_props['ifc_element_id'] = str(opening_elem.id())
            if hasattr(opening_elem, 'GlobalId'):
                window_props['ifc_global_id'] = opening_elem.GlobalId
            window_props['ifc_element_type'] = opening_elem.is_a()
            window_props['ifc_file_path'] = self.file_path
            
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
                # Early validation - reject if size is unreasonable
                if not self._is_valid_window_size(size):
                    area = size[0] * size[1] if size[0] > 0 and size[1] > 0 else 0
                    logger.warning(f"Plate {plate_id} has unreasonable size {size} (area: {area:.2f} m²) - REJECTING as invalid window")
                    return None
            except ValueError as e:
                # Geometry extraction raised ValueError due to invalid size
                logger.warning(f"Plate {plate_id} rejected due to invalid size: {e}")
                return None
            except Exception as e:
                logger.warning(f"Failed to extract geometry from plate {plate_id}: {e}")
                # Use defaults
                center = (0.0, 0.0, 1.5)
                normal = (0.0, 1.0, 0.0)
                size = (1.5, 1.2)
                # Validate defaults too
                if not self._is_valid_window_size(size):
                    logger.warning(f"Plate {plate_id} default size is invalid - REJECTING")
                    return None
            
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
            
            # Validate window size - reject unreasonable dimensions
            if not self._is_valid_window_size(size):
                area = size[0] * size[1] if size[0] > 0 and size[1] > 0 else 0
                logger.warning(f"Plate {plate_id} has unreasonable size {size} (area: {area:.2f} m²) - REJECTING as invalid window")
                return None
            
            # Set window properties (glazing panels are typically double-glazed)
            window_props = {
                'window_type': 'double_glazed',
                'glass_thickness': 6.0,
                'transmittance': 0.75,
                'frame_factor': 0.70,
                'source': 'IfcPlate'  # Mark as extracted from plate
            }
            window_props.update(properties)
            
            # Store IFC element reference for geometry extraction during highlighting
            window_props['ifc_element_id'] = str(plate_elem.id())
            if hasattr(plate_elem, 'GlobalId'):
                window_props['ifc_global_id'] = plate_elem.GlobalId
            window_props['ifc_element_type'] = plate_elem.is_a()
            window_props['ifc_file_path'] = self.file_path
            
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
        Uses multiple methods to ensure dimensions are ALWAYS extracted:
        1. Properties (fastest)
        2. Geometry extraction (if properties missing)
        3. Type definition properties (fallback)
        4. Reasonable defaults (last resort)
        """
        # Try to extract from properties first (fastest)
        properties = self._extract_properties(window_elem)
        
        # Extract size from properties (try multiple property names)
        width = properties.get('OverallWidth') or properties.get('Width') or properties.get('NominalWidth') or properties.get('FrameWidth')
        height = properties.get('OverallHeight') or properties.get('Height') or properties.get('NominalHeight') or properties.get('FrameHeight')
        
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
        
        # Method 2: Try to get dimensions from window type if available
        if (width is None or height is None or width <= 0 or height <= 0) and hasattr(window_elem, 'IsTypedBy') and window_elem.IsTypedBy:
            try:
                for type_rel in window_elem.IsTypedBy:
                    if hasattr(type_rel, 'RelatingType') and type_rel.RelatingType:
                        window_type = type_rel.RelatingType
                        type_properties = self._extract_properties(window_type)
                        if not width or width <= 0:
                            width = type_properties.get('OverallWidth') or type_properties.get('Width') or type_properties.get('NominalWidth')
                            if width:
                                try:
                                    width = float(width)
                                except (ValueError, TypeError):
                                    width = None
                        if not height or height <= 0:
                            height = type_properties.get('OverallHeight') or type_properties.get('Height') or type_properties.get('NominalHeight')
                            if height:
                                try:
                                    height = float(height)
                                except (ValueError, TypeError):
                                    height = None
                        if width and width > 0 and height and height > 0:
                            logger.debug(f"Extracted window dimensions from window type: {width}x{height}")
                            break
            except Exception as e:
                logger.debug(f"Error extracting dimensions from window type: {e}")
        
        # Method 3: If properties don't have size, try geometry extraction (ALWAYS try for windows, even in lightweight mode)
        # Windows need dimensions for calculations, so we always extract geometry if properties are missing
        if width is None or height is None or width <= 0 or height <= 0:
            logger.info(f"Window dimensions not found in properties for {window_elem.id()}, extracting from geometry...")
            try:
                geom_center, geom_normal, geom_size = self._extract_geometry_from_ifc(window_elem)
                if geom_size[0] > 0 and geom_size[1] > 0:
                    logger.info(f"✓ Successfully extracted window dimensions from geometry: {geom_size[0]:.2f}m x {geom_size[1]:.2f}m")
                    # Use geometry-extracted values
                    return geom_center, geom_normal, geom_size
                else:
                    logger.warning(f"Geometry extraction returned invalid size: {geom_size}")
            except Exception as e:
                logger.warning(f"Geometry extraction failed for window {window_elem.id()}: {e}")
                logger.info("Will use estimated dimensions based on window type or defaults")
        
        # Method 4: Use properties or reasonable defaults based on window type
        if width is None or width <= 0:
            # Try to estimate from window type or use reasonable default
            window_type_name = ""
            if hasattr(window_elem, 'IsTypedBy') and window_elem.IsTypedBy:
                try:
                    type_rel = window_elem.IsTypedBy[0]
                    if hasattr(type_rel, 'RelatingType') and hasattr(type_rel.RelatingType, 'Name'):
                        window_type_name = type_rel.RelatingType.Name.lower() if type_rel.RelatingType.Name else ""
                except:
                    pass
            
            # Estimate width based on window type
            if 'large' in window_type_name or 'wide' in window_type_name:
                width = 2.0
            elif 'small' in window_type_name or 'narrow' in window_type_name:
                width = 0.8
            else:
                width = 1.5  # Standard window width
        
        if height is None or height <= 0:
            # Try to estimate from window type or use reasonable default
            window_type_name = ""
            if hasattr(window_elem, 'IsTypedBy') and window_elem.IsTypedBy:
                try:
                    type_rel = window_elem.IsTypedBy[0]
                    if hasattr(type_rel, 'RelatingType') and hasattr(type_rel.RelatingType, 'Name'):
                        window_type_name = type_rel.RelatingType.Name.lower() if type_rel.RelatingType.Name else ""
                except:
                    pass
            
            # Estimate height based on window type
            if 'tall' in window_type_name or 'high' in window_type_name:
                height = 2.0
            elif 'short' in window_type_name or 'low' in window_type_name:
                height = 0.8
            else:
                height = 1.2  # Standard window height
        
        width = float(width)
        height = float(height)
        size = (width, height)
        logger.debug(f"Using size from properties/type/geometry/defaults: {size}")
        
        # Validate size BEFORE extracting position/normal (early rejection of invalid windows)
        if not self._is_valid_window_size(size):
            area = width * height
            element_id = window_elem.id() if hasattr(window_elem, 'id') else 'unknown'
            logger.warning(f"Window element {element_id} has unreasonable size {size} (area: {area:.2f} m²) - rejecting")
            # Return None to indicate invalid window (caller should handle)
            raise ValueError(f"Invalid window size: {size} (area: {area:.2f} m²)")
        
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
        """
        Extract window normal (direction window faces) from IFC element placement.
        
        In IFC, the window normal is typically the Y-axis of the transformation matrix,
        which represents the direction perpendicular to the window plane (the direction the window faces).
        """
        # Method 1: Try to extract from geometry transformation matrix (most accurate)
        if not self.lightweight:
            try:
                settings = geom.settings()
                shape = geom.create_shape(settings, window_elem)
                if hasattr(shape, 'transformation') and shape.transformation:
                    matrix = shape.transformation.matrix.data
                    if len(matrix) >= 16:
                        # IFC transformation matrix is 4x4 stored as 16-element array
                        # Column 0-3: X-axis (right direction)
                        # Column 4-7: Y-axis (window normal - direction window faces) ← THIS IS WHAT WE NEED
                        # Column 8-11: Z-axis (up direction)
                        # Column 12-15: Translation (position)
                        # Extract Y-axis (columns 4, 5, 6) as the window normal
                        normal = (
                            float(matrix[4]),
                            float(matrix[5]),
                            float(matrix[6])
                        )
                        # Normalize
                        norm_length = (normal[0]**2 + normal[1]**2 + normal[2]**2)**0.5
                        if norm_length > 1e-6:
                            normal = (normal[0]/norm_length, normal[1]/norm_length, normal[2]/norm_length)
                            logger.debug(f"Extracted window normal from transformation matrix Y-axis: {normal}")
                            return normal
            except Exception as e:
                logger.debug(f"Error extracting window normal from geometry: {e}")
        
        # Method 2: Try to get from ObjectPlacement rotation (IfcAxis2Placement3D)
        try:
            if hasattr(window_elem, 'ObjectPlacement') and window_elem.ObjectPlacement:
                placement = window_elem.ObjectPlacement
                if hasattr(placement, 'RelativePlacement') and placement.RelativePlacement:
                    rel_placement = placement.RelativePlacement
                    # IfcAxis2Placement3D has RefDirection (X-axis) and Axis (Z-axis)
                    # The Y-axis (window normal) is perpendicular to both
                    if hasattr(rel_placement, 'RefDirection') and rel_placement.RefDirection:
                        ref_dir = rel_placement.RefDirection
                        if hasattr(ref_dir, 'DirectionRatios'):
                            x_axis = ref_dir.DirectionRatios
                            if len(x_axis) >= 3:
                                x_axis = np.array([float(x_axis[0]), float(x_axis[1]), float(x_axis[2])])
                                
                                # Get Z-axis (up direction)
                                z_axis = None
                                if hasattr(rel_placement, 'Axis') and rel_placement.Axis:
                                    axis = rel_placement.Axis
                                    if hasattr(axis, 'DirectionRatios'):
                                        z_ratios = axis.DirectionRatios
                                        if len(z_ratios) >= 3:
                                            z_axis = np.array([float(z_ratios[0]), float(z_ratios[1]), float(z_ratios[2])])
                                
                                # Calculate Y-axis (window normal) = Z × X (cross product)
                                if z_axis is not None:
                                    y_axis = np.cross(z_axis, x_axis)
                                    norm = np.linalg.norm(y_axis)
                                    if norm > 1e-6:
                                        y_axis = y_axis / norm
                                        normal = tuple(y_axis)
                                        logger.debug(f"Extracted window normal from placement axes: {normal}")
                                        return normal
        except Exception as e:
            logger.debug(f"Error extracting window normal from placement: {e}")
        
        # Method 3: Fallback: use properties or default (facing north)
        direction = properties.get('Direction', 'North')
        direction_map = {
            'North': (0.0, 1.0, 0.0),
            'South': (0.0, -1.0, 0.0),
            'East': (1.0, 0.0, 0.0),
            'West': (-1.0, 0.0, 0.0)
        }
        logger.debug(f"Using fallback direction for window normal: {direction}")
        return direction_map.get(direction, (0.0, 1.0, 0.0))
    
    @staticmethod
    def extract_element_mesh(ifc_file_path: str, element_id: str) -> Optional['trimesh.Trimesh']:
        """
        Extract actual geometry mesh for a specific IFC element by ID.
        Used for highlighting objects with their actual geometry instead of synthetic meshes.
        
        Args:
            ifc_file_path: Path to IFC file
            element_id: IFC element ID (as string)
            
        Returns:
            trimesh.Trimesh object with element geometry, or None if extraction fails
        """
        if not TRIMESH_AVAILABLE:
            logger.warning("trimesh not available - cannot extract element mesh")
            return None
        
        try:
            # Open IFC file
            ifc_file = ifcopenshell.open(ifc_file_path)
            
            # Get element by ID
            try:
                element_id_int = int(element_id)
                element = ifc_file.by_id(element_id_int)
            except (ValueError, RuntimeError):
                logger.warning(f"Could not find element with ID {element_id} in IFC file")
                return None
            
            if element is None:
                logger.warning(f"Element {element_id} not found in IFC file")
                return None
            
            # Extract geometry using ifcopenshell
            # CRITICAL: Use the SAME settings as main mesh generation to ensure coordinate system consistency
            settings = geom.settings()
            try:
                # Enable world coordinates (same as main mesh generation)
                if hasattr(settings, 'USE_WORLD_COORDS'):
                    settings.set(settings.USE_WORLD_COORDS, True)
                    logger.debug(f"Enabled world coordinates for element {element_id}")
            except Exception as e:
                logger.debug(f"Could not enable world coordinates: {e}")
            
            # Use the same additional settings as main mesh generation for consistency
            try:
                if hasattr(settings, 'USE_BREP_DATA'):
                    settings.set(settings.USE_BREP_DATA, True)
                if hasattr(settings, 'USE_PYTHON_OPENCASCADE'):
                    settings.set(settings.USE_PYTHON_OPENCASCADE, False)
                if hasattr(settings, 'SEW_SHELLS'):
                    settings.set(settings.SEW_SHELLS, True)
                if hasattr(settings, 'DISABLE_OPENING_SUBTRACTION'):
                    # CRITICAL: Disable opening subtraction for element extraction
                    # Opening subtraction removes geometry from walls where windows/doors are located
                    # This can make walls invisible or very thin, especially if they have many openings
                    settings.set(settings.DISABLE_OPENING_SUBTRACTION, True)  # DISABLE subtraction
                    logger.debug("✓ Opening subtraction DISABLED for element extraction (walls will be fully visible)")
                if hasattr(settings, 'USE_MATERIAL_COLOR'):
                    settings.set(settings.USE_MATERIAL_COLOR, True)
                if hasattr(settings, 'WELD_VERTICES'):
                    settings.set(settings.WELD_VERTICES, False)
            except Exception as e:
                logger.debug(f"Some geometry settings could not be configured: {e}")
            
            # CRITICAL: Try multiple representations for windows (they may use different representation indices)
            # Windows can have multiple representations (Body, Profile, etc.)
            shape = None
            representation_index = 0
            max_representations = 10  # Try up to 10 different representations
            
            while shape is None and representation_index < max_representations:
                try:
                    if representation_index == 0:
                        # First try: default representation (usually Body)
                        try:
                            shape = geom.create_shape(settings, element)
                        except Exception as default_error:
                            # If default fails, try with explicit representation index 0
                            try:
                                shape = geom.create_shape(settings, element, 0)
                            except:
                                representation_index += 1
                                continue
                    else:
                        # Try other representations explicitly
                        try:
                            shape = geom.create_shape(settings, element, representation_index)
                        except Exception as repr_error:
                            # If representation index doesn't exist, try next
                            representation_index += 1
                            continue
                    
                    # Validate shape has geometry
                    if shape and hasattr(shape, 'geometry') and shape.geometry:
                        geometry = shape.geometry
                        # Check if geometry has valid data
                        has_valid_data = False
                        if hasattr(geometry, 'verts') and hasattr(geometry, 'faces'):
                            if len(geometry.verts) > 0 and len(geometry.faces) > 0:
                                has_valid_data = True
                        elif hasattr(geometry, 'tessellation'):
                            try:
                                tess = geometry.tessellation()
                                if tess and isinstance(tess, tuple) and len(tess) >= 2:
                                    if len(tess[0]) > 0 and len(tess[1]) > 0:
                                        has_valid_data = True
                            except:
                                pass
                        
                        if has_valid_data:
                            logger.debug(f"✓ Created shape for element {element_id} using representation {representation_index}")
                            break
                        else:
                            # Shape exists but has no valid geometry, try next representation
                            shape = None
                            representation_index += 1
                    else:
                        shape = None
                        representation_index += 1
                except Exception as shape_error:
                    # Try next representation
                    shape = None
                    representation_index += 1
            
            if shape is None:
                logger.warning(f"Could not create shape for element {element_id} after {max_representations} representation attempts")
                return None
            
            geometry = shape.geometry
            
            # Extract vertices and faces
            vertices = None
            faces = None
            
            # Method 1: Use tessellation
            try:
                if hasattr(geometry, 'tessellation'):
                    tess = geometry.tessellation()
                    if tess and isinstance(tess, tuple) and len(tess) >= 2:
                        vertices = np.array(tess[0], dtype=np.float64)
                        faces_data = tess[1]
                        faces = np.array(faces_data, dtype=np.int32)
                        if len(faces.shape) == 1 and len(faces) % 3 == 0:
                            faces = faces.reshape(-1, 3)
            except Exception as e:
                logger.debug(f"Tessellation failed for element {element_id}: {e}")
            
            # Method 2: Direct access to verts/faces
            if (vertices is None or faces is None) and hasattr(geometry, 'verts') and hasattr(geometry, 'faces'):
                try:
                    verts = geometry.verts
                    faces_data = geometry.faces
                    vertices = np.array(verts, dtype=np.float64)
                    if len(vertices.shape) == 1 and len(vertices) % 3 == 0:
                        vertices = vertices.reshape(-1, 3)
                    faces = np.array(faces_data, dtype=np.int32)
                    if len(faces.shape) == 1 and len(faces) % 3 == 0:
                        faces = faces.reshape(-1, 3)
                except Exception as e:
                    logger.debug(f"Direct verts/faces access failed for element {element_id}: {e}")
            
            # CRITICAL: Apply transformation matrix if available and not identity
            # Even with USE_WORLD_COORDS, some ifcopenshell versions may not apply transformations correctly
            # Check if transformation is non-identity before applying
            if vertices is not None and hasattr(shape, 'transformation') and shape.transformation:
                try:
                    matrix = shape.transformation.matrix.data
                    if len(matrix) >= 16:
                        # Check if transformation matrix is identity (no transformation needed)
                        identity = np.array([
                            [1, 0, 0, 0],
                            [0, 1, 0, 0],
                            [0, 0, 1, 0],
                            [0, 0, 0, 1]
                        ])
                        transform_matrix = np.array([
                            [matrix[0], matrix[1], matrix[2], matrix[3]],
                            [matrix[4], matrix[5], matrix[6], matrix[7]],
                            [matrix[8], matrix[9], matrix[10], matrix[11]],
                            [matrix[12], matrix[13], matrix[14], matrix[15]]
                        ])
                        
                        # Check if matrix is significantly different from identity
                        if not np.allclose(transform_matrix, identity, atol=1e-6):
                            # Apply transformation to all vertices
                            # Add homogeneous coordinate (w=1) to vertices
                            vertices_homogeneous = np.hstack([vertices, np.ones((len(vertices), 1))])
                            # Transform: v' = M * v
                            vertices_transformed = (transform_matrix @ vertices_homogeneous.T).T
                            # Extract x, y, z (drop w coordinate)
                            vertices = vertices_transformed[:, :3]
                            logger.debug(f"Applied transformation matrix to {len(vertices)} vertices for element {element_id}")
                        else:
                            logger.debug(f"Transformation matrix is identity for element {element_id} - no transformation needed")
                except Exception as e:
                    logger.debug(f"Could not apply transformation matrix for element {element_id}: {e}")
                    # Continue without transformation - USE_WORLD_COORDS might have already applied it
            
            # Create mesh if we have valid data
            if vertices is not None and faces is not None and len(vertices) > 0 and len(faces) > 0:
                try:
                    # Validate face indices
                    max_vertex_idx = np.max(faces)
                    if max_vertex_idx >= len(vertices):
                        # Filter out invalid faces
                        valid_faces = []
                        for face in faces:
                            if all(0 <= idx < len(vertices) for idx in face):
                                valid_faces.append(face)
                        if len(valid_faces) > 0:
                            faces = np.array(valid_faces, dtype=np.int32)
                        else:
                            logger.warning(f"All faces invalid for element {element_id}")
                            return None
                    
                    mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
                    
                    # Validate mesh
                    if len(mesh.vertices) > 0 and len(mesh.faces) > 0:
                        # CRITICAL: Extract and apply material/color from IFC element
                        # This ensures windows show their actual material, not just transparent boxes
                        try:
                            # Try to extract color from shape styles
                            if hasattr(shape, 'styles') and shape.styles:
                                for style in shape.styles:
                                    if hasattr(style, 'SurfaceColour') and style.SurfaceColour:
                                        colour = style.SurfaceColour
                                        if hasattr(colour, 'ColourComponents'):
                                            components = colour.ColourComponents
                                            if len(components) >= 3:
                                                r, g, b = float(components[0]), float(components[1]), float(components[2])
                                                # Convert to 0-255 range
                                                color_rgba = np.array([int(r * 255), int(g * 255), int(b * 255), 200], dtype=np.uint8)
                                                num_faces = len(mesh.faces)
                                                face_colors = np.tile(color_rgba, (num_faces, 1))
                                                mesh.visual.face_colors = face_colors
                                                logger.debug(f"Applied color from IFC style to element {element_id}: RGB({r*255:.0f}, {g*255:.0f}, {b*255:.0f})")
                                                break
                        except Exception as color_error:
                            logger.debug(f"Could not extract color from shape for element {element_id}: {color_error}")
                        
                        logger.info(f"✓ Extracted mesh for element {element_id}: {len(mesh.vertices)} vertices, {len(mesh.faces)} faces")
                        # Log mesh bounds for debugging
                        bounds = mesh.bounds
                        logger.debug(f"Mesh bounds: min={bounds[0]}, max={bounds[1]}")
                        return mesh
                    else:
                        logger.warning(f"Created mesh is empty for element {element_id}")
                        return None
                except Exception as e:
                    logger.error(f"Failed to create mesh for element {element_id}: {e}", exc_info=True)
                    return None
            else:
                logger.warning(f"Could not extract valid geometry for element {element_id}: vertices={vertices is not None and len(vertices) if vertices is not None else None}, faces={faces is not None and len(faces) if faces is not None else None}")
                return None
                
        except Exception as e:
            logger.warning(f"Error extracting mesh for element {element_id} from {ifc_file_path}: {e}")
            return None
    
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
            
            # Get bounding box - Triangulation objects don't have bbox attribute
            # Calculate from vertices instead
            if hasattr(geometry, 'bbox') and geometry.bbox is not None:
                # Some geometry types have bbox attribute
                bbox = geometry.bbox
                if len(bbox) >= 2:
                    min_bounds = bbox[0]
                    max_bounds = bbox[1]
                else:
                    raise ValueError("Invalid bounding box")
            elif hasattr(geometry, 'verts') and geometry.verts:
                # Calculate bbox from vertices (for Triangulation objects)
                verts = geometry.verts
                if not verts or len(verts) == 0:
                    raise ValueError("No vertices in geometry")
                
                # Convert to numpy array for efficient calculation
                try:
                    vertices = np.array(verts, dtype=np.float64)
                    if len(vertices.shape) == 1:
                        if len(vertices) % 3 == 0:
                            vertices = vertices.reshape(-1, 3)
                        else:
                            raise ValueError("Invalid vertex count")
                    elif len(vertices.shape) == 2 and vertices.shape[1] != 3:
                        raise ValueError("Invalid vertex shape")
                    
                    if len(vertices) < 3:
                        raise ValueError("Not enough vertices")
                    
                    # Calculate bounding box
                    min_bounds = np.min(vertices, axis=0)
                    max_bounds = np.max(vertices, axis=0)
                    min_bounds = tuple(min_bounds)
                    max_bounds = tuple(max_bounds)
                except Exception as e:
                    logger.debug(f"Error processing vertices for bbox: {e}")
                    # Fallback: manual calculation
                    if isinstance(verts, (list, tuple)) and len(verts) >= 3:
                        x_coords = [v[0] if isinstance(v, (list, tuple, np.ndarray)) and len(v) > 0 else (verts[i] if i < len(verts) else 0) for i, v in enumerate(verts[::3])]
                        y_coords = [v[1] if isinstance(v, (list, tuple, np.ndarray)) and len(v) > 1 else (verts[i+1] if i+1 < len(verts) else 0) for i, v in enumerate(verts[1::3])]
                        z_coords = [v[2] if isinstance(v, (list, tuple, np.ndarray)) and len(v) > 2 else (verts[i+2] if i+2 < len(verts) else 0) for i, v in enumerate(verts[2::3])]
                        
                        if x_coords and y_coords and z_coords:
                            min_bounds = (min(x_coords), min(y_coords), min(z_coords))
                            max_bounds = (max(x_coords), max(y_coords), max(z_coords))
                        else:
                            raise ValueError("Could not extract coordinates from vertices")
                    else:
                        raise ValueError("Invalid vertex format")
            else:
                raise ValueError("Geometry has no bbox or verts attribute")
            
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
            # In IFC, the window normal is the Y-axis of the transformation matrix
            # (the direction perpendicular to the window plane, i.e., the direction the window faces)
            normal = (0.0, 1.0, 0.0)  # Default facing north
            try:
                if hasattr(shape, 'transformation') and shape.transformation:
                    matrix = shape.transformation.matrix.data
                    if len(matrix) >= 16:
                        # IFC transformation matrix is 4x4 stored as 16-element array
                        # Column 0-3: X-axis (right direction)
                        # Column 4-7: Y-axis (window normal - direction window faces) ← THIS IS WHAT WE NEED
                        # Column 8-11: Z-axis (up direction)
                        # Column 12-15: Translation (position)
                        # Extract Y-axis (columns 4, 5, 6) as the window normal
                        normal = (
                            float(matrix[4]),
                            float(matrix[5]),
                            float(matrix[6])
                        )
                        # Normalize
                        norm_length = (normal[0]**2 + normal[1]**2 + normal[2]**2)**0.5
                        if norm_length > 1e-6:
                            normal = (normal[0]/norm_length, normal[1]/norm_length, normal[2]/norm_length)
                            logger.debug(f"Extracted window normal from transformation matrix Y-axis: {normal}")
                        else:
                            logger.debug("Normal vector has zero length, using default")
                    elif len(matrix) >= 12:
                        # Fallback for older matrix format - try Z-axis
                        normal = (
                            float(matrix[8]),
                            float(matrix[9]),
                            float(matrix[10])
                        )
                        norm_length = (normal[0]**2 + normal[1]**2 + normal[2]**2)**0.5
                        if norm_length > 1e-6:
                            normal = (normal[0]/norm_length, normal[1]/norm_length, normal[2]/norm_length)
                            logger.debug(f"Extracted window normal from transformation matrix Z-axis (fallback): {normal}")
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
                
                # Get bounding box - handle Triangulation objects
                if hasattr(geometry, 'bbox') and geometry.bbox is not None and len(geometry.bbox) >= 2:
                    bbox = geometry.bbox
                    min_bounds = bbox[0]
                    max_bounds = bbox[1]
                elif hasattr(geometry, 'verts') and geometry.verts:
                    # Calculate from vertices
                    verts = geometry.verts
                    try:
                        vertices = np.array(verts, dtype=np.float64)
                        if len(vertices.shape) == 1 and len(vertices) % 3 == 0:
                            vertices = vertices.reshape(-1, 3)
                        if len(vertices.shape) == 2 and vertices.shape[1] == 3:
                            min_bounds = np.min(vertices, axis=0)
                            max_bounds = np.max(vertices, axis=0)
                            min_bounds = tuple(min_bounds)
                            max_bounds = tuple(max_bounds)
                        else:
                            raise ValueError("Invalid vertex format")
                    except Exception:
                        raise ValueError("Could not process vertices")
                else:
                    raise ValueError("No bbox or verts in geometry")
                
                depth = abs(max_bounds[0] - min_bounds[0])
                width = abs(max_bounds[1] - min_bounds[1])
                height = abs(max_bounds[2] - min_bounds[2])
                
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
            logger.debug(f"Extracting materials for {element.is_a()} {element.id()}...")
            if hasattr(element, 'HasAssociations'):
                for assoc in element.HasAssociations:
                    if assoc.is_a("IfcRelAssociatesMaterial"):
                        material_select = assoc.RelatingMaterial
                        material_type = material_select.is_a()
                        logger.debug(f"Found material association: {material_type}")
                        material_info = self._extract_single_material(material_select)
                        if material_info:
                            all_materials.append(material_info)
                            # Use first material as primary
                            if not material_props:
                                material_props = material_info
                                logger.info(f"✓ Extracted primary material for {element.is_a()} {element.id()}: {material_info.get('name', 'Unknown')} (type: {material_type})")
            
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
            # This is CRITICAL for windows - they often have frame + glazing materials
            if hasattr(element, 'HasAssociations'):
                for assoc in element.HasAssociations:
                    if assoc.is_a("IfcRelAssociatesMaterial"):
                        material_select = assoc.RelatingMaterial
                        if material_select.is_a("IfcMaterialConstituentSet"):
                            # Use deep extraction method which handles constituents properly
                            logger.info(f"🔍 DEEP MATERIAL ANALYSIS: Found IfcMaterialConstituentSet for {element.is_a()} {element.id()}")
                            constituent_info = self._extract_single_material(material_select)
                            if constituent_info:
                                # Merge into material_props (override with constituent set if found)
                                material_props.update(constituent_info)  # Merge all properties
                                num_constituents = len(constituent_info.get('constituents', []))
                                logger.info(f"✓ Extracted material constituent set with {num_constituents} constituent(s)")
                                
                                # Log each constituent
                                for i, const in enumerate(constituent_info.get('constituents', [])):
                                    const_name = const.get('name', 'Unknown')
                                    const_type = []
                                    if const.get('is_glazing'):
                                        const_type.append('GLAZING')
                                    if const.get('is_frame'):
                                        const_type.append('FRAME')
                                    if const.get('is_panel'):
                                        const_type.append('PANEL')
                                    if const.get('is_opaque_panel') or const.get('is_opaque'):
                                        const_type.append('OPAQUE')
                                    type_str = '/'.join(const_type) if const_type else 'UNKNOWN'
                                    logger.info(f"  Constituent {i+1}: '{const_name}' - Type: {type_str}")
                                
                                if material_props.get('has_glazing'):
                                    logger.info(f"✓ Element {element.id()} has GLAZING material - confirmed as TRANSPARENT WINDOW")
                                if material_props.get('has_opaque_panel'):
                                    logger.info(f"✓ Element {element.id()} has OPAQUE PANEL material - confirmed as SOLID PANEL")
                                if material_props.get('window_type_classification'):
                                    logger.info(f"✓ Window type classification: {material_props['window_type_classification'].upper()}")
            
            # Method 4: ULTRA-DEEP - For windows, check window parts (panes, frames) for materials
            # Windows can have materials assigned to individual parts (glazing panes, frames, etc.)
            if element.is_a("IfcWindow"):
                window_parts_materials = []
                try:
                    if hasattr(element, 'IsDecomposedBy') and element.IsDecomposedBy:
                        for decomp_rel in element.IsDecomposedBy:
                            if hasattr(decomp_rel, 'RelatedObjects'):
                                for part in decomp_rel.RelatedObjects:
                                    # Extract materials from window parts (panes, frames, etc.)
                                    part_material = self._extract_material_properties(part)
                                    if part_material:
                                        part_material['part_type'] = part.is_a()
                                        part_material['part_id'] = part.id()
                                        window_parts_materials.append(part_material)
                                        logger.debug(f"Found material for window part {part.is_a()} {part.id()}: {part_material.get('name', 'Unknown')}")
                                        
                                        # Merge glazing/opaque flags from parts
                                        if part_material.get('has_glazing'):
                                            material_props['has_glazing'] = True
                                            material_props['is_window_material'] = True
                                        if part_material.get('has_opaque_panel'):
                                            material_props['has_opaque_panel'] = True
                                        
                                        # If part has constituents, merge them
                                        if 'constituents' in part_material:
                                            if 'constituents' not in material_props:
                                                material_props['constituents'] = []
                                            material_props['constituents'].extend(part_material['constituents'])
                                        
                                        # If part has layers, merge them
                                        if 'layers' in part_material:
                                            if 'layers' not in material_props:
                                                material_props['layers'] = []
                                            material_props['layers'].extend(part_material['layers'])
                except Exception as e:
                    logger.debug(f"Error extracting materials from window parts for {element.id()}: {e}")
                
                if window_parts_materials:
                    material_props['window_parts_materials'] = window_parts_materials
                    logger.info(f"Window {element.id()}: Found materials from {len(window_parts_materials)} window part(s)")
            
            # Method 5: ULTRA-DEEP - Check for materials in window representation items
            # Some IFC files store materials in representation items (IfcStyledItem)
            if element.is_a("IfcWindow"):
                try:
                    if hasattr(element, 'Representation') and element.Representation:
                        for representation in element.Representation.Representations:
                            if hasattr(representation, 'Items'):
                                for item in representation.Items:
                                    # Check if item has material/style information
                                    if hasattr(item, 'StyledByItem') and item.StyledByItem:
                                        for styled_item in item.StyledByItem:
                                            # Material information might be in styles
                                            if hasattr(styled_item, 'Styles') and styled_item.Styles:
                                                for style in styled_item.Styles:
                                                    # Try to extract material info from style
                                                    if hasattr(style, 'Name'):
                                                        style_name = style.Name
                                                        if any(keyword in style_name.lower() for keyword in ['glass', 'glazing', 'material']):
                                                            if 'name' not in material_props or not material_props.get('name'):
                                                                material_props['name'] = style_name
                                                            logger.debug(f"Found material name from style: {style_name}")
                except Exception as e:
                    logger.debug(f"Error checking representation items for materials: {e}")
            
            # Store all materials if multiple found
            if len(all_materials) > 1:
                material_props['all_materials'] = all_materials
                logger.debug(f"Found {len(all_materials)} material(s) for element {element.id()}")
            
            # ULTRA-DEEP: Final classification based on all collected material information
            if element.is_a("IfcWindow"):
                has_glazing = material_props.get('has_glazing', False)
                has_opaque_panel = material_props.get('has_opaque_panel', False)
                
                # Re-classify window type based on all collected materials
                if has_glazing and not has_opaque_panel:
                    material_props['window_type_classification'] = 'transparent_window'
                elif has_opaque_panel and not has_glazing:
                    material_props['window_type_classification'] = 'opaque_panel'
                elif has_glazing and has_opaque_panel:
                    material_props['window_type_classification'] = 'mixed_window'
                elif not has_glazing and not has_opaque_panel:
                    # No material info - keep existing classification or set to unknown
                    if 'window_type_classification' not in material_props:
                        material_props['window_type_classification'] = 'unknown'
                
                logger.info(f"Window {element.id()} final material classification: {material_props.get('window_type_classification', 'unknown')}")
            
            # ULTRA-DEEP: Log comprehensive material summary
            if material_props:
                logger.info(f"📋 MATERIAL EXTRACTION SUMMARY for {element.is_a()} {element.id()}:")
                logger.info(f"  - Material name: {material_props.get('name', 'Unknown')}")
                logger.info(f"  - Material type: {material_props.get('type', 'Unknown')}")
                logger.info(f"  - Has glazing: {material_props.get('has_glazing', False)}")
                logger.info(f"  - Has opaque panel: {material_props.get('has_opaque_panel', False)}")
                logger.info(f"  - Has frame: {material_props.get('has_frame', False)}")
                logger.info(f"  - Constituents count: {len(material_props.get('constituents', []))}")
                logger.info(f"  - Layers count: {len(material_props.get('layers', []))}")
                logger.info(f"  - Window parts materials: {len(material_props.get('window_parts_materials', []))}")
                logger.info(f"  - Classification: {material_props.get('window_type_classification', 'unknown')}")
            else:
                logger.warning(f"⚠ No material properties found for {element.is_a()} {element.id()}")
        
        except Exception as e:
            logger.warning(f"Error extracting material properties for element {element.id()}: {e}", exc_info=True)
        
        return material_props
    
    def _extract_single_material(self, material_select) -> Dict:
        """
        Extract properties from a single material entity with DEEP extraction.
        Extracts all material properties, including nested properties and constituent sets.
        
        Args:
            material_select: IFC material entity (IfcMaterial, IfcMaterialList, etc.)
        
        Returns:
            Dictionary with comprehensive material properties
        """
        material_props = {}
        
        try:
            # Handle different material types
            if material_select.is_a("IfcMaterial"):
                material = material_select
                material_props['name'] = material.Name if hasattr(material, 'Name') else None
                material_props['type'] = 'IfcMaterial'
                
                # DEEP extraction: Get ALL material properties (not just basic ones)
                if hasattr(material, 'HasProperties'):
                    material_props['properties'] = {}
                    for prop in material.HasProperties:
                        if hasattr(prop, 'Name'):
                            prop_name = prop.Name
                            
                            # Handle different property types comprehensively
                            if prop.is_a("IfcPropertySingleValue"):
                                if hasattr(prop, 'NominalValue') and prop.NominalValue:
                                    prop_value = prop.NominalValue
                                    if hasattr(prop_value, 'wrappedValue'):
                                        material_props['properties'][prop_name] = prop_value.wrappedValue
                                    else:
                                        material_props['properties'][prop_name] = prop_value
                            
                            elif prop.is_a("IfcPropertyBoundedValue"):
                                bounded = {}
                                if hasattr(prop, 'UpperBoundValue') and prop.UpperBoundValue:
                                    if hasattr(prop.UpperBoundValue, 'wrappedValue'):
                                        bounded['max'] = prop.UpperBoundValue.wrappedValue
                                    else:
                                        bounded['max'] = prop.UpperBoundValue
                                if hasattr(prop, 'LowerBoundValue') and prop.LowerBoundValue:
                                    if hasattr(prop.LowerBoundValue, 'wrappedValue'):
                                        bounded['min'] = prop.LowerBoundValue.wrappedValue
                                    else:
                                        bounded['min'] = prop.LowerBoundValue
                                if bounded:
                                    material_props['properties'][prop_name] = bounded
                            
                            elif prop.is_a("IfcPropertyListValue"):
                                if hasattr(prop, 'ListValues') and prop.ListValues:
                                    list_values = []
                                    for val in prop.ListValues:
                                        if hasattr(val, 'wrappedValue'):
                                            list_values.append(val.wrappedValue)
                                        else:
                                            list_values.append(val)
                                    material_props['properties'][prop_name] = list_values
                            
                            # Store property directly for backward compatibility
                            if prop_name not in material_props:
                                if hasattr(prop, 'NominalValue') and prop.NominalValue:
                                    prop_value = prop.NominalValue
                                    if hasattr(prop_value, 'wrappedValue'):
                                        material_props[prop_name] = prop_value.wrappedValue
                                    else:
                                        material_props[prop_name] = prop_value
                
                # Check for material category (important for identifying window materials)
                if hasattr(material, 'Category'):
                    material_props['category'] = material.Category
                
                # Check for material description
                if hasattr(material, 'Description'):
                    material_props['description'] = material.Description
            
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
                # Layered material - different materials for different layers
                layers = []
                for layer in material_select.MaterialLayers:
                    layer_info = {}
                    if hasattr(layer, 'Material') and layer.Material:
                        mat = layer.Material
                        if hasattr(mat, 'Name'):
                            layer_info['name'] = mat.Name
                        # DEEP extraction: Extract ALL properties from layer material
                        if hasattr(mat, 'HasProperties'):
                            layer_info['properties'] = {}
                            for prop in mat.HasProperties:
                                if hasattr(prop, 'Name'):
                                    prop_name = prop.Name
                                    if prop.is_a("IfcPropertySingleValue"):
                                        if hasattr(prop, 'NominalValue') and prop.NominalValue:
                                            prop_value = prop.NominalValue
                                            if hasattr(prop_value, 'wrappedValue'):
                                                layer_info['properties'][prop_name] = prop_value.wrappedValue
                                            else:
                                                layer_info['properties'][prop_name] = prop_value
                        
                        # ULTRA-DEEP: Analyze layer material to classify it
                        mat_name = layer_info.get('name', '').lower() if layer_info.get('name') else ''
                        mat_category = layer_info.get('category', '').lower() if layer_info.get('category') else ''
                        
                        # Check for glazing/glass materials
                        glazing_keywords = ['glass', 'glazing', 'verre', 'стекло', 'vitrage', 'pane', 'transparent', 'translucent']
                        if any(keyword in mat_name for keyword in glazing_keywords) or 'glazing' in mat_category:
                            layer_info['is_glazing'] = True
                            material_props['has_glazing'] = True
                            material_props['is_window_material'] = True
                            logger.debug(f"Layer '{layer_info.get('name')}' identified as GLAZING")
                        
                        # Check for opaque/solid panel materials
                        opaque_keywords = ['opaque', 'solid', 'metal', 'steel', 'aluminum', 'wood', 'timber', 'пластик', 'panel', 'панель']
                        if any(keyword in mat_name for keyword in opaque_keywords) or 'opaque' in mat_category:
                            layer_info['is_opaque'] = True
                            material_props['has_opaque_panel'] = True
                            logger.debug(f"Layer '{layer_info.get('name')}' identified as OPAQUE")
                        
                        # ULTRA-DEEP: Check layer properties for transparency/transmittance
                        layer_props = layer_info.get('properties', {})
                        transparency = None
                        for prop_key in ['Transparency', 'transparency', 'Transmittance', 'transmittance', 'VisibleTransmittance']:
                            if prop_key in layer_props:
                                try:
                                    transparency = float(layer_props[prop_key])
                                    layer_info['transparency'] = transparency
                                    logger.debug(f"Layer '{layer_info.get('name')}' has transparency: {transparency}")
                                    
                                    # Classify based on transparency
                                    if transparency < 0.1:
                                        layer_info['is_opaque'] = True
                                        material_props['has_opaque_panel'] = True
                                        logger.debug(f"Layer '{layer_info.get('name')}' is OPAQUE (transparency: {transparency})")
                                    elif transparency > 0.7:
                                        layer_info['is_transparent'] = True
                                        layer_info['is_glazing'] = True
                                        material_props['has_glazing'] = True
                                        material_props['is_window_material'] = True
                                        logger.debug(f"Layer '{layer_info.get('name')}' is TRANSPARENT (transparency: {transparency})")
                                    break
                                except:
                                    pass
                        
                        # Extract optical properties
                        for prop_key in ['Reflectance', 'reflectance', 'Emissivity', 'emissivity', 'SolarTransmittance', 'solar_transmittance']:
                            if prop_key in layer_props:
                                layer_info[prop_key.lower()] = layer_props[prop_key]
                    
                    if hasattr(layer, 'LayerThickness'):
                        layer_info['thickness'] = float(layer.LayerThickness)
                    if hasattr(layer, 'Category'):
                        layer_info['category'] = layer.Category
                    layers.append(layer_info)
                
                # ULTRA-DEEP: Classify window type based on material layers
                has_glazing = material_props.get('has_glazing', False)
                has_opaque_panel = material_props.get('has_opaque_panel', False)
                
                if has_glazing and not has_opaque_panel:
                    material_props['window_type_classification'] = 'transparent_window'
                    logger.info(f"Material layer set classified as TRANSPARENT WINDOW (has glazing, no opaque panel)")
                elif has_opaque_panel and not has_glazing:
                    material_props['window_type_classification'] = 'opaque_panel'
                    logger.info(f"Material layer set classified as OPAQUE PANEL (has opaque panel, no glazing)")
                elif has_glazing and has_opaque_panel:
                    material_props['window_type_classification'] = 'mixed_window'
                    logger.info(f"Material layer set classified as MIXED WINDOW (has both glazing and opaque panel)")
                material_props['layers'] = layers
                material_props['type'] = 'IfcMaterialLayerSet'
                
                # If material set has glazing, this is likely a window
                if material_props.get('has_glazing'):
                    logger.debug(f"Material layer set has glazing - likely window material")
            
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
                            # DEEP extraction: Extract ALL properties from profile material
                            if hasattr(mat, 'HasProperties'):
                                profile_info['properties'] = {}
                                for prop in mat.HasProperties:
                                    if hasattr(prop, 'Name'):
                                        prop_name = prop.Name
                                        if prop.is_a("IfcPropertySingleValue"):
                                            if hasattr(prop, 'NominalValue') and prop.NominalValue:
                                                prop_value = prop.NominalValue
                                                if hasattr(prop_value, 'wrappedValue'):
                                                    profile_info['properties'][prop_name] = prop_value.wrappedValue
                                                else:
                                                    profile_info['properties'][prop_name] = prop_value
                        if hasattr(profile, 'Category'):
                            profile_info['category'] = profile.Category
                        profiles.append(profile_info)
                material_props['profiles'] = profiles
                material_props['type'] = 'IfcMaterialProfileSet'
            
            elif material_select.is_a("IfcMaterialConstituentSet"):
                # ULTRA-DEEP: Material constituent set - different materials for different parts
                # CRITICAL for windows - they can have frame, glazing, panel, etc. as separate constituents
                # This is what distinguishes different window types (transparent vs. solid panels)
                constituents = []
                has_glazing = False
                has_frame = False
                has_panel = False
                has_opaque_panel = False
                
                if hasattr(material_select, 'MaterialConstituents'):
                    logger.debug(f"Found IfcMaterialConstituentSet with {len(material_select.MaterialConstituents)} constituent(s)")
                    
                    for constituent in material_select.MaterialConstituents:
                        constituent_info = {}
                        
                        # Extract material from constituent
                        if hasattr(constituent, 'Material') and constituent.Material:
                            mat = constituent.Material
                            if hasattr(mat, 'Name'):
                                constituent_info['name'] = mat.Name
                            
                            # DEEP extraction: Extract ALL properties from constituent material
                            if hasattr(mat, 'HasProperties'):
                                constituent_info['properties'] = {}
                                for prop in mat.HasProperties:
                                    if hasattr(prop, 'Name'):
                                        prop_name = prop.Name
                                        # Handle all property types
                                        if prop.is_a("IfcPropertySingleValue"):
                                            if hasattr(prop, 'NominalValue') and prop.NominalValue:
                                                prop_value = prop.NominalValue
                                                if hasattr(prop_value, 'wrappedValue'):
                                                    constituent_info['properties'][prop_name] = prop_value.wrappedValue
                                                else:
                                                    constituent_info['properties'][prop_name] = prop_value
                                        
                                        elif prop.is_a("IfcPropertyBoundedValue"):
                                            bounded = {}
                                            if hasattr(prop, 'UpperBoundValue') and prop.UpperBoundValue:
                                                if hasattr(prop.UpperBoundValue, 'wrappedValue'):
                                                    bounded['max'] = prop.UpperBoundValue.wrappedValue
                                                else:
                                                    bounded['max'] = prop.UpperBoundValue
                                            if hasattr(prop, 'LowerBoundValue') and prop.LowerBoundValue:
                                                if hasattr(prop.LowerBoundValue, 'wrappedValue'):
                                                    bounded['min'] = prop.LowerBoundValue.wrappedValue
                                                else:
                                                    bounded['min'] = prop.LowerBoundValue
                                            if bounded:
                                                constituent_info['properties'][prop_name] = bounded
                                        
                                        elif prop.is_a("IfcPropertyListValue"):
                                            if hasattr(prop, 'ListValues') and prop.ListValues:
                                                list_values = []
                                                for val in prop.ListValues:
                                                    if hasattr(val, 'wrappedValue'):
                                                        list_values.append(val.wrappedValue)
                                                    else:
                                                        list_values.append(val)
                                                constituent_info['properties'][prop_name] = list_values
                            
                            # Check material category (CRITICAL for distinguishing window parts)
                            if hasattr(mat, 'Category'):
                                constituent_info['category'] = mat.Category
                            
                            # Check material description
                            if hasattr(mat, 'Description'):
                                constituent_info['description'] = mat.Description
                            
                            # ULTRA-DEEP: Analyze material name and properties to classify constituent type
                            mat_name = constituent_info.get('name', '').lower() if constituent_info.get('name') else ''
                            mat_category = constituent_info.get('category', '').lower() if constituent_info.get('category') else ''
                            
                            # Check for glazing/glass materials
                            glazing_keywords = ['glass', 'glazing', 'verre', 'стекло', 'vitrage', 'pane', 'transparent', 'translucent']
                            if any(keyword in mat_name for keyword in glazing_keywords) or 'glazing' in mat_category:
                                constituent_info['is_glazing'] = True
                                has_glazing = True
                                material_props['has_glazing'] = True
                                material_props['is_window_material'] = True
                                logger.debug(f"Constituent '{constituent_info.get('name')}' identified as GLAZING")
                            
                            # Check for frame materials
                            frame_keywords = ['frame', 'рама', 'cadre', 'rahmen', 'mullion', 'transom']
                            if any(keyword in mat_name for keyword in frame_keywords) or 'frame' in mat_category:
                                constituent_info['is_frame'] = True
                                has_frame = True
                                logger.debug(f"Constituent '{constituent_info.get('name')}' identified as FRAME")
                            
                            # Check for panel materials (solid panels, opaque panels)
                            panel_keywords = ['panel', 'панель', 'panneau', 'plaque', 'solid', 'opaque', 'sheet']
                            opaque_keywords = ['opaque', 'solid', 'metal', 'steel', 'aluminum', 'wood', 'timber', 'пластик']
                            if any(keyword in mat_name for keyword in panel_keywords) or 'panel' in mat_category:
                                constituent_info['is_panel'] = True
                                has_panel = True
                                # Check if panel is opaque (not transparent)
                                if any(keyword in mat_name for keyword in opaque_keywords):
                                    constituent_info['is_opaque_panel'] = True
                                    has_opaque_panel = True
                                    logger.debug(f"Constituent '{constituent_info.get('name')}' identified as OPAQUE PANEL")
                                else:
                                    logger.debug(f"Constituent '{constituent_info.get('name')}' identified as PANEL")
                            
                            # Check material properties for transparency/transmittance
                            # These properties distinguish transparent windows from solid panels
                            props = constituent_info.get('properties', {})
                            
                            # Check for transparency property
                            transparency = None
                            for prop_key in ['Transparency', 'transparency', 'Transmittance', 'transmittance', 'VisibleTransmittance']:
                                if prop_key in props:
                                    try:
                                        transparency = float(props[prop_key])
                                        constituent_info['transparency'] = transparency
                                        logger.debug(f"Constituent '{constituent_info.get('name')}' has transparency: {transparency}")
                                        break
                                    except:
                                        pass
                            
                            # If transparency is low (< 0.1) or transmittance is low, it's likely opaque
                            if transparency is not None:
                                if transparency < 0.1:
                                    constituent_info['is_opaque'] = True
                                    has_opaque_panel = True
                                    logger.debug(f"Constituent '{constituent_info.get('name')}' is OPAQUE (transparency: {transparency})")
                                elif transparency > 0.7:
                                    constituent_info['is_transparent'] = True
                                    has_glazing = True
                                    material_props['has_glazing'] = True
                                    logger.debug(f"Constituent '{constituent_info.get('name')}' is TRANSPARENT (transparency: {transparency})")
                            
                            # Check for optical properties
                            for prop_key in ['Reflectance', 'reflectance', 'Emissivity', 'emissivity']:
                                if prop_key in props:
                                    constituent_info[prop_key.lower()] = props[prop_key]
                        
                        # Extract constituent category (CRITICAL for classification)
                        if hasattr(constituent, 'Category'):
                            constituent_category = constituent.Category
                            constituent_info['constituent_category'] = constituent_category
                            
                            # Use category to classify constituent
                            cat_lower = constituent_category.lower() if constituent_category else ''
                            if 'glazing' in cat_lower or 'glass' in cat_lower:
                                constituent_info['is_glazing'] = True
                                has_glazing = True
                                material_props['has_glazing'] = True
                            elif 'frame' in cat_lower:
                                constituent_info['is_frame'] = True
                                has_frame = True
                            elif 'panel' in cat_lower:
                                constituent_info['is_panel'] = True
                                has_panel = True
                                if 'opaque' in cat_lower or 'solid' in cat_lower:
                                    constituent_info['is_opaque_panel'] = True
                                    has_opaque_panel = True
                        
                        # Extract constituent name/description
                        if hasattr(constituent, 'Name'):
                            constituent_info['constituent_name'] = constituent.Name
                        if hasattr(constituent, 'Description'):
                            constituent_info['constituent_description'] = constituent.Description
                        
                        constituents.append(constituent_info)
                
                material_props['constituents'] = constituents
                material_props['type'] = 'IfcMaterialConstituentSet'
                material_props['has_glazing'] = has_glazing
                material_props['has_frame'] = has_frame
                material_props['has_panel'] = has_panel
                material_props['has_opaque_panel'] = has_opaque_panel
                
                # ULTRA-DEEP: Classify window type based on material constituents
                # This distinguishes transparent windows from solid panels
                if has_glazing and not has_opaque_panel:
                    material_props['window_type_classification'] = 'transparent_window'
                    material_props['is_window_material'] = True
                    logger.info(f"Material constituent set classified as TRANSPARENT WINDOW (has glazing, no opaque panel)")
                elif has_opaque_panel and not has_glazing:
                    material_props['window_type_classification'] = 'opaque_panel'
                    logger.info(f"Material constituent set classified as OPAQUE PANEL (has opaque panel, no glazing)")
                elif has_glazing and has_opaque_panel:
                    material_props['window_type_classification'] = 'mixed_window'
                    material_props['is_window_material'] = True
                    logger.info(f"Material constituent set classified as MIXED WINDOW (has both glazing and opaque panel)")
                elif has_panel:
                    material_props['window_type_classification'] = 'panel'
                    logger.info(f"Material constituent set classified as PANEL (has panel material)")
                else:
                    material_props['window_type_classification'] = 'unknown'
                
                logger.info(f"Material constituent set analysis: {len(constituents)} constituent(s), glazing={has_glazing}, frame={has_frame}, panel={has_panel}, opaque_panel={has_opaque_panel}")
            
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
    
    def _extract_comprehensive_element_metadata(self, element, shape=None) -> Dict:
        """
        Extract comprehensive metadata for an IFC element: type, color, and material.
        This is the ULTIMATE extraction method that combines all extraction strategies.
        
        Returns:
            Dictionary with comprehensive metadata:
            - element_type: Detailed type classification
            - element_type_hierarchy: Full IFC type hierarchy
            - element_name: Element name/identifier
            - element_global_id: Global unique identifier
            - color_style: Complete color and style information
            - material_properties: Complete material information
            - material_name: Primary material name
            - material_type: Material type (IfcMaterial, IfcMaterialLayerSet, etc.)
            - has_glazing: Whether element has glazing material
            - is_window: Whether element is a window
            - all_materials: List of all materials found
            - properties: Element properties
            - representation_type: Type of representation used
        """
        metadata = {
            'element_type': None,
            'element_type_hierarchy': [],
            'element_name': None,
            'element_global_id': None,
            'color_style': {},
            'material_properties': {},
            'material_name': None,
            'material_type': None,
            'has_glazing': False,
            'is_window': False,
            'all_materials': [],
            'properties': {},
            'representation_type': None
        }
        
        try:
            # TYPE DETECTION: Comprehensive element type classification
            element_type = element.is_a()
            metadata['element_type'] = element_type
            
            # Build type hierarchy (all parent types)
            type_hierarchy = []
            current_type = element_type
            while current_type:
                type_hierarchy.append(current_type)
                try:
                    # Get parent type from IFC schema
                    parent_type = self.ifc_file.schema.declaration_by_name(current_type)
                    if parent_type and hasattr(parent_type, 'supertype'):
                        current_type = parent_type.supertype().name() if parent_type.supertype() else None
                    else:
                        break
                except:
                    break
            metadata['element_type_hierarchy'] = type_hierarchy
            
            # ELEMENT IDENTIFICATION
            if hasattr(element, 'Name') and element.Name:
                metadata['element_name'] = str(element.Name)
            if hasattr(element, 'GlobalId') and element.GlobalId:
                metadata['element_global_id'] = str(element.GlobalId)
            elif hasattr(element, 'id'):
                metadata['element_global_id'] = f"#{element.id()}"
            
            # REPRESENTATION TYPE DETECTION
            if hasattr(element, 'Representation') and element.Representation:
                if hasattr(element.Representation, 'Representations'):
                    representations = element.Representation.Representations
                    if representations:
                        # Get representation identifiers/types
                        rep_types = []
                        for rep in representations:
                            if hasattr(rep, 'RepresentationIdentifier'):
                                rep_id = rep.RepresentationIdentifier
                                if rep_id:
                                    rep_types.append(str(rep_id))
                            if hasattr(rep, 'RepresentationType'):
                                rep_type = rep.RepresentationType
                                if rep_type:
                                    rep_types.append(str(rep_type))
                        if rep_types:
                            metadata['representation_type'] = ', '.join(rep_types)
            
            # COLOR EXTRACTION: Use all available methods
            # Method 1: From ifcopenshell shape (most reliable)
            color_from_shape = None
            if shape:
                try:
                    if hasattr(shape, 'styles') and shape.styles:
                        for style in shape.styles:
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
                                        break
                                elif hasattr(colour, 'Red') and hasattr(colour, 'Green') and hasattr(colour, 'Blue'):
                                    color_from_shape = (
                                        float(colour.Red),
                                        float(colour.Green),
                                        float(colour.Blue)
                                    )
                                    break
                except Exception as e:
                    logger.debug(f"Error extracting color from shape: {e}")
            
            # Method 2: Comprehensive color/style extraction from element
            color_style = self._extract_color_and_style(element)
            if color_style:
                metadata['color_style'] = color_style
                # If we got color from shape but not from element, use shape color
                if color_from_shape and 'color' not in color_style:
                    color_style['color'] = color_from_shape
                    color_style['color_source'] = 'ifcopenshell_shape'
                elif color_from_shape:
                    # Shape color takes priority
                    color_style['color'] = color_from_shape
                    color_style['color_source'] = 'ifcopenshell_shape'
            elif color_from_shape:
                # Only shape color available
                metadata['color_style'] = {
                    'color': color_from_shape,
                    'color_source': 'ifcopenshell_shape'
                }
            
            # Method 3: Window-specific color extraction
            if element_type == "IfcWindow" and not metadata['color_style'].get('color'):
                window_color = self._extract_window_specific_color(element)
                if window_color and 'color' in window_color:
                    metadata['color_style'].update(window_color)
                    metadata['color_style']['color_source'] = 'window_specific'
            
            # MATERIAL EXTRACTION: Comprehensive material properties
            material_props = self._extract_material_properties(element)
            if material_props:
                metadata['material_properties'] = material_props
                metadata['material_name'] = material_props.get('name')
                metadata['material_type'] = material_props.get('type')
                metadata['has_glazing'] = material_props.get('has_glazing', False)
                metadata['is_window_material'] = material_props.get('is_window_material', False)
                
                if 'all_materials' in material_props:
                    metadata['all_materials'] = material_props['all_materials']
                
                # Extract color from material if not already found
                if 'color_style' in material_props and not metadata['color_style'].get('color'):
                    mat_color_style = material_props['color_style']
                    if mat_color_style and 'color' in mat_color_style:
                        metadata['color_style'].update(mat_color_style)
                        metadata['color_style']['color_source'] = 'material'
            
            # WINDOW DETECTION: Comprehensive window identification
            if element_type == "IfcWindow":
                metadata['is_window'] = True
            elif element_type == "IfcPlate":
                # Check if plate is glazing
                plate_name = metadata.get('element_name', '').lower()
                if (metadata.get('has_glazing') or 
                    any(kw in plate_name for kw in ['glass', 'glazing', 'verre', 'стекло', 'vitrage', 'pane', 'window', 'окно'])):
                    metadata['is_window'] = True
            elif element_type == "IfcOpeningElement":
                # Check if opening is for window (not door)
                opening_name = metadata.get('element_name', '').lower()
                if opening_name:
                    if not any(kw in opening_name for kw in ['door', 'дверь', 'porte', 'tür', 'entrance']):
                        metadata['is_window'] = True
                else:
                    # Default: treat as window if no door keywords
                    metadata['is_window'] = True
            
            # PROPERTIES EXTRACTION: Get element properties
            try:
                if hasattr(element, 'IsDefinedBy'):
                    for prop_def in element.IsDefinedBy:
                        if prop_def.is_a("IfcRelDefinesByProperties"):
                            if hasattr(prop_def, 'RelatingPropertyDefinition'):
                                prop_set = prop_def.RelatingPropertyDefinition
                                if prop_set.is_a("IfcPropertySet"):
                                    if hasattr(prop_set, 'HasProperties'):
                                        for prop in prop_set.HasProperties:
                                            if hasattr(prop, 'Name'):
                                                prop_name = prop.Name
                                                if prop.is_a("IfcPropertySingleValue"):
                                                    if hasattr(prop, 'NominalValue') and prop.NominalValue:
                                                        prop_value = prop.NominalValue
                                                        if hasattr(prop_value, 'wrappedValue'):
                                                            metadata['properties'][prop_name] = prop_value.wrappedValue
                                                        else:
                                                            metadata['properties'][prop_name] = prop_value
            except Exception as e:
                logger.debug(f"Error extracting properties: {e}")
            
            # Note: Metadata storage in mesh happens after mesh creation
            # This method only extracts metadata, doesn't store it
            
        except Exception as e:
            logger.warning(f"Error extracting comprehensive metadata for element {element.id()}: {e}", exc_info=True)
        
        return metadata
    
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
            logger.info("=" * 80)
            logger.info("Generating 3D mesh from IFC geometry - COMPREHENSIVE EXTRACTION")
            logger.info("=" * 80)
            meshes = []
            
            # CRITICAL IMPROVEMENT: Process ALL IfcProduct elements directly
            # IfcProduct is the base class for ALL spatial/geometric elements in IFC
            # This ensures we capture EVERY element with geometry, regardless of type
            logger.info("Processing ALL IfcProduct elements for complete visualization...")
            logger.info("This includes: walls, windows, doors, slabs, roofs, columns, beams,")
            logger.info("  stairs, railings, spaces, openings, plates, and ALL other geometric elements")
            
            settings = geom.settings()
            
            # CRITICAL: Configure settings for maximum accuracy and completeness
            # Use world coordinates (ensures all geometry is in global coordinate system)
            try:
                if hasattr(settings, 'USE_WORLD_COORDS'):
                    settings.set(settings.USE_WORLD_COORDS, True)
                    logger.info("✓ World coordinates enabled (all transformations applied)")
            except Exception as e:
                logger.warning(f"Could not enable world coordinates: {e}")
            
            # Configure settings for better geometry and color extraction
            try:
                # Enable BREP data for better geometry quality (more accurate representation)
                if hasattr(settings, 'USE_BREP_DATA'):
                    settings.set(settings.USE_BREP_DATA, True)
                    logger.debug("✓ BREP data enabled")
                
                # Disable Python OpenCASCADE if causing issues (use C++ version for better performance)
                if hasattr(settings, 'USE_PYTHON_OPENCASCADE'):
                    settings.set(settings.USE_PYTHON_OPENCASCADE, False)
                    logger.debug("✓ Using C++ OpenCASCADE (better performance)")
                
                # Enable shell sewing for better geometry quality
                if hasattr(settings, 'SEW_SHELLS'):
                    settings.set(settings.SEW_SHELLS, True)
                    logger.debug("✓ Shell sewing enabled")
                
                # CRITICAL: Disable opening subtraction for visualization
                # Opening subtraction removes geometry from walls where windows/doors are located
                # This can make walls invisible or very thin, especially if they have many openings
                # For visualization, we want to see the full walls, and windows/doors are separate elements
                if hasattr(settings, 'DISABLE_OPENING_SUBTRACTION'):
                    settings.set(settings.DISABLE_OPENING_SUBTRACTION, True)  # DISABLE subtraction
                    logger.debug("✓ Opening subtraction DISABLED (walls will be fully visible)")
                
                # Enable material extraction
                if hasattr(settings, 'USE_MATERIAL_COLOR'):
                    settings.set(settings.USE_MATERIAL_COLOR, True)
                    logger.debug("✓ Material color extraction enabled")
                
                # Disable vertex welding for more accurate geometry (preserve all vertices)
                if hasattr(settings, 'WELD_VERTICES'):
                    settings.set(settings.WELD_VERTICES, False)
                    logger.debug("✓ Vertex welding disabled (preserve all vertices)")
            except Exception as e:
                logger.debug(f"Some geometry settings could not be configured: {e}")
            
            logger.info("IFC geometry settings configured for maximum accuracy and completeness")
            
            # CRITICAL: Get ALL IfcProduct elements including nested/aggregated parts
            # This ensures we capture EVERY geometric element, including:
            # - Main elements (walls, windows, doors, etc.)
            # - Building element parts (IfcBuildingElementPart)
            # - Element assemblies (IfcElementAssembly)
            # - Aggregated elements (via IfcRelAggregates)
            all_products = []
            processed_ids = set()  # Track processed elements to avoid duplicates
            
            try:
                # Get all IfcProduct elements (base class for all geometric elements)
                base_products = self.ifc_file.by_type("IfcProduct")
                logger.info(f"Found {len(base_products)} base IfcProduct element(s)")
                
                # Add all base products
                for product in base_products:
                    product_id = product.id()
                    if product_id not in processed_ids:
                        all_products.append(product)
                        processed_ids.add(product_id)
                
                # CRITICAL: Also get all building element parts and assemblies
                # These are often nested and might be missed
                try:
                    parts = self.ifc_file.by_type("IfcBuildingElementPart")
                    logger.info(f"Found {len(parts)} IfcBuildingElementPart element(s)")
                    for part in parts:
                        part_id = part.id()
                        if part_id not in processed_ids:
                            all_products.append(part)
                            processed_ids.add(part_id)
                except:
                    pass
                
                try:
                    assemblies = self.ifc_file.by_type("IfcElementAssembly")
                    logger.info(f"Found {len(assemblies)} IfcElementAssembly element(s)")
                    for assembly in assemblies:
                        assembly_id = assembly.id()
                        if assembly_id not in processed_ids:
                            all_products.append(assembly)
                            processed_ids.add(assembly_id)
                except:
                    pass
                
                # CRITICAL: Process aggregation relationships (IfcRelAggregates)
                # Elements can be aggregated (parent-child relationships)
                # We need to process both parent and children
                try:
                    aggregations = self.ifc_file.by_type("IfcRelAggregates")
                    logger.info(f"Found {len(aggregations)} IfcRelAggregates relationship(s)")
                    for agg_rel in aggregations:
                        # Process related objects (children)
                        if hasattr(agg_rel, 'RelatedObjects'):
                            for related_obj in agg_rel.RelatedObjects:
                                if related_obj.is_a("IfcProduct"):
                                    related_id = related_obj.id()
                                    if related_id not in processed_ids:
                                        all_products.append(related_obj)
                                        processed_ids.add(related_id)
                                        logger.debug(f"Added aggregated element: {related_obj.is_a()} {related_id}")
                except Exception as e:
                    logger.debug(f"Could not process aggregations: {e}")
                
                # CRITICAL: Process decomposition relationships (IsDecomposedBy)
                # Elements can be decomposed into parts (e.g., wall into wall parts)
                # We need to process both parent and decomposed parts
                try:
                    # Get all elements that might have decompositions
                    elements_with_decomp = []
                    for product in all_products:
                        if hasattr(product, 'IsDecomposedBy') and product.IsDecomposedBy:
                            elements_with_decomp.append(product)
                    
                    logger.info(f"Found {len(elements_with_decomp)} element(s) with decompositions")
                    for parent_elem in elements_with_decomp:
                        try:
                            for decomp_rel in parent_elem.IsDecomposedBy:
                                if hasattr(decomp_rel, 'RelatedObjects'):
                                    for part in decomp_rel.RelatedObjects:
                                        if part.is_a("IfcProduct"):
                                            part_id = part.id()
                                            if part_id not in processed_ids:
                                                all_products.append(part)
                                                processed_ids.add(part_id)
                                                logger.debug(f"Added decomposed part: {part.is_a()} {part_id} (from {parent_elem.is_a()} {parent_elem.id()})")
                        except Exception as e:
                            logger.debug(f"Error processing decomposition for {parent_elem.id()}: {e}")
                except Exception as e:
                    logger.debug(f"Could not process decompositions: {e}")
                
                # CRITICAL: Explicitly ensure walls and slabs are included
                # Some IFC files store walls/slabs in non-standard ways
                try:
                    # Get all walls (including standard case)
                    walls = self.ifc_file.by_type("IfcWall") + self.ifc_file.by_type("IfcWallStandardCase")
                    logger.info(f"Explicitly checking {len(walls)} wall element(s)...")
                    for wall in walls:
                        wall_id = wall.id()
                        if wall_id not in processed_ids:
                            all_products.append(wall)
                            processed_ids.add(wall_id)
                            logger.debug(f"Added wall element: {wall.is_a()} {wall_id}")
                    
                    # Get all slabs (floors/ceilings between layers)
                    slabs = self.ifc_file.by_type("IfcSlab")
                    logger.info(f"Explicitly checking {len(slabs)} slab element(s)...")
                    for slab in slabs:
                        slab_id = slab.id()
                        if slab_id not in processed_ids:
                            all_products.append(slab)
                            processed_ids.add(slab_id)
                            logger.debug(f"Added slab element: {slab.is_a()} {slab_id}")
                    
                    # Get all coverings (may include floors/ceilings)
                    coverings = self.ifc_file.by_type("IfcCovering")
                    logger.info(f"Explicitly checking {len(coverings)} covering element(s)...")
                    for covering in coverings:
                        covering_id = covering.id()
                        if covering_id not in processed_ids:
                            all_products.append(covering)
                            processed_ids.add(covering_id)
                            logger.debug(f"Added covering element: {covering.is_a()} {covering_id}")
                except Exception as e:
                    logger.debug(f"Error explicitly adding walls/slabs: {e}")
                
                logger.info(f"Total unique elements to process: {len(all_products)}")
                
            except Exception as e:
                logger.warning(f"Could not get all IfcProduct elements: {e}")
                # Fallback: try getting elements by common types
                logger.info("Falling back to processing specific element types...")
                all_products = []
                for element_type in ["IfcWindow", "IfcWall", "IfcWallStandardCase", "IfcSlab", "IfcDoor", 
                                     "IfcColumn", "IfcBeam", "IfcRoof", "IfcStair", "IfcSpace", 
                                     "IfcOpeningElement", "IfcPlate", "IfcRailing", "IfcCurtainWall", 
                                     "IfcBuildingElementProxy", "IfcBuildingElementPart", "IfcElementAssembly",
                                     "IfcCovering", "IfcMember", "IfcChimney", "IfcFooting", "IfcPile",
                                     "IfcRamp", "IfcRampFlight", "IfcBuildingElement"]:
                    try:
                        elements = self.ifc_file.by_type(element_type)
                        all_products.extend(elements)
                    except:
                        continue
                logger.info(f"Fallback found {len(all_products)} elements")
            
            total_elements = len(all_products)
            successful_elements = 0
            failed_elements = 0
            skipped_elements = 0
            element_type_counts = {}  # Track counts by type
            
            logger.info(f"Processing {total_elements} elements for geometry extraction...")
            logger.info(f"Element types found: {len(element_type_counts)} unique types")
            
            # Process each element
            for idx, element in enumerate(all_products):
                element_type = element.is_a()
                element_type_counts[element_type] = element_type_counts.get(element_type, 0) + 1
                
                # Log progress every 100 elements
                if (idx + 1) % 100 == 0:
                    logger.info(f"Progress: {idx + 1}/{total_elements} elements processed ({successful_elements} successful, {failed_elements} failed, {skipped_elements} skipped)")
                
                try:
                    # CRITICAL: Create shape from element with comprehensive representation handling
                    # IFC elements can have multiple representations:
                    # - Body (3D solid geometry) - PRIMARY
                    # - Axis (centerline/axis representation)
                    # - Box (bounding box)
                    # - Curve (2D curve representation)
                    # - FootPrint (footprint/plan view)
                    # - Surface (surface representation)
                    # - SweptSolid (extruded solid)
                    # - Brep (boundary representation)
                    # - CSG (constructive solid geometry)
                    # We try ALL representations to ensure we get geometry
                    # CRITICAL: For walls and slabs, we MUST get geometry - these are essential building elements
                    shape = None
                    representation_index = 0
                    max_representations = 20  # INCREASED: Try up to 20 different representations (walls/slabs may use many)
                    representation_types = []  # Track which representations we tried
                    
                    # CRITICAL: For structural elements, be more aggressive in trying representations
                    is_structural = element_type in ["IfcWall", "IfcWallStandardCase", "IfcSlab", "IfcRoof", 
                                                     "IfcColumn", "IfcBeam", "IfcCovering", "IfcBuildingElement"]
                    if is_structural:
                        max_representations = 30  # Even more attempts for structural elements
                        logger.debug(f"Processing structural element {element_type} {element.id()} - will try up to {max_representations} representations")
                    
                    while shape is None and representation_index < max_representations:
                        try:
                            # Try creating shape with specific representation index
                            if representation_index == 0:
                                # First try: default representation (usually Body)
                                try:
                                    shape = geom.create_shape(settings, element)
                                    representation_types.append("default")
                                except Exception as default_error:
                                    # If default fails, try with explicit representation index 0
                                    try:
                                        shape = geom.create_shape(settings, element, 0)
                                        representation_types.append("repr_0")
                                    except:
                                        representation_index += 1
                                        continue
                            else:
                                # Try other representations explicitly
                                try:
                                    shape = geom.create_shape(settings, element, representation_index)
                                    representation_types.append(f"repr_{representation_index}")
                                except Exception as repr_error:
                                    # If representation index doesn't exist, try next
                                    representation_index += 1
                                    continue
                            
                            # Validate shape has geometry
                            if shape and hasattr(shape, 'geometry') and shape.geometry:
                                # Check if geometry has valid data
                                geometry = shape.geometry
                                has_valid_data = False
                                
                                # Check for vertices/faces
                                if hasattr(geometry, 'verts') and hasattr(geometry, 'faces'):
                                    if len(geometry.verts) > 0 and len(geometry.faces) > 0:
                                        has_valid_data = True
                                elif hasattr(geometry, 'tessellation'):
                                    try:
                                        tess = geometry.tessellation()
                                        if tess and isinstance(tess, tuple) and len(tess) >= 2:
                                            if len(tess[0]) > 0 and len(tess[1]) > 0:
                                                has_valid_data = True
                                    except:
                                        pass
                                
                                if has_valid_data:
                                    logger.debug(f"✓ Created shape for {element_type} {element.id()} using {representation_types[-1]}")
                                    break
                                else:
                                    # Shape exists but has no valid geometry, try next representation
                                    shape = None
                                    representation_index += 1
                            else:
                                shape = None
                                representation_index += 1
                        except Exception as shape_error:
                            # Try next representation
                            shape = None
                            representation_index += 1
                            if representation_index >= max_representations:
                                # CRITICAL: For walls, slabs, and structural elements, log as warning (not debug)
                                # These are important building elements that should be visible
                                if element_type in ["IfcWall", "IfcWallStandardCase", "IfcSlab", "IfcRoof", 
                                                   "IfcColumn", "IfcBeam", "IfcCovering", "IfcBuildingElement"]:
                                    logger.warning(f"⚠ Could not create shape for {element_type} {element.id()} after {max_representations} attempts: {shape_error}")
                                else:
                                    logger.debug(f"Could not create shape for {element_type} {element.id()} after {max_representations} attempts: {shape_error}")
                                skipped_elements += 1
                                break
                    
                    if shape is None:
                        # CRITICAL: For walls, slabs, and structural elements, log as warning
                        if element_type in ["IfcWall", "IfcWallStandardCase", "IfcSlab", "IfcRoof", 
                                           "IfcColumn", "IfcBeam", "IfcCovering", "IfcBuildingElement"]:
                            logger.warning(f"⚠ No valid shape found for {element_type} {element.id()} (tried {len(representation_types)} representations) - THIS ELEMENT WILL NOT BE VISIBLE")
                        else:
                            logger.debug(f"No valid shape found for {element_type} {element.id()} (tried {len(representation_types)} representations)")
                        continue
                            
                    # Get geometry from shape
                    try:
                        geometry = shape.geometry
                        if not geometry:
                            # CRITICAL: For walls, slabs, and structural elements, log as warning
                            if element_type in ["IfcWall", "IfcWallStandardCase", "IfcSlab", "IfcRoof", 
                                               "IfcColumn", "IfcBeam", "IfcCovering", "IfcBuildingElement"]:
                                logger.warning(f"⚠ No geometry in shape for {element_type} {element.id()} - THIS ELEMENT WILL NOT BE VISIBLE")
                            else:
                                logger.debug(f"No geometry in shape for {element_type} {element.id()}")
                            skipped_elements += 1
                            continue
                    except Exception as geom_error:
                        # CRITICAL: For walls, slabs, and structural elements, log as warning
                        if element_type in ["IfcWall", "IfcWallStandardCase", "IfcSlab", "IfcRoof", 
                                           "IfcColumn", "IfcBeam", "IfcCovering", "IfcBuildingElement"]:
                            logger.warning(f"⚠ Error accessing geometry for {element_type} {element.id()}: {geom_error} - THIS ELEMENT WILL NOT BE VISIBLE")
                        else:
                            logger.debug(f"Error accessing geometry for {element_type} {element.id()}: {geom_error}")
                        failed_elements += 1
                        continue
                            
                    # Convert ifcopenshell geometry to trimesh
                    # Use multiple methods to ensure we extract geometry successfully
                    vertices = None
                    faces = None
                    
                    # Method 1: Use ifcopenshell tessellation (most reliable and recommended)
                    try:
                        if hasattr(geometry, 'tessellation'):
                            tess = geometry.tessellation()
                            if tess and isinstance(tess, tuple) and len(tess) >= 2:
                                vertices = np.array(tess[0], dtype=np.float64)
                                faces_data = tess[1]
                                faces = np.array(faces_data, dtype=np.int32)
                                if len(faces.shape) == 1 and len(faces) % 3 == 0:
                                    faces = faces.reshape(-1, 3)
                                logger.debug(f"✓ Extracted geometry using tessellation() for {element_type} {element.id()}")
                    except Exception as tess_error:
                        logger.debug(f"Tessellation method failed for {element_type} {element.id()}: {tess_error}")
                                
                    # Method 2: Direct access to geometry.verts and geometry.faces (standard ifcopenshell API)
                    if (vertices is None or faces is None) and hasattr(geometry, 'verts') and hasattr(geometry, 'faces'):
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
                                    logger.debug(f"Invalid vertex count for {element_type} {element.id()}: {len(vertices)} (not divisible by 3)")
                                    vertices = None
                            elif len(vertices.shape) == 2 and vertices.shape[1] != 3:
                                logger.debug(f"Invalid vertex shape for {element_type} {element.id()}: {vertices.shape}")
                                vertices = None
                            
                            if vertices is not None:
                                faces = np.array(faces_data, dtype=np.int32)
                                # Ensure faces are in shape (n, 3)
                                if len(faces.shape) == 1:
                                    if len(faces) % 3 == 0:
                                        faces = faces.reshape(-1, 3)
                                    else:
                                        logger.debug(f"Invalid face count for {element_type} {element.id()}: {len(faces)} (not divisible by 3)")
                                        faces = None
                                elif len(faces.shape) == 2 and faces.shape[1] != 3:
                                    logger.debug(f"Invalid face shape for {element_type} {element.id()}: {faces.shape}")
                                    faces = None
                                
                                # Validate data
                                if vertices is not None and faces is not None:
                                    if len(vertices) == 0 or len(faces) == 0:
                                        logger.debug(f"Empty geometry for {element_type} {element.id()}: {len(vertices)} vertices, {len(faces)} faces")
                                        vertices = None
                                        faces = None
                                    elif len(faces) > 0:
                                        max_vertex_idx = np.max(faces)
                                        if max_vertex_idx >= len(vertices):
                                            logger.debug(f"Face indices out of range for {element_type} {element.id()}: max index {max_vertex_idx}, but only {len(vertices)} vertices")
                                            vertices = None
                                            faces = None
                                        else:
                                            logger.debug(f"✓ Extracted geometry using verts/faces for {element_type} {element.id()}")
                        except Exception as e:
                            logger.debug(f"Failed to extract geometry using standard API for {element_type} {element.id()}: {e}")
                            vertices = None
                            faces = None
                                
                    # Method 3: Use shape's geometry data directly (fallback)
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
                                
                    # Method 4: Try accessing geometry data directly (last resort)
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
                                    logger.debug(f"✓ Extracted geometry using data.verts/faces for {element_type} {element.id()}")
                        except Exception as e:
                            logger.debug(f"Data access method failed for {element_type} {element.id()}: {e}")
                    
                    # Create mesh if we have valid data
                    if vertices is not None and faces is not None and len(vertices) > 0 and len(faces) > 0:
                        try:
                            # CRITICAL: Apply transformation matrix if available
                            # IMPORTANT: With USE_WORLD_COORDS enabled, ifcopenshell should already apply transformations
                            # However, some versions may not apply them correctly, especially for slabs/floors
                            # We check if transformation is needed by comparing matrix to identity
                            # For slabs specifically, we need to be careful - they might be in local coordinates
                            should_apply_transform = False
                            if hasattr(shape, 'transformation') and shape.transformation:
                                try:
                                    matrix = shape.transformation.matrix.data
                                    if len(matrix) >= 16:
                                        # Check if transformation matrix is identity (no transformation needed)
                                        identity = np.array([
                                            [1, 0, 0, 0],
                                            [0, 1, 0, 0],
                                            [0, 0, 1, 0],
                                            [0, 0, 0, 1]
                                        ])
                                        transform_matrix = np.array([
                                            [matrix[0], matrix[1], matrix[2], matrix[3]],
                                            [matrix[4], matrix[5], matrix[6], matrix[7]],
                                            [matrix[8], matrix[9], matrix[10], matrix[11]],
                                            [matrix[12], matrix[13], matrix[14], matrix[15]]
                                        ])
                                        
                                        # Check if matrix is significantly different from identity
                                        if not np.allclose(transform_matrix, identity, atol=1e-6):
                                            # Matrix is not identity - transformation is needed
                                            should_apply_transform = True
                                            
                                            # CRITICAL: For slabs/floors, we MUST apply transformation
                                            # They are often in local coordinates relative to building/storey
                                            # Even with USE_WORLD_COORDS, slabs might not be transformed correctly
                                            is_slab = element_type == "IfcSlab"
                                            
                                            if is_slab:
                                                # Log transformation matrix details for slabs
                                                translation = transform_matrix[:3, 3]
                                                rotation = transform_matrix[:3, :3]
                                                logger.info(f"Slab {element.id()} transformation detected:")
                                                logger.info(f"  Translation: ({translation[0]:.2f}, {translation[1]:.2f}, {translation[2]:.2f})")
                                                
                                                # Log mesh bounds before transformation
                                                if len(vertices) > 0:
                                                    bounds_before = np.array([np.min(vertices, axis=0), np.max(vertices, axis=0)])
                                                    center_before = np.mean(vertices, axis=0)
                                                    logger.info(f"  Bounds before: min={bounds_before[0]}, max={bounds_before[1]}, center={center_before}")
                                        
                                        # Apply transformation if needed
                                        if should_apply_transform:
                                            is_slab = element_type == "IfcSlab"
                                            
                                            # Apply transformation to all vertices
                                            # Add homogeneous coordinate (w=1) to vertices
                                            vertices_homogeneous = np.hstack([vertices, np.ones((len(vertices), 1))])
                                            # Transform: v' = M * v
                                            vertices_transformed = (transform_matrix @ vertices_homogeneous.T).T
                                            # Remove homogeneous coordinate
                                            vertices = vertices_transformed[:, :3]
                                            
                                            if is_slab:
                                                # Log mesh bounds after transformation
                                                if len(vertices) > 0:
                                                    bounds_after = np.array([np.min(vertices, axis=0), np.max(vertices, axis=0)])
                                                    center_after = np.mean(vertices, axis=0)
                                                    logger.info(f"  Bounds after: min={bounds_after[0]}, max={bounds_after[1]}, center={center_after}")
                                            
                                            logger.debug(f"Applied transformation matrix to {len(vertices)} vertices for {element_type} {element.id()}")
                                        else:
                                            # Transformation is identity - no transformation needed
                                            # But for slabs, log this for debugging
                                            if element_type == "IfcSlab":
                                                logger.info(f"Slab {element.id()} has identity transformation (USE_WORLD_COORDS may have already applied it)")
                                                # Log current position for debugging
                                                if len(vertices) > 0:
                                                    bounds = np.array([np.min(vertices, axis=0), np.max(vertices, axis=0)])
                                                    center = np.mean(vertices, axis=0)
                                                    logger.info(f"  Slab position: bounds={bounds}, center={center}")
                                except Exception as e:
                                    # CRITICAL: For slabs, log errors as warnings
                                    if element_type == "IfcSlab":
                                        logger.warning(f"⚠ Could not apply transformation matrix for slab {element.id()}: {e}")
                                    else:
                                        logger.debug(f"Could not apply transformation matrix for {element_type} {element.id()}: {e}")
                            
                            # CRITICAL: Validate and clean geometry before creating mesh
                            # Remove invalid faces (faces with out-of-range indices)
                            if len(faces) > 0:
                                max_vertex_idx = np.max(faces)
                                if max_vertex_idx >= len(vertices):
                                    # Filter out invalid faces
                                    valid_faces = []
                                    for face in faces:
                                        if all(0 <= idx < len(vertices) for idx in face):
                                            valid_faces.append(face)
                                    if len(valid_faces) > 0:
                                        faces = np.array(valid_faces, dtype=np.int32)
                                    else:
                                        logger.debug(f"All faces invalid for {element_type} {element.id()}")
                                        skipped_elements += 1
                                        continue
                            
                            # Create mesh
                            mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
                            
                            # CRITICAL: For structural elements (walls, slabs, floors), make them two-sided
                            # Structural elements should be visible from both inside and outside the building
                            # If faces are only on one side, they'll be visible from one direction but not the other
                            is_structural_for_two_sided = element_type in [
                                "IfcWall", "IfcWallStandardCase", "IfcSlab", "IfcRoof", 
                                "IfcColumn", "IfcBeam", "IfcCovering", "IfcBuildingElement"
                            ]
                            
                            if is_structural_for_two_sided and len(mesh.faces) > 0:
                                # Duplicate faces with reversed winding order to make mesh two-sided
                                # Original faces: [v0, v1, v2] → Reversed: [v0, v2, v1]
                                original_faces = mesh.faces.copy()
                                reversed_faces = original_faces[:, [0, 2, 1]]  # Reverse vertex order
                                
                                # Combine original and reversed faces
                                two_sided_faces = np.vstack([original_faces, reversed_faces])
                                
                                # Create new mesh with two-sided faces
                                mesh = trimesh.Trimesh(vertices=mesh.vertices, faces=two_sided_faces)
                                
                                logger.info(f"Made {element_type} {element.id()} two-sided: {len(original_faces)} faces → {len(two_sided_faces)} faces (visible from both sides)")
                            
                            # CRITICAL: For slabs/floors, log mesh information for debugging
                            if element_type == "IfcSlab":
                                if len(mesh.vertices) > 0:
                                    mesh_bounds = mesh.bounds
                                    mesh_center = mesh.centroid
                                    logger.info(f"Slab {element.id()} mesh created: {len(mesh.vertices)} vertices, {len(mesh.faces)} faces")
                                    logger.info(f"Slab {element.id()} bounds: min={mesh_bounds[0]}, max={mesh_bounds[1]}, center={mesh_center}")
                                else:
                                    logger.warning(f"⚠ Slab {element.id()} mesh is empty after creation!")
                            
                            # CRITICAL: Validate and clean the created mesh
                            if len(mesh.vertices) > 0 and len(mesh.faces) > 0:
                                # CRITICAL: For structural elements (walls, slabs), be more lenient with cleaning
                                # Don't remove too many faces - walls might have thin sections that are still valid
                                is_structural = element_type in ["IfcWall", "IfcWallStandardCase", "IfcSlab", "IfcRoof", 
                                                               "IfcColumn", "IfcBeam", "IfcCovering", "IfcBuildingElement"]
                                
                                # Remove degenerate faces (zero area)
                                try:
                                    # Calculate face areas
                                    face_areas = mesh.area_faces
                                    if len(face_areas) > 0:
                                        # For structural elements, use a more lenient threshold
                                        # Walls might have very thin sections that are still valid geometry
                                        if is_structural:
                                            min_area = 1e-12  # Very lenient threshold for structural elements
                                        else:
                                            min_area = 1e-10  # Standard threshold for other elements
                                        
                                        valid_mask = face_areas > min_area
                                        if np.any(valid_mask):
                                            if not np.all(valid_mask):
                                                # Some faces are degenerate, remove them
                                                # BUT: For structural elements, only remove if we still have enough faces left
                                                num_valid = np.sum(valid_mask)
                                                num_total = len(valid_mask)
                                                
                                                if is_structural:
                                                    # CRITICAL: For structural elements, be VERY lenient with face removal
                                                    # Even if many faces are "degenerate", they might still be valid thin sections
                                                    # Only remove faces if we can keep at least 1 face (absolute minimum)
                                                    # This prevents walls/slabs from disappearing completely
                                                    if num_valid >= 1:
                                                        mesh.update_faces(valid_mask)
                                                        logger.debug(f"Removed {np.sum(~valid_mask)} degenerate faces from {element_type} {element.id()} ({num_valid}/{num_total} faces remain)")
                                                    else:
                                                        # CRITICAL: Would remove ALL faces - keep original mesh even if "degenerate"
                                                        # Better to show something than nothing for structural elements
                                                        logger.warning(f"⚠ {element_type} {element.id()} would lose all faces during cleaning - keeping original mesh ({num_total} faces)")
                                                        # Don't update faces - keep original mesh
                                                else:
                                                    # For non-structural elements, remove degenerate faces normally
                                                    mesh.update_faces(valid_mask)
                                                    logger.debug(f"Removed {np.sum(~valid_mask)} degenerate faces from {element_type} {element.id()}")
                                except:
                                    # If area calculation fails, continue anyway
                                    pass
                                
                                # Ensure mesh is valid
                                if len(mesh.vertices) > 0 and len(mesh.faces) > 0:
                                    # COMPREHENSIVE METADATA EXTRACTION: Type, Color, Material
                                    # Extract metadata BEFORE applying colors (metadata extraction uses element, not mesh)
                                    element_metadata = self._extract_comprehensive_element_metadata(element, shape)
                                    
                                    # Extract and apply color/style from IFC element
                                    color_style = element_metadata.get('color_style', {})
                                    
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
                                                    if not color_from_shape and hasattr(colour, 'Red') and hasattr(colour, 'Green') and hasattr(colour, 'Blue'):
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
                                        
                                        # For windows, ALWAYS apply transparency (windows should be transparent)
                                        # CRITICAL: Slabs, floors, ceilings, walls should NEVER be transparent
                                        is_window = False
                                        
                                        # CRITICAL: Explicitly exclude structural elements from window detection
                                        # These should NEVER be transparent
                                        is_structural_element = element_type in [
                                            "IfcWall", "IfcWallStandardCase", "IfcSlab", "IfcRoof", 
                                            "IfcColumn", "IfcBeam", "IfcCovering", "IfcBuildingElement",
                                            "IfcChimney", "IfcFooting", "IfcPile", "IfcRamp", "IfcRampFlight"
                                        ]
                                        
                                        if is_structural_element:
                                            # Structural elements are NEVER windows - always opaque
                                            is_window = False
                                            logger.debug(f"Element {element_type} {element.id()} is structural - will be opaque (not transparent)")
                                        # Check if element is a window (comprehensive detection)
                                        elif element_type == "IfcWindow":
                                            is_window = True
                                        elif element.is_a("IfcPlate"):
                                            # Check if plate is a glazing panel (window)
                                            # BUT: Exclude if it's clearly a structural element (slab, floor, ceiling)
                                            plate_name = element.Name if hasattr(element, 'Name') else ''
                                            plate_name_lower = plate_name.lower() if plate_name else ''
                                            
                                            # CRITICAL: Check if plate is a structural element (slab, floor, ceiling, wall panel)
                                            is_structural_plate = any(keyword in plate_name_lower for keyword in [
                                                'slab', 'плита', 'floor', 'пол', 'ceiling', 'потолок', 
                                                'wall', 'стена', 'roof', 'крыша', 'deck', 'decking'
                                            ])
                                            
                                            if is_structural_plate:
                                                # This is a structural plate (slab/floor/ceiling) - NOT a window
                                                is_window = False
                                                logger.debug(f"Plate '{plate_name}' (ID: {element.id()}) is structural - will be opaque")
                                            else:
                                                # Check if plate is a glazing panel (window)
                                                # Method 1: Check material for glazing
                                                try:
                                                    material_props = self._extract_material_properties(element)
                                                    if material_props:
                                                        if material_props.get('has_glazing') or material_props.get('is_window_material'):
                                                            is_window = True
                                                        else:
                                                            material_name = material_props.get('name', '').lower() if material_props.get('name') else ''
                                                            if any(keyword in material_name for keyword in ['glass', 'glazing', 'verre', 'стекло', 'vitrage', 'pane']):
                                                                is_window = True
                                                except:
                                                    pass
                                                
                                                # Method 2: Check name for window keywords
                                                if not is_window and plate_name:
                                                    if any(keyword in plate_name_lower for keyword in ['window', 'окно', 'glazing', 'glass', 'pane', 'vitrage']):
                                                        is_window = True
                                                
                                                # Method 3: Check if plate has window-like geometry
                                                if not is_window:
                                                    try:
                                                        center, normal, size = self._extract_window_geometry(element)
                                                        width, height = size
                                                        # Windows are typically 0.3m - 3m in size
                                                        if 0.3 <= width <= 3.0 and 0.3 <= height <= 3.0:
                                                            is_window = True
                                                    except:
                                                        pass
                                                
                                                # DO NOT treat all plates as windows - only if they match window criteria
                                                # This prevents slabs/floors/ceilings from being transparent
                                        
                                        elif element.is_a("IfcOpeningElement"):
                                            # Check if opening is a window (not a door)
                                            # Method 1: Check if filled by door
                                            is_door = False
                                            if hasattr(element, 'HasFillings'):
                                                for filling_rel in element.HasFillings:
                                                    if hasattr(filling_rel, 'RelatedBuildingElement'):
                                                        if filling_rel.RelatedBuildingElement.is_a("IfcDoor"):
                                                            is_door = True
                                                            break
                                            
                                            # Method 2: Check name
                                            if not is_door:
                                                opening_name = element.Name if hasattr(element, 'Name') else ''
                                                if opening_name:
                                                    name_lower = opening_name.lower()
                                                    if any(keyword in name_lower for keyword in ['door', 'дверь', 'porte', 'tür', 'entrance']):
                                                        is_door = True
                                            
                                            # If not a door, it's likely a window
                                            if not is_door:
                                                is_window = True
                                                logger.debug(f"Treating IfcOpeningElement {element.id()} as window")
                                        
                                        # Apply transparency to windows ONLY (never to structural elements)
                                        # CRITICAL: Structural elements (slabs, floors, ceilings, walls) should NEVER be transparent
                                        if is_window and not is_structural_element:
                                            # Check material for glass/glazing to determine transparency level
                                            try:
                                                material_props = self._extract_material_properties(element)
                                                if material_props:
                                                    material_name = material_props.get('name', '').lower() if material_props.get('name') else ''
                                                    has_glazing = material_props.get('has_glazing', False)
                                                    
                                                    # If material is glass/glazing, make it more transparent
                                                    if has_glazing or any(keyword in material_name for keyword in ['glass', 'glazing', 'verre', 'стекло', 'vitrage']):
                                                        # Glass windows: 30-40% transparent (60-70% opaque)
                                                        transparency = 0.3
                                                        logger.debug(f"Applied high transparency to {element_type} {element.id()} (glass/glazing material)")
                                                    else:
                                                        # Regular windows: 20% transparent (80% opaque)
                                                        transparency = 0.2
                                                        logger.debug(f"Applied transparency to {element_type} {element.id()} (window element)")
                                                else:
                                                    # No material found, but it's a window - apply default transparency
                                                    transparency = 0.25  # 25% transparent = 75% opaque
                                                    logger.debug(f"Applied default transparency to {element_type} {element.id()} (window, no material)")
                                            except Exception as e:
                                                # Fallback: apply default transparency for windows
                                                transparency = 0.25
                                                logger.debug(f"Applied default transparency to {element_type} {element.id()} (window, error checking material: {e})")
                                        else:
                                            # NOT a window OR is a structural element - ensure fully opaque
                                            if is_structural_element:
                                                transparency = 0.0  # Fully opaque for structural elements
                                                logger.debug(f"Ensuring {element_type} {element.id()} is fully opaque (structural element)")
                                            else:
                                                # Use transparency from color_style if available, otherwise fully opaque
                                                transparency = color_style.get('transparency', 0.0) if color_style else 0.0
                                        
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
                                        # BUT: For windows, apply transparency even with default color
                                        # CRITICAL: Structural elements (slabs, floors, ceilings, walls) should NEVER be transparent
                                        is_window = False
                                        window_alpha = 255  # Default opaque
                                        
                                        # CRITICAL: Explicitly exclude structural elements from window detection
                                        is_structural_element = element_type in [
                                            "IfcWall", "IfcWallStandardCase", "IfcSlab", "IfcRoof", 
                                            "IfcColumn", "IfcBeam", "IfcCovering", "IfcBuildingElement",
                                            "IfcChimney", "IfcFooting", "IfcPile", "IfcRamp", "IfcRampFlight"
                                        ]
                                        
                                        if is_structural_element:
                                            # Structural elements are NEVER windows - always opaque
                                            is_window = False
                                            window_alpha = 255  # Fully opaque
                                            logger.debug(f"Element {element_type} {element.id()} is structural - using opaque default color")
                                        # Check if element is a window
                                        elif element_type == "IfcWindow":
                                            is_window = True
                                        elif element.is_a("IfcPlate"):
                                            # Check if plate is a glazing panel (window)
                                            # BUT: Exclude if it's clearly a structural element (slab, floor, ceiling)
                                            plate_name = element.Name if hasattr(element, 'Name') else ''
                                            plate_name_lower = plate_name.lower() if plate_name else ''
                                            
                                            # CRITICAL: Check if plate is a structural element (slab, floor, ceiling, wall panel)
                                            is_structural_plate = any(keyword in plate_name_lower for keyword in [
                                                'slab', 'плита', 'floor', 'пол', 'ceiling', 'потолок', 
                                                'wall', 'стена', 'roof', 'крыша', 'deck', 'decking'
                                            ])
                                            
                                            if is_structural_plate:
                                                # This is a structural plate (slab/floor/ceiling) - NOT a window
                                                is_window = False
                                                window_alpha = 255  # Fully opaque
                                                logger.debug(f"Plate '{plate_name}' (ID: {element.id()}) is structural - using opaque default color")
                                            else:
                                                # Check if plate is a glazing panel
                                                try:
                                                    material_props = self._extract_material_properties(element)
                                                    if material_props and (material_props.get('has_glazing') or material_props.get('is_window_material')):
                                                        is_window = True
                                                except:
                                                    pass
                                        elif element.is_a("IfcOpeningElement"):
                                            # Check if opening is a window (not a door)
                                            opening_name = element.Name if hasattr(element, 'Name') else ''
                                            if opening_name:
                                                name_lower = opening_name.lower()
                                                if not any(keyword in name_lower for keyword in ['door', 'дверь', 'porte', 'tür']):
                                                    is_window = True
                                            else:
                                                is_window = True
                                        
                                        # Apply transparency to windows even with default color
                                        # CRITICAL: Structural elements should NEVER be transparent
                                        if is_window and not is_structural_element:
                                            # Windows should be semi-transparent (75% opaque = 25% transparent)
                                            window_alpha = int(255 * 0.75)  # 75% opacity
                                            logger.debug(f"Applied transparency to {element_type} {element.id()} (window with default color)")
                                        elif is_structural_element:
                                            # Structural elements are always fully opaque
                                            window_alpha = 255  # Fully opaque
                                            logger.debug(f"Ensuring {element_type} {element.id()} is fully opaque (structural element with default color)")
                                        
                                        default_color = np.array([200, 200, 200, window_alpha], dtype=np.uint8)
                                        num_faces = len(mesh.faces)
                                        face_colors = np.tile(default_color, (num_faces, 1))
                                        mesh.visual.face_colors = face_colors
                                        
                                        # Log which element is missing color for debugging
                                        element_name = getattr(element, 'Name', 'Unnamed')
                                        element_id = getattr(element, 'GlobalId', element.id())
                                        if element_type == "IfcWindow" or is_window:
                                            logger.info(f"⚠ Window '{element_name}' (ID: {element_id}) has no color but transparency applied")
                                        else:
                                            logger.debug(f"⚠ No color found for {element_type} '{element_name}' (ID: {element_id}), using default gray")
                                    
                                    # Wrap color extraction in try/except for error handling
                                    try:
                                        pass  # Color extraction already done above
                                    except Exception as color_error:
                                        logger.warning(f"Error applying color to {element_type} {element.id()}: {color_error}")
                                        # Use default gray if color extraction fails
                                        # CRITICAL: Structural elements should NEVER be transparent, even on error
                                        is_structural_element = element_type in [
                                            "IfcWall", "IfcWallStandardCase", "IfcSlab", "IfcRoof", 
                                            "IfcColumn", "IfcBeam", "IfcCovering", "IfcBuildingElement",
                                            "IfcChimney", "IfcFooting", "IfcPile", "IfcRamp", "IfcRampFlight"
                                        ]
                                        
                                        if is_structural_element:
                                            # Structural elements are always fully opaque
                                            window_alpha = 255  # Fully opaque
                                            logger.debug(f"Ensuring {element_type} {element.id()} is fully opaque (structural element, color extraction error)")
                                        else:
                                            # For windows, apply transparency even on error
                                            is_window = (element_type == "IfcWindow" or 
                                                       (element.is_a("IfcPlate") and not is_structural_element) or 
                                                       element.is_a("IfcOpeningElement"))
                                            window_alpha = int(255 * 0.75) if is_window else 255  # 75% opacity for windows
                                            if is_window:
                                                logger.debug(f"Applied transparency to {element_type} {element.id()} (window, color extraction error)")
                                        
                                        default_color = np.array([200, 200, 200, window_alpha], dtype=np.uint8)
                                        num_faces = len(mesh.faces)
                                        face_colors = np.tile(default_color, (num_faces, 1))
                                        mesh.visual.face_colors = face_colors
                                    
                                    # Store comprehensive metadata with mesh
                                    try:
                                        # Store metadata in mesh for later access
                                        if not hasattr(mesh, 'metadata'):
                                            mesh.metadata = element_metadata
                                        else:
                                            mesh.metadata.update(element_metadata)
                                        
                                        # Also store in mesh visual for compatibility
                                        if not hasattr(mesh, 'visual'):
                                            mesh.visual = type('obj', (object,), {})()
                                        if not hasattr(mesh.visual, 'metadata'):
                                            mesh.visual.metadata = element_metadata
                                        
                                        # Log metadata extraction success
                                        logger.debug(f"✓ Extracted metadata for {element_metadata.get('element_type', 'Unknown')} "
                                                   f"{element_metadata.get('element_global_id', 'N/A')}: "
                                                   f"Color={'Yes' if element_metadata.get('color_style', {}).get('color') else 'No'}, "
                                                   f"Material={'Yes' if element_metadata.get('material_name') else 'No'}")
                                    except Exception as meta_error:
                                        logger.debug(f"Error storing metadata: {meta_error}")
                                    
                                    meshes.append(mesh)
                                    successful_elements += 1
                                    
                                    # CRITICAL: Log successful structural element creation
                                    if is_structural:
                                        logger.info(f"✓ Successfully created {element_type} {element.id()}: {len(mesh.vertices)} vertices, {len(mesh.faces)} faces - ADDED TO MESH")
                                else:
                                    # CRITICAL: For walls, slabs, and structural elements, log as warning
                                    if element_type in ["IfcWall", "IfcWallStandardCase", "IfcSlab", "IfcRoof", 
                                                       "IfcColumn", "IfcBeam", "IfcCovering", "IfcBuildingElement"]:
                                        logger.warning(f"⚠ Mesh became empty after cleaning for {element_type} {element.id()} - THIS ELEMENT WILL NOT BE VISIBLE")
                                    else:
                                        logger.debug(f"Mesh became empty after cleaning for {element_type} {element.id()}")
                                    skipped_elements += 1
                            else:
                                # CRITICAL: For walls, slabs, and structural elements, log as warning
                                if element_type in ["IfcWall", "IfcWallStandardCase", "IfcSlab", "IfcRoof", 
                                                   "IfcColumn", "IfcBeam", "IfcCovering", "IfcBuildingElement"]:
                                    logger.warning(f"⚠ Created mesh is empty for {element_type} {element.id()}: {len(mesh.vertices)} vertices, {len(mesh.faces)} faces - THIS ELEMENT WILL NOT BE VISIBLE")
                                else:
                                    logger.debug(f"Created mesh is empty for {element_type} {element.id()}: {len(mesh.vertices)} vertices, {len(mesh.faces)} faces")
                                skipped_elements += 1
                        except Exception as mesh_error:
                            # CRITICAL: For walls, slabs, and structural elements, log as warning
                            if element_type in ["IfcWall", "IfcWallStandardCase", "IfcSlab", "IfcRoof", 
                                               "IfcColumn", "IfcBeam", "IfcCovering", "IfcBuildingElement"]:
                                logger.warning(f"⚠ Failed to create trimesh from geometry for {element_type} {element.id()}: {mesh_error} - THIS ELEMENT WILL NOT BE VISIBLE")
                            else:
                                logger.debug(f"Failed to create trimesh from geometry for {element_type} {element.id()}: {mesh_error}")
                            failed_elements += 1
                    else:
                        # CRITICAL: For walls, slabs, and structural elements, log as warning
                        if element_type in ["IfcWall", "IfcWallStandardCase", "IfcSlab", "IfcRoof", 
                                           "IfcColumn", "IfcBeam", "IfcCovering", "IfcBuildingElement"]:
                            logger.warning(f"⚠ Could not extract valid geometry for {element_type} {element.id()} - THIS ELEMENT WILL NOT BE VISIBLE")
                        else:
                            logger.debug(f"Could not extract valid geometry for {element_type} {element.id()}")
                        skipped_elements += 1
                except Exception as e:
                    logger.debug(f"Error processing {element_type} {element.id()}: {e}")
                    failed_elements += 1
                    continue
            
            # Log comprehensive statistics with metadata extraction summary
            logger.info("=" * 80)
            logger.info("GEOMETRY EXTRACTION STATISTICS")
            logger.info("=" * 80)
            logger.info(f"Total elements processed: {total_elements}")
            logger.info(f"  ✓ Successful: {successful_elements} ({100*successful_elements/max(total_elements,1):.1f}%)")
            logger.info(f"  ✗ Failed: {failed_elements} ({100*failed_elements/max(total_elements,1):.1f}%)")
            logger.info(f"  ⊘ Skipped (no geometry): {skipped_elements} ({100*skipped_elements/max(total_elements,1):.1f}%)")
            logger.info("")
            logger.info("Elements by type:")
            for elem_type, count in sorted(element_type_counts.items(), key=lambda x: x[1], reverse=True):
                logger.info(f"  {elem_type}: {count}")
            
            # CRITICAL: Log structural element statistics
            structural_types = ["IfcWall", "IfcWallStandardCase", "IfcSlab", "IfcRoof", 
                              "IfcColumn", "IfcBeam", "IfcCovering", "IfcBuildingElement"]
            structural_count = sum(element_type_counts.get(st, 0) for st in structural_types)
            logger.info("")
            logger.info("STRUCTURAL ELEMENTS SUMMARY:")
            logger.info(f"  Total structural elements found: {structural_count}")
            for st in structural_types:
                count = element_type_counts.get(st, 0)
                if count > 0:
                    logger.info(f"    {st}: {count}")
            logger.info(f"  Total meshes created: {len(meshes)}")
            logger.info(f"  Structural elements should be visible in 3D viewer if meshes were created successfully")
            
            # CRITICAL: Check for missing structural elements (walls, slabs, etc.)
            structural_types = ["IfcWall", "IfcWallStandardCase", "IfcSlab", "IfcRoof", "IfcColumn", "IfcBeam", "IfcCovering"]
            missing_structural = []
            for struct_type in structural_types:
                try:
                    total_count = len(self.ifc_file.by_type(struct_type))
                    successful_count = sum(1 for m in meshes if hasattr(m, 'metadata') and m.metadata.get('element_type') == struct_type)
                    if total_count > 0 and successful_count == 0:
                        missing_structural.append(f"{struct_type}: {total_count} found, 0 displayed")
                    elif total_count > successful_count:
                        missing_structural.append(f"{struct_type}: {total_count} found, {successful_count} displayed")
                except:
                    pass
            
            if missing_structural:
                logger.warning("⚠ STRUCTURAL ELEMENTS MISSING FROM DISPLAY:")
                for msg in missing_structural:
                    logger.warning(f"  ⚠ {msg}")
                logger.warning("  These elements exist in the IFC file but could not be extracted/displayed")
                logger.warning("  This may indicate geometry representation issues in the IFC file")
            
            # METADATA EXTRACTION STATISTICS
            if meshes:
                logger.info("")
                logger.info("METADATA EXTRACTION SUMMARY:")
                elements_with_color = 0
                elements_with_material = 0
                elements_with_properties = 0
                window_count = 0
                material_types = {}
                
                for mesh in meshes:
                    # Check if mesh has metadata
                    metadata = None
                    if hasattr(mesh, 'metadata'):
                        metadata = mesh.metadata
                    elif hasattr(mesh, 'visual') and hasattr(mesh.visual, 'metadata'):
                        metadata = mesh.visual.metadata
                    
                    if metadata:
                        if metadata.get('color_style', {}).get('color'):
                            elements_with_color += 1
                        if metadata.get('material_name'):
                            elements_with_material += 1
                            mat_type = metadata.get('material_type', 'Unknown')
                            material_types[mat_type] = material_types.get(mat_type, 0) + 1
                        if metadata.get('properties'):
                            elements_with_properties += 1
                        if metadata.get('is_window'):
                            window_count += 1
                
                logger.info(f"  ✓ Elements with color: {elements_with_color}/{len(meshes)} ({100*elements_with_color/len(meshes):.1f}%)")
                logger.info(f"  ✓ Elements with material: {elements_with_material}/{len(meshes)} ({100*elements_with_material/len(meshes):.1f}%)")
                logger.info(f"  ✓ Elements with properties: {elements_with_properties}/{len(meshes)} ({100*elements_with_properties/len(meshes):.1f}%)")
                logger.info(f"  ✓ Windows detected: {window_count}")
                
                if material_types:
                    logger.info("  Material types found:")
                    for mat_type, count in sorted(material_types.items(), key=lambda x: x[1], reverse=True):
                        logger.info(f"    {mat_type}: {count}")
            
            logger.info("=" * 80)
            
            if not meshes:
                logger.warning("No valid meshes generated from IFC geometry")
                logger.warning("This could mean:")
                logger.warning("  - IFC file has no geometry data")
                logger.warning("  - Geometry extraction failed for all elements")
                logger.warning("  - IFC file uses unsupported geometry representation")
                
                # CRITICAL FIX: Try alternative approach - process ALL elements regardless of type
                logger.info("Attempting alternative geometry extraction: processing ALL IFC elements...")
                try:
                    # Get ALL elements that might have geometry
                    all_elements = []
                    for element_type in self.ifc_file.by_type("IfcProduct"):  # IfcProduct is base class for all spatial/geometric elements
                        try:
                            # Try to create shape for this element
                            shape = geom.create_shape(settings, element_type)
                            if shape and shape.geometry:
                                all_elements.append((element_type, shape))
                        except:
                            continue
                    
                    logger.info(f"Found {len(all_elements)} elements with geometry using alternative method")
                    
                    # Process these elements using the same reliable methods
                    for element, shape in all_elements:
                        try:
                            geometry = shape.geometry
                            vertices = None
                            faces = None
                            
                            # Try tessellation first (most reliable)
                            try:
                                if hasattr(geometry, 'tessellation'):
                                    tess = geometry.tessellation()
                                    if tess and isinstance(tess, tuple) and len(tess) >= 2:
                                        vertices = np.array(tess[0], dtype=np.float64)
                                        faces_data = tess[1]
                                        faces = np.array(faces_data, dtype=np.int32)
                                        if len(faces.shape) == 1 and len(faces) % 3 == 0:
                                            faces = faces.reshape(-1, 3)
                            except:
                                pass
                            
                            # Fallback to verts/faces
                            if (vertices is None or faces is None) and hasattr(geometry, 'verts') and hasattr(geometry, 'faces'):
                                try:
                                    verts = geometry.verts
                                    faces_data = geometry.faces
                                    
                                    vertices = np.array(verts, dtype=np.float64)
                                    if len(vertices.shape) == 1 and len(vertices) % 3 == 0:
                                        vertices = vertices.reshape(-1, 3)
                                    elif len(vertices.shape) != 2 or vertices.shape[1] != 3:
                                        continue
                                    
                                    faces = np.array(faces_data, dtype=np.int32)
                                    if len(faces.shape) == 1 and len(faces) % 3 == 0:
                                        faces = faces.reshape(-1, 3)
                                    elif len(faces.shape) != 2 or faces.shape[1] != 3:
                                        continue
                                except:
                                    continue
                            
                            # Create mesh if we have valid data
                            if vertices is not None and faces is not None and len(vertices) > 0 and len(faces) > 0:
                                max_vertex_idx = np.max(faces) if len(faces) > 0 else -1
                                if max_vertex_idx < len(vertices):
                                    mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
                                    if len(mesh.vertices) > 0 and len(mesh.faces) > 0:
                                        # Apply default color
                                        default_color = np.array([200, 200, 200, 255], dtype=np.uint8)
                                        num_faces = len(mesh.faces)
                                        face_colors = np.tile(default_color, (num_faces, 1))
                                        mesh.visual.face_colors = face_colors
                                        meshes.append(mesh)
                                        successful_elements += 1
                        except Exception as e:
                            logger.debug(f"Error processing element in alternative method: {e}")
                            continue
                    
                    if meshes:
                        logger.info(f"✓ Alternative method found {len(meshes)} meshes")
                    else:
                        logger.error("Alternative geometry extraction also failed - no meshes found")
                        return None
                except Exception as alt_error:
                    logger.error(f"Alternative geometry extraction failed: {alt_error}")
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
            
            # CRITICAL: Combine all meshes into one with proper handling
            if len(meshes) == 1:
                combined_mesh = meshes[0]
                logger.info(f"Using single mesh: {len(combined_mesh.vertices):,} vertices, {len(combined_mesh.faces):,} faces")
                if hasattr(combined_mesh.visual, 'face_colors') and combined_mesh.visual.face_colors is not None:
                    logger.info(f"Mesh has colors applied: {len(combined_mesh.visual.face_colors)} face colors")
            else:
                logger.info(f"Combining {len(meshes)} meshes into single mesh...")
                try:
                    # trimesh.util.concatenate preserves visual properties including colors
                    # This is the recommended way to combine multiple meshes
                    combined_mesh = trimesh.util.concatenate(meshes)
                    logger.info(f"✓ Successfully combined {len(meshes)} meshes")
                    if hasattr(combined_mesh.visual, 'face_colors') and combined_mesh.visual.face_colors is not None:
                        logger.info(f"Combined mesh has colors: {len(combined_mesh.visual.face_colors):,} face colors")
                except Exception as e:
                    logger.error(f"Failed to combine meshes using concatenate: {e}")
                    # Fallback: Try combining in batches if single concatenate fails
                    try:
                        logger.info("Attempting batch combination...")
                        batch_size = 100
                        current_mesh = meshes[0]
                        for i in range(1, len(meshes), batch_size):
                            batch = meshes[i:i+batch_size]
                            if len(batch) > 0:
                                batch_combined = trimesh.util.concatenate([current_mesh] + batch)
                                current_mesh = batch_combined
                        combined_mesh = current_mesh
                        logger.info(f"✓ Successfully combined {len(meshes)} meshes using batch method")
                    except Exception as e2:
                        logger.error(f"Batch combination also failed: {e2}")
                        # Last resort: use the first mesh
                        if meshes:
                            logger.warning("Using first mesh as fallback (some geometry may be missing)")
                            combined_mesh = meshes[0]
                        else:
                            return None
            
            # CRITICAL: Clean up and validate final mesh
            try:
                if hasattr(combined_mesh, 'process'):
                    logger.info("Processing final mesh (removing duplicates, fixing normals, etc.)...")
                    # Process mesh to clean up geometry
                    # This removes duplicate vertices, fixes normals, etc.
                    combined_mesh.process()
                    logger.info("✓ Mesh processing complete")
            except Exception as e:
                logger.warning(f"Mesh processing failed (continuing anyway): {e}")
            
            # Final validation
            if len(combined_mesh.vertices) == 0 or len(combined_mesh.faces) == 0:
                logger.error("Final combined mesh has no geometry!")
                return None
            
            logger.info("=" * 80)
            logger.info(f"✓✓✓ MESH GENERATION COMPLETE ✓✓✓")
            logger.info(f"Final mesh: {len(combined_mesh.vertices):,} vertices, {len(combined_mesh.faces):,} faces")
            logger.info(f"Mesh bounds: min={combined_mesh.bounds[0]}, max={combined_mesh.bounds[1]}")
            logger.info(f"Mesh volume: {combined_mesh.volume:.2f} cubic units")
            if hasattr(combined_mesh.visual, 'face_colors') and combined_mesh.visual.face_colors is not None:
                logger.info(f"Colors applied: {len(combined_mesh.visual.face_colors):,} face colors")
            logger.info("=" * 80)
            return combined_mesh
            
        except Exception as e:
            logger.error(f"Error generating mesh from IFC: {e}", exc_info=True)
            return None

