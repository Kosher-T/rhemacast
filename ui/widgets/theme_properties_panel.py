"""
ui/widgets/theme_properties_panel.py

Shared property editor panel for the theme designer.
Provides reusable row widgets (ColorRow, TextRow, FontRow, WeightRow, etc.)
and a main ThemePropertiesPanel that edits all theme properties and emits
theme_changed(dict) on every edit.
"""

import copy

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QFrame, QComboBox, QPushButton, QColorDialog, QScrollArea,
    QSizePolicy, QStackedWidget,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor

from ui.styles import SLATE_500, SLATE_400, WHITE, BLUE_500


# ─── Shared Styles ────────────────────────────────────────────────────────────

_INPUT_STYLE = (
    "background: rgba(0,0,0,0.3);"
    "border: 1px solid rgba(255,255,255,0.08);"
    "border-radius: 4px;"
    "padding: 2px 6px;"
    "color: #f8fafc;"
    "font-size: 10px;"
)

_LABEL_STYLE = (
    "background: transparent;"
    "border: none;"
    "color: #64748b;"
    "font-size: 10px;"
    "font-weight: 600;"
    "text-transform: uppercase;"
)

_COMBO_STYLE = (
    "QComboBox {"
    "  background: rgba(0,0,0,0.3);"
    "  border: 1px solid rgba(255,255,255,0.08);"
    "  border-radius: 4px;"
    "  padding: 2px 6px;"
    "  color: #f8fafc;"
    "  font-size: 10px;"
    "}"
    "QComboBox::drop-down {"
    "  border: none;"
    "  width: 14px;"
    "}"
    "QComboBox QAbstractItemView {"
    "  background: #1e293b;"
    "  color: #f8fafc;"
    "  border: 1px solid rgba(255,255,255,0.08);"
    "  selection-background-color: rgba(59,130,246,0.3);"
    "}"
)


# ─── Reusable Row Widgets ─────────────────────────────────────────────────────


class ColorRow(QWidget):
    """Label + color swatch + hex text input."""

    value_changed = pyqtSignal(str)

    def __init__(self, label_text: str, parent=None):
        super().__init__(parent)
        self.setFixedHeight(24)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(6)

        lbl = QLabel(label_text.upper())
        lbl.setFixedWidth(56)
        lbl.setStyleSheet(_LABEL_STYLE)
        layout.addWidget(lbl)

        self._swatch = QFrame()
        self._swatch.setFixedSize(22, 22)
        self._swatch.setCursor(Qt.CursorShape.PointingHandCursor)
        self._swatch.setStyleSheet(
            "background: #ffffff;"
            "border: 1px solid rgba(255,255,255,0.15);"
            "border-radius: 3px;"
        )
        self._swatch.mousePressEvent = lambda _: self._open_picker()
        layout.addWidget(self._swatch)

        self._hex = QLineEdit()
        self._hex.setFixedHeight(22)
        self._hex.setPlaceholderText("#000000")
        self._hex.setStyleSheet(_INPUT_STYLE)
        self._hex.textChanged.connect(self._on_hex_changed)
        self._hex.editingFinished.connect(self._on_hex_finished)
        layout.addWidget(self._hex, 1)

    def _open_picker(self):
        current = QColor(self._hex.text() if self._hex.text() else "#ffffff")
        dialog = QColorDialog(current, self)
        dialog.setOption(QColorDialog.ColorDialogOption.ShowAlphaChannel, True)
        dialog.setWindowTitle("Select Color")
        if dialog.exec():
            c = dialog.currentColor()
            if c.alpha() < 255:
                hex_str = f"rgba({c.red()},{c.green()},{c.blue()},{c.alpha()})"
            else:
                hex_str = c.name()
            self._hex.setText(hex_str)
            self._update_swatch(hex_str)

    def _update_swatch(self, color_str: str):
        if color_str.startswith("rgba"):
            parts = color_str.replace("rgba(", "").replace(")", "").split(",")
            r, g, b = int(parts[0]), int(parts[1]), int(parts[2])
            alpha = int(parts[3]) if len(parts) > 3 else 255
            if alpha < 255:
                self._swatch.setStyleSheet(
                    f"background: rgba({r},{g},{b},{alpha / 255:.2f});"
                    "border: 1px solid rgba(255,255,255,0.15);"
                    "border-radius: 3px;"
                )
            else:
                self._swatch.setStyleSheet(
                    f"background: #{r:02x}{g:02x}{b:02x};"
                    "border: 1px solid rgba(255,255,255,0.15);"
                    "border-radius: 3px;"
                )
        else:
            self._swatch.setStyleSheet(
                f"background: {color_str};"
                "border: 1px solid rgba(255,255,255,0.15);"
                "border-radius: 3px;"
            )

    def _on_hex_changed(self, text: str):
        self._update_swatch(text)

    def _on_hex_finished(self):
        self.value_changed.emit(self._hex.text())

    def set_value(self, value: str):
        self._hex.blockSignals(True)
        self._hex.setText(value)
        self._update_swatch(value)
        self._hex.blockSignals(False)

    def get_value(self) -> str:
        return self._hex.text()


