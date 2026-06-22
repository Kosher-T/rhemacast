import sys
import logging
logging.basicConfig(level=logging.DEBUG)
from PyQt6.QtWidgets import QApplication

print("Importing RhemaCastApp")
from core.ui import RhemaCastApp

print("Creating app instance")
app = RhemaCastApp(sys.argv)
print("OK")
