# Quick Start Guide

## 🚀 Fast Setup (3 Steps)

### Step 1: Install Dependencies

```bash
pip install -r requirements.txt
```

**Note:** On Windows, if `ifcopenshell` fails to install, try:
```bash
pip install ifcopenshell --no-cache-dir
```

### Step 2: Verify Installation

```bash
python test_installation.py
```

You should see `[SUCCESS] Installation is complete and working!`

### Step 3: Run the Application

```bash
python run_gui.py
```

## 📋 What You Need

1. **Python 3.8+** - Check with `python --version`
2. **BIM Model File** - IFC format (.ifc), RVT (.rvt), or GLB (.glb)
3. **Dependencies** - Install with `pip install -r requirements.txt`

## 🎯 First Run

1. **Launch GUI:**
   ```bash
   python run_gui.py
   ```

2. **Import Model:**
   - Click "Выбрать модель (IFC/RVT/GLB)" / "Select Model (IFC/RVT/GLB)"
   - Select your model file
   - Calculations run automatically!

3. **View Results:**
   - Results appear in the table automatically
   - View insolation duration and KEO values
   - Check compliance status

4. **Export Report:**
   - Click "Экспорт отчета" / "Export Report"
   - Save PDF or HTML report with diagrams

5. **Explore Features:**
   - Click "Show 3D Viewer" to visualize the building model
   - Click "Show Logs Viewer" to see detailed calculation logs

## ⚠️ Troubleshooting

**Problem:** Dependencies won't install
```bash
# Try upgrading pip first
python -m pip install --upgrade pip
pip install -r requirements.txt
```

**Problem:** GUI doesn't start
```bash
# Install PyQt6 separately
pip install PyQt6
```

**Problem:** No model file
- Export from REVIT: File → Export → IFC
- Or use sample IFC files from BIM repositories
- GLB files are also supported for 3D visualization

## 📚 More Information

- **Full Guide:** See `HOW_TO_RUN.md`
- **Project Details:** See `PROJECT_SUMMARY.md`
- **Configuration:** Edit `config.yaml`
- **UI Features:** See `UI_FEATURES.md`

---

**Ready to go!** 🎉
