# PyInstaller hook to handle workflow module conflict
# This prevents PyInstaller from using its built-in workflow hook
# which conflicts with our local workflow.py module

# This is an empty hook that tells PyInstaller to skip the workflow hook
# Our local workflow.py will be included automatically as a local module

