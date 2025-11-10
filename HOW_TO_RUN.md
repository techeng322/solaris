# How to Run Solaris Insolation Calculator

## Prerequisites

- Python 3.8 or higher
- pip (Python package manager)

## Step 1: Install Dependencies

### Option A: Using pip (Recommended)

Open a command prompt in the project directory and run:

```bash
pip install -r requirements.txt
```

### Option B: Using virtual environment (Recommended for isolation)

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On Linux/Mac:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Troubleshooting Installation

If you encounter issues:

1. **ifcopenshell installation issues** (common on Windows):
   ```bash
   # Try installing with pre-built wheels
   pip install ifcopenshell --no-cache-dir
   ```

2. **PyQt6 installation issues**:
   ```bash
   # On some systems, you may need:
   pip install PyQt6 --upgrade
   ```

3. **Missing system dependencies** (Linux):
   ```bash
   # Ubuntu/Debian:
   sudo apt-get install python3-dev python3-pip
   # Fedora:
   sudo dnf install python3-devel
   ```

## Step 2: Verify Installation

Run a quick test to verify everything is installed:

```bash
python test_installation.py
```

You should see `[SUCCESS] Installation is complete and working!`

## Step 3: Run the Application

Launch the GUI application:

```bash
python run_gui.py
```

**GUI Features:**
- Click "Выбрать модель (IFC/RVT/GLB)" / "Select Model (IFC/RVT/GLB)" to import a BIM model
- Calculations run automatically after model import
- View results in the table showing insolation duration and KEO values
- Export report using "Экспорт отчета" / "Export Report" button
- Use "Show 3D Viewer" to visualize building models
- Use "Show Logs Viewer" to see detailed calculation logs

## Step 4: Prepare Your BIM Model

### Supported Formats

- **IFC files** (.ifc) - Industry Foundation Classes format
- **RVT files** (.rvt) - REVIT model files
- **GLB files** (.glb) - 3D model format for visualization

### Preparing REVIT Models

1. Open your model in REVIT
2. Export to IFC format:
   - File → Export → IFC
   - Select IFC version (IFC2x3 or IFC4 recommended)
   - Export
3. Use the exported .ifc file with the program

### Model Requirements

For best results, ensure your BIM model has:
- ✅ Rooms/spaces properly defined
- ✅ Windows placed in walls
- ✅ Building location set (latitude/longitude)
- ✅ Floor levels organized

## Step 5: Configure Settings (Optional)

Edit `config.yaml` to customize:

- Calculation parameters (time step, grid density)
- Building location (latitude/longitude)
- Required insolation duration
- Window type properties
- Report format and options

Example configuration:

```yaml
calculation:
  insolation:
    min_duration: "01:30:00"  # Required: 1 hour 30 minutes
    time_step: 1  # Minutes

location:
  latitude: 55.7558  # Moscow
  longitude: 37.6173
  timezone: "Europe/Moscow"
```

## Example Workflow

### Using the GUI:

1. **Launch GUI:**
   ```bash
   python run_gui.py
   ```

2. **Import Model:**
   - Click "Выбрать модель (IFC/RVT/GLB)" / "Select Model (IFC/RVT/GLB)"
   - Select your model file (.ifc, .rvt, or .glb)
   - Calculations run automatically!

3. **View Results:**
   - Results appear automatically in the "Results" / "Результаты" tab
   - Check room-by-room insolation duration and KEO values
   - Review compliance status for each room

4. **Explore Features:**
   - Click "Show 3D Viewer" to visualize the building model in 3D
   - Click "Show Logs Viewer" to see detailed calculation logs
   - Review the "Log" / "Лог" tab for calculation details

5. **Recalculate (Optional):**
   - Change calculation date if needed
   - Select different calculation type (Insolation only, KEO only, or both)
   - Click "Рассчитать" / "Calculate" to recalculate

6. **Export Report:**
   - Click "Экспорт отчета" / "Export Report"
   - Choose location and format (PDF/HTML)
   - Save report with diagrams

## Output Files

After exporting a report, you'll find:

```
output/
├── report.pdf              # Main calculation report
└── diagrams/
    ├── room_1_insolation.png
    ├── room_1_keo.png
    ├── room_2_insolation.png
    └── building_summary.png
```

## Troubleshooting

### Problem: "ModuleNotFoundError"

**Solution:** Install missing dependencies:
```bash
pip install -r requirements.txt
```

### Problem: "No module named 'PyQt6'"

**Solution:** Install PyQt6:
```bash
pip install PyQt6
```

### Problem: "Failed to open IFC file"

**Solution:**
- Check file path is correct
- Verify file is valid IFC format
- Try exporting from REVIT again

### Problem: "No rooms found in model"

**Solution:**
- Ensure rooms/spaces are properly defined in BIM model
- Check that rooms have names/identifiers
- Verify IFC export includes space elements

### Problem: GUI doesn't start

**Solution:**
- Check Python version: `python --version` (should be 3.8+)
- Verify PyQt6 is installed: `pip list | grep PyQt6`
- Check for error messages in the console
- Try reinstalling PyQt6: `pip install --upgrade PyQt6`

### Problem: Calculations take too long

**Solution:**
- Reduce grid density in `config.yaml`
- Increase time step for insolation (e.g., 5 minutes instead of 1)
- Select only insolation or only KEO calculation (not both)

## Quick Test (No Model Required)

To test if the installation works without a BIM model, you can run:

```bash
python -c "from core import InsolationCalculator, KEOCalculator; print('Core modules loaded successfully!')"
```

## Getting Help

- Check `README.md` for general information
- Review `PROJECT_SUMMARY.md` for technical details
- Check `config.yaml` for configuration options
- Review logs in the GUI's Logs Viewer for error messages
- See `UI_FEATURES.md` for GUI feature documentation

## Next Steps

1. ✅ Install dependencies
2. ✅ Launch GUI application
3. ✅ Test with a sample IFC/GLB model
4. ✅ Review calculation results
5. ✅ Customize configuration as needed
6. ✅ Integrate into your workflow

---

**Note:** For production use, ensure you have valid BIM models with proper room and window definitions for accurate calculations.
