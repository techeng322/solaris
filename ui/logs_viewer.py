"""
Logs viewer window for displaying real-time application logs with sophisticated terminal aesthetic.
"""

import sys
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTextEdit,
    QLabel, QGroupBox, QCheckBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QTextCharFormat, QColor, QFont, QTextCursor
from ui.translations import Translations
from ui.styles import COLORS, get_button_style


class LogsViewerWidget(QWidget):
    """Widget for viewing application logs in real-time with hacker terminal aesthetic."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        self.auto_scroll = True
        # Add a test message to verify the widget can display text
        self.add_log("Logs viewer initialized - ready to receive logs", "INFO", "Logs viewer initialized - ready to receive logs")
    
    def init_ui(self):
        """Initialize UI with sophisticated terminal aesthetic."""
        t = Translations
        
        # Apply sophisticated terminal styling
        self.setStyleSheet(f"""
            QWidget {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #000000,
                    stop:0.3 {COLORS['bg_darker']},
                    stop:0.7 {COLORS['bg_dark']},
                    stop:1 #000000);
                color: {COLORS['text_primary']};
            }}
            QGroupBox {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {COLORS['bg_medium']},
                    stop:1 {COLORS['bg_light']});
                border: 2px solid {COLORS['primary_blue']};
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 15px;
                font-family: 'Consolas', 'Courier New', 'Monaco', 'Menlo', monospace;
                font-weight: bold;
                font-size: 12px;
                color: {COLORS['primary_blue']};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 8px;
                background: {COLORS['bg_dark']};
                color: {COLORS['cyan']};
                border: 1px solid {COLORS['primary_blue']};
                border-radius: 3px;
            }}
            QLabel {{
                color: {COLORS['text_primary']};
                background: transparent;
                font-family: 'Consolas', 'Courier New', 'Monaco', 'Menlo', monospace;
            }}
            QCheckBox {{
                color: {COLORS['text_primary']};
                font-family: 'Consolas', 'Courier New', 'Monaco', 'Menlo', monospace;
                font-size: 11px;
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border: 2px solid {COLORS['primary_blue']};
                border-radius: 3px;
                background: {COLORS['bg_medium']};
            }}
            QCheckBox::indicator:checked {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {COLORS['primary_blue']},
                    stop:1 {COLORS['electric_blue']});
                border: 2px solid {COLORS['cyan']};
            }}
        """)
        
        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)
        self.setLayout(layout)
        
        # Header with terminal-style prompt
        header = QLabel(">>> SOLARIS LOGS TERMINAL <<<")
        header.setStyleSheet(f"""
            QLabel {{
                color: {COLORS['cyan']};
                font-family: 'Consolas', 'Courier New', 'Monaco', 'Menlo', monospace;
                font-weight: bold;
                font-size: 14px;
                letter-spacing: 2px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {COLORS['bg_darker']},
                    stop:0.5 {COLORS['bg_dark']},
                    stop:1 {COLORS['bg_darker']});
                border: 1px solid {COLORS['primary_blue']};
                border-radius: 4px;
                padding: 8px;
            }}
        """)
        layout.addWidget(header)
        
        # Controls
        controls = QGroupBox("Controls / Управление")
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(10)
        
        clear_btn = QPushButton("Clear Logs / Очистить логи")
        clear_btn.setStyleSheet(get_button_style('secondary'))
        clear_btn.clicked.connect(self.clear_logs)
        controls_layout.addWidget(clear_btn)
        
        self.auto_scroll_checkbox = QCheckBox("Auto-scroll / Автопрокрутка")
        self.auto_scroll_checkbox.setChecked(True)
        self.auto_scroll_checkbox.toggled.connect(self.on_auto_scroll_toggled)
        controls_layout.addWidget(self.auto_scroll_checkbox)
        
        controls_layout.addStretch()
        
        self.log_count_label = QLabel("Logs: 0 / Логи: 0")
        self.log_count_label.setStyleSheet(f"""
            QLabel {{
                color: {COLORS['cyan']};
                font-family: 'Consolas', 'Courier New', 'Monaco', 'Menlo', monospace;
                font-weight: bold;
                font-size: 12px;
                background: {COLORS['bg_dark']};
                border: 1px solid {COLORS['primary_blue']};
                border-radius: 4px;
                padding: 6px 12px;
            }}
        """)
        controls_layout.addWidget(self.log_count_label)
        
        controls.setLayout(controls_layout)
        layout.addWidget(controls)
        
        # Log text area with sophisticated terminal styling
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        # Use larger, professional monospace font
        terminal_font = QFont("Consolas", 13)
        terminal_font.setStyleHint(QFont.StyleHint.Monospace)
        terminal_font.setFixedPitch(True)
        self.log_text.setFont(terminal_font)
        
        self.log_text.setStyleSheet(f"""
            QTextEdit {{
                background: #000000;
                color: {COLORS['cyan']};
                border: 2px solid {COLORS['primary_blue']};
                border-radius: 6px;
                padding: 12px;
                font-family: 'Consolas', 'Courier New', 'Monaco', 'Menlo', monospace;
                font-size: 13px;
                line-height: 1.6;
            }}
        """)
        layout.addWidget(self.log_text)
        
        self.log_count = 0
    
    def add_log(self, message: str, level: str = "INFO", formatted_message: str = None):
        """Add a log message to the viewer with sophisticated terminal formatting."""
        if formatted_message:
            display_message = formatted_message
        else:
            display_message = message
        
        # Get current timestamp for terminal-style display
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]  # Include milliseconds
        
        # Create terminal-style prefix with timestamp and level
        level_symbols = {
            "ERROR": "✗",
            "WARNING": "⚠",
            "INFO": "→",
            "DEBUG": "•"
        }
        symbol = level_symbols.get(level, "→")
        
        # Format: [HH:MM:SS.mmm] [LEVEL] message
        terminal_prefix = f"[{timestamp}] [{level:5s}] {symbol} "
        
        # Color coding based on level with terminal aesthetic
        format = QTextCharFormat()
        format.setFontWeight(QFont.Weight.Bold)
        
        if level == "ERROR":
            format.setForeground(QColor("#ff6b6b"))  # Bright red
            format.setBackground(QColor("#2a0000"))  # Subtle red background
        elif level == "WARNING":
            format.setForeground(QColor("#ffd93d"))  # Bright yellow
            format.setBackground(QColor("#2a2a00"))  # Subtle yellow background
        elif level == "INFO":
            format.setForeground(QColor("#4ec9b0"))  # Cyan
            format.setBackground(QColor("#001a1a"))  # Subtle cyan background
        elif level == "DEBUG":
            format.setForeground(QColor("#808080"))  # Gray
            format.setBackground(QColor("#1a1a1a"))  # Subtle gray background
        else:
            format.setForeground(QColor("#d4d4d4"))  # Light gray
            format.setBackground(QColor("#1a1a1a"))
        
        cursor = self.log_text.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        
        # Insert timestamp with subtle color
        timestamp_format = QTextCharFormat()
        timestamp_format.setForeground(QColor("#666666"))
        timestamp_format.setFontWeight(QFont.Weight.Normal)
        cursor.setCharFormat(timestamp_format)
        cursor.insertText(f"[{timestamp}] ")
        
        # Insert level with appropriate color
        level_format = QTextCharFormat()
        level_format.setForeground(format.foreground().color())
        level_format.setFontWeight(QFont.Weight.Bold)
        cursor.setCharFormat(level_format)
        cursor.insertText(f"[{level:5s}] ")
        
        # Insert symbol
        symbol_format = QTextCharFormat()
        symbol_format.setForeground(format.foreground().color())
        symbol_format.setFontWeight(QFont.Weight.Bold)
        cursor.setCharFormat(symbol_format)
        cursor.insertText(f"{symbol} ")
        
        # Insert message with main format
        cursor.setCharFormat(format)
        cursor.insertText(display_message + "\n")
        
        if self.auto_scroll:
            self.log_text.ensureCursorVisible()
        
        self.log_count += 1
        self.log_count_label.setText(f"Logs: {self.log_count} / Логи: {self.log_count}")
    
    def clear_logs(self):
        """Clear all logs."""
        self.log_text.clear()
        self.log_count = 0
        self.log_count_label.setText("Logs: 0 / Логи: 0")
        # Add a clear confirmation message
        self.add_log("Logs cleared - terminal ready", "INFO", "Logs cleared - terminal ready")
    
    def on_auto_scroll_toggled(self, checked):
        """Handle auto-scroll checkbox toggle."""
        self.auto_scroll = checked

# Backward compatibility alias
LogsViewerWindow = LogsViewerWidget
