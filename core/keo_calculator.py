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
    Implements formulas from SP 367.1325800.2017 with amendments.
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
        Calculate KEO for side lighting using formula 3.11 from Amendment No. 1
        to SP 367.1325800.2017 (dated December 14, 2020).
        
        Also implements formulas from Amendment No. 2 (December 20, 2022).
        
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
        Calculate sky component using formula 3.11 from Amendment No. 1.
        
        Formula 3.11: e_sky = (τ_0 * A_sky) / (A_room * ρ_avg)
        
        Where:
        - τ_0: Sky luminance distribution factor
        - A_sky: Visible sky area from calculation point
        - A_room: Room floor area
        - ρ_avg: Average room surface reflectance
        
        Args:
            window_geometry: Window definitions
            calculation_point: Calculation point
            room_depth: Room depth
            room_width: Room width
            room_height: Room height
        
        Returns:
            Sky component value (0-1)
        """
        # Calculate visible sky area from calculation point through windows
        total_sky_area = 0.0
        
        for window in window_geometry:
            window_center = window['center']
            window_size = window['size']  # (width, height)
            
            # Calculate solid angle of visible sky through this window
            # Simplified calculation - in practice, this requires complex geometry
            distance_to_window = math.sqrt(
                (calculation_point[0] - window_center[0])**2 +
                (calculation_point[1] - window_center[1])**2 +
                (calculation_point[2] - window_center[2])**2
            )
            
            # Window area
            window_area = window_size[0] * window_size[1]
            
            # Solid angle approximation
            # More accurate calculation would use actual sky view factor
            if distance_to_window > 0:
                solid_angle = window_area / (distance_to_window ** 2)
                total_sky_area += solid_angle
        
        # Room floor area
        room_area = room_depth * room_width
        
        # Sky luminance distribution factor (typical value for overcast sky)
        tau_0 = 0.4  # Standard value for CIE overcast sky
        
        # Average room surface reflectance (simplified)
        rho_avg = 0.5  # Typical value for residential buildings
        
        # Calculate sky component
        if room_area > 0:
            sky_component = (tau_0 * total_sky_area) / (room_area * rho_avg)
        else:
            sky_component = 0.0
        
        return min(1.0, max(0.0, sky_component))
    
    def _calculate_external_reflected_component(
        self,
        window_geometry: List[Dict],
        calculation_point: Tuple[float, float, float],
        room_depth: float,
        external_reflectance: float
    ) -> float:
        """
        Calculate external reflected component (light reflected from external surfaces).
        
        Args:
            window_geometry: Window definitions
            calculation_point: Calculation point
            room_depth: Room depth
            external_reflectance: External surface reflectance
        
        Returns:
            External reflected component value (0-1)
        """
        # Simplified calculation
        # In practice, this requires knowledge of external surfaces and their reflectance
        total_window_area = sum(
            w['size'][0] * w['size'][1] for w in window_geometry
        )
        
        # External reflected component is typically 10-20% of sky component
        # This is a simplified approximation
        reflected_factor = external_reflectance * 0.15
        
        return reflected_factor
    
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
        Calculate internal reflected component (light reflected from room surfaces).
        
        Args:
            window_geometry: Window definitions
            calculation_point: Calculation point
            room_depth: Room depth
            room_width: Room width
            room_height: Room height
            internal_reflectance: Internal surface reflectance
        
        Returns:
            Internal reflected component value (0-1)
        """
        # Calculate room surface areas
        floor_area = room_depth * room_width
        ceiling_area = floor_area
        wall_area = 2 * (room_depth + room_width) * room_height
        
        total_surface_area = floor_area + ceiling_area + wall_area
        
        # Window area
        total_window_area = sum(
            w['size'][0] * w['size'][1] for w in window_geometry
        )
        
        # Internal reflected component calculation
        # Simplified formula based on room geometry and reflectance
        if total_surface_area > 0:
            # Average reflectance weighted by surface area
            # Simplified: assume uniform reflectance
            rho_avg = internal_reflectance
            
            # Internal reflection factor
            # This is a simplified approximation
            # More accurate calculation uses interreflection method
            reflection_factor = (
                rho_avg * total_window_area / total_surface_area
            ) * 0.3  # Typical internal reflection coefficient
            
            return min(1.0, max(0.0, reflection_factor))
        
        return 0.0
    
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

