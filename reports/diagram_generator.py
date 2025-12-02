"""
Diagram generator for visualization of calculation results.
"""

from typing import List, Dict, Tuple, Optional
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.figure import Figure
import numpy as np

from models.calculation_result import BuildingCalculationResult, WindowCalculationResult
from models.building import Window


class DiagramGenerator:
    """Generates diagrams and visualizations for calculation results."""
    
    def __init__(self, dpi: int = 300):
        """
        Initialize diagram generator.
        
        Args:
            dpi: Resolution for diagrams
        """
        self.dpi = dpi
        plt.rcParams['font.family'] = 'DejaVu Sans'  # Support for Cyrillic
    
    def generate_insolation_diagram(
        self,
        window_result: WindowCalculationResult,
        output_path: Optional[str] = None
    ) -> Figure:
        """
        Generate insolation duration diagram for a window.
        
        Args:
            window_result: Window calculation result
            output_path: Optional path to save diagram
        
        Returns:
            Matplotlib figure
        """
        if not window_result.insolation_result:
            raise ValueError("No insolation result available")
        
        fig, ax = plt.subplots(figsize=(10, 6))
        
        ins = window_result.insolation_result
        duration_seconds = ins.duration_seconds
        
        # Create bar chart
        hours = duration_seconds / 3600.0
        color = 'green' if ins.meets_requirement else 'red'
        
        window_name = window_result.window_name or window_result.window_id
        ax.barh(['Инсоляция'], [hours], color=color, alpha=0.7)
        ax.set_xlabel('Продолжительность (часы)')
        ax.set_title(f'Инсоляция окна: {window_name}')
        ax.grid(axis='x', alpha=0.3)
        
        # Add requirement line if available
        if ins.required_duration:
            req_hours = ins.required_duration.total_seconds() / 3600.0
            ax.axvline(req_hours, color='blue', linestyle='--', label='Требуемая продолжительность')
            ax.legend()
        
        # Add text annotation
        duration_text = ins.duration_formatted
        ax.text(hours, 0, f' {duration_text}', va='center', fontsize=12, fontweight='bold')
        
        plt.tight_layout()
        
        if output_path:
            fig.savefig(output_path, dpi=self.dpi, bbox_inches='tight')
        
        return fig
    
    def generate_keo_contour_diagram(
        self,
        window_result: WindowCalculationResult,
        window: Window,
        output_path: Optional[str] = None
    ) -> Figure:
        """
        Generate KEO contour diagram for a window.
        
        Args:
            window_result: Window calculation result
            window: Window model
            output_path: Optional path to save diagram
        
        Returns:
            Matplotlib figure
        """
        if not window_result.keo_result:
            raise ValueError("No KEO result available")
        
        fig, ax = plt.subplots(figsize=(10, 8))
        
        keo = window_result.keo_result
        
        # For single window, show KEO value as a bar or single point
        window_name = window_result.window_name or window_result.window_id
        keo_value = keo.keo_total
        
        # Create a simple visualization for single window KEO
        ax.barh(['КЕО'], [keo_value], color='green' if keo.meets_requirement else 'red', alpha=0.7)
        ax.set_xlabel('КЕО (%)')
        ax.set_title(f'КЕО окна: {window_name}')
        ax.grid(axis='x', alpha=0.3)
        
        # Add text annotation
        ax.text(keo_value, 0, f' {keo_value:.2f}%', va='center', fontsize=12, fontweight='bold')
        
        # Add requirement line if available
        if keo.min_required_keo:
            ax.axvline(keo.min_required_keo, color='blue', linestyle='--', label=f'Требуемый КЕО: {keo.min_required_keo}%')
            ax.legend()
        
        plt.tight_layout()
        
        if output_path:
            fig.savefig(output_path, dpi=self.dpi, bbox_inches='tight')
        
        return fig
    
    def generate_window_plan(
        self,
        window: Window,
        output_path: Optional[str] = None
    ) -> Figure:
        """
        Generate window plan visualization.
        
        Args:
            window: Window model
            output_path: Optional path to save diagram
        
        Returns:
            Matplotlib figure
        """
        fig, ax = plt.subplots(figsize=(10, 8))
        
        # Draw window
        window_width = window.size[0]
        window_height = window.size[1]
        
        window_rect = patches.Rectangle(
            (0, 0), window_width, window_height,
            linewidth=2, edgecolor='blue', facecolor='lightblue', alpha=0.5
        )
        ax.add_patch(window_rect)
        
        # Add window label
        ax.text(window_width/2, window_height/2, f"Окно {window.id[-4:]}", 
               ha='center', va='center', fontsize=12, fontweight='bold')
        
        ax.set_xlim(-0.5, window_width + 0.5)
        ax.set_ylim(-0.5, window_height + 0.5)
        ax.set_xlabel('Ширина (м)')
        ax.set_ylabel('Высота (м)')
        ax.set_title(f'Окно: {window.id}')
        ax.grid(True, alpha=0.3)
        ax.set_aspect('equal')
        
        plt.tight_layout()
        
        if output_path:
            fig.savefig(output_path, dpi=self.dpi, bbox_inches='tight')
        
        return fig
    
    def generate_building_summary_diagram(
        self,
        building_result: BuildingCalculationResult,
        output_path: Optional[str] = None
    ) -> Figure:
        """
        Generate summary diagram for entire building.
        
        Args:
            building_result: Building calculation result
            output_path: Optional path to save diagram
        
        Returns:
            Matplotlib figure
        """
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
        
        # Compliance summary
        summary = building_result.get_compliance_summary()
        
        labels = ['Соответствует', 'Не соответствует']
        sizes = [summary['compliant_windows'], summary['non_compliant_windows']]
        colors_pie = ['green', 'red']
        
        ax1.pie(sizes, labels=labels, colors=colors_pie, autopct='%1.1f%%', startangle=90)
        ax1.set_title('Соответствие требованиям')
        
        # Window-by-window compliance
        window_names = [w.window_name or w.window_id for w in building_result.window_results]
        compliance_status = [1 if w.is_compliant else 0 for w in building_result.window_results]
        
        ax2.barh(window_names[:20], compliance_status[:20], color=['green' if s else 'red' for s in compliance_status[:20]])  # Limit to 20 for readability
        ax2.set_xlabel('Статус (1=Соответствует, 0=Не соответствует)')
        ax2.set_title('Соответствие по окнам (первые 20)')
        ax2.set_xlim(-0.1, 1.1)
        ax2.grid(axis='x', alpha=0.3)
        
        plt.tight_layout()
        
        if output_path:
            fig.savefig(output_path, dpi=self.dpi, bbox_inches='tight')
        
        return fig

