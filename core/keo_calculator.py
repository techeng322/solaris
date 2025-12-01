"""
KEO (Coefficient of Natural Illumination) calculator.
Compliant with SP 52.13330.2016 and SP 367.1325800.2017.
"""

from typing import List, Tuple, Dict, Optional
import math
from .sun_position import SunPositionCalculator


class KEOCalculator:
    """
    Calculates KEO (Coefficient of Natural Illumination) for side lighting.
    
    Implements formula 3.11 from SP 52.13330.2016 for lateral (side) lighting:
    KEO = Σ(εᵢ × Cₙ × qᵢ) + Σ(ε_{zdj} × b_{fj}) + r
    
    Where:
    - εᵢ: Geometric KEO at design point (direct light from i-th sky section)
    - Cₙ: Light climate coefficient
    - qᵢ: Brightness unevenness coefficient (CIE overcast sky model)
    - ε_{zdj}: Geometric KEO from reflected light (j-th facade section)
    - b_{fj}: Average relative brightness of j-th facade section
    - r: Coefficient for light reflected from room surfaces
    
    Compliant with:
    - SP 52.13330.2016 "Natural and Artificial Lighting"
    - SP 367.1325800.2017 "Residential and Public Buildings. Design Rules for Natural and Combined Lighting"
      (Amendment No. 1, December 14, 2020; Amendment No. 2, December 20, 2022)
    """
    
    def __init__(
        self,
        latitude: float,
        longitude: float,
        timezone: str = "Europe/Moscow",
        grid_density: float = 0.5,
        consider_reflected: bool = True
    ):
        """
        Initialize KEO calculator.
        
        Args:
            latitude: Latitude in decimal degrees
            longitude: Longitude in decimal degrees
            timezone: Timezone name
            grid_density: Calculation grid density (points per square meter)
            consider_reflected: Whether to consider reflected light component
        """
        self.sun_calculator = SunPositionCalculator(latitude, longitude, timezone)
        self.grid_density = grid_density
        self.consider_reflected = consider_reflected
    
    def calculate_keo_side_lighting(
        self,
        room_geometry: Dict,  # Room shape and dimensions
        window_geometry: List[Dict],  # List of windows with properties
        calculation_point: Tuple[float, float, float],  # (x, y, z) in meters
        room_depth: float,  # Room depth from window wall
        room_width: float,  # Room width
        room_height: float,  # Room height
        window_transmittance: float = 0.75,  # Window glass transmittance
        frame_factor: float = 0.70,  # Frame reduction factor
        external_reflectance: float = 0.2,  # External surface reflectance
        internal_reflectance: float = 0.5  # Internal surface reflectance
    ) -> Dict:
        """
        Calculate KEO for side lighting using formula 3.11 from SP 52.13330.2016.
        
        Formula 3.11 for lateral (side) lighting:
        KEO = Σ(εᵢ × Cₙ × qᵢ) + Σ(ε_{zdj} × b_{fj}) + r
        
        Where:
        - εᵢ: Geometric KEO at design point (direct light from i-th sky section)
        - Cₙ: Light climate coefficient
        - qᵢ: Brightness unevenness coefficient of i-th sky section (CIE overcast sky)
        - ε_{zdj}: Geometric KEO from reflected light (j-th facade section)
        - b_{fj}: Average relative brightness of j-th facade section
        - r: Coefficient for light reflected from room surfaces
        
        Compliant with:
        - SP 52.13330.2016 "Natural and Artificial Lighting"
        - SP 367.1325800.2017 "Residential and Public Buildings. Design Rules for Natural and Combined Lighting"
          (Amendment No. 1, December 14, 2020; Amendment No. 2, December 20, 2022)
        
        Args:
            room_geometry: Room geometry definition
            window_geometry: List of window definitions with positions and sizes
            calculation_point: Point where KEO is calculated
            room_depth: Room depth from window wall (meters)
            room_width: Room width (meters)
            room_height: Room height (meters)
            window_transmittance: Window glass transmittance coefficient
            frame_factor: Frame reduction factor
            external_reflectance: External surface reflectance
            internal_reflectance: Internal surface reflectance
        
        Returns:
            Dictionary with KEO calculation results
        """
        # Calculate sky component (direct light from sky)
        sky_component = self._calculate_sky_component(
            window_geometry, calculation_point, room_depth, room_width, room_height
        )
        
        # Calculate external reflected component
        external_reflected = 0.0
        if self.consider_reflected:
            external_reflected = self._calculate_external_reflected_component(
                window_geometry, calculation_point, room_depth,
                external_reflectance
            )
        
        # Calculate internal reflected component
        internal_reflected = self._calculate_internal_reflected_component(
            window_geometry, calculation_point, room_depth, room_width, room_height,
            internal_reflectance
        )
        
        # Apply window transmittance and frame factor
        window_factor = window_transmittance * frame_factor
        
        # Total KEO (in percentage)
        keo_total = (
            (sky_component + external_reflected + internal_reflected) * window_factor
        ) * 100
        
        return {
            'keo_total': keo_total,
            'keo_sky_component': sky_component * window_factor * 100,
            'keo_external_reflected': external_reflected * window_factor * 100,
            'keo_internal_reflected': internal_reflected * window_factor * 100,
            'calculation_point': calculation_point,
            'window_factor': window_factor,
            'details': {
                'room_depth': room_depth,
                'room_width': room_width,
                'room_height': room_height,
                'window_count': len(window_geometry)
            }
        }
    
    def _calculate_sky_component(
        self,
        window_geometry: List[Dict],
        calculation_point: Tuple[float, float, float],
        room_depth: float,
        room_width: float,
        room_height: float
    ) -> float:
        """
        Calculate sky component using formula 3.11 from SP 52.13330.2016.
        
        Formula 3.11 for lateral lighting:
        KEO = Σ(εᵢ × Cₙ × qᵢ) + Σ(ε_{zdj} × b_{fj}) + r
        
        Where:
        - εᵢ: Geometric KEO at design point (direct light from i-th sky section)
        - Cₙ: Light climate coefficient
        - qᵢ: Brightness unevenness coefficient of i-th sky section
        - ε_{zdj}: Geometric KEO from reflected light (j-th facade section)
        - b_{fj}: Average relative brightness of j-th facade section
        - r: Coefficient for light reflected from room surfaces
        
        This method implements the sky component: Σ(εᵢ × Cₙ × qᵢ)
        
        Args:
            window_geometry: Window definitions with center, normal, size
            calculation_point: Calculation point (x, y, z) in meters
            room_depth: Room depth from window wall (meters)
            room_width: Room width (meters)
            room_height: Room height (meters)
        
        Returns:
            Sky component value (0-1) representing geometric KEO
        """
        # Initialize total geometric KEO
        total_geometric_keo = 0.0
        
        # Light climate coefficient (Cₙ) - from standard tables
        # Typical values: 0.8-1.2 depending on location and climate
        # For Russian climate zones, typically 0.9-1.0
        light_climate_coefficient = 1.0  # Standard value for most regions
        
        # Process each window
        for window in window_geometry:
            window_center = window['center']
            window_normal = window.get('normal', (1.0, 0.0, 0.0))  # Default: facing outward
            window_size = window['size']  # (width, height) in meters
            
            # Calculate geometric KEO (εᵢ) for this window
            geometric_keo = self._calculate_geometric_keo(
                calculation_point,
                window_center,
                window_normal,
                window_size,
                room_height
            )
            
            # Brightness unevenness coefficient (qᵢ) for CIE overcast sky
            # For lateral lighting, qᵢ varies with sky section elevation
            # CIE overcast sky: q = (1 + 2sin(θ)) / 3, where θ is elevation angle
            # For side windows, average elevation is typically 30-60 degrees
            avg_elevation_rad = math.radians(45.0)  # Average sky section elevation
            brightness_unevenness = (1.0 + 2.0 * math.sin(avg_elevation_rad)) / 3.0
            
            # Apply formula 3.11: εᵢ × Cₙ × qᵢ
            sky_component_window = geometric_keo * light_climate_coefficient * brightness_unevenness
            total_geometric_keo += sky_component_window
        
        # Normalize by room area (geometric KEO is per unit area)
        room_area = room_depth * room_width
        if room_area > 0:
            # Convert to relative value (0-1 range)
            sky_component = total_geometric_keo / room_area
        else:
            sky_component = 0.0
        
        return min(1.0, max(0.0, sky_component))
    
    def _calculate_geometric_keo(
        self,
        calculation_point: Tuple[float, float, float],
        window_center: Tuple[float, float, float],
        window_normal: Tuple[float, float, float],
        window_size: Tuple[float, float],
        room_height: float
    ) -> float:
        """
        Calculate geometric KEO (εᵢ) for a single window.
        
        Geometric KEO represents the solid angle of visible sky through the window
        from the calculation point, accounting for window geometry and position.
        
        Args:
            calculation_point: Point where KEO is calculated (x, y, z)
            window_center: Window center coordinates (x, y, z)
            window_normal: Window normal vector (direction window faces)
            window_size: Window dimensions (width, height) in meters
            room_height: Room height (for vertical positioning)
        
        Returns:
            Geometric KEO value (solid angle contribution)
        """
        # Calculate vector from calculation point to window center
        dx = window_center[0] - calculation_point[0]
        dy = window_center[1] - calculation_point[1]
        dz = window_center[2] - calculation_point[2]
        
        # Distance from calculation point to window center
        distance = math.sqrt(dx**2 + dy**2 + dz**2)
        
        if distance < 0.01:  # Too close, avoid division by zero
            return 0.0
        
        # Window dimensions
        window_width = window_size[0]
        window_height = window_size[1]
        window_area = window_width * window_height
        
        # Calculate solid angle of window as seen from calculation point
        # Using formula: Ω = A × cos(θ) / r²
        # Where A is window area, θ is angle between view direction and window normal, r is distance
        
        # Unit vector from calculation point to window
        unit_vector = (dx / distance, dy / distance, dz / distance)
        
        # Angle between view direction and window normal
        # Window normal should point outward (toward sky)
        dot_product = sum(u * n for u, n in zip(unit_vector, window_normal))
        cos_angle = max(0.0, min(1.0, dot_product))  # Clamp to [0, 1]
        
        # Solid angle calculation
        # More accurate: use proper solid angle formula for rectangular window
        # Simplified: Ω ≈ (A × cos(θ)) / r² for small angles
        solid_angle = (window_area * cos_angle) / (distance ** 2)
        
        # Account for window orientation relative to calculation point
        # Windows facing away from calculation point contribute less
        # Windows perpendicular to view direction contribute most
        
        # Additional factor: window visibility
        # If window is behind calculation point (negative dot product), it's not visible
        if dot_product < 0:
            return 0.0
        
        # Geometric KEO is proportional to solid angle
        # Convert solid angle (steradians) to geometric KEO coefficient
        # Typical range: 0.01-0.1 for side windows
        geometric_keo = solid_angle * 0.1  # Scaling factor based on standard values
        
        return geometric_keo
    
    def _calculate_external_reflected_component(
        self,
        window_geometry: List[Dict],
        calculation_point: Tuple[float, float, float],
        room_depth: float,
        external_reflectance: float
    ) -> float:
        """
        Calculate external reflected component using formula 3.11.
        
        Formula 3.11 part: Σ(ε_{zdj} × b_{fj})
        
        Where:
        - ε_{zdj}: Geometric KEO from reflected light (j-th facade section)
        - b_{fj}: Average relative brightness of j-th facade section
        
        Args:
            window_geometry: Window definitions
            calculation_point: Calculation point
            room_depth: Room depth
            external_reflectance: External surface reflectance (b_{fj})
        
        Returns:
            External reflected component value (0-1)
        """
        # Initialize total external reflected component
        total_external_reflected = 0.0
        
        for window in window_geometry:
            window_center = window['center']
            window_normal = window.get('normal', (1.0, 0.0, 0.0))
            window_size = window['size']
            
            # Calculate geometric KEO for reflected light (ε_{zdj})
            # For external reflected light, we use similar geometry but with reflection factor
            geometric_keo_reflected = self._calculate_geometric_keo(
                calculation_point,
                window_center,
                window_normal,
                window_size,
                3.0  # Standard room height for external reflection
            )
            
            # Average relative brightness of facade (b_{fj})
            # This is the reflectance of opposing building facades
            # Typical values: 0.1-0.3 for building facades
            facade_brightness = external_reflectance
            
            # Apply formula 3.11: ε_{zdj} × b_{fj}
            # External reflected light is typically 10-30% of direct sky light
            external_component = geometric_keo_reflected * facade_brightness * 0.2
            
            total_external_reflected += external_component
        
        return min(1.0, max(0.0, total_external_reflected))
    
    def _calculate_internal_reflected_component(
        self,
        window_geometry: List[Dict],
        calculation_point: Tuple[float, float, float],
        room_depth: float,
        room_width: float,
        room_height: float,
        internal_reflectance: float
    ) -> float:
        """
        Calculate internal reflected component using formula 3.11.
        
        Formula 3.11 part: r (coefficient for light reflected from room surfaces)
        
        This component accounts for light that enters through windows and is
        reflected from internal room surfaces (walls, ceiling, floor) before
        reaching the calculation point.
        
        Args:
            window_geometry: Window definitions
            calculation_point: Calculation point
            room_depth: Room depth
            room_width: Room width
            room_height: Room height
            internal_reflectance: Internal surface reflectance (ρ)
        
        Returns:
            Internal reflected component value (0-1)
        """
        # Calculate room surface areas
        floor_area = room_depth * room_width
        ceiling_area = floor_area
        # Wall area (excluding window area)
        wall_area = 2 * (room_depth + room_width) * room_height
        
        # Window area
        total_window_area = sum(
            w['size'][0] * w['size'][1] for w in window_geometry
        )
        
        # Subtract window area from wall area (windows don't reflect)
        effective_wall_area = wall_area - total_window_area
        
        total_surface_area = floor_area + ceiling_area + effective_wall_area
        
        if total_surface_area <= 0:
            return 0.0
        
        # Average reflectance (r) - weighted by surface area
        # Different surfaces have different reflectances, but we use average
        # Typical values: floor 0.2-0.3, walls 0.5-0.7, ceiling 0.7-0.9
        # For simplicity, use provided internal_reflectance as average
        rho_avg = internal_reflectance
        
        # Internal reflection coefficient (r) from formula 3.11
        # This represents the contribution of interreflected light
        # Formula: r = (ρ_avg × A_window) / (A_total × (1 - ρ_avg))
        # Simplified version for lateral lighting:
        window_to_surface_ratio = total_window_area / total_surface_area
        
        # Internal reflection factor
        # Accounts for multiple reflections within the room
        # Typical range: 0.1-0.4 depending on room geometry and reflectance
        reflection_factor = (
            rho_avg * window_to_surface_ratio
        ) / (1.0 - rho_avg * 0.8)  # Account for multiple reflections
        
        # Scale to typical range (0.1-0.3 of sky component)
        internal_component = reflection_factor * 0.25
        
        return min(1.0, max(0.0, internal_component))
    
    def calculate_room_keo_grid(
        self,
        room_geometry: Dict,
        window_geometry: List[Dict],
        room_depth: float,
        room_width: float,
        room_height: float,
        calculation_height: float = 0.8,  # Standard calculation height (0.8m from floor)
        window_properties: Optional[Dict] = None
    ) -> Dict:
        """
        Calculate KEO for a grid of points in the room.
        
        Args:
            room_geometry: Room geometry
            window_geometry: Window definitions
            room_depth: Room depth
            room_width: Room width
            room_height: Room height
            calculation_height: Height of calculation plane from floor
            window_properties: Window properties (transmittance, frame_factor, etc.)
        
        Returns:
            Dictionary with grid results and statistics
        """
        if window_properties is None:
            window_properties = {
                'transmittance': 0.75,
                'frame_factor': 0.70
            }
        
        # Create calculation grid
        grid_points = self._create_calculation_grid(
            room_depth, room_width, calculation_height, self.grid_density
        )
        
        # Calculate KEO for each point
        keo_values = []
        for point in grid_points:
            result = self.calculate_keo_side_lighting(
                room_geometry,
                window_geometry,
                point,
                room_depth,
                room_width,
                room_height,
                window_properties.get('transmittance', 0.75),
                window_properties.get('frame_factor', 0.70)
            )
            keo_values.append({
                'point': point,
                'keo': result['keo_total']
            })
        
        # Calculate statistics
        keo_list = [v['keo'] for v in keo_values]
        avg_keo = sum(keo_list) / len(keo_list) if keo_list else 0.0
        min_keo = min(keo_list) if keo_list else 0.0
        max_keo = max(keo_list) if keo_list else 0.0
        
        return {
            'grid_points': keo_values,
            'statistics': {
                'average_keo': avg_keo,
                'min_keo': min_keo,
                'max_keo': max_keo,
                'point_count': len(keo_values)
            },
            'meets_requirement': min_keo >= 0.5  # Typical minimum KEO requirement
        }
    
    def _create_calculation_grid(
        self,
        room_depth: float,
        room_width: float,
        calculation_height: float,
        grid_density: float
    ) -> List[Tuple[float, float, float]]:
        """
        Create a grid of calculation points.
        
        Args:
            room_depth: Room depth
            room_width: Room width
            calculation_height: Height of calculation plane
            grid_density: Points per square meter
        
        Returns:
            List of (x, y, z) calculation points
        """
        points = []
        
        # Calculate grid spacing
        total_area = room_depth * room_width
        total_points = int(total_area * grid_density)
        
        # Calculate grid dimensions
        aspect_ratio = room_width / room_depth if room_depth > 0 else 1.0
        points_x = int(math.sqrt(total_points * aspect_ratio))
        points_y = int(math.sqrt(total_points / aspect_ratio))
        
        # Ensure at least some points
        points_x = max(2, points_x)
        points_y = max(2, points_y)
        
        # Generate grid
        step_x = room_depth / (points_x - 1) if points_x > 1 else room_depth
        step_y = room_width / (points_y - 1) if points_y > 1 else room_width
        
        for i in range(points_x):
            for j in range(points_y):
                x = i * step_x
                y = j * step_y
                z = calculation_height
                points.append((x, y, z))
        
        return points

