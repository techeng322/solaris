"""
Custom logging handler for GUI that captures logs and emits signals.
"""

import logging
from PyQt6.QtCore import QObject, pyqtSignal


class GUILogHandler(logging.Handler, QObject):
    """Custom logging handler that emits signals for GUI display."""
    
    log_message = pyqtSignal(str, str, str)  # message, level, formatted_message
    
    def __init__(self):
        logging.Handler.__init__(self)
        QObject.__init__(self)
        self.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        ))
    
    def emit(self, record):
        """Emit log record as signal."""
        try:
            msg = self.format(record)
            level = record.levelname
            self.log_message.emit(record.getMessage(), level, msg)
        except Exception:
            self.handleError(record)

