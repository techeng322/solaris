# UI Features Guide

## Overview

The Solaris application includes a comprehensive GUI with multiple viewer windows and features:

1. **Main Window** - Primary interface for model import, calculations, and results
2. **GLB 3D Viewer** - Interactive 3D visualization of GLB model files
3. **Logs Viewer** - Real-time log monitoring window

## Running the Application

Run the GUI application:

```bash
python run_gui.py
```

## Main Window Features

### Model Import
- Click "Select Model (IFC/RVT/GLB)" / "Выбрать модель (IFC/RVT/GLB)" button
- Select your BIM model file (.ifc, .rvt, or .glb)
- Calculations run automatically after import!

### Calculation Parameters
- **Calculation Date**: Select date for insolation calculations
- **Calculation Type**: Choose from:
  - Insolation & KEO (both)
  - Insolation Only
  - KEO Only
- **Calculate Button**: Recalculate with different parameters (optional)

### Results Display
- **Results Table**: Shows room-by-room results with:
  - Room name
  - Insolation duration
  - Insolation compliance
  - KEO percentage
  - KEO compliance
  - Overall status
- **Log Tab**: Shows detailed calculation logs
- **Export Button**: Generate PDF/HTML reports with diagrams

### Toolbar Buttons
- **Show 3D Viewer**: Open 3D model visualization window
- **Show Logs Viewer**: Open dedicated logs monitoring window

## GLB 3D Viewer Window

**Access:**
- Click "Show 3D Viewer" button in the toolbar
- Or use menu: View → 3D Viewer
- Automatically opens when loading a GLB file

**Features:**
- Interactive 3D model visualization
- Mouse controls:
  - **Left-click + drag**: Rotate model
  - **Mouse wheel**: Zoom in/out
- Reset view button
- Zoom slider
- Displays mesh information (vertices, faces count)

**Requirements:**
- For full 3D viewing: Install PyOpenGL
  ```bash
  pip install PyOpenGL PyOpenGL-accelerate
  ```
- Without PyOpenGL: Shows mesh information only

## Logs Viewer Window

**Access:**
- Click "Show Logs Viewer" button in the toolbar
- Or use menu: View → Logs Viewer
- Automatically opens on application start

**Features:**
- Real-time log display with color coding:
  - **ERROR**: Red (#f48771)
  - **WARNING**: Yellow (#dcdcaa)
  - **INFO**: Cyan (#4ec9b0)
  - **DEBUG**: Gray (#808080)
- Auto-scroll option (enabled by default)
- Clear logs button
- Log count display
- Dark theme for better readability

**Log Sources:**
- All application logs are captured automatically
- Logs from model import
- Logs from calculations
- Logs from room extraction
- All other application operations

## Workflow

1. **Launch Application**: `python run_gui.py`
2. **Import Model**: Click "Select Model" and choose your file
3. **Automatic Calculation**: Calculations run automatically
4. **View Results**: Check the results table
5. **Explore Features**: 
   - Open 3D viewer for GLB files
   - Open logs viewer for detailed information
6. **Export Report**: Click "Export Report" to save PDF/HTML

## Tips

1. **Keep Logs Viewer Open**: Keep the logs viewer window open to monitor all operations in real-time
2. **3D Viewer for GLB**: The 3D viewer automatically loads when you import a GLB file
3. **Multiple Windows**: You can have both viewer windows open simultaneously
4. **Log Tab**: The main window also has a log tab that shows the same logs
5. **Automatic Calculations**: No need to click "Calculate" - it runs automatically after import
6. **Recalculate**: Use the "Calculate" button if you want to change parameters and recalculate

## Troubleshooting

### 3D Viewer Not Showing Model
- Install PyOpenGL: `pip install PyOpenGL PyOpenGL-accelerate`
- Check that the GLB file loaded successfully
- Try resetting the view

### Logs Not Appearing
- Make sure the logs viewer window is open
- Check that logging level is set to INFO or lower
- Verify the log handler is properly initialized

### Performance
- Large GLB files may take time to load in the 3D viewer
- Logs viewer handles large amounts of logs efficiently
- Use "Clear Logs" if the viewer becomes slow with many logs

### Calculations Not Running
- Ensure model file is valid (IFC, RVT, or GLB)
- Check logs viewer for error messages
- Verify configuration file (config.yaml) is present
