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
    from PyQt6.QtCore import Qt, pyqtSignal, QTimer
    from PyQt6.QtOpenGLWidgets import QOpenGLWidget
    from PyQt6.QtGui import QMatrix4x4, QVector3D, QVector4D
    # Import OpenGL shader classes
    # In PyQt6, QOpenGLShaderProgram and QOpenGLShader are in PyQt6.QtOpenGL
    # This module may not be available in all PyQt6 installations
    try:
        from PyQt6.QtOpenGL import QOpenGLShaderProgram, QOpenGLShader
    except ImportError:
        # QtOpenGL module is not available
        # This is a known issue with some PyQt6 installations
        # The embedded OpenGL viewer requires these classes
        # Solution: Use the Trimesh fallback viewer or reinstall PyQt6 with OpenGL support
        raise ImportError(
            "PyQt6.QtOpenGL module not available.\n"
            "The embedded 3D viewer requires QOpenGLShaderProgram and QOpenGLShader.\n"
            "These are in PyQt6.QtOpenGL which may not be included in your PyQt6 installation.\n"
            "Options:\n"
            "1. Use the Trimesh viewer (fallback - already working)\n"
            "2. Reinstall PyQt6: pip uninstall PyQt6 && pip install PyQt6\n"
            "3. Check if PyQt6-Qt6 package is available: pip install PyQt6-Qt6"
        )
    PYQT6_AVAILABLE = True
    # Log at module load (logging may not be configured yet, so use print as fallback)
    try:
        import logging
        logger = logging.getLogger(__name__)
        logger.info("✓ PyQt6 imported successfully")
    except:
        print("✓ PyQt6 imported successfully")
except ImportError as e:
    PYQT6_AVAILABLE = False
    # Log at module load (logging may not be configured yet, so use print as fallback)
    try:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"❌ PyQt6 import failed: {e}")
    except:
        print(f"❌ PyQt6 import failed: {e}")

# Check OpenGL availability dynamically
def check_opengl_available():
    """Check if OpenGL is available at runtime."""
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info("=== Checking OpenGL availability ===")
    if not PYQT6_AVAILABLE:
        logger.error("❌ PyQt6 not available - OpenGL cannot be used")
        return False
    logger.info("✓ PyQt6 is available")
    
    try:
        from OpenGL import GL
        logger.info("✓ OpenGL module imported successfully")
        # Also check that QOpenGLWidget is available
        from PyQt6.QtOpenGLWidgets import QOpenGLWidget
        logger.info("✓ QOpenGLWidget is available")
        logger.info("✓ OpenGL is AVAILABLE - embedded 3D viewer will be used")
        return True
    except ImportError as e:
        logger.error(f"❌ OpenGL import failed: {e}")
        logger.error("   Install with: pip install PyOpenGL PyOpenGL-accelerate")
        logger.error("   Then restart the application")
        return False

# Check at module load time (but will re-check at runtime)
OPENGL_AVAILABLE = check_opengl_available()

