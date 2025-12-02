# Quick Build Guide - Solaris Executable

## Fastest Way to Build

### Option 1: Double-click (Windows)
1. Double-click `build_exe.bat`
2. Wait for build to complete
3. Find `Solaris.exe` in the `dist` folder

### Option 2: Command Line
```bash
python build_exe.py
```

### Option 3: Using Spec File
```bash
pyinstaller Solaris.spec
```

## Prerequisites

Make sure you have:
- ✅ Python 3.8+ installed
- ✅ All dependencies installed: `pip install -r requirements.txt`
- ✅ PyInstaller installed: `pip install pyinstaller`

## Build Time

- **First build**: 5-10 minutes (PyInstaller analyzes all dependencies)
- **Subsequent builds**: 2-5 minutes (with cache)

## Output

After building, you'll find:
- **Executable**: `dist/Solaris.exe` (~100-200 MB)
- **Build files**: `build/` (can be deleted)

## Testing

1. Run `dist/Solaris.exe` on your machine
2. Test importing a model (IFC/GLB file)
3. Test calculations
4. Test report generation

## Distribution

The `Solaris.exe` file is **standalone** - it includes:
- ✅ Python interpreter
- ✅ All dependencies
- ✅ Application code
- ✅ Configuration files

**No Python installation required** on target machines!

## Troubleshooting

### "Module not found" error
- Add missing module to `hiddenimports` in `Solaris.spec`
- Rebuild

### Config file not found
- Check that `config.yaml` is in the same directory as the executable
- Or modify spec file to include it properly

### Large file size
- This is normal (~100-200 MB) due to all dependencies
- Consider folder distribution for faster startup

## Need Help?

See `BUILD_EXE_GUIDE.md` for detailed instructions.

