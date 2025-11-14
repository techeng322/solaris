"""
REVIT command: Calculate Both (Insolation + KEO)
Runs both insolation and KEO calculations on current REVIT model.
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
    from Autodesk.Revit.DB import FilteredElementCollector, BuiltInCategory
    
    # Import shared calculation code
    from workflow import calculate_insolation, calculate_keo
    from models.calculation_result import BuildingCalculationResult
    from revit_plugin.revit_extractor import RevitExtractor
    from utils.config_loader import load_config
    
    REVIT_AVAILABLE = True
except ImportError as e:
    REVIT_AVAILABLE = False
    logger.error(f"REVIT dependencies not available: {e}")


if REVIT_AVAILABLE:
    @script.record
    def calculate_both_command():
        """REVIT command to calculate both insolation and KEO for current model."""
        try:
            # Get REVIT document
            doc = revit.doc
            output = script.get_output()
            
            output.print_md("# Solaris Insolation & KEO Calculation")
            output.print_md("## Calculating for REVIT model...")
            
            # Extract building from REVIT
            extractor = RevitExtractor(doc)
            building = extractor.extract_building()
            
            output.print_md(f"**Building:** {building.name}")
            output.print_md(f"**Windows:** {len(building.windows)}")
            
            # Get calculation parameters
            calculation_date = date.today()
            required_duration = timedelta(hours=1, minutes=30)
            
            output.print_md(f"**Calculation Date:** {calculation_date}")
            output.print_md(f"**Required Duration:** {required_duration}")
            
            # Load config
            config_path = plugin_dir / "config.yaml"
            config = load_config(str(config_path)) if config_path.exists() else {}
            
            # Run insolation calculation
            output.print_md("## Calculating Insolation...")
            insolation_result = calculate_insolation(
                building,
                calculation_date,
                required_duration,
                config
            )
            
            # Run KEO calculation
            output.print_md("## Calculating KEO...")
            keo_result = calculate_keo(building, config)
            
            # Merge results
            output.print_md("## Merging Results...")
            # Merge KEO into insolation results
            window_result_map = {r.window_id: r for r in insolation_result.window_results}
            for keo_window_result in keo_result.window_results:
                window_id = keo_window_result.window_id
                if window_id in window_result_map:
                    # Merge KEO result into existing window result
                    insolation_window_result = window_result_map[window_id]
                    insolation_window_result.keo_value = keo_window_result.keo_value
                    insolation_window_result.keo_sky_component = keo_window_result.keo_sky_component
                    insolation_window_result.keo_external_reflected = keo_window_result.keo_external_reflected
                    insolation_window_result.keo_internal_reflected = keo_window_result.keo_internal_reflected
            
            # Update compliance
            insolation_result.check_compliance(config)
            
            result = insolation_result
            
            # Display results
            output.print_md("## Calculation Results")
            
            # Summary
            total_windows = len(result.window_results)
            insolation_compliant = sum(1 for r in result.window_results if r.insolation_compliant)
            keo_compliant = sum(1 for r in result.window_results if r.keo_compliant if hasattr(r, 'keo_compliant') else True)
            both_compliant = sum(1 for r in result.window_results if r.insolation_compliant and (r.keo_compliant if hasattr(r, 'keo_compliant') else True))
            
            output.print_md(f"**Total Windows:** {total_windows}")
            output.print_md(f"**Insolation Compliant:** {insolation_compliant}")
            output.print_md(f"**KEO Compliant:** {keo_compliant}")
            output.print_md(f"**Both Compliant:** {both_compliant}")
            
            # Highlight non-compliant windows in REVIT
            highlight_non_compliant_windows(doc, result)
            
            # Show detailed results
            output.print_md("### Window Results")
            for window_result in result.window_results[:10]:  # Show first 10
                insolation_status = "✅" if window_result.insolation_compliant else "❌"
                keo_status = "✅" if (hasattr(window_result, 'keo_compliant') and window_result.keo_compliant) else "❌"
                output.print_md(f"- **{window_result.window_id}**:")
                output.print_md(f"  - Insolation: {insolation_status} ({window_result.insolation_duration})")
                if hasattr(window_result, 'keo_value'):
                    output.print_md(f"  - KEO: {keo_status} ({window_result.keo_value}%)")
            
            if len(result.window_results) > 10:
                output.print_md(f"... and {len(result.window_results) - 10} more windows")
            
            output.print_md("## ✅ Calculation Complete")
            
        except Exception as e:
            output = script.get_output()
            output.print_md(f"## ❌ Error: {str(e)}")
            logger.error(f"Error in calculation: {e}", exc_info=True)
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
                is_non_compliant = (
                    not window_result.insolation_compliant or
                    (hasattr(window_result, 'keo_compliant') and not window_result.keo_compliant)
                )
                
                if is_non_compliant:
                    # Find REVIT element by ID
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
    @script.record
    def calculate_both_command():
        """Placeholder when REVIT not available."""
        print("REVIT API not available. Please install REVIT and pyRevit.")