# Always define GLBViewerWidget if PyQt6 is available (will check OpenGL at runtime)
if PYQT6_AVAILABLE:
    # Log which viewer class will be used
    try:
        import logging
        logger = logging.getLogger(__name__)
        logger.info("=== Module glb_viewer.py loaded ===")
        logger.info(f"PYQT6_AVAILABLE: {PYQT6_AVAILABLE}")
        logger.info(f"OPENGL_AVAILABLE (module load): {OPENGL_AVAILABLE}")
        logger.info("Using OpenGL-enabled GLBViewerWidget class (will check OpenGL at runtime)")
    except:
        pass  # Logging may not be configured yet
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
            self.vertex_colors = None  # Store vertex colors for rendering
            # Window highlighting
            self.building = None  # Store building for window access
            self.ifc_file = None  # Store IFC file reference for extracting actual geometry
            self.highlighted_window = None  # Currently highlighted window/space/door
            self.window_meshes = {}  # Cache of window/space/door geometry meshes
            self.window_coordinate_transform = None  # Cached transformation offset for window coordinates
            self.highlight_is_space = False  # Track if current highlight is a space (for red color)
            self.highlight_is_door = False  # Track if current highlight is a door (for green color)
            self.highlight_is_window = False  # Track if current highlight is an IFC window (for cyan color)
            self.highlight_is_wall = False  # Track if current highlight is a wall (for yellow color)
            self.highlight_is_slab = False  # Track if current highlight is a slab (for magenta color)
            self.highlight_is_storey = False  # Track if current highlight is a storey (for orange color)
            self.highlight_is_opening = False  # Track if current highlight is an opening (for purple color)
            # Auto-rotation
            self.auto_rotate = False  # Auto-rotation enabled/disabled
            self.rotation_speed = 0.5  # Degrees per frame (adjustable)
            self.rotation_timer = QTimer(self)
            self.rotation_timer.timeout.connect(self._auto_rotate_step)
            self.rotation_timer.setInterval(16)  # ~60 FPS
            
            # Enable keyboard focus for arrow key controls
            self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            
        def set_mesh(self, mesh):
            """Set the mesh to display."""
            import logging
            logger = logging.getLogger(__name__)
            
            logger.info("=== set_mesh() called ===")
            logger.info(f"Mesh provided: {mesh is not None}")
            
            self.mesh = mesh
            self.window_coordinate_transform = None  # Clear transformation cache when mesh changes
            if mesh is not None:
                # Calculate center and scale
                vertices = mesh.vertices
                if len(vertices) > 0:
                    logger.info(f"✓ Mesh has {len(vertices):,} vertices, {len(mesh.faces):,} faces")
                    min_bounds = np.min(vertices, axis=0)
                    max_bounds = np.max(vertices, axis=0)
                    center = (min_bounds + max_bounds) / 2
                    self.center = QVector3D(center[0], center[1], center[2])
                    logger.info(f"✓ Calculated mesh center: ({self.center.x():.2f}, {self.center.y():.2f}, {self.center.z():.2f})")
                    
                    # Extract colors from mesh
                    self.vertex_colors = None
                    try:
                        # Check for face colors first (most common in trimesh)
                        if hasattr(mesh, 'visual') and hasattr(mesh.visual, 'face_colors'):
                            face_colors = mesh.visual.face_colors
                            if face_colors is not None and len(face_colors) > 0:
                                # Expand face colors to vertex colors (each vertex gets the color of its face)
                                faces = mesh.faces
                                vertex_colors_list = []
                                for face_idx, face in enumerate(faces):
                                    if face_idx < len(face_colors):
                                        # Get color for this face (normalize to 0-1 range)
                                        face_color = face_colors[face_idx]
                                        if len(face_color) >= 3:
                                            # Convert to float 0-1 range
                                            if face_color.dtype == np.uint8:
                                                color = face_color[:3].astype(np.float32) / 255.0
                                            else:
                                                color = face_color[:3].astype(np.float32)
                                            # Assign same color to all 3 vertices of the face
                                            for _ in range(3):
                                                vertex_colors_list.append(color)
                                
                                if len(vertex_colors_list) > 0:
                                    self.vertex_colors = np.array(vertex_colors_list, dtype=np.float32)
                                    logger.info(f"✓ Extracted {len(self.vertex_colors)} vertex colors from mesh face colors")
                        # Check for vertex colors as fallback
                        elif hasattr(mesh, 'visual') and hasattr(mesh.visual, 'vertex_colors'):
                            vertex_colors = mesh.visual.vertex_colors
                            if vertex_colors is not None and len(vertex_colors) > 0:
                                # Normalize to 0-1 range
                                if vertex_colors.dtype == np.uint8:
                                    self.vertex_colors = vertex_colors[:, :3].astype(np.float32) / 255.0
                                else:
                                    self.vertex_colors = vertex_colors[:, :3].astype(np.float32)
                                logger.info(f"✓ Extracted {len(self.vertex_colors)} vertex colors from mesh")
                    except Exception as e:
                        logger.debug(f"Could not extract colors from mesh: {e}, will use default color")
                    
                    if self.vertex_colors is None:
                        logger.info("Mesh has no colors - will use default shader color")
                    
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
                        logger.info(f"✓ Calculated camera distance: {self.distance:.2f} (model size: {size:.2f})")
                    else:
                        logger.warning("⚠ Mesh size is 0 - cannot calculate camera distance")
                    logger.info(f"✓ Mesh set successfully: {len(vertices):,} vertices, {len(mesh.faces):,} faces")
                else:
                    logger.error("❌ Mesh has no vertices - cannot display")
            else:
                logger.error("❌ Mesh is None - cannot display")
            
            # Force update - ensure widget is visible and OpenGL context is ready
            # Only make context current if widget is visible (otherwise it will fail)
            logger.info(f"Widget visible: {self.isVisible()}")
            if self.isVisible():
                try:
                    self.makeCurrent()  # Ensure OpenGL context is current
                    logger.info("✓ Made OpenGL context current")
                except Exception as e:
                    logger.warning(f"⚠ Could not make OpenGL context current: {e}")
            else:
                logger.info("Widget not visible - will render when shown")
            self.update()  # Trigger repaint
            logger.info("✓ Called update() to trigger repaint")
        
        def set_building(self, building):
            """Set building data for window highlighting."""
            self.building = building
            self.window_meshes = {}  # Clear cache when building changes
            self.window_coordinate_transform = None  # Clear transformation cache when building changes
            self.highlighted_window = None
            self.highlight_is_space = False
            self.highlight_is_door = False
            self.update()
        
        def set_ifc_file(self, ifc_file):
            """Set IFC file reference for extracting actual geometry from IFC elements."""
            import logging
            logger = logging.getLogger(__name__)
            self.ifc_file = ifc_file
            if ifc_file:
                try:
                    window_count = len(ifc_file.by_type('IfcWindow'))
                    logger.info(f"IFC file set: {getattr(ifc_file, 'schema', 'Unknown schema')}")
                    logger.info(f"  IFC file has {window_count} windows")
                except:
                    logger.info(f"IFC file set (could not count windows)")
            else:
                logger.info("IFC file cleared")
        
        def highlight_window(self, window):
            """Highlight a specific window, space, door, or object with colored surface (blue for windows, red for spaces, green for doors)."""
            import logging
            logger = logging.getLogger(__name__)
            
            if window is None:
                self.highlighted_window = None
                self.highlight_is_space = False
                self.highlight_is_door = False
                self.highlight_is_window = False
                self.highlight_is_wall = False
                self.highlight_is_slab = False
                self.highlight_is_storey = False
                self.highlight_is_opening = False
                logger.info("Object highlight cleared")
                # Ensure widget is visible and update
                if self.isVisible():
                    self.update()
                return
            
            # DIAGNOSTIC: Log object type and attributes
            logger.info(f"=== WINDOW/OBJECT HIGHLIGHT DIAGNOSTIC ===")
            logger.info(f"Object type: {type(window).__name__}")
            logger.info(f"Object class: {window.__class__}")
            logger.info(f"Object module: {getattr(window.__class__, '__module__', 'unknown')}")
            
            # Check if this is a Window object from models.building
            is_window_object = False
            try:
                from models.building import Window
                is_window_object = isinstance(window, Window)
                logger.info(f"Is Window object (from models.building): {is_window_object}")
            except ImportError:
                logger.debug("Could not import Window class for type checking")
            
            # Check if this is an IFC element (space, door, window, wall, slab, storey, opening, etc.)
            is_ifc_space = False
            is_ifc_door = False
            is_ifc_window = False
            is_ifc_wall = False
            is_ifc_slab = False
            is_ifc_storey = False
            is_ifc_opening = False
            
            logger.info(f"=== IFC ELEMENT DETECTION IN highlight_window ===")
            if hasattr(window, 'is_a') and callable(window.is_a):
                try:
                    is_ifc_space = window.is_a("IfcSpace")
                    is_ifc_door = window.is_a("IfcDoor")
                    is_ifc_window = window.is_a("IfcWindow")
                    is_ifc_wall = window.is_a("IfcWall") or window.is_a("IfcWallStandardCase")
                    is_ifc_slab = window.is_a("IfcSlab")
                    is_ifc_storey = window.is_a("IfcBuildingStorey")
                    is_ifc_opening = window.is_a("IfcOpeningElement")
                    logger.info(f"Using is_a() method: space={is_ifc_space}, door={is_ifc_door}, window={is_ifc_window}, wall={is_ifc_wall}, slab={is_ifc_slab}, storey={is_ifc_storey}, opening={is_ifc_opening}")
                except Exception as e:
                    logger.warning(f"Error calling is_a() method: {e}")
            elif hasattr(window, '__class__'):
                class_str = str(window.__class__)
                is_ifc_space = 'IfcSpace' in class_str
                is_ifc_door = 'IfcDoor' in class_str
                is_ifc_window = 'IfcWindow' in class_str
                is_ifc_wall = 'IfcWall' in class_str
                is_ifc_slab = 'IfcSlab' in class_str
                is_ifc_storey = 'IfcBuildingStorey' in class_str
                is_ifc_opening = 'IfcOpeningElement' in class_str
                logger.info(f"Using class string check: class_str={class_str}")
                logger.info(f"  space={is_ifc_space}, door={is_ifc_door}, window={is_ifc_window}, wall={is_ifc_wall}, slab={is_ifc_slab}, storey={is_ifc_storey}, opening={is_ifc_opening}")
            
            logger.info(f"Final detection: is_window_object={is_window_object}, space={is_ifc_space}, door={is_ifc_door}, window={is_ifc_window}, wall={is_ifc_wall}, slab={is_ifc_slab}, storey={is_ifc_storey}, opening={is_ifc_opening}")
            
            # Get object ID - ensure uniqueness
            obj_id = None
            if hasattr(window, 'GlobalId'):
                obj_id = window.GlobalId
                logger.info(f"Found GlobalId: {obj_id}")
            elif hasattr(window, 'id'):
                if callable(window.id):
                    obj_id = str(window.id())
                else:
                    obj_id = str(window.id)
                logger.info(f"Found id (callable={callable(window.id) if hasattr(window, 'id') else 'N/A'}): {obj_id}")
            
            # For Window objects, ensure unique ID by including position if available
            if obj_id and is_window_object:
                # Add position hash to make ID unique if multiple windows might have same ID
                if hasattr(window, 'center') and window.center is not None:
                    center = window.center
                    # Create a unique identifier from position (rounded to avoid floating point issues)
                    # Use absolute value of hash to avoid negative numbers
                    pos_hash = abs(hash(tuple(round(c, 2) for c in center)))
                    obj_id = f"{obj_id}_pos{pos_hash}"
                    logger.info(f"Enhanced Window object ID with position hash: {obj_id}")
                    logger.info(f"  Window center: {center}")
            
            if obj_id is None:
                logger.error(f"❌ ISSUE #1: Can't find the object on the model - Object {type(window)} does not have identifiable ID (no GlobalId or id attribute)")
                logger.error(f"   Object attributes: {dir(window)}")
                return
            else:
                logger.info(f"✓ Object ID found: {obj_id}")
                # Check if this ID is already in cache
                if obj_id in self.window_meshes:
                    cached_mesh = self.window_meshes[obj_id]
                    logger.info(f"  Cached mesh exists: {len(cached_mesh.vertices) if cached_mesh else 0} vertices")
                else:
                    logger.info(f"  No cached mesh - will create new one")
            
            # Check if widget is visible - if not, store highlight for later
            if not self.isVisible():
                if is_ifc_space:
                    obj_type = 'space'
                elif is_ifc_door:
                    obj_type = 'door'
                elif is_ifc_window:
                    obj_type = 'IFC window'
                elif is_ifc_wall:
                    obj_type = 'wall'
                elif is_ifc_slab:
                    obj_type = 'slab'
                elif is_ifc_opening:
                    obj_type = 'opening'
                elif is_ifc_storey:
                    obj_type = 'storey'
                elif is_window_object:
                    obj_type = 'window'
                else:
                    obj_type = 'object'
                logger.info(f"Widget not visible - storing highlight for {obj_type} {obj_id} to apply when visible")
                self.highlighted_window = window
                # Still create the mesh so it's ready when widget becomes visible
                if obj_id not in self.window_meshes:
                    if is_ifc_space:
                        space_mesh = self._create_space_mesh_from_ifc(window)
                        if space_mesh:
                            self.window_meshes[obj_id] = space_mesh
                    elif is_ifc_door:
                        door_mesh = self._create_door_mesh_from_ifc(window)
                        if door_mesh:
                            self.window_meshes[obj_id] = door_mesh
                    elif is_ifc_window:
                        window_mesh = self._create_ifc_window_mesh_from_ifc(window)
                        if window_mesh:
                            self.window_meshes[obj_id] = window_mesh
                    elif is_ifc_wall:
                        wall_mesh = self._create_wall_mesh_from_ifc(window)
                        if wall_mesh:
                            self.window_meshes[obj_id] = wall_mesh
                    elif is_ifc_slab:
                        slab_mesh = self._create_slab_mesh_from_ifc(window)
                        if slab_mesh:
                            self.window_meshes[obj_id] = slab_mesh
                    elif is_ifc_opening:
                        opening_mesh = self._create_opening_mesh_from_ifc(window)
                        if opening_mesh:
                            self.window_meshes[obj_id] = opening_mesh
                    elif is_ifc_storey:
                        storey_mesh = self._create_storey_mesh_from_ifc(window)
                        if storey_mesh:
                            self.window_meshes[obj_id] = storey_mesh
                    else:
                        # Window object or generic object with center/normal/size
                        window_mesh = self._create_window_mesh(window)
                        if window_mesh:
                            self.window_meshes[obj_id] = window_mesh
                return
            
            # Check if shaders are initialized (OpenGL context must be ready)
            if self.shader_program is None or self.shader_program_colored is None:
                logger.warning("OpenGL shaders not initialized yet - cannot highlight. Widget may need to be visible first.")
                # Store the object to highlight later when shaders are ready
                self.highlighted_window = window
                # Still create the mesh so it's ready
                if obj_id not in self.window_meshes:
                    if is_ifc_space:
                        space_mesh = self._create_space_mesh_from_ifc(window)
                        if space_mesh:
                            self.window_meshes[obj_id] = space_mesh
                    elif is_ifc_door:
                        door_mesh = self._create_door_mesh_from_ifc(window)
                        if door_mesh:
                            self.window_meshes[obj_id] = door_mesh
                    elif is_ifc_window:
                        window_mesh = self._create_ifc_window_mesh_from_ifc(window)
                        if window_mesh:
                            self.window_meshes[obj_id] = window_mesh
                    elif is_ifc_wall:
                        wall_mesh = self._create_wall_mesh_from_ifc(window)
                        if wall_mesh:
                            self.window_meshes[obj_id] = wall_mesh
                    elif is_ifc_slab:
                        slab_mesh = self._create_slab_mesh_from_ifc(window)
                        if slab_mesh:
                            self.window_meshes[obj_id] = slab_mesh
                    elif is_ifc_opening:
                        opening_mesh = self._create_opening_mesh_from_ifc(window)
                        if opening_mesh:
                            self.window_meshes[obj_id] = opening_mesh
                    elif is_ifc_storey:
                        storey_mesh = self._create_storey_mesh_from_ifc(window)
                        if storey_mesh:
                            self.window_meshes[obj_id] = storey_mesh
                    else:
                        # Window object or generic object with center/normal/size
                        window_mesh = self._create_window_mesh(window)
                        if window_mesh:
                            self.window_meshes[obj_id] = window_mesh
                return
            
            # Check if main mesh is loaded
            if is_ifc_space:
                obj_type = 'space'
            elif is_ifc_door:
                obj_type = 'door'
            elif is_ifc_window:
                obj_type = 'IFC window'
            elif is_ifc_wall:
                obj_type = 'wall'
            elif is_ifc_slab:
                obj_type = 'slab'
            elif is_ifc_opening:
                obj_type = 'opening'
            elif is_ifc_storey:
                obj_type = 'storey'
            elif is_window_object:
                obj_type = 'window'
            else:
                obj_type = 'object'
            
            if self.mesh is None or len(self.mesh.vertices) == 0:
                logger.warning(f"Cannot highlight {obj_type} {obj_id}: No mesh loaded in 3D viewer")
                return
            
            logger.info(f"=== STEP-BY-STEP WINDOW HIGHLIGHTING DIAGNOSTIC ===")
            logger.info(f"STEP 1: Object type: {obj_type}, ID: {obj_id}, Python type: {type(window).__name__}")
            logger.info(f"STEP 2: Main mesh loaded: {self.mesh is not None}")
            if self.mesh is not None:
                logger.info(f"STEP 2a: Main mesh has {len(self.mesh.vertices):,} vertices, {len(self.mesh.faces):,} faces")
                logger.info(f"STEP 2b: Main mesh bounds: {self.mesh.bounds}")
                logger.info(f"STEP 2c: Main mesh center: {self.mesh.centroid}")
            
            logger.info(f"STEP 3: Highlighting {obj_type}: {obj_id} (type: {type(window).__name__})")
            self.highlighted_window = window
            
            # Generate mesh if not cached
            if obj_id not in self.window_meshes:
                logger.info(f"Creating mesh for {obj_type} {obj_id}")
                if is_ifc_space:
                    space_mesh = self._create_space_mesh_from_ifc(window)
                    self.window_meshes[obj_id] = space_mesh
                    if space_mesh is None:
                        logger.error(f"❌ ISSUE #2: Error on highlight part - Failed to create mesh for space {obj_id}")
                        logger.error(f"   This means geometry extraction failed. Check logs above for details.")
                    else:
                        logger.info(f"✓ Created mesh for space {obj_id} with {len(space_mesh.vertices)} vertices, {len(space_mesh.faces)} faces")
                elif is_ifc_door:
                    logger.info(f"Attempting to create door mesh for {obj_id}...")
                    door_mesh = self._create_door_mesh_from_ifc(window)
                    self.window_meshes[obj_id] = door_mesh
                    if door_mesh is None:
                        logger.error(f"❌ ISSUE #2: Error on highlight part - Failed to create mesh for door {obj_id}")
                        logger.error(f"   This means geometry extraction failed. Check logs above for details.")
                        logger.error(f"   Door element: {window}")
                        logger.error(f"   Door GlobalId: {getattr(window, 'GlobalId', 'N/A')}")
                    else:
                        logger.info(f"✓ Created mesh for door {obj_id} with {len(door_mesh.vertices)} vertices, {len(door_mesh.faces)} faces")
                elif is_ifc_window:
                    logger.info(f"Attempting to create IFC window mesh for {obj_id}...")
                    window_mesh = self._create_ifc_window_mesh_from_ifc(window)
                    self.window_meshes[obj_id] = window_mesh
                    if window_mesh is None:
                        logger.error(f"❌ ISSUE #2: Error on highlight part - Failed to create mesh for IFC window {obj_id}")
                        logger.error(f"   This means geometry extraction failed. Check logs above for details.")
                    else:
                        logger.info(f"✓ Created mesh for IFC window {obj_id} with {len(window_mesh.vertices)} vertices, {len(window_mesh.faces)} faces")
                elif is_ifc_wall:
                    logger.info(f"Attempting to create wall mesh for {obj_id}...")
                    wall_mesh = self._create_wall_mesh_from_ifc(window)
                    self.window_meshes[obj_id] = wall_mesh
                    if wall_mesh is None:
                        logger.error(f"❌ ISSUE #2: Error on highlight part - Failed to create mesh for wall {obj_id}")
                        logger.error(f"   This means geometry extraction failed. Check logs above for details.")
                    else:
                        logger.info(f"✓ Created mesh for wall {obj_id} with {len(wall_mesh.vertices)} vertices, {len(wall_mesh.faces)} faces")
                elif is_ifc_slab:
                    logger.info(f"Attempting to create slab mesh for {obj_id}...")
                    slab_mesh = self._create_slab_mesh_from_ifc(window)
                    self.window_meshes[obj_id] = slab_mesh
                    if slab_mesh is None:
                        logger.error(f"❌ ISSUE #2: Error on highlight part - Failed to create mesh for slab {obj_id}")
                        logger.error(f"   This means geometry extraction failed. Check logs above for details.")
                    else:
                        logger.info(f"✓ Created mesh for slab {obj_id} with {len(slab_mesh.vertices)} vertices, {len(slab_mesh.faces)} faces")
                elif is_ifc_opening:
                    logger.info(f"Attempting to create opening mesh for {obj_id}...")
                    opening_mesh = self._create_opening_mesh_from_ifc(window)
                    if opening_mesh is None:
                        logger.warning(f"⚠ Opening {obj_id} has no geometry - this may be normal for some openings")
                        logger.warning(f"   Some openings are defined by relationships rather than direct geometry")
                        # Don't cache None - this prevents rendering errors
                    else:
                        self.window_meshes[obj_id] = opening_mesh
                        logger.info(f"✓ Created mesh for opening {obj_id} with {len(opening_mesh.vertices)} vertices, {len(opening_mesh.faces)} faces")
                elif is_ifc_storey:
                    logger.info(f"Attempting to create storey mesh for {obj_id}...")
                    storey_mesh = self._create_storey_mesh_from_ifc(window)
                    if storey_mesh is None:
                        logger.warning(f"⚠ Storey {obj_id} has no geometry - this is expected for IfcBuildingStorey")
                        logger.warning(f"   Storeys are container elements that contain spaces and building elements")
                        logger.warning(f"   They don't have direct geometry themselves")
                        # Don't cache None - this prevents rendering errors
                        # The highlight will be cleared since there's no mesh to show
                    else:
                        self.window_meshes[obj_id] = storey_mesh
                        logger.info(f"✓ Created mesh for storey {obj_id} with {len(storey_mesh.vertices)} vertices, {len(storey_mesh.faces)} faces")
                else:
                    # Window object or generic object with center/normal/size
                    logger.info(f"STEP 4: Creating window/object mesh from properties (center, normal, size)")
                    logger.info(f"STEP 4a: Window object properties check:")
                    logger.info(f"   - Has center: {hasattr(window, 'center')} = {getattr(window, 'center', 'N/A')}")
                    logger.info(f"   - Has normal: {hasattr(window, 'normal')} = {getattr(window, 'normal', 'N/A')}")
                    logger.info(f"   - Has size: {hasattr(window, 'size')} = {getattr(window, 'size', 'N/A')}")
                    window_mesh = self._create_window_mesh(window)
                    self.window_meshes[obj_id] = window_mesh
                    if window_mesh is None:
                        logger.error(f"❌ STEP 4 FAILED: Error on highlight part - Failed to create mesh for {obj_type} {obj_id}")
                        logger.error(f"   This usually means the object is missing center, normal, or size properties")
                        logger.error(f"   Object has center: {hasattr(window, 'center')}, normal: {hasattr(window, 'normal')}, size: {hasattr(window, 'size')}")
                    else:
                        logger.info(f"✓ STEP 4 SUCCESS: Created mesh for {obj_type} {obj_id} with {len(window_mesh.vertices)} vertices, {len(window_mesh.faces)} faces")
                        logger.info(f"STEP 4b: Window mesh bounds: {window_mesh.bounds}")
                        logger.info(f"STEP 4c: Window mesh center: {window_mesh.centroid}")
                        logger.info(f"STEP 4d: Window mesh extents: {window_mesh.extents}")
                        if self.mesh is not None:
                            # Check if window is within model bounds
                            model_bounds = self.mesh.bounds
                            window_bounds = window_mesh.bounds
                            logger.info(f"STEP 4e: Coordinate system check:")
                            logger.info(f"   - Model bounds: {model_bounds}")
                            logger.info(f"   - Window bounds: {window_bounds}")
                            # Check if window overlaps with model
                            window_in_model = (
                                window_bounds[0][0] <= model_bounds[1][0] and window_bounds[1][0] >= model_bounds[0][0] and
                                window_bounds[0][1] <= model_bounds[1][1] and window_bounds[1][1] >= model_bounds[0][1] and
                                window_bounds[0][2] <= model_bounds[1][2] and window_bounds[1][2] >= model_bounds[0][2]
                            )
                            logger.info(f"   - Window overlaps model: {window_in_model}")
                            if not window_in_model:
                                logger.warning(f"⚠ STEP 4 WARNING: Window bounds do not overlap with model bounds!")
                                logger.warning(f"   This suggests a coordinate system mismatch - window may not be visible")
            else:
                logger.info(f"Using cached mesh for {obj_type} {obj_id}")
                cached_mesh = self.window_meshes.get(obj_id)
                if cached_mesh is None:
                    # Check if it was never created or if creation failed
                    if obj_id in self.window_meshes:
                        logger.error(f"❌ ISSUE #2: Error on highlight part - Cached mesh is None for {obj_id}")
                        logger.error(f"   This means mesh creation failed previously. Check logs above for details.")
                        # Clear the None entry to allow retry
                        del self.window_meshes[obj_id]
                    else:
                        logger.warning(f"⚠ No cached mesh found for {obj_type} {obj_id} - will attempt to create now")
                        # Retry mesh creation
                        if is_ifc_space:
                            cached_mesh = self._create_space_mesh_from_ifc(window)
                        elif is_ifc_door:
                            cached_mesh = self._create_door_mesh_from_ifc(window)
                        elif is_ifc_window:
                            cached_mesh = self._create_ifc_window_mesh_from_ifc(window)
                        elif is_ifc_wall:
                            cached_mesh = self._create_wall_mesh_from_ifc(window)
                        elif is_ifc_slab:
                            cached_mesh = self._create_slab_mesh_from_ifc(window)
                        elif is_ifc_opening:
                            cached_mesh = self._create_opening_mesh_from_ifc(window)
                        elif is_ifc_storey:
                            cached_mesh = self._create_storey_mesh_from_ifc(window)
                        else:
                            cached_mesh = self._create_window_mesh(window)
                        
                        if cached_mesh:
                            self.window_meshes[obj_id] = cached_mesh
                            logger.info(f"✓ Created mesh on retry: {len(cached_mesh.vertices)} vertices, {len(cached_mesh.faces)} faces")
                else:
                    logger.info(f"✓ Cached mesh available: {len(cached_mesh.vertices)} vertices, {len(cached_mesh.faces)} faces")
            
            # Store highlight type for color selection
            self.highlight_is_space = is_ifc_space
            self.highlight_is_door = is_ifc_door
            self.highlight_is_window = is_ifc_window
            self.highlight_is_wall = is_ifc_wall
            self.highlight_is_slab = is_ifc_slab
            self.highlight_is_opening = is_ifc_opening
            self.highlight_is_storey = is_ifc_storey
            # Note: Window objects (is_window_object) will use default blue color (not IFC elements)
            
            # Force update to redraw with highlight
            logger.info(f"STEP 5: Preparing to render highlight")
            try:
                self.makeCurrent()  # Ensure context is current
                logger.info(f"✓ STEP 5a: OpenGL context is current")
            except Exception as e:
                logger.warning(f"❌ STEP 5a FAILED: Could not make OpenGL context current: {e}")
            
            # Check if mesh is ready for rendering
            final_mesh = self.window_meshes.get(obj_id)
            if final_mesh is None:
                logger.error(f"❌ STEP 5b FAILED: No mesh available for rendering {obj_id}")
            elif len(final_mesh.vertices) == 0:
                logger.error(f"❌ STEP 5b FAILED: Mesh has no vertices for {obj_id}")
            else:
                logger.info(f"✓ STEP 5b: Mesh ready for rendering: {len(final_mesh.vertices)} vertices, {len(final_mesh.faces)} faces")
            
            self.update()  # Trigger repaint
            logger.info(f"✓ STEP 5c: Update called for {obj_type} highlight: {obj_id}")
            logger.info(f"=== END OF HIGHLIGHTING DIAGNOSTIC ===")
        
        def _create_window_mesh(self, window):
            """Create a trimesh representation of a window or object from its properties.
            First tries to extract actual geometry from IFC file if available, then falls back to simple rectangle.
            """
            import trimesh
            from models.building import Window
            import logging
            
            logger = logging.getLogger(__name__)
            
            window_id = getattr(window, 'id', 'unknown')
            logger.info(f"=== CREATING WINDOW MESH FROM PROPERTIES ===")
            logger.info(f"Window ID: {window_id}")
            
            # Try to extract actual geometry from IFC file first (if available)
            if hasattr(self, 'ifc_file') and self.ifc_file is not None:
                logger.info(f"IFC file available - attempting to extract actual geometry for window {window_id}")
                logger.info(f"Window object type: {type(window).__name__}")
                logger.info(f"Window object attributes: {[attr for attr in dir(window) if not attr.startswith('_')]}")
                try:
                    # Try to find IFC window element by GlobalId
                    ifc_window = None
                    try:
                        # Try by GlobalId first (most common)
                        ifc_window = self.ifc_file.by_guid(window_id)
                        if ifc_window and ifc_window.is_a("IfcWindow"):
                            logger.info(f"✓ Found IFC window element by GlobalId: {window_id}")
                            logger.info(f"  IFC window GlobalId: {ifc_window.GlobalId}")
                            logger.info(f"  IFC window type: {ifc_window.is_a()}")
                        else:
                            logger.warning(f"⚠ Found element by GlobalId but it's not an IfcWindow: {ifc_window.is_a() if ifc_window else 'None'}")
                            ifc_window = None
                    except Exception as guid_error:
                        logger.debug(f"Could not find by GlobalId: {guid_error}")
                    
                    # If not found by GlobalId, try to find by searching all windows
                    if ifc_window is None:
                        all_windows = self.ifc_file.by_type("IfcWindow")
                        logger.info(f"Searching through {len(all_windows)} IFC windows for match...")
                        for w in all_windows:
                            w_guid = getattr(w, 'GlobalId', None)
                            if w_guid == window_id:
                                ifc_window = w
                                logger.info(f"✓ Found IFC window element by searching: {window_id}")
                                logger.info(f"  Matched window GlobalId: {w_guid}")
                                break
                            else:
                                logger.debug(f"  Window {w_guid} does not match {window_id}")
                        
                        if ifc_window is None:
                            logger.warning(f"⚠ Could not find IFC window with GlobalId={window_id} in {len(all_windows)} windows")
                            logger.warning(f"   Available window GlobalIds: {[getattr(w, 'GlobalId', 'N/A') for w in all_windows[:5]]}...")
                    
                    # If found, extract actual geometry
                    if ifc_window:
                        logger.info(f"Extracting actual geometry from IFC window element...")
                        logger.info(f"  IFC Window element: {ifc_window}")
                        logger.info(f"  IFC Window GlobalId: {getattr(ifc_window, 'GlobalId', 'N/A')}")
                        logger.info(f"  IFC Window Name: {getattr(ifc_window, 'Name', 'N/A')}")
                        # Try to get IFC element properties as text for debugging
                        try:
                            logger.info(f"  IFC Window attributes: {[attr for attr in dir(ifc_window) if not attr.startswith('_') and not callable(getattr(ifc_window, attr, None))][:10]}")
                        except:
                            pass
                        actual_mesh = self._create_ifc_window_mesh_from_ifc(ifc_window)
                        if actual_mesh and len(actual_mesh.vertices) > 0:
                            logger.info(f"✓ Successfully extracted actual geometry: {len(actual_mesh.vertices)} vertices, {len(actual_mesh.faces)} faces")
                            logger.info(f"   Mesh bounds: {actual_mesh.bounds}")
                            logger.info(f"   Mesh center: {actual_mesh.centroid}")
                            # Check if mesh is in model coordinate system
                            if self.mesh is not None and len(self.mesh.vertices) > 0:
                                model_bounds = self.mesh.bounds
                                window_bounds = actual_mesh.bounds
                                # Check if window overlaps with model
                                window_in_model = (
                                    window_bounds[0][0] <= model_bounds[1][0] and window_bounds[1][0] >= model_bounds[0][0] and
                                    window_bounds[0][1] <= model_bounds[1][1] and window_bounds[1][1] >= model_bounds[0][1] and
                                    window_bounds[0][2] <= model_bounds[1][2] and window_bounds[1][2] >= model_bounds[0][2]
                                )
                                if window_in_model:
                                    logger.info(f"   ✓ Window mesh is in model coordinate system - overlaps with model bounds")
                                else:
                                    logger.warning(f"   ⚠ Window mesh does not overlap with model - coordinate system mismatch")
                                    logger.warning(f"      Model bounds: {model_bounds}")
                                    logger.warning(f"      Window bounds: {window_bounds}")
                            return actual_mesh
                        else:
                            logger.warning(f"Could not extract geometry from IFC element, falling back to simple rectangle")
                except Exception as e:
                    logger.debug(f"Error extracting from IFC file: {e}, falling back to simple rectangle")
            
            # Fallback: Create simple rectangle from properties
            logger.info(f"Creating simple rectangle from window properties (center, normal, size)")
            
            # Validate object has required properties (works for Window or any object with these attributes)
            if not hasattr(window, 'center') or window.center is None:
                logger.warning(f"Object {window_id} missing center property")
                return None
            if not hasattr(window, 'normal') or window.normal is None:
                logger.warning(f"Object {window_id} missing normal property")
                return None
            if not hasattr(window, 'size') or window.size is None or len(window.size) < 2:
                logger.warning(f"Object {window_id} missing or invalid size property")
                return None
            
            # Window properties
            center = np.array(window.center)
            normal = np.array(window.normal)
            width, height = window.size
            
            # Log window properties for debugging
            logger.info(f"Window properties (original): center=({center[0]:.2f}, {center[1]:.2f}, {center[2]:.2f}), size=({width:.2f}, {height:.2f}), normal=({normal[0]:.2f}, {normal[1]:.2f}, {normal[2]:.2f})")
            
            # CRITICAL FIX: Transform window coordinates to match model coordinate system
            # If model is loaded, check if window coordinates need transformation
            if self.mesh is not None and len(self.mesh.vertices) > 0:
                model_bounds = self.mesh.bounds
                model_center = self.mesh.centroid
                
                # Check if window is in a completely different coordinate system
                # Model is typically in local coordinates (small numbers)
                # Windows from IFC are often in world coordinates (large numbers)
                window_distance_from_model = np.linalg.norm(center - model_center)
                model_size = np.linalg.norm(model_bounds[1] - model_bounds[0])
                
                logger.info(f"STEP 4f: Coordinate transformation check:")
                logger.info(f"   - Model center: {model_center}")
                logger.info(f"   - Window center (original): {center}")
                logger.info(f"   - Distance from model: {window_distance_from_model:.2f}")
                logger.info(f"   - Model size: {model_size:.2f}")
                
                # If window is very far from model (more than 10x model size), transform it
                if window_distance_from_model > model_size * 10:
                    logger.warning(f"⚠ Window coordinates are in different coordinate system - applying transformation")
                    logger.warning(f"   Window is {window_distance_from_model:.2f} units away, model size is {model_size:.2f}")
                    
                    # Try to find the window in the IFC file and extract its actual geometry
                    # This will be in the same coordinate system as the model mesh
                    if hasattr(self, 'ifc_file') and self.ifc_file is not None:
                        logger.info(f"   Attempting to find window in IFC file by GlobalId...")
                        try:
                            # Search all windows in IFC file
                            all_ifc_windows = self.ifc_file.by_type("IfcWindow")
                            logger.info(f"   Found {len(all_ifc_windows)} IFC windows in file")
                            
                            # Try to match by GlobalId
                            matched_ifc_window = None
                            for ifc_win in all_ifc_windows:
                                if hasattr(ifc_win, 'GlobalId') and ifc_win.GlobalId == window_id:
                                    matched_ifc_window = ifc_win
                                    logger.info(f"   ✓ Found matching IFC window by GlobalId: {window_id}")
                                    break
                            
                            # If found, extract actual geometry (in model coordinate system)
                            if matched_ifc_window:
                                logger.info(f"   Extracting actual geometry from IFC window element...")
                                actual_mesh = self._create_ifc_window_mesh_from_ifc(matched_ifc_window)
                                if actual_mesh and len(actual_mesh.vertices) > 0:
                                    logger.info(f"   ✓ Successfully extracted geometry in model coordinate system")
                                    logger.info(f"      Mesh bounds: {actual_mesh.bounds}")
                                    logger.info(f"      Mesh center: {actual_mesh.centroid}")
                                    return actual_mesh
                                else:
                                    logger.warning(f"   Could not extract geometry from IFC element")
                        except Exception as e:
                            logger.debug(f"   Error searching IFC file: {e}")
                    
                    # Fallback: Transform window to model coordinate system
                    # Calculate transformation to preserve relative positions
                    logger.warning(f"   Applying coordinate transformation to preserve relative window positions")
                    
                    # Calculate transformation offset
                    # Strategy: Extract actual geometry from IFC first (best solution)
                    # If that fails, calculate transformation to map window coordinates to model coordinates
                    # Cache the transformation so all windows use the same offset (preserves relative positions)
                    
                    # First, try to extract actual geometry from IFC (this should be in correct coordinate system)
                    if hasattr(self, 'ifc_file') and self.ifc_file is not None:
                        logger.info(f"   Attempting to extract actual geometry from IFC file...")
                        try:
                            # Try to find window in IFC by GlobalId
                            ifc_window = None
                            try:
                                ifc_window = self.ifc_file.by_guid(window_id)
                                if ifc_window and ifc_window.is_a("IfcWindow"):
                                    logger.info(f"   ✓ Found IFC window element by GlobalId: {window_id}")
                                else:
                                    ifc_window = None
                            except:
                                pass
                            
                            if ifc_window is None:
                                # Search all windows
                                all_ifc_windows = self.ifc_file.by_type("IfcWindow")
                                for w in all_ifc_windows:
                                    if hasattr(w, 'GlobalId') and w.GlobalId == window_id:
                                        ifc_window = w
                                        logger.info(f"   ✓ Found IFC window element by searching: {window_id}")
                                        break
                            
                            if ifc_window:
                                # Extract geometry using _create_ifc_window_mesh_from_ifc
                                # This will use the correct coordinate system
                                logger.info(f"   Extracting geometry from IFC window element (will use correct coordinate system)...")
                                # Note: This will be called from _create_window_mesh, so we'll return early
                                # Actually, we can't return here because we're in the middle of _create_window_mesh
                                # So we'll let it continue and the IFC extraction will happen in the earlier check
                                pass
                        except Exception as e:
                            logger.debug(f"   Error searching IFC file for geometry extraction: {e}")
                    
                    # Calculate transformation offset if not cached
                    # This is a fallback when IFC geometry extraction fails
                    if self.window_coordinate_transform is None:
                        # Calculate transformation offset using building's window positions
                        if hasattr(self, 'building') and self.building and len(self.building.windows) > 0:
                            # Calculate centroid of all windows in world coordinates
                            window_centers = [np.array(w.center) for w in self.building.windows]
                            if window_centers:
                                windows_centroid = np.mean(window_centers, axis=0)
                                # Calculate offset: how to transform from window coordinate system to model coordinate system
                                # The offset should map windows_centroid to model_center
                                # Formula: model_center = windows_centroid + offset
                                # Therefore: offset = model_center - windows_centroid
                                self.window_coordinate_transform = model_center - windows_centroid
                                logger.info(f"   Calculated transformation offset from {len(self.building.windows)} windows")
                                logger.info(f"   Windows centroid (world): {windows_centroid}")
                                logger.info(f"   Model center (local): {model_center}")
                                logger.info(f"   Transformation offset (cached): {self.window_coordinate_transform}")
                    
                    # Apply cached transformation to this window
                    if self.window_coordinate_transform is not None:
                        center = center + self.window_coordinate_transform
                        logger.info(f"   Applied cached transformation - transformed window center: {center}")
                        # Validate transformed position
                        if self.mesh is not None:
                            model_bounds = self.mesh.bounds
                            # Check if transformed center is within reasonable range of model
                            center_distance = np.linalg.norm(center - model_center)
                            model_size = np.linalg.norm(model_bounds[1] - model_bounds[0])
                            if center_distance > model_size * 2:
                                logger.warning(f"   ⚠ Transformed window is still far from model ({center_distance:.2f} units, model size: {model_size:.2f})")
                                logger.warning(f"   ⚠ Transformation failed - window will not be visible")
                                logger.warning(f"   ⚠ SOLUTION: Extract actual geometry from IFC file (should be in correct coordinate system)")
                                # Try to extract from IFC as last resort
                                if hasattr(self, 'ifc_file') and self.ifc_file is not None:
                                    logger.info(f"   Attempting IFC geometry extraction as fallback...")
                                    try:
                                        ifc_window = self.ifc_file.by_guid(window_id)
                                        if ifc_window and ifc_window.is_a("IfcWindow"):
                                            logger.info(f"   Found IFC window - extracting geometry...")
                                            ifc_mesh = self._create_ifc_window_mesh_from_ifc(ifc_window)
                                            if ifc_mesh and len(ifc_mesh.vertices) > 0:
                                                logger.info(f"   ✓ Successfully extracted IFC geometry - using it instead of transformation")
                                                return ifc_mesh
                                    except:
                                        pass
                                # If IFC extraction also fails, place window at model center as last resort
                                logger.warning(f"   ⚠ Placing window at model center as last resort (may not be accurate)")
                                center = model_center.copy()
                    else:
                        # Fallback: Use simple offset calculation when building is not available
                        # This is a last resort - ideally we should have the building object
                        # For now, we'll calculate a relative position within model bounds
                        # This preserves some relative positioning but is not perfect
                        model_min = model_bounds[0]
                        model_max = model_bounds[1]
                        model_range = model_max - model_min
                        
                        # Calculate a relative position within model bounds
                        # Use window's position relative to a reference point (e.g., first window or model origin)
                        # Scale the window position to fit within model bounds
                        # This is approximate - best solution is to extract from IFC or use building reference
                        logger.warning(f"   ⚠ No building reference available - using model center as fallback")
                        logger.warning(f"   ⚠ All windows will appear at model center - this is a limitation")
                        logger.warning(f"   ⚠ To fix: Ensure building object is set or extract geometry from IFC")
                        # Place at model center as last resort
                        center = model_center.copy()
                        logger.info(f"   Transformed window center to model center: {center}")
                else:
                    logger.info(f"   ✓ Window coordinates are in same coordinate system as model")
            
            # Validate size values
            if width <= 0 or height <= 0:
                logger.warning(f"Window {window_id} has invalid size: {width}x{height}")
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
            
            # Add small thickness to make window visible from all angles
            # Use 5% of the smaller dimension as thickness, but at least 0.05m
            thickness = max(0.05, min(width, height) * 0.05)
            half_thickness = thickness / 2.0
            
            # Create a thin box (extruded rectangle) instead of flat rectangle
            # Front face (in direction of normal)
            front_corners = [
                center + (half_thickness * normal) + (-half_width * right) + (-half_height * up),
                center + (half_thickness * normal) + (half_width * right) + (-half_height * up),
                center + (half_thickness * normal) + (half_width * right) + (half_height * up),
                center + (half_thickness * normal) + (-half_width * right) + (half_height * up)
            ]
            
            # Back face (opposite direction of normal)
            back_corners = [
                center + (-half_thickness * normal) + (-half_width * right) + (-half_height * up),
                center + (-half_thickness * normal) + (half_width * right) + (-half_height * up),
                center + (-half_thickness * normal) + (half_width * right) + (half_height * up),
                center + (-half_thickness * normal) + (-half_width * right) + (half_height * up)
            ]
            
            # Combine all vertices: front face (0-3), back face (4-7)
            vertices = np.array(front_corners + back_corners)
            
            # Create faces for the box:
            # Front face (2 triangles)
            # Back face (2 triangles)
            # 4 side faces (each with 2 triangles)
            faces = np.array([
                # Front face
                [0, 1, 2], [0, 2, 3],
                # Back face (reversed winding)
                [4, 6, 5], [4, 7, 6],
                # Side faces
                [0, 4, 5], [0, 5, 1],  # Bottom
                [1, 5, 6], [1, 6, 2],  # Right
                [2, 6, 7], [2, 7, 3],  # Top
                [3, 7, 4], [3, 4, 0]   # Left
            ])
            
            # Create trimesh
            window_mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
            logger.info(f"✓ Created window mesh: {len(window_mesh.vertices)} vertices, {len(window_mesh.faces)} faces")
            logger.info(f"   Mesh bounds: {window_mesh.bounds}")
            logger.info(f"   Mesh center: {window_mesh.centroid}")
            logger.info(f"   Mesh size: {window_mesh.extents}")
            logger.info(f"   Thickness: {thickness:.3f}m (added for visibility)")
            return window_mesh
        
        def _create_space_mesh_from_ifc(self, space_element):
            """Create a trimesh representation of an IFC space (room) from its geometry."""
            import trimesh
            import logging
            logger = logging.getLogger(__name__)
            
            try:
                # Try to extract geometry from IFC space element using ifcopenshell
                import ifcopenshell
                import ifcopenshell.geom as geom
                
                # Create geometry settings
                settings = geom.settings()
                try:
                    if hasattr(settings, 'USE_WORLD_COORDS'):
                        settings.set(settings.USE_WORLD_COORDS, True)
                except:
                    pass
                
                # Create shape from space element
                shape = geom.create_shape(settings, space_element)
                if not shape:
                    logger.warning(f"Could not create shape for space {getattr(space_element, 'GlobalId', space_element.id())}")
                    return None
                
                # Get geometry from shape
                geometry = shape.geometry
                if not geometry:
                    logger.warning(f"Space {getattr(space_element, 'GlobalId', space_element.id())} has no geometry")
                    return None
                
                # Extract vertices and faces
                vertices = None
                faces = None
                
                # Method 1: Direct access to geometry.verts and geometry.faces
                if hasattr(geometry, 'verts') and hasattr(geometry, 'faces'):
                    try:
                        verts = geometry.verts
                        faces_data = geometry.faces
                        
                        # Convert to numpy arrays
                        vertices = np.array(verts, dtype=np.float64)
                        # Ensure vertices are in shape (n, 3)
                        if len(vertices.shape) == 1:
                            if len(vertices) % 3 == 0:
                                vertices = vertices.reshape(-1, 3)
                            else:
                                logger.warning(f"Invalid vertex count: {len(vertices)} (not divisible by 3)")
                                return None
                        elif len(vertices.shape) == 2 and vertices.shape[1] != 3:
                            logger.warning(f"Invalid vertex shape: {vertices.shape}")
                            return None
                        
                        faces = np.array(faces_data, dtype=np.int32)
                        # Ensure faces are in shape (n, 3)
                        if len(faces.shape) == 1:
                            if len(faces) % 3 == 0:
                                faces = faces.reshape(-1, 3)
                            else:
                                logger.warning(f"Invalid face count: {len(faces)} (not divisible by 3)")
                                return None
                        elif len(faces.shape) == 2 and faces.shape[1] != 3:
                            logger.warning(f"Invalid face shape: {faces.shape}")
                            return None
                    except Exception as e:
                        logger.warning(f"Failed to extract geometry using standard API: {e}")
                        return None
                
                # Create mesh if we have valid data
                if vertices is not None and faces is not None and len(vertices) > 0 and len(faces) > 0:
                    try:
                        # Validate face indices
                        if len(faces) > 0:
                            max_vertex_idx = np.max(faces)
                            if max_vertex_idx >= len(vertices):
                                logger.warning(f"Face indices out of range: max index {max_vertex_idx}, but only {len(vertices)} vertices")
                                return None
                        
                        space_mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
                        logger.info(f"Created space mesh with {len(vertices)} vertices, {len(faces)} faces")
                        return space_mesh
                    except Exception as mesh_error:
                        logger.warning(f"Failed to create trimesh from space geometry: {mesh_error}")
                        return None
                else:
                    logger.warning(f"Could not extract valid geometry for space {getattr(space_element, 'GlobalId', space_element.id())}")
                    return None
                    
            except ImportError:
                logger.warning("ifcopenshell.geom not available - cannot extract space geometry")
                return None
            except Exception as e:
                logger.warning(f"Error creating space mesh from IFC: {e}", exc_info=True)
                return None
        
        def _create_door_mesh_from_ifc(self, door_element):
            """Create a trimesh representation of an IFC door from its geometry."""
            import trimesh
            import logging
            logger = logging.getLogger(__name__)
            
            door_id = getattr(door_element, 'GlobalId', None) or getattr(door_element, 'id', None)
            logger.info(f"=== CREATING DOOR MESH ===")
            logger.info(f"Door ID: {door_id}")
            logger.info(f"Door type: {type(door_element).__name__}")
            
            try:
                # Try to extract geometry from IFC door element using ifcopenshell
                import ifcopenshell
                import ifcopenshell.geom as geom
                logger.info("✓ ifcopenshell.geom imported successfully")
                
                # Create geometry settings
                settings = geom.settings()
                try:
                    if hasattr(settings, 'USE_WORLD_COORDS'):
                        settings.set(settings.USE_WORLD_COORDS, True)
                        logger.info("✓ Enabled USE_WORLD_COORDS")
                except Exception as e:
                    logger.debug(f"Could not set USE_WORLD_COORDS: {e}")
                
                # Create shape from door element
                logger.info(f"Attempting to create shape from door element...")
                try:
                    shape = geom.create_shape(settings, door_element)
                    if not shape:
                        logger.error(f"❌ ISSUE #2: Could not create shape for door {door_id}")
                        logger.error(f"   geom.create_shape() returned None or False")
                        return None
                    logger.info("✓ Shape created successfully")
                except Exception as e:
                    logger.error(f"❌ ISSUE #2: Exception creating shape for door {door_id}: {e}", exc_info=True)
                    return None
                
                # Get geometry from shape
                geometry = shape.geometry
                if not geometry:
                    logger.error(f"❌ ISSUE #2: Door {door_id} has no geometry")
                    logger.error(f"   shape.geometry is None or empty")
                    return None
                logger.info("✓ Geometry extracted from shape")
                
                # Extract vertices and faces
                vertices = None
                faces = None
                
                # Method 1: Direct access to geometry.verts and geometry.faces
                logger.info(f"Checking geometry attributes: has verts={hasattr(geometry, 'verts')}, has faces={hasattr(geometry, 'faces')}")
                if hasattr(geometry, 'verts') and hasattr(geometry, 'faces'):
                    try:
                        verts = geometry.verts
                        faces_data = geometry.faces
                        logger.info(f"✓ Extracted verts and faces: {len(verts) if verts is not None else 'None'} vertices, {len(faces_data) if faces_data is not None else 'None'} faces")
                        
                        # Convert to numpy arrays
                        vertices = np.array(verts, dtype=np.float64)
                        # Ensure vertices are in shape (n, 3)
                        if len(vertices.shape) == 1:
                            if len(vertices) % 3 == 0:
                                vertices = vertices.reshape(-1, 3)
                            else:
                                logger.error(f"❌ ISSUE #2: Invalid vertex count: {len(vertices)} (not divisible by 3)")
                                return None
                        elif len(vertices.shape) == 2 and vertices.shape[1] != 3:
                            logger.error(f"❌ ISSUE #2: Invalid vertex shape: {vertices.shape}")
                            return None
                        
                        faces = np.array(faces_data, dtype=np.int32)
                        # Ensure faces are in shape (n, 3)
                        if len(faces.shape) == 1:
                            if len(faces) % 3 == 0:
                                faces = faces.reshape(-1, 3)
                            else:
                                logger.error(f"❌ ISSUE #2: Invalid face count: {len(faces)} (not divisible by 3)")
                                return None
                        elif len(faces.shape) == 2 and faces.shape[1] != 3:
                            logger.error(f"❌ ISSUE #2: Invalid face shape: {faces.shape}")
                            return None
                        logger.info(f"✓ Successfully converted to numpy arrays: {len(vertices)} vertices, {len(faces)} faces")
                    except Exception as e:
                        logger.error(f"❌ ISSUE #2: Failed to extract geometry using standard API: {e}", exc_info=True)
                        return None
                else:
                    logger.error(f"❌ ISSUE #2: Geometry object missing 'verts' or 'faces' attributes")
                    logger.error(f"   Geometry attributes: {dir(geometry)}")
                    return None
                
                # Create mesh if we have valid data
                if vertices is not None and faces is not None and len(vertices) > 0 and len(faces) > 0:
                    try:
                        # Validate face indices
                        if len(faces) > 0:
                            max_vertex_idx = np.max(faces)
                            if max_vertex_idx >= len(vertices):
                                logger.error(f"❌ ISSUE #2: Face indices out of range: max index {max_vertex_idx}, but only {len(vertices)} vertices")
                                return None
                        
                        door_mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
                        logger.info(f"✓ Created door mesh successfully: {len(vertices)} vertices, {len(faces)} faces")
                        logger.info(f"   Mesh bounds: {door_mesh.bounds}")
                        logger.info(f"   Mesh center: {door_mesh.centroid}")
                        return door_mesh
                    except Exception as mesh_error:
                        logger.error(f"❌ ISSUE #2: Failed to create trimesh from door geometry: {mesh_error}", exc_info=True)
                        return None
                else:
                    logger.error(f"❌ ISSUE #2: Could not extract valid geometry for door {door_id}")
                    logger.error(f"   vertices: {vertices is not None} (len={len(vertices) if vertices is not None else 0})")
                    logger.error(f"   faces: {faces is not None} (len={len(faces) if faces is not None else 0})")
                    return None
                    
            except ImportError:
                logger.warning("ifcopenshell.geom not available - cannot extract door geometry")
                return None
            except Exception as e:
                logger.warning(f"Error creating door mesh from IFC: {e}", exc_info=True)
                return None
        
        def _extract_ifc_element_data_as_text(self, element) -> str:
            """Extract IFC element data as text for debugging.
            
            Args:
                element: IFC element (IfcWindow, IfcDoor, etc.)
                
            Returns:
                String representation of element data
            """
            import logging
            logger = logging.getLogger(__name__)
            
            try:
                lines = []
                lines.append(f"=== IFC ELEMENT DATA ===")
                lines.append(f"Type: {element.is_a() if hasattr(element, 'is_a') else type(element).__name__}")
                lines.append(f"GlobalId: {getattr(element, 'GlobalId', 'N/A')}")
                lines.append(f"Name: {getattr(element, 'Name', 'N/A')}")
                
                # Extract placement/position
                if hasattr(element, 'ObjectPlacement'):
                    placement = element.ObjectPlacement
                    lines.append(f"ObjectPlacement: {placement}")
                    if hasattr(placement, 'RelativePlacement'):
                        rel_placement = placement.RelativePlacement
                        if hasattr(rel_placement, 'Location'):
                            location = rel_placement.Location
                            if hasattr(location, 'Coordinates'):
                                coords = location.Coordinates
                                lines.append(f"  Location Coordinates: {coords}")
                
                # Extract properties
                if hasattr(element, 'HasProperties'):
                    props = []
                    for prop in element.HasProperties:
                        if hasattr(prop, 'Name') and hasattr(prop, 'NominalValue'):
                            prop_name = prop.Name
                            prop_val = getattr(prop.NominalValue, 'wrappedValue', prop.NominalValue) if hasattr(prop.NominalValue, 'wrappedValue') else prop.NominalValue
                            props.append(f"{prop_name}={prop_val}")
                    if props:
                        lines.append(f"Properties: {', '.join(props[:5])}")  # First 5 properties
                
                # Extract material
                if hasattr(element, 'HasAssociations'):
                    for assoc in element.HasAssociations:
                        if hasattr(assoc, 'is_a') and assoc.is_a("IfcRelAssociatesMaterial"):
                            material = assoc.RelatingMaterial
                            lines.append(f"Material: {getattr(material, 'Name', material)}")
                            break
                
                return "\n".join(lines)
            except Exception as e:
                logger.debug(f"Error extracting IFC element data: {e}")
                return f"Error extracting data: {e}"
        
        def _create_ifc_window_mesh_from_ifc(self, window_element):
            """Create a trimesh representation of an IFC window from its geometry.
            Uses the SAME coordinate system settings as the model mesh generation.
            """
            import trimesh
            import logging
            logger = logging.getLogger(__name__)
            
            window_id = getattr(window_element, 'GlobalId', None) or getattr(window_element, 'id', None)
            logger.info(f"=== CREATING IFC WINDOW MESH ===")
            logger.info(f"Window ID: {window_id}")
            logger.info(f"Window type: {type(window_element).__name__}")
            
            # Extract IFC element data as text for debugging
            element_data = self._extract_ifc_element_data_as_text(window_element)
            logger.info(f"IFC Element Data:\n{element_data}")
            
            try:
                import ifcopenshell
                import ifcopenshell.geom as geom
                logger.info("✓ ifcopenshell.geom imported successfully")
                
                settings = geom.settings()
                # CRITICAL: Use the EXACT SAME settings as model mesh generation
                # The model mesh is generated with USE_WORLD_COORDS=True (see ifc_importer.py line 1411)
                # Even though the resulting mesh has small coordinates, we must use the same setting
                # to ensure window geometry is in the same coordinate system
                use_world_coords = True  # Match model mesh generation setting
                
                if self.mesh is not None and len(self.mesh.vertices) > 0:
                    model_bounds = self.mesh.bounds
                    model_center = self.mesh.centroid
                    model_size = np.linalg.norm(model_bounds[1] - model_bounds[0])
                    logger.info(f"Model bounds: {model_bounds}")
                    logger.info(f"Model center: {model_center}")
                    logger.info(f"Model size: {model_size:.2f}")
                    logger.info(f"Using USE_WORLD_COORDS=True to match model mesh generation (from ifc_importer.py)")
                
                try:
                    if hasattr(settings, 'USE_WORLD_COORDS'):
                        settings.set(settings.USE_WORLD_COORDS, use_world_coords)
                        logger.info(f"✓ Set USE_WORLD_COORDS={use_world_coords} to match model mesh generation")
                    else:
                        logger.warning("⚠ USE_WORLD_COORDS setting not available in this ifcopenshell version")
                except Exception as e:
                    logger.debug(f"Could not set USE_WORLD_COORDS: {e}")
                
                # Also match other settings from model mesh generation
                try:
                    if hasattr(settings, 'USE_BREP_DATA'):
                        settings.set(settings.USE_BREP_DATA, False)  # Match model mesh generation
                except:
                    pass
                try:
                    if hasattr(settings, 'SEW_SHELLS'):
                        settings.set(settings.SEW_SHELLS, True)  # Match model mesh generation
                except:
                    pass
                
                logger.info(f"Attempting to create shape from IFC window element...")
                try:
                    shape = geom.create_shape(settings, window_element)
                    if not shape:
                        logger.error(f"❌ ISSUE #2: Could not create shape for IFC window {window_id}")
                        return None
                    logger.info("✓ Shape created successfully")
                except Exception as e:
                    logger.error(f"❌ ISSUE #2: Exception creating shape for IFC window {window_id}: {e}", exc_info=True)
                    return None
                
                geometry = shape.geometry
                if not geometry:
                    logger.error(f"❌ ISSUE #2: IFC window {window_id} has no geometry")
                    return None
                logger.info("✓ Geometry extracted from shape")
                
                vertices = None
                faces = None
                
                if hasattr(geometry, 'verts') and hasattr(geometry, 'faces'):
                    try:
                        verts = geometry.verts
                        faces_data = geometry.faces
                        logger.info(f"✓ Extracted verts and faces: {len(verts) if verts is not None else 'None'} vertices, {len(faces_data) if faces_data is not None else 'None'} faces")
                        
                        vertices = np.array(verts, dtype=np.float64)
                        if len(vertices.shape) == 1:
                            if len(vertices) % 3 == 0:
                                vertices = vertices.reshape(-1, 3)
                            else:
                                logger.error(f"❌ ISSUE #2: Invalid vertex count: {len(vertices)} (not divisible by 3)")
                                return None
                        elif len(vertices.shape) == 2 and vertices.shape[1] != 3:
                            logger.error(f"❌ ISSUE #2: Invalid vertex shape: {vertices.shape}")
                            return None
                        
                        faces = np.array(faces_data, dtype=np.int32)
                        if len(faces.shape) == 1:
                            if len(faces) % 3 == 0:
                                faces = faces.reshape(-1, 3)
                            else:
                                logger.error(f"❌ ISSUE #2: Invalid face count: {len(faces)} (not divisible by 3)")
                                return None
                        elif len(faces.shape) == 2 and faces.shape[1] != 3:
                            logger.error(f"❌ ISSUE #2: Invalid face shape: {faces.shape}")
                            return None
                        logger.info(f"✓ Successfully converted to numpy arrays: {len(vertices)} vertices, {len(faces)} faces")
                    except Exception as e:
                        logger.error(f"❌ ISSUE #2: Failed to extract geometry: {e}", exc_info=True)
                        return None
                else:
                    logger.error(f"❌ ISSUE #2: Geometry object missing 'verts' or 'faces' attributes")
                    return None
                
                if vertices is not None and faces is not None and len(vertices) > 0 and len(faces) > 0:
                    try:
                        if len(faces) > 0:
                            max_vertex_idx = np.max(faces)
                            if max_vertex_idx >= len(vertices):
                                logger.error(f"❌ ISSUE #2: Face indices out of range: max index {max_vertex_idx}, but only {len(vertices)} vertices")
                                return None
                        
                        window_mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
                        logger.info(f"✓ Created IFC window mesh successfully: {len(vertices)} vertices, {len(faces)} faces")
                        return window_mesh
                    except Exception as mesh_error:
                        logger.error(f"❌ ISSUE #2: Failed to create trimesh: {mesh_error}", exc_info=True)
                        return None
                else:
                    logger.error(f"❌ ISSUE #2: Could not extract valid geometry for IFC window {window_id}")
                    return None
                    
            except ImportError:
                logger.warning("ifcopenshell.geom not available - cannot extract IFC window geometry")
                return None
            except Exception as e:
                logger.warning(f"Error creating IFC window mesh from IFC: {e}", exc_info=True)
                return None
        
        def _create_wall_mesh_from_ifc(self, wall_element):
            """Create a trimesh representation of an IFC wall from its geometry."""
            import trimesh
            import logging
            logger = logging.getLogger(__name__)
            
            wall_id = getattr(wall_element, 'GlobalId', None) or getattr(wall_element, 'id', None)
            logger.info(f"=== CREATING WALL MESH ===")
            logger.info(f"Wall ID: {wall_id}")
            
            try:
                import ifcopenshell
                import ifcopenshell.geom as geom
                
                settings = geom.settings()
                try:
                    if hasattr(settings, 'USE_WORLD_COORDS'):
                        settings.set(settings.USE_WORLD_COORDS, True)
                except:
                    pass
                
                shape = geom.create_shape(settings, wall_element)
                if not shape:
                    logger.error(f"❌ ISSUE #2: Could not create shape for wall {wall_id}")
                    return None
                
                geometry = shape.geometry
                if not geometry:
                    logger.error(f"❌ ISSUE #2: Wall {wall_id} has no geometry")
                    return None
                
                if hasattr(geometry, 'verts') and hasattr(geometry, 'faces'):
                    try:
                        verts = geometry.verts
                        faces_data = geometry.faces
                        
                        vertices = np.array(verts, dtype=np.float64)
                        if len(vertices.shape) == 1:
                            if len(vertices) % 3 == 0:
                                vertices = vertices.reshape(-1, 3)
                            else:
                                return None
                        
                        faces = np.array(faces_data, dtype=np.int32)
                        if len(faces.shape) == 1:
                            if len(faces) % 3 == 0:
                                faces = faces.reshape(-1, 3)
                            else:
                                return None
                        
                        if len(faces) > 0:
                            max_vertex_idx = np.max(faces)
                            if max_vertex_idx >= len(vertices):
                                return None
                        
                        wall_mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
                        logger.info(f"✓ Created wall mesh: {len(vertices)} vertices, {len(faces)} faces")
                        return wall_mesh
                    except Exception as e:
                        logger.error(f"❌ ISSUE #2: Failed to extract geometry: {e}", exc_info=True)
                        return None
                else:
                    logger.error(f"❌ ISSUE #2: Geometry object missing 'verts' or 'faces' attributes")
                    return None
                    
            except ImportError:
                logger.warning("ifcopenshell.geom not available - cannot extract wall geometry")
                return None
            except Exception as e:
                logger.warning(f"Error creating wall mesh from IFC: {e}", exc_info=True)
                return None
        
        def _create_slab_mesh_from_ifc(self, slab_element):
            """Create a trimesh representation of an IFC slab from its geometry."""
            import trimesh
            import logging
            logger = logging.getLogger(__name__)
            
            slab_id = getattr(slab_element, 'GlobalId', None) or getattr(slab_element, 'id', None)
            logger.info(f"=== CREATING SLAB MESH ===")
            logger.info(f"Slab ID: {slab_id}")
            
            try:
                import ifcopenshell
                import ifcopenshell.geom as geom
                
                settings = geom.settings()
                try:
                    if hasattr(settings, 'USE_WORLD_COORDS'):
                        settings.set(settings.USE_WORLD_COORDS, True)
                except:
                    pass
                
                shape = geom.create_shape(settings, slab_element)
                if not shape:
                    logger.error(f"❌ ISSUE #2: Could not create shape for slab {slab_id}")
                    return None
                
                geometry = shape.geometry
                if not geometry:
                    logger.error(f"❌ ISSUE #2: Slab {slab_id} has no geometry")
                    return None
                
                if hasattr(geometry, 'verts') and hasattr(geometry, 'faces'):
                    try:
                        verts = geometry.verts
                        faces_data = geometry.faces
                        
                        vertices = np.array(verts, dtype=np.float64)
                        if len(vertices.shape) == 1:
                            if len(vertices) % 3 == 0:
                                vertices = vertices.reshape(-1, 3)
                            else:
                                return None
                        
                        faces = np.array(faces_data, dtype=np.int32)
                        if len(faces.shape) == 1:
                            if len(faces) % 3 == 0:
                                faces = faces.reshape(-1, 3)
                            else:
                                return None
                        
                        if len(faces) > 0:
                            max_vertex_idx = np.max(faces)
                            if max_vertex_idx >= len(vertices):
                                return None
                        
                        slab_mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
                        logger.info(f"✓ Created slab mesh: {len(vertices)} vertices, {len(faces)} faces")
                        return slab_mesh
                    except Exception as e:
                        logger.error(f"❌ ISSUE #2: Failed to extract geometry: {e}", exc_info=True)
                        return None
                else:
                    logger.error(f"❌ ISSUE #2: Geometry object missing 'verts' or 'faces' attributes")
                    return None
                    
            except ImportError:
                logger.warning("ifcopenshell.geom not available - cannot extract slab geometry")
                return None
            except Exception as e:
                logger.warning(f"Error creating slab mesh from IFC: {e}", exc_info=True)
                return None
        
        def _create_opening_mesh_from_ifc(self, opening_element):
            """Create a trimesh representation of an IFC opening element from its geometry."""
            import trimesh
            import logging
            logger = logging.getLogger(__name__)
            
            opening_id = getattr(opening_element, 'GlobalId', None) or getattr(opening_element, 'id', None)
            logger.info(f"=== CREATING OPENING MESH ===")
            logger.info(f"Opening ID: {opening_id}")
            logger.info(f"Opening type: {type(opening_element).__name__}")
            
            try:
                import ifcopenshell
                import ifcopenshell.geom as geom
                logger.info("✓ ifcopenshell.geom imported successfully")
                
                settings = geom.settings()
                try:
                    if hasattr(settings, 'USE_WORLD_COORDS'):
                        settings.set(settings.USE_WORLD_COORDS, True)
                        logger.info("✓ Enabled USE_WORLD_COORDS")
                except Exception as e:
                    logger.debug(f"Could not set USE_WORLD_COORDS: {e}")
                
                logger.info(f"Attempting to create shape from opening element...")
                try:
                    shape = geom.create_shape(settings, opening_element)
                    if not shape:
                        logger.error(f"❌ ISSUE #2: Could not create shape for opening {opening_id}")
                        logger.error(f"   geom.create_shape() returned None or False")
                        return None
                    logger.info("✓ Shape created successfully")
                except RuntimeError as e:
                    error_msg = str(e)
                    if "Representation is NULL" in error_msg or "NULL" in error_msg:
                        logger.warning(f"⚠ Opening {opening_id} has no geometry representation (NULL)")
                        logger.warning(f"   This is common for openings - they may be defined by relationships rather than geometry")
                        return None
                    else:
                        logger.error(f"❌ ISSUE #2: Exception creating shape for opening {opening_id}: {e}", exc_info=True)
                        return None
                except Exception as e:
                    logger.error(f"❌ ISSUE #2: Exception creating shape for opening {opening_id}: {e}", exc_info=True)
                    return None
                
                geometry = shape.geometry
                if not geometry:
                    logger.error(f"❌ ISSUE #2: Opening {opening_id} has no geometry")
                    logger.error(f"   shape.geometry is None or empty")
                    return None
                logger.info("✓ Geometry extracted from shape")
                
                vertices = None
                faces = None
                
                if hasattr(geometry, 'verts') and hasattr(geometry, 'faces'):
                    try:
                        verts = geometry.verts
                        faces_data = geometry.faces
                        logger.info(f"✓ Extracted verts and faces: {len(verts) if verts is not None else 'None'} vertices, {len(faces_data) if faces_data is not None else 'None'} faces")
                        
                        vertices = np.array(verts, dtype=np.float64)
                        if len(vertices.shape) == 1:
                            if len(vertices) % 3 == 0:
                                vertices = vertices.reshape(-1, 3)
                            else:
                                logger.error(f"❌ ISSUE #2: Invalid vertex count: {len(vertices)} (not divisible by 3)")
                                return None
                        elif len(vertices.shape) == 2 and vertices.shape[1] != 3:
                            logger.error(f"❌ ISSUE #2: Invalid vertex shape: {vertices.shape}")
                            return None
                        
                        faces = np.array(faces_data, dtype=np.int32)
                        if len(faces.shape) == 1:
                            if len(faces) % 3 == 0:
                                faces = faces.reshape(-1, 3)
                            else:
                                logger.error(f"❌ ISSUE #2: Invalid face count: {len(faces)} (not divisible by 3)")
                                return None
                        elif len(faces.shape) == 2 and faces.shape[1] != 3:
                            logger.error(f"❌ ISSUE #2: Invalid face shape: {faces.shape}")
                            return None
                        logger.info(f"✓ Successfully converted to numpy arrays: {len(vertices)} vertices, {len(faces)} faces")
                    except Exception as e:
                        logger.error(f"❌ ISSUE #2: Failed to extract geometry: {e}", exc_info=True)
                        return None
                else:
                    logger.error(f"❌ ISSUE #2: Geometry object missing 'verts' or 'faces' attributes")
                    return None
                
                if vertices is not None and faces is not None and len(vertices) > 0 and len(faces) > 0:
                    try:
                        if len(faces) > 0:
                            max_vertex_idx = np.max(faces)
                            if max_vertex_idx >= len(vertices):
                                logger.error(f"❌ ISSUE #2: Face indices out of range: max index {max_vertex_idx}, but only {len(vertices)} vertices")
                                return None
                        
                        opening_mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
                        logger.info(f"✓ Created opening mesh successfully: {len(vertices)} vertices, {len(faces)} faces")
                        logger.info(f"   Mesh bounds: {opening_mesh.bounds}")
                        logger.info(f"   Mesh center: {opening_mesh.centroid}")
                        return opening_mesh
                    except Exception as mesh_error:
                        logger.error(f"❌ ISSUE #2: Failed to create trimesh: {mesh_error}", exc_info=True)
                        return None
                else:
                    logger.error(f"❌ ISSUE #2: Could not extract valid geometry for opening {opening_id}")
                    return None
                    
            except ImportError:
                logger.warning("ifcopenshell.geom not available - cannot extract opening geometry")
                return None
            except Exception as e:
                logger.warning(f"Error creating opening mesh from IFC: {e}", exc_info=True)
                return None
        
        def _create_storey_mesh_from_ifc(self, storey_element):
            """Create a trimesh representation of an IFC building storey from its geometry."""
            import trimesh
            import logging
            logger = logging.getLogger(__name__)
            
            storey_id = getattr(storey_element, 'GlobalId', None) or getattr(storey_element, 'id', None)
            logger.info(f"=== CREATING STOREY MESH ===")
            logger.info(f"Storey ID: {storey_id}")
            logger.warning(f"⚠ Note: IfcBuildingStorey typically has no direct geometry - it contains spaces and elements")
            logger.warning(f"   Attempting to extract geometry anyway...")
            
            try:
                import ifcopenshell
                import ifcopenshell.geom as geom
                
                settings = geom.settings()
                try:
                    if hasattr(settings, 'USE_WORLD_COORDS'):
                        settings.set(settings.USE_WORLD_COORDS, True)
                except:
                    pass
                
                try:
                    shape = geom.create_shape(settings, storey_element)
                    if not shape:
                        logger.warning(f"⚠ Could not create shape for storey {storey_id} - storeys typically have no direct geometry")
                        return None
                except RuntimeError as e:
                    error_msg = str(e)
                    if "Representation is NULL" in error_msg or "NULL" in error_msg:
                        logger.warning(f"⚠ Storey {storey_id} has no geometry representation (NULL)")
                        logger.warning(f"   This is expected - IfcBuildingStorey is a container element with no direct geometry")
                        logger.warning(f"   Storeys contain spaces and building elements, but don't have geometry themselves")
                        return None
                    else:
                        logger.warning(f"⚠ Error creating shape for storey {storey_id}: {e}")
                        return None
                except Exception as e:
                    logger.warning(f"⚠ Error creating shape for storey {storey_id}: {e}")
                    return None
                
                geometry = shape.geometry
                if not geometry:
                    logger.warning(f"⚠ Storey {storey_id} has no geometry - storeys typically contain elements, not geometry themselves")
                    return None
                
                if hasattr(geometry, 'verts') and hasattr(geometry, 'faces'):
                    try:
                        verts = geometry.verts
                        faces_data = geometry.faces
                        
                        vertices = np.array(verts, dtype=np.float64)
                        if len(vertices.shape) == 1:
                            if len(vertices) % 3 == 0:
                                vertices = vertices.reshape(-1, 3)
                            else:
                                return None
                        
                        faces = np.array(faces_data, dtype=np.int32)
                        if len(faces.shape) == 1:
                            if len(faces) % 3 == 0:
                                faces = faces.reshape(-1, 3)
                            else:
                                return None
                        
                        if len(faces) > 0:
                            max_vertex_idx = np.max(faces)
                            if max_vertex_idx >= len(vertices):
                                return None
                        
                        storey_mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
                        logger.info(f"✓ Created storey mesh: {len(vertices)} vertices, {len(faces)} faces")
                        return storey_mesh
                    except Exception as e:
                        logger.warning(f"⚠ Failed to extract geometry: {e}")
                        return None
                else:
                    logger.warning(f"⚠ Geometry object missing 'verts' or 'faces' attributes")
                    return None
                    
            except ImportError:
                logger.warning("ifcopenshell.geom not available - cannot extract storey geometry")
                return None
            except Exception as e:
                logger.warning(f"Error creating storey mesh from IFC: {e}", exc_info=True)
                return None
        
        def initializeGL(self):
            """Initialize OpenGL."""
            from OpenGL import GL
            import logging
            logger = logging.getLogger(__name__)
            
            try:
                GL.glEnable(GL.GL_DEPTH_TEST)
                GL.glClearColor(0.1, 0.1, 0.15, 1.0)  # Darker background to avoid white screen
                GL.glEnable(GL.GL_CULL_FACE)
                GL.glCullFace(GL.GL_BACK)
                logger.info("OpenGL initialized - shaders will be created")
                
                # Simple shader program for default mesh with better visibility
                vertex_shader = QOpenGLShader(QOpenGLShader.ShaderTypeBit.Vertex)
                if not vertex_shader.compileSourceCode("""
                    attribute vec3 position;
                    uniform mat4 mvpMatrix;
                    varying float depth;
                    varying vec4 color;
                    void main() {
                        gl_Position = mvpMatrix * vec4(position, 1.0);
                        // Pass depth for simple shading
                        depth = gl_Position.z / gl_Position.w;
                        // Pass color through (gl_Color is set via GL.glColor3f in immediate mode)
                        color = gl_Color;
                    }
                """):
                    logger.error(f"Failed to compile vertex shader: {vertex_shader.log()}")
                    return
                
                fragment_shader = QOpenGLShader(QOpenGLShader.ShaderTypeBit.Fragment)
                if not fragment_shader.compileSourceCode("""
                    varying float depth;
                    varying vec4 color;
                    void main() {
                        // Use vertex color (passed from vertex shader via gl_Color)
                        // The color is set via GL.glColor3f() in the code before each vertex
                        vec3 baseColor = color.rgb;
                        
                        // Simple depth-based shading for better 3D perception
                        float depthFactor = 0.7 + 0.3 * smoothstep(-1.0, 1.0, depth);
                        
                        // Apply depth shading
                        vec3 finalColor = baseColor * depthFactor;
                        
                        gl_FragColor = vec4(finalColor, 1.0);
                    }
                """):
                    logger.error(f"Failed to compile fragment shader: {fragment_shader.log()}")
                    return
                
                self.shader_program = QOpenGLShaderProgram()
                self.shader_program.addShader(vertex_shader)
                self.shader_program.addShader(fragment_shader)
                if not self.shader_program.link():
                    logger.error(f"Failed to link shader program: {self.shader_program.log()}")
                    return
                else:
                    logger.info("Main shader program linked successfully")
                
                # Colored shader program for window highlighting
                vertex_shader_colored = QOpenGLShader(QOpenGLShader.ShaderTypeBit.Vertex)
                if not vertex_shader_colored.compileSourceCode("""
                    attribute vec3 position;
                    uniform mat4 mvpMatrix;
                    void main() {
                        gl_Position = mvpMatrix * vec4(position, 1.0);
                    }
                """):
                    logger.error(f"Failed to compile colored vertex shader: {vertex_shader_colored.log()}")
                    return
                
                fragment_shader_colored = QOpenGLShader(QOpenGLShader.ShaderTypeBit.Fragment)
                if not fragment_shader_colored.compileSourceCode("""
                    uniform vec4 color;
                    void main() {
                        gl_FragColor = color;
                    }
                """):
                    logger.error(f"Failed to compile colored fragment shader: {fragment_shader_colored.log()}")
                    return
                
                self.shader_program_colored = QOpenGLShaderProgram()
                self.shader_program_colored.addShader(vertex_shader_colored)
                self.shader_program_colored.addShader(fragment_shader_colored)
                if not self.shader_program_colored.link():
                    logger.error(f"Failed to link colored shader: {self.shader_program_colored.log()}")
                else:
                    logger.info("Colored shader program linked successfully")
                
                # If there's a pending highlight, apply it now that shaders are ready
                if self.highlighted_window is not None:
                    # Get object ID for logging
                    obj_id = None
                    if hasattr(self.highlighted_window, 'GlobalId'):
                        obj_id = self.highlighted_window.GlobalId
                    elif hasattr(self.highlighted_window, 'id'):
                        obj_id = str(self.highlighted_window.id) if callable(self.highlighted_window.id) else self.highlighted_window.id
                    logger.info(f"Shaders initialized - applying pending highlight for {obj_id}")
                    # Re-highlight to create mesh and render
                    window_to_highlight = self.highlighted_window
                    self.highlighted_window = None  # Clear first
                    self.highlight_window(window_to_highlight)  # Re-apply
            except Exception as e:
                logger.error(f"Error initializing OpenGL: {e}", exc_info=True)
            
        def resizeGL(self, width, height):
            """Handle resize."""
            from OpenGL import GL
            GL.glViewport(0, 0, width, height)
        
        def paintGL(self):
            """Paint the scene with orbit camera."""
            from OpenGL import GL
            import logging
            logger = logging.getLogger(__name__)
            
            try:
                # Only log first call and errors to avoid spam
                if not hasattr(self, '_paintgl_logged'):
                    logger.info("=== STEP 1: paintGL() called (first time) ===")
                    self._paintgl_logged = True
                
                # Ensure we have a valid OpenGL context
                if not self.isValid():
                    if not hasattr(self, '_context_error_logged'):
                        logger.error("❌ STEP 1 FAILED: OpenGL context is not valid - cannot render")
                        self._context_error_logged = True
                    return
                
                # Clear with dark background to avoid white screen
                GL.glClearColor(0.1, 0.1, 0.15, 1.0)
                GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
                
                # Check if shaders are initialized
                if self.shader_program is None:
                    if not hasattr(self, '_shader_error_logged'):
                        logger.error("❌ STEP 3 FAILED: Shader program not initialized yet - showing background only")
                        logger.error("   This means OpenGL initialization failed or widget is not visible yet")
                        self._shader_error_logged = True
                    return
                
                if self.mesh is None:
                    # This is normal during initialization - widget renders before mesh is loaded
                    # Only log once as debug/info, not as error
                    if not hasattr(self, '_mesh_none_logged'):
                        logger.debug("Mesh not loaded yet - showing background (this is normal during initialization)")
                        self._mesh_none_logged = True
                    return
                
                if len(self.mesh.vertices) == 0:
                    if not hasattr(self, '_mesh_empty_logged'):
                        logger.warning("⚠ Mesh has no vertices - showing background only")
                        logger.warning(f"   Mesh object exists but has 0 vertices (faces: {len(self.mesh.faces) if hasattr(self.mesh, 'faces') else 'N/A'})")
                        self._mesh_empty_logged = True
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
                
                # Draw main mesh (always show it, even when highlighting)
                if self.mesh is not None and len(self.mesh.vertices) > 0:
                    if not hasattr(self, '_mesh_drawn_logged'):
                        logger.info(f"=== STEP 7: Drawing main mesh - {len(self.mesh.vertices):,} vertices, {len(self.mesh.faces):,} faces ===")
                        self._mesh_drawn_logged = True
                    
                    if not self.shader_program.bind():
                        if not hasattr(self, '_bind_error_logged'):
                            logger.error("❌ STEP 7 FAILED: Failed to bind shader program")
                            self._bind_error_logged = True
                        return
                    
                    self.shader_program.setUniformValue("mvpMatrix", mvp)
                    
                    vertices = self.mesh.vertices
                    faces = self.mesh.faces
                    
                    # Enable depth testing for proper rendering
                    GL.glEnable(GL.GL_DEPTH_TEST)
                    GL.glDepthFunc(GL.GL_LESS)
                    
                    # Set default color first (light gray-blue)
                    GL.glColor3f(0.85, 0.88, 0.92)
                    
                    # Enable color material if we have vertex colors
                    has_colors = self.vertex_colors is not None and len(self.vertex_colors) > 0
                    if has_colors:
                        GL.glEnable(GL.GL_COLOR_MATERIAL)
                        GL.glColorMaterial(GL.GL_FRONT_AND_BACK, GL.GL_AMBIENT_AND_DIFFUSE)
                    
                    GL.glBegin(GL.GL_TRIANGLES)
                    vertex_color_idx = 0
                    for face in faces:
                        for vertex_idx in face:
                            if vertex_idx < len(vertices):
                                v = vertices[vertex_idx]
                                # Set color if available
                                if has_colors and vertex_color_idx < len(self.vertex_colors):
                                    color = self.vertex_colors[vertex_color_idx]
                                    # Ensure color values are in valid range
                                    r = max(0.0, min(1.0, float(color[0])))
                                    g = max(0.0, min(1.0, float(color[1])))
                                    b = max(0.0, min(1.0, float(color[2])))
                                    GL.glColor3f(r, g, b)
                                    vertex_color_idx += 1
                                # If no colors, the default color set above will be used
                                GL.glVertex3f(float(v[0]), float(v[1]), float(v[2]))
                    GL.glEnd()
                    
                    if has_colors:
                        GL.glDisable(GL.GL_COLOR_MATERIAL)
                    
                    self.shader_program.release()
                
                # Draw highlighted window/space/door with colored surface
                if self.highlighted_window is not None:
                    logger.info("=== STEP 8: Drawing highlighted object ===")
                    # Get object ID (works for both Window objects and IFC elements)
                    # Use the same ID enhancement logic as highlight_window() to match cached mesh
                    obj_id = None
                    if hasattr(self.highlighted_window, 'GlobalId'):
                        obj_id = self.highlighted_window.GlobalId
                        logger.info(f"✓ STEP 8a: Found GlobalId: {obj_id}")
                    elif hasattr(self.highlighted_window, 'id'):
                        obj_id = str(self.highlighted_window.id) if callable(self.highlighted_window.id) else self.highlighted_window.id
                        logger.info(f"✓ STEP 8a: Found id: {obj_id}")
                    
                    # Apply same ID enhancement for Window objects (add position hash)
                    # This must match the logic in highlight_window() to find the cached mesh
                    try:
                        from models.building import Window
                        is_window_object = isinstance(self.highlighted_window, Window)
                        if is_window_object and obj_id:
                            # Add position hash to match the enhanced ID used when caching
                            if hasattr(self.highlighted_window, 'center') and self.highlighted_window.center is not None:
                                center = self.highlighted_window.center
                                pos_hash = abs(hash(tuple(round(c, 2) for c in center)))
                                obj_id = f"{obj_id}_pos{pos_hash}"
                                logger.info(f"✓ STEP 8a1: Enhanced Window object ID with position hash: {obj_id}")
                    except ImportError:
                        pass  # Window class not available, skip enhancement
                    
                    if obj_id is None:
                        logger.error("❌ STEP 8 FAILED: Highlighted object has no identifiable ID")
                        logger.error(f"   Object type: {type(self.highlighted_window).__name__}")
                        logger.error(f"   Object attributes: {[attr for attr in dir(self.highlighted_window) if not attr.startswith('_')]}")
                    else:
                        window_mesh = self.window_meshes.get(obj_id)
                        if window_mesh is None:
                            logger.error(f"❌ STEP 8 FAILED: Mesh not found in cache for {obj_id}")
                            logger.error(f"   Available cached meshes: {list(self.window_meshes.keys())}")
                            logger.error(f"   This means mesh creation failed - check highlight_window() logs")
                        elif len(window_mesh.vertices) == 0:
                            logger.error(f"❌ STEP 8 FAILED: Mesh has no vertices for {obj_id}")
                        else:
                            logger.info(f"✓ STEP 8b: Found cached mesh for {obj_id}: {len(window_mesh.vertices)} vertices, {len(window_mesh.faces)} faces")
                            # Validate that window mesh is different from main building mesh
                            if self.mesh is not None and len(self.mesh.vertices) > 0:
                                # Check if window mesh is the same as main mesh (shouldn't happen)
                                if (len(window_mesh.vertices) == len(self.mesh.vertices) and 
                                    len(window_mesh.faces) == len(self.mesh.faces)):
                                    # Check if they're actually the same mesh
                                    window_center = window_mesh.centroid
                                    main_center = self.mesh.centroid
                                    if np.allclose(window_center, main_center, atol=0.01):
                                        logger.error(f"❌ WARNING: Window mesh appears to be the same as main building mesh!")
                                        logger.error(f"   This means window geometry extraction failed - using building mesh instead")
                                        logger.error(f"   Window mesh center: {window_center}")
                                        logger.error(f"   Main mesh center: {main_center}")
                                        logger.error(f"   This is why all windows highlight the same geometry!")
                        if window_mesh is not None and len(window_mesh.vertices) > 0:
                            # Check if colored shader is available
                            if self.shader_program_colored is None:
                                logger.error("❌ STEP 8c FAILED: Colored shader not initialized - cannot highlight window")
                                logger.error("   This means OpenGL initialization failed for colored shader")
                            else:
                                try:
                                    logger.info("✓ STEP 8c: Colored shader is available")
                                    # Use colored shader
                                    if not self.shader_program_colored.bind():
                                        logger.error("❌ STEP 8d FAILED: Failed to bind colored shader for window highlighting")
                                    else:
                                        logger.info("✓ STEP 8d: Colored shader bound successfully")
                                        self.shader_program_colored.setUniformValue("mvpMatrix", mvp)
                                        
                                        # Highlight color based on element type
                                        if getattr(self, 'highlight_is_space', False):
                                            color_vec = QVector4D(1.0, 0.0, 0.0, 0.6)  # Red for spaces
                                            color_name = "red (space)"
                                        elif getattr(self, 'highlight_is_door', False):
                                            color_vec = QVector4D(0.0, 1.0, 0.0, 0.6)  # Green for doors
                                            color_name = "green (door)"
                                        elif getattr(self, 'highlight_is_window', False):
                                            color_vec = QVector4D(0.0, 1.0, 1.0, 0.6)  # Cyan for IFC windows
                                            color_name = "cyan (IFC window)"
                                        elif getattr(self, 'highlight_is_wall', False):
                                            color_vec = QVector4D(1.0, 1.0, 0.0, 0.6)  # Yellow for walls
                                            color_name = "yellow (wall)"
                                        elif getattr(self, 'highlight_is_slab', False):
                                            color_vec = QVector4D(1.0, 0.0, 1.0, 0.6)  # Magenta for slabs
                                            color_name = "magenta (slab)"
                                        elif getattr(self, 'highlight_is_opening', False):
                                            color_vec = QVector4D(1.0, 0.0, 1.0, 0.6)  # Purple for openings
                                            color_name = "purple (opening)"
                                        elif getattr(self, 'highlight_is_storey', False):
                                            color_vec = QVector4D(1.0, 0.5, 0.0, 0.6)  # Orange for storeys
                                            color_name = "orange (storey)"
                                        else:
                                            color_vec = QVector4D(0.0, 0.8, 1.0, 1.0)  # Bright cyan-blue, fully opaque for Window objects
                                            color_name = "bright cyan-blue (window object)"
                                        self.shader_program_colored.setUniformValue("color", color_vec)
                                        logger.info(f"✓ STEP 8e: Color set to {color_name}")
                                        
                                        # Log window position relative to model for debugging
                                        if self.mesh is not None and len(self.mesh.vertices) > 0:
                                            model_bounds = self.mesh.bounds
                                            window_bounds = window_mesh.bounds
                                            logger.info(f"✓ STEP 8f1: Model bounds: {model_bounds}")
                                            logger.info(f"✓ STEP 8f2: Window bounds: {window_bounds}")
                                            logger.info(f"✓ STEP 8f3: Window center: {window_mesh.centroid}")
                                            logger.info(f"✓ STEP 8f4: Window extents: {window_mesh.extents}")
                                        
                                        # Enable blending for transparency
                                        GL.glEnable(GL.GL_BLEND)
                                        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
                                        logger.info("✓ STEP 8f: Blending enabled for transparency")
                                        
                                        # Disable depth testing for highlights to ensure they're always visible
                                        # This makes highlights render on top of the model
                                        GL.glDisable(GL.GL_DEPTH_TEST)
                                        logger.info("✓ STEP 8f5: Depth testing disabled for highlight visibility")
                                        
                                        # Draw window/door/space mesh
                                        vertices = window_mesh.vertices
                                        faces = window_mesh.faces
                                        
                                        GL.glBegin(GL.GL_TRIANGLES)
                                        highlight_triangles = 0
                                        for face in faces:
                                            for vertex_idx in face:
                                                if vertex_idx < len(vertices):
                                                    v = vertices[vertex_idx]
                                                    GL.glVertex3f(float(v[0]), float(v[1]), float(v[2]))
                                                    highlight_triangles += 1
                                        GL.glEnd()
                                        logger.info(f"✓ STEP 8g: Drawn {highlight_triangles // 3:,} triangles for highlighted object")
                                        
                                        # Re-enable depth testing
                                        GL.glEnable(GL.GL_DEPTH_TEST)
                                        GL.glDisable(GL.GL_BLEND)
                                        self.shader_program_colored.release()
                                        logger.info("✓ STEP 8h: Highlight rendering complete")
                                except Exception as e:
                                    logger.error(f"❌ STEP 8 ERROR: Error rendering highlighted window: {e}", exc_info=True)
                        else:
                            logger.warning(f"⚠ STEP 8 SKIPPED: Object mesh not available for highlighting: {obj_id}")
                else:
                    logger.debug("No highlighted object - skipping STEP 8")
            except Exception as e:
                logger.error(f"❌ FATAL ERROR in paintGL: {e}", exc_info=True)
        
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
        
        def keyPressEvent(self, event):
            """Handle keyboard input for rotation controls."""
            key = event.key()
            
            # Arrow keys for rotation
            if key == Qt.Key.Key_Left:
                self.azimuth -= 5.0  # Rotate left
                self.azimuth = self.azimuth % 360.0
                self.update()
            elif key == Qt.Key.Key_Right:
                self.azimuth += 5.0  # Rotate right
                self.azimuth = self.azimuth % 360.0
                self.update()
            elif key == Qt.Key.Key_Up:
                self.elevation += 5.0  # Rotate up
                self.elevation = max(-89.0, min(89.0, self.elevation))
                self.update()
            elif key == Qt.Key.Key_Down:
                self.elevation -= 5.0  # Rotate down
                self.elevation = max(-89.0, min(89.0, self.elevation))
                self.update()
            # Space bar to toggle auto-rotation
            elif key == Qt.Key.Key_Space:
                self.toggle_auto_rotate()
            else:
                super().keyPressEvent(event)
        
        def _auto_rotate_step(self):
            """Step function for auto-rotation timer."""
            if self.auto_rotate:
                self.azimuth += self.rotation_speed
                self.azimuth = self.azimuth % 360.0
                self.update()
        
        def toggle_auto_rotate(self):
            """Toggle auto-rotation on/off."""
            self.auto_rotate = not self.auto_rotate
            if self.auto_rotate:
                self.rotation_timer.start()
            else:
                self.rotation_timer.stop()
            return self.auto_rotate
        
        def set_rotation_speed(self, speed):
            """Set rotation speed (degrees per frame)."""
            self.rotation_speed = max(0.1, min(5.0, speed))  # Clamp between 0.1 and 5.0
        
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
        
        def showEvent(self, event):
            """Handle widget show event - ensure OpenGL context is ready and render."""
            super().showEvent(event)
            import logging
            logger = logging.getLogger(__name__)
            
            # When widget becomes visible, ensure OpenGL context is ready
            if self.isValid():
                try:
                    self.makeCurrent()
                    # If we have a pending highlight, apply it now
                    if self.highlighted_window is not None:
                        # Get object ID for logging
                        obj_id = None
                        if hasattr(self.highlighted_window, 'GlobalId'):
                            obj_id = self.highlighted_window.GlobalId
                        elif hasattr(self.highlighted_window, 'id'):
                            obj_id = str(self.highlighted_window.id) if callable(self.highlighted_window.id) else self.highlighted_window.id
                        logger.info(f"Widget shown - applying pending highlight for {obj_id}")
                        window_to_highlight = self.highlighted_window
                        self.highlighted_window = None  # Clear first
                        self.highlight_window(window_to_highlight)  # Re-apply
                    else:
                        # Force a repaint to show the model
                        self.update()
                except Exception as e:
                    logger.warning(f"Could not make OpenGL context current on show: {e}")
            else:
                logger.warning("OpenGL context not valid when widget shown")
    
    class GLBViewerWidget(QWidget):
        """Widget for viewing GLB 3D models (embedded in main window)."""
        
        def __init__(self, parent=None):
            super().__init__(parent)
            import logging
            logger = logging.getLogger(__name__)
            
            logger.info("=== GLBViewerWidget.__init__() called ===")
            self.mesh = None
            # Check OpenGL availability at runtime (always re-check)
            self.opengl_available = check_opengl_available()
            logger.info(f"OpenGL available check result: {self.opengl_available}")
            
            # Log for debugging
            if not self.opengl_available:
                logger.warning("⚠ OpenGL not available - will use fallback Trimesh viewer")
                logger.warning("   Install PyOpenGL: pip install PyOpenGL PyOpenGL-accelerate")
                logger.warning("   Then restart the application")
            else:
                logger.info("✓ OpenGL is available - will use embedded OpenGL viewer")
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
            
            # Auto-rotation toggle button
            self.auto_rotate_btn = QPushButton("Auto Rotate / Авто вращение")
            self.auto_rotate_btn.setCheckable(True)
            self.auto_rotate_btn.setStyleSheet(get_button_style('secondary'))
            self.auto_rotate_btn.clicked.connect(self.toggle_auto_rotate)
            controls_layout.addWidget(self.auto_rotate_btn)
            
            controls_layout.addWidget(QLabel("Zoom / Масштаб:"))
            self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
            self.zoom_slider.setMinimum(10)
            self.zoom_slider.setMaximum(100)
            self.zoom_slider.setValue(50)
            self.zoom_slider.valueChanged.connect(self.on_zoom_changed)
            controls_layout.addWidget(self.zoom_slider)
            
            controls_layout.addWidget(QLabel("Rotate Speed / Скорость вращения:"))
            self.rotate_speed_slider = QSlider(Qt.Orientation.Horizontal)
            self.rotate_speed_slider.setMinimum(1)  # 0.1 degrees per frame
            self.rotate_speed_slider.setMaximum(50)  # 5.0 degrees per frame
            self.rotate_speed_slider.setValue(5)  # Default: 0.5 degrees per frame
            self.rotate_speed_slider.valueChanged.connect(self.on_rotate_speed_changed)
            controls_layout.addWidget(self.rotate_speed_slider)
            
            # Add hint about controls
            hint_label = QLabel("Mouse: Left Drag = Rotate | Right/Shift+Left = Pan | Wheel = Zoom | Arrow Keys = Rotate | Space = Auto Rotate")
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
            import logging
            logger = logging.getLogger(__name__)
            
            if self.opengl_available:
                logger.info("Creating embedded OpenGL viewer widget...")
                self.viewer = GLBViewerOpenGLWidget(self)  # Set parent to embed in widget
                # Set size policy to expand and fill available space
                self.viewer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
                # Ensure widget is shown when tab becomes visible
                self.viewer.setVisible(True)
                logger.info("✓ Embedded OpenGL viewer widget created successfully")
            else:
                logger.warning("Creating fallback placeholder widget (OpenGL not available)...")
                # Fallback: create a placeholder widget
                self.viewer = QLabel("OpenGL not available. Please restart the application after installing PyOpenGL.", self)
                self.viewer.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.viewer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
                logger.warning("⚠ Using placeholder widget - no 3D rendering available")
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
        
        def load_mesh(self, mesh, auto_open_viewer=False):
            """Load mesh into viewer. Works for both GLB and IFC files.
            
            Args:
                mesh: trimesh.Trimesh object to load
                auto_open_viewer: If True, automatically open Trimesh viewer (ignored for OpenGL viewer)
            """
            import logging
            logger = logging.getLogger(__name__)
            
            logger.info("=== GLBViewerWidget.load_mesh() called ===")
            logger.info(f"OpenGL available: {self.opengl_available}")
            logger.info(f"Mesh provided: {mesh is not None}")
            if mesh is not None:
                logger.info(f"Mesh has {len(mesh.vertices):,} vertices, {len(mesh.faces):,} faces")
            
            # Note: auto_open_viewer is ignored for OpenGL viewer (only used by Trimesh fallback)
            if auto_open_viewer:
                logger.debug("auto_open_viewer=True (ignored for OpenGL viewer)")
            
            self.mesh = mesh
            if self.opengl_available:
                logger.info("✓ OpenGL is available - using embedded OpenGL viewer")
                if hasattr(self.viewer, 'set_mesh'):
                    logger.info("✓ Viewer has set_mesh() method - calling it")
                    try:
                        self.viewer.set_mesh(mesh)
                        logger.info("✓ set_mesh() called successfully on OpenGL viewer")
                    except Exception as e:
                        logger.error(f"❌ Error calling set_mesh() on OpenGL viewer: {e}", exc_info=True)
                else:
                    logger.error(f"❌ Viewer does not have set_mesh() method")
                    logger.error(f"   Viewer type: {type(self.viewer).__name__}")
                    logger.error(f"   Viewer attributes: {[attr for attr in dir(self.viewer) if not attr.startswith('_')]}")
            else:
                logger.warning("⚠ OpenGL not available - using fallback viewer")
                logger.warning("   This means PyOpenGL is not installed or OpenGL context failed")
                logger.warning("   Install with: pip install PyOpenGL PyOpenGL-accelerate")
                # If OpenGL not available, show message
                if hasattr(self.viewer, 'setText'):
                    self.viewer.setText(f"OpenGL not available.\nMesh loaded: {len(mesh.vertices):,} vertices, {len(mesh.faces):,} faces\nPlease restart the application after installing PyOpenGL.")
            
            if mesh is not None:
                info = f"Vertices: {len(mesh.vertices):,}, Faces: {len(mesh.faces):,} / Вершин: {len(mesh.vertices):,}, Граней: {len(mesh.faces):,}"
                self.info_label.setText(info)
            else:
                self.info_label.setText("No model loaded / Модель не загружена")
        
        def set_building(self, building):
            """Set building data for window highlighting."""
            if self.opengl_available and hasattr(self.viewer, 'set_building'):
                self.viewer.set_building(building)
        
        def set_ifc_file(self, ifc_file):
            """Set IFC file reference for extracting actual geometry from IFC elements."""
            if self.opengl_available and hasattr(self.viewer, 'set_ifc_file'):
                self.viewer.set_ifc_file(ifc_file)
        
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
                # Stop auto-rotation when resetting
                if hasattr(self.viewer, 'auto_rotate') and self.viewer.auto_rotate:
                    self.viewer.toggle_auto_rotate()
                    self.auto_rotate_btn.setChecked(False)
                    self.auto_rotate_btn.setText("Auto Rotate / Авто вращение")
                
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
        
        def toggle_auto_rotate(self):
            """Toggle auto-rotation on/off."""
            if self.opengl_available and hasattr(self.viewer, 'toggle_auto_rotate'):
                is_enabled = self.viewer.toggle_auto_rotate()
                # Update button state
                self.auto_rotate_btn.setChecked(is_enabled)
                if is_enabled:
                    self.auto_rotate_btn.setText("Stop Rotate / Остановить")
                else:
                    self.auto_rotate_btn.setText("Auto Rotate / Авто вращение")
        
        def on_rotate_speed_changed(self, value):
            """Handle rotation speed slider change."""
            if self.opengl_available and hasattr(self.viewer, 'set_rotation_speed'):
                # Convert slider value (1-50) to speed (0.1-5.0 degrees per frame)
                speed = value / 10.0
                self.viewer.set_rotation_speed(speed)

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
            """Highlight a specific object (window, space, door, or any object) in Trimesh viewer. Automatically opens viewer if not already open. Works for both GLB and IFC files."""
            import logging
            logger = logging.getLogger(__name__)
            
            if window is None:
                self.highlighted_window = None
                logger.info("Object highlight cleared for Trimesh viewer")
                # Update viewer if it's open
                if self.trimesh_viewer_open:
                    self._update_trimesh_viewer()
                return
            
            # Check if this is an IFC element (space, door, etc.)
            is_ifc_space = False
            is_ifc_door = False
            if hasattr(window, 'is_a') and callable(window.is_a):
                try:
                    is_ifc_space = window.is_a("IfcSpace")
                    is_ifc_door = window.is_a("IfcDoor")
                    logger.info(f"IFC element detection: is_ifc_space={is_ifc_space}, is_ifc_door={is_ifc_door}")
                except Exception as e:
                    logger.warning(f"Error calling is_a() method: {e}")
            elif hasattr(window, '__class__'):
                class_str = str(window.__class__)
                is_ifc_space = 'IfcSpace' in class_str
                is_ifc_door = 'IfcDoor' in class_str
                logger.info(f"IFC element detection (class string): is_ifc_space={is_ifc_space}, is_ifc_door={is_ifc_door}")
            
            # Get object ID (works for both Window objects and IFC elements)
            obj_id = None
            if hasattr(window, 'GlobalId'):
                obj_id = window.GlobalId
            elif hasattr(window, 'id'):
                if callable(window.id):
                    obj_id = str(window.id())
                else:
                    obj_id = str(window.id)
            
            if obj_id is None:
                logger.warning(f"Object {type(window)} does not have identifiable ID (no GlobalId or id attribute) - cannot highlight")
                return
            
            # Check if mesh is available (required for highlighting)
            if self.mesh is None:
                logger.warning(f"Cannot highlight object {obj_id}: No mesh loaded in viewer")
                logger.info("Note: Make sure the model (GLB or IFC) has been loaded and mesh generation succeeded")
                return
            
            # Verify mesh has valid data
            if not hasattr(self.mesh, 'vertices') or len(self.mesh.vertices) == 0:
                logger.warning(f"Cannot highlight object {obj_id}: Mesh has no vertices")
                return
            
            obj_type = 'space' if is_ifc_space else ('door' if is_ifc_door else 'object')
            logger.info(f"Object highlighted for Trimesh viewer: {obj_id} (type: {obj_type})")
            self.highlighted_window = window
            
            # Generate object mesh if not cached (works for windows, spaces, doors, and other objects)
            if obj_id not in self.window_meshes:
                if is_ifc_space:
                    object_mesh = self._create_space_mesh_from_ifc(window)
                elif is_ifc_door:
                    object_mesh = self._create_door_mesh_from_ifc(window)
                else:
                    object_mesh = self._create_window_mesh(window)
                
                self.window_meshes[obj_id] = object_mesh
                if object_mesh is None:
                    logger.warning(f"Failed to create mesh for {obj_type} {obj_id}")
                else:
                    logger.info(f"Created mesh for {obj_type} {obj_id} with {len(object_mesh.vertices)} vertices")
            
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
                return
            
            try:
                # Close any existing pyglet windows
                try:
                    import pyglet
                    # Close all pyglet windows
                    for window in pyglet.app.windows:
                        window.close()
                except Exception as e:
                    logger.debug(f"Could not close existing pyglet windows: {e}")
                
                # Create updated scene and show it
                scene = self._create_trimesh_scene()
                scene.show()
                logger.info("Trimesh viewer updated with highlighted window")
            except Exception as e:
                logger.warning(f"Could not update Trimesh viewer: {e}")
        
        def _create_window_mesh(self, window):
            """Create a trimesh representation of an object (window or any object) from its properties. Works for any object with center, normal, and size attributes."""
            import trimesh
            import numpy as np
            import logging
            
            logger = logging.getLogger(__name__)
            
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
            
            # Create rectangle vertices
            half_width = width / 2.0
            half_height = height / 2.0
            
            corners = [
                center + (-half_width * right) + (-half_height * up),
                center + (half_width * right) + (-half_height * up),
                center + (half_width * right) + (half_height * up),
                center + (-half_width * right) + (half_height * up)
            ]
            
            # Create two triangles
            vertices = np.array(corners)
            faces = np.array([
                [0, 1, 2],
                [0, 2, 3]
            ])
            
            # Create trimesh (works for windows and other objects)
            object_mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
            return object_mesh
        
        def _create_space_mesh_from_ifc(self, space_element):
            """Create a trimesh representation of an IFC space from its geometry."""
            import trimesh
            import numpy as np
            import logging
            logger = logging.getLogger(__name__)
            
            try:
                # Try to extract geometry from IFC space element using ifcopenshell
                import ifcopenshell
                import ifcopenshell.geom as geom
                
                # Create geometry settings
                settings = geom.settings()
                try:
                    if hasattr(settings, 'USE_WORLD_COORDS'):
                        settings.set(settings.USE_WORLD_COORDS, True)
                except Exception:
                    pass
                
                # Create shape from space element
                try:
                    shape = geom.create_shape(settings, space_element)
                    if not shape:
                        logger.warning(f"Could not create shape for space {getattr(space_element, 'GlobalId', space_element.id())}")
                        return None
                except Exception as e:
                    logger.warning(f"Could not create shape for space {getattr(space_element, 'GlobalId', space_element.id())}: {e}")
                    return None
                
                # Get geometry from shape
                geometry = shape.geometry
                if not geometry:
                    logger.warning(f"Space {getattr(space_element, 'GlobalId', space_element.id())} has no geometry")
                    return None
                
                # Extract vertices and faces
                vertices = None
                faces = None
                
                # Method 1: Direct access to geometry.verts and geometry.faces
                if hasattr(geometry, 'verts') and hasattr(geometry, 'faces'):
                    try:
                        verts = geometry.verts
                        faces_data = geometry.faces
                        
                        # Convert to numpy arrays
                        vertices = np.array(verts, dtype=np.float64)
                        # Ensure vertices are in shape (n, 3)
                        if len(vertices.shape) == 1:
                            if len(vertices) % 3 == 0:
                                vertices = vertices.reshape(-1, 3)
                            else:
                                logger.warning(f"Invalid vertex count: {len(vertices)} (not divisible by 3)")
                                return None
                        elif len(vertices.shape) == 2 and vertices.shape[1] != 3:
                            logger.warning(f"Invalid vertex shape: {vertices.shape}")
                            return None
                        
                        faces = np.array(faces_data, dtype=np.int32)
                        # Ensure faces are in shape (n, 3)
                        if len(faces.shape) == 1:
                            if len(faces) % 3 == 0:
                                faces = faces.reshape(-1, 3)
                            else:
                                logger.warning(f"Invalid face count: {len(faces)} (not divisible by 3)")
                                return None
                        elif len(faces.shape) == 2 and faces.shape[1] != 3:
                            logger.warning(f"Invalid face shape: {faces.shape}")
                            return None
                    except Exception as e:
                        logger.warning(f"Failed to extract geometry using standard API: {e}")
                        return None
                
                # Create mesh if we have valid data
                if vertices is not None and faces is not None and len(vertices) > 0 and len(faces) > 0:
                    try:
                        # Validate face indices
                        if len(faces) > 0:
                            max_vertex_idx = np.max(faces)
                            if max_vertex_idx >= len(vertices):
                                logger.warning(f"Face indices out of range: max index {max_vertex_idx}, but only {len(vertices)} vertices")
                                return None
                        
                        space_mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
                        logger.info(f"Created space mesh with {len(vertices)} vertices, {len(faces)} faces")
                        return space_mesh
                    except Exception as mesh_error:
                        logger.warning(f"Failed to create trimesh from space geometry: {mesh_error}")
                        return None
                else:
                    logger.warning(f"Could not extract valid geometry for space {getattr(space_element, 'GlobalId', space_element.id())}")
                    return None
                    
            except ImportError:
                logger.warning("ifcopenshell.geom not available - cannot extract space geometry")
                return None
            except Exception as e:
                logger.warning(f"Error creating space mesh from IFC: {e}", exc_info=True)
                return None
        
        def _create_door_mesh_from_ifc(self, door_element):
            """Create a trimesh representation of an IFC door from its geometry."""
            import trimesh
            import numpy as np
            import logging
            logger = logging.getLogger(__name__)
            
            door_id = getattr(door_element, 'GlobalId', None) or getattr(door_element, 'id', None)
            logger.info(f"=== CREATING DOOR MESH (Trimesh viewer) ===")
            logger.info(f"Door ID: {door_id}")
            logger.info(f"Door type: {type(door_element).__name__}")
            
            try:
                # Try to extract geometry from IFC door element using ifcopenshell
                import ifcopenshell
                import ifcopenshell.geom as geom
                logger.info("✓ ifcopenshell.geom imported successfully")
                
                # Create geometry settings
                settings = geom.settings()
                try:
                    if hasattr(settings, 'USE_WORLD_COORDS'):
                        settings.set(settings.USE_WORLD_COORDS, True)
                        logger.info("✓ Enabled USE_WORLD_COORDS")
                except Exception as e:
                    logger.debug(f"Could not set USE_WORLD_COORDS: {e}")
                
                # Create shape from door element
                logger.info(f"Attempting to create shape from door element...")
                try:
                    shape = geom.create_shape(settings, door_element)
                    if not shape:
                        logger.error(f"❌ ISSUE #2: Could not create shape for door {door_id}")
                        logger.error(f"   geom.create_shape() returned None or False")
                        return None
                    logger.info("✓ Shape created successfully")
                except Exception as e:
                    logger.error(f"❌ ISSUE #2: Exception creating shape for door {door_id}: {e}", exc_info=True)
                    return None
                
                # Get geometry from shape
                geometry = shape.geometry
                if not geometry:
                    logger.error(f"❌ ISSUE #2: Door {door_id} has no geometry")
                    logger.error(f"   shape.geometry is None or empty")
                    return None
                logger.info("✓ Geometry extracted from shape")
                
                # Extract vertices and faces
                vertices = None
                faces = None
                
                # Method 1: Direct access to geometry.verts and geometry.faces
                logger.info(f"Checking geometry attributes: has verts={hasattr(geometry, 'verts')}, has faces={hasattr(geometry, 'faces')}")
                if hasattr(geometry, 'verts') and hasattr(geometry, 'faces'):
                    try:
                        verts = geometry.verts
                        faces_data = geometry.faces
                        logger.info(f"✓ Extracted verts and faces: {len(verts) if verts is not None else 'None'} vertices, {len(faces_data) if faces_data is not None else 'None'} faces")
                        
                        # Convert to numpy arrays
                        vertices = np.array(verts, dtype=np.float64)
                        # Ensure vertices are in shape (n, 3)
                        if len(vertices.shape) == 1:
                            if len(vertices) % 3 == 0:
                                vertices = vertices.reshape(-1, 3)
                            else:
                                logger.error(f"❌ ISSUE #2: Invalid vertex count: {len(vertices)} (not divisible by 3)")
                                return None
                        elif len(vertices.shape) == 2 and vertices.shape[1] != 3:
                            logger.error(f"❌ ISSUE #2: Invalid vertex shape: {vertices.shape}")
                            return None
                        
                        faces = np.array(faces_data, dtype=np.int32)
                        # Ensure faces are in shape (n, 3)
                        if len(faces.shape) == 1:
                            if len(faces) % 3 == 0:
                                faces = faces.reshape(-1, 3)
                            else:
                                logger.error(f"❌ ISSUE #2: Invalid face count: {len(faces)} (not divisible by 3)")
                                return None
                        elif len(faces.shape) == 2 and faces.shape[1] != 3:
                            logger.error(f"❌ ISSUE #2: Invalid face shape: {faces.shape}")
                            return None
                        logger.info(f"✓ Successfully converted to numpy arrays: {len(vertices)} vertices, {len(faces)} faces")
                    except Exception as e:
                        logger.error(f"❌ ISSUE #2: Failed to extract geometry using standard API: {e}", exc_info=True)
                        return None
                else:
                    logger.error(f"❌ ISSUE #2: Geometry object missing 'verts' or 'faces' attributes")
                    logger.error(f"   Geometry attributes: {dir(geometry)}")
                    return None
                
                # Create mesh if we have valid data
                if vertices is not None and faces is not None and len(vertices) > 0 and len(faces) > 0:
                    try:
                        # Validate face indices
                        if len(faces) > 0:
                            max_vertex_idx = np.max(faces)
                            if max_vertex_idx >= len(vertices):
                                logger.error(f"❌ ISSUE #2: Face indices out of range: max index {max_vertex_idx}, but only {len(vertices)} vertices")
                                return None
                        
                        door_mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
                        logger.info(f"✓ Created door mesh successfully: {len(vertices)} vertices, {len(faces)} faces")
                        logger.info(f"   Mesh bounds: {door_mesh.bounds}")
                        logger.info(f"   Mesh center: {door_mesh.centroid}")
                        return door_mesh
                    except Exception as mesh_error:
                        logger.error(f"❌ ISSUE #2: Failed to create trimesh from door geometry: {mesh_error}", exc_info=True)
                        return None
                else:
                    logger.error(f"❌ ISSUE #2: Could not extract valid geometry for door {door_id}")
                    logger.error(f"   vertices: {vertices is not None} (len={len(vertices) if vertices is not None else 0})")
                    logger.error(f"   faces: {faces is not None} (len={len(faces) if faces is not None else 0})")
                    return None
                    
            except ImportError:
                logger.warning("ifcopenshell.geom not available - cannot extract door geometry")
                return None
            except Exception as e:
                logger.warning(f"Error creating door mesh from IFC: {e}", exc_info=True)
                return None
        
        def _create_trimesh_scene(self):
            """Create a trimesh scene with main mesh and highlighted object (if any). Works for windows and other objects."""
            import trimesh
            import numpy as np
            import logging
            logger = logging.getLogger(__name__)
            
            # Validate mesh is available
            if self.mesh is None:
                logger.error("Cannot create Trimesh scene: No mesh loaded")
                raise ValueError("No mesh loaded - cannot create scene")
            
            if not hasattr(self.mesh, 'vertices') or len(self.mesh.vertices) == 0:
                logger.error("Cannot create Trimesh scene: Mesh has no vertices")
                raise ValueError("Mesh has no vertices - cannot create scene")
            
            # Create a copy of the mesh for better visualization
            # Add professional colors and materials
            display_mesh = self.mesh.copy()
            
            # Apply professional color scheme to main building mesh
            # Light gray/blue tint for building surfaces
            try:
                # Always apply professional colors for consistent appearance
                # Check if mesh has meaningful colors (not just default)
                has_meaningful_colors = False
                try:
                    if hasattr(display_mesh.visual, 'face_colors') and display_mesh.visual.face_colors is not None:
                        colors = display_mesh.visual.face_colors
                        if len(colors) > 0:
                            # Check if colors are varied (not all the same)
                            if len(colors.shape) == 2 and colors.shape[0] > 1:
                                # Check if there's variation in colors
                                color_variance = np.var(colors[:, :3], axis=0).sum()
                                if color_variance > 100:  # Has meaningful color variation
                                    has_meaningful_colors = True
                except:
                    pass
                
                # Apply our professional color scheme (overwrite if no meaningful colors exist)
                if not has_meaningful_colors:
                    # Create a nice light gray-blue color for the building
                    face_count = len(display_mesh.faces)
                    # Light gray-blue: RGB(200, 210, 220) with slight variation for depth perception
                    base_color = np.array([200, 210, 220], dtype=np.float32)
                    
                    # Add slight variation based on face normals for better 3D perception
                    try:
                        # Ensure face normals are calculated
                        if not hasattr(display_mesh, 'face_normals') or display_mesh.face_normals is None:
                            # Trimesh will calculate normals automatically when accessed
                            _ = display_mesh.face_normals  # Trigger calculation
                        
                        if hasattr(display_mesh, 'face_normals') and display_mesh.face_normals is not None and len(display_mesh.face_normals) == face_count:
                            # Use face normals to add subtle shading
                            normals = display_mesh.face_normals
                            # Calculate lighting factor based on normal direction (simulate top-down lighting)
                            # Assume light comes from above (0, 0, 1)
                            light_dir = np.array([0.3, 0.3, 1.0])
                            light_dir = light_dir / np.linalg.norm(light_dir)
                            # Dot product gives lighting intensity
                            lighting = np.clip(np.dot(normals, light_dir), 0.3, 1.0)
                            lighting = lighting.reshape(-1, 1)
                            # Apply lighting to base color
                            colors = (base_color * lighting).astype(np.uint8)
                            colors = np.hstack([colors, np.full((face_count, 1), 255, dtype=np.uint8)])
                        else:
                            # Simple uniform color
                            colors = np.tile(np.append(base_color.astype(np.uint8), 255), (face_count, 1))
                    except Exception as norm_error:
                        logger.debug(f"Could not calculate lighting: {norm_error}, using uniform color")
                        # Simple uniform color
                        colors = np.tile(np.append(base_color.astype(np.uint8), 255), (face_count, 1))
                    
                    display_mesh.visual.face_colors = colors
                    logger.info("Applied professional color scheme with lighting to building mesh")
                else:
                    logger.info("Mesh already has meaningful colors, keeping original")
            except Exception as e:
                logger.debug(f"Could not apply colors to mesh: {e}, using default")
            
            # Create scene
            scene = trimesh.Scene()
            
            # Add main mesh to scene (CRITICAL - this is the IFC/GLB model)
            try:
                scene.add_geometry(display_mesh, node_name='building')
                logger.info(f"Added main mesh to scene: {len(display_mesh.vertices):,} vertices, {len(display_mesh.faces):,} faces")
            except Exception as e:
                logger.error(f"Failed to add main mesh to scene: {e}")
                raise
            
            # Add highlighted object mesh if available (works for windows, spaces, doors, and other objects)
            if self.highlighted_window is not None:
                # Get object ID (works for both Window objects and IFC elements)
                object_id = None
                if hasattr(self.highlighted_window, 'GlobalId'):
                    object_id = self.highlighted_window.GlobalId
                elif hasattr(self.highlighted_window, 'id'):
                    if callable(self.highlighted_window.id):
                        object_id = str(self.highlighted_window.id())
                    else:
                        object_id = str(self.highlighted_window.id)
                else:
                    object_id = 'unknown'
                
                object_mesh = self.window_meshes.get(object_id)
                if object_mesh is not None:
                    # Color the object mesh: red for spaces, green for doors, blue for windows
                    try:
                        # Detect object type for color
                        is_ifc_space = False
                        is_ifc_door = False
                        if hasattr(self.highlighted_window, 'is_a') and callable(self.highlighted_window.is_a):
                            try:
                                is_ifc_space = self.highlighted_window.is_a("IfcSpace")
                                is_ifc_door = self.highlighted_window.is_a("IfcDoor")
                            except Exception:
                                pass
                        elif hasattr(self.highlighted_window, '__class__'):
                            class_str = str(self.highlighted_window.__class__)
                            is_ifc_space = 'IfcSpace' in class_str
                            is_ifc_door = 'IfcDoor' in class_str
                        
                        if is_ifc_space:
                            object_mesh.visual.face_colors = [255, 0, 0, 200]  # Red with transparency for spaces
                        elif is_ifc_door:
                            object_mesh.visual.face_colors = [0, 255, 0, 200]  # Green with transparency for doors
                        else:
                            object_mesh.visual.face_colors = [0, 128, 255, 200]  # Blue with transparency for windows
                        scene.add_geometry(object_mesh, node_name=f'highlighted_{object_id}')
                        logger.info(f"Added highlighted object {object_id} to Trimesh scene")
                    except Exception as e:
                        logger.warning(f"Could not color object mesh: {e}, showing without color")
                        scene.add_geometry(object_mesh, node_name=f'highlighted_{object_id}')
                else:
                    logger.warning(f"Object mesh not available for {object_id}")
            
            # Scene will be automatically centered and scaled by Trimesh viewer
            # The viewer handles camera positioning automatically
            
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

