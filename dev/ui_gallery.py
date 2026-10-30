"""Developer gallery for the RhemaCast dialog / popup language.

Not part of the app: nothing in ``core/`` or ``ui/`` imports this file, and
it is not packaged. It exists so the same dialogs, combos, menus and tooltip
can be opened side by side on Linux and Windows while comparing pixels.

Run from the repository root (the script adds the repo root to sys.path):

    Linux:    venv/bin/python dev/ui_gallery.py
    Windows:  venv\\Scripts\\python.exe dev\\ui_gallery.py

The startup order mirrors ``core/ui.py`` exactly: Fusion base, application
stylesheet, app font, palette. That order is what keeps the platform theme
from substituting its own font family.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt6.QtWidgets import (
    QApplication, QComboBox, QFontComboBox, QGridLayout, QLabel, QMenu,
    QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from ui import dialogs, field_chrome, tokens
from ui.app_style import install as install_app_style
from ui.app_theme import apply_palette
from ui.popups import install_combo, menu_qss
from ui.typography import install as install_typography


def build_app() -> QApplication:
    app = QApplication(["rhemacast-ui-gallery"])
    install_app_style(app)

    from ui.popups import tooltip_qss
    from ui.tokens import scrollbar_qss
    app.setStyleSheet(scrollbar_qss() + "\n" + tooltip_qss())

    install_typography(app)
    apply_palette(app)
    return app


class Gallery(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RhemaCast — dialog & popup gallery (dev)")
        self.resize(900, 820)
        self._nonmodal: dialogs.MessageDialog | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(
            tokens.SPACE_16, tokens.SPACE_16,
            tokens.SPACE_16, tokens.SPACE_16)
        root.setSpacing(tokens.SPACE_16)

        heading = QLabel("Dialog & popup gallery")
        heading.setStyleSheet(
            f"color: {tokens.TEXT_PRIMARY}; font-size: {tokens.TYPE_TITLE}px;"
            f" font-weight: {tokens.WEIGHT_SEMIBOLD};")
        root.addWidget(heading)

        note = QLabel(
            "Every button opens the real production dialog. Compare this "
            "window and its popups on Linux and Windows.")
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {tokens.TEXT_MUTED};")
        root.addWidget(note)

        root.addLayout(self._message_section())
        root.addLayout(self._input_section())
        root.addLayout(self._settings_fields_section())
        root.addLayout(self._popup_section())
        root.addStretch(1)

        self._status = QLabel("last result: —")
        self._status.setStyleSheet(f"color: {tokens.TEXT_SECONDARY};")
        root.addWidget(self._status)

    # ── sections ────────────────────────────────────────────────────────
    def _section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet(
            f"color: {tokens.ACCENT_TEXT};"
            f" font-weight: {tokens.WEIGHT_SEMIBOLD};")
        return label

    def _button(self, text: str, slot, tooltip: str = "") -> QPushButton:
        button = QPushButton(text)
        button.setMinimumHeight(tokens.BUTTON_HEIGHT)
        button.clicked.connect(slot)
        if tooltip:
            button.setToolTip(tooltip)
        return button

    def _grid(self, buttons: list[QPushButton]) -> QGridLayout:
        grid = QGridLayout()
        grid.setHorizontalSpacing(tokens.SPACE_8)
        grid.setVerticalSpacing(tokens.SPACE_8)
        for index, button in enumerate(buttons):
            grid.addWidget(button, index // 3, index % 3)
        return grid

    def _message_section(self) -> QVBoxLayout:
        box = QVBoxLayout()
        box.setSpacing(tokens.SPACE_8)
        box.addWidget(self._section_label("Message boxes"))
        box.addLayout(self._grid([
            self._button("Information", self._information),
            self._button("Warning", self._warning),
            self._button("Critical", self._critical),
            self._button("Question (Yes / No)", self._question,
                         "Enter and Escape both choose No"),
            self._button("Save / Discard / Cancel", self._save_discard,
                         "Enter = Save, Escape = Cancel"),
            self._button("Custom actions", self._custom_actions),
            self._button("Non-modal prompt", self._nonmodal_prompt,
                         "Offline-queue prompt: keeps a reference"),
        ]))
        return box

    def _input_section(self) -> QVBoxLayout:
        box = QVBoxLayout()
        box.setSpacing(tokens.SPACE_8)
        box.addWidget(self._section_label("Input dialogs"))
        box.addLayout(self._grid([
            self._button("Text input", self._text_input),
            self._button("Number input", self._number_input),
            self._button("Multiline editor", self._multiline),
            self._button("Add Translation", self._add_translation),
        ]))
        return box

    def _settings_fields_section(self) -> QVBoxLayout:
        """Every Settings field variant and state, side by side.

        Normal controls are live: hover them, tab/click for focus, and the
        two buttons focus the size field or open a real compact popup. The
        bottom row is a disabled set so the dimmed chevron is visible
        without touching the live controls.
        """
        box = QVBoxLayout()
        box.setSpacing(tokens.SPACE_8)
        box.addWidget(self._section_label("Settings fields"))

        def field_label(text: str) -> QLabel:
            label = QLabel(text)
            label.setStyleSheet(f"color: {tokens.TEXT_MUTED};")
            return label

        family = QFontComboBox()
        install_combo(family)
        field_chrome.apply_combo(
            family, field_chrome.SETTINGS_FONT_FAMILY_COMBO)

        weight = QComboBox()
        install_combo(weight)
        weight.addItems(["Regular", "Medium", "SemiBold", "Bold"])
        weight.setCurrentIndex(1)
        field_chrome.apply_combo(
            weight, field_chrome.SETTINGS_FONT_WEIGHT_COMBO)

        size = QSpinBox()
        size.setRange(8, 16)
        size.setValue(13)
        size.setSuffix(" px")
        field_chrome.apply_spin(size, field_chrome.SETTINGS_FONT_SIZE_SPIN)

        standard_combo = QComboBox()
        install_combo(standard_combo)
        standard_combo.addItems(["Microphone (PipeWire)", "Line In (ALSA)"])
        field_chrome.apply_combo(standard_combo)

        standard_spin = QSpinBox()
        standard_spin.setRange(0, 10)
        standard_spin.setValue(3)
        standard_spin.setSuffix(" verses")
        field_chrome.apply_spin(standard_spin)

        compact = QComboBox()
        install_combo(compact)
        compact.addItems(["KJV", "NIV", "ESV"])
        field_chrome.apply_combo(
            compact, field_chrome.SETTINGS_COMPACT_COMBO, compact=True)

        disabled_combo = QComboBox()
        install_combo(disabled_combo)
        disabled_combo.addItems(["KJV", "NIV", "ESV"])
        field_chrome.apply_combo(
            disabled_combo, field_chrome.SETTINGS_COMPACT_COMBO,
            compact=True)
        disabled_combo.setEnabled(False)

        disabled_spin = QSpinBox()
        disabled_spin.setRange(8, 16)
        disabled_spin.setValue(13)
        disabled_spin.setSuffix(" px")
        field_chrome.apply_spin(
            disabled_spin, field_chrome.SETTINGS_FONT_SIZE_SPIN)
        disabled_spin.setEnabled(False)

        grid = QGridLayout()
        grid.setHorizontalSpacing(tokens.SPACE_12)
        grid.setVerticalSpacing(tokens.SPACE_4)
        grid.addWidget(field_label("Font family"), 0, 0, 1, 2)
        grid.addWidget(field_label("Weight"), 0, 2)
        grid.addWidget(field_label("Size"), 0, 3)
        grid.addWidget(family, 1, 0, 1, 2)
        grid.addWidget(weight, 1, 2)
        grid.addWidget(size, 1, 3)
        grid.addWidget(field_label("Standard combo"), 2, 0)
        grid.addWidget(field_label("Standard spin"), 2, 1)
        grid.addWidget(field_label("Compact combo"), 2, 2, 1, 2)
        grid.addWidget(standard_combo, 3, 0)
        grid.addWidget(standard_spin, 3, 1)
        grid.addWidget(compact, 3, 2, 1, 2)
        grid.addWidget(field_label("Disabled"), 4, 0)
        grid.addWidget(disabled_combo, 5, 0)
        grid.addWidget(disabled_spin, 5, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)
        grid.setColumnStretch(3, 1)
        box.addLayout(grid)

        hint = QLabel(
            "Hover a field for the hover state; tab or click for focus; "
            "the bottom row is disabled. The buttons drive focus and a real "
            "popup so the open state can be inspected too.")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {tokens.TEXT_MUTED};")
        box.addWidget(hint)

        focus_button = QPushButton("Focus size field")
        focus_button.setMinimumHeight(tokens.BUTTON_HEIGHT)
        focus_button.clicked.connect(lambda: size.setFocus())
        popup_button = QPushButton("Open compact popup")
        popup_button.setMinimumHeight(tokens.BUTTON_HEIGHT)
        popup_button.clicked.connect(compact.showPopup)
        buttons = QGridLayout()
        buttons.setHorizontalSpacing(tokens.SPACE_8)
        buttons.addWidget(focus_button, 0, 0)
        buttons.addWidget(popup_button, 0, 1)
        buttons.setColumnStretch(2, 1)
        box.addLayout(buttons)

        # Referenced by the platform-theme render script; not product API.
        self._field_demo = {
            "family": family, "weight": weight, "size": size,
            "standard_combo": standard_combo, "standard_spin": standard_spin,
            "compact": compact, "disabled_combo": disabled_combo,
            "disabled_spin": disabled_spin,
        }
        return box

    def _popup_section(self) -> QVBoxLayout:
        box = QVBoxLayout()
        box.setSpacing(tokens.SPACE_8)
        box.addWidget(self._section_label("Combos, menus, tooltips"))

        translations = QComboBox()
        install_combo(translations)
        translations.addItems(["KJV", "NIV", "ESV", "NLT", "NKJV", "AMP"])

        fonts = QFontComboBox()
        install_combo(fonts)

        menu = QMenu(self)
        menu.setStyleSheet(menu_qss())
        menu.addAction("Rename…", lambda: self._result("menu: Rename"))
        menu.addAction("Duplicate", lambda: self._result("menu: Duplicate"))
        menu.addSeparator()
        checkable = menu.addAction("Show in Preview")
        checkable.setCheckable(True)
        checkable.setChecked(True)
        menu.addAction("Delete").setEnabled(False)

        menu_button = QPushButton("Open menu")
        menu_button.setMinimumHeight(tokens.BUTTON_HEIGHT)
        menu_button.setToolTip("Context menu surface")
        menu_button.clicked.connect(
            lambda: menu.exec(menu_button.mapToGlobal(
                menu_button.rect().bottomLeft())))

        tooltip_target = QLabel("Hover for tooltip")
        tooltip_target.setToolTip("Double-click to send live")
        tooltip_target.setStyleSheet(
            f"color: {tokens.TEXT_PRIMARY};"
            f" border: 1px dashed {tokens.BORDER_POPOVER};"
            f" border-radius: {tokens.RADIUS_SM}px;"
            f" padding: {tokens.SPACE_4}px {tokens.SPACE_8}px;")

        row = QGridLayout()
        row.setHorizontalSpacing(tokens.SPACE_8)
        row.setVerticalSpacing(tokens.SPACE_8)
        row.addWidget(QLabel("Translation"), 0, 0)
        row.addWidget(translations, 0, 1)
        row.addWidget(QLabel("Font"), 0, 2)
        row.addWidget(fonts, 0, 3)
        row.addWidget(menu_button, 1, 0)
        row.addWidget(tooltip_target, 1, 1, 1, 2)
        row.setColumnStretch(1, 1)
        row.setColumnStretch(3, 1)
        box.addLayout(row)
        return box

    # ── actions ─────────────────────────────────────────────────────────
    def _result(self, text: str) -> None:
        self._status.setText(f"last result: {text}")

    def _information(self) -> None:
        dialogs.information(
            self, "Translation Saved",
            "The new translation is ready to use.")
        self._result("information closed")

    def _warning(self) -> None:
        dialogs.warning(
            self, "Import Failed",
            "Some files could not be imported:\n\nsong.xml\nInvalid section")
        self._result("warning closed")

    def _critical(self) -> None:
        dialogs.critical(
            self, "Export Failed",
            "Could not write file:\n\nPermission denied")
        self._result("critical closed")

    def _question(self) -> None:
        answer = dialogs.question(
            self, "Delete Deck",
            "Delete \"Sunday Morning\"?\nThis cannot be undone.")
        self._result(f"question -> {int(answer)}")

    def _save_discard(self) -> None:
        dialog = dialogs.MessageDialog(
            self, icon="question", title="Unsaved Changes",
            text="Save before starting a new schedule?")
        dialog.setStandardButtons(
            dialogs.Save | dialogs.Discard | dialogs.Cancel)
        dialog.setDefaultButton(dialogs.Save)
        dialog.exec()
        clicked = dialog.clickedButton()
        self._result(
            f"save/discard/cancel -> {clicked.text() if clicked else 'closed'}")

    def _custom_actions(self) -> None:
        dialog = dialogs.MessageDialog(
            self, icon="question", title="EasyWorship Import",
            text="2 of 5 songs are already in your library.\n\n"
                 "Skip them, or overwrite them with the imported versions?")
        skip = dialog.addButton("Skip existing", dialogs.ButtonRole.ActionRole)
        dialog.addButton("Overwrite existing", dialogs.ButtonRole.ActionRole)
        dialog.addButton(dialogs.Cancel)
        dialog.setDefaultButton(skip)
        dialog.exec()
        clicked = dialog.clickedButton()
        self._result(
            f"custom -> {clicked.text() if clicked else 'closed'}")

    def _nonmodal_prompt(self) -> None:
        if self._nonmodal is not None:
            self._nonmodal.close()
        dialog = dialogs.MessageDialog(self)
        dialog.setWindowTitle("Offline Extraction Queue")
        dialog.setText("2 past services pending. Process now or after service?")
        dialog.setStandardButtons(dialogs.Yes | dialogs.No)
        dialog.button(dialogs.Yes).setText("Process Now")
        dialog.button(dialogs.No).setText("After Service")
        dialog.setModal(False)
        dialog.show()
        # Same discipline as MainWindow._check_offline_queue: the prompt is
        # not modal, so the window must keep a reference to it.
        self._nonmodal = dialog
        self._result("non-modal prompt shown")

    def _text_input(self) -> None:
        text, accepted = dialogs.get_text(
            self, "Rename Translation", "Display name", text="New King James")
        self._result(f"text -> {text!r}, accepted={accepted}")

    def _number_input(self) -> None:
        value, accepted = dialogs.get_double(
            self, "Line Spacing", "Spacing (pt)", 1.5, 0.5, 6.0, 2, 0.1)
        self._result(f"number -> {value}, accepted={accepted}")

    def _multiline(self) -> None:
        text, accepted = dialogs.edit_text(
            self, "Edit Slide 1 — Sunday Morning",
            "Section: verse    ·    Raw text ([markers] preserved)",
            "For God so loved the world, that he gave his only begotten Son.")
        self._result(f"editor accepted={accepted}, {len(text)} chars")

    def _add_translation(self) -> None:
        from ui.dialogs.add_translation_dialog import AddTranslationDialog

        dialog = AddTranslationDialog(self)
        dialog.exec()
        self._result(f"add translation -> {dialog.selected_path()!r}")


def main() -> int:
    app = build_app()
    gallery = Gallery()
    gallery.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
