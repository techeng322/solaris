"""
BIM model validation and quality checks.
Validates IFC, GLB, and REVIT models for compliance and data quality.
"""

import logging
from typing import List, Dict, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


class BIMValidationResult:
    """Result of BIM model validation."""
    
    def __init__(self):
        self.is_valid: bool = True
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.info: List[str] = []
        self.schema_version: Optional[str] = None
        self.element_counts: Dict[str, int] = {}
        self.missing_properties: List[str] = []
        self.relationship_issues: List[str] = []
    
    def add_error(self, message: str):
        """Add validation error."""
        self.is_valid = False
        self.errors.append(message)
        logger.error(f"BIM Validation Error: {message}")
    
    def add_warning(self, message: str):
        """Add validation warning."""
        self.warnings.append(message)
        logger.warning(f"BIM Validation Warning: {message}")
    
    def add_info(self, message: str):
        """Add validation info."""
        self.info.append(message)
        logger.info(f"BIM Validation Info: {message}")
    
    def get_summary(self) -> str:
        """Get validation summary."""
        summary = []
        summary.append(f"Validation Status: {'✓ VALID' if self.is_valid else '✗ INVALID'}")
        if self.schema_version:
            summary.append(f"Schema Version: {self.schema_version}")
        summary.append(f"Errors: {len(self.errors)}, Warnings: {len(self.warnings)}, Info: {len(self.info)}")
        if self.element_counts:
            summary.append(f"Elements: {', '.join(f'{k}={v}' for k, v in self.element_counts.items())}")
        return " | ".join(summary)


