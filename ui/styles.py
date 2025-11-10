"""
Professional blue-toned fluorescent color scheme with black backgrounds and gradients.
"""

# Color palette - Intelligence Agency / Spy Movie Aesthetic
COLORS = {
    # Primary blues (luminescent, subtle glow)
    'primary_blue': '#00D4FF',      # Bright cyan-blue (luminescent)
    'bright_blue': '#00A8CC',       # Medium cyan-blue
    'cyan': '#00FFFF',              # Pure cyan (data highlight)
    'electric_blue': '#0099CC',     # Deep cyan-blue
    'neon_blue': '#0066CC',         # Deep blue glow
    'luminescent': '#00FFE5',       # Bright luminescent cyan
    
    # Backgrounds (deep black tones with subtle blue tint)
    'bg_dark': '#0A0E14',           # Almost black with blue tint
    'bg_darker': '#05080A',         # Very dark with blue tint
    'bg_medium': '#151A20',         # Dark gray-blue
    'bg_light': '#1F2830',          # Medium dark blue-gray
    'bg_panel': '#0F1419',          # Panel background
    
    # Text (high contrast, readable)
    'text_primary': '#E0F0FF',      # Soft white-blue
    'text_secondary': '#A0B8CC',   # Light blue-gray
    'text_muted': '#708090',        # Steel blue-gray
    'text_data': '#00FFFF',         # Cyan for data values
    
    # Accents (subtle but revealing)
    'accent_blue': '#00B8E6',        # Medium cyan-blue
    'accent_cyan': '#00E6FF',       # Bright cyan accent
    'glow_blue': '#004D66',         # Deep blue glow
    'glow_cyan': '#006680',         # Cyan glow
    
    # Status colors (subtle luminescent)
    'success': '#00FF99',           # Green-cyan (luminescent)
    'warning': '#FFCC00',          # Amber-gold
    'error': '#FF3366',             # Red-pink
    'info': '#00CCFF',              # Info cyan
    
    # Gradients (spy movie aesthetic)
    'gradient_start': '#000A14',    # Deep blue-black
    'gradient_mid': '#001A2E',      # Medium blue-black
    'gradient_end': '#002A48',      # Dark blue
    'gradient_glow': '#003D5C',     # Glow gradient
}

def get_main_window_style():
    """Get main window stylesheet - Intelligence agency aesthetic."""
    return f"""
    QMainWindow {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {COLORS['gradient_start']},
            stop:0.3 {COLORS['gradient_mid']},
            stop:0.7 {COLORS['bg_darker']},
            stop:1 {COLORS['bg_dark']});
        color: {COLORS['text_primary']};
    }}
    
    QWidget {{
        background: transparent;
        color: {COLORS['text_primary']};
    }}
    """

def get_button_style(style_type='primary'):
    """Get button stylesheet - Intelligence agency aesthetic."""
    if style_type == 'primary':
        return f"""
        QPushButton {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {COLORS['bg_light']},
                stop:0.3 {COLORS['bg_medium']},
                stop:1 {COLORS['bg_dark']});
            color: {COLORS['luminescent']};
            border: 1px solid {COLORS['primary_blue']};
            border-radius: 6px;
            padding: 10px 20px;
            font-family: 'Segoe UI', 'Roboto', 'Arial', sans-serif;
            font-weight: 600;
            font-size: 12px;
            letter-spacing: 0.5px;
        }}
        QPushButton:hover {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {COLORS['bg_medium']},
                stop:0.5 {COLORS['bg_light']},
                stop:1 {COLORS['bg_medium']});
            border: 1px solid {COLORS['luminescent']};
            color: {COLORS['text_primary']};
        }}
        QPushButton:pressed {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {COLORS['bg_dark']},
                stop:1 {COLORS['bg_medium']});
            border: 1px solid {COLORS['accent_cyan']};
        }}
        """
    elif style_type == 'secondary':
        return f"""
        QPushButton {{
            background: {COLORS['bg_panel']};
            color: {COLORS['text_secondary']};
            border: 1px solid {COLORS['glow_blue']};
            border-radius: 5px;
            padding: 8px 16px;
            font-family: 'Segoe UI', 'Roboto', 'Arial', sans-serif;
            font-weight: 500;
            font-size: 11px;
            letter-spacing: 0.3px;
        }}
        QPushButton:hover {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {COLORS['bg_medium']},
                stop:1 {COLORS['bg_light']});
            border: 1px solid {COLORS['primary_blue']};
            color: {COLORS['accent_cyan']};
        }}
        """
    else:  # default
        return f"""
        QPushButton {{
            background: {COLORS['bg_medium']};
            color: {COLORS['text_primary']};
            border: 1px solid {COLORS['bg_light']};
            border-radius: 5px;
            padding: 6px 12px;
        }}
        QPushButton:hover {{
            background: {COLORS['bg_light']};
            border: 1px solid {COLORS['primary_blue']};
        }}
        """

