# Complete Guide to Running Solaris Project

## 🎯 Quick Start (Recommended Path)

### Step 1: Verify Python Version
```bash
python --version
```
**Required:** Python 3.8 or higher (you have Python 3.13.7 ✅)

### Step 2: Navigate to Project Directory
```bash
cd E:\Github\solaris-main\solaris-main
```

### Step 3: Install Dependencies
```bash
pip install -r requirements.txt
```

**Important Notes:**
- If `open3d` fails (not available for Python 3.13), that's OK - GLB files will work without advanced features
- If `ifcopenshell` fails on Windows, try: `pip install ifcopenshell --no-cache-dir`
- Ensure `pyglet<2` is installed (should be `pyglet 1.5.31` or similar, NOT version 2.x)

### Step 4: Verify Installation
```bash
python test_installation.py
```
You should see: `[SUCCESS] Installation is complete and working!`

### Step 5: Run the Application
```bash
python run_gui.py
```

---

## 📋 Detailed Setup Instructions

### Option A: Direct Installation (Current Setup)
You're already using this method. Dependencies are installed globally.

**Pros:** Simple, quick setup  
**Cons:** May conflict with other Python projects

### Option B: Virtual Environment (Recommended for Production)
```bash
# Create virtual environment
python -m venv venv

# Activate (Windows PowerShell)
venv\Scripts\Activate.ps1

# If you get execution policy error, run this first:
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# Install dependencies
pip install -r requirements.txt

# Run application
python run_gui.py
```

---

## ✅ Verification Checklist

Before running, verify:

- [x] Python 3.8+ installed
- [x] Dependencies installed (`pip list` shows PyQt6, numpy, etc.)
- [x] `pyglet<2` installed (check with `pip show pyglet` - should be version 1.x)
- [x] PyOpenGL installed (for 3D viewer)
- [x] Project directory is correct

---

## 🚀 Running the Application

### Method 1: Command Line (Recommended)
```bash
cd E:\Github\solaris-main\solaris-main
python run_gui.py
```

### Method 2: From IDE
- Open the project in your IDE
- Run `run_gui.py` directly
- Or use the run button in your IDE

---

## 🎮 Using the Application

### 1. Launch GUI
The application window should open automatically.

### 2. Import BIM Model
- Click **"Выбрать модель (IFC/RVT/GLB)"** / **"Select Model"**
- Choose your model file:
  - **IFC files** (.ifc) - Best for calculations
  - **RVT files** (.rvt) - REVIT models
  - **GLB files** (.glb) - 3D visualization

### 3. Automatic Calculations
- Calculations run automatically after import
- Progress bar shows status
- Results appear in the "Results" tab

### 4. View Results
- **Results Tab**: See insolation duration and KEO values
- **3D Viewer Tab**: Visualize building model (if OpenGL available)
- **Object Tree Tab**: Browse building hierarchy, select windows to highlight
- **Logs Viewer Tab**: See detailed calculation logs

### 5. Export Report
- Click **"Экспорт отчета"** / **"Export Report"**
- Choose PDF or HTML format
- Reports saved in `output/` directory

---

## 🔧 Configuration (Optional)

Edit `config.yaml` to customize:

```yaml
calculation:
  insolation:
    min_duration: "01:30:00"  # Required insolation duration
    time_step: 1  # Minutes (1 = most accurate, 5 = faster)

location:
  latitude: 55.7558   # Building location
  longitude: 37.6173
  timezone: "Europe/Moscow"
```

---

## ⚠️ Common Issues & Solutions

### Issue 1: "ModuleNotFoundError"
**Solution:**
```bash
pip install -r requirements.txt
```

### Issue 2: "pyglet version 2.x installed"
**Solution:**
```bash
pip uninstall pyglet -y
pip install "pyglet<2"
```

### Issue 3: "open3d not available for Python 3.13"
**Status:** This is expected. GLB files will work, but advanced window detection features are disabled.

### Issue 4: "ZeroDivisionError" during import
**Status:** ✅ Fixed! The code now handles zero-weight cases properly.

### Issue 5: "RuntimeWarning: invalid value encountered in divide"
**Status:** ✅ Fixed! Normalization now checks for zero values.

### Issue 6: GUI doesn't start
**Solution:**
```bash
# Check PyQt6
pip install PyQt6 --upgrade

# Verify Python version
python --version
```

### Issue 7: Trimesh viewer errors
**Solution:** Use the embedded 3D viewer instead (requires PyOpenGL). The trimesh viewer has limitations on some systems.

### Issue 8: Calculations take too long
**Solution:**
- Increase `time_step` in `config.yaml` (e.g., from 1 to 5 minutes)
- Select only "Insolation" or only "KEO" (not both)
- Reduce grid density in config

---

## 🎯 Best Practices

### 1. **Use Virtual Environment** (for production)
Isolates dependencies from other projects.

### 2. **Check Dependencies Regularly**
```bash
pip list | grep -E "PyQt6|numpy|trimesh|pyglet"
```

### 3. **Keep Python Updated**
But note: Python 3.13 has some compatibility issues (open3d). Python 3.11 or 3.12 is more compatible.

### 4. **Prepare BIM Models Properly**
- Ensure rooms/spaces are defined
- Windows placed in walls
- Building location set
- Export from REVIT to IFC format

### 5. **Monitor Logs**
- Check "Logs Viewer" tab for detailed information
- Review console output for warnings
- Logs help diagnose issues

---

## 📊 Performance Tips

### Faster Calculations:
1. Increase `time_step` to 5 minutes (instead of 1)
2. Calculate only insolation OR only KEO (not both)
3. Use smaller, simpler models for testing

### Better Accuracy:
1. Use `time_step: 1` (1 minute intervals)
2. Calculate both insolation and KEO
3. Ensure model has proper room/window definitions

---

## 🔍 Verification Commands

### Check Python Version
```bash
python --version
```

### Check Dependencies
```bash
pip list
```

### Test Installation
```bash
python test_installation.py
```

### Test Core Modules
```bash
python -c "from core import InsolationCalculator, KEOCalculator; print('Core modules OK!')"
```

---

## 📁 Project Structure

```
solaris-main/
├── core/              # Calculation engines
├── models/            # Data models
├── importers/         # BIM importers (IFC, RVT, GLB)
├── ui/                # GUI interface
├── reports/           # Report generation
├── utils/             # Utilities
├── config.yaml        # Configuration file
├── run_gui.py         # Main entry point
└── requirements.txt   # Dependencies
```

---

## 🎉 You're Ready!

1. ✅ Dependencies installed
2. ✅ Application runs
3. ✅ GUI opens successfully
4. ✅ Ready to import BIM models

**Next Steps:**
- Import a BIM model (IFC/RVT/GLB)
- View calculation results
- Export reports
- Explore 3D viewer features

---

## 📚 Additional Resources

- **Full Guide:** `HOW_TO_RUN.md`
- **Quick Start:** `QUICK_START.md`
- **Project Details:** `PROJECT_SUMMARY.md`
- **UI Features:** `UI_FEATURES.md`
- **Configuration:** `config.yaml`

---

## 💡 Pro Tips

1. **Start with a simple model** to test the workflow
2. **Use IFC format** for best compatibility
3. **Check logs** if something doesn't work
4. **Export reports** to share results
5. **Use 3D viewer** to visualize and select windows
6. **Object Tree** - Select windows to highlight them in 3D viewer

---

**Happy Calculating! 🏗️☀️**


