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
            """Create a trimesh representation of a window or object from its properties."""
            import trimesh
            from models.building import Window
            import logging
            
            logger = logging.getLogger(__name__)
            
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
        
        def load_mesh(self, mesh):
            """Load mesh and show info."""
            self.mesh = mesh
            if mesh is not None:
                info = f"Mesh loaded / Модель загружена: {len(mesh.vertices):,} vertices / вершин, {len(mesh.faces):,} faces / граней"
                self.info_label.setText(info)
                self.view_button.setEnabled(True)
            else:
                self.info_label.setText("No model loaded / Модель не загружена")
                self.view_button.setEnabled(False)
        
        def set_building(self, building):
            """Set building data for window highlighting (not available without OpenGL)."""
            pass  # Window highlighting requires OpenGL
        
        def highlight_window(self, window):
            """Highlight a specific window (not available without OpenGL)."""
            pass  # Window highlighting requires OpenGL
        
        def launch_trimesh_viewer(self):
            """Launch trimesh's built-in viewer."""
            if self.mesh is not None:
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
                    
                    # Try to launch viewer (must be in main thread for pyglet)
                    # Note: This may block the UI, but pyglet requires main thread
                    try:
                        self.mesh.show()
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
                    except Exception as e:
                        QMessageBox.warning(
                            self,
                            "Viewer Error / Ошибка просмотра",
                            f"Could not launch viewer / Не удалось запустить просмотр:\n{str(e)}"
                        )
                except Exception as e:
                    QMessageBox.warning(
                        self,
                        "Viewer Error / Ошибка просмотра",
                        f"Could not launch viewer / Не удалось запустить просмотр:\n{str(e)}"
                    )

