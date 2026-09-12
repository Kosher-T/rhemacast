import sys
import os
import logging


def _maybe_filter_desktop_noise():
    """Re-launch with COSMIC/Wayland console spam filtered from stderr.

    On COSMIC, the terminal itself logs Rust-formatted lines like
    `cosmic::theme ... frosted_maximized_apps ... NotFound` (a system key
    absent from cosmic-settings) and `winit_wayland ... not supported`.
    That is the desktop environment, not RhemaCast — but it lands on our
    console. Narrow patterns only; every other line passes through.
    """
    if os.environ.get("RHEMACAST_STDERR_FILTERED") or os.name != "posix":
        return
    try:
        import subprocess
        env = dict(os.environ, RHEMACAST_STDERR_FILTERED="1",
                   RHEMACAST_NOISE_RE=r"cosmic::theme|winit_wayland::window::state")
        proc = subprocess.Popen(
            ["bash", "-c",
             'exec "$@" 2> >(grep -v -E "$RHEMACAST_NOISE_RE")',
             "_", sys.executable, *sys.argv],
            env=env,
        )
        sys.exit(proc.wait())
    except Exception:
        return  # fall through unfiltered


_maybe_filter_desktop_noise()

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