def get_groupbox_style():
    """Get groupbox stylesheet - Intelligence panel aesthetic."""
    return f"""
    QGroupBox {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {COLORS['bg_panel']},
            stop:0.5 {COLORS['bg_medium']},
            stop:1 {COLORS['bg_panel']});
        border: 1px solid {COLORS['glow_blue']};
        border-radius: 6px;
        margin-top: 12px;
        padding-top: 18px;
        font-family: 'Segoe UI', 'Roboto', 'Arial', sans-serif;
        font-weight: 600;
        font-size: 12px;
        color: {COLORS['accent_cyan']};
        letter-spacing: 0.5px;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 2px 10px;
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {COLORS['bg_darker']},
            stop:1 {COLORS['bg_dark']});
        color: {COLORS['luminescent']};
        border: 1px solid {COLORS['primary_blue']};
        border-radius: 3px;
    }}
    """

def get_label_style():
    """Get label stylesheet."""
    return f"""
    QLabel {{
        color: {COLORS['text_primary']};
        background: transparent;
        font-family: 'Segoe UI', 'Roboto', 'Arial', sans-serif;
        font-size: 11px;
    }}
    """

def get_lineedit_style():
    """Get line edit stylesheet."""
    return f"""
    QLineEdit, QDateEdit, QComboBox {{
        background: {COLORS['bg_medium']};
        color: {COLORS['text_primary']};
        border: 1px solid {COLORS['bg_light']};
        border-radius: 4px;
        padding: 6px;
        font-family: 'Segoe UI', 'Roboto', 'Arial', sans-serif;
        font-size: 11px;
    }}
    QLineEdit:focus, QDateEdit:focus, QComboBox:focus {{
        border: 2px solid {COLORS['primary_blue']};
        background: {COLORS['bg_light']};
    }}
    QComboBox::drop-down {{
        border: none;
        background: {COLORS['primary_blue']};
    }}
    QComboBox::down-arrow {{
        image: none;
        border-left: 4px solid transparent;
        border-right: 4px solid transparent;
        border-top: 6px solid {COLORS['text_primary']};
    }}
    QComboBox QAbstractItemView {{
        background: {COLORS['bg_medium']};
        color: {COLORS['text_primary']};
        selection-background-color: {COLORS['primary_blue']};
        selection-color: {COLORS['text_primary']};
    }}
    """

def get_table_style():
    """Get table stylesheet - Data terminal aesthetic."""
    return f"""
    QTableWidget {{
        background: {COLORS['bg_darker']};
        color: {COLORS['text_primary']};
        border: 1px solid {COLORS['glow_blue']};
        border-radius: 4px;
        gridline-color: {COLORS['glow_blue']};
        font-size: 13px;
        font-family: 'Segoe UI', 'Roboto', 'Arial', sans-serif;
    }}
    QTableWidget::item {{
        padding: 8px;
        border: none;
        background: transparent;
        font-size: 13px;
    }}
    QTableWidget::item:alternate {{
        background: {COLORS['bg_panel']};
    }}
    QTableWidget::item:selected {{
        background: {COLORS['bg_medium']};
        color: {COLORS['luminescent']};
        border: 2px solid {COLORS['primary_blue']};
        font-weight: 600;
    }}
    QHeaderView::section {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {COLORS['bg_medium']},
            stop:1 {COLORS['bg_dark']});
        color: {COLORS['luminescent']};
        padding: 10px;
        border: 1px solid {COLORS['glow_blue']};
        border-bottom: 2px solid {COLORS['primary_blue']};
        font-family: 'Segoe UI', 'Roboto', 'Arial', sans-serif;
        font-weight: 600;
        font-size: 14px;
        letter-spacing: 0.5px;
    }}
    """

