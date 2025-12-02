# Fix for Workflow Hook Error

## Problem

When building the executable, you may encounter this error:

```
ERROR: Failed to import module __PyInstaller_hooks_0_workflow required by hook for module 
hook-workflow.py
```

## Cause

PyInstaller has a hook for a third-party package called "workflow" in `pyinstaller-hooks-contrib`. This hook conflicts with the project's local `workflow.py` file.

## Solution

The build script now uses the `Solaris.spec` file which:
1. Includes a custom hook in `pyinstaller_hooks/hook-workflow.py` that overrides the problematic hook
2. Explicitly includes the local `workflow` module in `hiddenimports`
3. Excludes third-party workflow package submodules

## How to Build

### Option 1: Using the build script (recommended)
```bash
python build_exe.py
```

### Option 2: Using the spec file directly
```bash
pyinstaller Solaris.spec --clean --noconfirm
```

## If Error Persists

If you still get the error, try:

1. **Clean build:**
   ```bash
   rmdir /s /q build dist
   pyinstaller Solaris.spec --clean --noconfirm
   ```

2. **Check for third-party workflow package:**
   ```bash
   pip list | findstr workflow
   ```
   If a "workflow" package is installed, uninstall it:
   ```bash
   pip uninstall workflow
   ```

3. **Use spec file with explicit exclusions:**
   The spec file already excludes `workflow.tasks` and `workflow.contrib` which should prevent the conflict.

## Files Modified

- `Solaris.spec` - Updated with proper hook configuration
- `build_exe.py` - Now uses spec file for better control
- `pyinstaller_hooks/hook-workflow.py` - Custom hook to override problematic hook

