"""
Insolation duration calculator.
Compliant with GOST R 57795-2017 and SanPiN 1.2.3685-21.
"""

from datetime import datetime, date, timedelta
from typing import List, Tuple, Optional, Dict
import math
from .sun_position import SunPositionCalculator


class InsolationCalculator:
    """
    Calculates insolation duration for rooms and windows.
    Implements GOST R 57795-2017 methodology with amendments.
    """
    
    def __init__(
        self,
        latitude: float,
        longitude: float,
        timezone: str = "Europe/Moscow",
        time_step_minutes: int = 1,
        consider_shadowing: bool = True
    ):
        """
        Initialize insolation calculator.
        
        Args:
            latitude: Latitude in decimal degrees
            longitude: Longitude in decimal degrees
            timezone: Timezone name
            time_step_minutes: Calculation time step in minutes (default: 1 minute for accuracy)
            consider_shadowing: Whether to consider shadowing from surrounding buildings
        """
        self.sun_calculator = SunPositionCalculator(latitude, longitude, timezone)
        self.time_step = timedelta(minutes=time_step_minutes)
        self.consider_shadowing = consider_shadowing
        self.shadowing_objects = []  # List of shadowing building geometries
    
    def add_shadowing_object(self, geometry):
        """
        Add a shadowing object (building, structure) that can cast shadows.
        
        Args:
            geometry: 3D geometry object representing the shadowing structure
        """
        self.shadowing_objects.append(geometry)
    
    def calculate_insolation_duration(
        self,
        window_center: Tuple[float, float, float],  # (x, y, z) in meters
        window_normal: Tuple[float, float, float],  # Normal vector of window
        window_size: Tuple[float, float],  # (width, height) in meters
        calculation_date: date,
        required_duration: Optional[timedelta] = None
    ) -> Dict:
        """
        Calculate insolation duration for a window.
        
        Args:
            window_center: Window center coordinates (x, y, z)
            window_normal: Window normal vector (direction window faces)
            window_size: Window dimensions (width, height)
            calculation_date: Date for calculation
            required_duration: Required minimum duration (for validation)
        
        Returns:
            Dictionary with:
            - duration: Total insolation duration as timedelta
            - duration_seconds: Duration in seconds (for precise comparison)
            - periods: List of insolation periods
            - meets_requirement: Boolean indicating if requirement is met
            - details: Detailed calculation data
        """
        # Get sunrise and sunset
        sunrise, sunset = self.sun_calculator.get_sunrise_sunset(calculation_date)
        
        # Calculate insolation periods throughout the day
        insolation_periods = []
        current_time = sunrise
        
        total_insolation_seconds = 0
        
        while current_time < sunset:
            # Check if sun is above horizon
            if not self.sun_calculator.is_sun_above_horizon(current_time):
                current_time += self.time_step
                continue
            
            # Get sun position
            azimuth, elevation = self.sun_calculator.get_sun_position(current_time)
            
            # Check if sun rays reach the window
            if self._is_window_illuminated(
                window_center, window_normal, window_size,
                azimuth, elevation, current_time
            ):
                # Check if window is shadowed
                if not self._is_window_shadowed(
                    window_center, azimuth, elevation, current_time
                ):
                    insolation_periods.append(current_time)
                    total_insolation_seconds += self.time_step.total_seconds()
            
            current_time += self.time_step
        
        # Convert to timedelta
        # Use exact seconds (no rounding) to ensure accuracy
        duration = timedelta(seconds=int(total_insolation_seconds))
        
        # Check if requirement is met
        # CRITICAL: Use exact second-level comparison to avoid Altec-style overstatement
        # If required is 1:30 (5400 seconds), we must get >= 5400, not 5399
        meets_requirement = True
        if required_duration:
            required_seconds = required_duration.total_seconds()
            # Exact comparison: must be >= required (not > required - 1)
            # This ensures 1:30 requirement is met with exactly 1:30 or more
            meets_requirement = total_insolation_seconds >= required_seconds
        
        return {
            'duration': duration,
            'duration_seconds': total_insolation_seconds,
            'duration_formatted': self._format_duration(total_insolation_seconds),
            'periods': insolation_periods,
            'meets_requirement': meets_requirement,
            'calculation_date': calculation_date,
            'window_center': window_center,
            'details': {
                'sunrise': sunrise,
                'sunset': sunset,
                'total_daylight_hours': self.sun_calculator.get_daylight_hours(calculation_date),
                'time_step_minutes': self.time_step.total_seconds() / 60.0
            }
        }
    
    def _is_window_illuminated(
        self,
        window_center: Tuple[float, float, float],
        window_normal: Tuple[float, float, float],
        window_size: Tuple[float, float],
        sun_azimuth: float,
        sun_elevation: float,
        dt: datetime
    ) -> bool:
        """
        Check if sun rays directly illuminate the window.
        
        Args:
            window_center: Window center coordinates
            window_normal: Window normal vector
            sun_azimuth: Sun azimuth in degrees
            sun_elevation: Sun elevation in degrees
            dt: Current datetime
        
        Returns:
            True if window is directly illuminated
        """
        # Convert sun position to direction vector
        elevation_rad = math.radians(sun_elevation)
        azimuth_rad = math.radians(sun_azimuth)
        
        # Sun direction vector (pointing from sun to window)
        sun_direction = (
            math.sin(azimuth_rad) * math.cos(elevation_rad),
            math.cos(azimuth_rad) * math.cos(elevation_rad),
            math.sin(elevation_rad)
        )
        
        # Calculate angle between window normal and sun direction
        # Window normal should point outward from building
        dot_product = sum(n * s for n, s in zip(window_normal, sun_direction))
        
        # Normalize vectors
        normal_magnitude = math.sqrt(sum(n * n for n in window_normal))
        sun_magnitude = math.sqrt(sum(s * s for s in sun_direction))
        
        if normal_magnitude == 0 or sun_magnitude == 0:
            return False
        
        cos_angle = dot_product / (normal_magnitude * sun_magnitude)
        angle_rad = math.acos(max(-1.0, min(1.0, cos_angle)))
        angle_degrees = math.degrees(angle_rad)
        
        # Window is illuminated if angle is less than 90 degrees
        # (sun rays hit window from front)
        return angle_degrees < 90.0
    
    def _is_window_shadowed(
        self,
        window_center: Tuple[float, float, float],
        sun_azimuth: float,
        sun_elevation: float,
        dt: datetime
    ) -> bool:
        """
        Check if window is shadowed by surrounding buildings.
        
        Args:
            window_center: Window center coordinates
            sun_azimuth: Sun azimuth in degrees
            sun_elevation: Sun elevation in degrees
            dt: Current datetime
        
        Returns:
            True if window is shadowed
        """
        if not self.consider_shadowing or not self.shadowing_objects:
            return False
        
        # TODO: Implement shadow casting algorithm
        # This requires 3D geometry intersection calculations
        # For now, return False (no shadowing)
        return False
    
    def _format_duration(self, seconds: float) -> str:
        """
        Format duration in seconds to HH:MM:SS format.
        
        Args:
            seconds: Duration in seconds
        
        Returns:
            Formatted string (HH:MM:SS)
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    
    def calculate_room_insolation(
        self,
        room_windows: List[Dict],  # List of window definitions
        calculation_date: date,
        required_duration: Optional[timedelta] = None
    ) -> Dict:
        """
        Calculate insolation for a room with multiple windows.
        According to GOST R 57795-2017, room insolation is determined by
        the window(s) that receive the most insolation.
        
        Args:
            room_windows: List of window dictionaries with center, normal, size
            calculation_date: Date for calculation
            required_duration: Required minimum duration
        
        Returns:
            Dictionary with room insolation results
        """
        window_results = []
        
        for window in room_windows:
            result = self.calculate_insolation_duration(
                window['center'],
                window['normal'],
                window['size'],
                calculation_date,
                required_duration
            )
            window_results.append({
                'window_id': window.get('id', 'unknown'),
                **result
            })
        
        # Find maximum insolation duration among all windows
        max_result = max(window_results, key=lambda x: x['duration_seconds'])
        
        return {
            'room_insolation': max_result,
            'all_windows': window_results,
            'meets_requirement': max_result['meets_requirement'],
            'calculation_date': calculation_date
        }

