"""
ui/theme.py

Centralized theme system using QPalette for native-looking, accessible theming.
Replaces hard-coded QSS colors with semantic color roles.
"""

from PyQt6.QtGui import QPalette, QColor
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt


class Theme:
    """Defines a complete theme palette for light/dark modes."""

    def __init__(self, name: str, colors: dict):
        self.name = name
        self.colors = colors

    def apply(self, palette: QPalette):
        """Apply this theme to a QPalette."""
        for role, color in self.colors.items():
            palette.setColor(getattr(QPalette.ColorRole, role), QColor(color))
        return palette


# Base semantic colors shared by both themes
BASE_COLORS = {
    # Text
    "Text": "#f8fafc",           # Primary text (slate-50)
    "PlaceholderText": "#64748b", # Placeholder/muted text (slate-500)
    "ToolTipText": "#f8fafc",    # Tooltip text
    # Window/Background
    "Window": "#020617",         # Main background (slate-950)
    "WindowText": "#f8fafc",     # Text on window
    "Base": "#0f172a",           # Input/editor background (slate-900)
    "AlternateBase": "#1e293b",  # Alternate rows (slate-800)
    # Buttons/Controls
    "Button": "#334155",         # Button background (slate-700)
    "ButtonText": "#f8fafc",     # Button text
    "BrightText": "#ef4444",     # Error/destructive text
    # Highlight/Selection
    "Highlight": "#3b82f6",      # Selection background (blue-500)
    "HighlightedText": "#f8fafc",# Selection text
    # Links
    "Link": "#60a5fa",           # Links (blue-400)
    "LinkVisited": "#a78bfa",    # Visited links (violet-400)
    # Borders/Edges
    "Mid": "#475569",            # Mid-tone for borders (slate-600)
    "Dark": "#1e293b",           # Dark borders (slate-800)
    "Shadow": "#000000",         # Shadows
    # Tooltips
    "ToolTipBase": "#1e293b",    # Tooltip background (slate-800)
    "ToolTipText": "#f8fafc",    # Tooltip text
}


DARK_THEME = Theme("dark", BASE_COLORS)

# Light theme (for accessibility/preference)
LIGHT_COLORS = {
    "Text": "#0f172a",
    "PlaceholderText": "#64748b",
    "ToolTipText": "#0f172a",
    "Window": "#f8fafc",
    "WindowText": "#0f172a",
    "Base": "#ffffff",
    "AlternateBase": "#f1f5f9",
    "Button": "#e2e8f0",
    "ButtonText": "#0f172a",
    "BrightText": "#dc2626",
    "Highlight": "#2563eb",
    "HighlightedText": "#ffffff",
    "Link": "#2563eb",
    "LinkVisited": "#7c3aed",
    "Mid": "#94a3b8",
    "Dark": "#cbd5e1",
    "Shadow": "#000000",
    "ToolTipBase": "#f1f5f9",
    "ToolTipText": "#0f172a",
}
LIGHT_THEME = Theme("light", LIGHT_COLORS)


def create_palette(theme_name: str = "dark") -> QPalette:
    """Create a QPalette with the specified theme."""
    palette = QPalette()
    if theme_name == "light":
        LIGHT_THEME.apply(palette)
    else:
        DARK_THEME.apply(palette)
    return palette


def apply_theme(app: QApplication, theme_name: str = "dark"):
    """Apply theme to the entire application."""
    app.setPalette(create_palette(theme_name))


# Semantic accent colors for custom widgets (not in QPalette)
ACCENTS = {
    "cyan": "#22d3ee",      # Primary brand
    "cyan_hover": "#06b6d4",
    "amber": "#f59e0b",     # Warning/queue
    "amber_hover": "#fbbf24",
    "emerald": "#10b981",   # Success/show
    "emerald_hover": "#34d399",
    "red": "#ef4444",       # Error/reject
    "red_hover": "#f87171",
    "blue": "#3b82f6",      # Info/links
    "blue_hover": "#60a5fa",
    "violet": "#a855f7",    # Theme/accent
    "slate": "#64748b",     # Neutral
}

# Focus ring color (for accessibility)
FOCUS_COLOR = ACCENTS["cyan"]
FOCUS_WIDTH = 2