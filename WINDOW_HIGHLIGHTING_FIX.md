# Window Highlighting Fix - Implementation

## Problem
Window highlighting in the 3D viewer was not working when users selected items in the object tree.

## Root Causes Identified
1. **Missing logging** - No visibility into what was happening during selection
2. **Missing error handling** - Errors during highlighting were silently failing
3. **Missing validation** - No checks for mesh availability or shader initialization
4. **Missing connection confirmation** - No way to verify signal connection was working

## Fixes Applied

### 1. Enhanced Logging (`ui/main_window.py`)
- Added comprehensive logging in `on_object_tree_selection()`:
  - Logs when window is selected
  - Logs when building is set in viewer
  - Logs when tab is switched
  - Logs when highlight request is sent
  - Logs warnings if viewer widget is not available

### 2. Enhanced Logging (`ui/object_tree_viewer.py`)
- Added logging in `on_selection_changed()`:
  - Logs when object is selected
  - Logs when signal is emitted
  - Logs warnings if item has no data
- Added logging in `on_item_double_clicked()`:
  - Logs when object is double-clicked
  - Logs when signal is emitted

### 3. Enhanced Logging (`ui/glb_viewer.py` - GLBViewerWidget)
- Added logging in `highlight_window()`:
  - Logs when OpenGL is not available
  - Logs when viewer doesn't support highlighting
  - Logs when forwarding highlight request

### 4. Enhanced Logging (`ui/glb_viewer.py` - GLBViewerOpenGLWidget)
- Added comprehensive logging in `highlight_window()`:
  - Logs when highlighting starts
  - Logs when mesh is created
  - Logs when cached mesh is used
  - Logs warnings if mesh creation fails
  - Logs when update is called

### 5. Mesh Validation (`ui/glb_viewer.py`)
- Added check to ensure main mesh is loaded before highlighting:
  ```python
  if self.mesh is None or len(self.mesh.vertices) == 0:
      logger.warning(f"Cannot highlight window {window.id}: No mesh loaded in 3D viewer")
      return
  ```

### 6. Shader Validation (`ui/glb_viewer.py`)
- Added check for shader initialization:
  ```python
  if self.shader_program_colored is None:
      logging.warning("Colored shader not initialized - cannot highlight window")
  ```
- Added check for shader binding:
  ```python
  if not self.shader_program_colored.bind():
      logging.error("Failed to bind colored shader for window highlighting")
  ```

### 7. Error Handling (`ui/glb_viewer.py`)
- Added try-except block around window rendering:
  ```python
  try:
      # Render highlighted window
  except Exception as e:
      logging.error(f"Error rendering highlighted window: {e}", exc_info=True)
  ```

### 8. Building Data Verification (`ui/main_window.py`)
- Added check to ensure building is set in viewer before highlighting:
  ```python
  if self.building:
      self.glb_viewer_widget.set_building(self.building)
  ```

### 9. Connection Confirmation (`ui/main_window.py`)
- Added log message when signal connection is made:
  ```python
  logging.info("Object tree selection connected to 3D viewer highlighting")
  ```

## How to Debug

### Step 1: Check Logs
When you select a window in the object tree, check the logs viewer for:
1. "Object selected in tree: Window - emitting signal"
2. "Window selected in object tree: [window_id]"
3. "Building set in 3D viewer for window highlighting"
4. "Switched to 3D viewer tab"
5. "Highlight request sent for window: [window_id]"
6. "Forwarding highlight request to OpenGL widget for window: [window_id]"
7. "Highlighting window: [window_id]"
8. "Created mesh for window [window_id] with X vertices, Y faces"
9. "Update called for window highlight"

### Step 2: Check for Errors
Look for any warnings or errors in the logs:
- "OpenGL not available" - Install PyOpenGL
- "No mesh loaded in 3D viewer" - Mesh not loaded yet
- "Failed to create mesh for window" - Window properties invalid
- "Colored shader not initialized" - Shader initialization failed
- "Failed to bind colored shader" - Shader binding failed

### Step 3: Verify Requirements
1. **OpenGL Available**: Check if PyOpenGL is installed
   ```bash
   pip install PyOpenGL PyOpenGL-accelerate
   ```
2. **Mesh Loaded**: Ensure a GLB model is loaded
3. **Building Data**: Ensure building data is set in viewer
4. **Window Properties**: Ensure windows have valid center, normal, and size

## Expected Behavior

1. User clicks on a window in the object tree
2. Signal is emitted: "Object selected in tree: Window - emitting signal"
3. Main window receives signal: "Window selected in object tree: [window_id]"
4. Building is set in viewer: "Building set in 3D viewer for window highlighting"
5. Tab switches to 3D viewer: "Switched to 3D viewer tab"
6. Highlight request is sent: "Highlight request sent for window: [window_id]"
7. OpenGL widget receives request: "Highlighting window: [window_id]"
8. Window mesh is created/cached: "Created mesh for window [window_id] with X vertices, Y faces"
9. View is updated: "Update called for window highlight"
10. Window is rendered with cyan highlight in 3D viewer

## Testing

1. **Load a GLB model** with windows
2. **Open the Object Tree tab**
3. **Click on a window** in the tree
4. **Check the logs viewer** for the sequence of log messages
5. **Verify the 3D viewer tab** switches automatically
6. **Look for cyan highlight** on the selected window

## Troubleshooting

### Issue: No logs appear when selecting window
**Solution**: Check if signal connection is made - look for "Object tree selection connected to 3D viewer highlighting" in logs

### Issue: "OpenGL not available" warning
**Solution**: Install PyOpenGL: `pip install PyOpenGL PyOpenGL-accelerate` and restart application

### Issue: "No mesh loaded in 3D viewer" warning
**Solution**: Ensure a GLB model is loaded before selecting windows

### Issue: "Failed to create mesh for window" warning
**Solution**: Check window properties (center, normal, size) are valid

### Issue: Window highlight not visible
**Possible causes**:
1. Window mesh is too small or positioned incorrectly
2. Window is outside the current view
3. Shader rendering failed (check logs for errors)
4. Window is behind other geometry

**Solutions**:
1. Reset view in 3D viewer
2. Zoom out to see full model
3. Check logs for rendering errors
4. Verify window properties are correct

## Files Modified

1. `ui/main_window.py` - Enhanced selection handler with logging and building verification
2. `ui/glb_viewer.py` - Enhanced highlighting with validation, error handling, and logging
3. `ui/object_tree_viewer.py` - Enhanced selection handlers with logging

## Status

✅ **FIXES APPLIED** - Window highlighting should now work with comprehensive logging for debugging.

If the issue persists, check the logs viewer for detailed error messages that will help identify the specific problem.

