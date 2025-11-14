"""
REVIT UI components for Solaris plugin.
Provides dialogs and panels for calculation parameters and results.
"""

import logging
from typing import Optional, Tuple
from datetime import date, timedelta

logger = logging.getLogger(__name__)

try:
    from pyrevit import forms
    from Autodesk.Revit import DB
    REVIT_UI_AVAILABLE = True
except ImportError:
    REVIT_UI_AVAILABLE = False
    logger.warning("REVIT UI components not available")


if REVIT_UI_AVAILABLE:
    def get_calculation_parameters() -> Optional[Tuple[date, timedelta, str]]:
        """
        Show dialog to get calculation parameters from user.
        
        Returns:
            Tuple of (calculation_date, required_duration, calc_type) or None if cancelled
        """
        try:
            # Create dialog for calculation parameters
            # For now, use simple input - can be enhanced with custom dialog
            calc_date = forms.ask_for_one_item(
                items=[date.today().isoformat()],
                default=date.today().isoformat(),
                prompt="Select calculation date:",
                title="Calculation Parameters"
            )
            
            if not calc_date:
                return None
            
            calculation_date = date.fromisoformat(calc_date) if isinstance(calc_date, str) else calc_date
            
            # Duration options
            duration_options = [
                ("1:30:00", timedelta(hours=1, minutes=30)),
                ("2:00:00", timedelta(hours=2)),
                ("2:30:00", timedelta(hours=2, minutes=30)),
                ("3:00:00", timedelta(hours=3)),
            ]
            
            duration_str = forms.ask_for_one_item(
                items=[opt[0] for opt in duration_options],
                default="1:30:00",
                prompt="Select required insolation duration:",
                title="Calculation Parameters"
            )
            
            if not duration_str:
                return None
            
            required_duration = next(opt[1] for opt in duration_options if opt[0] == duration_str)
            
            # Calculation type
            calc_type = forms.ask_for_one_item(
                items=["insolation", "keo", "both"],
                default="both",
                prompt="Select calculation type:",
                title="Calculation Parameters"
            )
            
            if not calc_type:
                return None
            
            return (calculation_date, required_duration, calc_type)
            
        except Exception as e:
            logger.error(f"Error getting calculation parameters: {e}")
            # Return defaults
            return (date.today(), timedelta(hours=1, minutes=30), "both")
    
    def show_results_summary(result, output):
        """
        Display calculation results summary in pyRevit output.
        
        Args:
            result: BuildingCalculationResult object
            output: pyRevit output object
        """
        try:
            output.print_md("## 📊 Results Summary")
            
            total_windows = len(result.window_results)
            
            # Insolation compliance
            insolation_compliant = sum(1 for r in result.window_results if r.insolation_compliant)
            insolation_non_compliant = total_windows - insolation_compliant
            
            # KEO compliance
            keo_compliant = sum(1 for r in result.window_results if hasattr(r, 'keo_compliant') and r.keo_compliant)
            keo_non_compliant = total_windows - keo_compliant
            
            # Both compliant
            both_compliant = sum(1 for r in result.window_results 
                                if r.insolation_compliant and (hasattr(r, 'keo_compliant') and r.keo_compliant))
            
            output.print_md(f"**Total Windows:** {total_windows}")
            output.print_md(f"**Insolation Compliant:** {insolation_compliant} ({insolation_compliant*100/total_windows:.1f}%)")
            output.print_md(f"**KEO Compliant:** {keo_compliant} ({keo_compliant*100/total_windows:.1f}%)")
            output.print_md(f"**Both Compliant:** {both_compliant} ({both_compliant*100/total_windows:.1f}%)")
            
            if insolation_non_compliant > 0:
                output.print_md(f"⚠️ **{insolation_non_compliant} window(s) do not meet insolation requirements**")
            if keo_non_compliant > 0:
                output.print_md(f"⚠️ **{keo_non_compliant} window(s) do not meet KEO requirements**")
            
        except Exception as e:
            logger.error(f"Error showing results summary: {e}")

else:
    def get_calculation_parameters():
        """Placeholder when REVIT UI not available."""
        return (date.today(), timedelta(hours=1, minutes=30), "both")
    
    def show_results_summary(result, output):
        """Placeholder when REVIT UI not available."""
        pass