def get_tab_style():
    """Get tab widget stylesheet - Intelligence interface aesthetic."""
    return f"""
    QTabWidget::pane {{
        background: {COLORS['bg_darker']};
        border: 1px solid {COLORS['glow_blue']};
        border-radius: 4px;
        top: -1px;
    }}
    QTabBar::tab {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {COLORS['bg_panel']},
            stop:1 {COLORS['bg_dark']});
        color: {COLORS['text_muted']};
        border: 1px solid {COLORS['glow_blue']};
        border-bottom: none;
        border-top-left-radius: 4px;
        border-top-right-radius: 4px;
        padding: 8px 20px;
        margin-right: 1px;
        font-family: 'Segoe UI', 'Roboto', 'Arial', sans-serif;
        font-weight: 500;
        font-size: 11px;
        letter-spacing: 0.3px;
    }}
    QTabBar::tab:selected {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {COLORS['bg_medium']},
            stop:1 {COLORS['bg_darker']});
        color: {COLORS['luminescent']};
        border: 1px solid {COLORS['primary_blue']};
        border-bottom: 2px solid {COLORS['bg_darker']};
        font-weight: 600;
    }}
    QTabBar::tab:hover {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {COLORS['bg_light']},
            stop:1 {COLORS['bg_medium']});
        color: {COLORS['accent_cyan']};
        border: 1px solid {COLORS['primary_blue']};
    }}
    """

def get_textedit_style():
    """Get text edit stylesheet - Terminal/console aesthetic."""
    return f"""
    QTextEdit {{
        background: {COLORS['bg_darker']};
        color: {COLORS['text_data']};
        border: 1px solid {COLORS['glow_blue']};
        border-radius: 4px;
        padding: 10px;
        font-family: 'Consolas', 'Courier New', 'Monaco', 'Menlo', monospace;
        font-size: 11px;
        selection-background-color: {COLORS['glow_cyan']};
        selection-color: {COLORS['text_primary']};
    }}
    QTextEdit:focus {{
        border: 1px solid {COLORS['primary_blue']};
    }}
    """

def get_progressbar_style():
    """Get progress bar stylesheet - Data transfer aesthetic."""
    return f"""
    QProgressBar {{
        background: {COLORS['bg_panel']};
        border: 1px solid {COLORS['glow_blue']};
        border-radius: 4px;
        text-align: center;
        color: {COLORS['luminescent']};
        font-weight: 600;
        font-size: 10px;
        height: 18px;
        font-family: 'Consolas', monospace;
    }}
    QProgressBar::chunk {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {COLORS['glow_cyan']},
            stop:0.3 {COLORS['primary_blue']},
            stop:0.7 {COLORS['accent_cyan']},
            stop:1 {COLORS['luminescent']});
        border-radius: 3px;
        border: 1px solid {COLORS['primary_blue']};
    }}
    """

def get_menu_style():
    """Get menu bar stylesheet - Intelligence interface aesthetic."""
    return f"""
    QMenuBar {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {COLORS['bg_dark']},
            stop:1 {COLORS['bg_darker']});
        color: {COLORS['text_secondary']};
        border-bottom: 1px solid {COLORS['glow_blue']};
        padding: 4px;
    }}
    QMenuBar::item {{
        background: transparent;
        padding: 6px 12px;
        border-radius: 3px;
        font-family: 'Segoe UI', 'Roboto', 'Arial', sans-serif;
        font-weight: 500;
        letter-spacing: 0.3px;
    }}
    QMenuBar::item:selected {{
        background: {COLORS['bg_medium']};
        color: {COLORS['luminescent']};
        border: 1px solid {COLORS['primary_blue']};
    }}
    QMenu {{
        background: {COLORS['bg_panel']};
        color: {COLORS['text_primary']};
        border: 1px solid {COLORS['glow_blue']};
        border-radius: 4px;
        padding: 4px;
    }}
    QMenu::item {{
        padding: 6px 30px;
        border-radius: 3px;
        font-family: 'Segoe UI', 'Roboto', 'Arial', sans-serif;
        font-size: 11px;
    }}
    QMenu::item:selected {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {COLORS['glow_cyan']},
            stop:1 {COLORS['primary_blue']});
        color: {COLORS['text_primary']};
        border: 1px solid {COLORS['accent_cyan']};
    }}
    QMenu::separator {{
        height: 1px;
        background: {COLORS['glow_blue']};
        margin: 4px 8px;
    }}
    """

def get_complete_stylesheet():
    """Get complete application stylesheet."""
    return (
        get_main_window_style() +
        get_button_style('primary') +
        get_button_style('secondary') +
        get_button_style('default') +
        get_groupbox_style() +
        get_label_style() +
        get_lineedit_style() +
        get_table_style() +
        get_tab_style() +
        get_textedit_style() +
        get_progressbar_style() +
        get_menu_style()
    )

