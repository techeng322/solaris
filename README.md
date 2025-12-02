

![photo_2025-12-02_13-53-57](https://github.com/user-attachments/assets/2c72df4e-ff71-4c97-97a7-feb7a736e637)

# Solaris Insolation Calculator

A comprehensive GUI application for calculating insolation duration and natural illumination (KEO) for buildings, compliant with Russian building standards.

## Features

- **Insolation Calculations**: Compliant with GOST R 57795-2017 and SanPiN 1.2.3685-21
- **KEO Calculations**: Compliant with SP 52.13330.2016 and SP 367.1325800.2017
- **BIM Integration**: Import models from IFC, RVT, and GLB formats
- **Modern GUI**: Professional PyQt6 interface with bilingual support (English/Russian)
- **Offline Operation**: Full functionality without internet connection
- **Accurate Calculations**: Precise second-level accuracy for insolation requirements
- **Loggia Support**: Calculate rooms behind loggias
- **Report Generation**: Professional reports with diagrams and formatted output
- **3D Model Viewer**: Interactive 3D visualization of building models
- **Real-time Logging**: Comprehensive logging system with dedicated viewer

## Standards Compliance

### Insolation
- GOST R 57795-2017 "Buildings and Structures. Methods for Calculating Insolation Duration"
  - Amendment No. 1 (June 1, 2021)
  - Amendment No. 2 (September 1, 2022)
- SanPiN 1.2.3685-21 "Hygienic Standards and Requirements for Ensuring the Safety and/or Harmlessness of Environmental Factors for Humans"

### Illumination (KEO)
- SP 52.13330.2016 "Natural and Artificial Lighting"
  - Amendment No. 1 (November 20, 2019)
  - Amendment No. 2 (December 28, 2021)
- SP 367.1325800.2017 "Residential and Public Buildings. Design Rules for Natural and Combined Lighting"
  - Amendment No. 1 (December 14, 2020)
  - Amendment No. 2 (December 20, 2022)

## Installation

```bash
pip install -r requirements.txt
```

## Usage

### Launch the Application

```bash
python run_gui.py
```

### Using the GUI

1. **Import Model**: Click "Select Model" and choose your BIM file (IFC, RVT, or GLB)
2. **Automatic Calculation**: Calculations run automatically after model import
3. **View Results**: Results appear in the table showing insolation duration and KEO values
4. **Export Report**: Click "Export Report" to generate PDF/HTML reports with diagrams
5. **3D Viewer**: Click "Show 3D Viewer" to visualize the building model
6. **Logs Viewer**: Click "Show Logs Viewer" to see detailed calculation logs

### Configuration

Edit `config.yaml` to customize:
- Calculation parameters (time step, grid density)
- Building standards compliance settings
- Window type properties
- Location settings
- Report format and options

## Project Structure

```
solaris/
├── core/              # Core calculation engines
├── models/            # Data models and schemas
├── importers/         # BIM model import modules
├── ui/                # GUI user interface
├── reports/           # Report generation
├── utils/             # Utility functions
├── workflow.py        # Calculation workflow functions
└── run_gui.py         # Main entry point
```

## License

Proprietary - All rights reserved
