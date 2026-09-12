"""Section-hop navigation: consecutive same-section runs.

Pure logic (no Qt/DB): section_run_starts() must match the strip's visual
grouping, including None-section runs.
"""

from core.slide_service import section_run_starts


def test_runs_basic():
    slides = [
        {"section": "V", "text": "a"},
        {"section": "V", "text": "b"},
        {"section": "C", "text": "c"},
        {"section": "C", "text": "d"},
        {"section": "B", "text": "e"},
    ]
    assert section_run_starts(slides) == [0, 2, 4]


def test_none_groups_with_none():
    slides = [
        {"section": None, "text": "a"},
        {"section": None, "text": "b"},
        {"section": "V", "text": "c"},
        {"section": None, "text": "d"},
    ]
    assert section_run_starts(slides) == [0, 2, 3]


def test_single_and_empty():
    assert section_run_starts([{"section": "V", "text": "a"}]) == [0]
    assert section_run_starts([]) == []
    assert section_run_starts(None) == []


def test_hop_targets():
    runs = [0, 2, 4]
    # next from 0/1 -> 2 ; from 2/3 -> 4 ; from 4 -> nowhere
    assert [r for r in runs if r > 0][0] == 2
    assert [r for r in runs if r > 1][0] == 2
    assert [r for r in runs if r > 3][0] == 4
    assert [r for r in runs if r > 4] == []
    # prev from 4/3 -> 2 ; from 2 -> 0 ; from 0 -> nowhere
    assert [r for r in runs if r < 4][-1] == 2
    assert [r for r in runs if r < 2][-1] == 0
    assert [r for r in runs if r < 0] == []
