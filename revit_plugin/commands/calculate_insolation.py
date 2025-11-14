"""
REVIT command: Calculate Insolation
Runs insolation calculation on current REVIT model.
"""

import sys
from pathlib import Path
from datetime import date, timedelta
import logging

logger = logging.getLogger(__name__)

# Add parent directory to path to import shared code
plugin_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(plugin_dir))

try:
    from pyrevit import script, revit
    from Autodesk.Revit import DB
    
    # Import shared calculation code
    from core.insolation_calculator import InsolationCalculator
    from models.calculation_result import BuildingCalculationResult
    from revit_plugin.revit_extractor import RevitExtractor
    from utils.config_loader import load_config
    
    REVIT_AVAILABLE = True
except ImportError as e:
    REVIT_AVAILABLE = False
    logger.error(f"REVIT dependencies not available: {e}")


if REVIT_AVAILABLE:
    @script.record
    def calculate_insolation_command():
        """REVIT command to calculate insolation for current model."""
        try:
            # Get REVIT document
            doc = revit.doc
            output = script.get_output()
            
            output.print_md("# Solaris Insolation Calculation")
            output.print_md("## Calculating insolation for REVIT model...")
            
            # Extract building from REVIT
            extractor = RevitExtractor(doc)
            building = extractor.extract_building()
            
            output.print_md(f"**Building:** {building.name}")
            output.print_md(f"**Windows:** {len(building.windows)}")
            
            # Get calculation parameters (from dialog or defaults)
            from revit_plugin.revit_ui import get_calculation_parameters
            params = get_calculation_parameters()
            if params:
                calculation_date, required_duration, _ = params
            else:
                # Use defaults if dialog cancelled
                calculation_date = date.today()
                required_duration = timedelta(hours=1, minutes=30)
            
            output.print_md(f"**Calculation Date:** {calculation_date}")
            output.print_md(f"**Required Duration:** {required_duration}")
            
            # Load config
            config_path = plugin_dir / "config.yaml"
            config = load_config(str(config_path)) if config_path.exists() else {}
            
            # Run calculation (reuse existing code!)
            from workflow import calculate_insolation
            result = calculate_insolation(
                building,
                calculation_date,
                required_duration,
                config
            )
            
            # Display results
            output.print_md("## Calculation Results")
            
            # Summary
            total_windows = len(result.window_results)
            compliant = sum(1 for r in result.window_results if r.is_compliant)
            non_compliant = total_windows - compliant
            
            output.print_md(f"**Total Windows:** {total_windows}")
            output.print_md(f"**Compliant:** {compliant}")
            output.print_md(f"**Non-Compliant:** {non_compliant}")
            
            # Highlight non-compliant windows in REVIT
            highlight_non_compliant_windows(doc, result)
            
            # Show detailed results
            output.print_md("### Window Results")
            for window_result in result.window_results[:10]:  # Show first 10
                status = "✅ Compliant" if window_result.is_compliant else "❌ Non-Compliant"
                output.print_md(f"- **{window_result.window_id}**: {status}")
                output.print_md(f"  - Insolation: {window_result.insolation_duration}")
            
            if len(result.window_results) > 10:
                output.print_md(f"... and {len(result.window_results) - 10} more windows")
            
            output.print_md("## ✅ Calculation Complete")
            
        except Exception as e:
            output.print_md(f"## ❌ Error: {str(e)}")
            logger.error(f"Error in insolation calculation: {e}", exc_info=True)
            import traceback
            output.print_code(traceback.format_exc())
    
    def highlight_non_compliant_windows(doc, result: BuildingCalculationResult):
        """Highlight non-compliant windows in REVIT view."""
        try:
            output = script.get_output()
            
            # Get active view
            active_view = doc.ActiveView
            
            # Collect window elements
            collector = FilteredElementCollector(doc, active_view.Id)
            windows = collector.OfCategory(BuiltInCategory.OST_Windows)\
                .WhereElementIsNotElementType()\
                .ToElements()
            
            # Create element set for highlighting
            non_compliant_ids = []
            for window_result in result.window_results:
                if not window_result.is_compliant:
                    # Find REVIT element by ID (stored in window properties)
                    # Window ID format: "Window_{ElementId}"
                    try:
                        element_id_str = window_result.window_id.replace("Window_", "")
                        element_id = DB.ElementId(int(element_id_str))
                        if element_id:
                            non_compliant_ids.append(element_id)
                    except:
                        pass
            
            # Highlight elements
            if non_compliant_ids:
                revit.get_selection().set_to(non_compliant_ids)
                output.print_md(f"**Highlighted {len(non_compliant_ids)} non-compliant window(s)**")
        
        except Exception as e:
            logger.warning(f"Could not highlight windows: {e}")

else:
    def calculate_insolation_command():
        """Placeholder when REVIT not available."""
        print("REVIT API not available. Please install REVIT and pyRevit.")

