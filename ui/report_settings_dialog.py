"""
Report settings dialog for selecting plans, setting scales, and editing text.
Addresses requirements: plan selection, scale settings, report text editing.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QListWidget, QListWidgetItem, QSpinBox, QTextEdit, QTabWidget,
    QWidget, QGroupBox, QCheckBox, QLineEdit, QFileDialog
)
from PyQt6.QtCore import Qt
from typing import Dict, List, Optional
import logging

from reports.report_enhancements import ReportSettings, ReportTextEditor, PlanSettings

logger = logging.getLogger(__name__)


class ReportSettingsDialog(QDialog):
    """Dialog for configuring report settings."""
    
    def __init__(self, parent=None, available_plans: Optional[List[str]] = None):
        """
        Initialize report settings dialog.
        
        Args:
            parent: Parent widget
            available_plans: List of available plan IDs
        """
        super().__init__(parent)
        self.available_plans = available_plans or []
        self.report_settings = ReportSettings()
        self.text_editor = ReportTextEditor()
        
        self.setWindowTitle("Настройки отчета / Report Settings")
        self.setMinimumSize(800, 600)
        
        self.init_ui()
    
    def init_ui(self):
        """Initialize UI components."""
        layout = QVBoxLayout(self)
        
        # Create tabs
        tabs = QTabWidget()
        
        # Tab 1: Plan Selection and Scales
        plan_tab = self.create_plan_selection_tab()
        tabs.addTab(plan_tab, "Планы / Plans")
        
        # Tab 2: Report Text Editing
        text_tab = self.create_text_editing_tab()
        tabs.addTab(text_tab, "Текст / Text")
        
        # Tab 3: Stamps
        stamp_tab = self.create_stamp_tab()
        tabs.addTab(stamp_tab, "Печати / Stamps")
        
        layout.addWidget(tabs)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.ok_button = QPushButton("OK")
        self.ok_button.clicked.connect(self.accept)
        
        self.cancel_button = QPushButton("Отмена / Cancel")
        self.cancel_button.clicked.connect(self.reject)
        
        button_layout.addStretch()
        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.cancel_button)
        
        layout.addLayout(button_layout)
    
    def create_plan_selection_tab(self) -> QWidget:
        """Create plan selection and scale settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Plan selection
        selection_group = QGroupBox("Выбор планов / Plan Selection")
        selection_layout = QVBoxLayout()
        
        self.plan_list = QListWidget()
        self.plan_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        
        # Add available plans
        for plan_id in self.available_plans:
            item = QListWidgetItem(plan_id)
            item.setCheckState(Qt.CheckState.Checked)  # All selected by default
            self.plan_list.addItem(item)
        
        selection_layout.addWidget(QLabel("Выберите планы для включения в отчет:"))
        selection_layout.addWidget(self.plan_list)
        selection_group.setLayout(selection_layout)
        layout.addWidget(selection_group)
        
        # Scale settings
        scale_group = QGroupBox("Масштаб планов / Plan Scale")
        scale_layout = QVBoxLayout()
        
        self.scale_widgets = {}
        
        for plan_id in self.available_plans:
            scale_layout_item = QHBoxLayout()
            
            label = QLabel(f"{plan_id}:")
            scale_spin = QSpinBox()
            scale_spin.setMinimum(10)
            scale_spin.setMaximum(1000)
            scale_spin.setValue(100)  # Default 1:100
            scale_spin.setSuffix(" (1:X)")
            
            scale_layout_item.addWidget(label)
            scale_layout_item.addWidget(scale_spin)
            scale_layout_item.addStretch()
            
            scale_layout.addLayout(scale_layout_item)
            self.scale_widgets[plan_id] = scale_spin
        
        scale_group.setLayout(scale_layout)
        layout.addWidget(scale_group)
        
        layout.addStretch()
        
        return widget
    
    def create_text_editing_tab(self) -> QWidget:
        """Create text editing tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Introduction section
        intro_group = QGroupBox("Введение / Introduction")
        intro_layout = QVBoxLayout()
        
        self.intro_text = QTextEdit()
        self.intro_text.setPlaceholderText("Введите текст введения...")
        intro_layout.addWidget(self.intro_text)
        intro_group.setLayout(intro_layout)
        layout.addWidget(intro_group)
        
        # Conclusion section
        conclusion_group = QGroupBox("Заключение / Conclusion")
        conclusion_layout = QVBoxLayout()
        
        self.conclusion_text = QTextEdit()
        self.conclusion_text.setPlaceholderText("Введите текст заключения...")
        conclusion_layout.addWidget(self.conclusion_text)
        conclusion_group.setLayout(conclusion_layout)
        layout.addWidget(conclusion_group)
        
        layout.addStretch()
        
        return widget
    
    def create_stamp_tab(self) -> QWidget:
        """Create stamp editing tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Architect stamp
        arch_group = QGroupBox("Архитектор / Architect")
        arch_layout = QVBoxLayout()
        
        arch_layout.addWidget(QLabel("Имя / Name:"))
        self.architect_name = QLineEdit()
        arch_layout.addWidget(self.architect_name)
        
        arch_layout.addWidget(QLabel("Дата / Date:"))
        self.architect_date = QLineEdit()
        arch_layout.addWidget(self.architect_date)
        
        arch_layout.addWidget(QLabel("Подпись / Signature:"))
        self.architect_signature_btn = QPushButton("Выбрать файл / Choose File")
        self.architect_signature_btn.clicked.connect(lambda: self.select_signature_file('architect'))
        arch_layout.addWidget(self.architect_signature_btn)
        
        arch_group.setLayout(arch_layout)
        layout.addWidget(arch_group)
        
        # Engineer stamp
        eng_group = QGroupBox("Инженер / Engineer")
        eng_layout = QVBoxLayout()
        
        eng_layout.addWidget(QLabel("Имя / Name:"))
        self.engineer_name = QLineEdit()
        eng_layout.addWidget(self.engineer_name)
        
        eng_layout.addWidget(QLabel("Дата / Date:"))
        self.engineer_date = QLineEdit()
        eng_layout.addWidget(self.engineer_date)
        
        eng_layout.addWidget(QLabel("Подпись / Signature:"))
        self.engineer_signature_btn = QPushButton("Выбрать файл / Choose File")
        self.engineer_signature_btn.clicked.connect(lambda: self.select_signature_file('engineer'))
        eng_layout.addWidget(self.engineer_signature_btn)
        
        eng_group.setLayout(eng_layout)
        layout.addWidget(eng_group)
        
        layout.addStretch()
        
        return widget
    
    def select_signature_file(self, stamp_type: str):
        """Select signature image file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            f"Выберите файл подписи / Choose Signature File ({stamp_type})",
            "",
            "Image Files (*.png *.jpg *.jpeg *.bmp)"
        )
        
        if file_path:
            # Store file path (would be used when generating report)
            logger.info(f"Selected signature file for {stamp_type}: {file_path}")
    
    def get_report_settings(self) -> ReportSettings:
        """Get configured report settings."""
        # Update selected plans
        self.report_settings.selected_plans = []
        for i in range(self.plan_list.count()):
            item = self.plan_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                self.report_settings.selected_plans.append(item.text())
        
        # Update scales
        for plan_id, spin_box in self.scale_widgets.items():
            self.report_settings.set_plan_scale(plan_id, spin_box.value())
        
        return self.report_settings
    
    def get_text_editor(self) -> ReportTextEditor:
        """Get configured text editor."""
        # Update custom texts
        self.text_editor.set_custom_text('introduction', self.intro_text.toPlainText())
        self.text_editor.set_custom_text('conclusion', self.conclusion_text.toPlainText())
        
        # Update stamps
        self.text_editor.set_stamp_data('architect', {
            'name': self.architect_name.text(),
            'date': self.architect_date.text()
        })
        
        self.text_editor.set_stamp_data('engineer', {
            'name': self.engineer_name.text(),
            'date': self.engineer_date.text()
        })
        
        return self.text_editor

