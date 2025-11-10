"""
Building data models: Building, Window.
Focus: Window extraction and calculations only (no rooms).
"""

from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass, field
from datetime import date, timedelta


@dataclass
class Window:
    """Window model with geometry and properties."""
    
    id: str
    center: Tuple[float, float, float]  # (x, y, z) in meters
    normal: Tuple[float, float, float]  # Normal vector (direction window faces)
    size: Tuple[float, float]  # (width, height) in meters
    window_type: Optional[str] = None  # Window type identifier
    glass_thickness: float = 4.0  # mm
    transmittance: float = 0.75  # Glass transmittance coefficient
    frame_factor: float = 0.70  # Frame reduction factor
    properties: Dict = field(default_factory=dict)  # Additional properties
    
    def get_area(self) -> float:
        """Calculate window area in square meters."""
        return self.size[0] * self.size[1]
    
    def get_window_factor(self) -> float:
        """Calculate total window factor (transmittance * frame_factor)."""
        return self.transmittance * self.frame_factor


@dataclass
class Building:
    """Building model with windows directly (no rooms)."""
    
    id: str
    name: str
    windows: List[Window] = field(default_factory=list)  # Windows directly in building
    location: Tuple[float, float] = (55.7558, 37.6173)  # (latitude, longitude)
    timezone: str = "Europe/Moscow"
    properties: Dict = field(default_factory=dict)
    
    def add_window(self, window: Window):
        """Add a window to the building."""
        self.windows.append(window)
    
    def get_total_windows(self) -> int:
        """Get total number of windows."""
        return len(self.windows)
    
    def get_total_window_area(self) -> float:
        """Calculate total window area in square meters."""
        return sum(w.get_area() for w in self.windows)

