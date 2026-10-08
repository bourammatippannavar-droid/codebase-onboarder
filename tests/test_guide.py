from pathlib import Path

from onboarder.guide import build_guide

PROJECT = Path(__file__).parent / "fixtures" / "call_project"


def test_guide_includes_required_sections_and_deterministic_reading_order() -> None:
    guide = build_guide(PROJECT)
    rendered = guide.render()

    assert "Entry points" in rendered
    assert "Most imported" in rendered
    assert "Reading order" in rendered
    assert "Cycles" in rendered
    assert "Files by top-level folder" in rendered
    assert "Quality" in rendered
    assert guide.entry_points == (PROJECT / "main.py",)
    assert guide.reading_order[:1] == (PROJECT / "main.py",)
    assert guide.reading_order == build_guide(PROJECT).reading_order


def test_guide_resolution_rate_uses_resolved_and_stored_unresolved_calls() -> None:
    guide = build_guide(PROJECT)
    resolved = guide.call_counts["exact"] + guide.call_counts["inferred"]
    stored_unresolved = guide.call_counts["unresolved"]

    assert guide.resolution_rate == resolved / (resolved + stored_unresolved)
    assert guide.not_stored_count == sum(guide.not_stored.values())