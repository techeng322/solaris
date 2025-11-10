"""
Handler for loggia calculations.
Handles rooms behind loggias that have no direct external windows.
"""

from typing import List, Dict, Tuple, Optional
from models.building import Window
from core.insolation_calculator import InsolationCalculator
from core.keo_calculator import KEOCalculator


class LoggiaHandler:
    """
    Handles calculations for rooms with loggias.
    Implements special logic for rooms behind loggias.
    """
    
    def __init__(self, insolation_calculator: InsolationCalculator, keo_calculator: KEOCalculator):
        """
        Initialize loggia handler.
        
        Args:
            insolation_calculator: Insolation calculator instance
            keo_calculator: KEO calculator instance
        """
        self.insolation_calculator = insolation_calculator
        self.keo_calculator = keo_calculator
    
    def calculate_room_with_loggia(
        self,
        room: Room,
        calculation_date,
        required_duration
    ) -> Dict:
        """
        Calculate insolation and KEO for room behind loggia.
        
        For rooms behind loggias:
        - Insolation is calculated through the loggia opening
        - KEO accounts for reduced light transmission through loggia
        - Window properties of loggia are used if loggia has external window
        
        Args:
            room: Room with attached loggia
            calculation_date: Date for calculation
            required_duration: Required insolation duration
        
        Returns:
            Dictionary with calculation results
        """
        if not room.has_loggia():
            raise ValueError("Room does not have a loggia")
        
        loggia = room.loggia
        
        # If loggia has external window, use it for calculations
        if loggia.has_external_window:
            # Create virtual window at loggia opening
            # Position window at loggia opening (between room and loggia)
            loggia_window = self._create_loggia_window(room, loggia)
            
            # Calculate insolation through loggia (if calculator available)
            if self.insolation_calculator:
                room_windows = [{
                    'id': loggia_window.id,
                    'center': loggia_window.center,
                    'normal': loggia_window.normal,
                    'size': loggia_window.size
                }]
                
                insolation_data = self.insolation_calculator.calculate_room_insolation(
                    room_windows,
                    calculation_date,
                    required_duration
                )
                
                # Convert to result format
                from datetime import timedelta
                insolation_result = {
                    'duration': insolation_data['room_insolation']['duration'],
                    'duration_seconds': insolation_data['room_insolation']['duration_seconds'],
                    'duration_formatted': insolation_data['room_insolation']['duration_formatted'],
                    'meets_requirement': insolation_data['room_insolation']['meets_requirement'],
                    'periods': insolation_data['room_insolation'].get('periods', []),
                    'details': insolation_data['room_insolation'].get('details', {})
                }
            else:
                # No insolation calculator - return zero
                from datetime import timedelta
                insolation_result = {
                    'duration': timedelta(0),
                    'duration_seconds': 0.0,
                    'duration_formatted': '00:00:00',
                    'meets_requirement': False,
                    'periods': [],
                    'details': {}
                }
            
            # Calculate KEO with reduced transmission (loggia acts as light filter)
            # Loggia reduces light transmission by approximately 20-30%
            loggia_transmission_factor = 0.75  # 25% reduction
            
            if self.keo_calculator:
                window_geometry = [{
                    'id': loggia_window.id,
                    'center': loggia_window.center,
                    'normal': loggia_window.normal,
                    'size': loggia_window.size
                }]
                
                # Adjust window transmittance for loggia
                adjusted_transmittance = loggia_window.transmittance * loggia_transmission_factor
                
                center_point = (room.depth / 2, room.width / 2, 0.8)
                keo_result = self.keo_calculator.calculate_keo_side_lighting(
                    room.geometry,
                    window_geometry,
                    center_point,
                    room.depth,
                    room.width,
                    room.height,
                    window_transmittance=adjusted_transmittance,
                    frame_factor=loggia_window.frame_factor
                )
            else:
                # No KEO calculator - return zero
                keo_result = {
                    'keo_total': 0.0,
                    'keo_sky_component': 0.0,
                    'keo_external_reflected': 0.0,
                    'keo_internal_reflected': 0.0,
                    'details': {}
                }
            
            return {
                'insolation': insolation_result,
                'keo': keo_result,
                'loggia_factor': loggia_transmission_factor
            }
        
        else:
            # Loggia has no external window - room has no direct insolation
            # KEO is calculated from reflected light only
            return {
                'insolation': {
                    'duration': 0,
                    'duration_seconds': 0.0,
                    'duration_formatted': '00:00:00',
                    'meets_requirement': False,
                    'periods': []
                },
                'keo': {
                    'keo_total': 0.0,  # Very low KEO, only from internal reflections
                    'keo_sky_component': 0.0,
                    'keo_external_reflected': 0.0,
                    'keo_internal_reflected': 0.0
                },
                'loggia_factor': 0.0,
                'note': 'Room has no external window - only internal reflected light'
            }
    
    def _create_loggia_window(self, room: Room, loggia: Loggia) -> Window:
        """
        Create virtual window at loggia opening.
        
        Args:
            room: Room with loggia
            loggia: Loggia object
        
        Returns:
            Window object representing loggia opening
        """
        # Loggia opening is typically at the boundary between room and loggia
        # Position window at room depth (where loggia starts)
        # Size based on loggia depth and room height
        
        window_center = (
            room.depth,  # At room depth (loggia boundary)
            room.width / 2,  # Center of room width
            room.height / 2  # Mid-height
        )
        
        # Window normal points from loggia to room (inward)
        window_normal = (-1.0, 0.0, 0.0)  # Pointing into room
        
        # Window size: loggia depth x room height
        window_size = (
            loggia.depth if loggia.depth > 0 else 1.5,  # Width (loggia depth)
            room.height * 0.8  # Height (80% of room height)
        )
        
        # Use default window properties (can be customized)
        window = Window(
            id=f"loggia_{loggia.id}",
            center=window_center,
            normal=window_normal,
            size=window_size,
            window_type='loggia_opening',
            glass_thickness=0.0,  # No glass, just opening
            transmittance=1.0,  # Full transmission (opening)
            frame_factor=0.9  # Slight reduction for loggia structure
        )
        
        return window

