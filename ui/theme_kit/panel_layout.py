"""ui/theme_kit/panel_layout.py

The three numbers that put a tiered Designer panel on one grid.

    PANEL_PAD    left margin of the panel (outside every heading)
    TIER_STEP    how far each tier steps in
    GUTTER       the arrow slot at the left of every row

A row's left edge and its label's x follow from the tier alone::

    edge(N)   = PANEL_PAD + (N - 1) * TIER_STEP
    label_x(N) = edge(N) + GUTTER

With the defaults that is Tier 1 label 20, Tier 2 label 32, Tier 3 label 44.
Every child label sits strictly to the right of its parent's label, and a
Tier-3 row reserves the gutter even though it has no arrow, so its label never
collapses back to the Tier-2 position.

If a panel feels too narrow, change ``TIER_STEP`` and ``GUTTER`` here and
nothing else: the row chrome, the section body, the parameter body and the
stacked-control indent all read these three values.

The rules are documented in ``docs/PANEL_ORGANIZATION.md``.
"""

from __future__ import annotations

#: Left margin of the panel, outside every heading.
PANEL_PAD = 8
#: How far each tier steps in from the one above it.
TIER_STEP = 12
#: Width of the arrow slot at the left of every row (reserved even with no arrow).
GUTTER = 12


def edge(tier: int) -> int:
    """Left edge of a tier-*N* row, in panel coordinates."""
    return PANEL_PAD + (max(1, int(tier)) - 1) * TIER_STEP


def label_x(tier: int) -> int:
    """Where a tier-*N* label starts, in panel coordinates."""
    return edge(tier) + GUTTER


__all__ = ["GUTTER", "PANEL_PAD", "TIER_STEP", "edge", "label_x"]
