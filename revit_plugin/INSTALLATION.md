# REVIT Plugin Installation Guide

## Prerequisites

1. **REVIT** (2019 or later) - **MUST BE INSTALLED FIRST**
2. **pyRevit** - Python-based REVIT add-in framework
3. **Python 3.8+** (comes with pyRevit)

> **IMPORTANT**: pyRevit is an extension FOR REVIT. You must have REVIT installed first!

## Installation Steps

### Step 1: Verify REVIT Installation

**First, make sure REVIT is installed:**
1. Check if REVIT is installed: Look for "Autodesk Revit" in your Start menu
2. If not installed, download from: https://www.autodesk.com/products/revit/overview
3. Install REVIT first before proceeding

### Step 2: Install pyRevit

1. Download pyRevit from: https://github.com/eirannejad/pyRevit/releases
2. Run the installer
3. Follow the installation wizard
4. **Restart REVIT** after installation
5. Verify pyRevit is loaded:
   - Open REVIT
   - Look for **"pyRevit"** tab in the ribbon
   - If you see the pyRevit tab, installation was successful

### Step 3: Install Plugin

#### Option A: Manual Installation (Recommended)

1. **Find pyRevit extensions directory:**
   - Open File Explorer
   - Type in address bar: `%APPDATA%\pyRevit\Extensions\`
   - Press Enter
   - This should open: `C:\Users\YourUsername\AppData\Roaming\pyRevit\Extensions\`

2. **Copy the plugin folder:**
   - Copy the entire `revit_plugin/` folder from your project
   - Paste it into the Extensions directory
   - Final path should be: `%APPDATA%\pyRevit\Extensions\revit_plugin\`
   - **OR** rename it to `Solaris` if you prefer: `%APPDATA%\pyRevit\Extensions\Solaris\`

3. **Copy shared code (IMPORTANT):**
   - The plugin needs access to your calculation code
   - **Option 1 - Copy files:**
     - Copy these folders/files to the plugin directory:
       - `core/` → `%APPDATA%\pyRevit\Extensions\revit_plugin\core\`
       - `models/` → `%APPDATA%\pyRevit\Extensions\revit_plugin\models\`
       - `utils/` → `%APPDATA%\pyRevit\Extensions\revit_plugin\utils\`
       - `workflow.py` → `%APPDATA%\pyRevit\Extensions\revit_plugin\workflow.py`
       - `config.yaml` → `%APPDATA%\pyRevit\Extensions\revit_plugin\config.yaml`
   
   - **Option 2 - Create symlinks (Advanced):**
     ```bash
     # In Command Prompt (as Administrator)
     cd %APPDATA%\pyRevit\Extensions\revit_plugin
     mklink /D core "D:\Github\goTech007\solaris\core"
     mklink /D models "D:\Github\goTech007\solaris\models"
     mklink /D utils "D:\Github\goTech007\solaris\utils"
     mklink workflow.py "D:\Github\goTech007\solaris\workflow.py"
     mklink config.yaml "D:\Github\goTech007\solaris\config.yaml"
     ```
     (Adjust paths to match your project location)

4. **Verify folder structure:**
   ```
   %APPDATA%\pyRevit\Extensions\revit_plugin\
   ├── __init__.py
   ├── extension.json
   ├── revit_extractor.py
   ├── revit_ui.py
   ├── workflow.py          # Copied or symlinked
   ├── config.yaml          # Copied or symlinked
   ├── core/                # Copied or symlinked
   ├── models/              # Copied or symlinked
   ├── utils/               # Copied or symlinked
   └── commands/
       ├── __init__.py
       ├── calculate_insolation.py
       ├── calculate_keo.py
       └── calculate_both.py
   ```

#### Option B: Using pyRevit CLI

1. **Open Command Prompt**
2. **Navigate to your project directory:**
   ```bash
   cd D:\Github\goTech007\solaris
   ```
3. **Install extension using pyRevit CLI:**
   ```bash
   pyrevit extensions install revit_plugin
   ```
   (This may require the extension to be in a specific format)

### Step 4: Reload Extensions in REVIT

1. **Open REVIT**
2. **Go to pyRevit tab** in the ribbon
3. **Click "Reload Extensions"** or "Reload" button
4. **Check for errors** in pyRevit output window

### Step 5: Verify Plugin is Loaded

1. **In REVIT, go to pyRevit tab**
2. **Look for "Solaris" section** or check the extension list
3. **You should see three buttons:**
   - Calculate Insolation
   - Calculate KEO
   - Calculate Both

**If you don't see the buttons:**
- Check pyRevit output window for errors
- Verify folder structure matches above
- Make sure `extension.json` is valid JSON
- Try restarting REVIT completely

### Step 6: Install Python Dependencies

1. **Open pyRevit Command Prompt:**
   - In REVIT: pyRevit tab → Settings → Open pyRevit Command Prompt
   - **OR** use pyRevit CLI from regular Command Prompt

2. **Install dependencies:**
   ```bash
   pip install numpy scipy shapely trimesh astral pytz pyyaml
   ```

   Or install from requirements.txt (if in project directory):
   ```bash
   pip install -r requirements.txt
   ```

3. **Verify installation:**
   ```bash
   python -c "import numpy, scipy, shapely, trimesh, astral; print('All dependencies installed!')"
   ```

### Step 7: Test the Plugin

1. **Open a REVIT model** with windows
2. **Go to pyRevit tab** → Look for "Solaris" section
3. **Click "Calculate Insolation"** (or any button)
4. **Check pyRevit output window** for results or errors

## Usage

### In REVIT:

1. **Open REVIT model** with windows
2. **Go to pyRevit tab** → **Solaris** section
3. **Click calculation button:**
   - "Calculate Insolation" - Insolation only
   - "Calculate KEO" - KEO only
   - "Calculate Both" - Both calculations
4. **View results** in pyRevit output window
5. **Non-compliant windows** are automatically highlighted in REVIT view

### Features:

- **Direct REVIT Access**: No export/import needed
- **Real-time Calculations**: Uses current REVIT model
- **Element Highlighting**: See non-compliant windows
- **Results Display**: View in pyRevit output window
- **Code Reuse**: Same calculation engine as standalone app

## Troubleshooting

### Plugin Not Appearing in REVIT

**Step-by-step debugging:**

1. **Verify REVIT is installed:**
   - Open REVIT manually (not through pyRevit)
   - If REVIT doesn't open, install REVIT first

2. **Verify pyRevit is loaded:**
   - Open REVIT
   - Look for "pyRevit" tab in the ribbon
   - If no pyRevit tab, pyRevit is not installed correctly

3. **Check extension folder:**
   - Open: `%APPDATA%\pyRevit\Extensions\`
   - Verify `revit_plugin/` folder exists
   - Check that `extension.json` file exists inside

4. **Check extension.json format:**
   - Open `extension.json` in a text editor
   - Verify it's valid JSON (no syntax errors)
   - Check that file paths in commands are correct

5. **Reload extensions:**
   - In REVIT: pyRevit tab → Click "Reload Extensions"
   - Check pyRevit output window for errors

6. **Check pyRevit output window:**
   - In REVIT: pyRevit tab → Click "Toggle Output" or "Show Output"
   - Look for error messages about the extension

7. **Verify file structure:**
   - Make sure all required files are in the extension folder
   - Check that `commands/` folder exists with all command files

### Import Errors

**If you see "ModuleNotFoundError" or "ImportError":**

1. **Check shared code is accessible:**
   - Verify `core/`, `models/`, `utils/` folders exist in extension directory
   - Or verify symlinks are working (if using symlinks)

2. **Check Python path:**
   - The plugin adds parent directory to `sys.path`
   - Verify the path is correct in command files

3. **Install missing dependencies:**
   ```bash
   pip install numpy scipy shapely trimesh astral pytz pyyaml
   ```

4. **Check pyRevit Python version:**
   - pyRevit uses its own Python installation
   - Make sure dependencies are installed in pyRevit's Python, not system Python

### Calculation Errors

1. **Verify REVIT model has windows:**
   - Open model in REVIT
   - Check that windows exist (not just openings)
   - Windows should be `FamilyInstance` elements

2. **Check window elements are valid:**
   - Windows must have geometry (bounding box)
   - Windows must have location

3. **Review pyRevit output window:**
   - All errors are logged there
   - Check for specific error messages

### Common Issues

**Issue: "REVIT API not available"**
- Solution: Make sure you're running the command from within REVIT, not standalone Python

**Issue: "Extension not found"**
- Solution: Check folder name matches in `extension.json` and actual folder name

**Issue: "Command not appearing"**
- Solution: Check `extension.json` has correct command definitions
- Verify command files exist in `commands/` folder

**Issue: "Cannot import workflow"**
- Solution: Make sure `workflow.py` is in extension directory or path is correct

## Development

### Testing Plugin

1. Make changes to plugin code
2. Reload extension in pyRevit (pyRevit tab → Reload Extensions)
3. Test in REVIT

### Debugging

- Use `script.get_output()` for logging
- Check pyRevit output window
- Use REVIT's built-in debugging tools

## File Structure

```
revit_plugin/
├── __init__.py
├── extension.json          # Plugin metadata
├── revit_extractor.py      # REVIT data extraction
├── commands/
│   ├── __init__.py
│   ├── calculate_insolation.py
│   ├── calculate_keo.py
│   └── calculate_both.py
└── INSTALLATION.md
```

## Benefits

✅ **No Export Needed** - Work directly with REVIT models  
✅ **Real-time Updates** - Calculations reflect current model  
✅ **Native Integration** - Use REVIT's built-in features  
✅ **Code Reuse** - Same calculation engine  
✅ **Professional Workflow** - Integrated into REVIT  

## Support

For issues or questions:
1. Check pyRevit output window for errors
2. Review REVIT journal files
3. Check plugin logs

