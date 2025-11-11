# Running Solaris Project with venv312

## ✅ Setup Complete!

The `venv312` virtual environment has been created and configured with Python 3.13.7 and all required dependencies.

## 🚀 How to Run

### Method 1: Activate venv312 and Run (Recommended)

**In PowerShell:**
```powershell
# Navigate to project directory
cd E:\Github\solaris-main

# Activate venv312
.\venv312\Scripts\Activate.ps1

# If you get execution policy error, run this first:
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# Run the application
python run_gui.py
```

**In Command Prompt (CMD):**
```cmd
cd E:\Github\solaris-main
venv312\Scripts\activate
python run_gui.py
```

### Method 2: Run Directly with venv312 Python

**In PowerShell:**
```powershell
cd E:\Github\solaris-main
.\venv312\Scripts\python.exe run_gui.py
```

**In Command Prompt:**
```cmd
cd E:\Github\solaris-main
venv312\Scripts\python.exe run_gui.py
```

## 📋 Quick Reference

### Activate venv312
```powershell
.\venv312\Scripts\Activate.ps1
```

### Deactivate venv312
```powershell
deactivate
```

### Check Python Version
```powershell
python --version
# Should show: Python 3.13.7
```

### Verify Installation
```powershell
python test_installation.py
# Should show: [SUCCESS] Installation is complete and working!
```

### Install Additional Packages
```powershell
# Make sure venv312 is activated first
pip install package_name
```

## 📦 Installed Dependencies

All dependencies from `requirements.txt` are installed except:
- ❌ `open3d` - Not available for Python 3.13 (GLB files will work without advanced features)

**Installed packages:**
- ✅ numpy, scipy, pandas
- ✅ shapely, trimesh, pyproj
- ✅ pygltflib, pyglet<2 (1.5.31)
- ✅ PyQt6, PyOpenGL, PyOpenGL-accelerate
- ✅ matplotlib, reportlab, pillow
- ✅ ifcopenshell
- ✅ astral, pytz, pyyaml
- ✅ pytest, pytest-cov

## 🎯 Usage Workflow

1. **Activate venv312:**
   ```powershell
   .\venv312\Scripts\Activate.ps1
   ```

2. **Run the application:**
   ```powershell
   python run_gui.py
   ```

3. **Use the GUI:**
   - Click "Select Model" to import BIM files (IFC/RVT/GLB)
   - Calculations run automatically
   - View results in the table
   - Export reports
   - Use 3D viewer and object tree

4. **Deactivate when done:**
   ```powershell
   deactivate
   ```

## ⚠️ Important Notes

### Execution Policy (PowerShell)
If you get an error activating venv312 in PowerShell:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Python Version
- venv312 uses Python 3.13.7
- All dependencies are compatible with Python 3.13
- `open3d` is not available for Python 3.13 (expected limitation)

### Virtual Environment Location
- Path: `E:\Github\solaris-main\venv312\`
- Python: `venv312\Scripts\python.exe`
- Activate script: `venv312\Scripts\Activate.ps1` (PowerShell) or `activate.bat` (CMD)

## 🔧 Troubleshooting

### Problem: "Activate.ps1 cannot be loaded"
**Solution:**
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Problem: "ModuleNotFoundError"
**Solution:**
```powershell
# Make sure venv312 is activated
.\venv312\Scripts\Activate.ps1

# Reinstall dependencies
pip install -r requirements.txt
```

### Problem: "Python not found"
**Solution:**
```powershell
# Use full path
.\venv312\Scripts\python.exe run_gui.py
```

## 📚 Additional Resources

- **Full Guide:** `HOW_TO_RUN.md`
- **Quick Start:** `QUICK_START.md`
- **Project Details:** `PROJECT_SUMMARY.md`
- **Configuration:** `config.yaml`

---

**Ready to use venv312!** 🎉

