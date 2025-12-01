"""
Sun position calculator for determining solar angles at any given time and location.
Based on astronomical calculations for accurate insolation and illumination calculations.
"""

import math
from datetime import datetime, date, time, timedelta
from typing import Tuple, Optional
import pytz
from astral import LocationInfo
from astral.sun import sun


class SunPositionCalculator:
    """
    Calculates sun position (azimuth and elevation) for a given location and time.
    Essential for insolation and KEO calculations.
    """
    
    def __init__(self, latitude: float, longitude: float, timezone: str = "Europe/Moscow"):
        """
        Initialize sun position calculator.
        
        Args:
            latitude: Latitude in decimal degrees (positive for North)
            longitude: Longitude in decimal degrees (positive for East)
            timezone: Timezone name (e.g., "Europe/Moscow")
        """
        self.latitude = math.radians(latitude)
        self.longitude = longitude
        self.tz = pytz.timezone(timezone)
        self.location = LocationInfo(
            name="Building",
            region="RU",
            timezone=timezone,
            latitude=latitude,
            longitude=longitude
        )
    
    def get_sun_position(self, dt: datetime) -> Tuple[float, float]:
        """
        Calculate sun azimuth and elevation for a given datetime.
        
        Args:
            dt: Datetime object (will be converted to local timezone)
        
        Returns:
            Tuple of (azimuth_degrees, elevation_degrees)
            - Azimuth: 0° = North, 90° = East, 180° = South, 270° = West
            - Elevation: 0° = horizon, 90° = zenith
        """
        # Ensure datetime is timezone-aware
        if dt.tzinfo is None:
            dt = self.tz.localize(dt)
        else:
            dt = dt.astimezone(self.tz)
        
        # Get sun position using astral library
        s = sun(self.location.observer, date=dt.date(), tzinfo=self.tz)
        
        # Calculate position for specific time
        # Using simplified solar position algorithm
        # More accurate than basic formulas, suitable for building calculations
        
        # Day of year
        day_of_year = dt.timetuple().tm_yday
        
        # Solar declination (angle of sun relative to equator)
        declination = 23.45 * math.sin(math.radians(360 * (284 + day_of_year) / 365))
        declination_rad = math.radians(declination)
        
        # Hour angle (time from solar noon)
        # Include seconds and microseconds for second-level precision
        hour = dt.hour + dt.minute / 60.0 + dt.second / 3600.0 + dt.microsecond / 3600000000.0
        # Get UTC offset by converting to UTC and calculating the timedelta difference
        # This avoids issues with pytz's utcoffset() method which expects naive datetimes
        utc_dt = dt.astimezone(pytz.UTC)
        # Create naive versions for comparison
        naive_local = dt.replace(tzinfo=None)
        naive_utc = utc_dt.replace(tzinfo=None)
        # Calculate offset: difference between local and UTC
        utc_offset = naive_local - naive_utc
        utc_offset_hours = utc_offset.total_seconds() / 3600.0
        solar_time = hour + (self.longitude / 15.0) - utc_offset_hours
        hour_angle = 15.0 * (solar_time - 12.0)
        hour_angle_rad = math.radians(hour_angle)
        
        # Elevation angle (altitude)
        sin_elevation = (
            math.sin(self.latitude) * math.sin(declination_rad) +
            math.cos(self.latitude) * math.cos(declination_rad) * math.cos(hour_angle_rad)
        )
        elevation_rad = math.asin(max(-1.0, min(1.0, sin_elevation)))
        elevation_degrees = math.degrees(elevation_rad)
        
        # Azimuth angle
        cos_azimuth = (
            (math.sin(declination_rad) - math.sin(self.latitude) * sin_elevation) /
            (math.cos(self.latitude) * math.cos(elevation_rad))
        )
        cos_azimuth = max(-1.0, min(1.0, cos_azimuth))
        azimuth_rad = math.acos(cos_azimuth)
        
        # Determine if morning or afternoon
        if hour_angle > 0:
            azimuth_degrees = 360 - math.degrees(azimuth_rad)
        else:
            azimuth_degrees = math.degrees(azimuth_rad)
        
        return azimuth_degrees, elevation_degrees
    
    def is_sun_above_horizon(self, dt: datetime) -> bool:
        """
        Check if sun is above horizon at given time.
        
        Args:
            dt: Datetime object
        
        Returns:
            True if sun is above horizon, False otherwise
        """
        _, elevation = self.get_sun_position(dt)
        return elevation > 0
    
    def get_sunrise_sunset(self, date_obj: date) -> Tuple[datetime, datetime]:
        """
        Get sunrise and sunset times for a given date.
        
        Args:
            date_obj: Date object
        
        Returns:
            Tuple of (sunrise, sunset) datetime objects
        """
        s = sun(self.location.observer, date=date_obj, tzinfo=self.tz)
        return s['sunrise'], s['sunset']
    
    def get_daylight_hours(self, date_obj: date) -> float:
        """
        Calculate total daylight hours for a given date.
        
        Args:
            date_obj: Date object
        
        Returns:
            Daylight hours as float
        """
        sunrise, sunset = self.get_sunrise_sunset(date_obj)
        delta = sunset - sunrise
        return delta.total_seconds() / 3600.0

