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
    
    def import_model(self) -> List[Building]:
        """
        Import IFC model.
        
        Returns:
            List of Building objects
        """
        try:
            self.ifc_file = ifcopenshell.open(self.file_path)
            
            # Detect and log IFC schema version
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
            raise ValueError(f"Failed to open IFC file: {e}")
        
        # Extract buildings
        buildings = []
        
        # Get all building elements
        buildings_elements = self.ifc_file.by_type("IfcBuilding")
        
        for building_elem in buildings_elements:
            building = self._extract_building(building_elem)
            if building:
                buildings.append(building)
        
        # If no buildings found, create a default building
        if not buildings:
            building = Building(
                id="Building_1",
                name="Building 1",
                location=(55.7558, 37.6173)  # Default to Moscow
            )
            # Extract windows directly
            windows = self.extract_windows()
            for window in windows:
                building.add_window(window)
            buildings.append(building)
        
        return buildings
    
    def _extract_building(self, building_elem) -> Optional[Building]:
        """Extract building from IFC element."""
        building_id = building_elem.GlobalId if hasattr(building_elem, 'GlobalId') else str(building_elem.id())
        building_name = building_elem.Name if hasattr(building_elem, 'Name') else f"Building {building_id}"
        
        building = Building(
            id=building_id,
            name=building_name
        )
        
        # Extract windows directly
        windows = self.extract_windows()
        for window in windows:
            building.add_window(window)
        
        return building
    
    def extract_windows(self) -> List[Window]:
        """
        Extract all windows from IFC model.
        
        Returns:
            List of Window objects
        """
        windows = []
        
        # Get all window elements
        window_elements = self.ifc_file.by_type("IfcWindow")
        
        for window_elem in window_elements:
            window = self._extract_window(window_elem)
            if window:
                windows.append(window)
        
        return windows
    
    def _extract_window(self, window_elem) -> Optional[Window]:
        """Extract window from IFC window element."""
        window_id = window_elem.GlobalId if hasattr(window_elem, 'GlobalId') else str(window_elem.id())
        
        # Extract geometry
        geometry = self._extract_geometry(window_elem)
        
        # Extract center and size
        center, normal, size = self._extract_window_geometry(window_elem)
        
        # Extract all properties (enhanced - supports all IFC property types)
        all_properties = self._extract_properties(window_elem)
        
        # Extract material properties
        material_props = self._extract_material_properties(window_elem)
        if material_props:
            all_properties['material'] = material_props
        
        # Recognize window type and properties
        window_props = self.recognize_window_type(window_elem)
        
        # Merge all properties
        window_props.update(all_properties)
        
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
        
        return window
    
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
        
        # Extract size from properties
        width = properties.get('OverallWidth', properties.get('Width', 1.5))
        height = properties.get('OverallHeight', properties.get('Height', 1.2))
        size = (float(width), float(height))
        
        # Extract position from properties or placement
        center = self._extract_window_position(window_elem, properties)
        
        # Extract normal (direction window faces) from placement
        normal = self._extract_window_normal(window_elem, properties)
        
        # If lightweight mode and properties available, use them
        if self.lightweight and properties:
            return center, normal, size
        
        # Otherwise, extract from geometry (more accurate but slower)
        try:
            if not self.lightweight:
                geom_center, geom_normal, geom_size = self._extract_geometry_from_ifc(window_elem)
                if geom_size[0] > 0 and geom_size[1] > 0:
                    return geom_center, geom_normal, geom_size
        except Exception as e:
            logger.debug(f"Geometry extraction failed, using properties: {e}")
        
        return center, normal, size
    
    def _extract_window_position(self, window_elem, properties: Dict) -> Tuple[float, float, float]:
        """Extract window position from IFC element placement or properties."""
        # Try to get from ObjectPlacement
        try:
            if hasattr(window_elem, 'ObjectPlacement') and window_elem.ObjectPlacement:
                placement = window_elem.ObjectPlacement
                # Extract coordinates from placement matrix
                if hasattr(placement, 'RelativePlacement') and placement.RelativePlacement:
                    location = placement.RelativePlacement.Location
                    if hasattr(location, 'Coordinates'):
                        coords = location.Coordinates
                        if len(coords) >= 3:
                            return (float(coords[0]), float(coords[1]), float(coords[2]))
        except Exception as e:
            logger.debug(f"Error extracting window position: {e}")
        
        # Fallback: use properties or default
        x = properties.get('X', 0.0)
        y = properties.get('Y', 0.0)
        z = properties.get('SillHeight', properties.get('Z', 1.5))
        return (float(x), float(y), float(z))
    
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
        """
        try:
            settings = geom.settings()
            shape = geom.create_shape(settings, element)
            geometry = shape.geometry
            
            # Get bounding box
            bbox = geometry.bbox
            min_bounds = bbox[0]
            max_bounds = bbox[1]
            
            # Calculate center
            center = (
                (min_bounds[0] + max_bounds[0]) / 2,
                (min_bounds[1] + max_bounds[1]) / 2,
                (min_bounds[2] + max_bounds[2]) / 2
            )
            
            # Calculate size (width, height)
            width = max_bounds[0] - min_bounds[0]
            height = max_bounds[2] - min_bounds[2]  # Z is typically height
            size = (width, height)
            
            # Default normal (would need more complex calculation for actual direction)
            normal = (0.0, 1.0, 0.0)
            
            return center, normal, size
        except Exception as e:
            logger.warning(f"Failed to extract geometry from IFC: {e}")
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

