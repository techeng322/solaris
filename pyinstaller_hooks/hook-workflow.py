# PyInstaller hook to prevent conflict with local workflow.py
# This hook overrides PyInstaller's built-in workflow hook from pyinstaller-hooks-contrib
# which tries to import __PyInstaller_hooks_0_workflow that doesn't exist

# By creating this hook, we tell PyInstaller to use this instead of the problematic one
# Our local workflow.py will be included automatically as a local module

# This is a minimal hook that prevents the error
datas = []
hiddenimports = []
excludedimports = []
