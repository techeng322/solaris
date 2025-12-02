# Building Solaris Executable (.exe) - Guide

This guide explains how to create a Windows executable (.exe) file from the Solaris application.

## Prerequisites

1. **Python 3.8+** installed on Windows
2. **All dependencies installed** (from `requirements.txt`)
3. **PyInstaller** installed

## Installation Steps

### 1. Install PyInstaller

```bash
pip install pyinstaller
```

Or if using the virtual environment:

```bash
# Activate virtual environment first
.\venv312\Scripts\activate

# Then install PyInstaller
pip install pyinstaller
```

### 2. Build the Executable

#### Option A: Using the Build Script (Recommended)

```bash
python build_exe.py
```

#### Option B: Using PyInstaller Directly

```bash
pyinstaller Solaris.spec
```

#### Option C: Using PyInstaller Command Line

```bash
pyinstaller --name=Solaris --onefile --windowed --add-data "config.yaml;." --add-data "ui/translations.py;ui" --add-data "ui/styles.py;ui" run_gui.py
```

## Build Output

After building, you'll find:

- **Executable**: `dist/Solaris.exe` - This is the final executable file
- **Build files**: `build/` - Temporary build files (can be deleted)
- **Spec file**: `Solaris.spec` - PyInstaller configuration (keep for future builds)

## Distribution

### Single File Distribution

The `--onefile` option creates a single executable that includes all dependencies. This is convenient but:
- **Larger file size** (~100-200 MB)
- **Slower startup** (extracts files to temp directory on first run)
- **Easier distribution** (just one file)

### Folder Distribution (Alternative)

If you prefer faster startup, you can build a folder distribution:

```bash
pyinstaller --name=Solaris --windowed --add-data "config.yaml;." --add-data "ui/translations.py;ui" --add-data "ui/styles.py;ui" run_gui.py
```

This creates:
- `dist/Solaris/` folder containing the executable and all dependencies
- **Faster startup** but requires distributing the entire folder

## Troubleshooting

### Issue: "Module not found" errors

**Solution**: Add missing modules to `hiddenimports` in `Solaris.spec` or use `--hidden-import` flag.

### Issue: Config file not found

**Solution**: Ensure `config.yaml` is included in `datas` list in the spec file.

### Issue: Large executable size

**Solution**: 
- Use `--exclude-module` to exclude unnecessary packages
- Consider using folder distribution instead of onefile
- Use UPX compression (already enabled in spec file)

### Issue: Antivirus false positives

**Solution**: 
- This is common with PyInstaller executables
- Sign the executable with a code signing certificate
- Submit to antivirus vendors for whitelisting

### Issue: Missing DLL errors

**Solution**: 
- Ensure all required DLLs are included
- Check if Visual C++ Redistributable is installed on target machine
- Add DLL paths to `binaries` in spec file if needed

## Testing the Executable

1. **Test on build machine**: Run `dist/Solaris.exe` to ensure it works
2. **Test on clean machine**: Copy to a machine without Python to test standalone operation
3. **Test all features**: 
   - Import IFC/GLB files
   - Run calculations
   - Generate reports
   - View 3D models

## File Size Optimization

The executable will be large (~100-200 MB) due to:
- Python interpreter
- PyQt6 libraries
- NumPy, SciPy, Matplotlib
- All other dependencies

To reduce size:
1. Exclude unnecessary modules (already done in spec file)
2. Use UPX compression (already enabled)
3. Consider using folder distribution
4. Remove unused dependencies from requirements.txt

## Advanced Configuration

### Adding an Icon

1. Create or obtain an `.ico` file
2. Add to spec file: `icon='path/to/icon.ico'`
3. Rebuild

### Code Signing (Optional)

For production distribution, consider code signing:

```bash
signtool sign /f certificate.pfx /p password /t http://timestamp.digicert.com dist/Solaris.exe
```

## Notes

- **First run may be slow**: The onefile executable extracts files to a temp directory on first run
- **Antivirus warnings**: Some antivirus software may flag PyInstaller executables (false positive)
- **Windows Defender**: May need to allow the executable through Windows Defender
- **Dependencies**: The executable is self-contained and doesn't require Python installation on target machines

## Build Script Features

The `build_exe.py` script:
- Automatically detects project root
- Includes all necessary data files
- Configures hidden imports
- Excludes unnecessary modules
- Provides build status feedback

## Alternative Build Tools

If PyInstaller doesn't work for your needs, consider:
- **cx_Freeze**: Alternative Python to executable tool
- **py2exe**: Windows-specific tool (older, less maintained)
- **Nuitka**: Compiles Python to C++ (faster, smaller, but more complex)

## Support

If you encounter issues:
1. Check PyInstaller documentation: https://pyinstaller.org/
2. Review build logs in `build/` directory
3. Test with `--debug=all` flag for detailed information
4. Check Windows Event Viewer for runtime errors

