"""
3D GLB model viewer window using PyQt6 and OpenGL.
"""

import sys
import numpy as np
from pathlib import Path
from typing import Optional

# Import styles outside try block so it's available in all code paths
from ui.styles import COLORS, get_button_style

try:
    from PyQt6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
        QSlider, QGroupBox, QMessageBox, QSizePolicy
    )
    from PyQt6.QtCore import Qt, pyqtSignal
    from PyQt6.QtOpenGLWidgets import QOpenGLWidget
    from PyQt6.QtGui import QOpenGLShaderProgram, QOpenGLShader, QMatrix4x4, QVector3D, QVector4D
    PYQT6_AVAILABLE = True
except ImportError:
    PYQT6_AVAILABLE = False

# Check OpenGL availability dynamically
def check_opengl_available():
    """Check if OpenGL is available at runtime."""
    if not PYQT6_AVAILABLE:
        return False
    try:
        from OpenGL import GL
        # Also check that QOpenGLWidget is available
        from PyQt6.QtOpenGLWidgets import QOpenGLWidget
        return True
    except ImportError:
        return False

# Check at module load time (but will re-check at runtime)
OPENGL_AVAILABLE = check_opengl_available()

# Always define GLBViewerWidget if PyQt6 is available (will check OpenGL at runtime)
if PYQT6_AVAILABLE:
    class GLBViewerOpenGLWidget(QOpenGLWidget):
        """OpenGL widget for displaying 3D GLB models with orbit-style camera."""
        
        def __init__(self, parent=None):
            super().__init__(parent)
            self.mesh = None
            # Orbit camera parameters
            self.azimuth = 45.0  # Horizontal rotation (around Y axis)
            self.elevation = 30.0  # Vertical rotation (pitch)
            self.distance = 5.0  # Distance from model center
            self.pan_x = 0.0  # Horizontal pan offset
            self.pan_y = 0.0  # Vertical pan offset
            self.last_pos = None
            self.shader_program = None
            self.shader_program_colored = None  # Shader for colored surfaces
            self.vertex_buffer = None
            self.vertex_count = 0
            self.center = QVector3D(0, 0, 0)  # Model center point
            self.scale_factor = 1.0
            self.base_distance = 5.0  # Base distance for auto-fit
            # Window highlighting
            self.building = None  # Store building for window access
            self.highlighted_window = None  # Currently highlighted window
            self.window_meshes = {}  # Cache of window geometry meshes
            
        def set_mesh(self, mesh):
            """Set the mesh to display."""
            self.mesh = mesh
            if mesh is not None:
                # Calculate center and scale
                vertices = mesh.vertices
                if len(vertices) > 0:
                    min_bounds = np.min(vertices, axis=0)
                    max_bounds = np.max(vertices, axis=0)
                    center = (min_bounds + max_bounds) / 2
                    self.center = QVector3D(center[0], center[1], center[2])
                    
                    # Calculate scale to fit in view and set appropriate camera distance
                    size = np.max(max_bounds - min_bounds)
                    if size > 0:
                        self.scale_factor = 1.0  # Keep model at natural scale
                        # Set camera distance to fit model nicely in view
                        self.base_distance = size * 1.5  # Distance to see full model
                        self.distance = self.base_distance
                        # Reset pan when loading new model
                        self.pan_x = 0.0
                        self.pan_y = 0.0
            self.update()
        
        def set_building(self, building):
            """Set building data for window highlighting."""
            self.building = building
            self.window_meshes = {}  # Clear cache when building changes
            self.highlighted_window = None
            self.update()
        
        def highlight_window(self, window):
            """Highlight a specific window or object with blue colored surface."""
            import logging
            logger = logging.getLogger(__name__)
            
            if window is None:
                self.highlighted_window = None
                logger.info("Object highlight cleared")
                self.update()
                return
            
            # Check if shaders are initialized (OpenGL context must be ready)
            if self.shader_program is None or self.shader_program_colored is None:
                logger.warning("OpenGL shaders not initialized yet - cannot highlight. Widget may need to be visible first.")
                # Store the window to highlight later when shaders are ready
                self.highlighted_window = window
                return
            
            # Check if main mesh is loaded
            if self.mesh is None or len(self.mesh.vertices) == 0:
                logger.warning(f"Cannot highlight object {getattr(window, 'id', 'unknown')}: No mesh loaded in 3D viewer")
                return
            
            # Check if object has required attributes (id, center, normal, size)
            if not hasattr(window, 'id'):
                logger.warning(f"Object {type(window)} does not have 'id' attribute - cannot highlight")
                return
            
            logger.info(f"Highlighting object: {window.id} (type: {type(window).__name__})")
            self.highlighted_window = window
            
            # Generate window mesh if not cached
            if window.id not in self.window_meshes:
                logger.debug(f"Creating mesh for object {window.id}")
                window_mesh = self._create_window_mesh(window)
                self.window_meshes[window.id] = window_mesh
                if window_mesh is None:
                    logger.warning(f"Failed to create mesh for object {window.id} - highlight may not be visible")
                else:
                    logger.info(f"Created mesh for object {window.id} with {len(window_mesh.vertices)} vertices, {len(window_mesh.faces)} faces")
            else:
                logger.debug(f"Using cached mesh for object {window.id}")
            
            # Force update to redraw with highlight
            self.update()
            logger.info(f"Update called for object highlight: {window.id}")
        
        def _create_window_mesh(self, window):
            """Create a trimesh representation of a window or object from its properties.
            
            For IFC files, extracts the ACTUAL geometry mesh from the IFC file instead of creating a synthetic mesh.
            For other files, creates a synthetic rectangle mesh from properties.
            """
            import trimesh
            from models.building import Window
            import logging
            
            logger = logging.getLogger(__name__)
            
            # CRITICAL FIX: For IFC files, extract ACTUAL geometry mesh instead of creating synthetic mesh
            if hasattr(window, 'properties') and isinstance(window.properties, dict):
                ifc_element_id = window.properties.get('ifc_element_id')
                ifc_file_path = window.properties.get('ifc_file_path')
                
                if ifc_element_id and ifc_file_path:
                    logger.info(f"Extracting ACTUAL geometry mesh for IFC element {ifc_element_id} from {ifc_file_path}")
                    try:
                        from importers.ifc_importer import IFCImporter
                        actual_mesh = IFCImporter.extract_element_mesh(ifc_file_path, ifc_element_id)
                        if actual_mesh is not None and len(actual_mesh.vertices) > 0 and len(actual_mesh.faces) > 0:
                            logger.info(f"✓ Successfully extracted actual geometry mesh: {len(actual_mesh.vertices)} vertices, {len(actual_mesh.faces)} faces")
                            return actual_mesh
                        else:
                            logger.warning(f"Could not extract geometry for IFC element {ifc_element_id} (mesh is None or empty), falling back to synthetic mesh")
                    except Exception as e:
                        logger.error(f"Error extracting IFC geometry for element {ifc_element_id}: {e}, falling back to synthetic mesh", exc_info=True)
                else:
                    logger.debug(f"Window {getattr(window, 'id', 'unknown')} does not have IFC element info (ifc_element_id={ifc_element_id}, ifc_file_path={ifc_file_path})")
            
            # Fallback: Create synthetic mesh from properties (for non-IFC files or if IFC extraction fails)
            # Validate object has required properties (works for Window or any object with these attributes)
            if not hasattr(window, 'center') or window.center is None:
                logger.warning(f"Object {getattr(window, 'id', 'unknown')} missing center property")
                return None
            if not hasattr(window, 'normal') or window.normal is None:
                logger.warning(f"Object {getattr(window, 'id', 'unknown')} missing normal property")
                return None
            if not hasattr(window, 'size') or window.size is None or len(window.size) < 2:
                logger.warning(f"Object {getattr(window, 'id', 'unknown')} missing or invalid size property")
                return None
            
            # Window properties
            center = np.array(window.center)
            normal = np.array(window.normal)
            width, height = window.size
            
            # Validate size values
            if width <= 0 or height <= 0:
                logger.warning(f"Window {window.id} has invalid size: {width}x{height}")
                return None
            
            # Normalize normal vector
            normal_norm = np.linalg.norm(normal)
            if normal_norm < 1e-6:
                logger.warning(f"Window {window.id} has zero-length normal vector")
                return None
            normal = normal / normal_norm
            
            # Create a rectangle representing the window
            # Window is a flat rectangle perpendicular to its normal
            
            # Find two perpendicular vectors to the normal
            # Use world up (0, 0, 1) or (0, 1, 0) as reference
            if abs(normal[2]) < 0.9:
                # Normal is not too close to Z-axis, use Z as up
                up_ref = np.array([0, 0, 1])
            else:
                # Normal is close to Z-axis, use Y as up
                up_ref = np.array([0, 1, 0])
            
            # Calculate right and up vectors for the window plane
            right = np.cross(normal, up_ref)
            right_norm = np.linalg.norm(right)
            if right_norm < 1e-6:
                # Normal is parallel to up_ref, use different reference
                if abs(normal[0]) < 0.9:
                    up_ref = np.array([1, 0, 0])
                else:
                    up_ref = np.array([0, 1, 0])
                right = np.cross(normal, up_ref)
                right_norm = np.linalg.norm(right)
            
            if right_norm > 1e-6:
                right = right / right_norm
            else:
                # Fallback: use arbitrary perpendicular vector
                right = np.array([1, 0, 0]) if abs(normal[0]) < 0.9 else np.array([0, 1, 0])
            
            up = np.cross(right, normal)
            up_norm = np.linalg.norm(up)
            if up_norm > 1e-6:
                up = up / up_norm
            else:
                # Fallback: use arbitrary perpendicular vector
                up = np.array([0, 0, 1]) if abs(normal[2]) < 0.9 else np.array([0, 1, 0])
            
            # Create rectangle vertices (centered at window center)
            half_width = width / 2.0
            half_height = height / 2.0
            
            # Four corners of the rectangle
            corners = [
                center + (-half_width * right) + (-half_height * up),
                center + (half_width * right) + (-half_height * up),
                center + (half_width * right) + (half_height * up),
                center + (-half_width * right) + (half_height * up)
            ]
            
            # Create two triangles to form the rectangle
            vertices = np.array(corners)
            faces = np.array([
                [0, 1, 2],  # First triangle
                [0, 2, 3]   # Second triangle
            ])
            
            # Create trimesh
            window_mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
            return window_mesh
        
        def initializeGL(self):
            """Initialize OpenGL."""
            from OpenGL import GL
            import logging
            logger = logging.getLogger(__name__)
            
            GL.glEnable(GL.GL_DEPTH_TEST)
            GL.glClearColor(0.2, 0.2, 0.3, 1.0)
            logger.info("OpenGL initialized - shaders will be created")
            
            # Simple shader program for default mesh
            vertex_shader = QOpenGLShader(QOpenGLShader.ShaderTypeBit.Vertex)
            vertex_shader.compileSourceCode("""
                attribute vec3 position;
                uniform mat4 mvpMatrix;
                void main() {
                    gl_Position = mvpMatrix * vec4(position, 1.0);
                }
            """)
            
            fragment_shader = QOpenGLShader(QOpenGLShader.ShaderTypeBit.Fragment)
            fragment_shader.compileSourceCode("""
                void main() {
                    gl_FragColor = vec4(0.8, 0.8, 0.9, 1.0);
                }
            """)
            
            self.shader_program = QOpenGLShaderProgram()
            self.shader_program.addShader(vertex_shader)
            self.shader_program.addShader(fragment_shader)
            self.shader_program.link()
            
            # Colored shader program for window highlighting
            vertex_shader_colored = QOpenGLShader(QOpenGLShader.ShaderTypeBit.Vertex)
            vertex_shader_colored.compileSourceCode("""
                attribute vec3 position;
                uniform mat4 mvpMatrix;
                void main() {
                    gl_Position = mvpMatrix * vec4(position, 1.0);
                }
            """)
            
            fragment_shader_colored = QOpenGLShader(QOpenGLShader.ShaderTypeBit.Fragment)
            fragment_shader_colored.compileSourceCode("""
                uniform vec4 color;
                void main() {
                    gl_FragColor = color;
                }
            """)
            
            self.shader_program_colored = QOpenGLShaderProgram()
            self.shader_program_colored.addShader(vertex_shader_colored)
            self.shader_program_colored.addShader(fragment_shader_colored)
            if not self.shader_program_colored.link():
                import logging
                logging.error(f"Failed to link colored shader: {self.shader_program_colored.log()}")
            else:
                import logging
                logging.info("Colored shader program linked successfully")
            
            # If there's a pending highlight, apply it now that shaders are ready
            if self.highlighted_window is not None:
                import logging
                logging.info(f"Shaders initialized - applying pending highlight for {self.highlighted_window.id}")
                # Re-highlight to create mesh and render
                window_to_highlight = self.highlighted_window
                self.highlighted_window = None  # Clear first
                self.highlight_window(window_to_highlight)  # Re-apply
            
        def resizeGL(self, width, height):
            """Handle resize."""
            from OpenGL import GL
            GL.glViewport(0, 0, width, height)
        
        def paintGL(self):
            """Paint the scene with orbit camera."""
            from OpenGL import GL
            GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
            
            if self.mesh is None or len(self.mesh.vertices) == 0:
                return
            
            # Setup matrices
            width = self.width()
            height = self.height()
            aspect = width / height if height > 0 else 1.0
            
            # Projection matrix
            projection = QMatrix4x4()
            projection.perspective(45.0, aspect, 0.1, 1000.0)  # Increased far plane for large models
            
            # View matrix - orbit camera
            # Calculate camera position using spherical coordinates
            azimuth_rad = np.radians(self.azimuth)
            elevation_rad = np.radians(self.elevation)
            
            # Camera position in spherical coordinates
            x = self.distance * np.cos(elevation_rad) * np.sin(azimuth_rad)
            y = self.distance * np.sin(elevation_rad)
            z = self.distance * np.cos(elevation_rad) * np.cos(azimuth_rad)
            
            camera_pos = QVector3D(x, y, z)
            # Add pan offset to center
            pan_offset = QVector3D(self.pan_x, self.pan_y, 0)
            # Transform pan offset by current rotation to get world-space pan
            # We need to rotate the pan vector based on current view orientation
            azimuth_rad = np.radians(self.azimuth)
            # Pan in the plane perpendicular to view direction
            # Right vector in horizontal plane
            right_x = np.cos(azimuth_rad)
            right_z = -np.sin(azimuth_rad)
            # Forward vector (we'll use this for depth pan if needed)
            forward_x = np.sin(azimuth_rad)
            forward_z = np.cos(azimuth_rad)
            
            # Apply pan in world space (right and up directions)
            world_pan = QVector3D(
                pan_offset.x() * right_x,
                pan_offset.y(),
                pan_offset.x() * right_z
            )
            
            view_center = self.center + world_pan
            up = QVector3D(0, 1, 0)  # World up vector
            
            # Create view matrix looking at center from camera position
            # Camera is at view_center + camera_pos (relative to center)
            view = QMatrix4x4()
            view.lookAt(view_center + camera_pos, view_center, up)
            
            # Model matrix - just scale if needed
            model = QMatrix4x4()
            if self.scale_factor != 1.0:
                model.scale(self.scale_factor)
            
            mvp = projection * view * model
            
            # Draw main mesh
            from OpenGL import GL
            if self.mesh is not None and len(self.mesh.vertices) > 0:
                self.shader_program.bind()
                self.shader_program.setUniformValue("mvpMatrix", mvp)
                
                vertices = self.mesh.vertices
                faces = self.mesh.faces
                
                GL.glBegin(GL.GL_TRIANGLES)
                for face in faces:
                    for vertex_idx in face:
                        if vertex_idx < len(vertices):
                            v = vertices[vertex_idx]
                            GL.glVertex3f(v[0], v[1], v[2])
                GL.glEnd()
                
                self.shader_program.release()
            
            # Draw highlighted window with colored surface
            if self.highlighted_window is not None:
                window_mesh = self.window_meshes.get(self.highlighted_window.id)
                if window_mesh is not None and len(window_mesh.vertices) > 0:
                    # Check if colored shader is available
                    if self.shader_program_colored is None:
                        import logging
                        logging.warning("Colored shader not initialized - cannot highlight window")
                    else:
                        try:
                            # Use colored shader
                            if not self.shader_program_colored.bind():
                                import logging
                                logging.error("Failed to bind colored shader for window highlighting")
                            else:
                                self.shader_program_colored.setUniformValue("mvpMatrix", mvp)
                                
                                # Highlight color: bright blue for visibility
                                color_vec = QVector4D(0.0, 0.5, 1.0, 0.8)  # Blue, semi-transparent
                                self.shader_program_colored.setUniformValue("color", color_vec)
                                
                                # Enable blending for transparency
                                GL.glEnable(GL.GL_BLEND)
                                GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
                                
                                # Draw window mesh
                                vertices = window_mesh.vertices
                                faces = window_mesh.faces
                                
                                GL.glBegin(GL.GL_TRIANGLES)
                                for face in faces:
                                    for vertex_idx in face:
                                        if vertex_idx < len(vertices):
                                            v = vertices[vertex_idx]
                                            GL.glVertex3f(v[0], v[1], v[2])
                                GL.glEnd()
                                
                                GL.glDisable(GL.GL_BLEND)
                                self.shader_program_colored.release()
                        except Exception as e:
                            import logging
                            logging.error(f"Error rendering highlighted window: {e}", exc_info=True)
                else:
                    import logging
                    logging.debug(f"Window mesh not available for highlighting: {self.highlighted_window.id}")
        
        def mousePressEvent(self, event):
            """Handle mouse press for rotation and panning."""
            self.last_pos = event.position()
            self.setFocus()  # Ensure widget receives keyboard events
        
        def mouseMoveEvent(self, event):
            """Handle mouse move for free rotation (left) or panning (right/middle/shift)."""
            if self.last_pos is None:
                return
            
            dx = event.position().x() - self.last_pos.x()
            dy = event.position().y() - self.last_pos.y()
            
            # Left mouse button: Rotate (orbit around model)
            if event.buttons() & Qt.MouseButton.LeftButton:
                # Check if shift is pressed for panning instead
                shift_pressed = event.modifiers() & Qt.KeyboardModifier.ShiftModifier
                
                if shift_pressed:
                    # Shift + Left drag: Pan
                    pan_sensitivity = self.distance * 0.001  # Scale pan by distance
                    # Calculate pan direction based on current view
                    azimuth_rad = np.radians(self.azimuth)
                    elevation_rad = np.radians(self.elevation)
                    
                    # Right vector (perpendicular to view direction in horizontal plane)
                    right_x = np.cos(azimuth_rad)
                    right_z = -np.sin(azimuth_rad)
                    
                    # Up vector (world up, but adjusted for elevation)
                    up_y = 1.0
                    
                    # Apply panning
                    self.pan_x += (dx * right_x - dy * right_z) * pan_sensitivity
                    self.pan_y += dy * up_y * pan_sensitivity
                else:
                    # Free rotation: Left drag rotates around model
                    rotation_speed = 0.5
                    self.azimuth += dx * rotation_speed
                    self.elevation += dy * rotation_speed
                    
                    # Clamp elevation to prevent flipping
                    self.elevation = max(-89.0, min(89.0, self.elevation))
                    
                    # Keep azimuth in reasonable range (optional, allows full rotation)
                    self.azimuth = self.azimuth % 360.0
            
            # Right mouse button: Pan
            elif event.buttons() & Qt.MouseButton.RightButton:
                pan_sensitivity = self.distance * 0.001
                azimuth_rad = np.radians(self.azimuth)
                elevation_rad = np.radians(self.elevation)
                
                right_x = np.cos(azimuth_rad)
                right_z = -np.sin(azimuth_rad)
                up_y = 1.0
                
                self.pan_x += (dx * right_x - dy * right_z) * pan_sensitivity
                self.pan_y += dy * up_y * pan_sensitivity
            
            # Middle mouse button: Pan (alternative)
            elif event.buttons() & Qt.MouseButton.MiddleButton:
                pan_sensitivity = self.distance * 0.001
                azimuth_rad = np.radians(self.azimuth)
                
                right_x = np.cos(azimuth_rad)
                right_z = -np.sin(azimuth_rad)
                up_y = 1.0
                
                self.pan_x += (dx * right_x - dy * right_z) * pan_sensitivity
                self.pan_y += dy * up_y * pan_sensitivity
            
            self.last_pos = event.position()
            self.update()
        
        def wheelEvent(self, event):
            """Handle mouse wheel for zoom (distance adjustment)."""
            delta = event.angleDelta().y() / 120.0
            zoom_factor = 1.0 + delta * 0.1
            self.distance *= zoom_factor
            
            # Clamp distance to reasonable bounds
            min_distance = self.base_distance * 0.1
            max_distance = self.base_distance * 10.0
            self.distance = max(min_distance, min(max_distance, self.distance))
            
            self.update()
    
    class GLBViewerWidget(QWidget):
        """Widget for viewing GLB 3D models (embedded in main window)."""
        
        def __init__(self, parent=None):
            super().__init__(parent)
            self.mesh = None
            # Check OpenGL availability at runtime (always re-check)
            self.opengl_available = check_opengl_available()
            # Log for debugging
            if not self.opengl_available:
                import logging
                logging.warning("OpenGL not available - using fallback viewer. Please restart the application after installing PyOpenGL.")
            self.init_ui()
        
        def init_ui(self):
            """Initialize UI."""
            
            # Apply professional styling
            self.setStyleSheet(f"""
                QWidget {{
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 {COLORS['bg_darker']},
                        stop:0.5 {COLORS['bg_dark']},
                        stop:1 {COLORS['bg_medium']});
                    color: {COLORS['text_primary']};
                }}
                QGroupBox {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 {COLORS['bg_medium']},
                        stop:1 {COLORS['bg_light']});
                    border: 2px solid {COLORS['primary_blue']};
                    border-radius: 8px;
                    margin-top: 10px;
                    padding-top: 15px;
                    font-weight: bold;
                    font-size: 13px;
                    color: {COLORS['primary_blue']};
                }}
                QGroupBox::title {{
                    subcontrol-origin: margin;
                    subcontrol-position: top left;
                    padding: 0 8px;
                    background: {COLORS['bg_dark']};
                    color: {COLORS['cyan']};
                }}
                QLabel {{
                    color: {COLORS['text_primary']};
                    background: transparent;
                }}
                QSlider::groove:horizontal {{
                    background: {COLORS['bg_medium']};
                    height: 8px;
                    border-radius: 4px;
                }}
                QSlider::handle:horizontal {{
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 {COLORS['primary_blue']},
                        stop:1 {COLORS['electric_blue']});
                    border: 2px solid {COLORS['cyan']};
                    width: 18px;
                    height: 18px;
                    margin: -5px 0;
                    border-radius: 9px;
                }}
                QSlider::handle:horizontal:hover {{
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 {COLORS['bright_blue']},
                        stop:1 {COLORS['cyan']});
                }}
            """)
            
            layout = QVBoxLayout()
            layout.setSpacing(10)
            layout.setContentsMargins(15, 15, 15, 15)
            self.setLayout(layout)
            
            # Controls
            controls = QGroupBox("Controls / Управление")
            controls_layout = QHBoxLayout()
            controls_layout.setSpacing(10)
            
            reset_btn = QPushButton("Reset View / Сброс вида")
            reset_btn.setStyleSheet(get_button_style('secondary'))
            reset_btn.clicked.connect(self.reset_view)
            controls_layout.addWidget(reset_btn)
            
            controls_layout.addWidget(QLabel("Zoom / Масштаб:"))
            self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
            self.zoom_slider.setMinimum(10)
            self.zoom_slider.setMaximum(100)
            self.zoom_slider.setValue(50)
            self.zoom_slider.valueChanged.connect(self.on_zoom_changed)
            controls_layout.addWidget(self.zoom_slider)
            
            # Add hint about mouse controls
            hint_label = QLabel("Mouse: Left Drag = Rotate | Right/Shift+Left = Pan | Wheel = Zoom")
            hint_label.setStyleSheet(f"""
                QLabel {{
                    color: {COLORS['text_secondary']};
                    font-size: 10px;
                    background: transparent;
                }}
            """)
            controls_layout.addWidget(hint_label)
            
            controls_layout.addStretch()
            controls.setLayout(controls_layout)
            layout.addWidget(controls)
            
            # 3D Viewer - create OpenGL widget if available
            if self.opengl_available:
                self.viewer = GLBViewerOpenGLWidget(self)  # Set parent to embed in widget
                # Set size policy to expand and fill available space
                self.viewer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            else:
                # Fallback: create a placeholder widget
                self.viewer = QLabel("OpenGL not available. Please restart the application after installing PyOpenGL.", self)
                self.viewer.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.viewer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            layout.addWidget(self.viewer, 1)  # Add stretch factor to make viewer take most space
            
            # Info label
            self.info_label = QLabel("No model loaded / Модель не загружена")
            self.info_label.setStyleSheet(f"""
                QLabel {{
                    background: {COLORS['bg_medium']};
                    color: {COLORS['cyan']};
                    border: 1px solid {COLORS['primary_blue']};
                    border-radius: 6px;
                    padding: 8px;
                    font-size: 11px;
                }}
            """)
            layout.addWidget(self.info_label)
        
        def load_mesh(self, mesh):
            """Load mesh into viewer."""
            self.mesh = mesh
            if self.opengl_available and hasattr(self.viewer, 'set_mesh'):
                self.viewer.set_mesh(mesh)
            elif not self.opengl_available:
                # If OpenGL not available, show message
                self.viewer.setText(f"OpenGL not available.\nMesh loaded: {len(mesh.vertices):,} vertices, {len(mesh.faces):,} faces\nPlease restart the application.")
            
            if mesh is not None:
                info = f"Vertices: {len(mesh.vertices):,}, Faces: {len(mesh.faces):,} / Вершин: {len(mesh.vertices):,}, Граней: {len(mesh.faces):,}"
                self.info_label.setText(info)
            else:
                self.info_label.setText("No model loaded / Модель не загружена")
        
        def set_building(self, building):
            """Set building data for window highlighting."""
            if self.opengl_available and hasattr(self.viewer, 'set_building'):
                self.viewer.set_building(building)
        
        def highlight_window(self, window):
            """Highlight a specific window or object in the 3D viewer."""
            import logging
            logger = logging.getLogger(__name__)
            
            if not self.opengl_available:
                logger.warning("OpenGL not available - cannot highlight object")
                return
            
            if not hasattr(self, 'viewer') or self.viewer is None:
                logger.error("OpenGL viewer widget not initialized - cannot highlight")
                return
            
            if not hasattr(self.viewer, 'highlight_window'):
                logger.warning("3D viewer does not support highlighting")
                return
            
            window_id = getattr(window, 'id', None) if window else None
            logger.info(f"Forwarding highlight request to OpenGL widget for object: {window_id}")
            try:
                self.viewer.highlight_window(window)
                logger.info(f"Highlight request forwarded successfully")
            except Exception as e:
                logger.error(f"Error forwarding highlight request: {e}", exc_info=True)
        
        def reset_view(self):
            """Reset view to default."""
            if self.opengl_available and hasattr(self.viewer, 'azimuth'):
                self.viewer.azimuth = 45.0
                self.viewer.elevation = 30.0
                self.viewer.distance = self.viewer.base_distance if hasattr(self.viewer, 'base_distance') else 5.0
                self.viewer.pan_x = 0.0
                self.viewer.pan_y = 0.0
                # Update zoom slider to match distance
                if hasattr(self.viewer, 'base_distance') and self.viewer.base_distance > 0:
                    zoom_ratio = self.viewer.distance / self.viewer.base_distance
                    slider_value = int(50 * zoom_ratio)
                    slider_value = max(10, min(100, slider_value))
                    self.zoom_slider.setValue(slider_value)
                self.viewer.update()
        
        def on_zoom_changed(self, value):
            """Handle zoom slider change."""
            if self.opengl_available and hasattr(self.viewer, 'base_distance'):
                # Convert slider value (10-100) to distance multiplier
                zoom_ratio = value / 50.0
                self.viewer.distance = self.viewer.base_distance * zoom_ratio
                self.viewer.update()

