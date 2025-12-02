# Object Tree Selection Fix

## Problem
Users could not select objects in the object tree. Clicking on items did nothing.

## Root Cause
The QTreeWidget did not have selection mode explicitly configured, which can prevent selection in some cases. Additionally:
- Selection mode was not set
- Items might not have been marked as selectable
- Click handlers were not properly connected

## Fixes Applied

### 1. Enabled Selection Mode
**Location**: `ui/object_tree_viewer.py` lines 113-116

```python
# Enable selection - CRITICAL for selection to work
self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
self.tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
self.tree.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
```

**What this does**:
- `SingleSelection`: Allows selecting one item at a time
- `SelectItems`: Selection works on individual items
- `StrongFocus`: Widget can receive keyboard focus

### 2. Made Items Selectable
**Location**: `ui/object_tree_viewer.py` lines 158-159, 176-177

```python
# Make item selectable
building_item.setFlags(building_item.flags() | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
window_item.setFlags(window_item.flags() | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
```

**What this does**:
- Explicitly marks items as selectable and enabled
- Ensures items can be clicked and selected

### 3. Added Click Handler
**Location**: `ui/object_tree_viewer.py` lines 121, 232-242

```python
self.tree.itemClicked.connect(self.on_item_clicked)  # Also handle single click
```

**What this does**:
- Handles single clicks on items
- Ensures item is selected when clicked
- Emits signal immediately on click

### 4. Improved Selection Handler
**Location**: `ui/object_tree_viewer.py` lines 207-230

**Changes**:
- Uses `currentItem()` in addition to `selectedItems()` for more reliable selection detection
- Better logging with object ID
- More robust item detection

### 5. Enhanced Click Handlers
**Location**: `ui/object_tree_viewer.py` lines 232-258

**Changes**:
- `on_item_clicked()`: Ensures item is selected and emits signal
- `on_item_double_clicked()`: Also ensures selection before emitting

## How It Works Now

1. **User clicks on item** → `itemClicked` signal fires
2. **Click handler** → Ensures item is selected (`setCurrentItem`)
3. **Selection handler** → `itemSelectionChanged` signal fires
4. **Selection handler** → Gets item data and emits `item_selected` signal
5. **Main window** → Receives signal and highlights object in 3D viewer

## Testing

1. **Load a GLB model** with windows
2. **Open Object Tree tab**
3. **Click on any item** (building or window)
4. **Verify**:
   - Item becomes highlighted/selected (blue background)
   - Selection label updates: "1 object(s) selected"
   - Logs show: "Object selected in tree: Window (id: ...)"
   - 3D viewer tab switches automatically
   - Object is highlighted in blue in 3D viewer

## Expected Behavior

### Visual Feedback
- **Selected item**: Blue background (from stylesheet)
- **Hover**: Medium background color
- **Selection label**: Shows "1 object(s) selected / 1 объектов выбрано"

### Log Messages
When clicking an item, you should see:
```
Object clicked in tree: Window - emitting signal
Object selected in tree: Window (id: window_123) - emitting signal
```

## Troubleshooting

### Issue: Items still not selectable
**Check**:
1. Is the tree widget enabled? (should be by default)
2. Are there items in the tree? (load a model first)
3. Check logs for any errors

### Issue: Selection works but no signal emitted
**Check**:
1. Look for "Selected item has no data associated" in logs
2. Verify items have data set: `item.setData(0, Qt.ItemDataRole.UserRole, object)`
3. Check if signal connection is made in main window

### Issue: Selection works but highlighting doesn't
**Check**:
1. Verify signal connection: "Object tree selection connected to 3D viewer highlighting"
2. Check 3D viewer logs for highlight requests
3. Ensure OpenGL is available

## Files Modified

1. `ui/object_tree_viewer.py`:
   - Added selection mode configuration
   - Made items selectable
   - Added click handler
   - Improved selection detection

## Status

✅ **FIXED** - Object tree selection should now work smoothly:
- Items are selectable with single click
- Visual feedback shows selected item
- Signals are emitted properly
- Works for both building and window items

## Key Changes Summary

| Change | Purpose |
|--------|---------|
| `setSelectionMode(SingleSelection)` | Enable item selection |
| `setSelectionBehavior(SelectItems)` | Select individual items |
| `setFocusPolicy(StrongFocus)` | Allow keyboard focus |
| `ItemIsSelectable` flag | Make items clickable |
| `itemClicked` handler | Handle single clicks |
| Improved `on_selection_changed()` | More reliable selection detection |

The object tree should now work smoothly for selecting objects! 🎉

