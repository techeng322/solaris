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
            
            # Check for required properties on windows
            for window in windows[:10]:  # Check first 10 windows
                props = BIMValidator._extract_window_properties(window)
                if not props.get('width') and not props.get('OverallWidth'):
                    result.missing_properties.append(f"Window {window.GlobalId}: missing width property")
                if not props.get('height') and not props.get('OverallHeight'):
                    result.missing_properties.append(f"Window {window.GlobalId}: missing height property")
            
            if result.missing_properties:
                result.add_warning(f"{len(result.missing_properties)} windows missing dimension properties")
            
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
    def _extract_window_properties(window_elem) -> Dict:
        """Extract properties from window element for validation."""
        properties = {}
        
        try:
            if hasattr(window_elem, 'IsDefinedBy'):
                for rel in window_elem.IsDefinedBy:
                    if rel.is_a("IfcRelDefinesByProperties"):
                        prop_set = rel.RelatingPropertyDefinition
                        if prop_set.is_a("IfcPropertySet"):
                            for prop in prop_set.HasProperties:
                                if hasattr(prop, 'Name'):
                                    properties[prop.Name] = True
        except Exception:
            pass
        
        return properties