else:
    # Fallback viewer widget (when OpenGL not available)
    class GLBViewerWidget(QWidget):
        """Simple viewer widget using trimesh's scene viewer as fallback (embedded in main window)."""
        
        def __init__(self, parent=None):
            super().__init__(parent)
            self.mesh = None
            self.building = None  # Store building for window highlighting
            self.highlighted_window = None  # Currently highlighted window
            self.window_meshes = {}  # Cache of window geometry meshes
            self.trimesh_viewer_open = False  # Track if Trimesh viewer is open
            self.init_ui()
        
        def init_ui(self):
            """Initialize UI."""
            
            # Apply professional styling
            self.setStyleSheet(f"""
                QWidget {{
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 {COLORS['bg_darker']},
                        stop:0.5 {COLORS['bg_dark']},
                        stop:1 {COLORS['bg_medium']});
                    color: {COLORS['text_primary']};
                }}
                QLabel {{
                    color: {COLORS['text_primary']};
                    background: transparent;
                    padding: 10px;
                }}
            """)
            
            layout = QVBoxLayout()
            layout.setSpacing(10)
            layout.setContentsMargins(15, 15, 15, 15)
            self.setLayout(layout)
            
            info_label = QLabel(
                "3D Viewer Info / Информация о 3D просмотре:\n\n"
                "For full 3D viewing, install PyOpenGL:\n"
                "Для полного 3D просмотра установите PyOpenGL:\n"
                "pip install PyOpenGL PyOpenGL-accelerate\n\n"
                "Click the button below to open trimesh's built-in viewer:\n"
                "Нажмите кнопку ниже, чтобы открыть встроенный просмотр trimesh:"
            )
            info_label.setWordWrap(True)
            info_label.setStyleSheet(f"""
                QLabel {{
                    background: {COLORS['bg_medium']};
                    color: {COLORS['cyan']};
                    border: 1px solid {COLORS['primary_blue']};
                    border-radius: 6px;
                    padding: 15px;
                    font-size: 11px;
                }}
            """)
            layout.addWidget(info_label)
            
            # Button to launch trimesh viewer
            self.view_button = QPushButton("Open Trimesh Viewer / Открыть просмотр Trimesh")
            self.view_button.setStyleSheet(get_button_style('primary'))
            self.view_button.setEnabled(False)  # Disabled until mesh is loaded
            self.view_button.clicked.connect(self.launch_trimesh_viewer)
            layout.addWidget(self.view_button)
            
            self.info_label = QLabel("No model loaded / Модель не загружена")
            self.info_label.setStyleSheet(f"""
                QLabel {{
                    background: {COLORS['bg_medium']};
                    color: {COLORS['cyan']};
                    border: 1px solid {COLORS['primary_blue']};
                    border-radius: 6px;
                    padding: 8px;
                    font-size: 11px;
                }}
            """)
            layout.addWidget(self.info_label)
        
        def load_mesh(self, mesh, auto_open_viewer=False):
            """Load mesh and show info. Works for both GLB and IFC files.
            
            Args:
                mesh: trimesh.Trimesh object to load
                auto_open_viewer: If True, automatically open Trimesh viewer after loading
            """
            import logging
            logger = logging.getLogger(__name__)
            
            self.mesh = mesh
            if mesh is not None:
                info = f"Mesh loaded / Модель загружена: {len(mesh.vertices):,} vertices / вершин, {len(mesh.faces):,} faces / граней"
                self.info_label.setText(info)
                self.view_button.setEnabled(True)
                logger.info(f"Mesh loaded into Trimesh viewer widget: {len(mesh.vertices):,} vertices, {len(mesh.faces):,} faces")
                # Clear any existing window meshes when new mesh is loaded
                self.window_meshes = {}
                
                # Automatically open Trimesh viewer if requested (for IFC files)
                if auto_open_viewer and not self.trimesh_viewer_open:
                    logger.info("Auto-opening Trimesh viewer for IFC file...")
                    try:
                        self.launch_trimesh_viewer()
                    except Exception as e:
                        logger.warning(f"Could not auto-open Trimesh viewer: {e}")
            else:
                self.info_label.setText("No model loaded / Модель не загружена")
                self.view_button.setEnabled(False)
                logger.warning("No mesh provided to load_mesh()")
        
        def set_building(self, building):
            """Set building data for window highlighting."""
            self.building = building
            self.window_meshes = {}  # Clear cache when building changes
        
        def highlight_window(self, window):
            """Highlight a specific object (window or any object) in Trimesh viewer. Automatically opens viewer if not already open. Works for both GLB and IFC files."""
            import logging
            logger = logging.getLogger(__name__)
            
            if window is None:
                self.highlighted_window = None
                logger.info("Object highlight cleared for Trimesh viewer")
                # Update viewer if it's open
                if self.trimesh_viewer_open:
                    self._update_trimesh_viewer()
                return
            
            # Check if object has required attributes
            if not hasattr(window, 'id'):
                logger.warning(f"Object {type(window)} does not have 'id' attribute - cannot highlight")
                return
            
            # Check if mesh is available (required for highlighting)
            if self.mesh is None:
                logger.warning(f"Cannot highlight object {getattr(window, 'id', 'unknown')}: No mesh loaded in viewer")
                logger.info("Note: Make sure the model (GLB or IFC) has been loaded and mesh generation succeeded")
                return
            
            # Verify mesh has valid data
            if not hasattr(self.mesh, 'vertices') or len(self.mesh.vertices) == 0:
                logger.warning(f"Cannot highlight object {getattr(window, 'id', 'unknown')}: Mesh has no vertices")
                return
            
            logger.info(f"Object highlighted for Trimesh viewer: {window.id} (type: {type(window).__name__})")
            self.highlighted_window = window
            
            # Generate object mesh if not cached (works for windows and other objects)
            if window.id not in self.window_meshes:
                logger.info(f"Creating mesh for object {window.id}...")
                object_mesh = self._create_window_mesh(window)
                self.window_meshes[window.id] = object_mesh
                if object_mesh is None:
                    logger.error(f"Failed to create mesh for object {window.id} - highlight will not be visible")
                else:
                    logger.info(f"✓ Created mesh for object {window.id} with {len(object_mesh.vertices)} vertices, {len(object_mesh.faces)} faces")
            else:
                logger.debug(f"Using cached mesh for object {window.id}")
            
            # If viewer is not open, open it automatically with the highlighted object
            if not self.trimesh_viewer_open:
                logger.info("Trimesh viewer not open - opening automatically with highlighted object")
                # Ensure mesh is loaded before opening viewer
                if self.mesh is None:
                    logger.error("Cannot open Trimesh viewer: No mesh loaded. Please load a model first.")
                    return
                try:
                    self.launch_trimesh_viewer()
                    logger.info("Trimesh viewer opened successfully with highlighted object")
                except Exception as e:
                    logger.error(f"Could not automatically open Trimesh viewer: {e}")
                    import traceback
                    logger.error(f"Error details: {traceback.format_exc()}")
            else:
                # Update viewer if it's already open
                logger.info("Trimesh viewer already open - updating with highlighted object")
                self._update_trimesh_viewer()
        
        def _update_trimesh_viewer(self):
            """Update the Trimesh viewer with current highlighted window (close and reopen)."""
            import logging
            logger = logging.getLogger(__name__)
            
            if self.mesh is None:
                logger.warning("Cannot update Trimesh viewer: No mesh loaded")
                return
            
            try:
                # Close any existing pyglet windows
                try:
                    import pyglet
                    if hasattr(pyglet, 'app') and hasattr(pyglet.app, 'windows'):
                        # Close all pyglet windows
                        windows_to_close = list(pyglet.app.windows)  # Create a copy to avoid modification during iteration
                        for window in windows_to_close:
                            try:
                                window.close()
                                logger.debug(f"Closed pyglet window: {window}")
                            except Exception as e:
                                logger.debug(f"Error closing pyglet window: {e}")
                        logger.info(f"Closed {len(windows_to_close)} pyglet window(s)")
                except Exception as e:
                    logger.debug(f"Could not close existing pyglet windows: {e}")
                
                # Create updated scene and show it
                logger.info("Creating updated Trimesh scene with highlighted object...")
                scene = self._create_trimesh_scene()
                logger.info(f"Scene created with {len(scene.geometry)} geometry object(s)")
                
                # Show the updated scene
                scene.show()
                logger.info("Trimesh viewer updated successfully with highlighted object")
            except Exception as e:
                logger.error(f"Could not update Trimesh viewer: {e}", exc_info=True)
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
        
        def _create_window_mesh(self, window):
            """Create a trimesh representation of an object (window or any object) from its properties. Works for any object with center, normal, and size attributes.
            
            For IFC files, extracts the ACTUAL geometry mesh from the IFC file instead of creating a synthetic mesh.
            For other files, creates a visible box-shaped highlight that extends slightly from the surface for better visibility.
            """
            import trimesh
            import numpy as np
            import logging
            
            logger = logging.getLogger(__name__)
            
            # CRITICAL FIX: For IFC files, extract ACTUAL geometry mesh instead of creating synthetic mesh
            if hasattr(window, 'properties') and isinstance(window.properties, dict):
                ifc_element_id = window.properties.get('ifc_element_id')
                ifc_file_path = window.properties.get('ifc_file_path')
                
                if ifc_element_id and ifc_file_path:
                    logger.info(f"Extracting ACTUAL geometry mesh for IFC element {ifc_element_id} from {ifc_file_path}")
                    try:
                        from importers.ifc_importer import IFCImporter
                        actual_mesh = IFCImporter.extract_element_mesh(ifc_file_path, ifc_element_id)
                        if actual_mesh is not None and len(actual_mesh.vertices) > 0 and len(actual_mesh.faces) > 0:
                            logger.info(f"✓ Successfully extracted actual geometry mesh: {len(actual_mesh.vertices)} vertices, {len(actual_mesh.faces)} faces")
                            return actual_mesh
                        else:
                            logger.warning(f"Could not extract geometry for IFC element {ifc_element_id} (mesh is None or empty), falling back to synthetic mesh")
                    except Exception as e:
                        logger.error(f"Error extracting IFC geometry for element {ifc_element_id}: {e}, falling back to synthetic mesh", exc_info=True)
                else:
                    logger.debug(f"Window {getattr(window, 'id', 'unknown')} does not have IFC element info (ifc_element_id={ifc_element_id}, ifc_file_path={ifc_file_path})")
            
            # Fallback: Create synthetic mesh from properties (for non-IFC files or if IFC extraction fails)
            # Validate object properties (works for windows and other objects)
            if not hasattr(window, 'center') or window.center is None:
                logger.warning(f"Object {getattr(window, 'id', 'unknown')} missing center property")
                return None
            if not hasattr(window, 'normal') or window.normal is None:
                logger.warning(f"Object {getattr(window, 'id', 'unknown')} missing normal property")
                return None
            if not hasattr(window, 'size') or window.size is None or len(window.size) < 2:
                logger.warning(f"Object {getattr(window, 'id', 'unknown')} missing or invalid size property")
                return None
            
            # Object properties
            center = np.array(window.center)
            normal = np.array(window.normal)
            width, height = window.size
            
            # Log window properties for debugging
            logger.info(f"Creating highlight for {window.id}: center={center}, normal={normal}, size={width}x{height}")
            
            # Validate size values
            if width <= 0 or height <= 0:
                logger.warning(f"Object {window.id} has invalid size: {width}x{height}")
                return None
            
            # Normalize normal vector
            normal_norm = np.linalg.norm(normal)
            if normal_norm < 1e-6:
                logger.warning(f"Object {window.id} has zero-length normal vector")
                return None
            normal = normal / normal_norm
            
            # Find two perpendicular vectors to the normal
            if abs(normal[2]) < 0.9:
                up_ref = np.array([0, 0, 1])
            else:
                up_ref = np.array([0, 1, 0])
            
            # Calculate right and up vectors for the object plane
            right = np.cross(normal, up_ref)
            right_norm = np.linalg.norm(right)
            if right_norm < 1e-6:
                if abs(normal[0]) < 0.9:
                    up_ref = np.array([1, 0, 0])
                else:
                    up_ref = np.array([0, 1, 0])
                right = np.cross(normal, up_ref)
                right_norm = np.linalg.norm(right)
            
            if right_norm > 1e-6:
                right = right / right_norm
            else:
                right = np.array([1, 0, 0]) if abs(normal[0]) < 0.9 else np.array([0, 1, 0])
            
            up = np.cross(right, normal)
            up_norm = np.linalg.norm(up)
            if up_norm > 1e-6:
                up = up / up_norm
            else:
                up = np.array([0, 0, 1]) if abs(normal[2]) < 0.9 else np.array([0, 1, 0])
            
            # Create a box-shaped highlight for better visibility
            # Extend slightly outward from the surface (0.05m or 5% of smallest dimension)
            thickness = min(width, height) * 0.05  # 5% of smallest dimension, but at least 0.05m
            thickness = max(0.05, min(thickness, 0.2))  # Clamp between 0.05m and 0.2m
            
            # Position the box slightly in front of the surface (along normal)
            offset = normal * (thickness / 2.0)
            box_center = center + offset
            
            # Create box dimensions
            half_width = width / 2.0
            half_height = height / 2.0
            half_thickness = thickness / 2.0
            
            # Create box vertices (8 corners of a box)
            # Front face (in direction of normal)
            front_corners = [
                box_center + normal * half_thickness + (-half_width * right) + (-half_height * up),
                box_center + normal * half_thickness + (half_width * right) + (-half_height * up),
                box_center + normal * half_thickness + (half_width * right) + (half_height * up),
                box_center + normal * half_thickness + (-half_width * right) + (half_height * up)
            ]
            
            # Back face (opposite direction)
            back_corners = [
                box_center - normal * half_thickness + (-half_width * right) + (-half_height * up),
                box_center - normal * half_thickness + (half_width * right) + (-half_height * up),
                box_center - normal * half_thickness + (half_width * right) + (half_height * up),
                box_center - normal * half_thickness + (-half_width * right) + (half_height * up)
            ]
            
            # Combine all vertices
            vertices = np.array(front_corners + back_corners)
            
            # Create box faces (12 triangles for a box: 2 per face * 6 faces)
            # Vertex indices: 0-3 = front face, 4-7 = back face
            # 0=front-bottom-left, 1=front-bottom-right, 2=front-top-right, 3=front-top-left
            # 4=back-bottom-left, 5=back-bottom-right, 6=back-top-right, 7=back-top-left
            faces = [
                [0, 1, 2], [0, 2, 3],  # Front face (facing normal direction)
                [4, 6, 5], [4, 7, 6],  # Back face (opposite normal)
                [1, 5, 6], [1, 6, 2],  # Right face (connecting front-right to back-right)
                [0, 3, 7], [0, 7, 4],  # Left face (connecting front-left to back-left)
                [0, 4, 5], [0, 5, 1],  # Bottom face
                [3, 2, 6], [3, 6, 7]   # Top face
            ]
            
            # Create trimesh box (more visible than flat rectangle)
            object_mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
            
            logger.debug(f"Created highlight box for {window.id}: center={center}, size={width}x{height}, thickness={thickness:.3f}m")
            return object_mesh
        
        def _create_trimesh_scene(self):
            """Create a trimesh scene with main mesh and highlighted object (if any). Works for windows and other objects."""
            import trimesh
            import logging
            logger = logging.getLogger(__name__)
            
            # Validate mesh is available
            if self.mesh is None:
                logger.error("Cannot create Trimesh scene: No mesh loaded")
                raise ValueError("No mesh loaded - cannot create scene")
            
            if not hasattr(self.mesh, 'vertices') or len(self.mesh.vertices) == 0:
                logger.error("Cannot create Trimesh scene: Mesh has no vertices")
                raise ValueError("Mesh has no vertices - cannot create scene")
            
            # Create scene
            scene = trimesh.Scene()
            
            # Add main mesh to scene (CRITICAL - this is the IFC/GLB model)
            try:
                scene.add_geometry(self.mesh, node_name='building')
                logger.info(f"Added main mesh to scene: {len(self.mesh.vertices):,} vertices, {len(self.mesh.faces):,} faces")
            except Exception as e:
                logger.error(f"Failed to add main mesh to scene: {e}")
                raise
            
            # Add highlighted object mesh if available (works for windows and other objects)
            if self.highlighted_window is not None:
                object_id = getattr(self.highlighted_window, 'id', 'unknown')
                object_mesh = self.window_meshes.get(object_id)
                if object_mesh is not None:
                    # Color the object mesh bright blue/cyan for highlighting (more visible)
                    try:
                        # Create a copy to avoid modifying the cached mesh
                        import copy
                        import numpy as np
                        highlighted_mesh = copy.deepcopy(object_mesh)
                        
                        # Set face colors correctly - trimesh expects (num_faces, 4) array for RGBA
                        # Format: numpy array with shape (num_faces, 4), dtype uint8, values 0-255
                        num_faces = len(highlighted_mesh.faces)
                        # Bright cyan-blue color: RGB(0, 200, 255), alpha: 180 (semi-transparent)
                        color_rgba = np.array([0, 200, 255, 180], dtype=np.uint8)
                        # Apply color to all faces (tile the color for each face)
                        face_colors = np.tile(color_rgba, (num_faces, 1))
                        highlighted_mesh.visual.face_colors = face_colors
                        
                        logger.info(f"Colored highlight mesh for {object_id}: {num_faces} faces, color RGBA(0, 200, 255, 180)")
                        logger.debug(f"Face colors shape: {face_colors.shape}, dtype: {face_colors.dtype}, sample: {face_colors[0] if len(face_colors) > 0 else 'empty'}")
                        
                        # Log mesh bounds for debugging
                        bounds = highlighted_mesh.bounds
                        center = highlighted_mesh.centroid
                        size = bounds[1] - bounds[0]
                        logger.info(f"Highlight mesh bounds: min={bounds[0]}, max={bounds[1]}, center={center}, size={size}")
                        
                        # Compare with main mesh bounds to check if highlight is in reasonable position
                        if hasattr(self, 'mesh') and self.mesh is not None:
                            main_bounds = self.mesh.bounds
                            main_center = self.mesh.centroid
                            main_size = main_bounds[1] - main_bounds[0]
                            distance = np.linalg.norm(np.array(center) - np.array(main_center))
                            logger.info(f"Main mesh bounds: min={main_bounds[0]}, max={main_bounds[1]}, center={main_center}, size={main_size}")
                            logger.info(f"Distance from main mesh center to highlight center: {distance:.2f}m")
                            if distance > 1000:  # More than 1km away - likely wrong coordinate system
                                logger.warning(f"⚠️ Highlight mesh is very far from main mesh ({distance:.2f}m) - coordinate system mismatch possible!")
                        
                        # Make highlight MORE VISIBLE: Create a bounding box that's significantly larger
                        try:
                            # Get the bounding box of the highlighted mesh
                            bbox = highlighted_mesh.bounding_box
                            bbox_center = bbox.centroid
                            bbox_extents = bbox.extents
                            
                            # Ensure minimum size for visibility (at least 0.2m in each dimension if mesh is very small)
                            # If the mesh is very small (like 16 vertices), make the bounding box much larger
                            max_extent = np.max(bbox_extents)
                            if max_extent < 0.5:  # If mesh is smaller than 50cm, make it more visible
                                min_size = 0.3  # 30cm minimum for small meshes
                                bbox_extents = np.maximum(bbox_extents, min_size)
                                scale_factor = 1.5  # Scale up by 50% for small meshes
                            else:
                                min_size = 0.1  # 10cm minimum for larger meshes
                                bbox_extents = np.maximum(bbox_extents, min_size)
                                scale_factor = 1.2  # Scale up by 20% for larger meshes
                            
                            scaled_extents = bbox_extents * scale_factor
                            logger.info(f"Original mesh extents: {bbox_extents}, scaled extents: {scaled_extents}, scale_factor: {scale_factor}")
                            
                            # Create a new box mesh that's larger
                            bbox_mesh = trimesh.creation.box(extents=scaled_extents)
                            bbox_mesh.apply_translation(bbox_center - bbox_mesh.centroid)
                            
                            # Use BRIGHTER, MORE OPAQUE color for bounding box (fully opaque for maximum visibility)
                            bright_color_rgba = np.array([0, 255, 255, 255], dtype=np.uint8)  # Bright cyan, fully opaque
                            bbox_face_colors = np.tile(bright_color_rgba, (len(bbox_mesh.faces), 1))
                            bbox_mesh.visual.face_colors = bbox_face_colors
                            
                            # Also make the original mesh brighter
                            bright_mesh_color = np.array([0, 200, 255, 220], dtype=np.uint8)  # Brighter, more opaque
                            bright_face_colors = np.tile(bright_mesh_color, (num_faces, 1))
                            highlighted_mesh.visual.face_colors = bright_face_colors
                            
                            # Add both the original mesh AND the bounding box for maximum visibility
                            scene.add_geometry(highlighted_mesh, node_name=f'highlighted_{object_id}')
                            scene.add_geometry(bbox_mesh, node_name=f'highlighted_bbox_{object_id}')
                            logger.info(f"Added highlighted object {object_id} with bounding box to Trimesh scene: mesh={len(highlighted_mesh.vertices)} vertices, bbox={len(bbox_mesh.vertices)} vertices")
                            logger.info(f"Bounding box extents: {scaled_extents}, center: {bbox_center}")
                        except Exception as bbox_error:
                            logger.warning(f"Could not create bounding box for highlight: {bbox_error}, using original mesh only", exc_info=True)
                            # Make the original mesh brighter if bounding box fails
                            bright_mesh_color = np.array([0, 255, 255, 255], dtype=np.uint8)  # Bright cyan, fully opaque
                            bright_face_colors = np.tile(bright_mesh_color, (num_faces, 1))
                            highlighted_mesh.visual.face_colors = bright_face_colors
                            scene.add_geometry(highlighted_mesh, node_name=f'highlighted_{object_id}')
                            logger.info(f"Added highlighted object {object_id} to Trimesh scene: {len(highlighted_mesh.vertices)} vertices, {len(highlighted_mesh.faces)} faces")
                    except Exception as e:
                        logger.warning(f"Could not color object mesh: {e}, showing without color", exc_info=True)
                        try:
                            scene.add_geometry(object_mesh, node_name=f'highlighted_{object_id}')
                        except Exception as e2:
                            logger.error(f"Failed to add object mesh to scene: {e2}", exc_info=True)
                else:
                    logger.warning(f"Object mesh not available for {object_id} - mesh may not have been created")
            
            logger.info(f"Trimesh scene created with {len(scene.geometry)} geometry object(s)")
            return scene
        
        def launch_trimesh_viewer(self):
            """Launch trimesh's built-in viewer with optional window highlighting. Works for both GLB and IFC files."""
            import logging
            logger = logging.getLogger(__name__)
            
            if self.mesh is None:
                logger.error("Cannot launch Trimesh viewer: No mesh loaded")
                QMessageBox.warning(
                    self,
                    "Viewer Error / Ошибка просмотра",
                    "No mesh loaded.\n"
                    "Модель не загружена.\n\n"
                    "Please load a model (GLB or IFC file) first.\n"
                    "Пожалуйста, сначала загрузите модель (GLB или IFC файл)."
                )
                return
            
            if not hasattr(self.mesh, 'vertices') or len(self.mesh.vertices) == 0:
                logger.error("Cannot launch Trimesh viewer: Mesh has no vertices")
                QMessageBox.warning(
                    self,
                    "Viewer Error / Ошибка просмотра",
                    "Mesh has no geometry.\n"
                    "Модель не имеет геометрии.\n\n"
                    "The loaded model has no vertices.\n"
                    "Загруженная модель не имеет вершин."
                )
                return
            
            try:
                # Check if pyglet is available
                try:
                    import pyglet
                    if not hasattr(pyglet, 'app'):
                        raise ImportError("pyglet.app not available")
                except ImportError as e:
                    QMessageBox.warning(
                        self,
                        "Viewer Error / Ошибка просмотра",
                        "Trimesh viewer requires pyglet<2.\n"
                        "Trimesh просмотр требует pyglet<2.\n\n"
                        f"Error / Ошибка: {str(e)}\n\n"
                        "Please install: pip install \"pyglet<2\""
                    )
                    return
                
                # Create scene with main mesh and highlighted window (if any)
                logger.info(f"Creating Trimesh scene with mesh: {len(self.mesh.vertices):,} vertices, {len(self.mesh.faces):,} faces")
                scene = self._create_trimesh_scene()
                
                # Mark viewer as open
                self.trimesh_viewer_open = True
                
                # Try to launch viewer (must be in main thread for pyglet)
                # Note: This may block the UI, but pyglet requires main thread
                try:
                    logger.info("Launching Trimesh viewer window...")
                    scene.show()
                    logger.info("Trimesh viewer launched successfully")
                except RuntimeError as e:
                    error_msg = str(e)
                    if "EventLoop.run()" in error_msg or "thread" in error_msg.lower():
                        QMessageBox.warning(
                            self,
                            "Viewer Error / Ошибка просмотра",
                            "Trimesh viewer cannot run in a separate thread.\n"
                            "Trimesh просмотр не может работать в отдельном потоке.\n\n"
                            "The viewer requires the main thread.\n"
                            "Просмотр требует главный поток.\n\n"
                            "Note: This feature may not work in all environments.\n"
                            "Примечание: Эта функция может не работать во всех средах."
                        )
                    elif "OpenGL" in error_msg or "wgl" in error_msg.lower() or "ARB" in error_msg:
                        QMessageBox.warning(
                            self,
                            "Viewer Error / Ошибка просмотра",
                            "OpenGL driver does not support required features.\n"
                            "Драйвер OpenGL не поддерживает необходимые функции.\n\n"
                            f"Error / Ошибка: {error_msg}\n\n"
                            "The trimesh viewer requires OpenGL support.\n"
                            "Trimesh просмотр требует поддержку OpenGL.\n\n"
                            "Try using the embedded 3D viewer instead.\n"
                            "Попробуйте использовать встроенный 3D просмотр."
                        )
                    else:
                        QMessageBox.warning(
                            self,
                            "Viewer Error / Ошибка просмотра",
                            f"Could not launch viewer / Не удалось запустить просмотр:\n{error_msg}"
                        )
                    logger.error(f"Failed to launch Trimesh viewer: {error_msg}")
                except Exception as e:
                    logger.error(f"Unexpected error launching Trimesh viewer: {e}")
                    import traceback
                    logger.error(f"Error details: {traceback.format_exc()}")
                    QMessageBox.warning(
                        self,
                        "Viewer Error / Ошибка просмотра",
                        f"Could not launch viewer / Не удалось запустить просмотр:\n{str(e)}"
                    )
            except Exception as e:
                logger.error(f"Error in launch_trimesh_viewer outer try block: {e}")
                import traceback
                logger.error(f"Error details: {traceback.format_exc()}")
                QMessageBox.warning(
                    self,
                    "Viewer Error / Ошибка просмотра",
                    f"Could not launch viewer / Не удалось запустить просмотр:\n{str(e)}"
                )

