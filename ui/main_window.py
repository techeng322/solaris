"""
Main GUI window for Solaris Insolation Calculator.
"""

import sys
import logging
from pathlib import Path
from datetime import date
from typing import Optional
import yaml
from ui.translations import Translations
from ui.styles import get_complete_stylesheet, get_button_style, get_progressbar_style, get_table_style, COLORS

try:
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QLabel, QFileDialog, QTextEdit, QProgressBar,
        QTabWidget, QTableWidget, QTableWidgetItem, QGroupBox, QSpinBox,
        QDateEdit, QTimeEdit, QComboBox, QMessageBox, QSizePolicy, QHeaderView
    )
    from PyQt6.QtCore import Qt, QThread, pyqtSignal, QDate, QEvent
    from PyQt6.QtGui import QFont, QKeySequence, QCloseEvent, QColor
    PYQT6_AVAILABLE = True
except ImportError:
    PYQT6_AVAILABLE = False
    print("PyQt6 not available. GUI will not work. Install with: pip install PyQt6")


if PYQT6_AVAILABLE:
    class ImportAndCalculateWorker(QThread):
        """Worker thread for importing model and running calculations - full workflow."""
        
        finished = pyqtSignal(object, object)  # Emits (Building, BuildingCalculationResult)
        error = pyqtSignal(str)
        progress = pyqtSignal(str)
        mesh_loaded = pyqtSignal(object)  # Emits mesh for immediate 3D viewer display
        
        def __init__(self, file_path, calculation_date, required_duration, config, calc_type='both'):
            super().__init__()
            self.file_path = file_path
            self.calculation_date = calculation_date
            self.required_duration = required_duration
            self.config = config
            self.calc_type = calc_type  # 'insolation', 'keo', or 'both'
        
        def run(self):
            """Run full workflow: import model then calculate."""
            try:
                from workflow import import_building_model, calculate_insolation, calculate_keo
                from models.calculation_result import BuildingCalculationResult
                
                # STEP 1: Import building model
                self.progress.emit("Importing building model...")
                buildings, importer = import_building_model(self.file_path, self.config)
                
                if not buildings:
                    self.error.emit("No buildings found in model")
                    return
                
                building = buildings[0]
                self.progress.emit(f"Model imported: {building.name} ({building.get_total_windows()} windows)")
                
                # Store importer for mesh access (for GLB files)
                self.importer = importer
                
                # Emit mesh immediately for 3D viewer (before calculations)
                # This allows the viewer to show the model while calculations are running
                # Works for both GLB and IFC files
                if hasattr(importer, 'mesh') and importer.mesh is not None:
                    import trimesh
                    if isinstance(importer.mesh, trimesh.Trimesh):
                        file_type = "IFC" if self.file_path.lower().endswith('.ifc') else "GLB"
                        self.progress.emit(f"Loading {file_type} 3D model into viewer...")
                        self.mesh_loaded.emit(importer.mesh)
                    else:
                        import logging
                        logging.warning(f"Importer mesh is not a trimesh.Trimesh object (type: {type(importer.mesh)})")
                else:
                    import logging
                    file_type = "IFC" if self.file_path.lower().endswith('.ifc') else "GLB"
                    logging.info(f"{file_type} importer has no mesh - mesh generation may have failed or file has no geometry")
                
                # STEP 2: Calculate insolation (if needed)
                insolation_results = None
                if self.calc_type in ['insolation', 'both']:
                    self.progress.emit("Calculating insolation...")
                    insolation_results = calculate_insolation(
                        building,
                        self.calculation_date,
                        self.required_duration,
                        self.config
                    )
                    self.progress.emit("Insolation calculation complete")
                
                # STEP 3: Calculate KEO (if needed)
                keo_results = None
                if self.calc_type in ['keo', 'both']:
                    self.progress.emit("Calculating KEO...")
                    keo_results = calculate_keo(building, self.config)
                    self.progress.emit("KEO calculation complete")
                
                # STEP 4: Merge results
                if self.calc_type == 'both' and insolation_results and keo_results:
                    # Merge KEO into insolation results
                    window_result_map = {r.window_id: r for r in insolation_results.window_results}
                    for keo_window_result in keo_results.window_results:
                        window_id = keo_window_result.window_id
                        if window_id in window_result_map:
                            # Merge KEO result into existing window result
                            window_result_map[window_id].keo_result = keo_window_result.keo_result
                            window_result_map[window_id].check_compliance()
                        else:
                            # Window has KEO but no insolation - add it
                            insolation_results.add_window_result(keo_window_result)
                    final_result = insolation_results
                elif insolation_results:
                    final_result = insolation_results
                elif keo_results:
                    final_result = keo_results
                else:
                    # Create empty result
                    final_result = BuildingCalculationResult(
                        building_id=building.id,
                        building_name=building.name,
                        calculation_date=self.calculation_date
                    )
                
                self.progress.emit("All calculations complete")
                self.finished.emit(building, final_result)
            
            except Exception as e:
                import traceback
                error_msg = f"{str(e)}\n{traceback.format_exc()}"
                self.error.emit(error_msg)
    
    
    class CalculationWorker(QThread):
        """Worker thread for calculations only (when model already loaded)."""
        
        finished = pyqtSignal(object)  # Emits BuildingCalculationResult
        error = pyqtSignal(str)
        progress = pyqtSignal(str)
        
        def __init__(self, building, calculation_date, required_duration, config, calc_type='both'):
            super().__init__()
            self.building = building
            self.calculation_date = calculation_date
            self.required_duration = required_duration
            self.config = config
            self.calc_type = calc_type  # 'insolation', 'keo', or 'both'
        
        def run(self):
            """Run calculations in background thread."""
            try:
                from models.calculation_result import BuildingCalculationResult
                from workflow import calculate_insolation, calculate_keo
                
                building_result = BuildingCalculationResult(
                    building_id=self.building.id,
                    building_name=self.building.name,
                    calculation_date=self.calculation_date
                )
                
                # Calculate insolation
                if self.calc_type in ['insolation', 'both']:
                    self.progress.emit("Calculating insolation...")
                    insolation_results = calculate_insolation(
                        self.building,
                        self.calculation_date,
                        self.required_duration,
                        self.config
                    )
                    building_result.window_results = insolation_results.window_results
                
                # Calculate KEO
                if self.calc_type in ['keo', 'both']:
                    self.progress.emit("Calculating KEO...")
                    keo_results = calculate_keo(self.building, self.config)
                    
                    # Merge results
                    if self.calc_type == 'both':
                        window_result_map = {r.window_id: r for r in building_result.window_results}
                        for keo_window_result in keo_results.window_results:
                            window_id = keo_window_result.window_id
                            if window_id in window_result_map:
                                # Merge KEO result into existing window result
                                window_result_map[window_id].keo_result = keo_window_result.keo_result
                                window_result_map[window_id].check_compliance()
                            else:
                                # Window has KEO but no insolation - add it
                                building_result.add_window_result(keo_window_result)
                    else:
                        building_result.window_results = keo_results.window_results
                
                self.finished.emit(building_result)
            
            except Exception as e:
                import traceback
                error_msg = f"{str(e)}\n{traceback.format_exc()}"
                self.error.emit(error_msg)
    
    
    class MainWindow(QMainWindow):
        """Main application window."""
        
        def __init__(self):
            super().__init__()
            self.building = None
            self.calculation_result = None
            self.config = self.load_config()
            self.gui_log_handler = None
            self.current_file_path = None  # Store current file path for viewer updates
            self.current_mesh = None  # Store current mesh for viewer access
            self.logs_viewer_widget = None  # Will be set in init_ui
            self.glb_viewer_widget = None  # Will be set in init_ui
            self.object_tree_viewer_widget = None  # Will be set in init_ui
            self.logs_viewer_connected = False  # Track if logs viewer is connected
            self.object_tree_connected = False  # Track if object tree is connected to 3D viewer
            self.init_ui()
            self.setup_logging()
        
        def changeEvent(self, event):
            """Handle window state changes to bring window to front when activated."""
            if event.type() == QEvent.Type.WindowActivate:
                self.raise_()
                self.activateWindow()
            super().changeEvent(event)
        
        def focusInEvent(self, event):
            """Bring window to front when it receives focus."""
            self.raise_()
            self.activateWindow()
            super().focusInEvent(event)
        
        def mousePressEvent(self, event):
            """Bring window to front when clicked on window background."""
            # Only raise if clicking directly on the window (not on child widgets)
            # Child widgets will handle their own events, so this will only fire for window background
            if event.button() == Qt.MouseButton.LeftButton:
                self.raise_()
                self.activateWindow()
            super().mousePressEvent(event)
        
        def load_config(self) -> dict:
            """Load configuration."""
            try:
                with open('config.yaml', 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f) or {}
            except FileNotFoundError:
                return {}
        
        def init_ui(self):
            """Initialize user interface."""
            t = Translations
            self.setWindowTitle(t.WINDOW_TITLE)
            
            # Set professional default font for the application
            app_font = QFont("Segoe UI", 10)
            app_font.setStyleHint(QFont.StyleHint.SansSerif)
            self.setFont(app_font)
            
            # Apply professional styling
            self.setStyleSheet(get_complete_stylesheet())
            
            # Set default window size (resizable)
            self.resize(1400, 900)
            self.setMinimumSize(800, 600)
            
            # Central widget
            central_widget = QWidget()
            self.setCentralWidget(central_widget)
            
            # Main layout with spacing
            main_layout = QVBoxLayout()
            main_layout.setSpacing(15)
            main_layout.setContentsMargins(20, 20, 20, 20)
            central_widget.setLayout(main_layout)
            
            # Menu bar
            self.create_menu_bar()
            
            # Toolbar
            toolbar_layout = QHBoxLayout()
            toolbar_layout.setSpacing(10)
            
            # File selection
            self.file_label = QLabel(t.FILE_NOT_SELECTED)
            self.file_label.setStyleSheet(f"""
                QLabel {{
                    background: {COLORS['bg_medium']};
                    color: {COLORS['text_primary']};
                    border: 1px solid {COLORS['bg_light']};
                    border-radius: 6px;
                    padding: 8px 12px;
                    font-size: 11px;
                }}
            """)
            select_file_btn = QPushButton(t.SELECT_MODEL)
            select_file_btn.setStyleSheet(get_button_style('secondary'))
            select_file_btn.clicked.connect(self.select_file)
            
            toolbar_layout.addWidget(QLabel(t.MODEL))
            toolbar_layout.addWidget(self.file_label)
            toolbar_layout.addWidget(select_file_btn)
            
            toolbar_layout.addStretch()
            
            main_layout.addLayout(toolbar_layout)
            
            # Calculation parameters
            params_group = QGroupBox(t.CALCULATION_PARAMETERS)
            params_layout = QHBoxLayout()
            params_layout.setSpacing(15)
            
            params_layout.addWidget(QLabel(t.CALCULATION_DATE))
            self.date_edit = QDateEdit()
            self.date_edit.setDate(QDate.currentDate())
            self.date_edit.setCalendarPopup(True)
            params_layout.addWidget(self.date_edit)
            
            params_layout.addWidget(QLabel(t.CALCULATION_TYPE))
            self.calc_type_combo = QComboBox()
            self.calc_type_combo.addItems([t.BOTH, t.INSOLATION_ONLY, t.KEO_ONLY])
            params_layout.addWidget(self.calc_type_combo)
            
            calculate_btn = QPushButton(t.CALCULATE)
            calculate_btn.setStyleSheet(get_button_style('primary'))
            calculate_btn.clicked.connect(self.calculate)
            params_layout.addWidget(calculate_btn)
            
            params_layout.addStretch()
            params_group.setLayout(params_layout)
            main_layout.addWidget(params_group)
            
            # Progress bar
            self.progress_bar = QProgressBar()
            self.progress_bar.setVisible(False)
            self.progress_bar.setStyleSheet(get_progressbar_style())
            main_layout.addWidget(self.progress_bar)
            
            # Status label with enhanced styling
            self.status_label = QLabel(t.READY)
            self.status_label.setStyleSheet(f"""
                QLabel {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 {COLORS['bg_medium']},
                        stop:1 {COLORS['bg_light']});
                    color: {COLORS['cyan']};
                    border: 1px solid {COLORS['primary_blue']};
                    border-radius: 6px;
                    padding: 10px;
                    font-weight: bold;
                    font-size: 12px;
                }}
            """)
            main_layout.addWidget(self.status_label)
            
            # Tabs for results and viewers
            self.tabs = QTabWidget()
            main_layout.addWidget(self.tabs)
            
            # Results table tab
            self.results_table = QTableWidget()
            self.results_table.setColumnCount(6)
            self.results_table.setHorizontalHeaderLabels([
                t.WINDOW, t.INSOLATION, t.COMPLIANCE, t.KEO_PERCENT, t.COMPLIANCE, t.STATUS
            ])
            self.results_table.setStyleSheet(get_table_style())
            
            # Set minimum column widths to accommodate bilingual text
            # Column 0: Window / Окно
            self.results_table.setColumnWidth(0, 250)
            # Column 1: Insolation / Инсоляция
            self.results_table.setColumnWidth(1, 220)
            # Column 2: Compliance / Соответствие
            self.results_table.setColumnWidth(2, 250)
            # Column 3: KEO (%) / КЕО (%)
            self.results_table.setColumnWidth(3, 180)
            # Column 4: Compliance / Соответствие (duplicate)
            self.results_table.setColumnWidth(4, 250)
            # Column 5: Status / Статус
            self.results_table.setColumnWidth(5, 220)
            
            # Set minimum widths to prevent columns from getting too small
            header = self.results_table.horizontalHeader()
            header.setMinimumSectionSize(150)
            # Allow columns to stretch to fill available space
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)  # Window name - interactive
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)  # Insolation - interactive
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)  # Compliance - interactive
            header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)  # KEO - interactive
            header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)  # Compliance - interactive
            header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)     # Status - stretch to fill
            
            self.tabs.addTab(self.results_table, t.RESULTS)
            
            # Logs Viewer tab (sophisticated terminal viewer)
            from ui.logs_viewer import LogsViewerWidget
            self.logs_viewer_widget = LogsViewerWidget()
            self.tabs.addTab(self.logs_viewer_widget, "Logs Viewer / Просмотр логов")
            
            # 3D Viewer tab
            from ui.glb_viewer import GLBViewerWidget
            self.glb_viewer_widget = GLBViewerWidget()
            self.tabs.addTab(self.glb_viewer_widget, "3D Viewer / 3D просмотр")
            
            # Object Tree Viewer tab
            from ui.object_tree_viewer import ObjectTreeViewerWidget
            self.object_tree_viewer_widget = ObjectTreeViewerWidget()
            self.tabs.addTab(self.object_tree_viewer_widget, "Object Tree / Дерево объектов")
            
            # Export button
            export_layout = QHBoxLayout()
            export_layout.addStretch()
            export_btn = QPushButton(t.EXPORT_REPORT)
            export_btn.setStyleSheet(get_button_style('primary'))
            export_btn.clicked.connect(self.export_report)
            export_btn.setEnabled(False)
            self.export_btn = export_btn
            export_layout.addWidget(export_btn)
            main_layout.addLayout(export_layout)
        
        def create_menu_bar(self):
            """Create menu bar with window controls."""
            t = Translations
            menubar = self.menuBar()
            
            file_menu = menubar.addMenu(t.FILE_MENU)
            open_action = file_menu.addAction(t.OPEN_MODEL)
            open_action.triggered.connect(self.select_file)
            file_menu.addSeparator()
            exit_action = file_menu.addAction(t.EXIT)
            exit_action.triggered.connect(self.close)
            
            view_menu = menubar.addMenu(t.VIEW_MENU)
            view_3d_action = view_menu.addAction(t.VIEW_3D)
            view_3d_action.triggered.connect(self.switch_to_3d_viewer)
            view_logs_action = view_menu.addAction(t.VIEW_LOGS)
            view_logs_action.triggered.connect(self.switch_to_logs_viewer)
            view_tree_action = view_menu.addAction(t.VIEW_OBJECT_TREE)
            view_tree_action.triggered.connect(self.switch_to_object_tree)
            view_menu.addSeparator()
            self.fullscreen_action = view_menu.addAction(t.TOGGLE_FULLSCREEN)
            self.fullscreen_action.setShortcut(QKeySequence("F11"))
            self.fullscreen_action.triggered.connect(self.toggle_fullscreen)
            
            help_menu = menubar.addMenu(t.HELP_MENU)
            about_action = help_menu.addAction(t.ABOUT)
            about_action.triggered.connect(self.show_about)
            
            # Add window control buttons to top right
            self.create_window_controls(menubar)
        
        def create_window_controls(self, menubar):
            """Create minimize and close buttons in top right corner."""
            # Create a widget for the window controls
            controls_widget = QWidget()
            controls_layout = QHBoxLayout()
            controls_layout.setContentsMargins(0, 0, 0, 0)
            controls_layout.setSpacing(5)
            controls_widget.setLayout(controls_layout)
            
            # Minimize button
            minimize_btn = QPushButton("−")
            minimize_btn.setFixedSize(30, 25)
            minimize_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {COLORS['bg_panel']};
                    color: {COLORS['text_secondary']};
                    border: 1px solid {COLORS['glow_blue']};
                    border-radius: 4px;
                    font-weight: bold;
                    font-size: 14px;
                }}
                QPushButton:hover {{
                    background: {COLORS['bg_medium']};
                    color: {COLORS['accent_cyan']};
                    border: 1px solid {COLORS['primary_blue']};
                }}
                QPushButton:pressed {{
                    background: {COLORS['bg_dark']};
                }}
            """)
            minimize_btn.clicked.connect(self.showMinimized)
            minimize_btn.setToolTip("Minimize / Свернуть")
            controls_layout.addWidget(minimize_btn)
            
            # Close button
            close_btn = QPushButton("×")
            close_btn.setFixedSize(30, 25)
            close_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {COLORS['bg_panel']};
                    color: {COLORS['text_secondary']};
                    border: 1px solid {COLORS['glow_blue']};
                    border-radius: 4px;
                    font-weight: bold;
                    font-size: 18px;
                }}
                QPushButton:hover {{
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 {COLORS['error']},
                        stop:1 #CC0033);
                    color: {COLORS['text_primary']};
                    border: 1px solid {COLORS['error']};
                }}
                QPushButton:pressed {{
                    background: #990022;
                }}
            """)
            close_btn.clicked.connect(self.close)
            close_btn.setToolTip("Close / Закрыть")
            controls_layout.addWidget(close_btn)
            
            # Add the controls widget to the menu bar
            menubar.setCornerWidget(controls_widget, Qt.Corner.TopRightCorner)
        
        def select_file(self):
            """Select BIM model file."""
            t = Translations
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                t.OPEN_MODEL,
                "",
                "BIM Files (*.ifc *.rvt *.glb);;All Files (*)"
            )
            
            if file_path:
                # Ensure logs viewer is open and connected before loading
                self.ensure_logs_viewer_connected()
                self.file_label.setText(Path(file_path).name)
                self.load_model(file_path)
        
        def load_model(self, file_path: str):
            """Load building model from file and automatically run calculations."""
            t = Translations
            # Store the file path for later use
            self.current_file_path = file_path
            self.file_label.setText(Path(file_path).name)
            
            # Ensure logs viewer is connected
            self.ensure_logs_viewer_connected()
            
            # Get calculation parameters from UI
            calc_date = self.date_edit.date().toPyDate()
            calc_type_idx = self.calc_type_combo.currentIndex()
            calc_type_map = {0: 'both', 1: 'insolation', 2: 'keo'}
            calc_type = calc_type_map[calc_type_idx]
            
            # Required duration from config
            from datetime import timedelta
            min_duration_str = self.config.get('calculation', {}).get('insolation', {}).get('min_duration', '01:30:00')
            hours, minutes, seconds = map(int, min_duration_str.split(':'))
            required_duration = timedelta(hours=hours, minutes=minutes, seconds=seconds)
            
            # Show progress
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 0)  # Indeterminate
            self.status_label.setText(t.LOADING_MODEL)
            self.export_btn.setEnabled(False)
            
            # Start import and calculation worker (full workflow)
            self.import_worker = ImportAndCalculateWorker(
                file_path,
                calc_date,
                required_duration,
                self.config,
                calc_type
            )
            self.import_worker.finished.connect(self.on_import_and_calculate_finished)
            self.import_worker.error.connect(self.on_import_error)
            self.import_worker.progress.connect(self.log)
            self.import_worker.mesh_loaded.connect(self.on_mesh_loaded)
            self.import_worker.start()
        
        def load_glb_mesh_into_viewer(self, mesh):
            """Load mesh object directly into embedded 3D viewer widget."""
            if self.glb_viewer_widget:
                self.glb_viewer_widget.load_mesh(mesh)
                if mesh is not None:
                    import trimesh
                    if isinstance(mesh, trimesh.Trimesh):
                        self.log(f"GLB mesh loaded into 3D viewer: {len(mesh.vertices):,} vertices, {len(mesh.faces):,} faces")
        
        def switch_to_3d_viewer(self):
            """Switch to 3D viewer tab."""
            if self.glb_viewer_widget:
                self.tabs.setCurrentWidget(self.glb_viewer_widget)
        
        def switch_to_logs_viewer(self):
            """Switch to logs viewer tab."""
            if self.logs_viewer_widget:
                self.tabs.setCurrentWidget(self.logs_viewer_widget)
        
        def switch_to_object_tree(self):
            """Switch to object tree tab."""
            if self.object_tree_viewer_widget:
                self.tabs.setCurrentWidget(self.object_tree_viewer_widget)
        
        def load_glb_into_viewer(self, file_path: str):
            """Load GLB mesh from file into 3D viewer (fallback method)."""
            try:
                import trimesh
                mesh = trimesh.load(file_path)
                
                # If it's a scene, combine meshes
                if isinstance(mesh, trimesh.Scene):
                    meshes = []
                    for geometry in mesh.geometry.values():
                        if isinstance(geometry, trimesh.Trimesh):
                            meshes.append(geometry)
                    if meshes:
                        mesh = trimesh.util.concatenate(meshes)
                
                if isinstance(mesh, trimesh.Trimesh):
                    self.load_glb_mesh_into_viewer(mesh)
                else:
                    self.log(f"Could not load GLB: mesh is not a Trimesh object")
            except Exception as e:
                self.log(f"Could not load GLB into viewer: {e}")
                import traceback
                self.log(f"Error details: {traceback.format_exc()}")
        
        def load_glb_mesh_into_viewer(self, mesh, auto_open_viewer=False):
            """Load mesh into the embedded GLB viewer widget. Works for both GLB and IFC files.
            
            Args:
                mesh: trimesh.Trimesh object to load
                auto_open_viewer: If True, automatically open Trimesh viewer (for IFC files)
            """
            import logging
            logger = logging.getLogger(__name__)
            
            if self.glb_viewer_widget:
                logger.debug(f"Loading mesh into viewer widget: {len(mesh.vertices) if mesh else 0} vertices")
                self.glb_viewer_widget.load_mesh(mesh, auto_open_viewer=auto_open_viewer)
                # Ensure building is set in viewer for window highlighting
                if self.building:
                    self.glb_viewer_widget.set_building(self.building)
                    logger.debug("Building set in viewer widget for highlighting support")
            else:
                logger.warning("GLB viewer widget not available - cannot load mesh")
        
        def ensure_logs_viewer_connected(self):
            """Ensure logs viewer widget is connected to log handler."""
            if self.gui_log_handler and self.logs_viewer_widget and not self.logs_viewer_connected:
                # Connect to logs viewer widget
                self.gui_log_handler.log_message.connect(
                    lambda msg, level, fmt: self.logs_viewer_widget.add_log(msg, level, fmt)
                )
                self.logs_viewer_connected = True
        
        def setup_logging(self):
            """Setup custom logging handler for GUI."""
            try:
                from ui.log_handler import GUILogHandler
                self.gui_log_handler = GUILogHandler()
                
                # Connect to logs viewer widget (embedded in tabs)
                if self.logs_viewer_widget:
                    self.gui_log_handler.log_message.connect(
                        lambda msg, level, fmt: self.logs_viewer_widget.add_log(msg, level, fmt)
                    )
                    self.logs_viewer_connected = True
                
                # Add handler to root logger
                # Configure logging handler for GUI
                root_logger = logging.getLogger()
                
                # Remove any existing StreamHandlers to avoid duplicate logs
                gui_handler_class_name = GUILogHandler.__name__
                for handler in root_logger.handlers[:]:
                    handler_class_name = handler.__class__.__name__
                    if isinstance(handler, logging.StreamHandler) and handler_class_name != gui_handler_class_name:
                        root_logger.removeHandler(handler)
                
                # Add our GUI handler
                root_logger.addHandler(self.gui_log_handler)
                root_logger.setLevel(logging.INFO)
                
                # Ensure all child loggers propagate to root and have appropriate levels
                # This is critical - child loggers must propagate for the GUI handler to receive messages
                for logger_name in ['main', 'importers', 'core', 'importers.glb_importer', 'importers.ifc_importer', 'importers.revit_importer']:
                    child_logger = logging.getLogger(logger_name)
                    child_logger.setLevel(logging.INFO)
                    child_logger.propagate = True  # CRITICAL: Must propagate to root logger
                    # Remove any handlers from child loggers (they should use root logger)
                    for handler in child_logger.handlers[:]:
                        child_logger.removeHandler(handler)
                
            except Exception as e:
                # Fallback: use print if logging setup fails
                print(f"Could not setup GUI logging: {e}")
                import traceback
                traceback.print_exc()
        
        def calculate(self):
            """Start calculation."""
            t = Translations
            if not self.building:
                QMessageBox.warning(self, t.WARNING, t.LOAD_MODEL_FIRST)
                return
            
            # Get calculation parameters
            calc_date = self.date_edit.date().toPyDate()
            calc_type_idx = self.calc_type_combo.currentIndex()
            calc_type_map = {0: 'both', 1: 'insolation', 2: 'keo'}
            calc_type = calc_type_map[calc_type_idx]
            
            # Required duration
            min_duration_str = self.config.get('calculation', {}).get('insolation', {}).get('min_duration', '01:30:00')
            from datetime import timedelta
            hours, minutes, seconds = map(int, min_duration_str.split(':'))
            required_duration = timedelta(hours=hours, minutes=minutes, seconds=seconds)
            
            # Start calculation in background thread
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 0)  # Indeterminate
            self.status_label.setText(t.CALCULATING)
            self.export_btn.setEnabled(False)
            
            self.worker = CalculationWorker(
                self.building,
                calc_date,
                required_duration,
                self.config,
                calc_type
            )
            self.worker.finished.connect(self.on_calculation_finished)
            self.worker.error.connect(self.on_calculation_error)
            self.worker.progress.connect(self.log)
            self.worker.start()
        
        def on_import_and_calculate_finished(self, building, result):
            """Handle completion of import and calculation workflow."""
            t = Translations
            self.building = building
            self.calculation_result = result
            self.progress_bar.setVisible(False)
            self.status_label.setText(t.CALCULATION_COMPLETE)
            self.export_btn.setEnabled(True)
            
            # Log model loaded info
            self.log(f"{t.MODEL_LOADED}: {building.name}")
            self.log(f"Windows / Окон: {building.get_total_windows()}")
            
            # Load mesh into viewer if applicable (GLB or IFC)
            if hasattr(self.import_worker, 'importer') and self.import_worker.importer:
                importer = self.import_worker.importer
                # Check if importer has a mesh (works for both GLB and IFC)
                if hasattr(importer, 'mesh'):
                    if importer.mesh is not None:
                        import trimesh
                        if isinstance(importer.mesh, trimesh.Trimesh):
                            file_type = "IFC" if self.current_file_path and self.current_file_path.lower().endswith('.ifc') else "GLB"
                            self.log(f"Loading {file_type} mesh into 3D viewer: {len(importer.mesh.vertices):,} vertices, {len(importer.mesh.faces):,} faces")
                            # For IFC files, automatically open Trimesh viewer
                            auto_open = file_type == "IFC"
                            self.load_glb_mesh_into_viewer(importer.mesh, auto_open_viewer=auto_open)
                            self.log(f"✓ {file_type} mesh loaded into 3D viewer successfully")
                            if auto_open:
                                self.log("Trimesh viewer opened automatically for IFC file")
                        else:
                            self.log(f"Warning: Mesh is not a trimesh.Trimesh object (type: {type(importer.mesh)})")
                    else:
                        file_type = "IFC" if self.current_file_path and self.current_file_path.lower().endswith('.ifc') else "GLB"
                        self.log(f"⚠ {file_type} importer has no mesh - 3D visualization may not be available")
                        self.log("This is normal if the file has no geometry or geometry extraction failed")
                elif self.current_file_path and self.current_file_path.lower().endswith('.glb'):
                    # Fallback for GLB: try loading from file
                    self.load_glb_into_viewer(self.current_file_path)
            
            # Update object tree viewer widget if it exists
            if self.object_tree_viewer_widget:
                # Pass importer to tree viewer so it can display IFC elements
                importer = None
                if hasattr(self.import_worker, 'importer'):
                    importer = self.import_worker.importer
                self.object_tree_viewer_widget.set_building(building, importer=importer)
                # Connect object tree selection to 3D viewer highlighting (only once)
                if not self.object_tree_connected:
                    self.object_tree_viewer_widget.item_selected.connect(self.on_object_tree_selection)
                    self.object_tree_connected = True
                    import logging
                    logging.info("Object tree selection connected to 3D viewer highlighting")
            
            # Update 3D viewer with building data for window highlighting
            if self.glb_viewer_widget:
                self.glb_viewer_widget.set_building(building)
            
            # Update results table
            self.update_results_table(result)
            
            # Log summary
            summary = result.get_compliance_summary()
            self.log(f"\n{t.CALCULATION_COMPLETE_MSG}:")
            self.log(f"Total windows / Всего окон: {summary['total_windows']}")
            self.log(f"Compliant windows / Соответствующих: {summary['compliant_windows']}")
            self.log(f"Non-compliant windows / Не соответствующих: {summary['non_compliant_windows']}")
            self.log(f"{t.COMPLIANCE_RATE}: {summary['compliance_rate']*100:.1f}%")
        
        def on_mesh_loaded(self, mesh):
            """Handle mesh loaded signal - load into embedded 3D viewer widget. Works for both GLB and IFC files."""
            try:
                import trimesh
                if isinstance(mesh, trimesh.Trimesh):
                    self.current_mesh = mesh  # Store mesh reference
                    # Load into embedded viewer widget
                    self.load_glb_mesh_into_viewer(mesh)
                    file_type = "IFC" if self.current_file_path and self.current_file_path.lower().endswith('.ifc') else "GLB"
                    self.log(f"{file_type} 3D model loaded into viewer: {len(mesh.vertices):,} vertices, {len(mesh.faces):,} faces")
                else:
                    self.log(f"Warning: Mesh is not a trimesh.Trimesh object (type: {type(mesh)})")
            except Exception as e:
                self.log(f"Could not load mesh into viewer: {e}")
                import traceback
                self.log(f"Error details: {traceback.format_exc()}")
        
        def on_import_error(self, error_msg):
            """Handle import/calculation error."""
            t = Translations
            self.progress_bar.setVisible(False)
            self.status_label.setText(t.CALCULATION_ERROR)
            self.log(f"{t.ERROR}: {error_msg}")
            QMessageBox.critical(self, t.CALCULATION_ERROR, f"{t.FAILED_TO_LOAD}:\n{error_msg}")
        
        def on_calculation_finished(self, result):
            """Handle calculation completion (when recalculating with existing model)."""
            t = Translations
            self.calculation_result = result
            self.progress_bar.setVisible(False)
            self.status_label.setText(t.CALCULATION_COMPLETE)
            self.export_btn.setEnabled(True)
            
            # Update results table
            self.update_results_table(result)
            
            # Log summary
            summary = result.get_compliance_summary()
            self.log(f"\n{t.CALCULATION_COMPLETE_MSG}:")
            self.log(f"Total windows / Всего окон: {summary['total_windows']}")
            self.log(f"Compliant windows / Соответствующих: {summary['compliant_windows']}")
            self.log(f"Non-compliant windows / Не соответствующих: {summary['non_compliant_windows']}")
            self.log(f"{t.COMPLIANCE_RATE}: {summary['compliance_rate']*100:.1f}%")
        
        def on_calculation_error(self, error_msg):
            """Handle calculation error (when recalculating with existing model)."""
            t = Translations
            self.progress_bar.setVisible(False)
            self.status_label.setText(t.CALCULATION_ERROR)
            self.log(f"{t.ERROR}: {error_msg}")
            QMessageBox.critical(self, t.CALCULATION_ERROR, error_msg)
        
        def on_object_tree_selection(self, selected_object):
            """Handle object selection from object tree viewer."""
            from models.building import Window, Building
            import logging
            logger = logging.getLogger(__name__)
            
            logger.info(f"Object selected in tree: {type(selected_object).__name__}")
            
            if not self.glb_viewer_widget:
                logger.warning("3D viewer widget not available for highlighting")
                return
            
            # Ensure building is set in viewer (needed for highlighting)
            if self.building:
                self.glb_viewer_widget.set_building(self.building)
                logger.debug(f"Building set in 3D viewer for highlighting")
            
            # Switch to 3D viewer tab to show the highlight
            self.switch_to_3d_viewer()
            
            # If a window is selected, highlight it (Trimesh viewer will open automatically if needed)
            if isinstance(selected_object, Window):
                logger.info(f"Window selected: {selected_object.id} - highlighting")
                # Highlight the selected window (this will open Trimesh viewer automatically if not open)
                self.glb_viewer_widget.highlight_window(selected_object)
                logger.info(f"Highlight request sent for window: {selected_object.id}")
            elif isinstance(selected_object, Building):
                logger.info(f"Building selected: {selected_object.id} - clearing highlight")
                # Clear highlight for building selection
                self.glb_viewer_widget.highlight_window(None)
            else:
                # For any other object, try to highlight if it has the required attributes
                logger.info(f"Object selected: {type(selected_object).__name__} - attempting highlight")
                # Check if object has required attributes for highlighting (id, center, normal, size)
                if (hasattr(selected_object, 'id') and 
                    hasattr(selected_object, 'center') and 
                    hasattr(selected_object, 'normal') and 
                    hasattr(selected_object, 'size')):
                    # Try to highlight (this will open Trimesh viewer automatically if not open)
                    self.glb_viewer_widget.highlight_window(selected_object)
                    logger.info(f"Highlight request sent for object: {getattr(selected_object, 'id', 'unknown')}")
                else:
                    logger.debug(f"Object {type(selected_object).__name__} does not have required attributes for highlighting")
                    # Clear highlight if object can't be highlighted
                    self.glb_viewer_widget.highlight_window(None)
        
        def update_results_table(self, result):
            """Update results table with calculation results (windows only)."""
            t = Translations
            
            # Set row count to number of windows
            total_windows = len(result.window_results)
            self.results_table.setRowCount(total_windows)
            
            for row, window_result in enumerate(result.window_results):
                # Window name
                window_name_text = window_result.window_name or window_result.window_id
                window_name_item = QTableWidgetItem(window_name_text)
                self.results_table.setItem(row, 0, window_name_item)
                
                # Insolation
                if window_result.insolation_result:
                    ins = window_result.insolation_result
                    self.results_table.setItem(row, 1, QTableWidgetItem(ins.duration_formatted))
                    self.results_table.setItem(row, 2, QTableWidgetItem(
                        t.YES if ins.meets_requirement else t.NO
                    ))
                else:
                    self.results_table.setItem(row, 1, QTableWidgetItem(t.N_A))
                    self.results_table.setItem(row, 2, QTableWidgetItem(t.N_A))
                
                # KEO
                if window_result.keo_result:
                    keo = window_result.keo_result
                    self.results_table.setItem(row, 3, QTableWidgetItem(f"{keo.keo_total:.2f}"))
                    self.results_table.setItem(row, 4, QTableWidgetItem(
                        t.YES if keo.meets_requirement else t.NO
                    ))
                else:
                    self.results_table.setItem(row, 3, QTableWidgetItem(t.N_A))
                    self.results_table.setItem(row, 4, QTableWidgetItem(t.N_A))
                
                # Overall status
                status_item = QTableWidgetItem(t.COMPLIANT if window_result.is_compliant else t.NON_COMPLIANT)
                if not window_result.is_compliant:
                    status_item.setForeground(Qt.GlobalColor.red)
                else:
                    status_item.setForeground(Qt.GlobalColor.green)
                self.results_table.setItem(row, 5, status_item)
            
            # Resize columns to contents, but respect minimum widths
            self.results_table.resizeColumnsToContents()
            
            # Ensure minimum widths are maintained after resize (increased for better visibility)
            min_widths = [250, 220, 250, 180, 250, 220]
            for col, min_width in enumerate(min_widths):
                if self.results_table.columnWidth(col) < min_width:
                    self.results_table.setColumnWidth(col, min_width)
        
        def export_report(self):
            """Export calculation report."""
            t = Translations
            if not self.calculation_result:
                QMessageBox.warning(self, t.WARNING, t.NO_RESULTS)
                return
            
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                t.EXPORT_REPORT,
                "report.pdf",
                "PDF Files (*.pdf);;HTML Files (*.html)"
            )
            
            if file_path:
                try:
                    from reports import ReportGenerator
                    report_gen = ReportGenerator()
                    output_path = report_gen.generate_report(
                        self.calculation_result,
                        file_path,
                        self.building
                    )
                    self.log(f"{t.REPORT_SAVED}: {output_path}")
                    QMessageBox.information(self, t.SUCCESS, f"{t.REPORT_SAVED}:\n{output_path}")
                except Exception as e:
                    self.log(f"{t.FAILED_TO_SAVE}: {e}")
                    QMessageBox.critical(self, t.ERROR, f"{t.FAILED_TO_SAVE}:\n{e}")
        
        def log(self, message: str):
            """Add message to log."""
            # Use logging system so it goes through the handler to the logs viewer
            # The handler will send formatted messages to the logs viewer widget
            logging.info(message)
        
        def toggle_fullscreen(self):
            """Toggle between full screen and windowed mode."""
            if self.isFullScreen():
                self.showNormal()
            else:
                self.showFullScreen()
        
        def closeEvent(self, event: QCloseEvent):
            """Handle window close event."""
            # All viewers are now embedded in tabs, no separate windows to close
            event.accept()
        
        def show_about(self):
            """Show about dialog."""
            t = Translations
            QMessageBox.about(
                self,
                t.ABOUT_TITLE,
                t.ABOUT_TEXT
            )
    
    def run_gui():
        """Run GUI application."""
        if not PYQT6_AVAILABLE:
            print("PyQt6 not available. Please install: pip install PyQt6")
            return
        
        app = QApplication(sys.argv)
        window = MainWindow()
        
        # Center window on screen
        screen = app.primaryScreen().geometry()
        window_geometry = window.frameGeometry()
        window_geometry.moveCenter(screen.center())
        window.move(window_geometry.topLeft())
        
        window.show()
        
        sys.exit(app.exec())
else:
    def run_gui():
        """Run GUI application (not available)."""
        print("GUI not available. PyQt6 is required.")
        print("Install with: pip install PyQt6")
        print("Please install PyQt6 to use the GUI application.")

