"""Test script to load GLB file with Unicode filename."""
import os
import sys
from pathlib import Path

# Set UTF-8 encoding
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Find GLB file
glb_files = list(Path('.').glob('*.glb'))
if not glb_files:
    print("No GLB files found in current directory")
    sys.exit(1)

glb_file = glb_files[0]
print(f"Found GLB file: {glb_file}")

# Now run the main script with the found file
print("Importing modules...")
from main import import_building_model, load_config

print("Loading config...")
config = load_config()
print(f"\nLoading GLB model: {glb_file}")
try:
    print("Calling import_building_model...")
    buildings = import_building_model(str(glb_file), config)
    print(f"Successfully imported {len(buildings)} building(s)")
    for building in buildings:
        print(f"  Building: {building.name}")
        print(f"  Rooms: {building.get_total_rooms()}")
        for room in building.rooms:
            print(f"    - {room.name}: {len(room.windows)} windows, floor {room.floor_number}")
            print(f"      Dimensions: {room.depth:.2f}m x {room.width:.2f}m x {room.height:.2f}m")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

