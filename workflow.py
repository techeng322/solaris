"""
Calculation workflow functions for Solaris Insolation Calculator.

This module contains the core workflow functions for importing models and
performing calculations. These functions are used by the GUI application.
"""

import logging
from pathlib import Path
from datetime import date, timedelta
from typing import Optional, Tuple

from models.building import Building
from models.calculation_result import BuildingCalculationResult, InsolationResult, KEOResult, WindowCalculationResult
from core import InsolationCalculator, KEOCalculator
from importers import IFCImporter, RevitImporter, GLBImporter
from importers.bim_validator import BIMValidator

logger = logging.getLogger(__name__)


def import_building_model(file_path: str, config: dict) -> Tuple[list[Building], Optional[object]]:
    """
    Import building model from file.
    
    Args:
        file_path: Path to BIM model file
        config: Configuration dictionary
    
    Returns:
        Tuple of (List of Building objects, importer instance)
        The importer instance can be used to access mesh data (for GLB files)
    """
    logger.info(f"Starting import of building model: {file_path}")
    file_ext = Path(file_path).suffix.lower()
    logger.info(f"Detected file format: {file_ext}")
    
    # Validate BIM model before import
    logger.info("Validating BIM model...")
    if file_ext == '.ifc':
        validation_result = BIMValidator.validate_ifc(file_path)
    elif file_ext == '.glb':
        validation_result = BIMValidator.validate_glb(file_path)
    else:
        validation_result = None
    
    if validation_result:
        logger.info(f"BIM Validation: {validation_result.get_summary()}")
        if validation_result.warnings:
            for warning in validation_result.warnings[:5]:  # Log first 5 warnings
                logger.warning(f"BIM Warning: {warning}")
        if validation_result.errors:
            for error in validation_result.errors[:5]:  # Log first 5 errors
                logger.error(f"BIM Error: {error}")
    
    if file_ext == '.ifc':
        logger.info("Using IFC importer (lightweight mode: semantic data extraction)")
        # Use lightweight mode by default - extracts semantic data without heavy geometry processing
        importer = IFCImporter(file_path, lightweight=True)
    elif file_ext == '.rvt':
        logger.info("Using Revit importer")
        importer = RevitImporter(file_path)
    elif file_ext == '.glb':
        logger.info("Using GLB importer")
        importer = GLBImporter(file_path)
    else:
        logger.error(f"Unsupported file format: {file_ext}")
        raise ValueError(f"Unsupported file format: {file_ext}")
    
    logger.info("Importing model...")
    buildings = importer.import_model()
    logger.info(f"Import complete. Found {len(buildings)} building(s)")
    return buildings, importer


def calculate_insolation(
    building: Building,
    calculation_date: date,
    required_duration: timedelta,
    config: dict
) -> BuildingCalculationResult:
    """
    Calculate insolation for all windows in building.
    
    Args:
        building: Building model
        calculation_date: Date for calculation
        required_duration: Required minimum insolation duration
        config: Configuration dictionary
    
    Returns:
        BuildingCalculationResult
    """
    logger.info(f"Starting insolation calculation for building: {building.name}")
    logger.info(f"Calculation date: {calculation_date}")
    logger.info(f"Required duration: {required_duration}")
    
    calc_config = config.get('calculation', {}).get('insolation', {})
    
    # Get time step in seconds (default: 1.0 second for second-level precision)
    time_step_seconds = calc_config.get('time_step', 1.0)
    
    logger.info(f"Initializing InsolationCalculator (lat: {building.location[0]}, lon: {building.location[1]})")
    logger.info(f"Calculation precision: {time_step_seconds} second(s) - second-level precision enabled")
    calculator = InsolationCalculator(
        latitude=building.location[0],
        longitude=building.location[1],
        timezone=building.timezone,
        time_step_seconds=time_step_seconds,
        consider_shadowing=calc_config.get('consider_shadowing', True)
    )
    
    building_result = BuildingCalculationResult(
        building_id=building.id,
        building_name=building.name,
        calculation_date=calculation_date
    )
    
    total_windows = len(building.windows)
    logger.info(f"Processing {total_windows} window(s) for insolation calculation")
    
    if total_windows == 0:
        logger.warning("Building has no windows - skipping insolation calculation")
        return building_result
    
    for window_idx, window in enumerate(building.windows, 1):
        logger.info(f"[{window_idx}/{total_windows}] Calculating insolation for window: {window.id}")
        
        # Calculate insolation for this window
        window_insolation_data = calculator.calculate_insolation_duration(
            window.center,
            window.normal,
            window.size,
            calculation_date,
            required_duration
        )
        
        logger.info(f"  Window {window.id}: Duration={window_insolation_data['duration_formatted']}, Meets requirement: {window_insolation_data['meets_requirement']}")
        
        # Create window insolation result
        window_insolation = InsolationResult(
            window_id=window.id,
            calculation_date=calculation_date,
            duration=window_insolation_data['duration'],
            duration_seconds=window_insolation_data['duration_seconds'],
            duration_formatted=window_insolation_data['duration_formatted'],
            meets_requirement=window_insolation_data['meets_requirement'],
            required_duration=required_duration,
            periods=window_insolation_data['periods'],
            details=window_insolation_data.get('details', {})
        )
        
        # Create window result (will add KEO later if calculated)
        window_result = WindowCalculationResult(
            window_id=window.id,
            window_name=window.window_type or f"Window {window_idx}",
            insolation_result=window_insolation
        )
        window_result.check_compliance()
        
        building_result.add_window_result(window_result)
    
    logger.info(f"Insolation calculation complete for all windows")
    return building_result


