# REVIT Plugin Integration Plan

## Overview

Creating a REVIT plugin would provide **perfect integration** with REVIT models, allowing:
- Direct access to REVIT elements (windows, rooms, building data)
- Real-time calculations within REVIT
- Results visualization directly in REVIT views
- No need to export to IFC/GLB
- Native REVIT element highlighting and annotation

## Architecture Options

### Option 1: pyRevit Plugin (Python-based)
**Advantages:**
- Can reuse existing Python calculation code
- Easier development (Python vs C#)
- Faster iteration
- Can share code with standalone application

**Requirements:**
- pyRevit framework
- REVIT API Python wrapper
- REVIT installation

### Option 2: Native REVIT Add-in (C#)
**Advantages:**
- Full REVIT API access
- Better performance
- Professional deployment
- Standard REVIT plugin format

**Requirements:**
- C# development
- REVIT API (Autodesk.Revit.dll)
- Visual Studio
- REVIT installation

### Option 3: Hybrid Approach
**Advantages:**
- REVIT plugin for UI and data extraction
- Python backend for calculations
- Best of both worlds

**Architecture:**
- REVIT Add-in (C#) → Extracts data → Calls Python calculation engine → Displays results

## Recommended: pyRevit Plugin

For this project, **pyRevit** is the best choice because:
1. **Code Reuse**: Can use existing Python calculation code directly
2. **Faster Development**: Python is easier than C# for this use case
3. **Maintainability**: Same codebase for standalone and plugin versions
4. **Flexibility**: Easy to update and extend

## Implementation Plan

### Phase 1: pyRevit Plugin Structure

```
solaris_revit_plugin/
├── __init__.py
├── commands/
│   ├── calculate_insolation.py      # REVIT command for insolation
│   ├── calculate_keo.py              # REVIT command for KEO
│   └── export_report.py             # Export results from REVIT
├── revit_extractor/
│   ├── building_extractor.py        # Extract building from REVIT
│   ├── window_extractor.py          # Extract windows from REVIT
│   └── room_extractor.py            # Extract rooms from REVIT
├── revit_ui/
│   ├── calculation_dialog.py        # REVIT dialog for parameters
│   └── results_panel.py             # Results display in REVIT
└── shared/
    ├── core/                         # Shared calculation engines
    └── models/                       # Shared data models
```

### Phase 2: REVIT Data Extraction

**Key Features:**
- Extract windows directly from REVIT `FamilyInstance` elements
- Extract rooms from REVIT `SpatialElement` (Room/Area)
- Extract building properties from REVIT project
- Use REVIT's native element properties and parameters

**Advantages over IFC/GLB:**
- No export needed - direct access
- Native REVIT element properties
- Accurate geometry from REVIT
- Real-time updates when model changes

### Phase 3: REVIT UI Integration

**Features:**
- REVIT ribbon tab with calculation buttons
- Dialog for calculation parameters (date, duration, etc.)
- Results panel showing compliance status
- Element highlighting in REVIT 3D view
- Annotation of results on REVIT views

### Phase 4: Results Visualization

**In REVIT:**
- Color-code windows by compliance status
- Add text annotations with results
- Create schedules with calculation results
- Generate views with highlighted non-compliant windows

## Code Structure

### REVIT Window Extractor Example

```python
# revit_extractor/window_extractor.py
from Autodesk.Revit import DB
from Autodesk.Revit.DB import FilteredElementCollector, BuiltInCategory

def extract_windows(doc):
    """Extract all windows from REVIT document."""
    windows = []
    
    # Get all window family instances
    collector = FilteredElementCollector(doc)
    window_elements = collector.OfCategory(BuiltInCategory.OST_Windows).WhereElementIsNotElementType().ToElements()
    
    for window_elem in window_elements:
        # Extract window properties
        window_id = window_elem.Id.ToString()
        
        # Get location
        location = window_elem.Location.Point
        
        # Get bounding box for size
        bbox = window_elem.get_BoundingBox(None)
        width = abs(bbox.Max.X - bbox.Min.X)
        height = abs(bbox.Max.Z - bbox.Min.Z)
        
        # Get window type parameters
        window_type = window_elem.Symbol
        transmittance = get_parameter_value(window_elem, "Glass_Transmittance", 0.75)
        frame_factor = get_parameter_value(window_elem, "Frame_Factor", 0.70)
        
        # Create Window object
        window = Window(
            id=window_id,
            center=(location.X, location.Y, location.Z),
            normal=get_window_normal(window_elem),
            size=(width, height),
            transmittance=transmittance,
            frame_factor=frame_factor
        )
        
        windows.append(window)
    
    return windows
```

### REVIT Command Example

```python
# commands/calculate_insolation.py
from pyrevit import script, revit
from Autodesk.Revit import DB

# Import shared calculation code
import sys
sys.path.append(r'path/to/solaris')
from core.insolation_calculator import InsolationCalculator

# Get REVIT document
doc = revit.doc

# Extract building data
from revit_extractor import extract_building
building = extract_building(doc)

# Run calculation (reuse existing code!)
from workflow import calculate_insolation
result = calculate_insolation(building, date.today(), timedelta(hours=1, minutes=30), config)

# Display results in REVIT
highlight_non_compliant_windows(doc, result)
show_results_dialog(result)
```

## Benefits of REVIT Plugin

1. **Direct Integration**: No export/import needed
2. **Real-time Updates**: Calculations update when model changes
3. **Native Highlighting**: Use REVIT's built-in element highlighting
4. **Annotations**: Add results directly to REVIT views
5. **Schedules**: Create REVIT schedules with calculation results
6. **Workflow**: Seamless integration with REVIT workflow

## Implementation Steps

1. **Setup pyRevit Environment**
   - Install pyRevit
   - Create plugin structure
   - Test basic REVIT API access

2. **Create REVIT Extractors**
   - Window extractor
   - Room extractor
   - Building extractor
   - Property extractor

3. **Integrate Calculation Engine**
   - Import existing calculation code
   - Adapt to REVIT data structures
   - Test calculations with REVIT data

4. **Create REVIT UI**
   - Ribbon buttons
   - Parameter dialogs
   - Results panels

5. **Add Visualization**
   - Element highlighting
   - Color coding
   - Annotations
   - Schedules

## Current Project Enhancement

While developing the plugin, we can also enhance the current standalone application:

1. **Better REVIT Export Support**
   - Guide users on optimal IFC export settings
   - Validate exported IFC files
   - Preserve REVIT properties in export

2. **REVIT-Specific Features**
   - Recognize REVIT window types
   - Use REVIT parameter names
   - Support REVIT room naming conventions

## Next Steps

Would you like me to:
1. **Create the pyRevit plugin structure** - Set up the plugin framework
2. **Implement REVIT extractors** - Extract windows/rooms from REVIT
3. **Integrate calculation engine** - Connect existing calculations to REVIT
4. **Create REVIT UI** - Add ribbon buttons and dialogs
5. **Enhance current app** - Better REVIT export support

Let me know which approach you prefer!