class TextRow(QWidget):
    """Label + single QLineEdit."""

    value_changed = pyqtSignal(str)

    def __init__(self, label_text: str, placeholder: str = "", parent=None):
        super().__init__(parent)
        self.setFixedHeight(24)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(6)

        lbl = QLabel(label_text.upper())
        lbl.setFixedWidth(56)
        lbl.setStyleSheet(_LABEL_STYLE)
        layout.addWidget(lbl)

        self._input = QLineEdit()
        self._input.setFixedHeight(22)
        self._input.setPlaceholderText(placeholder)
        self._input.setStyleSheet(_INPUT_STYLE)
        self._input.textChanged.connect(lambda t: self.value_changed.emit(t))
        layout.addWidget(self._input, 1)

    def set_value(self, value: str):
        self._input.blockSignals(True)
        self._input.setText(str(value) if value is not None else "")
        self._input.blockSignals(False)

    def get_value(self) -> str:
        return self._input.text()


class FontRow(QWidget):
    """Label + QComboBox with font family options."""

    value_changed = pyqtSignal(str)

    FONTS = [
        "'Nunito', sans-serif",
        "'DM Sans', sans-serif",
        "Georgia, serif",
        "'Times New Roman', serif",
    ]

    def __init__(self, label_text: str, parent=None):
        super().__init__(parent)
        self.setFixedHeight(24)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(6)

        lbl = QLabel(label_text.upper())
        lbl.setFixedWidth(56)
        lbl.setStyleSheet(_LABEL_STYLE)
        layout.addWidget(lbl)

        self._combo = QComboBox()
        self._combo.setFixedHeight(22)
        self._combo.addItems(self.FONTS)
        self._combo.setStyleSheet(_COMBO_STYLE)
        self._combo.currentTextChanged.connect(lambda t: self.value_changed.emit(t))
        layout.addWidget(self._combo, 1)

    def set_value(self, value: str):
        self._combo.blockSignals(True)
        idx = self._combo.findText(value)
        if idx >= 0:
            self._combo.setCurrentIndex(idx)
        else:
            self._combo.setCurrentText(value)
        self._combo.blockSignals(False)

    def get_value(self) -> str:
        return self._combo.currentText()


class WeightRow(QWidget):
    """Label + QComboBox with font weight options."""

    value_changed = pyqtSignal(int)

    WEIGHTS = [
        ("Regular (400)", 400),
        ("Medium (500)", 500),
        ("Semi Bold (600)", 600),
        ("Bold (700)", 700),
        ("Extra Bold (800)", 800),
    ]

    def __init__(self, label_text: str, parent=None):
        super().__init__(parent)
        self.setFixedHeight(24)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(6)

        lbl = QLabel(label_text.upper())
        lbl.setFixedWidth(56)
        lbl.setStyleSheet(_LABEL_STYLE)
        layout.addWidget(lbl)

        self._combo = QComboBox()
        self._combo.setFixedHeight(22)
        for label, _ in self.WEIGHTS:
            self._combo.addItem(label)
        self._combo.setStyleSheet(_COMBO_STYLE)
        self._combo.currentIndexChanged.connect(self._on_changed)
        layout.addWidget(self._combo, 1)

    def _on_changed(self, index: int):
        if 0 <= index < len(self.WEIGHTS):
            self.value_changed.emit(self.WEIGHTS[index][1])

    def set_value(self, value: int):
        self._combo.blockSignals(True)
        for i, (_, w) in enumerate(self.WEIGHTS):
            if w == value:
                self._combo.setCurrentIndex(i)
                break
        self._combo.blockSignals(False)

    def get_value(self) -> int:
        idx = self._combo.currentIndex()
        if 0 <= idx < len(self.WEIGHTS):
            return self.WEIGHTS[idx][1]
        return 400


