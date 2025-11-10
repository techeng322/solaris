# Setting Up Python 3.12 Environment for Solaris

This guide will help you set up a Python 3.12 virtual environment to use Open3D (which requires Python 3.8-3.12).

## Step 1: Install Python 3.12

1. **Download Python 3.12.11** (latest 3.12 release):
   - Visit: https://www.python.org/downloads/release/python-31211/
   - Download "Windows installer (64-bit)" for your system

2. **Run the installer**:
   - ✅ **IMPORTANT**: Check "Add Python 3.12 to PATH"
   - ✅ Check "Install for all users" (optional but recommended)
   - Click "Install Now"

3. **Verify installation**:
   ```powershell
   py -3.12 --version
   ```
   Should show: `Python 3.12.11`

## Step 2: Create Virtual Environment

### Option A: Automated Setup (Recommended)

Run the PowerShell script:
```powershell
.\setup_python312_env.ps1
```

This script will:
- Detect Python 3.12
- Create a virtual environment named `venv312`
- Install all dependencies including Open3D

### Option B: Manual Setup

1. **Create virtual environment**:
   ```powershell
   py -3.12 -m venv venv312
   ```

2. **Activate virtual environment**:
   ```powershell
   .\venv312\Scripts\Activate.ps1
   ```

3. **Upgrade pip**:
   ```powershell
   python -m pip install --upgrade pip
   ```

4. **Install dependencies**:
   ```powershell
   python -m pip install -r requirements.txt
   ```

5. **Verify Open3D installation**:
   ```powershell
   python -c "import open3d as o3d; print('Open3D version:', o3d.__version__)"
   ```

## Step 3: Using the Environment

### Activate the environment:
```powershell
.\venv312\Scripts\Activate.ps1
```

### Run the application:
```powershell
python run_gui.py
```

### Deactivate when done:
```powershell
deactivate
```

## Troubleshooting

### "Python 3.12 not found"
- Make sure Python 3.12 is installed
- Check that "Add Python to PATH" was selected during installation
- Try: `py -3.12 --version` to verify

### "Execution Policy" error when running PowerShell script
Run this in PowerShell as Administrator:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Open3D installation fails
- Make sure you're using Python 3.12 (not 3.13)
- Check: `python --version` should show 3.12.x
- Try: `python -m pip install open3d --upgrade`

### Virtual environment activation fails
- Make sure you're in the project directory
- Try: `.\venv312\Scripts\python.exe` directly
- On Windows, you might need to use: `venv312\Scripts\activate.bat` instead

## Notes

- The virtual environment `venv312` is separate from your system Python 3.13
- All dependencies are installed in the virtual environment
- You can have both Python 3.12 and 3.13 installed simultaneously
- The `py` launcher will use the correct version based on the virtual environment

## Benefits

✅ Open3D support for enhanced window detection  
✅ All project dependencies properly isolated  
✅ Compatible with all required libraries  
✅ Easy to recreate if needed

