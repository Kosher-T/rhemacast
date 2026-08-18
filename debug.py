import sys
import os
import logging

# High DPI support - must be set before QApplication creation
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

logging.basicConfig(level=logging.DEBUG)
from core.ui import RhemaCastApp

print("Creating app instance")
app = RhemaCastApp(sys.argv)
# Main window is now shown after loading screen completes
print("OK — entering event loop")
sys.exit(app.exec())
