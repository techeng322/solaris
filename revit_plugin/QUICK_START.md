# Quick Start Guide - REVIT Plugin

## Prerequisites Checklist

- [ ] **REVIT is installed** (Autodesk Revit 2019 or later)
- [ ] **pyRevit is installed** (you should see "pyRevit" tab in REVIT)
- [ ] **Python dependencies** (numpy, scipy, etc.)

## Quick Installation (5 minutes)

### 1. Find pyRevit Extensions Folder

Open File Explorer and type in address bar:
```
%APPDATA%\pyRevit\Extensions\
```

This opens: `C:\Users\YourUsername\AppData\Roaming\pyRevit\Extensions\`

### 2. Copy Plugin Folder

Copy the entire `revit_plugin/` folder to:
```
%APPDATA%\pyRevit\Extensions\revit_plugin\
```

### 3. Copy Shared Code

Copy these from your project root to the plugin folder:
- `core/` folder
- `models/` folder  
- `utils/` folder
- `workflow.py` file
- `config.yaml` file

**Final structure should be:**
```
%APPDATA%\pyRevit\Extensions\revit_plugin\
├── __init__.py
├── extension.json
├── revit_extractor.py
├── revit_ui.py
├── workflow.py          ← Copied
├── config.yaml          ← Copied
├── core/                ← Copied
├── models/              ← Copied
├── utils/               ← Copied
└── commands/
    ├── calculate_insolation.py
    ├── calculate_keo.py
    └── calculate_both.py
```

### 4. Install Dependencies

Open Command Prompt and run:
```bash
pip install numpy scipy shapely trimesh astral pytz pyyaml
```

### 5. Reload in REVIT

1. **Open REVIT**
2. **Go to pyRevit tab**
3. **Click "Reload Extensions"** (or restart REVIT)
4. **Look for "Solaris" section** with three buttons

## Verify Installation

1. Open REVIT
2. Go to **pyRevit tab**
3. You should see **"Solaris"** section with buttons:
   - Calculate Insolation
   - Calculate KEO
   - Calculate Both

## First Use

1. **Open a REVIT model** that has windows
2. **Click "Calculate Insolation"** button
3. **Check pyRevit output window** for results
4. **Non-compliant windows** will be highlighted in REVIT

## Still Not Working?

### Check pyRevit is Installed

1. Open REVIT
2. Look for **"pyRevit"** tab in ribbon
3. If you don't see it, install pyRevit first

### Check Extension Folder

1. Open: `%APPDATA%\pyRevit\Extensions\`
2. Verify `revit_plugin/` folder exists
3. Check `extension.json` file is inside

### Check pyRevit Output

1. In REVIT: pyRevit tab → **Toggle Output** or **Show Output**
2. Look for error messages
3. Common errors:
   - "Module not found" → Install dependencies
   - "Extension not found" → Check folder location
   - "Import error" → Check shared code is copied

### Get Help

1. Check `INSTALLATION.md` for detailed troubleshooting
2. Review pyRevit output window for specific errors
3. Verify all files are in correct locations

## Alternative: Use Standalone App

If REVIT plugin is too complex, you can use the standalone GUI app:
```bash
python run_gui.py
```

This works with exported IFC/GLB files from REVIT.