class SectionLabel(QLabel):
    """Tiny uppercase section heading."""

    def __init__(self, text: str, parent=None):
        super().__init__(text.upper(), parent)
        self.setStyleSheet(
            "background: transparent;"
            "border: none;"
            "color: #475569;"
            "font-size: 9px;"
            "font-weight: 700;"
            "text-transform: uppercase;"
            "letter-spacing: 1px;"
        )


class Divider(QFrame):
    """1px horizontal rule."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(1)
        self.setStyleSheet(
            "background: rgba(255,255,255,0.06);"
            "border: none;"
        )


class ElementToggle(QFrame):
    """Clickable row with label + toggle button for enabling/disabling a theme element."""

    focused = pyqtSignal(str)

    def __init__(self, element_key: str, display_name: str, parent=None):
        super().__init__(parent)
        self._element_key = element_key
        self._focused = False
        self._enabled = True
        self.setFixedHeight(28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(8)

        self._label = QLabel(display_name)
        self._label.setStyleSheet(
            "background: transparent;"
            "border: none;"
            "color: #94a3b8;"
            "font-size: 10px;"
            "font-weight: 600;"
        )
        layout.addWidget(self._label)

        layout.addStretch()

        self._toggle = QPushButton()
        self._toggle.setFixedSize(32, 18)
        self._toggle.setCheckable(True)
        self._toggle.setChecked(True)
        self._toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle.setStyleSheet(self._toggle_style(False))
        self._toggle.clicked.connect(self._on_toggle)
        layout.addWidget(self._toggle)

        self._apply_row_style()

    def _toggle_style(self, checked: bool) -> str:
        if checked:
            return (
                "QPushButton {"
                "  background: #3b82f6;"
                "  border: none;"
                "  border-radius: 9px;"
                "}"
                "QPushButton::indicator {"
                "  width: 14px; height: 14px;"
                "  border-radius: 7px;"
                "  background: white;"
                "  margin: 2px;"
                "}"
                "QPushButton:checked::indicator {"
                "  margin-left: 16px;"
                "}"
            )
        else:
            return (
                "QPushButton {"
                "  background: rgba(255,255,255,0.1);"
                "  border: none;"
                "  border-radius: 9px;"
                "}"
                "QPushButton::indicator {"
                "  width: 14px; height: 14px;"
                "  border-radius: 7px;"
                "  background: #64748b;"
                "  margin: 2px;"
                "}"
                "QPushButton:checked::indicator {"
                "  margin-left: 16px;"
                "}"
            )

    def _on_toggle(self, checked: bool):
        self._enabled = checked
        self._toggle.setStyleSheet(self._toggle_style(checked))
        self._apply_row_style()

    def _apply_row_style(self):
        if self._focused:
            self.setStyleSheet(
                "QFrame {"
                "  background: rgba(59,130,246,0.12);"
                "  border-left: 2px solid #3b82f6;"
                "  border-radius: 0;"
                "}"
            )
            self._label.setStyleSheet(
                "background: transparent;"
                "border: none;"
                "color: #f8fafc;"
                "font-size: 10px;"
                "font-weight: 600;"
            )
        else:
            self.setStyleSheet(
                "QFrame {"
                "  background: transparent;"
                "  border-left: 2px solid transparent;"
                "  border-radius: 0;"
                "}"
            )
            if self._enabled:
                self._label.setStyleSheet(
                    "background: transparent;"
                    "border: none;"
                    "color: #94a3b8;"
                    "font-size: 10px;"
                    "font-weight: 600;"
                )
            else:
                self._label.setStyleSheet(
                    "background: transparent;"
                    "border: none;"
                    "color: #475569;"
                    "font-size: 10px;"
                    "font-weight: 600;"
                )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.focused.emit(self._element_key)
        super().mousePressEvent(event)

    def set_focused(self, focused: bool):
        self._focused = focused
        self._apply_row_style()

    def is_enabled(self) -> bool:
        return self._enabled

    def get_key(self) -> str:
        return self._element_key


# ─── Main Panel ───────────────────────────────────────────────────────────────


class ThemePropertiesPanel(QWidget):
    """Property editor panel for themes. Emits theme_changed(dict) on every edit."""

    theme_changed = pyqtSignal(dict)

    ELEMENTS = [
        ("text", "Text"),
        ("reference", "Reference"),
        ("translation", "Translation"),
        ("verse_num", "Verse #"),
    ]

    CONTAINER_PROPS = [
        ("background", "Background"),
        ("border", "Border"),
        ("border_radius", "Radius"),
        ("box_shadow", "Shadow"),
        ("backdrop_filter", "Backdrop"),
        ("padding", "Padding"),
        ("width", "Width"),
        ("height", "Height"),
        ("max_width", "Max W"),
        ("min_width", "Min W"),
        ("flex_direction", "Direction"),
        ("justify_content", "Justify"),
        ("align_items", "Align"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loading = False
        self._active_element = "text"
        self._theme_name = "default"
        self._theme_label = "Default"

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Tab bar (Elements | Container) ──
        tab_bar = QFrame()
        tab_bar.setFixedHeight(32)
        tab_bar.setStyleSheet(
            "QFrame {"
            "  background: rgba(15,23,42,0.6);"
            "  border-bottom: 1px solid rgba(255,255,255,0.06);"
            "}"
        )
        tab_layout = QHBoxLayout(tab_bar)
        tab_layout.setContentsMargins(4, 4, 4, 4)
        tab_layout.setSpacing(2)

        self._tab_elements = QPushButton("Elements")
        self._tab_elements.setCheckable(True)
        self._tab_elements.setChecked(True)
        self._tab_elements.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tab_elements.setFixedHeight(24)
        self._tab_elements.clicked.connect(lambda: self._switch_tab("elements"))
        self._tab_elements.setStyleSheet(self._tab_btn_style(True))
        tab_layout.addWidget(self._tab_elements)

        self._tab_container = QPushButton("Container")
        self._tab_container.setCheckable(True)
        self._tab_container.setChecked(False)
        self._tab_container.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tab_container.setFixedHeight(24)
        self._tab_container.clicked.connect(lambda: self._switch_tab("container"))
        self._tab_container.setStyleSheet(self._tab_btn_style(False))
        tab_layout.addWidget(self._tab_container)

        tab_layout.addStretch()
        main_layout.addWidget(tab_bar)

        # ── Scrollable content area ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical { background: transparent; width: 5px; }"
            "QScrollBar::handle:vertical {"
            "  background: rgba(255,255,255,0.1);"
            "  border-radius: 2px;"
            "}"
        )

        self._content = QWidget()
        self._content.setStyleSheet("background: transparent;")
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(8, 8, 8, 8)
        self._content_layout.setSpacing(4)
        self._content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        scroll.setWidget(self._content)
        main_layout.addWidget(scroll, 1)

        # ── Build widgets ──
        self._element_toggles: dict[str, ElementToggle] = {}
        self._element_stacks: dict[str, QStackedWidget] = {}
        self._container_rows: dict[str, TextRow] = {}

        self._build_elements_tab()
        self._build_container_tab()

        self._show_tab("elements")

    # ── Tab switching ──────────────────────────────────────────────────────

    def _tab_btn_style(self, active: bool) -> str:
        if active:
            return (
                "QPushButton {"
                "  background: rgba(59,130,246,0.2);"
                "  color: #60a5fa;"
                "  border: none;"
                "  border-radius: 4px;"
                "  font-size: 10px;"
                "  font-weight: 700;"
                "  padding: 0 12px;"
                "}"
            )
        return (
            "QPushButton {"
            "  background: transparent;"
            "  color: #64748b;"
            "  border: none;"
            "  border-radius: 4px;"
            "  font-size: 10px;"
            "  font-weight: 700;"
            "  padding: 0 12px;"
            "}"
            "QPushButton:hover { color: #94a3b8; }"
        )

    def _switch_tab(self, tab: str):
        self._tab_elements.setChecked(tab == "elements")
        self._tab_container.setChecked(tab == "container")
        self._tab_elements.setStyleSheet(self._tab_btn_style(tab == "elements"))
        self._tab_container.setStyleSheet(self._tab_btn_style(tab == "container"))
        self._show_tab(tab)

    def _show_tab(self, tab: str):
        self._elements_widget.setVisible(tab == "elements")
        self._container_widget.setVisible(tab == "container")

    # ── Elements tab ───────────────────────────────────────────────────────

    def _build_elements_tab(self):
        self._elements_widget = QWidget()
        self._elements_widget.setStyleSheet("background: transparent;")
        el_layout = QVBoxLayout(self._elements_widget)
        el_layout.setContentsMargins(0, 0, 0, 0)
        el_layout.setSpacing(4)

        for key, display in self.ELEMENTS:
            toggle = ElementToggle(key, display)
            toggle.focused.connect(self._on_element_focused)
            self._element_toggles[key] = toggle
            el_layout.addWidget(toggle)

            stack = QStackedWidget()
            stack.setStyleSheet("background: transparent;")
            page = QWidget()
            page.setStyleSheet("background: transparent;")
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(8, 4, 4, 4)
            page_layout.setSpacing(2)
            page_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

            self._build_element_rows(key, page_layout)

            page_layout.addStretch()
            stack.addWidget(page)
            self._element_stacks[key] = stack
            el_layout.addWidget(stack)
            el_layout.addSpacing(2)

        el_layout.addStretch()
        self._content_layout.addWidget(self._elements_widget)

        self._on_element_focused("text")

    def _build_element_rows(self, key: str, layout: QVBoxLayout):
        if key == "text":
            self._text_font = FontRow("Font")
            self._text_color = ColorRow("Color")
            self._text_size = TextRow("Size", "44px")
            self._text_weight = WeightRow("Weight")
            self._text_line_height = TextRow("Line H", "1.08")
            self._text_spacing = TextRow("Spacing", "-0.02em")
            self._text_shadow = TextRow("Shadow", "none")
            self._text_min_size = TextRow("Min Sz", "38px")
            self._text_max_size = TextRow("Max Sz", "58px")

            for w in (
                self._text_font, self._text_color, self._text_size,
                self._text_weight, self._text_line_height, self._text_spacing,
                self._text_shadow, self._text_min_size, self._text_max_size,
            ):
                w.value_changed.connect(lambda _: self._on_edit())
                layout.addWidget(w)

        elif key == "reference":
            self._ref_font = FontRow("Font")
            self._ref_color = ColorRow("Color")
            self._ref_size = TextRow("Size", "34px")
            self._ref_weight = WeightRow("Weight")
            self._ref_transform = TextRow("Transform", "uppercase")
            self._ref_letter_spacing = TextRow("Letter Sp", "0.1em")

            for w in (
                self._ref_font, self._ref_color, self._ref_size,
                self._ref_weight, self._ref_transform, self._ref_letter_spacing,
            ):
                w.value_changed.connect(lambda _: self._on_edit())
                layout.addWidget(w)

        elif key == "translation":
            self._trans_color = ColorRow("Color")
            self._trans_margin = TextRow("Margin L", "8px")

            for w in (self._trans_color, self._trans_margin):
                w.value_changed.connect(lambda _: self._on_edit())
                layout.addWidget(w)

        elif key == "verse_num":
            self._vn_color = ColorRow("Color")
            self._vn_font = FontRow("Font")

            for w in (self._vn_color, self._vn_font):
                w.value_changed.connect(lambda _: self._on_edit())
                layout.addWidget(w)

    def _on_element_focused(self, key: str):
        self._active_element = key
        for k, toggle in self._element_toggles.items():
            toggle.set_focused(k == key)
        for k, stack in self._element_stacks.items():
            stack.setVisible(k == key)

    # ── Container tab ──────────────────────────────────────────────────────

    def _build_container_tab(self):
        self._container_widget = QWidget()
        self._container_widget.setStyleSheet("background: transparent;")
        c_layout = QVBoxLayout(self._container_widget)
        c_layout.setContentsMargins(0, 0, 0, 0)
        c_layout.setSpacing(4)

        c_layout.addWidget(SectionLabel("Container"))
        c_layout.addWidget(Divider())

        for key, display in self.CONTAINER_PROPS:
            row = TextRow(display)
            row.value_changed.connect(lambda _: self._on_edit())
            self._container_rows[key] = row
            c_layout.addWidget(row)

        c_layout.addStretch()
        self._content_layout.addWidget(self._container_widget)

    # ── Collect / load / get ───────────────────────────────────────────────

    def _on_edit(self):
        if self._loading:
            return
        theme = self._collect_theme()
        self.theme_changed.emit(theme)

    def _collect_theme(self) -> dict:
        """Read all widget values into a theme dict matching default.json structure."""
        theme: dict = {
            "name": self._theme_name,
            "label": self._theme_label,
            "container": {},
            "body": {
                "vertical_align": "center",
                "padding_bottom": "0",
            },
            "text": {},
            "reference": {},
            "translation": {},
            "verse_num": {},
        }

        # ── Container ──
        for key in self._container_rows:
            theme["container"][key] = self._container_rows[key].get_value()

        # Ensure display/flex properties always present
        theme["container"]["display"] = "flex"
        if "flex_direction" not in theme["container"] or not theme["container"]["flex_direction"]:
            theme["container"]["flex_direction"] = "column"
        if "justify_content" not in theme["container"] or not theme["container"]["justify_content"]:
            theme["container"]["justify_content"] = "center"
        if "align_items" not in theme["container"] or not theme["container"]["align_items"]:
            theme["container"]["align_items"] = "center"

        # ── Text ──
        if self._element_toggles["text"].is_enabled():
            theme["text"] = {
                "color": self._text_color.get_value(),
                "font_family": self._text_font.get_value(),
                "size": self._text_size.get_value(),
                "weight": self._text_weight.get_value(),
                "line_height": self._text_line_height.get_value(),
                "letter_spacing": self._text_spacing.get_value(),
                "text_shadow": self._text_shadow.get_value(),
                "min_size": self._text_min_size.get_value(),
                "max_size": self._text_max_size.get_value(),
            }

        # ── Reference ──
        if self._element_toggles["reference"].is_enabled():
            theme["reference"] = {
                "color": self._ref_color.get_value(),
                "font_family": self._ref_font.get_value(),
                "size": self._ref_size.get_value(),
                "weight": self._ref_weight.get_value(),
                "text_transform": self._ref_transform.get_value(),
                "letter_spacing": self._ref_letter_spacing.get_value(),
            }

        # ── Translation ──
        if self._element_toggles["translation"].is_enabled():
            theme["translation"] = {
                "color": self._trans_color.get_value(),
                "margin_left": self._trans_margin.get_value(),
            }

        # ── Verse number ──
        if self._element_toggles["verse_num"].is_enabled():
            theme["verse_num"] = {
                "color": self._vn_color.get_value(),
                "font_family": self._vn_font.get_value(),
            }

        return theme

    def load_theme(self, theme_dict: dict):
        """Populate all widgets from a theme dict."""
        self._loading = True
        theme = copy.deepcopy(theme_dict)
        self._theme_name = theme.get("name", "default")
        self._theme_label = theme.get("label", theme.get("name", "Default"))

        # ── Container ──
        container = theme.get("container", {})
        for key, row in self._container_rows.items():
            row.set_value(container.get(key, ""))

        # ── Text ──
        text = theme.get("text", {})
        self._text_color.set_value(text.get("color", "#ffffff"))
        self._text_font.set_value(text.get("font_family", "'Nunito', sans-serif"))
        self._text_size.set_value(text.get("size", "44px"))
        self._text_weight.set_value(text.get("weight", 700))
        self._text_line_height.set_value(text.get("line_height", "1.08"))
        self._text_spacing.set_value(text.get("letter_spacing", "-0.02em"))
        self._text_shadow.set_value(text.get("text_shadow", "none"))
        self._text_min_size.set_value(text.get("min_size", "38px"))
        self._text_max_size.set_value(text.get("max_size", "58px"))

        # ── Reference ──
        ref = theme.get("reference", {})
        self._ref_color.set_value(ref.get("color", "#cccccc"))
        self._ref_font.set_value(ref.get("font_family", "'Nunito', sans-serif"))
        self._ref_size.set_value(ref.get("size", "34px"))
        self._ref_weight.set_value(ref.get("weight", 500))
        self._ref_transform.set_value(ref.get("text_transform", "uppercase"))
        self._ref_letter_spacing.set_value(ref.get("letter_spacing", "0.1em"))

        # ── Translation ──
        trans = theme.get("translation", {})
        self._trans_color.set_value(trans.get("color", "#999999"))
        self._trans_margin.set_value(trans.get("margin_left", "8px"))

        # ── Verse number ──
        vn = theme.get("verse_num", {})
        self._vn_color.set_value(vn.get("color", "#cccccc"))
        self._vn_font.set_value(vn.get("font_family", "'Nunito', sans-serif"))

        # ── Element toggles (all enabled if present) ──
        for key, toggle in self._element_toggles.items():
            section = theme.get(key, {})
            toggle._toggle.setChecked(bool(section))
            toggle._enabled = bool(section)
            toggle._toggle.setStyleSheet(toggle._toggle_style(bool(section)))
            toggle._apply_row_style()

        self._loading = False

    def get_theme(self) -> dict:
        """Return the current theme dict."""
        return self._collect_theme()
