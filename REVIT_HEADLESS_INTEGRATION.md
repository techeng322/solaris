# REVIT Headless Integration

## Overview

This project now supports **direct REVIT (.rvt) file import** without requiring REVIT UI to be running. The integration uses REVIT API DLLs directly via Python.NET, allowing your standalone application to read REVIT files programmatically.

## How It Works

### Architecture

```
Standalone App → Python.NET (clr) → REVIT API DLLs → Read .rvt file → Extract data
```

**Key Points:**
- ✅ **No REVIT UI required** - Uses REVIT API DLLs directly
- ✅ **Headless operation** - REVIT doesn't need to be running
- ✅ **Same data extraction** - Uses same logic as REVIT plugin extractor
- ✅ **Integrated into workflow** - Works with existing import system

### Requirements

1. **REVIT Installation** (required for API DLLs)
   - REVIT must be installed (2019 or later)
   - DLLs are located in: `C:\Program Files\Autodesk\Revit {version}\`
   - REVIT UI does NOT need to run

2. **Python.NET** (for accessing .NET DLLs)
   ```bash
   pip install pythonnet
   ```

3. **REVIT API DLLs** (automatically detected)
   - The system searches for REVIT installation
   - Loads `RevitAPI.dll` automatically
   - Supports REVIT 2019-2025

## Usage

### In Your Application

Simply select a `.rvt` file - the system will automatically:

1. Detect REVIT installation
2. Load REVIT API DLLs via Python.NET
3. Open .rvt file in headless mode
4. Extract windows, rooms, and building data
5. Use the same calculation engine

**No changes needed in your workflow!**

### Code Example

```python
from importers.revit_importer import RevitImporter

# Import REVIT file directly (no UI needed)
importer = RevitImporter("building.rvt")
buildings = importer.import_model()

# Use buildings as usual
for building in buildings:
    print(f"Building: {building.name}")
    print(f"Windows: {len(building.windows)}")
```

## Implementation Details

### Files Created

1. **`importers/revit_headless.py`** (NEW)
   - `RevitHeadlessExtractor` class
   - Opens REVIT documents in headless mode
   - Extracts windows, rooms, building data
   - Uses context manager for automatic cleanup

### Files Modified

1. **`importers/revit_importer.py`**
   - Updated `_import_rvt_direct()` to use headless extractor
   - Updated `extract_windows()` to support .rvt files
   - Graceful fallback with helpful error messages

2. **`requirements.txt`**
   - Added comment about pythonnet (optional dependency)

## Features

### Data Extraction

- ✅ **Windows**: Extracted from `FamilyInstance` elements
- ✅ **Properties**: All REVIT parameters extracted
- ✅ **Geometry**: Position, size, orientation from bounding boxes
- ✅ **Materials**: Transmittance, frame factor, glass thickness
- ✅ **Location**: Building location from REVIT project settings

### Error Handling

- ✅ **Graceful fallback**: If REVIT API not available, suggests IFC export
- ✅ **Helpful messages**: Clear instructions if setup incomplete
- ✅ **Automatic detection**: Finds REVIT installation automatically

## Comparison: Plugin vs Headless

| Feature | REVIT Plugin | Headless Integration |
|---------|--------------|---------------------|
| **REVIT UI Required** | Yes (must run REVIT) | No (headless) |
| **REVIT Installation** | Required | Required (for DLLs) |
| **Use Case** | Work inside REVIT | Standalone app |
| **Data Access** | Direct from REVIT | Direct from .rvt file |
| **Code Reuse** | Shared extractor logic | Shared extractor logic |

## Installation

### Step 1: Install REVIT

REVIT must be installed (for API DLLs), but you don't need to run it:
- Download from Autodesk
- Install REVIT (any version 2019+)
- DLLs will be in: `C:\Program Files\Autodesk\Revit {version}\`

### Step 2: Install Python.NET

```bash
pip install pythonnet
```

### Step 3: Verify

The system will automatically:
1. Search for REVIT installation
2. Load REVIT API DLLs
3. Enable headless .rvt import

## Troubleshooting

### "REVIT API not available"

**Solution:**
1. Verify REVIT is installed
2. Check DLL path: `C:\Program Files\Autodesk\Revit {version}\RevitAPI.dll`
3. Install Python.NET: `pip install pythonnet`

### "Could not load REVIT API"

**Solution:**
1. Check REVIT version compatibility
2. Verify Python.NET is installed correctly
3. Try restarting the application

### "Failed to open REVIT document"

**Solution:**
1. Verify .rvt file is not corrupted
2. Check file permissions
3. Ensure file is not open in another application

## Benefits

✅ **No REVIT UI** - Work entirely in your standalone app  
✅ **Direct Access** - Read .rvt files without export  
✅ **Same Data** - Identical extraction as REVIT plugin  
✅ **Integrated** - Works with existing workflow  
✅ **Automatic** - No manual configuration needed  

## Alternative: IFC Export

If headless REVIT import is not available, you can still:
1. Export REVIT model to IFC format
2. Import IFC file (fully supported)
3. Get same calculation results

The headless integration is an **enhancement**, not a requirement!

## Status

✅ **IMPLEMENTED** - Headless REVIT integration complete  
✅ **READY TO USE** - Works with existing application  
✅ **OPTIONAL** - Falls back gracefully if not available  

Your standalone application can now read REVIT files directly! 🎉

