"""
Data models for buildings, windows, and calculation results.
Focus: Window extraction and calculations only (no rooms).
"""

from .building import Building, Window
from .calculation_result import InsolationResult, KEOResult, WindowCalculationResult, BuildingCalculationResult

__all__ = [
    'Building',
    'Window',
    'InsolationResult',
    'KEOResult',
    'WindowCalculationResult',
    'BuildingCalculationResult',
]

