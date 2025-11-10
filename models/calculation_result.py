"""
Calculation result models for insolation and KEO.
"""

from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from datetime import date, timedelta


@dataclass
class InsolationResult:
    """Result of insolation calculation for a window."""
    
    window_id: str
    calculation_date: Optional[date] = None
    duration: timedelta = timedelta(0)
    duration_seconds: float = 0.0
    duration_formatted: str = "00:00:00"
    meets_requirement: bool = False
    required_duration: Optional[timedelta] = None
    periods: List = field(default_factory=list)  # List of insolation periods
    details: Dict = field(default_factory=dict)
    
    def is_compliant(self) -> bool:
        """Check if result meets requirements."""
        return self.meets_requirement


@dataclass
class KEOResult:
    """Result of KEO calculation for a window."""
    
    window_id: str
    calculation_point: Optional[Tuple[float, float, float]] = None
    keo_total: float = 0.0  # Total KEO in percentage
    keo_sky_component: float = 0.0
    keo_external_reflected: float = 0.0
    keo_internal_reflected: float = 0.0
    meets_requirement: bool = False
    min_required_keo: float = 0.5  # Minimum required KEO in percentage
    details: Dict = field(default_factory=dict)
    
    def is_compliant(self) -> bool:
        """Check if result meets requirements."""
        return self.meets_requirement


@dataclass
class WindowCalculationResult:
    """Complete calculation result for a single window (insolation + KEO)."""
    
    window_id: str
    window_name: Optional[str] = None
    insolation_result: Optional[InsolationResult] = None
    keo_result: Optional[KEOResult] = None
    is_compliant: bool = False
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    
    def check_compliance(self):
        """Check overall compliance of window."""
        self.is_compliant = True
        
        if self.insolation_result and not self.insolation_result.is_compliant():
            self.is_compliant = False
            self.warnings.append("Insolation requirement not met")
        
        if self.keo_result and not self.keo_result.is_compliant():
            self.is_compliant = False
            self.warnings.append("KEO requirement not met")


@dataclass
class BuildingCalculationResult:
    """Complete calculation results for entire building (windows only)."""
    
    building_id: str
    building_name: str
    window_results: List[WindowCalculationResult] = field(default_factory=list)
    calculation_date: Optional[date] = None
    summary: Dict = field(default_factory=dict)
    
    def add_window_result(self, result: WindowCalculationResult):
        """Add a window calculation result."""
        self.window_results.append(result)
    
    def get_compliance_summary(self) -> Dict:
        """Get summary of compliance across all windows."""
        total_windows = len(self.window_results)
        compliant_windows = sum(1 for w in self.window_results if w.is_compliant)
        non_compliant_windows = total_windows - compliant_windows
        
        return {
            'total_windows': total_windows,
            'compliant_windows': compliant_windows,
            'non_compliant_windows': non_compliant_windows,
            'compliance_rate': compliant_windows / total_windows if total_windows > 0 else 0.0
        }