def calculate_keo(
    building: Building,
    config: dict
) -> BuildingCalculationResult:
    """
    Calculate KEO for all windows in building.
    
    Args:
        building: Building model
        config: Configuration dictionary
    
    Returns:
        BuildingCalculationResult with KEO calculations
    """
    logger.info(f"Starting KEO calculation for building: {building.name}")
    calc_config = config.get('calculation', {}).get('keo', {})
    
    logger.info(f"Initializing KEOCalculator (lat: {building.location[0]}, lon: {building.location[1]})")
    calculator = KEOCalculator(
        latitude=building.location[0],
        longitude=building.location[1],
        timezone=building.timezone,
        grid_density=calc_config.get('grid_density', 0.5),
        consider_reflected=calc_config.get('consider_reflected', True)
    )
    
    building_result = BuildingCalculationResult(
        building_id=building.id,
        building_name=building.name
    )
    
    total_windows = len(building.windows)
    logger.info(f"Processing {total_windows} window(s) for KEO calculation")
    
    if total_windows == 0:
        logger.warning("Building has no windows - skipping KEO calculation")
        return building_result
    
    for window_idx, window in enumerate(building.windows, 1):
        logger.info(f"[{window_idx}/{total_windows}] Calculating KEO for window: {window.id}")
        
        # Calculate KEO for this window
        # Use a point near the window for calculation (1m from window center at standard height)
        calculation_point = (
            window.center[0] - 1.0,  # 1m from window wall
            window.center[1],
            0.8  # Standard calculation height
        )
        
        # Single window geometry for this calculation
        single_window_geometry = [{
            'id': window.id,
            'center': window.center,
            'normal': window.normal,
            'size': window.size
        }]
        
        # Use default room geometry (simplified - just for calculation context)
        # Since we don't have room data, use window-based estimates
        default_depth = 5.0  # Default room depth
        default_width = 4.0  # Default room width
        default_height = 3.0  # Default room height
        
        keo_result_data = calculator.calculate_keo_side_lighting(
            {'type': 'default'},  # Simplified geometry
            single_window_geometry,
            calculation_point,
            default_depth,
            default_width,
            default_height,
            window_transmittance=window.transmittance,
            frame_factor=window.frame_factor
        )
        
        window_keo = KEOResult(
            window_id=window.id,
            calculation_point=calculation_point,
            keo_total=keo_result_data['keo_total'],
            keo_sky_component=keo_result_data['keo_sky_component'],
            keo_external_reflected=keo_result_data['keo_external_reflected'],
            keo_internal_reflected=keo_result_data['keo_internal_reflected'],
            meets_requirement=keo_result_data['keo_total'] >= calc_config.get('min_keo', 0.5),
            min_required_keo=calc_config.get('min_keo', 0.5),
            details=keo_result_data['details']
        )
        
        logger.info(f"  Window {window.id}: KEO={window_keo.keo_total:.2f}%, Meets requirement: {window_keo.meets_requirement}")
        
        # Find existing window result or create new
        existing_result = next(
            (w for w in building_result.window_results if w.window_id == window.id),
            None
        )
        
        if existing_result:
            existing_result.keo_result = window_keo
            existing_result.check_compliance()
        else:
            window_result = WindowCalculationResult(
                window_id=window.id,
                window_name=window.window_type or f"Window {window_idx}",
                keo_result=window_keo
            )
            window_result.check_compliance()
            building_result.add_window_result(window_result)
    
    logger.info(f"KEO calculation complete for all windows")
    return building_result

