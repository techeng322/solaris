# Blue Object Highlighting Fix

## Problem
Window highlighting was not working when selecting objects in the object tree. Users wanted:
1. **Blue color** (not cyan) for highlighting
2. **Any object** selected in tree should be highlighted (not just windows)

## Fixes Applied

### 1. Changed Highlight Color to Blue
- **Before**: Cyan color `QVector4D(0.0, 1.0, 1.0, 0.7)`
- **After**: Blue color `QVector4D(0.0, 0.5, 1.0, 0.8)`
- Location: `ui/glb_viewer.py` line 391

### 2. Support for Any Object (Not Just Windows)
- **Before**: Only `Window` objects could be highlighted
- **After**: Any object with `id`, `center`, `normal`, and `size` attributes can be highlighted
- Updated `_create_window_mesh()` to work with any object type
- Updated `highlight_window()` to accept any object
- Location: `ui/glb_viewer.py` lines 99-144, 146-156

### 3. Enhanced Object Selection Handler
- Now handles `Window`, `Building`, and any other object types
- Always switches to 3D viewer tab when object is selected
- Attempts to highlight any selected object
- Location: `ui/main_window.py` lines 807-842

### 4. OpenGL Shader Initialization Check
- Added check to ensure shaders are initialized before highlighting
- Stores pending highlight if shaders aren't ready yet
- Applies pending highlight when shaders become ready
- Location: `ui/glb_viewer.py` lines 110-115, 303-310

### 5. Enhanced Error Handling
- Added comprehensive error handling in `highlight_window()`
- Added shader linking validation
- Added viewer widget initialization check
- Location: `ui/glb_viewer.py` lines 667-690

### 6. Comprehensive Logging
- Added detailed logging throughout the highlighting pipeline
- Logs object selection, highlight requests, mesh creation, and rendering
- Helps identify issues in the highlighting process

## How It Works Now

1. **User selects object in tree** → Signal emitted
2. **Main window receives signal** → `on_object_tree_selection()`
3. **Building set in viewer** → Ensures building data is available
4. **Tab switches to 3D viewer** → Shows the highlight
5. **Highlight request sent** → `glb_viewer_widget.highlight_window()`
6. **OpenGL widget highlights** → Creates mesh and renders in **blue**

## Testing

1. **Load a GLB model** with windows/objects
2. **Open Object Tree tab**
3. **Click on any object** (window, building, etc.)
4. **Check Logs Viewer** for detailed messages
5. **Verify 3D Viewer tab** switches automatically
6. **Look for blue highlight** on selected object

## Expected Log Messages

When selecting an object, you should see:
```
Object selected in tree: Window
Window selected: window_123 - highlighting in blue
Building set in 3D viewer for highlighting
Switched to 3D viewer tab
Forwarding highlight request to OpenGL widget for object: window_123
Highlight request forwarded successfully
Highlighting object: window_123 (type: Window)
Creating mesh for object window_123
Created mesh for object window_123 with 4 vertices, 2 faces
Update called for object highlight: window_123
```

## Troubleshooting

### Issue: "OpenGL shaders not initialized yet"
**Solution**: The 3D viewer tab needs to be visible at least once to initialize OpenGL. Try:
1. Switch to 3D viewer tab manually first
2. Then select objects in tree

### Issue: "No mesh loaded in 3D viewer"
**Solution**: Load a GLB model first before selecting objects

### Issue: "Object missing center/normal/size property"
**Solution**: The object doesn't have the required geometry properties. Only objects with these properties can be highlighted.

### Issue: Highlight not visible
**Possible causes**:
1. Object mesh is too small
2. Object is outside current view
3. Shader rendering failed (check logs)

**Solutions**:
1. Reset view in 3D viewer
2. Zoom out to see full model
3. Check logs for rendering errors

## Files Modified

1. `ui/main_window.py` - Enhanced selection handler for any object type
2. `ui/glb_viewer.py` - Changed color to blue, support for any object, shader checks

## Status

✅ **FIXES APPLIED** - Object highlighting should now work with:
- **Blue color** for highlights
- **Any object** can be highlighted (not just windows)
- **Comprehensive logging** for debugging
- **Error handling** for edge cases

If highlighting still doesn't work, check the Logs Viewer for detailed error messages.

