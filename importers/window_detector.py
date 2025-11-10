"""
Advanced window detection from 3D mesh geometry.
Uses multiple algorithms to detect windows from building meshes.
"""

import logging
import numpy as np
from typing import List, Tuple, Optional, Dict
import trimesh

from models.building import Window

logger = logging.getLogger(__name__)


class WindowDetector:
    """Detects windows from 3D mesh geometry using various algorithms."""
    
    def __init__(self, mesh: trimesh.Trimesh):
        """
        Initialize window detector.
        
        Args:
            mesh: Trimesh object containing building geometry
        """
        self.mesh = mesh
        self.windows = []
    
    def detect_windows(self, room_bounds: np.ndarray) -> List[Window]:
        """
        Detect windows from mesh using multiple algorithms.
        
        Args:
            room_bounds: Bounding box of the room [min_bounds, max_bounds]
            
        Returns:
            List of detected Window objects
        """
        windows = []
        
        if self.mesh is None or len(self.mesh.vertices) == 0:
            logger.warning("Empty mesh, cannot detect windows")
            return windows
        
        logger.info("Starting window detection using multiple algorithms...")
        
        # Method 1: Detect openings/holes in walls
        logger.info("Method 1: Detecting openings/holes in mesh...")
        opening_windows = self._detect_openings(room_bounds)
        windows.extend(opening_windows)
        logger.info(f"Detected {len(opening_windows)} window(s) from openings")
        
        # Method 2: Detect rectangular openings (typical window shapes)
        logger.info("Method 2: Detecting rectangular openings...")
        rectangular_windows = self._detect_rectangular_openings(room_bounds)
        # Avoid duplicates
        for win in rectangular_windows:
            if not self._is_duplicate(win, windows):
                windows.append(win)
        logger.info(f"Detected {len(rectangular_windows)} additional window(s) from rectangular openings")
        
        # Method 3: Analyze mesh normals to find window-like surfaces
        logger.info("Method 3: Analyzing mesh normals for window surfaces...")
        normal_windows = self._detect_from_normals(room_bounds)
        for win in normal_windows:
            if not self._is_duplicate(win, windows):
                windows.append(win)
        logger.info(f"Detected {len(normal_windows)} additional window(s) from normal analysis")
        
        # Method 4: Extract from GLB metadata if available
        logger.info("Method 4: Checking GLB metadata for window information...")
        metadata_windows = self._extract_from_metadata()
        for win in metadata_windows:
            if not self._is_duplicate(win, windows):
                windows.append(win)
        logger.info(f"Detected {len(metadata_windows)} additional window(s) from metadata")
        
        logger.info(f"Total windows detected: {len(windows)}")
        return windows
    
    def _detect_openings(self, room_bounds: np.ndarray) -> List[Window]:
        """Detect windows by finding openings/holes in the mesh."""
        windows = []
        
        try:
            # Get mesh bounds
            min_bounds = room_bounds[0]
            max_bounds = room_bounds[1]
            
            # Find wall surfaces (surfaces facing outward)
            # Walls are typically vertical surfaces on the boundary
            wall_threshold = 0.1  # 10cm threshold for wall detection
            
            # Analyze mesh to find potential openings
            # Look for areas with missing geometry (holes)
            if hasattr(self.mesh, 'is_watertight') and not self.mesh.is_watertight:
                # Mesh has holes - these might be windows
                logger.info("Mesh is not watertight - checking for openings...")
                
                # Get boundary edges (edges that belong to only one face)
                if hasattr(self.mesh, 'edges_boundary'):
                    boundary_edges = self.mesh.edges[self.mesh.edges_boundary]
                    
                    if len(boundary_edges) > 0:
                        # Group boundary edges into potential openings
                        openings = self._group_boundary_edges_into_openings(boundary_edges, min_bounds, max_bounds)
                        
                        for opening in openings:
                            window = self._opening_to_window(opening, min_bounds, max_bounds)
                            if window:
                                windows.append(window)
            
        except Exception as e:
            logger.warning(f"Error detecting openings: {e}")
        
        return windows
    
    def _group_boundary_edges_into_openings(self, boundary_edges: np.ndarray, 
                                            min_bounds: np.ndarray, 
                                            max_bounds: np.ndarray) -> List[Dict]:
        """Group boundary edges into potential window openings."""
        openings = []
        
        if len(boundary_edges) == 0:
            return openings
        
        # Get vertices from boundary edges
        boundary_vertices = np.unique(boundary_edges.flatten())
        boundary_points = self.mesh.vertices[boundary_vertices]
        
        # Filter points that are on walls (near room boundaries)
        wall_points = []
        tolerance = 0.2  # 20cm tolerance
        
        for point in boundary_points:
            # Check if point is near a wall (on room boundary)
            on_wall = (
                abs(point[0] - min_bounds[0]) < tolerance or
                abs(point[0] - max_bounds[0]) < tolerance or
                abs(point[1] - min_bounds[1]) < tolerance or
                abs(point[1] - max_bounds[1]) < tolerance
            )
            
            if on_wall:
                wall_points.append(point)
        
        if len(wall_points) < 4:  # Need at least 4 points for a rectangular opening
            return openings
        
        # Cluster points into potential rectangular openings
        # Simple approach: find rectangular patterns
        wall_points = np.array(wall_points)
        
        # Group by wall face
        openings = self._find_rectangular_patterns(wall_points, min_bounds, max_bounds)
        
        return openings
    
    def _find_rectangular_patterns(self, points: np.ndarray, 
                                   min_bounds: np.ndarray, 
                                   max_bounds: np.ndarray) -> List[Dict]:
        """Find rectangular patterns in wall points (potential windows)."""
        openings = []
        
        if len(points) < 4:
            return openings
        
        # Group points by which wall they're on
        walls = {
            'front': [],  # +Y
            'back': [],   # -Y
            'left': [],   # -X
            'right': []   # +X
        }
        
        tolerance = 0.2
        
        for point in points:
            if abs(point[1] - max_bounds[1]) < tolerance:
                walls['front'].append(point)
            elif abs(point[1] - min_bounds[1]) < tolerance:
                walls['back'].append(point)
            elif abs(point[0] - min_bounds[0]) < tolerance:
                walls['left'].append(point)
            elif abs(point[0] - max_bounds[0]) < tolerance:
                walls['right'].append(point)
        
        # Find rectangular openings on each wall
        for wall_name, wall_points in walls.items():
            if len(wall_points) >= 4:
                opening = self._find_rectangle_in_points(np.array(wall_points), wall_name, min_bounds, max_bounds)
                if opening:
                    openings.append(opening)
        
        return openings
    
    def _find_rectangle_in_points(self, points: np.ndarray, wall_name: str,
                                  min_bounds: np.ndarray, max_bounds: np.ndarray) -> Optional[Dict]:
        """Find a rectangular opening in a set of points."""
        if len(points) < 4:
            return None
        
        # Project points to 2D based on wall orientation
        if wall_name in ['front', 'back']:
            # Project to XZ plane
            proj_points = points[:, [0, 2]]
        else:
            # Project to YZ plane
            proj_points = points[:, [1, 2]]
        
        # Find bounding rectangle
        min_proj = np.min(proj_points, axis=0)
        max_proj = np.max(proj_points, axis=0)
        
        # Check if it's a reasonable window size (0.5m to 3m)
        width = max_proj[0] - min_proj[0]
        height = max_proj[1] - min_proj[1]
        
        if 0.5 < width < 3.0 and 0.5 < height < 3.0:
            # Calculate center in 3D
            if wall_name == 'front':
                center = (np.mean(points[:, 0]), max_bounds[1], np.mean(points[:, 2]))
                normal = (0.0, 1.0, 0.0)
            elif wall_name == 'back':
                center = (np.mean(points[:, 0]), min_bounds[1], np.mean(points[:, 2]))
                normal = (0.0, -1.0, 0.0)
            elif wall_name == 'left':
                center = (min_bounds[0], np.mean(points[:, 1]), np.mean(points[:, 2]))
                normal = (-1.0, 0.0, 0.0)
            else:  # right
                center = (max_bounds[0], np.mean(points[:, 1]), np.mean(points[:, 2]))
                normal = (1.0, 0.0, 0.0)
            
            return {
                'center': center,
                'normal': normal,
                'size': (width, height),
                'wall': wall_name
            }
        
        return None
    
    def _opening_to_window(self, opening: Dict, min_bounds: np.ndarray, max_bounds: np.ndarray) -> Optional[Window]:
        """Convert an opening dictionary to a Window object."""
        try:
            window_id = f"window_{opening['wall']}_{len(self.windows)}"
            window = Window(
                id=window_id,
                center=opening['center'],
                normal=opening['normal'],
                size=opening['size'],
                window_type='detected',
                transmittance=0.75,
                frame_factor=0.70
            )
            return window
        except Exception as e:
            logger.warning(f"Error converting opening to window: {e}")
            return None
    
    def _detect_rectangular_openings(self, room_bounds: np.ndarray) -> List[Window]:
        """Detect windows by finding rectangular openings in walls."""
        windows = []
        
        try:
            # This is a simplified version - in practice, you'd use more sophisticated algorithms
            # For now, we'll use the opening detection which already looks for rectangles
            pass
        except Exception as e:
            logger.warning(f"Error detecting rectangular openings: {e}")
        
        return windows
    
    def _detect_from_normals(self, room_bounds: np.ndarray) -> List[Window]:
        """Detect windows by analyzing mesh normals (windows often have specific normal patterns)."""
        windows = []
        
        try:
            if not hasattr(self.mesh, 'face_normals'):
                return windows
            
            # Find faces with normals pointing outward (potential window surfaces)
            # Windows are often represented as separate surfaces with specific normals
            face_normals = self.mesh.face_normals
            face_centers = self.mesh.triangles_center
            
            # Filter faces that are on walls and have outward normals
            min_bounds = room_bounds[0]
            max_bounds = room_bounds[1]
            tolerance = 0.2
            
            for i, (normal, center) in enumerate(zip(face_normals, face_centers)):
                # Check if face is on a wall
                on_wall = (
                    abs(center[0] - min_bounds[0]) < tolerance or
                    abs(center[0] - max_bounds[0]) < tolerance or
                    abs(center[1] - min_bounds[1]) < tolerance or
                    abs(center[1] - max_bounds[1]) < tolerance
                )
                
                if on_wall:
                    # Check if normal is pointing outward (window-like)
                    # This is a simplified check
                    if abs(normal[2]) < 0.5:  # Not horizontal/vertical
                        # Potential window surface
                        pass  # Would need more sophisticated analysis
        
        except Exception as e:
            logger.warning(f"Error detecting from normals: {e}")
        
        return windows
    
    def _extract_from_metadata(self) -> List[Window]:
        """Extract windows from GLB metadata if available."""
        windows = []
        
        try:
            # Check if mesh has metadata
            if hasattr(self.mesh, 'metadata') and self.mesh.metadata:
                # Look for window information in metadata
                pass
        except Exception as e:
            logger.warning(f"Error extracting from metadata: {e}")
        
        return windows
    
    def _is_duplicate(self, window: Window, existing_windows: List[Window], 
                     distance_threshold: float = 0.5) -> bool:
        """Check if a window is a duplicate of an existing one."""
        for existing in existing_windows:
            # Calculate distance between centers
            dist = np.linalg.norm(
                np.array(window.center) - np.array(existing.center)
            )
            if dist < distance_threshold:
                return True
        return False

