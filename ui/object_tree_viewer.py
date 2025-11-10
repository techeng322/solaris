"""
Object tree viewer for displaying building hierarchy.
"""

from typing import Optional, Dict, Any
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QTreeWidgetItemIterator, QLineEdit, QLabel, QPushButton, QGroupBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from ui.styles import COLORS, get_button_style
from models.building import Building, Window


class ObjectTreeViewerWidget(QWidget):
    """Tree viewer widget for building hierarchy (embedded in main window)."""
    
    # Signal emitted when an item is selected
    item_selected = pyqtSignal(object)  # Emits the selected object (Building, Window, etc.)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.building = None
        self.init_ui()
    
    def init_ui(self):
        """Initialize UI."""
        
        # Apply styling
        self.setStyleSheet(f"""
            QWidget {{
                background: {COLORS['bg_dark']};
                color: {COLORS['text_primary']};
            }}
            QTreeWidget {{
                background: {COLORS['bg_darker']};
                color: {COLORS['text_primary']};
                border: 1px solid {COLORS['primary_blue']};
                border-radius: 4px;
                font-size: 11px;
            }}
            QTreeWidget::item {{
                padding: 4px;
            }}
            QTreeWidget::item:selected {{
                background: {COLORS['primary_blue']};
                color: {COLORS['text_primary']};
            }}
            QTreeWidget::item:hover {{
                background: {COLORS['bg_medium']};
            }}
            QLineEdit {{
                background: {COLORS['bg_medium']};
                color: {COLORS['text_primary']};
                border: 1px solid {COLORS['primary_blue']};
                border-radius: 4px;
                padding: 5px;
                font-size: 11px;
            }}
            QLabel {{
                color: {COLORS['text_primary']};
                background: transparent;
            }}
        """)
        
        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)
        self.setLayout(layout)
        
        # Title
        title = QLabel("Object Tree / Дерево объектов")
        title.setStyleSheet(f"""
            QLabel {{
                font-size: 14px;
                font-weight: bold;
                color: {COLORS['cyan']};
                padding: 5px;
            }}
        """)
        layout.addWidget(title)
        
        # Search box
        search_layout = QHBoxLayout()
        search_label = QLabel("Search / Поиск:")
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search objects... / Поиск объектов...")
        self.search_input.textChanged.connect(self.filter_tree)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_input)
        layout.addLayout(search_layout)
        
        # Selection status
        self.selection_label = QLabel("0 objects selected / 0 объектов выбрано")
        self.selection_label.setStyleSheet(f"""
            QLabel {{
                font-size: 10px;
                color: {COLORS['cyan']};
                padding: 3px;
            }}
        """)
        layout.addWidget(self.selection_label)
        
        # Tree widget
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Object / Объект", "Details / Детали"])
        self.tree.setColumnWidth(0, 250)
        self.tree.setColumnWidth(1, 150)
        self.tree.itemSelectionChanged.connect(self.on_selection_changed)
        self.tree.itemDoubleClicked.connect(self.on_item_double_clicked)
        layout.addWidget(self.tree)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        expand_btn = QPushButton("Expand All / Развернуть все")
        expand_btn.setStyleSheet(get_button_style('secondary'))
        expand_btn.clicked.connect(self.tree.expandAll)
        button_layout.addWidget(expand_btn)
        
        collapse_btn = QPushButton("Collapse All / Свернуть все")
        collapse_btn.setStyleSheet(get_button_style('secondary'))
        collapse_btn.clicked.connect(self.tree.collapseAll)
        button_layout.addWidget(collapse_btn)
        
        layout.addLayout(button_layout)
    
    def set_building(self, building: Optional[Building]):
        """Set building to display in tree."""
        self.building = building
        self.refresh_tree()
    
    def refresh_tree(self):
        """Refresh the tree with current building data."""
        self.tree.clear()
        
        if self.building is None:
            return
        
        # Create building root item
        building_item = QTreeWidgetItem(self.tree)
        building_item.setText(0, f"BUILDING {self.building.id}")
        building_item.setText(1, f"{len(self.building.windows)} windows")
        building_item.setData(0, Qt.ItemDataRole.UserRole, self.building)
        building_item.setExpanded(True)
        
        # Add windows directly under building
        for window in self.building.windows:
            window_item = QTreeWidgetItem(building_item)
            window_item.setText(0, f"Window {window.id}")
            
            window_details = []
            if window.size:
                area = window.get_area()
                window_details.append(f"Area: {area:.2f} m²")
                window_details.append(f"Size: {window.size[0]:.2f}×{window.size[1]:.2f} m")
            if window.window_type:
                window_details.append(f"Type: {window.window_type}")
            
            window_item.setText(1, ", ".join(window_details) if window_details else "")
            window_item.setData(0, Qt.ItemDataRole.UserRole, window)
    
    def filter_tree(self, text: str):
        """Filter tree items based on search text."""
        if not text:
            # Show all items - expand all
            self.tree.expandAll()
            return
        
        text_lower = text.lower()
        
        # Expand all and highlight matching items
        self.tree.expandAll()
        
        # Highlight matching items
        iterator = QTreeWidgetItemIterator(self.tree)
        while iterator.value():
            item = iterator.value()
            item_text = item.text(0).lower()
            if text_lower in item_text:
                # Scroll to first match
                if not hasattr(self, '_first_match'):
                    self.tree.scrollToItem(item)
                    self._first_match = True
            iterator += 1
        
        # Reset flag for next search
        if hasattr(self, '_first_match'):
            delattr(self, '_first_match')
    
    def on_selection_changed(self):
        """Handle selection change."""
        selected_items = self.tree.selectedItems()
        count = len(selected_items)
        self.selection_label.setText(f"{count} object(s) selected / {count} объектов выбрано")
        
        if selected_items:
            item = selected_items[0]
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data:
                self.item_selected.emit(data)
    
    def on_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle double-click on item."""
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data:
            self.item_selected.emit(data)

# Backward compatibility alias
ObjectTreeViewer = ObjectTreeViewerWidget

