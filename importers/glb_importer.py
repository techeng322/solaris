"""
GLB (glTF Binary) model importer.
GLB files contain 3D geometry with scene graph structure.
This importer extracts hierarchical building information from GLB scene graph.
"""

from typing import List, Dict, Optional, Tuple
import logging
import trimesh
import numpy as np
from pathlib import Path
import re

from .base_importer import BaseImporter
from models.building import Building, Window

logger = logging.getLogger(__name__)

# Try to import Open3D for advanced 3D processing
try:
    import open3d as o3d
    OPEN3D_AVAILABLE = True
except ImportError:
    OPEN3D_AVAILABLE = False
    logger.warning("Open3D not available - advanced window detection features disabled. Install with: pip install open3d")

# Try to import pygltflib for GLB material extraction
try:
    import pygltflib
    PYGGLTF_AVAILABLE = True
except ImportError:
    PYGGLTF_AVAILABLE = False
    logger.warning("pygltflib not available - material colors may not be extracted. Install with: pip install pygltflib")


class GLBImporter(BaseImporter):
    """
    Importer for GLB format 3D models.
    Extracts building information from GLB scene graph structure.
    """
    
    def __init__(self, file_path: str, lightweight: bool = True):
        """
        Initialize GLB importer.
        
        Args:
            file_path: Path to GLB file
            lightweight: If True, skip heavy mesh processing for large files
        """
        super().__init__(file_path)
        self.mesh = None
        self.scene = None
        self.lightweight = lightweight
        self.file_path = Path(file_path)
        self.gltf_data = None
        self.node_meshes = {}  # Map node index to mesh
        
    def import_model(self) -> List[Building]:
        """
        Import GLB model by analyzing MESH GEOMETRY directly (vertices and faces).
        Scans all vertices and faces to extract rooms and windows.
        
        Returns:
            List of Building objects
        """
        logger.info(f"Loading GLB file: {self.file_path}")
        logger.info("Using MESH-BASED extraction - analyzing vertices and faces directly")
        
        # Load mesh using trimesh
        try:
            file_path_str = str(self.file_path.resolve())
            loaded = trimesh.load(file_path_str)
            logger.info(f"GLB file loaded: {type(loaded)}")
            
            # Store scene for window extraction from individual geometries
            if isinstance(loaded, trimesh.Scene):
                self.scene = loaded
                logger.info(f"Scene has {len(loaded.geometry)} geometry object(s)")
                # Log all geometries
                for key, geometry in loaded.geometry.items():
                    if isinstance(geometry, trimesh.Trimesh):
                        logger.info(f"  Geometry '{key}': {len(geometry.vertices)} vertices, {len(geometry.faces)} faces")
                
                # Create combined mesh for default room (but we'll extract windows from individual geometries)
                # First, preserve colors from individual geometries if they exist
                meshes = []
                for key, geometry in loaded.geometry.items():
                    if isinstance(geometry, trimesh.Trimesh):
                        # Check if this geometry has colors
                        if hasattr(geometry, 'visual'):
                            if hasattr(geometry.visual, 'face_colors') and geometry.visual.face_colors is not None:
                                if len(geometry.visual.face_colors) > 0:
                                    logger.info(f"Geometry '{key}' has {len(geometry.visual.face_colors)} face colors")
                            elif hasattr(geometry.visual, 'vertex_colors') and geometry.visual.vertex_colors is not None:
                                if len(geometry.visual.vertex_colors) > 0:
                                    logger.info(f"Geometry '{key}' has {len(geometry.visual.vertex_colors)} vertex colors")
                        meshes.append(geometry)
                
                if meshes:
                    self.mesh = trimesh.util.concatenate(meshes)
                    logger.info(f"Combined mesh: {len(self.mesh.vertices):,} vertices, {len(self.mesh.faces):,} faces")
                    # Check if colors were preserved
                    if hasattr(self.mesh, 'visual'):
                        if hasattr(self.mesh.visual, 'face_colors') and self.mesh.visual.face_colors is not None:
                            if len(self.mesh.visual.face_colors) > 0:
                                logger.info(f"✓ Colors preserved in combined mesh: {len(self.mesh.visual.face_colors)} face colors")
                else:
                    raise ValueError("No meshes found in scene")
            elif isinstance(loaded, trimesh.Trimesh):
                self.mesh = loaded
                self.scene = None
                logger.info(f"Single mesh: {len(self.mesh.vertices):,} vertices, {len(self.mesh.faces):,} faces")
            else:
                raise ValueError(f"Unexpected loaded type: {type(loaded)}")
            
            logger.info(f"MESH LOADED: {len(self.mesh.vertices):,} vertices, {len(self.mesh.faces):,} faces")
            
            # Extract and apply colors from GLB materials
            self._extract_and_apply_colors()
            
        except Exception as e:
            logger.error(f"Failed to load GLB mesh: {e}", exc_info=True)
            return self._fallback_import()
        
        # Extract building from MESH GEOMETRY
        building = self._extract_building_from_mesh()
        
        if building and building.get_total_windows() > 0:
            logger.info(f"Building import complete: {building.name} - {building.get_total_windows()} window(s)")
            return [building]
        else:
            logger.warning("No windows extracted from mesh, using fallback")
            return self._fallback_import()
    
    def _extract_building_from_mesh(self) -> Optional[Building]:
        """Extract building structure by analyzing MESH GEOMETRY directly."""
        if self.mesh is None or len(self.mesh.vertices) == 0:
            logger.error("No mesh available for extraction")
            return None
        
        logger.info("=" * 80)
        logger.info("EXTRACTING BUILDING FROM MESH GEOMETRY")
        logger.info(f"Mesh stats: {len(self.mesh.vertices):,} vertices, {len(self.mesh.faces):,} faces")
        logger.info("=" * 80)
        
        # Extract building name from filename
        file_name = self.file_path.stem
        building_id = f"Building_{file_name}"
        building_name = file_name.replace('_', ' ')
        
        building = Building(
            id=building_id,
            name=building_name,
            location=(55.7558, 37.6173),  # Default to Moscow
            properties={}
        )
        
        # SKIP room extraction - we only need windows
        logger.info("Skipping room extraction - focusing only on window extraction")
        
        # Extract windows from mesh geometry
        # SMART EXTRACTION: Extract from individual geometries with window names first
        logger.info("Extracting windows from mesh geometry...")
        all_windows = []
        
        # Method 1: Extract from named geometries (fastest and most accurate)
        if self.scene and isinstance(self.scene, trimesh.Scene):
            logger.info("Method 1: Extracting windows from named geometries...")
            window_geometries = self._extract_windows_from_named_geometries()
            all_windows.extend(window_geometries)
            logger.info(f"Found {len(window_geometries)} window(s) from named geometries")
            
            # Method 1.5: Also scan ALL geometries (not just named ones) for window-like shapes
            logger.info("Method 1.5: Scanning ALL geometries for window-like shapes...")
            all_geometry_windows = self._extract_windows_from_all_geometries()
            for geom_window in all_geometry_windows:
                if not self._is_duplicate_window(geom_window, all_windows, tolerance=0.3):
                    all_windows.append(geom_window)
            logger.info(f"Found {len(all_geometry_windows)} additional window(s) from all geometries")
        
        # Method 2: COMPREHENSIVE mesh analysis - scan ALL faces systematically
        logger.info("Method 2: Comprehensive mesh analysis - scanning ALL faces and vertices...")
        mesh_windows = self._extract_windows_from_mesh_comprehensive()
        # Remove duplicates from mesh analysis
        for mesh_window in mesh_windows:
            if not self._is_duplicate_window(mesh_window, all_windows, tolerance=0.3):
                all_windows.append(mesh_window)
        logger.info(f"Found {len(mesh_windows)} window candidate(s) from comprehensive mesh analysis, {len([w for w in mesh_windows if not self._is_duplicate_window(w, window_geometries, tolerance=0.3)])} unique")
        
        logger.info(f"Total windows extracted: {len(all_windows)}")
        
        # Add all windows directly to building (no rooms)
        for window in all_windows:
            building.add_window(window)
        
        logger.info(f"Added {len(all_windows)} window(s) directly to building")
        
        return building
    
    def _extract_rooms_from_mesh(self):  # Unused - kept for compatibility
        """
        Extract rooms by analyzing MESH GEOMETRY directly.
        Analyzes vertices and faces to identify spatial regions (rooms).
        """
        rooms = []
        
        if self.mesh is None or len(self.mesh.vertices) == 0:
            logger.warning("No mesh available for room extraction")
            return rooms
        
        logger.info(f"Analyzing mesh for rooms: {len(self.mesh.vertices):,} vertices, {len(self.mesh.faces):,} faces")
        
        # Method 1: Split mesh into connected components (separate rooms/spaces)
        # Skip for very large meshes (too slow)
        LARGE_MESH_THRESHOLD = 1_000_000  # 1M vertices
        if len(self.mesh.vertices) < LARGE_MESH_THRESHOLD:
            try:
                logger.info("Method 1: Splitting mesh into connected components...")
                components = self.mesh.split(only_watertight=False)
                logger.info(f"Found {len(components)} connected component(s)")
                
                if len(components) > 1:
                    # Each component could be a room or part of building
                    for i, component in enumerate(components):
                        if len(component.vertices) < 100:  # Skip very small components
                            continue
                        
                        # Create room from component
                        room = self._create_room_from_mesh_component(component, i)
                        if room:
                            rooms.append(room)
                            logger.info(f"Created room from component {i}: {room.name} ({len(component.vertices):,} vertices)")
            except Exception as e:
                logger.warning(f"Failed to split mesh into components: {e}")
        else:
            logger.info(f"Mesh too large ({len(self.mesh.vertices):,} vertices) - skipping component split, using entire mesh as single room")
        
        # Method 2: If no rooms found, analyze spatial regions
        if len(rooms) == 0:
            logger.info("Method 2: Analyzing spatial regions...")
            # Get mesh bounds
            bounds = self.mesh.bounds
            min_bounds = bounds[0]
            max_bounds = bounds[1]
            
            # Calculate dimensions
            depth = abs(max_bounds[0] - min_bounds[0])
            width = abs(max_bounds[1] - min_bounds[1])
            height = abs(max_bounds[2] - min_bounds[2])
            
            # Create default room from entire mesh (UNUSED - room extraction disabled)
            # Room extraction is disabled - this method is kept for compatibility only
            logger.info("Room extraction disabled - skipping room creation")
        
        return rooms
    
    def _create_room_from_mesh_component(self, mesh: trimesh.Trimesh, index: int):  # Unused - kept for compatibility
        """Create a Room object from a mesh component."""
        if len(mesh.vertices) == 0:
            return None
        
        bounds = mesh.bounds
        min_bounds = bounds[0]
        max_bounds = bounds[1]
        
        depth = abs(max_bounds[0] - min_bounds[0])
        width = abs(max_bounds[1] - min_bounds[1])
        height = abs(max_bounds[2] - min_bounds[2])
        
        # Use reasonable defaults if dimensions are too small
        if depth < 0.1:
            depth = 5.0
        if width < 0.1:
            width = 4.0
        if height < 0.1:
            height = 3.0
        
        floor_area = depth * width
        
        # Room extraction is disabled - this method is kept for compatibility only
        return None
    
    def _extract_windows_from_named_geometries(self) -> List[Window]:
        """
        Extract windows from individual geometries with window-related names.
        This is MUCH faster than analyzing the entire combined mesh.
        Looks for geometries with names containing window keywords.
        """
        windows = []
        
        if not self.scene or not isinstance(self.scene, trimesh.Scene):
            return windows
        
        # Window name patterns (Russian and English)
        window_patterns = [
            'витраж',  # stained glass/window
            'окно',    # window
            'window',
            'win',
            'оп-',     # ОП-24, ОП-15 (window types)
            'в-',      # В-2 (window type)
            'glazing',
            'glass'
        ]
        
        logger.info(f"Scanning {len(self.scene.geometry)} geometry object(s) for windows...")
        
        window_count = 0
        for key, geometry in self.scene.geometry.items():
            if not isinstance(geometry, trimesh.Trimesh):
                continue
            
            key_str = str(key).lower()
            
            # Check if geometry name suggests it's a window
            is_window_geometry = False
            for pattern in window_patterns:
                if pattern in key_str:
                    is_window_geometry = True
                    break
            
            if is_window_geometry:
                window_count += 1
                logger.info(f"  Found window geometry: '{key}' ({len(geometry.vertices)} vertices, {len(geometry.faces)} faces)")
                
                # Extract window from this geometry
                window = self._create_window_from_geometry_mesh(geometry, str(key))
                if window:
                    windows.append(window)
                    logger.info(f"    Extracted window: {window.id} (size: {window.size}, center: {window.center})")
        
        logger.info(f"Scanned {len(self.scene.geometry)} geometries, found {window_count} window geometry object(s), extracted {len(windows)} window(s)")
        return windows
    
    def _extract_windows_from_all_geometries(self) -> List[Window]:
        """
        Scan ALL geometries (not just named ones) for window-like shapes.
        Uses relaxed geometric criteria to find windows that might not have window-related names.
        """
        windows = []
        
        if not self.scene or not isinstance(self.scene, trimesh.Scene):
            return windows
        
        logger.info(f"Scanning ALL {len(self.scene.geometry)} geometries for window-like shapes...")
        
        window_count = 0
        for key, geometry in self.scene.geometry.items():
            if not isinstance(geometry, trimesh.Trimesh):
                continue
            
            if len(geometry.vertices) == 0:
                continue
            
            # Analyze geometry for window-like characteristics
            bounds = geometry.bounds
            size_x = abs(bounds[1][0] - bounds[0][0])
            size_y = abs(bounds[1][1] - bounds[0][1])
            size_z = abs(bounds[1][2] - bounds[0][2])
            
            dimensions = sorted([size_x, size_y, size_z])
            thickness = dimensions[0]
            width = dimensions[1]
            height = dimensions[2]
            max_dimension = max(size_x, size_y, size_z)
            
            # RELAXED criteria for window detection
            is_window_like = False
            
            # Criterion 1: Flat shape (thickness << width/height)
            if thickness < 0.8 and (thickness / max(width, 0.1)) < 0.5:
                # Reasonable size (0.1m - 12m)
                if 0.1 <= width <= 12.0 and 0.1 <= height <= 10.0:
                    is_window_like = True
            
            # Criterion 2: Small geometry (likely not a wall/floor)
            if max_dimension < 4.0 and width > 0.05 and height > 0.05:
                is_window_like = True
            
            # Criterion 3: Very small geometry (could be window frame or detail)
            if max_dimension < 2.0 and len(geometry.faces) < 100:
                is_window_like = True
            
            if is_window_like:
                window_count += 1
                window = self._create_window_from_geometry_mesh(geometry, str(key))
                if window:
                    windows.append(window)
                    if window_count % 50 == 0:
                        logger.info(f"  Found {window_count} window-like geometry object(s) so far...")
        
        logger.info(f"Scanned {len(self.scene.geometry)} geometries, found {window_count} window-like object(s), extracted {len(windows)} window(s)")
        return windows
    
    def _create_window_from_geometry_mesh(self, mesh: trimesh.Trimesh, geometry_name: str) -> Optional[Window]:
        """Create a Window object from a geometry mesh."""
        if len(mesh.vertices) == 0:
            return None
        
        try:
            # Calculate window size from mesh bounds
            bounds = mesh.bounds
            size_x = abs(bounds[1][0] - bounds[0][0])
            size_y = abs(bounds[1][1] - bounds[0][1])
            size_z = abs(bounds[1][2] - bounds[0][2])
            
            # Windows are typically flat (one dimension is much smaller)
            dimensions = sorted([size_x, size_y, size_z])
            thickness = dimensions[0]  # Smallest dimension (window thickness)
            
            # Width and height are the two larger dimensions
            if size_z == thickness:
                window_width = max(size_x, size_y)
                window_height = min(size_x, size_y)
            elif size_y == thickness:
                window_width = max(size_x, size_z)
                window_height = min(size_x, size_z)
            else:
                window_width = max(size_y, size_z)
                window_height = min(size_y, size_z)
            
            # Use reasonable defaults if dimensions are too small
            if window_width < 0.1:
                window_width = 1.5
            if window_height < 0.1:
                window_height = 1.2
            
            # Calculate center from mesh centroid
            center = mesh.centroid
            center = tuple(center[:3]) if len(center) >= 3 else (0.0, 0.0, 1.5)
            
            # Calculate normal from mesh face normals
            if len(mesh.faces) > 0:
                face_normals = mesh.face_normals
                face_areas = mesh.area_faces
                if len(face_areas) > 0:
                    # Check if weights sum to non-zero before using weighted average
                    total_area = np.sum(face_areas)
                    if total_area > 1e-10:  # Check if weights sum to non-zero
                        weighted_normal = np.average(face_normals, axis=0, weights=face_areas)
                    else:
                        # Fallback to unweighted average if all areas are zero
                        weighted_normal = np.mean(face_normals, axis=0)
                    
                    norm = np.linalg.norm(weighted_normal)
                    if norm > 1e-10:  # Avoid division by zero
                        normal = tuple(weighted_normal / norm)
                    else:
                        # Fallback to first face normal if weighted normal is zero
                        normal = tuple(face_normals[0] if len(face_normals) > 0 else (0.0, 1.0, 0.0))
                else:
                    normal = tuple(face_normals[0] if len(face_normals) > 0 else (0.0, 1.0, 0.0))
            else:
                normal = (0.0, 1.0, 0.0)
            
            # Ensure normal is unit vector (safety check)
            normal_array = np.array(normal)
            norm = np.linalg.norm(normal_array)
            if norm > 1e-10:  # Avoid division by zero
                normal = tuple(normal_array / norm)
            else:
                # Fallback to default normal if calculation failed
                normal = (0.0, 1.0, 0.0)
            
            # Clean geometry name for window ID
            window_id = geometry_name.split('<')[0] if '<' in geometry_name else geometry_name
            window_id = window_id.strip().replace(' ', '_')
            
            window = Window(
                id=window_id,
                center=center,
                normal=normal,
                size=(float(window_width), float(window_height)),
                window_type='double_glazed',
                transmittance=0.75,
                frame_factor=0.70
            )
            
            return window
        except Exception as e:
            logger.warning(f"Error creating window from geometry '{geometry_name}': {e}")
            return None
    
    def _extract_windows_from_mesh(self) -> List[Window]:
        """
        Extract windows by analyzing MESH GEOMETRY directly.
        Scans all faces and vertices to identify window-like geometry.
        """
        windows = []
        
        if self.mesh is None or len(self.mesh.vertices) == 0:
            logger.warning("No mesh available for window extraction")
            return windows
        
        logger.info(f"Analyzing mesh for windows: {len(self.mesh.vertices):,} vertices, {len(self.mesh.faces):,} faces")
        
        # Method 1: Find flat surfaces (windows are typically flat)
        logger.info("Method 1: Finding flat surfaces (potential windows)...")
        flat_surfaces = self._find_flat_surfaces()
        logger.info(f"Found {len(flat_surfaces)} flat surface(s)")
        
        for surface in flat_surfaces:
            window = self._surface_to_window(surface)
            if window:
                windows.append(window)
                logger.info(f"Window from flat surface: {window.id} (size: {window.size})")
        
        # Method 2: Find openings/holes in mesh
        logger.info("Method 2: Finding openings/holes (potential windows)...")
        openings = self._find_openings()
        logger.info(f"Found {len(openings)} opening(s)")
        
        for opening in openings:
            window = self._opening_to_window(opening)
            if window:
                # Check for duplicates
                if not self._is_duplicate_window(window, windows, tolerance=0.5):
                    windows.append(window)
                    logger.info(f"Window from opening: {window.id} (size: {window.size})")
        
        # Method 3: Analyze face clusters (group faces by normal and position)
        logger.info("Method 3: Analyzing face clusters...")
        face_clusters = self._find_face_clusters()
        logger.info(f"Found {len(face_clusters)} face cluster(s)")
        
        for cluster in face_clusters:
            window = self._cluster_to_window(cluster)
            if window:
                if not self._is_duplicate_window(window, windows, tolerance=0.5):
                    windows.append(window)
                    logger.info(f"Window from cluster: {window.id} (size: {window.size})")
        
        logger.info(f"Total windows extracted from mesh: {len(windows)}")
        return windows
    
    def _extract_windows_from_mesh_comprehensive(self) -> List[Window]:
        """
        COMPREHENSIVE window extraction - scans ALL faces systematically.
        Uses spatial hashing and relaxed criteria to find ALL windows.
        """
        windows = []
        
        if self.mesh is None or len(self.mesh.vertices) == 0:
            logger.warning("No mesh available for comprehensive window extraction")
            return windows
        
        total_faces = len(self.mesh.faces)
        total_vertices = len(self.mesh.vertices)
        logger.info(f"COMPREHENSIVE SCAN: Analyzing {total_faces:,} faces, {total_vertices:,} vertices for windows...")
        
        # Get face data
        face_normals = self.mesh.face_normals
        face_centers = self.mesh.triangles_center
        face_areas = self.mesh.area_faces if hasattr(self.mesh, 'area_faces') else np.ones(len(self.mesh.faces))
        
        # Use spatial hashing for efficient clustering
        # Group faces by spatial grid cells and similar normals
        grid_size = 0.5  # 50cm grid cells
        spatial_grid = {}  # (grid_x, grid_y, grid_z, normal_bin) -> list of face indices
        
        logger.info("Step 1: Building spatial hash grid...")
        for i in range(total_faces):
            if i % 10000 == 0 and i > 0:
                logger.info(f"  Processed {i:,}/{total_faces:,} faces ({i*100/total_faces:.1f}%)...")
            
            center = face_centers[i]
            normal = face_normals[i]
            
            # Quantize position to grid
            grid_x = int(center[0] / grid_size)
            grid_y = int(center[1] / grid_size)
            grid_z = int(center[2] / grid_size)
            
            # Quantize normal to 26 directions (more fine-grained for better clustering)
            # Round to nearest 0.5 to get 26 directions (3^3 - 1 = 26)
            normal_rounded = np.round(normal * 2) / 2
            normal_bin = tuple(normal_rounded)
            
            key = (grid_x, grid_y, grid_z, normal_bin)
            if key not in spatial_grid:
                spatial_grid[key] = []
            spatial_grid[key].append(i)
        
        logger.info(f"Step 1 complete: Created {len(spatial_grid)} spatial grid cells")
        
        # Step 2: Analyze each grid cell for window-like clusters
        logger.info("Step 2: Analyzing grid cells for window clusters...")
        processed_faces = set()
        window_clusters = []
        
        total_grid_cells = len(spatial_grid)
        batch_size = max(1000, total_grid_cells // 50)  # Process in batches of ~2% or 1000 cells
        batch_items = []
        batch_num = 0
        
        for cell_idx, (grid_key, face_indices) in enumerate(spatial_grid.items()):
            batch_items.append((grid_key, face_indices))
            
            # Process batch when full
            if len(batch_items) >= batch_size:
                batch_num += 1
                clusters_before = len(window_clusters)
                
                # Process batch
                for grid_key_batch, face_indices_batch in batch_items:
                    if len(face_indices_batch) < 2:  # Need at least 2 faces for a cluster
                        continue
                    
                    # Check if already processed
                    if any(i in processed_faces for i in face_indices_batch):
                        continue
                    
                    # Get face data for this cell
                    cell_centers = face_centers[face_indices_batch]
                    cell_normals = face_normals[face_indices_batch]
                    cell_areas = face_areas[face_indices_batch]
                    
                    # Calculate cluster bounds
                    min_center = np.min(cell_centers, axis=0)
                    max_center = np.max(cell_centers, axis=0)
                    size = max_center - min_center
                    
                    # Calculate average normal (handle zero weights)
                    total_area = np.sum(cell_areas)
                    if total_area > 1e-10:  # Check if weights sum to non-zero
                        weighted_normal = np.average(cell_normals, axis=0, weights=cell_areas)
                    else:
                        # Fallback to unweighted average if all areas are zero
                        weighted_normal = np.mean(cell_normals, axis=0)
                    
                    norm = np.linalg.norm(weighted_normal)
                    if norm > 1e-10:
                        avg_normal = weighted_normal / norm
                    else:
                        # Fallback to first normal if weighted normal is zero
                        avg_normal = cell_normals[0] if len(cell_normals) > 0 else np.array([0.0, 1.0, 0.0])
                        norm_fallback = np.linalg.norm(avg_normal)
                        if norm_fallback > 1e-10:
                            avg_normal = avg_normal / norm_fallback
                        else:
                            # Final fallback to default normal
                            avg_normal = np.array([0.0, 1.0, 0.0])
                    
                    # RELAXED criteria for window detection
                    max_dim = np.max(size)
                    min_dim = np.min(size[size > 0.01]) if len(size[size > 0.01]) > 0 else max_dim
                    thickness_estimate = min_dim
                    
                    # Check if this could be a window
                    is_window_candidate = False
                    
                    # Criterion 1: Flat surface (thickness << width/height)
                    if max_dim > 0.1 and thickness_estimate < 0.8 and (thickness_estimate / max_dim) < 0.5:
                        is_window_candidate = True
                    
                    # Criterion 2: Reasonable size (0.1m - 10m)
                    if 0.1 <= max_dim <= 10.0:
                        is_window_candidate = True
                    
                    # Criterion 3: Small cluster (likely not a wall/floor)
                    if max_dim < 5.0 and len(face_indices_batch) < 500:
                        is_window_candidate = True
                    
                    if is_window_candidate:
                        # Mark faces as processed
                        processed_faces.update(face_indices_batch)
                        
                        window_clusters.append({
                            'faces': face_indices_batch,
                            'center': np.mean(cell_centers, axis=0),
                            'normal': avg_normal,
                            'size': size,
                            'bounds': (min_center, max_center)
                        })
                
                # Log batch completion
                clusters_found = len(window_clusters) - clusters_before
                processed_count = batch_num * batch_size
                progress_pct = (processed_count / total_grid_cells) * 100 if total_grid_cells > 0 else 0
                logger.info(f"  Batch {batch_num}: Processed {processed_count:,}/{total_grid_cells:,} cells ({progress_pct:.1f}%) - Found {clusters_found} new cluster(s), Total: {len(window_clusters)}")
                
                batch_items = []
        
        # Process remaining items in final batch
        if batch_items:
            batch_num += 1
            clusters_before = len(window_clusters)
            
            for grid_key_batch, face_indices_batch in batch_items:
                if len(face_indices_batch) < 2:
                    continue
                
                if any(i in processed_faces for i in face_indices_batch):
                    continue
                
                cell_centers = face_centers[face_indices_batch]
                cell_normals = face_normals[face_indices_batch]
                cell_areas = face_areas[face_indices_batch]
                
                min_center = np.min(cell_centers, axis=0)
                max_center = np.max(cell_centers, axis=0)
                size = max_center - min_center
                
                # Calculate average normal (handle zero weights)
                total_area = np.sum(cell_areas)
                if total_area > 1e-10:  # Check if weights sum to non-zero
                    weighted_normal = np.average(cell_normals, axis=0, weights=cell_areas)
                else:
                    # Fallback to unweighted average if all areas are zero
                    weighted_normal = np.mean(cell_normals, axis=0)
                
                norm = np.linalg.norm(weighted_normal)
                if norm > 1e-10:
                    avg_normal = weighted_normal / norm
                else:
                    # Fallback to first normal if weighted normal is zero
                    avg_normal = cell_normals[0] if len(cell_normals) > 0 else np.array([0.0, 1.0, 0.0])
                    norm_fallback = np.linalg.norm(avg_normal)
                    if norm_fallback > 1e-10:
                        avg_normal = avg_normal / norm_fallback
                    else:
                        # Final fallback to default normal
                        avg_normal = np.array([0.0, 1.0, 0.0])
                
                max_dim = np.max(size)
                min_dim = np.min(size[size > 0.01]) if len(size[size > 0.01]) > 0 else max_dim
                thickness_estimate = min_dim
                
                is_window_candidate = False
                if max_dim > 0.1 and thickness_estimate < 0.8 and (thickness_estimate / max_dim) < 0.5:
                    is_window_candidate = True
                if 0.1 <= max_dim <= 10.0:
                    is_window_candidate = True
                if max_dim < 5.0 and len(face_indices_batch) < 500:
                    is_window_candidate = True
                
                if is_window_candidate:
                    processed_faces.update(face_indices_batch)
                    window_clusters.append({
                        'faces': face_indices_batch,
                        'center': np.mean(cell_centers, axis=0),
                        'normal': avg_normal,
                        'size': size,
                        'bounds': (min_center, max_center)
                    })
            
            clusters_found = len(window_clusters) - clusters_before
            logger.info(f"  Batch {batch_num} (final): Processed {total_grid_cells:,}/{total_grid_cells:,} cells (100.0%) - Found {clusters_found} new cluster(s), Total: {len(window_clusters)}")
        
        logger.info(f"Step 2 complete: Found {len(window_clusters)} window cluster(s)")
        
        # Step 2.5: Merge nearby clusters that might be the same window
        logger.info(f"Step 2.5: Merging nearby clusters ({len(window_clusters)} clusters)...")
        
        # Use spatial indexing to speed up merging (only check nearby clusters, not all)
        logger.info("  Building spatial index for fast merging...")
        merge_grid_size = 1.0  # 1m grid cells
        merge_spatial_grid = {}
        for i, cluster in enumerate(window_clusters):
            center = cluster['center']
            grid_x = int(center[0] / merge_grid_size)
            grid_y = int(center[1] / merge_grid_size)
            grid_z = int(center[2] / merge_grid_size)
            
            # Add to grid cell and neighboring cells (3x3x3 = 27 cells)
            for dx in [-1, 0, 1]:
                for dy in [-1, 0, 1]:
                    for dz in [-1, 0, 1]:
                        key = (grid_x + dx, grid_y + dy, grid_z + dz)
                        if key not in merge_spatial_grid:
                            merge_spatial_grid[key] = []
                        merge_spatial_grid[key].append(i)
        
        logger.info(f"  Spatial index built: {len(merge_spatial_grid)} grid cells")
        
        merged_clusters = []
        cluster_processed = set()
        
        total_clusters = len(window_clusters)
        batch_size = max(100, total_clusters // 50)  # Process in batches of ~2% or 100 clusters
        batch_num = 0
        batch_start_idx = 0
        
        for i, cluster1 in enumerate(window_clusters):
            if i in cluster_processed:
                continue
            
            merged = cluster1.copy()
            merged_faces = set(cluster1['faces'])
            cluster_processed.add(i)
            
            # Only check clusters in nearby grid cells (much faster than checking all)
            center1 = cluster1['center']
            grid_x = int(center1[0] / merge_grid_size)
            grid_y = int(center1[1] / merge_grid_size)
            grid_z = int(center1[2] / merge_grid_size)
            
            # Get candidate clusters from nearby grid cells
            candidates = set()
            for dx in [-1, 0, 1]:
                for dy in [-1, 0, 1]:
                    for dz in [-1, 0, 1]:
                        key = (grid_x + dx, grid_y + dy, grid_z + dz)
                        if key in merge_spatial_grid:
                            candidates.update(merge_spatial_grid[key])
            
            # Check only candidate clusters (not all clusters)
            for j in candidates:
                if j <= i or j in cluster_processed:
                    continue
                
                cluster2 = window_clusters[j]
                
                # Check if clusters are close (within 0.5m)
                dist = np.linalg.norm(cluster1['center'] - cluster2['center'])
                if dist < 0.5:
                    # Check if normals are similar
                    normal_sim = np.dot(cluster1['normal'], cluster2['normal'])
                    if normal_sim > 0.7:  # Similar orientation
                        # Merge clusters
                        merged_faces.update(cluster2['faces'])
                        cluster_processed.add(j)
            
            # Update merged cluster
            if len(merged_faces) > len(cluster1['faces']):
                # Recalculate bounds and center
                merged_centers = face_centers[list(merged_faces)]
                merged_normals = face_normals[list(merged_faces)]
                merged_areas = face_areas[list(merged_faces)]
                
                merged['faces'] = list(merged_faces)
                merged['center'] = np.mean(merged_centers, axis=0)
                
                # Calculate average normal (handle zero weights)
                total_area = np.sum(merged_areas)
                if total_area > 1e-10:  # Check if weights sum to non-zero
                    weighted_normal = np.average(merged_normals, axis=0, weights=merged_areas)
                else:
                    # Fallback to unweighted average if all areas are zero
                    weighted_normal = np.mean(merged_normals, axis=0)
                
                norm = np.linalg.norm(weighted_normal)
                if norm > 1e-10:
                    merged['normal'] = weighted_normal / norm
                else:
                    # Fallback to first normal if weighted normal is zero
                    merged['normal'] = merged_normals[0] if len(merged_normals) > 0 else np.array([0.0, 1.0, 0.0])
                    merged['normal'] = merged['normal'] / np.linalg.norm(merged['normal'])
                min_center = np.min(merged_centers, axis=0)
                max_center = np.max(merged_centers, axis=0)
                merged['size'] = max_center - min_center
                merged['bounds'] = (min_center, max_center)
            
            merged_clusters.append(merged)
            
            # Log after each batch
            if (i + 1) % batch_size == 0:
                batch_num += 1
                progress_pct = ((i + 1) / total_clusters) * 100 if total_clusters > 0 else 0
                processed_in_batch = (i + 1) - batch_start_idx
                logger.info(f"  Batch {batch_num}: Processed {i + 1:,}/{total_clusters:,} clusters ({progress_pct:.1f}%) - {processed_in_batch} in this batch, {len(merged_clusters)} merged total...")
                batch_start_idx = i + 1
        
        # Log final batch if there are remaining items
        if (i + 1) % batch_size != 0:
            batch_num += 1
            processed_in_batch = (i + 1) - batch_start_idx
            logger.info(f"  Batch {batch_num} (final): Processed {total_clusters:,}/{total_clusters:,} clusters (100.0%) - {processed_in_batch} in this batch, {len(merged_clusters)} total merged")
        
        logger.info(f"Step 2.5 complete: Merged to {len(merged_clusters)} cluster(s) (from {len(window_clusters)})")
        window_clusters = merged_clusters
        
        # Step 3: Convert clusters to windows
        logger.info(f"Step 3: Converting {len(window_clusters)} cluster(s) to windows...")
        total_clusters = len(window_clusters)
        batch_size = max(100, total_clusters // 20)  # Process in batches of ~5% or 100 clusters
        batch_num = 0
        
        for i, cluster in enumerate(window_clusters):
            window = self._cluster_to_window_comprehensive(cluster, i)
            if window:
                windows.append(window)
            
            # Log after each batch
            if (i + 1) % batch_size == 0:
                batch_num += 1
                progress_pct = ((i + 1) / total_clusters) * 100 if total_clusters > 0 else 0
                logger.info(f"  Batch {batch_num}: Processed {i + 1:,}/{total_clusters:,} clusters ({progress_pct:.1f}%) - {len(windows)} window(s) converted...")
        
        # Log final batch if there are remaining items
        if len(window_clusters) % batch_size != 0:
            batch_num += 1
            logger.info(f"  Batch {batch_num} (final): Processed {total_clusters:,}/{total_clusters:,} clusters (100.0%) - {len(windows)} total window(s) converted")
        
        logger.info(f"COMPREHENSIVE SCAN complete: Found {len(windows)} window(s) from {len(window_clusters)} cluster(s)")
        return windows
    
    def _cluster_to_window_comprehensive(self, cluster: Dict, index: int) -> Optional[Window]:
        """Convert a face cluster to a Window object (comprehensive version with relaxed criteria)."""
        try:
            center = cluster['center']
            normal = cluster['normal']
            size = cluster['size']
            
            # Normalize normal
            normal = normal / np.linalg.norm(normal)
            
            # Calculate width and height (two larger dimensions)
            dims = sorted(size[size > 0.01], reverse=True)
            if len(dims) >= 2:
                width = dims[0]
                height = dims[1]
            elif len(dims) == 1:
                width = dims[0]
                height = dims[0] * 0.8  # Assume 4:5 aspect ratio
            else:
                width = 1.0
                height = 1.2
            
            # VERY RELAXED size constraints (accept more windows)
            if width < 0.05:  # Too small (5cm minimum)
                return None
            if width > 15.0:  # Too large (15m maximum)
                return None
            if height < 0.05:
                return None
            if height > 12.0:
                return None
            
            window = Window(
                id=f"Window_mesh_{index}",
                center=tuple(center),
                normal=tuple(normal),
                size=(float(width), float(height)),
                window_type='double_glazed',
                transmittance=0.75,
                frame_factor=0.70
            )
            
            return window
        except Exception as e:
            logger.warning(f"Error converting cluster to window: {e}")
            return None
    
    def _find_flat_surfaces(self) -> List[Dict]:
        """Find flat surfaces in the mesh that could be windows."""
        surfaces = []
        
        if len(self.mesh.faces) == 0:
            return surfaces
        
        # Get face normals and centers
        face_normals = self.mesh.face_normals
        face_centers = self.mesh.triangles_center
        
        # Group faces by similar normal and position
        # Windows are typically vertical or horizontal flat surfaces
        tolerance = 0.1  # 10cm tolerance for grouping
        
        # Cluster faces by normal direction
        clusters = {}
        for i, (normal, center) in enumerate(zip(face_normals, face_centers)):
            # Round normal to nearest cardinal direction
            normal_rounded = np.round(normal, 1)
            key = tuple(normal_rounded)
            
            if key not in clusters:
                clusters[key] = []
            clusters[key].append((i, center, normal))
        
        # Analyze each cluster
        for key, faces in clusters.items():
            if len(faces) < 10:  # Skip very small clusters
                continue
            
            # Get bounding box of cluster
            centers = np.array([f[1] for f in faces])
            min_center = np.min(centers, axis=0)
            max_center = np.max(centers, axis=0)
            
            size = max_center - min_center
            max_dim = np.max(size)
            min_dim = np.min(size[size > 0.01])
            
            # Check if it's a flat surface (one dimension is much smaller)
            if max_dim > 0.2 and min_dim < 0.5:  # Flat surface
                surfaces.append({
                    'faces': [f[0] for f in faces],
                    'center': np.mean(centers, axis=0),
                    'normal': faces[0][2],
                    'size': size,
                    'bounds': (min_center, max_center)
                })
        
        return surfaces
    
    def _surface_to_window(self, surface: Dict) -> Optional[Window]:
        """Convert a flat surface to a Window object."""
        try:
            center = surface['center']
            normal = surface['normal']
            size = surface['size']
            
            # Calculate width and height (two larger dimensions)
            dims = sorted(size[size > 0.01], reverse=True)
            if len(dims) >= 2:
                width = dims[0]
                height = dims[1]
            else:
                width = max(size)
                height = min(size[size > 0.01]) if len(size[size > 0.01]) > 0 else width
            
            # Ensure reasonable size
            if width < 0.1 or width > 10.0:
                return None
            if height < 0.1 or height > 8.0:
                return None
            
            window = Window(
                id=f"Window_{len(surface['faces'])}",
                center=tuple(center),
                normal=tuple(normal / np.linalg.norm(normal)),
                size=(float(width), float(height)),
                window_type='double_glazed',
                transmittance=0.75,
                frame_factor=0.70
            )
            
            return window
        except Exception as e:
            logger.warning(f"Error converting surface to window: {e}")
            return None
    
    def _find_openings(self) -> List[Dict]:
        """Find openings/holes in the mesh that could be windows."""
        openings = []
        
        try:
            # Check if mesh has boundary edges (holes)
            if hasattr(self.mesh, 'edges_boundary'):
                boundary_edges = self.mesh.edges[self.mesh.edges_boundary]
                
                if len(boundary_edges) > 0:
                    # Group boundary edges into potential openings
                    # This is simplified - in practice, you'd use more sophisticated clustering
                    boundary_vertices = np.unique(boundary_edges.flatten())
                    boundary_points = self.mesh.vertices[boundary_vertices]
                    
                    # Find bounding box of boundary
                    min_point = np.min(boundary_points, axis=0)
                    max_point = np.max(boundary_points, axis=0)
                    size = max_point - min_point
                    
                    # Check if it's a reasonable window size
                    if 0.2 < np.max(size) < 5.0:
                        openings.append({
                            'center': np.mean(boundary_points, axis=0),
                            'size': size,
                            'points': boundary_points
                        })
        except Exception as e:
            logger.warning(f"Error finding openings: {e}")
        
        return openings
    
    def _opening_to_window(self, opening: Dict) -> Optional[Window]:
        """Convert an opening to a Window object."""
        try:
            center = opening['center']
            size = opening['size']
            
            # Calculate width and height
            dims = sorted(size[size > 0.01], reverse=True)
            if len(dims) >= 2:
                width = dims[0]
                height = dims[1]
            else:
                width = max(size)
                height = min(size[size > 0.01]) if len(size[size > 0.01]) > 0 else width
            
            # Default normal (outward facing)
            normal = (0.0, 1.0, 0.0)
            
            window = Window(
                id=f"Window_opening_{len(opening['points'])}",
                center=tuple(center),
                normal=normal,
                size=(float(width), float(height)),
                window_type='double_glazed',
                transmittance=0.75,
                frame_factor=0.70
            )
            
            return window
        except Exception as e:
            logger.warning(f"Error converting opening to window: {e}")
            return None
    
    def _find_face_clusters(self) -> List[Dict]:
        """Find clusters of faces that could represent windows."""
        clusters = []
        
        if len(self.mesh.faces) == 0:
            return clusters
        
        total_faces = len(self.mesh.faces)
        logger.info(f"Analyzing {total_faces:,} faces for clusters...")
        logger.info(f"  Starting analysis... (this may take a while for large meshes)")
        
        # Simple approach: group faces by spatial proximity and normal
        # This is a simplified version - in practice, you'd use more sophisticated clustering
        
        face_normals = self.mesh.face_normals
        face_centers = self.mesh.triangles_center
        
        # Group faces by similar position and normal
        tolerance = 0.5  # 50cm tolerance for clustering
        
        # Progress logging - log more frequently for large meshes
        # Log every 0.1% or every 10k faces, whichever is smaller
        log_interval = min(10000, max(1000, total_faces // 1000))  # Every 0.1% or 10k faces max
        last_logged = -1  # Start at -1 so first log happens immediately
        
        processed = set()
        logger.info(f"  Progress: 0/{total_faces:,} faces (0.0%) - Starting...")
        
        for i in range(total_faces):
            # Progress logging
            if i - last_logged >= log_interval:
                progress_pct = (i / total_faces) * 100
                logger.info(f"  Progress: {i:,}/{total_faces:,} faces ({progress_pct:.1f}%) - {len(clusters)} cluster(s) found, {len(processed):,} processed")
                last_logged = i
            
            if i in processed:
                continue
            
            cluster_faces = [i]
            processed.add(i)
            
            center_i = face_centers[i]
            normal_i = face_normals[i]
            
            # Find nearby faces with similar normals
            for j in range(i + 1, total_faces):
                if j in processed:
                    continue
                
                center_j = face_centers[j]
                normal_j = face_normals[j]
                
                # Check distance and normal similarity
                dist = np.linalg.norm(center_i - center_j)
                normal_sim = np.dot(normal_i, normal_j)
                
                if dist < tolerance and normal_sim > 0.7:  # Similar position and normal
                    cluster_faces.append(j)
                    processed.add(j)
            
            # If cluster is small and flat, it could be a window
            if len(cluster_faces) < 100:  # Small cluster
                cluster_centers = face_centers[cluster_faces]
                cluster_normals = face_normals[cluster_faces]
                
                min_center = np.min(cluster_centers, axis=0)
                max_center = np.max(cluster_centers, axis=0)
                size = max_center - min_center
                
                # Check if it's a reasonable window size
                if 0.2 < np.max(size) < 3.0:
                    clusters.append({
                        'faces': cluster_faces,
                        'center': np.mean(cluster_centers, axis=0),
                        'normal': np.mean(cluster_normals, axis=0),
                        'size': size
                    })
        
        logger.info(f"  Completed: {total_faces:,}/{total_faces:,} faces (100.0%) - {len(clusters)} total cluster(s) found")
        return clusters
    
    def _cluster_to_window(self, cluster: Dict) -> Optional[Window]:
        """Convert a face cluster to a Window object."""
        try:
            center = cluster['center']
            normal = cluster['normal']
            size = cluster['size']
            
            # Normalize normal
            normal = normal / np.linalg.norm(normal)
            
            # Calculate width and height
            dims = sorted(size[size > 0.01], reverse=True)
            if len(dims) >= 2:
                width = dims[0]
                height = dims[1]
            else:
                width = max(size)
                height = min(size[size > 0.01]) if len(size[size > 0.01]) > 0 else width
            
            window = Window(
                id=f"Window_cluster_{len(cluster['faces'])}",
                center=tuple(center),
                normal=tuple(normal),
                size=(float(width), float(height)),
                window_type='double_glazed',
                transmittance=0.75,
                frame_factor=0.70
            )
            
            return window
        except Exception as e:
            logger.warning(f"Error converting cluster to window: {e}")
            return None
    
    def _find_nearest_room_for_window(self, window: Window, rooms):  # Unused - kept for compatibility
        """Find the nearest room to a window based on spatial proximity."""
        if not rooms:
            return None
        
        window_center = np.array(window.center)
        min_distance = float('inf')
        nearest_room = None
        
        for room in rooms:
            # Get room bounds from geometry
            room_bounds = None
            if 'bounds' in room.geometry:
                room_bounds = np.array(room.geometry['bounds'])
            elif 'type' in room.geometry and room.geometry['type'] == 'mesh':
                # Estimate bounds from room dimensions
                room_center_est = np.array([room.depth/2, room.width/2, room.height/2])
                room_bounds = np.array([
                    room_center_est - np.array([room.depth/2, room.width/2, room.height/2]),
                    room_center_est + np.array([room.depth/2, room.width/2, room.height/2])
                ])
            
            if room_bounds is not None:
                distance = self._distance_to_bounds(window_center, room_bounds)
                if distance < min_distance:
                    min_distance = distance
                    nearest_room = room
        
        # If no room found by bounds, return first room
        return nearest_room if nearest_room else rooms[0] if rooms else None
    
    def _extract_building_from_scene(self) -> Optional[Building]:
        """Extract building structure from GLB scene graph."""
        if not self.gltf_data or not self.scene:
            return None
        
        # Extract metadata from glTF extensions (BIM data)
        metadata = self._extract_gltf_metadata()
        
        # Extract building name from filename, scene, metadata, or nodes
        file_name = self.file_path.stem
        building_id = f"Building_{file_name}"
        building_name = file_name.replace('_', ' ')
        
        # Use metadata if available
        if metadata.get('building_name'):
            building_name = metadata['building_name']
            building_id = f"Building_{building_name}"
            logger.info(f"Found building name from metadata: '{building_name}'")
        
        # Try to find building name in scene nodes
        if self.gltf_data.scenes and len(self.gltf_data.scenes) > 0:
            scene = self.gltf_data.scenes[0]
            logger.info(f"Scene name: '{scene.name}'")
            if scene.name and not metadata.get('building_name'):
                building_name = scene.name
                building_id = f"Building_{scene.name}"
        
        # Also check node names for building (including Russian)
        if self.gltf_data.nodes:
            for node in self.gltf_data.nodes[:20]:  # Check first 20 nodes
                if node.name:
                    name_lower = node.name.lower()
                    if any(pattern in name_lower for pattern in ['building', 'корпус', 'здание']):
                        if not metadata.get('building_name'):
                            building_name = node.name
                            building_id = f"Building_{node.name}"
                            logger.info(f"Found building name from node: '{node.name}'")
                        break
        
        logger.info(f"Creating building: {building_name} (ID: {building_id})")
        
        # Extract location from metadata if available
        location = (55.7558, 37.6173)  # Default to Moscow
        if metadata.get('location'):
            location = metadata['location']
            logger.info(f"Using location from metadata: {location}")
        
        building = Building(
            id=building_id,
            name=building_name,
            location=location,
            properties=metadata.get('properties', {})
        )
        
        # Build node hierarchy map
        node_map = self._build_node_map()
        
        # Extract rooms from scene graph
        rooms = self._extract_rooms_from_scene_graph(node_map)
        
        # Add rooms to building
        total_windows = 0
        for room in rooms:
            building.add_room(room)
            total_windows += len(room.windows)
            logger.info(f"Added room: {room.name} (floor {room.floor_number}, {len(room.windows)} windows)")
        
        # GLOBAL WINDOW EXTRACTION: Find ALL windows in the entire building
        # This catches windows that weren't associated with specific rooms
        logger.info("Starting GLOBAL window extraction to find ALL windows in building...")
        all_windows = self._extract_all_windows_global(node_map, rooms)
        logger.info(f"Global extraction found {len(all_windows)} total window(s) in building")
        
        # Associate global windows with nearest rooms
        for window in all_windows:
            # Find nearest room
            nearest_room = self._find_nearest_room(window, rooms)
            if nearest_room:
                # Check if window is already in room
                is_duplicate = False
                for existing_window in nearest_room.windows:
                    if self._is_duplicate_window(window, [existing_window], tolerance=0.5):
                        is_duplicate = True
                        break
                
                if not is_duplicate:
                    nearest_room.add_window(window)
                    logger.info(f"Associated global window {window.id} with room {nearest_room.name}")
        
        # Recalculate totals
        total_windows = sum(len(room.windows) for room in rooms)
        logger.info(f"Building import complete: {building.name} - {total_windows} window(s)")
        
        return building
    
    def _extract_gltf_metadata(self) -> Dict:
        """
        Extract BIM metadata from glTF extensions.
        Supports:
        - EXT_structural_metadata: Structural and property metadata
        - KHR_materials: Material properties
        - Custom extensions: Building information
        
        Returns:
            Dictionary with extracted metadata
        """
        metadata = {
            'building_name': None,
            'location': None,
            'properties': {},
            'materials': {},
            'extensions_used': []
        }
        
        if not self.gltf_data:
            return metadata
        
        # Check for extensions
        if hasattr(self.gltf_data, 'extensionsUsed') and self.gltf_data.extensionsUsed:
            metadata['extensions_used'] = list(self.gltf_data.extensionsUsed)
            logger.info(f"GLB extensions found: {', '.join(self.gltf_data.extensionsUsed)}")
        
        # Extract from EXT_structural_metadata extension
        if hasattr(self.gltf_data, 'extensions') and self.gltf_data.extensions:
            if 'EXT_structural_metadata' in self.gltf_data.extensions:
                try:
                    struct_meta = self.gltf_data.extensions['EXT_structural_metadata']
                    # Extract structural metadata
                    if 'schema' in struct_meta:
                        logger.info("Found EXT_structural_metadata schema")
                    if 'propertyTables' in struct_meta:
                        logger.info(f"Found {len(struct_meta.get('propertyTables', []))} property table(s)")
                except Exception as e:
                    logger.debug(f"Error extracting EXT_structural_metadata: {e}")
        
        # Extract from KHR_materials extension
        if hasattr(self.gltf_data, 'materials') and self.gltf_data.materials:
            for i, material in enumerate(self.gltf_data.materials):
                mat_name = material.name or f"Material_{i}"
                mat_props = {}
                
                # Extract material properties
                if hasattr(material, 'extensions') and material.extensions:
                    if 'KHR_materials_pbrMetallicRoughness' in material.extensions:
                        pbr = material.extensions['KHR_materials_pbrMetallicRoughness']
                        if 'baseColorFactor' in pbr:
                            mat_props['base_color'] = pbr['baseColorFactor']
                        if 'metallicFactor' in pbr:
                            mat_props['metallic'] = pbr['metallicFactor']
                        if 'roughnessFactor' in pbr:
                            mat_props['roughness'] = pbr['roughnessFactor']
                
                if mat_props:
                    metadata['materials'][mat_name] = mat_props
        
        # Extract from asset metadata
        if hasattr(self.gltf_data, 'asset') and self.gltf_data.asset:
            asset = self.gltf_data.asset
            if hasattr(asset, 'extras') and asset.extras:
                extras = asset.extras
                if 'building_name' in extras:
                    metadata['building_name'] = extras['building_name']
                if 'location' in extras:
                    location_data = extras['location']
                    if isinstance(location_data, (list, tuple)) and len(location_data) >= 2:
                        metadata['location'] = (float(location_data[0]), float(location_data[1]))
                if 'properties' in extras:
                    metadata['properties'].update(extras['properties'])
        
        # Extract from scene extras
        if self.gltf_data.scenes:
            for scene in self.gltf_data.scenes:
                if hasattr(scene, 'extras') and scene.extras:
                    extras = scene.extras
                    if 'building_name' in extras and not metadata['building_name']:
                        metadata['building_name'] = extras['building_name']
                    if 'location' in extras and not metadata['location']:
                        location_data = extras['location']
                        if isinstance(location_data, (list, tuple)) and len(location_data) >= 2:
                            metadata['location'] = (float(location_data[0]), float(location_data[1]))
                    if 'properties' in extras:
                        metadata['properties'].update(extras['properties'])
        
        if metadata['building_name'] or metadata['location'] or metadata['properties']:
            logger.info(f"Extracted metadata: building={metadata['building_name']}, location={metadata['location']}, "
                       f"properties={len(metadata['properties'])}")
        
        return metadata
    
    def _extract_and_apply_colors(self):
        """
        Extract colors from GLB materials and apply them to the mesh.
        This ensures the mesh displays with proper colors instead of default gray.
        """
        if self.mesh is None:
            return
        
        # Check if mesh already has colors
        has_colors = False
        if hasattr(self.mesh, 'visual'):
            if hasattr(self.mesh.visual, 'face_colors') and self.mesh.visual.face_colors is not None:
                if len(self.mesh.visual.face_colors) > 0:
                    has_colors = True
                    logger.info("Mesh already has face colors, keeping them")
            elif hasattr(self.mesh.visual, 'vertex_colors') and self.mesh.visual.vertex_colors is not None:
                if len(self.mesh.visual.vertex_colors) > 0:
                    has_colors = True
                    logger.info("Mesh already has vertex colors, keeping them")
        
        if has_colors:
            logger.info("Mesh already has colors - skipping material extraction")
            return
        
        # Try to extract colors from GLB materials
        if not PYGGLTF_AVAILABLE:
            logger.warning("pygltflib not available - cannot extract material colors")
            return
        
        try:
            logger.info("Extracting colors from GLB materials...")
            gltf_data = pygltflib.GLTF2.load(str(self.file_path.resolve()))
            
            # Extract material colors
            material_colors = {}
            if hasattr(gltf_data, 'materials') and gltf_data.materials:
                for i, material in enumerate(gltf_data.materials):
                    color = None
                    # Try to get base color from PBR material
                    if hasattr(material, 'pbrMetallicRoughness') and material.pbrMetallicRoughness:
                        pbr = material.pbrMetallicRoughness
                        if hasattr(pbr, 'baseColorFactor') and pbr.baseColorFactor:
                            # baseColorFactor is RGBA [0-1]
                            color = np.array(pbr.baseColorFactor[:3], dtype=np.float32)
                    # Try extensions
                    elif hasattr(material, 'extensions') and material.extensions:
                        if 'KHR_materials_pbrMetallicRoughness' in material.extensions:
                            pbr = material.extensions['KHR_materials_pbrMetallicRoughness']
                            if 'baseColorFactor' in pbr:
                                color = np.array(pbr['baseColorFactor'][:3], dtype=np.float32)
                    
                    if color is not None:
                        material_colors[i] = color
                        logger.info(f"Material {i} ({material.name or 'unnamed'}): color = {color}")
            
            if not material_colors:
                logger.warning("No material colors found in GLB file")
                return
            
            # Apply colors to mesh based on material assignments
            # Map materials to geometries using GLB node/mesh structure
            if self.scene and isinstance(self.scene, trimesh.Scene):
                logger.info("Applying colors to scene geometries based on GLB materials...")
                colors_applied = False
                
                # Build mapping: node -> mesh -> material
                node_mesh_material_map = {}
                if hasattr(gltf_data, 'nodes') and gltf_data.nodes:
                    for node_idx, node in enumerate(gltf_data.nodes):
                        if hasattr(node, 'mesh') and node.mesh is not None:
                            mesh_idx = node.mesh
                            # Get material from mesh primitives
                            if mesh_idx < len(gltf_data.meshes):
                                gltf_mesh = gltf_data.meshes[mesh_idx]
                                if hasattr(gltf_mesh, 'primitives') and gltf_mesh.primitives:
                                    for primitive in gltf_mesh.primitives:
                                        if hasattr(primitive, 'material') and primitive.material is not None:
                                            mat_idx = primitive.material
                                            node_mesh_material_map[node_idx] = (mesh_idx, mat_idx)
                                            break
                
                # Apply colors to geometries based on node names/indices
                geometry_colors = {}  # Map geometry key to color
                for node_idx, (mesh_idx, mat_idx) in node_mesh_material_map.items():
                    if mat_idx in material_colors:
                        color = material_colors[mat_idx]
                        # Try to find geometry by node name or index
                        node_name = None
                        if node_idx < len(gltf_data.nodes):
                            node = gltf_data.nodes[node_idx]
                            if hasattr(node, 'name') and node.name:
                                node_name = node.name
                        
                        # Match geometry by name or create mapping
                        for geom_key, geometry in self.scene.geometry.items():
                            if isinstance(geometry, trimesh.Trimesh):
                                # Match by name or use first available
                                if node_name and (node_name in str(geom_key) or str(geom_key) in node_name):
                                    geometry_colors[geom_key] = color
                                    logger.info(f"Mapped material {mat_idx} (color {color}) to geometry '{geom_key}' (node: {node_name})")
                                    break
                        
                        # If no match found, assign to first unmatched geometry
                        if node_name is None or node_name not in [str(k) for k in geometry_colors.keys()]:
                            for geom_key, geometry in self.scene.geometry.items():
                                if isinstance(geometry, trimesh.Trimesh) and geom_key not in geometry_colors:
                                    geometry_colors[geom_key] = color
                                    logger.info(f"Assigned material {mat_idx} (color {color}) to geometry '{geom_key}'")
                                    break
                
                # Apply colors to geometries
                for geom_key, color in geometry_colors.items():
                    geometry = self.scene.geometry.get(geom_key)
                    if isinstance(geometry, trimesh.Trimesh):
                        if not hasattr(geometry, 'visual'):
                            geometry.visual = trimesh.visual.ColorVisuals()
                        
                        # Convert color to uint8
                        color_uint8 = (color * 255).astype(np.uint8)
                        # Apply to all faces
                        face_count = len(geometry.faces)
                        face_colors = np.tile(
                            np.append(color_uint8, 255), 
                            (face_count, 1)
                        )
                        geometry.visual.face_colors = face_colors
                        colors_applied = True
                        logger.info(f"✓ Applied color {color} to geometry '{geom_key}' ({face_count} faces)")
                
                if colors_applied:
                    # Re-combine meshes with colors
                    meshes = []
                    for key, geometry in self.scene.geometry.items():
                        if isinstance(geometry, trimesh.Trimesh):
                            meshes.append(geometry)
                    
                    if meshes:
                        self.mesh = trimesh.util.concatenate(meshes)
                        logger.info(f"Re-combined mesh with colors: {len(self.mesh.vertices):,} vertices, {len(self.mesh.faces):,} faces")
                        # Check if colors were preserved
                        if hasattr(self.mesh, 'visual') and hasattr(self.mesh.visual, 'face_colors'):
                            if self.mesh.visual.face_colors is not None and len(self.mesh.visual.face_colors) > 0:
                                logger.info(f"✓ Colors successfully applied to combined mesh: {len(self.mesh.visual.face_colors)} face colors")
                            else:
                                logger.warning("⚠ Colors were not preserved when combining meshes")
                else:
                    # Fallback: apply first material color to entire mesh
                    if material_colors:
                        first_color = list(material_colors.values())[0]
                        color_uint8 = (first_color * 255).astype(np.uint8)
                        face_count = len(self.mesh.faces)
                        face_colors = np.tile(
                            np.append(color_uint8, 255),
                            (face_count, 1)
                        )
                        if not hasattr(self.mesh, 'visual'):
                            self.mesh.visual = trimesh.visual.ColorVisuals()
                        self.mesh.visual.face_colors = face_colors
                        logger.info(f"Applied fallback color {first_color} to entire mesh")
            
        except Exception as e:
            logger.warning(f"Failed to extract colors from GLB materials: {e}")
            logger.debug(f"Error details: {e}", exc_info=True)
    
    def _build_node_map(self) -> Dict[int, Dict]:
        """Build a map of node indices to node information."""
        node_map = {}
        
        if not self.gltf_data or not self.gltf_data.nodes:
            logger.warning("No nodes found in GLB file")
            return node_map
        
        logger.info(f"Found {len(self.gltf_data.nodes)} node(s) in GLB file")
        
        # Map scene geometry keys (which may contain node names) to meshes
        geometry_by_name = {}
        if isinstance(self.scene, trimesh.Scene):
            for key, geometry in self.scene.geometry.items():
                geometry_by_name[str(key)] = geometry
            logger.info(f"Scene has {len(geometry_by_name)} geometry object(s)")
        
        # Build node map from GLB structure
        for i, node in enumerate(self.gltf_data.nodes):
            node_name = node.name or f"Node_{i}"
            node_info = {
                'index': i,
                'name': node_name,
                'mesh_index': node.mesh if node.mesh is not None else None,
                'children': node.children or [],
                'translation': node.translation or [0, 0, 0],
                'rotation': node.rotation or [0, 0, 0, 1],
                'scale': node.scale or [1, 1, 1],
                'geometry': None
            }
            
            # Try to find geometry by node name or mesh index
            if node_name in geometry_by_name:
                node_info['geometry'] = geometry_by_name[node_name]
            elif node.mesh is not None:
                # Try to find by mesh index
                mesh_name = f"mesh_{node.mesh}"
                if mesh_name in geometry_by_name:
                    node_info['geometry'] = geometry_by_name[mesh_name]
                elif isinstance(self.scene, trimesh.Scene):
                    # Try to get from scene geometry by index
                    geometry_list = list(self.scene.geometry.values())
                    if node.mesh < len(geometry_list):
                        node_info['geometry'] = geometry_list[node.mesh]
            
            node_map[i] = node_info
            
            # Log first 20 nodes for debugging
            if i < 20:
                logger.info(f"Node {i}: name='{node_name}', mesh={node.mesh}, children={len(node.children) if node.children else 0}")
        
        if len(self.gltf_data.nodes) > 20:
            logger.info(f"... and {len(self.gltf_data.nodes) - 20} more nodes")
        
        return node_map
    
    def _extract_rooms_from_scene_graph(self, node_map: Dict[int, Dict]):  # Unused - kept for compatibility
        """Extract rooms from scene graph by analyzing node names and hierarchy."""
        rooms = []
        
        if not self.gltf_data or not self.gltf_data.scenes:
            logger.warning("No scenes found in GLB file")
            return rooms
        
        # Get root scene nodes
        scene = self.gltf_data.scenes[0]
        root_nodes = scene.nodes or []
        logger.info(f"Scene '{scene.name or 'unnamed'}' has {len(root_nodes)} root node(s)")
        
        if not root_nodes:
            logger.warning("No root nodes in scene")
            return rooms
        
        # Organize nodes by type (building, floor, apartment, room, window)
        organized_nodes = self._organize_nodes_by_type(node_map, root_nodes)
        
        # Log what was organized
        logger.info(f"Organized nodes: {len(organized_nodes['rooms'])} room(s), {len(organized_nodes['windows'])} window(s), "
                   f"{len(organized_nodes['floors'])} floor(s), {len(organized_nodes['apartments'])} apartment(s)")
        
        # Extract rooms from organized structure
        rooms = self._create_rooms_from_nodes(organized_nodes, node_map)
        
        logger.info(f"Extracted {len(rooms)} room(s) from scene graph")
        return rooms
    
    def _organize_nodes_by_type(self, node_map: Dict[int, Dict], root_nodes: List[int]) -> Dict:
        """Organize nodes into hierarchical structure based on names."""
        organized = {
            'building': None,
            'floors': {},
            'apartments': {},
            'rooms': {},
            'windows': {}
        }
        
        # Traverse scene graph
        current_room_id = None
        current_room_name = None
        
        def traverse_node(node_idx: int, parent_type: str = None, parent_id: str = None):
            nonlocal current_room_id, current_room_name
            
            if node_idx not in node_map:
                return
            
            node = node_map[node_idx]
            node_name = node['name']
            
            # Identify node type from name
            node_type, node_id = self._identify_node_type(node_name)
            
            # Log node identification for debugging (first 100 nodes)
            total_identified = len(organized['rooms']) + len(organized['windows']) + len(organized['floors']) + len(organized['apartments'])
            if total_identified < 100:
                if node_type not in ['unknown', 'container']:
                    logger.info(f"Node '{node_name}' -> type: {node_type}, id: {node_id}")
            
            # Skip container nodes (they're just organizational, not actual building elements)
            # But still traverse their children to find actual building elements
            if node_type == 'container':
                logger.debug(f"Skipping container node: '{node_name}', traversing {len(node['children'])} children")
                for child_idx in node['children']:
                    traverse_node(child_idx, parent_type, parent_id)
                return
            
            if node_type == 'building':
                organized['building'] = node_idx
            elif node_type == 'floor':
                floor_num = self._extract_floor_number(node_name)
                organized['floors'][floor_num] = {
                    'node_idx': node_idx,
                    'name': node_name,
                    'children': []
                }
            elif node_type == 'apartment':
                if parent_type == 'floor':
                    floor_num = self._extract_floor_number(parent_id) if parent_id else 1
                    if floor_num not in organized['apartments']:
                        organized['apartments'][floor_num] = {}
                    organized['apartments'][floor_num][node_id] = {
                        'node_idx': node_idx,
                        'name': node_name,
                        'children': []
                    }
            elif node_type == 'room':
                # Find parent floor/apartment
                floor_num = 1
                apartment_id = None
                if parent_type == 'apartment':
                    # Extract floor from parent
                    for fnum, apts in organized['apartments'].items():
                        if parent_id in apts:
                            floor_num = fnum
                            apartment_id = parent_id
                            break
                elif parent_type == 'floor':
                    floor_num = self._extract_floor_number(parent_id) if parent_id else 1
                
                room_id = node_id or f"Room_{len(organized['rooms'])}"
                organized['rooms'][room_id] = {
                    'node_idx': node_idx,
                    'name': node_name,
                    'floor_number': floor_num,
                    'apartment_id': apartment_id,
                    'children': []
                }
                # Update current room context for child windows
                current_room_id = room_id
                current_room_name = node_name
            elif node_type == 'window':
                # Windows are attached to rooms - use current room context or parent
                window_id = node_id or f"Window_{len(organized['windows'])}"
                parent_room = current_room_id or parent_id
                organized['windows'][window_id] = {
                    'node_idx': node_idx,
                    'name': node_name,
                    'parent_room': parent_room,
                    'parent_room_name': current_room_name
                }
            
            # Traverse children (preserve room context for nested windows)
            prev_room_id = current_room_id
            prev_room_name = current_room_name
            for child_idx in node['children']:
                traverse_node(child_idx, node_type, node_id or node_name)
            # Restore room context after traversing children
            current_room_id = prev_room_id
            current_room_name = prev_room_name
        
        # Start traversal from root nodes
        for root_idx in root_nodes:
            traverse_node(root_idx)
        
        return organized
    
    def _identify_node_type(self, node_name: str) -> Tuple[str, Optional[str]]:
        """Identify node type from name patterns."""
        if not node_name:
            return 'unknown', None
        
        name_lower = node_name.lower()
        
        # Skip container/group nodes (these are not actual building elements)
        if name_lower in ['floors', 'windows', 'doors', 'walls', 'columns', 'curtainwalls', 
                          'mechanicalequipment', 'genericmodel', 'этажи', 'окна', 'двери', 'стены']:
            return 'container', None
        
        # Building patterns (including Russian)
        if any(pattern in name_lower for pattern in ['building', 'корпус', 'здание']):
            return 'building', self._extract_id(node_name)
        
        # Floor patterns (but not container "Floors")
        if any(pattern in name_lower for pattern in ['floor', 'этаж', 'o_floor']):
            # Check if it's a specific floor (has a number) vs container
            if re.search(r'\d+', node_name):
                return 'floor', self._extract_id(node_name)
            else:
                return 'container', None
        
        # Apartment patterns
        if any(pattern in name_lower for pattern in ['apartment', 'квартира', 'premises']):
            return 'apartment', self._extract_id(node_name)
        
        # Room patterns (more specific)
        if any(pattern in name_lower for pattern in ['living room', 'kitchen', 'bedroom', 'bathroom', 
                                                     'npki', 'комната', 'гостиная', 'кухня', 'спальня']):
            return 'room', self._extract_id(node_name)
        # Also check for room-like patterns with numbers (e.g., "NPKI 202", "Living room 1288")
        if re.search(r'(npki|living|kitchen|room|комната)\s*\d+', name_lower):
            return 'room', self._extract_id(node_name)
        
        # Window patterns (but not container "Windows")
        if any(pattern in name_lower for pattern in ['window', 'окно']):
            # Check if it's a specific window (has a number) vs container
            if re.search(r'\d+', node_name) or 'window' in name_lower:
                return 'window', self._extract_id(node_name)
            else:
                return 'container', None
        
        return 'unknown', None
    
    def _extract_id(self, name: str) -> str:
        """Extract ID from node name."""
        # Try to extract number or ID
        match = re.search(r'(\d+)', name)
        if match:
            return match.group(1)
        return name.replace(' ', '_').replace('-', '_')
    
    def _extract_floor_number(self, name: str) -> int:
        """Extract floor number from name."""
        # Look for floor number patterns
        match = re.search(r'floor\s*(\d+)', name, re.IGNORECASE)
        if match:
            return int(match.group(1))
        
        # Look for "O_Floor 1" pattern
        match = re.search(r'o_floor\s*(\d+)', name, re.IGNORECASE)
        if match:
            return int(match.group(1))
        
        # Look for "Floor 9. Typical floor (9th-18th floors)" pattern
        match = re.search(r'floor\s*(\d+)', name, re.IGNORECASE)
        if match:
            return int(match.group(1))
        
        # Default to 1 if not found
        return 1
    
    def _create_rooms_from_nodes(self, organized_nodes: Dict, node_map: Dict[int, Dict]):  # Unused - kept for compatibility
        """Create Room objects from organized node structure."""
        rooms = []
        
        # Process each room node
        for room_id, room_info in organized_nodes['rooms'].items():
            node_idx = room_info['node_idx']
            node = node_map.get(node_idx)
            
            if not node:
                continue
            
            # Get geometry for this room
            mesh = node.get('geometry')
            
            # If no specific geometry found, try to find by room name
            if not mesh and isinstance(self.scene, trimesh.Scene):
                room_name = room_info['name']
                # Try to find geometry with matching name
                for key, geometry in self.scene.geometry.items():
                    if room_name.lower() in str(key).lower() or str(key).lower() in room_name.lower():
                        if isinstance(geometry, trimesh.Trimesh):
                            mesh = geometry
                            break
            
            # If no specific geometry, use bounding box from node translation
            if not mesh or not isinstance(mesh, trimesh.Trimesh):
                # Create room from node information
                room = self._create_room_from_node(room_info, node, organized_nodes, node_map)
            else:
                # Create room from mesh
                room = self._create_room_from_mesh(
                    mesh,
                    room_id=room_id,
                    room_name=room_info['name'],
                    building_id="Building_1",
                    floor_number=room_info.get('floor_number', 1)
                )
            
            # Add windows for this room
            windows = self._extract_windows_for_room(room_id, organized_nodes, node_map)
            for window in windows:
                room.add_window(window)
            
            rooms.append(room)
        
        return rooms
    
    def _create_room_from_node(self, room_info: Dict, node: Dict, organized_nodes: Dict, node_map: Dict):  # Unused - kept for compatibility
        """Create a Room object from node information when no mesh is available."""
        room_id = room_info.get('name', 'Room_1')
        room_name = room_info.get('name', 'Room')
        floor_number = room_info.get('floor_number', 1)
        
        # Use default dimensions
        depth = 5.0
        width = 4.0
        height = 3.0
        
        # Try to extract from translation/scale
        translation = node.get('translation', [0, 0, 0])
        scale = node.get('scale', [1, 1, 1])
        
        # Estimate dimensions from scale
        if scale and len(scale) >= 3:
            depth = abs(scale[0]) * 5.0 if abs(scale[0]) > 0.1 else 5.0
            width = abs(scale[1]) * 4.0 if abs(scale[1]) > 0.1 else 4.0
            height = abs(scale[2]) * 3.0 if abs(scale[2]) > 0.1 else 3.0
        
        floor_area = depth * width
        
        # Room extraction is disabled - this method is kept for compatibility only
        return None
    
    def _extract_windows_for_room(self, room_id: str, organized_nodes: Dict, node_map: Dict[int, Dict]) -> List[Window]:
        """Extract windows for a specific room using AGGRESSIVE geometry-based detection."""
        windows = []
        room_info = organized_nodes['rooms'].get(room_id, {})
        room_name = room_info.get('name', room_id)
        room_node_idx = room_info.get('node_idx')
        
        # Get room geometry for spatial matching
        room_geometry = None
        room_bounds = None
        room_center = None
        if room_node_idx and room_node_idx in node_map:
            room_node = node_map[room_node_idx]
            room_geometry = room_node.get('geometry')
            if room_geometry and isinstance(room_geometry, trimesh.Trimesh):
                room_bounds = room_geometry.bounds
                room_center = room_geometry.centroid
        
        # Method 1: Find windows from organized nodes (name-based)
        for window_id, window_info in organized_nodes['windows'].items():
            parent_room = window_info.get('parent_room')
            parent_room_name = window_info.get('parent_room_name')
            window_name = window_info.get('name', '')
            
            # Match windows to room by:
            # 1. Direct parent relationship (room ID match)
            # 2. Parent room name match
            # 3. Window name contains room name/ID
            is_match = False
            
            # Check by room ID
            if parent_room:
                if parent_room == room_id or parent_room in room_id or room_id in parent_room:
                    is_match = True
            
            # Check by room name
            if not is_match and parent_room_name:
                if parent_room_name == room_name or parent_room_name in room_name or room_name in parent_room_name:
                    is_match = True
            
            # Also check if window name suggests it belongs to this room
            if not is_match and window_name:
                # Extract room identifier from window name
                window_num_match = re.search(r'(\d+)', window_name)
                room_num_match = re.search(r'(\d+)', room_name)
                if window_num_match and room_num_match:
                    try:
                        window_num = window_num_match.group(1)
                        room_num = room_num_match.group(1)
                        if window_num == room_num or abs(int(window_num) - int(room_num)) < 10:
                            is_match = True
                    except ValueError:
                        pass
            
            if is_match:
                # Create window from node
                node_idx = window_info['node_idx']
                node = node_map.get(node_idx)
                
                if node:
                    window = self._create_window_from_geometry(node, room_id, room_bounds)
                    if window:
                        windows.append(window)
                        logger.info(f"Found window from name match: {window_name} -> {room_name}")
        
        # Method 2: AGGRESSIVE geometry-based detection - scan ALL nodes
        # This is the main method - finds windows regardless of names
        geometry_windows = self._detect_all_windows_aggressive(node_map, room_node_idx, room_bounds, room_center)
        
        # Add geometry-detected windows (avoid duplicates)
        for window in geometry_windows:
            if not self._is_duplicate_window(window, windows, tolerance=0.5):
                windows.append(window)
        
        logger.info(f"Found {len(windows)} window(s) for room {room_name} ({len(geometry_windows)} from aggressive geometry scan)")
        return windows
    
    def _create_window_from_geometry(self, node: Dict, room_id: str, room_bounds: Optional[np.ndarray] = None) -> Optional[Window]:
        """Create a Window object from node geometry (preferred method)."""
        node_name = node.get('name', f"{room_id}_window")
        geometry = node.get('geometry')
        translation = node.get('translation', [0, 0, 0])
        scale = node.get('scale', [1, 1, 1])
        
        # If we have actual mesh geometry, extract properties from it
        if geometry and isinstance(geometry, trimesh.Trimesh):
            return self._create_window_from_mesh(geometry, node_name, room_id, translation, room_bounds)
        
        # Fallback: Use node transform information
        # Default window size from scale
        window_width = abs(scale[0]) * 1.5 if len(scale) > 0 and abs(scale[0]) > 0.1 else 1.5
        window_height = abs(scale[1]) * 1.2 if len(scale) > 1 and abs(scale[1]) > 0.1 else 1.2
        
        # Window center from translation
        center = tuple(translation[:3]) if len(translation) >= 3 else (0.0, 0.0, 1.5)
        
        # Default normal (facing outward)
        normal = (0.0, 1.0, 0.0)
        
        window = Window(
            id=node_name,
            center=center,
            normal=normal,
            size=(window_width, window_height),
            window_type='double_glazed',
            transmittance=0.75,
            frame_factor=0.70
        )
        
        return window
    
    def _create_window_from_mesh(self, mesh: trimesh.Trimesh, window_id: str, room_id: str, 
                                  node_translation: List[float], room_bounds: Optional[np.ndarray] = None) -> Optional[Window]:
        """Create a Window object from mesh geometry with actual properties."""
        if len(mesh.vertices) == 0:
            return None
        
        # Calculate window size from mesh bounds
        bounds = mesh.bounds
        size_x = abs(bounds[1][0] - bounds[0][0])
        size_y = abs(bounds[1][1] - bounds[0][1])
        size_z = abs(bounds[1][2] - bounds[0][2])
        
        # Windows are typically flat (one dimension is much smaller)
        # Determine which dimensions represent width and height
        dimensions = sorted([size_x, size_y, size_z])
        thickness = dimensions[0]  # Smallest dimension (window thickness)
        
        # Width and height are the two larger dimensions
        if size_z == thickness:
            # Window in XY plane
            window_width = max(size_x, size_y)
            window_height = min(size_x, size_y)
        elif size_y == thickness:
            # Window in XZ plane
            window_width = max(size_x, size_z)
            window_height = min(size_x, size_z)
        else:
            # Window in YZ plane
            window_width = max(size_y, size_z)
            window_height = min(size_y, size_z)
        
        # Use reasonable defaults if dimensions are too small
        if window_width < 0.1:
            window_width = 1.5
        if window_height < 0.1:
            window_height = 1.2
        
        # Calculate center from mesh centroid
        center = mesh.centroid
        center = tuple(center[:3]) if len(center) >= 3 else (0.0, 0.0, 1.5)
        
        # Calculate normal from mesh face normals (average of all faces)
        if len(mesh.faces) > 0:
            face_normals = mesh.face_normals
            # Average normal (weighted by face area)
            face_areas = mesh.area_faces
            if len(face_areas) > 0:
                # Check if weights sum to non-zero before using weighted average
                total_area = np.sum(face_areas)
                if total_area > 1e-10:  # Check if weights sum to non-zero
                    weighted_normal = np.average(face_normals, axis=0, weights=face_areas)
                else:
                    # Fallback to unweighted average if all areas are zero
                    weighted_normal = np.mean(face_normals, axis=0)
                
                norm = np.linalg.norm(weighted_normal)
                if norm > 1e-10:
                    normal = tuple(weighted_normal / norm)
                else:
                    # Fallback to first face normal if weighted normal is zero
                    normal = tuple(face_normals[0] if len(face_normals) > 0 else (0.0, 1.0, 0.0))
            else:
                normal = tuple(face_normals[0] if len(face_normals) > 0 else (0.0, 1.0, 0.0))
        else:
            normal = (0.0, 1.0, 0.0)
        
        # Ensure normal is unit vector
        normal_array = np.array(normal)
        norm = np.linalg.norm(normal_array)
        if norm > 1e-10:
            normal = tuple(normal_array / norm)
        else:
            normal = (0.0, 1.0, 0.0)
        
        window = Window(
            id=window_id,
            center=center,
            normal=normal,
            size=(float(window_width), float(window_height)),
            window_type='double_glazed',
            transmittance=0.75,
            frame_factor=0.70
        )
        
        return window
    
    def _detect_all_windows_aggressive(self, node_map: Dict[int, Dict], room_node_idx: Optional[int] = None, 
                                       room_bounds: Optional[np.ndarray] = None, room_center: Optional[np.ndarray] = None) -> List[Window]:
        """
        AGGRESSIVE window detection - scans ALL nodes with geometry.
        Uses multiple heuristics to identify windows:
        1. Name-based (window, окно patterns)
        2. Geometry-based (flat, reasonable size)
        3. Spatial proximity to room
        """
        windows = []
        processed_count = 0
        window_candidates = []
        
        logger.info(f"Starting AGGRESSIVE window detection - scanning {len(node_map)} nodes...")
        
        # Step 1: Scan ALL nodes with geometry
        for node_idx, node in node_map.items():
            # Skip the room node itself
            if node_idx == room_node_idx:
                continue
            
            geometry = node.get('geometry')
            if not geometry or not isinstance(geometry, trimesh.Trimesh):
                continue
            
            # Skip if no vertices (empty mesh)
            if len(geometry.vertices) == 0:
                continue
            
            processed_count += 1
            node_name = node.get('name', f"Node_{node_idx}")
            
            # Check if node name suggests it's a window
            name_suggests_window = False
            if node_name:
                name_lower = node_name.lower()
                if any(pattern in name_lower for pattern in ['window', 'окно', 'win', 'glazing', 'glass']):
                    name_suggests_window = True
            
            # Analyze geometry
            bounds = geometry.bounds
            size_x = abs(bounds[1][0] - bounds[0][0])
            size_y = abs(bounds[1][1] - bounds[0][1])
            size_z = abs(bounds[1][2] - bounds[0][2])
            dimensions = sorted([size_x, size_y, size_z])
            thickness = dimensions[0]
            width = dimensions[1]
            height = dimensions[2]
            max_dimension = max(size_x, size_y, size_z)
            
            # Calculate mesh center
            mesh_center = geometry.centroid
            
            # Check spatial proximity to room
            near_room = False
            if room_bounds is not None and room_center is not None:
                # Check if mesh center is near room bounds (within 3m)
                distance_to_bounds = self._distance_to_bounds(mesh_center, room_bounds)
                distance_to_center = np.linalg.norm(mesh_center - room_center)
                if distance_to_bounds < 3.0 or distance_to_center < 10.0:
                    near_room = True
            
            # Window detection heuristics (RELAXED criteria)
            is_window_candidate = False
            reason = ""
            
            # Heuristic 1: Name suggests window
            if name_suggests_window:
                is_window_candidate = True
                reason = "name_match"
            
            # Heuristic 2: Geometry-based (flat and reasonable size)
            # RELAXED: Accept thicker objects (up to 0.5m) and larger sizes
            if not is_window_candidate:
                # Flat check (thickness < 0.5m and thickness/width < 0.3)
                is_flat = thickness < 0.5 and (thickness / max(width, 0.1) < 0.3)
                
                # Size check (reasonable window size: 0.2m - 8m)
                reasonable_size = (0.2 <= width <= 8.0) and (0.2 <= height <= 6.0)
                
                # Not too large (max dimension < 15m to exclude walls/floors)
                not_too_large = max_dimension < 15.0
                
                if is_flat and reasonable_size and not_too_large:
                    is_window_candidate = True
                    reason = "geometry_flat"
            
            # Heuristic 3: Small mesh near room (could be window even if not perfectly flat)
            if not is_window_candidate and near_room:
                # Small meshes near room boundaries are likely windows
                if max_dimension < 3.0 and width > 0.1 and height > 0.1:
                    is_window_candidate = True
                    reason = "spatial_proximity"
            
            # Heuristic 4: Open3D-enhanced analysis (if available)
            if not is_window_candidate and OPEN3D_AVAILABLE:
                o3d_result = self._analyze_with_open3d(geometry, room_bounds)
                if o3d_result:
                    is_window_candidate = True
                    reason = f"open3d_{o3d_result}"
            
            # If candidate, extract window
            if is_window_candidate:
                translation = node.get('translation', [0, 0, 0])
                window = self._create_window_from_mesh(geometry, node_name, "Room", translation, room_bounds)
                if window:
                    window_candidates.append((window, reason, node_name))
                    logger.info(f"Window candidate #{len(window_candidates)}: {node_name} (reason: {reason}, size: {window.size}, center: {window.center})")
        
        logger.info(f"Processed {processed_count} nodes with geometry, found {len(window_candidates)} window candidates")
        
        # Add all candidates as windows
        for window, reason, node_name in window_candidates:
            windows.append(window)
        
        return windows
    
    def _analyze_with_open3d(self, mesh: trimesh.Trimesh, room_bounds: Optional[np.ndarray] = None) -> Optional[str]:
        """
        Use Open3D for advanced 3D geometry analysis to detect windows.
        Uses point cloud analysis, normal estimation, and surface classification.
        
        Returns:
            Detection reason string if window-like, None otherwise
        """
        if not OPEN3D_AVAILABLE:
            return None
        
        try:
            # Convert trimesh to Open3D mesh
            o3d_mesh = o3d.geometry.TriangleMesh()
            o3d_mesh.vertices = o3d.utility.Vector3dVector(mesh.vertices)
            o3d_mesh.triangles = o3d.utility.Vector3iVector(mesh.faces)
            
            # Compute normals if not present
            if not o3d_mesh.has_vertex_normals():
                o3d_mesh.compute_vertex_normals()
            if not o3d_mesh.has_triangle_normals():
                o3d_mesh.compute_triangle_normals()
            
            # Analyze surface characteristics
            # Windows typically have:
            # 1. High planarity (most faces are coplanar)
            # 2. Consistent normals (all pointing in similar direction)
            # 3. Low curvature variation
            
            # Get triangle normals
            triangle_normals = np.asarray(o3d_mesh.triangle_normals)
            if len(triangle_normals) == 0:
                return None
            
            # Check normal consistency (windows have consistent normals)
            # Calculate average normal
            avg_normal = np.mean(triangle_normals, axis=0)
            norm = np.linalg.norm(avg_normal)
            if norm > 1e-10:
                avg_normal = avg_normal / norm
            else:
                # Fallback to default normal if average is zero
                avg_normal = np.array([0.0, 1.0, 0.0])
            
            # Calculate normal variance (low variance = consistent normals = window-like)
            normal_dots = np.abs(np.dot(triangle_normals, avg_normal))
            normal_consistency = np.mean(normal_dots)
            
            # Windows should have high normal consistency (>0.9)
            if normal_consistency > 0.9:
                # Check planarity using point cloud analysis
                pcd = o3d_mesh.sample_points_uniformly(number_of_points=min(1000, len(mesh.vertices) * 10))
                
                # Estimate normals for point cloud
                pcd.estimate_normals()
                pcd.orient_normals_consistent_tangent_plane(100)
                
                # Analyze point distribution (windows are typically planar)
                points = np.asarray(pcd.points)
                if len(points) < 3:
                    return None
                
                # Fit plane to points
                plane_model, inliers = pcd.segment_plane(distance_threshold=0.05, ransac_n=3, num_iterations=100)
                
                # Check if most points fit a plane (planarity check)
                inlier_ratio = len(inliers) / len(points) if len(points) > 0 else 0
                
                # Windows are highly planar (inlier ratio > 0.8)
                if inlier_ratio > 0.8:
                    # Additional check: surface area vs bounding box volume
                    # Windows have low volume-to-area ratio (they're flat)
                    bounds = mesh.bounds
                    volume = np.prod(bounds[1] - bounds[0])
                    surface_area = mesh.area
                    
                    if volume > 0 and surface_area > 0:
                        flatness_ratio = surface_area / volume
                        # Windows have high flatness ratio (>10)
                        if flatness_ratio > 10:
                            return "planar_surface"
            
            # Check for rectangular shape using bounding box analysis
            bounds = mesh.bounds
            size = bounds[1] - bounds[0]
            dimensions = sorted(size)
            
            # Check aspect ratio (windows are often rectangular, not square)
            if dimensions[2] > 0:
                aspect_ratio = dimensions[1] / dimensions[2]
                # Windows typically have aspect ratio between 0.5 and 2.0
                if 0.5 <= aspect_ratio <= 2.0:
                    # Check if it's a reasonable window size
                    if 0.3 <= dimensions[1] <= 5.0 and 0.3 <= dimensions[2] <= 4.0:
                        return "rectangular_shape"
            
        except Exception as e:
            logger.debug(f"Open3D analysis failed: {e}")
            return None
        
        return None
    
    def _is_window_like_geometry(self, mesh: trimesh.Trimesh, room_bounds: Optional[np.ndarray] = None) -> bool:
        """
        Simple fast check if mesh could be a window - minimal checks only.
        """
        if len(mesh.vertices) == 0:
            return False
        
        bounds = mesh.bounds
        size_x = abs(bounds[1][0] - bounds[0][0])
        size_y = abs(bounds[1][1] - bounds[0][1])
        size_z = abs(bounds[1][2] - bounds[0][2])
        
        dimensions = sorted([size_x, size_y, size_z])
        thickness = dimensions[0]
        width = dimensions[1]
        height = dimensions[2]
        
        # Fast checks only
        if thickness > 0.2:  # Too thick
            return False
        if width < 0.2 or width > 6.0:  # Size range
            return False
        if height < 0.2 or height > 5.0:
            return False
        
        return True
    
    def _distance_to_bounds(self, point: np.ndarray, bounds: np.ndarray) -> float:
        """Calculate minimum distance from point to bounding box."""
        # Clamp point to bounds
        clamped = np.clip(point, bounds[0], bounds[1])
        # Distance from point to clamped point
        return np.linalg.norm(point - clamped)
    
    def _extract_all_windows_global(self, node_map: Dict[int, Dict], rooms) -> List[Window]:
        """
        Extract ALL windows from the entire building, regardless of room association.
        This is a global scan that finds windows that might not be linked to specific rooms.
        """
        all_windows = []
        
        logger.info(f"Global window extraction: scanning {len(node_map)} nodes for ALL windows...")
        
        # Scan ALL nodes (we'll use spatial matching to associate with rooms)
        for node_idx, node in node_map.items():
            geometry = node.get('geometry')
            if not geometry or not isinstance(geometry, trimesh.Trimesh):
                continue
            
            if len(geometry.vertices) == 0:
                continue
            
            node_name = node.get('name', f"Node_{node_idx}")
            
            # Check if name suggests window
            name_suggests_window = False
            if node_name:
                name_lower = node_name.lower()
                if any(pattern in name_lower for pattern in ['window', 'окно', 'win', 'glazing', 'glass']):
                    name_suggests_window = True
            
            # Analyze geometry
            bounds = geometry.bounds
            size_x = abs(bounds[1][0] - bounds[0][0])
            size_y = abs(bounds[1][1] - bounds[0][1])
            size_z = abs(bounds[1][2] - bounds[0][2])
            dimensions = sorted([size_x, size_y, size_z])
            thickness = dimensions[0]
            width = dimensions[1]
            height = dimensions[2]
            max_dimension = max(size_x, size_y, size_z)
            
            # Window detection (same relaxed criteria as per-room detection)
            is_window = False
            
            # Name-based
            if name_suggests_window:
                is_window = True
            
            # Geometry-based
            if not is_window:
                is_flat = thickness < 0.5 and (thickness / max(width, 0.1) < 0.3)
                reasonable_size = (0.2 <= width <= 8.0) and (0.2 <= height <= 6.0)
                not_too_large = max_dimension < 15.0
                
                if is_flat and reasonable_size and not_too_large:
                    is_window = True
            
            # Small mesh check
            if not is_window:
                if max_dimension < 3.0 and width > 0.1 and height > 0.1:
                    is_window = True
            
            if is_window:
                translation = node.get('translation', [0, 0, 0])
                window = self._create_window_from_mesh(geometry, node_name, "Global", translation, None)
                if window:
                    # Check for duplicates
                    if not self._is_duplicate_window(window, all_windows, tolerance=0.5):
                        all_windows.append(window)
                        logger.info(f"Global window found: {node_name} (size: {window.size})")
        
        logger.info(f"Global extraction complete: found {len(all_windows)} unique windows")
        return all_windows
    
    def _find_nearest_room(self, window: Window, rooms):  # Unused - kept for compatibility
        """Find the nearest room to a window based on spatial proximity."""
        if not rooms:
            return None
        
        window_center = np.array(window.center)
        min_distance = float('inf')
        nearest_room = None
        
        for room in rooms:
            # Try to get room bounds from geometry
            room_bounds = None
            if 'bounds' in room.geometry:
                room_bounds = np.array(room.geometry['bounds'])
            elif 'type' in room.geometry and room.geometry['type'] == 'mesh':
                # Estimate bounds from room dimensions
                room_center_est = np.array([room.depth/2, room.width/2, room.height/2])
                room_bounds = np.array([
                    room_center_est - np.array([room.depth/2, room.width/2, room.height/2]),
                    room_center_est + np.array([room.depth/2, room.width/2, room.height/2])
                ])
            
            if room_bounds is not None:
                distance = self._distance_to_bounds(window_center, room_bounds)
                if distance < min_distance:
                    min_distance = distance
                    nearest_room = room
        
        # If no room found by bounds, return first room
        return nearest_room if nearest_room else rooms[0] if rooms else None
    
    def _is_duplicate_window(self, new_window: Window, existing_windows: List[Window], tolerance: float = 0.5) -> bool:
        """Check if a window is a duplicate of an existing one (same position and size)."""
        for existing in existing_windows:
            # Check if centers are close (relaxed tolerance)
            center_dist = np.linalg.norm(np.array(new_window.center) - np.array(existing.center))
            if center_dist < tolerance:
                # Check if sizes are similar (relaxed tolerance)
                size_diff = abs(new_window.size[0] - existing.size[0]) + abs(new_window.size[1] - existing.size[1])
                if size_diff < tolerance:
                    return True
        return False
    
    def _create_room_from_mesh(
        self,
        mesh: trimesh.Trimesh,
        room_id: str,
        room_name: str,
        building_id: str,
        floor_number: int = 1
    ):  # Unused - kept for compatibility
        """Create a Room object from a mesh."""
        logger.info(f"Creating room from mesh: {room_name}")
        
        vertices = mesh.vertices
        if len(vertices) == 0:
            logger.warning(f"Mesh has no vertices for room {room_name}")
            min_bounds = np.array([0.0, 0.0, 0.0])
            max_bounds = np.array([5.0, 4.0, 3.0])
        else:
            min_bounds = np.min(vertices, axis=0)
            max_bounds = np.max(vertices, axis=0)
        
        bounds = np.array([min_bounds, max_bounds])
        
        # Calculate dimensions
        depth = abs(max_bounds[0] - min_bounds[0])
        width = abs(max_bounds[1] - min_bounds[1])
        height = abs(max_bounds[2] - min_bounds[2])
        
        # Use reasonable defaults if dimensions are too small
        if depth < 0.1:
            depth = 5.0
        if width < 0.1:
            width = 4.0
        if height < 0.1:
            height = 3.0
        
        floor_area = depth * width
        
        # Room extraction is disabled - this method is kept for compatibility only
        return None
    
    def _fallback_import(self) -> List[Building]:
        """Fallback to basic import when scene graph parsing fails."""
        logger.info("Using fallback import method")
        
        try:
            file_path_str = str(self.file_path.resolve())
            self.mesh = trimesh.load(file_path_str)
            
            if isinstance(self.mesh, trimesh.Scene):
                meshes = []
                for geometry in self.mesh.geometry.values():
                    if isinstance(geometry, trimesh.Trimesh):
                        meshes.append(geometry)
                if meshes:
                    self.mesh = trimesh.util.concatenate(meshes)
            
            if not isinstance(self.mesh, trimesh.Trimesh):
                raise ValueError("Could not extract mesh from GLB file")
            
            file_name = self.file_path.stem
            building_id = f"Building_{file_name}"
            building_name = file_name.replace('_', ' ')
            
            building = Building(
                id=building_id,
                name=building_name,
                location=(55.7558, 37.6173)
            )
            
            # Room extraction disabled - windows are added directly to building
            # Extract windows from mesh
            windows = self._extract_windows_from_named_geometries()
            for window in windows:
                building.add_window(window)
            
            return [building]
            
        except Exception as e:
            logger.error(f"Fallback import failed: {e}", exc_info=True)
            raise ValueError(f"Failed to import GLB file: {e}")
    
    def _create_default_room_from_mesh(self, building_id: str):  # Unused - kept for compatibility
        """Create a default room from the entire mesh."""
        return self._create_room_from_mesh(
            self.mesh,
            room_id="Room_1",
            room_name="Main Room",
            building_id=building_id,
            floor_number=1
        )
    
    def extract_rooms(self):  # Unused - kept for compatibility
        """
        Extract rooms from GLB model.
        
        Returns:
            List of Room objects
        """
        # Rooms are extracted during import_model
        return []
    
    def extract_windows(self, room_id: str) -> List[Window]:
        """
        Extract windows for a specific room.
        
        Args:
            room_id: Room identifier
        
        Returns:
            List of Window objects
        """
        # Windows are extracted during room creation
        return []
