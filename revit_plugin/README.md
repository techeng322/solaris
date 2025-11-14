# Solaris REVIT Plugin

REVIT add-in for insolation and KEO calculations, integrated directly into REVIT.

## Overview

This plugin brings the Solaris calculation engine directly into REVIT, allowing you to:
- Calculate insolation and KEO without exporting models
- See results directly in REVIT views
- Highlight non-compliant windows
- Generate reports from REVIT

## Installation

### Prerequisites
1. **REVIT** (2019 or later)
2. **pyRevit** - Install from: https://github.com/eirannejad/pyRevit

### Setup

1. **Install pyRevit:**
   ```bash
   # Download and install pyRevit
   # Follow instructions at: https://github.com/eirannejad/pyRevit
   ```

2. **Install Plugin:**
   - Copy `revit_plugin/` folder to pyRevit extensions directory
   - Or use pyRevit's extension manager

3. **Install Dependencies:**
   ```bash
   pip install numpy scipy shapely trimesh astral pytz pyyaml
   ```

## Usage

### In REVIT:

1. **Open REVIT model** with windows and rooms
2. **Go to pyRevit tab** → Solaris section
3. **Click "Calculate Insolation"** or "Calculate KEO"
4. **View results** in pyRevit output window
5. **Non-compliant windows** are automatically highlighted

### Features

- **Direct REVIT Integration**: No export/import needed
- **Real-time Calculations**: Use current REVIT model state
- **Element Highlighting**: See non-compliant windows in REVIT
- **Native Properties**: Use REVIT element parameters directly
- **Results in REVIT**: View results in pyRevit output panel

## Architecture

The plugin reuses the existing Solaris calculation engine:
- **Shared Code**: Same calculation logic as standalone app
- **REVIT Extractors**: Extract data from REVIT elements
- **REVIT UI**: pyRevit commands and dialogs
- **Results Display**: pyRevit output window

## Development

### File Structure

```
revit_plugin/
├── __init__.py
├── revit_extractor.py      # Extract data from REVIT
├── commands/
│   ├── calculate_insolation.py
│   ├── calculate_keo.py
│   └── export_report.py
└── README.md
```

### Adding New Commands

1. Create command file in `commands/` directory
2. Use `@script.record` decorator for pyRevit
3. Import shared calculation code
4. Extract data using `RevitExtractor`
5. Run calculations
6. Display results

## Benefits

✅ **No Export Needed** - Work directly with REVIT models  
✅ **Real-time Updates** - Calculations reflect current model state  
✅ **Native Integration** - Use REVIT's built-in features  
✅ **Code Reuse** - Same calculation engine as standalone app  
✅ **Professional Workflow** - Integrated into REVIT workflow  

## Status

🚧 **In Development** - Basic structure created, ready for implementation