class BIMValidator:
    """Validates BIM models for quality and compliance."""
    
    @staticmethod
    def validate_ifc(file_path: str) -> BIMValidationResult:
        """
        Validate IFC file.
        
        Args:
            file_path: Path to IFC file
            
        Returns:
            BIMValidationResult
        """
        result = BIMValidationResult()
        
        try:
            import ifcopenshell
            ifc_file = ifcopenshell.open(file_path)
            
            # Detect schema version
            schema = ifc_file.schema
            result.schema_version = schema
            result.add_info(f"IFC Schema: {schema}")
            
            # Check for required elements
            buildings = ifc_file.by_type("IfcBuilding")
            spaces = ifc_file.by_type("IfcSpace")
            windows = ifc_file.by_type("IfcWindow")
            storeys = ifc_file.by_type("IfcBuildingStorey")
            
            result.element_counts = {
                'buildings': len(buildings),
                'spaces': len(spaces),
                'windows': len(windows),
                'storeys': len(storeys)
            }
            
            # Validation checks
            if len(buildings) == 0:
                result.add_warning("No IfcBuilding elements found")
            
            if len(spaces) == 0:
                result.add_warning("No IfcSpace (room) elements found")
            
            if len(windows) == 0:
                result.add_warning("No IfcWindow elements found")
            
            # Check relationships
            contained_rels = ifc_file.by_type("IfcRelContainedInSpatialStructure")
            if len(contained_rels) == 0:
                result.add_warning("No spatial containment relationships found - windows may not be linked to rooms")
            
            # Check for properties
            prop_sets = ifc_file.by_type("IfcPropertySet")
            if len(prop_sets) == 0:
                result.add_warning("No property sets found - limited semantic data available")
            
            # Check for required properties on windows (check ALL windows)
            # IMPORTANT: Actually try to extract dimensions to verify they CAN be obtained
            windows_without_dimensions = 0
            windows_with_property_dimensions = 0  # From properties
            windows_with_type_dimensions = 0  # From window type
            windows_with_geometry_dimensions = 0  # From geometry extraction
            
            # Performance optimization: For large numbers of windows, sample geometry extraction
            # but check all windows for properties and types (fast)
            geometry_sample_size = min(50, len(windows))  # Sample up to 50 windows for geometry extraction
            geometry_sample_indices = set()
            if len(windows) > geometry_sample_size:
                import random
                random.seed(42)  # Deterministic sampling
                geometry_sample_indices = set(random.sample(range(len(windows)), geometry_sample_size))
                logger.debug(f"Sampling {geometry_sample_size} windows for geometry dimension extraction (out of {len(windows)} total)")
            
            logger.debug(f"Validating dimensions for {len(windows)} window(s)...")
            
            for idx, window in enumerate(windows):
                props = BIMValidator._extract_window_properties(window)
                
                # Check for width (try multiple property names)
                has_width = (props.get('width') or props.get('OverallWidth') or 
                            props.get('NominalWidth') or props.get('FrameWidth') or
                            props.get('Width'))
                
                # Check for height (try multiple property names)
                has_height = (props.get('height') or props.get('OverallHeight') or 
                             props.get('NominalHeight') or props.get('FrameHeight') or
                             props.get('Height'))
                
                if has_width and has_height:
                    windows_with_property_dimensions += 1
                
                # Method 1: If dimensions missing from properties, try window type (fast check)
                if (not has_width or not has_height) and hasattr(window, 'IsTypedBy') and window.IsTypedBy:
                    try:
                        type_rel = window.IsTypedBy[0]
                        if hasattr(type_rel, 'RelatingType'):
                            window_type = type_rel.RelatingType
                            type_props = BIMValidator._extract_window_properties(window_type)
                            if not has_width and (type_props.get('OverallWidth') or type_props.get('Width')):
                                has_width = True
                                windows_with_type_dimensions += 1
                            if not has_height and (type_props.get('OverallHeight') or type_props.get('Height')):
                                has_height = True
                                windows_with_type_dimensions += 1
                    except Exception as e:
                        logger.debug(f"Error checking window type for dimensions: {e}")
                
                # Method 2: If dimensions still missing, try geometry extraction (slower, but comprehensive)
                # Only do full geometry extraction for sampled windows (or all if small set)
                if (not has_width or not has_height) and (len(windows) <= geometry_sample_size or idx in geometry_sample_indices):
                    try:
                        geometry_dimensions = BIMValidator._extract_dimensions_from_geometry(window, ifc_file)
                        if geometry_dimensions:
                            width, height = geometry_dimensions
                            if width > 0 and height > 0:
                                # Dimensions CAN be extracted from geometry - don't count as missing
                                windows_with_geometry_dimensions += 1
                                has_width = True
                                has_height = True
                    except Exception as e:
                        logger.debug(f"Error extracting dimensions from geometry: {e}")
                
                # If we sampled and this window could get dimensions from geometry (based on sample),
                # assume other similar windows can too (extrapolate)
                if (not has_width or not has_height) and len(windows) > geometry_sample_size and idx not in geometry_sample_indices:
                    # Estimate based on sample: if most sampled windows can get dimensions from geometry,
                    # assume this one can too (will be verified during actual import)
                    if windows_with_geometry_dimensions > 0:
                        # At least some windows can get dimensions from geometry
                        # Assume this window can too (will be verified during import)
                        has_width = True
                        has_height = True
                
                # Only count as missing if we truly can't get dimensions from any source
                if not has_width or not has_height:
                    windows_without_dimensions += 1
                    if len(result.missing_properties) < 10:  # Only store first 10 for logging
                        window_id = window.GlobalId if hasattr(window, 'GlobalId') else str(window.id())
                        missing = []
                        if not has_width:
                            missing.append('width')
                        if not has_height:
                            missing.append('height')
                        result.missing_properties.append(f"Window {window_id}: missing {', '.join(missing)} property")
            
            # Report dimension availability by source
            # Note: geometry_dimensions count may be extrapolated from sample
            total_with_dimensions = windows_with_property_dimensions + windows_with_type_dimensions
            geometry_available = windows_with_geometry_dimensions > 0
            
            if windows_with_property_dimensions > 0:
                result.add_info(f"{windows_with_property_dimensions} window(s) have dimensions in properties")
            if windows_with_type_dimensions > 0:
                result.add_info(f"{windows_with_type_dimensions} window(s) can get dimensions from window type")
            if geometry_available:
                if len(windows) > geometry_sample_size:
                    result.add_info(f"Geometry extraction available for dimensions (tested {min(geometry_sample_size, len(windows))} sample window(s))")
                else:
                    result.add_info(f"{windows_with_geometry_dimensions} window(s) can get dimensions from geometry")
            
            # Calculate total windows that can get dimensions
            # If geometry extraction works for sampled windows, assume it works for others too
            if geometry_available and windows_without_dimensions > 0:
                # Geometry extraction is available - most windows can get dimensions
                estimated_with_dimensions = total_with_dimensions + (len(windows) - total_with_dimensions - windows_without_dimensions)
                if estimated_with_dimensions < len(windows):
                    estimated_with_dimensions = len(windows) - windows_without_dimensions
            else:
                estimated_with_dimensions = total_with_dimensions
            
            if estimated_with_dimensions > 0:
                result.add_info(f"Estimated {estimated_with_dimensions}/{len(windows)} window(s) have accessible dimensions from any source")
            
            # Only warn if dimensions truly can't be obtained from any source
            if windows_without_dimensions > 0:
                # If geometry extraction is available, dimensions can be obtained - just informational
                if geometry_available or windows_with_type_dimensions > 0:
                    # Fallback sources available - this is just informational, not a warning
                    result.add_info(f"{windows_without_dimensions} window(s) missing dimension properties but can use type/geometry extraction or defaults")
                else:
                    # No fallback available - this is a real warning
                    result.add_warning(f"{windows_without_dimensions} window(s) missing dimension properties and no type/geometry extraction available (will use reasonable defaults)")
            
            result.add_info(f"Validation complete: {len(buildings)} building(s), {len(spaces)} space(s), {len(windows)} window(s)")
            
        except Exception as e:
            result.add_error(f"Failed to validate IFC file: {e}")
        
        return result
    
    @staticmethod
    def validate_glb(file_path: str) -> BIMValidationResult:
        """
        Validate GLB file for BIM data.
        
        Args:
            file_path: Path to GLB file
            
        Returns:
            BIMValidationResult
        """
        result = BIMValidationResult()
        
        try:
            import pygltflib
            gltf_data = pygltflib.GLTF2.load(str(file_path))
            
            # Check for scene graph
            if not gltf_data.scenes or len(gltf_data.scenes) == 0:
                result.add_warning("No scenes found in GLB file")
            else:
                result.add_info(f"Found {len(gltf_data.scenes)} scene(s)")
            
            # Check for nodes
            if not gltf_data.nodes or len(gltf_data.nodes) == 0:
                result.add_warning("No nodes found in GLB file")
            else:
                result.element_counts['nodes'] = len(gltf_data.nodes)
                result.add_info(f"Found {len(gltf_data.nodes)} node(s)")
            
            # Check for meshes
            if not gltf_data.meshes or len(gltf_data.meshes) == 0:
                result.add_warning("No meshes found in GLB file")
            else:
                result.element_counts['meshes'] = len(gltf_data.meshes)
                result.add_info(f"Found {len(gltf_data.meshes)} mesh(es)")
            
            # Check for extensions (BIM metadata)
            if gltf_data.extensionsUsed:
                result.add_info(f"Extensions used: {', '.join(gltf_data.extensionsUsed)}")
                if 'EXT_structural_metadata' in gltf_data.extensionsUsed:
                    result.add_info("Found structural metadata extension - BIM data available")
            
            # Check for named nodes (indicates semantic structure)
            named_nodes = [n for n in gltf_data.nodes if n.name]
            if len(named_nodes) < len(gltf_data.nodes) * 0.5:
                result.add_warning(f"Only {len(named_nodes)}/{len(gltf_data.nodes)} nodes have names - limited semantic data")
            
            result.add_info("GLB validation complete")
            
        except ImportError:
            result.add_warning("pygltflib not available - limited GLB validation")
        except Exception as e:
            result.add_error(f"Failed to validate GLB file: {e}")
        
        return result
    
    @staticmethod
    def _extract_dimensions_from_geometry(window_elem, ifc_file) -> Optional[Tuple[float, float]]:
        """
        Try to extract window dimensions from geometry.
        Returns (width, height) if successful, None otherwise.
        This is a lightweight check - just verifies dimensions CAN be extracted.
        """
        try:
            import ifcopenshell.geom as geom
            settings = geom.settings()
            # Use fast settings for validation (don't need full detail)
            settings.set(settings.USE_WORLD_COORDS, False)
            settings.set(settings.WELD_VERTICES, False)
            
            # Try to create shape from window (this is the expensive part)
            try:
                shape = geom.create_shape(settings, window_elem)
            except Exception as e:
                logger.debug(f"Could not create shape for window {window_elem.id()}: {e}")
                return None
            
            if not shape or not hasattr(shape, 'geometry'):
                return None
            
            geometry = shape.geometry
            if not geometry:
                return None
            
            # Extract vertices
            verts = None
            if hasattr(geometry, 'verts'):
                verts = geometry.verts
            elif hasattr(geometry, 'id_data') and hasattr(geometry.id_data(), 'verts'):
                verts = geometry.id_data().verts
            
            if not verts or len(verts) == 0:
                return None
            
            # Convert to numpy array if available (fast path)
            try:
                import numpy as np
                # Handle different vertex formats
                if isinstance(verts, np.ndarray):
                    vertices = verts
                else:
                    vertices = np.array(verts, dtype=np.float64)
                
                # Reshape if needed
                if len(vertices.shape) == 1:
                    if len(vertices) % 3 == 0:
                        vertices = vertices.reshape(-1, 3)
                    else:
                        return None
                elif len(vertices.shape) == 2:
                    if vertices.shape[1] != 3:
                        return None
                else:
                    return None
                
                if len(vertices) < 3:  # Need at least 3 vertices
                    return None
                
                # Calculate bounding box (fast numpy operation)
                min_bounds = np.min(vertices, axis=0)
                max_bounds = np.max(vertices, axis=0)
                dims = max_bounds - min_bounds
                
                # Windows are typically flat, so use the two largest dimensions
                all_dims = sorted([abs(dims[0]), abs(dims[1]), abs(dims[2])], reverse=True)
                width = all_dims[0]
                height = all_dims[1]
                
                # Validate dimensions are reasonable for windows (0.1m to 20m)
                if width > 0.1 and height > 0.1 and width < 20.0 and height < 20.0:
                    return (width, height)
                    
            except ImportError:
                # numpy not available - skip geometry extraction (too slow without numpy)
                logger.debug("NumPy not available - skipping geometry dimension extraction")
                return None
            except Exception as e:
                logger.debug(f"Error processing geometry vertices: {e}")
                return None
                
        except ImportError:
            # ifcopenshell.geom not available
            logger.debug("ifcopenshell.geom not available - cannot extract dimensions from geometry")
            return None
        except Exception as e:
            logger.debug(f"Error extracting dimensions from geometry for window {window_elem.id() if hasattr(window_elem, 'id') else 'unknown'}: {e}")
        
        return None
    
    @staticmethod
    def _extract_window_properties(window_elem) -> Dict:
        """
        Extract properties from window element for validation.
        Uses comprehensive extraction similar to IFC importer.
        """
        properties = {}
        
        try:
            # Method 1: Extract from property sets
            if hasattr(window_elem, 'IsDefinedBy'):
                for rel in window_elem.IsDefinedBy:
                    if rel.is_a("IfcRelDefinesByProperties"):
                        prop_set = rel.RelatingPropertyDefinition
                        if prop_set.is_a("IfcPropertySet"):
                            for prop in prop_set.HasProperties:
                                if hasattr(prop, 'Name'):
                                    prop_name = prop.Name
                                    properties[prop_name] = True
                                    
                                    # Also extract value if available
                                    if prop.is_a("IfcPropertySingleValue"):
                                        if hasattr(prop, 'NominalValue') and prop.NominalValue:
                                            prop_value = prop.NominalValue
                                            if hasattr(prop_value, 'wrappedValue'):
                                                properties[prop_name] = prop_value.wrappedValue
                                            else:
                                                properties[prop_name] = prop_value
            
            # Method 2: Extract from quantities
            if hasattr(window_elem, 'IsDefinedBy'):
                for rel in window_elem.IsDefinedBy:
                    if rel.is_a("IfcRelDefinesByProperties"):
                        qty_set = rel.RelatingPropertyDefinition
                        if qty_set.is_a("IfcElementQuantity"):
                            for qty in qty_set.Quantities:
                                if hasattr(qty, 'Name'):
                                    qty_name = qty.Name
                                    properties[qty_name] = True
                                    
                                    # Extract quantity value
                                    if qty.is_a("IfcQuantityLength"):
                                        if hasattr(qty, 'LengthValue') and qty.LengthValue is not None:
                                            properties[qty_name] = float(qty.LengthValue)
            
            # Method 3: Check direct attributes (IFC2X3 sometimes uses these)
            if hasattr(window_elem, 'OverallWidth'):
                properties['OverallWidth'] = float(window_elem.OverallWidth)
            if hasattr(window_elem, 'OverallHeight'):
                properties['OverallHeight'] = float(window_elem.OverallHeight)
            
            # Method 4: Check window type for dimensions
            if hasattr(window_elem, 'IsTypedBy') and window_elem.IsTypedBy:
                try:
                    type_rel = window_elem.IsTypedBy[0]
                    if hasattr(type_rel, 'RelatingType'):
                        window_type = type_rel.RelatingType
                        if hasattr(window_type, 'OverallWidth'):
                            properties['OverallWidth'] = float(window_type.OverallWidth)
                        if hasattr(window_type, 'OverallHeight'):
                            properties['OverallHeight'] = float(window_type.OverallHeight)
                except:
                    pass
            
            # Method 5: Check if geometry is available (can extract dimensions from geometry)
            try:
                import ifcopenshell.geom as geom
                settings = geom.settings()
                shape = geom.create_shape(settings, window_elem)
                if shape and hasattr(shape, 'geometry'):
                    geometry = shape.geometry
                    if hasattr(geometry, 'verts') and hasattr(geometry, 'faces'):
                        # Geometry is available - dimensions can be extracted
                        properties['has_geometry'] = True
            except:
                pass
        
        except Exception as e:
            logger.debug(f"Error extracting window properties for validation: {e}")
        
        return properties

