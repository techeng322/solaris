"""
Enhanced report features based on requirements.
- Prevents overlapping calculation points
- Organizes plan sequence
- Plan selection and scale settings
- Report text editing
"""

from typing import List, Dict, Tuple, Optional, Set
import math
from dataclasses import dataclass


@dataclass
class CalculationPoint:
    """Represents a calculation point with position and data."""
    x: float
    y: float
    label: str
    value: float
    room_id: str
    floor_number: Optional[int] = None


@dataclass
class PlanSettings:
    """Settings for plan layout in reports."""
    plan_id: str
    room_id: Optional[str] = None
    floor_number: Optional[int] = None
    scale: float = 1.0  # Scale factor (e.g., 1:50 = 0.02)
    include: bool = True
    order: int = 0  # Display order


class ReportLayoutManager:
    """
    Manages report layout to prevent overlapping points and organize plans.
    """
    
    def __init__(self, min_point_distance: float = 0.5):
        """
        Initialize layout manager.
        
        Args:
            min_point_distance: Minimum distance between calculation points (in meters)
        """
        self.min_point_distance = min_point_distance
        self.placed_points: List[CalculationPoint] = []
    
    def add_calculation_point(
        self,
        x: float,
        y: float,
        label: str,
        value: float,
        room_id: str,
        floor_number: Optional[int] = None
    ) -> CalculationPoint:
        """
        Add a calculation point, automatically adjusting position if it overlaps.
        
        Args:
            x, y: Original position
            label: Point label
            value: Calculation value
            room_id: Room identifier
            floor_number: Floor number (optional)
        
        Returns:
            CalculationPoint with adjusted position if needed
        """
        point = CalculationPoint(x, y, label, value, room_id, floor_number)
        
        # Check for overlaps and adjust position
        adjusted_point = self._adjust_point_position(point)
        
        self.placed_points.append(adjusted_point)
        return adjusted_point
    
    def _adjust_point_position(self, point: CalculationPoint) -> CalculationPoint:
        """
        Adjust point position to avoid overlaps.
        
        Args:
            point: Original point
        
        Returns:
            Point with adjusted position
        """
        # Check if point overlaps with existing points
        for existing_point in self.placed_points:
            distance = math.sqrt(
                (point.x - existing_point.x) ** 2 + 
                (point.y - existing_point.y) ** 2
            )
            
            if distance < self.min_point_distance:
                # Adjust position - move in a spiral pattern
                angle = math.atan2(
                    point.y - existing_point.y,
                    point.x - existing_point.x
                )
                
                # Move point away from existing point
                new_x = existing_point.x + math.cos(angle) * self.min_point_distance
                new_y = existing_point.y + math.sin(angle) * self.min_point_distance
                
                point.x = new_x
                point.y = new_y
                
                # Recursively check again (with limit to prevent infinite loop)
                return self._adjust_point_position(point)
        
        return point
    
    def get_points_for_room(self, room_id: str) -> List[CalculationPoint]:
        """Get all calculation points for a specific room."""
        return [p for p in self.placed_points if p.room_id == room_id]
    
    def get_points_for_floor(self, floor_number: int) -> List[CalculationPoint]:
        """Get all calculation points for a specific floor."""
        return [p for p in self.placed_points if p.floor_number == floor_number]


class PlanOrganizer:
    """
    Organizes plans in reports to prevent chaotic sequence.
    """
    
    @staticmethod
    def organize_plans_by_floor(plans: List[PlanSettings]) -> List[PlanSettings]:
        """
        Organize plans by floor number (ascending).
        
        Args:
            plans: List of plan settings
        
        Returns:
            Organized list of plans
        """
        # Sort by floor number, then by room ID
        sorted_plans = sorted(
            plans,
            key=lambda p: (
                p.floor_number if p.floor_number is not None else 999,
                p.room_id or ""
            )
        )
        
        # Assign order numbers
        for i, plan in enumerate(sorted_plans):
            plan.order = i
        
        return sorted_plans
    
    @staticmethod
    def filter_selected_plans(plans: List[PlanSettings]) -> List[PlanSettings]:
        """Filter to only include plans marked for inclusion."""
        return [p for p in plans if p.include]
    
    @staticmethod
    def apply_scale_to_plan(plan: PlanSettings, base_width: float, base_height: float) -> Tuple[float, float]:
        """
        Apply scale to plan dimensions.
        
        Args:
            plan: Plan settings
            base_width: Base width in meters
            base_height: Base height in meters
        
        Returns:
            Scaled (width, height)
        """
        # Scale factor: 1:50 means 1 unit = 50 units, so scale = 1/50 = 0.02
        if plan.scale > 0:
            scale_factor = 1.0 / plan.scale
        else:
            scale_factor = 1.0
        
        return (base_width * scale_factor, base_height * scale_factor)


class ReportTextEditor:
    """
    Manages editable text portions of reports.
    """
    
    def __init__(self):
        """Initialize text editor."""
        self.custom_texts: Dict[str, str] = {}
        self.stamp_data: Dict[str, Dict] = {}
    
    def set_custom_text(self, section: str, text: str):
        """
        Set custom text for a report section.
        
        Args:
            section: Section identifier (e.g., 'introduction', 'conclusion')
            text: Custom text content
        """
        self.custom_texts[section] = text
    
    def get_custom_text(self, section: str, default: str = "") -> str:
        """Get custom text for a section, or default if not set."""
        return self.custom_texts.get(section, default)
    
    def set_stamp_data(self, stamp_type: str, data: Dict):
        """
        Set data for a stamp (signature, date, etc.).
        
        Args:
            stamp_type: Type of stamp (e.g., 'architect', 'engineer', 'approver')
            data: Stamp data (name, date, signature_path, etc.)
        """
        self.stamp_data[stamp_type] = data
    
    def get_stamp_data(self, stamp_type: str) -> Optional[Dict]:
        """Get stamp data for a type."""
        return self.stamp_data.get(stamp_type)
    
    def get_all_stamps(self) -> Dict[str, Dict]:
        """Get all stamp data."""
        return self.stamp_data.copy()


class ReportSettings:
    """
    Comprehensive report settings including plan selection and scales.
    """
    
    def __init__(self):
        """Initialize report settings."""
        self.selected_plans: List[str] = []  # Plan IDs to include
        self.plan_scales: Dict[str, float] = {}  # Scale for each plan (e.g., 50 for 1:50)
        self.page_size: str = "A4"  # A3, A4, etc.
        self.include_diagrams: bool = True
        self.include_stamps: bool = True
        self.editable_text: bool = True
        self.organize_by_floor: bool = True
    
    def set_plan_scale(self, plan_id: str, scale: float):
        """
        Set scale for a specific plan.
        
        Args:
            plan_id: Plan identifier
            scale: Scale value (e.g., 50 for 1:50)
        """
        self.plan_scales[plan_id] = scale
    
    def get_plan_scale(self, plan_id: str, default: float = 100.0) -> float:
        """Get scale for a plan."""
        return self.plan_scales.get(plan_id, default)
    
    def is_plan_selected(self, plan_id: str) -> bool:
        """Check if plan is selected for inclusion."""
        if not self.selected_plans:
            return True  # If no selection, include all
        return plan_id in self.selected_plans

