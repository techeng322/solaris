# BIM Model Integration - Complete Guide

## Overview

The Solaris project has **comprehensive BIM model integration** that supports multiple formats and utilizes BIM data throughout the application.

## Supported BIM Formats

### 1. IFC (Industry Foundation Classes)
- **Full Support**: IFC2X3, IFC4, IFC4X3 schemas
- **Lightweight Mode**: Semantic data extraction without heavy geometry processing
- **Property Extraction**: All IFC property types supported
- **Relationship-Based**: Uses IFC relationships for accurate linking

### 2. REVIT (RVT)
- **Via IFC Export**: Recommended method (full feature support)
- **Direct RVT**: Placeholder for REVIT API integration

### 3. GLB (3D Models)
- **Scene Graph Parsing**: Extracts hierarchical building structure
- **Metadata Support**: glTF extensions (EXT_structural_metadata, KHR_materials)
- **Geometry-Based Detection**: Finds windows from geometry characteristics

## BIM Data Utilization

### Properties Extracted from BIM Models

#### Building Properties
- Building name, ID, location
- Project information
- Building type, address
- IFC schema version

#### Window Properties
- **Geometry**: Position, size, orientation (center, normal, size)
- **Material Properties**: Glass thickness, transmittance, frame factor
- **BIM Properties**: OverallWidth, OverallHeight, Material, IfcType, GlobalId
- **Window Type**: Automatic recognition from BIM data

#### Room Properties
- Room geometry and dimensions
- Floor associations
- Spatial relationships

### How BIM Properties Are Used

1. **Calculations**:
   - Window transmittance from BIM material properties
   - Frame factor from window type recognition
   - Glass thickness for accurate calculations
   - Window dimensions from BIM geometry

2. **UI Display**:
   - Object Tree shows BIM properties
   - Building metadata displayed
   - Window properties visible in tree view

3. **Reports**:
   - BIM metadata included in reports
   - Property information in calculation results

## Recent Enhancements

### Enhanced Object Tree Display
- **Building Level**: Shows building name, location, and key BIM properties
- **Window Level**: Displays window size, type, and BIM properties (OverallWidth, OverallHeight, Material, IfcType, GlobalId)
- **Property Visibility**: Key BIM properties automatically shown in tree view

### BIM Property Extraction
- **Comprehensive**: All IFC property types supported
- **Material Properties**: Extracted from IfcMaterial relationships
- **Quantity Data**: Length, area, volume quantities extracted
- **Relationship-Based**: Uses IFC spatial relationships for accurate linking

## Using BIM Models

### Import Process

1. **Select Model**: Click "Select Model" and choose IFC/RVT/GLB file
2. **Automatic Validation**: BIM model is validated before import
3. **Property Extraction**: All BIM properties are extracted automatically
4. **Calculation Ready**: Model is ready for calculations with BIM data

### Viewing BIM Data

1. **Object Tree Tab**: View building hierarchy with BIM properties
2. **Property Details**: Click on building/window to see properties
3. **3D Viewer**: Visualize BIM model geometry
4. **Results Table**: See calculation results with BIM context

## BIM Validation

The project includes comprehensive BIM validation:

- **Schema Validation**: Checks IFC schema version
- **Element Validation**: Verifies required elements exist
- **Relationship Validation**: Checks spatial relationships
- **Property Validation**: Validates property completeness

## Best Practices

1. **IFC Files**: Use IFC format for best compatibility and feature support
2. **Property Sets**: Ensure windows have proper property sets in BIM model
3. **Material Data**: Include material properties for accurate calculations
4. **Spatial Relationships**: Use proper IFC relationships for room-window linking

## Technical Details

### Property Extraction
- Uses `IfcPropertySet` and `IfcElementQuantity` for semantic data
- Supports all 6 IFC property types
- Supports all 6 IFC quantity types
- Extracts material properties from `IfcRelAssociatesMaterial`

### Window Type Recognition
- Automatic detection from BIM properties
- Falls back to geometry-based recognition
- Uses configurable window type database

### Performance
- Lightweight mode for fast import
- Semantic data extraction (no heavy geometry processing)
- Efficient property caching

## Future Enhancements

Potential areas for further BIM integration:
- Enhanced BIM metadata panel
- BIM relationship visualization
- More BIM formats (DWG, OBJ, etc.)
- BIM property editing
- Export to BIM formats

