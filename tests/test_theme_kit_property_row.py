"""PropertyRow label column: long labels render in full at panel widths."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PyQt6.QtWidgets import QApplication, QVBoxLayout, QWidget  # noqa: E402

from ui.theme_kit import NumberField, PropertyRow  # noqa: E402

_QAPP = None


@pytest.fixture(scope="module")
def qapp():
    global _QAPP
    _QAPP = QApplication.instance() or QApplication([])
    return _QAPP


@pytest.mark.parametrize(
    "text,label_width",
    [
        ("Margin right", 76),
        ("Margin bottom", 76),
        ("Letter space", 76),
        ("Word space", 76),
        ("While cloaked", 86),
    ],
)
def test_long_labels_are_not_elided(qapp, text, label_width):
    host = QWidget()
    layout = QVBoxLayout(host)
    row = PropertyRow(text, NumberField(4), label_width=label_width)
    layout.addWidget(row)
    host.resize(240, 80)
    host.show()
    qapp.processEvents()

    assert row.label() == text
    assert row._label.text() == text

    # The reset glyph is an overlay; showing it must not elide the label.
    row.set_changed(True)
    qapp.processEvents()
    assert row._reset.isVisible()
    assert row._label.text() == text
    assert row._label.width() >= row._label.fontMetrics().horizontalAdvance(text)
