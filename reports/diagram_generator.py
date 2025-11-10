"""
Diagram generator for visualization of calculation results.
"""

from typing import List, Dict, Tuple, Optional
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.figure import Figure
import numpy as np

from models.calculation_result import BuildingCalculationResult, RoomCalculationResult
from models.building import Room, Window


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
        room_result: RoomCalculationResult,
        output_path: Optional[str] = None
    ) -> Figure:
        """
        Generate insolation duration diagram for a room.
        
        Args:
            room_result: Room calculation result
            output_path: Optional path to save diagram
        
        Returns:
            Matplotlib figure
        """
        if not room_result.insolation_result:
            raise ValueError("No insolation result available")
        
        fig, ax = plt.subplots(figsize=(10, 6))
        
        ins = room_result.insolation_result
        duration_seconds = ins.duration_seconds
        
        # Create bar chart
        hours = duration_seconds / 3600.0
        color = 'green' if ins.meets_requirement else 'red'
        
        ax.barh(['Инсоляция'], [hours], color=color, alpha=0.7)
        ax.set_xlabel('Продолжительность (часы)')
        ax.set_title(f'Инсоляция помещения: {room_result.room_name}')
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
        room_result: RoomCalculationResult,
        room: Room,
        output_path: Optional[str] = None
    ) -> Figure:
        """
        Generate KEO contour diagram for a room.
        
        Args:
            room_result: Room calculation result
            room: Room model
            output_path: Optional path to save diagram
        
        Returns:
            Matplotlib figure
        """
        if not room_result.keo_grid_result:
            raise ValueError("No KEO grid result available")
        
        fig, ax = plt.subplots(figsize=(10, 8))
        
        grid_data = room_result.keo_grid_result
        grid_points = grid_data['grid_points']
        
        # Extract coordinates and KEO values
        x_coords = [p['point'][0] for p in grid_points]
        y_coords = [p['point'][1] for p in grid_points]
        keo_values = [p['keo'] for p in grid_points]
        
        # Create contour plot
        if len(set(x_coords)) > 1 and len(set(y_coords)) > 1:
            # Reshape for contour
            x_unique = sorted(set(x_coords))
            y_unique = sorted(set(y_coords))
            
            X = np.array(x_coords).reshape(len(y_unique), len(x_unique))
            Y = np.array(y_coords).reshape(len(y_unique), len(x_unique))
            Z = np.array(keo_values).reshape(len(y_unique), len(x_unique))
            
            contour = ax.contourf(X, Y, Z, levels=20, cmap='YlOrRd')
            ax.contour(X, Y, Z, levels=20, colors='black', alpha=0.3, linewidths=0.5)
            
            # Add colorbar
            cbar = plt.colorbar(contour, ax=ax)
            cbar.set_label('КЕО (%)', rotation=270, labelpad=20)
        else:
            # Scatter plot if not enough points for contour
            scatter = ax.scatter(x_coords, y_coords, c=keo_values, cmap='YlOrRd', s=100)
            plt.colorbar(scatter, ax=ax, label='КЕО (%)')
        
        ax.set_xlabel('Глубина помещения (м)')
        ax.set_ylabel('Ширина помещения (м)')
        ax.set_title(f'Распределение КЕО: {room_result.room_name}')
        ax.grid(True, alpha=0.3)
        ax.set_aspect('equal')
        
        plt.tight_layout()
        
        if output_path:
            fig.savefig(output_path, dpi=self.dpi, bbox_inches='tight')
        
        return fig
    
    def generate_room_plan(
        self,
        room: Room,
        output_path: Optional[str] = None
    ) -> Figure:
        """
        Generate room plan with windows marked.
        
        Args:
            room: Room model
            output_path: Optional path to save diagram
        
        Returns:
            Matplotlib figure
        """
        fig, ax = plt.subplots(figsize=(10, 8))
        
        # Draw room outline
        room_rect = patches.Rectangle(
            (0, 0), room.depth, room.width,
            linewidth=2, edgecolor='black', facecolor='lightgray', alpha=0.3
        )
        ax.add_patch(room_rect)
        
        # Draw windows
        for window in room.windows:
            # Simplified window representation
            window_x = window.center[0]
            window_y = window.center[1]
            window_width = window.size[0]
            window_height = window.size[1]
            
            window_rect = patches.Rectangle(
                (window_x - window_width/2, window_y - window_height/2),
                window_width, window_height,
                linewidth=2, edgecolor='blue', facecolor='lightblue', alpha=0.5
            )
            ax.add_patch(window_rect)
            
            # Add window label
            ax.text(window_x, window_y, f"W{window.id[-4:]}", 
                   ha='center', va='center', fontsize=8, fontweight='bold')
        
        ax.set_xlim(-1, room.depth + 1)
        ax.set_ylim(-1, room.width + 1)
        ax.set_xlabel('Глубина (м)')
        ax.set_ylabel('Ширина (м)')
        ax.set_title(f'План помещения: {room.name}')
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
        sizes = [summary['compliant_rooms'], summary['non_compliant_rooms']]
        colors_pie = ['green', 'red']
        
        ax1.pie(sizes, labels=labels, colors=colors_pie, autopct='%1.1f%%', startangle=90)
        ax1.set_title('Соответствие требованиям')
        
        # Room-by-room compliance
        room_names = [r.room_name for r in building_result.room_results]
        compliance_status = [1 if r.is_compliant else 0 for r in building_result.room_results]
        
        ax2.barh(room_names, compliance_status, color=['green' if s else 'red' for s in compliance_status])
        ax2.set_xlabel('Статус (1=Соответствует, 0=Не соответствует)')
        ax2.set_title('Соответствие по помещениям')
        ax2.set_xlim(-0.1, 1.1)
        ax2.grid(axis='x', alpha=0.3)
        
        plt.tight_layout()
        
        if output_path:
            fig.savefig(output_path, dpi=self.dpi, bbox_inches='tight')
        
        return fig

