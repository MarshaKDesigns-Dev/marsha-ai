from types import SimpleNamespace

from services.research_need_coverage import build_need_coverage


def asset(asset_id, name, description="", sponsor_value=""):
    return SimpleNamespace(
        id=asset_id,
        name=name,
        description=description,
        sponsor_value=sponsor_value,
        value=None,
        delivery_method="",
    )


def test_grouped_asset_maps_each_selected_need_without_duplicates():
    initiative = SimpleNamespace(
        sponsorship_needs_json='["Audio", "Lighting", "Stage", "Audio"]',
        sponsorship_needs_other="",
    )
    coverage = build_need_coverage(
        initiative,
        [
            asset(
                1,
                "Stage and Technical Partner",
                "Stage rental with professional sound and lighting",
            )
        ],
    )
    assert coverage["selected_needs"] == ["Audio", "Lighting", "Stage"]
    assert coverage["asset_needs"] == {1: ["Audio", "Lighting", "Stage"]}
    assert coverage["uncovered_needs"] == []


def test_unrepresented_and_other_needs_remain_visible():
    initiative = SimpleNamespace(
        sponsorship_needs_json='["Venue", "Transportation", "Other"]',
        sponsorship_needs_other="Childcare during rehearsals",
    )
    coverage = build_need_coverage(initiative, [asset(2, "Official Venue Host")])
    assert coverage["asset_needs"] == {2: ["Venue"]}
    assert coverage["selected_needs"] == ["Venue", "Transportation"]
    assert coverage["uncovered_needs"] == [
        "Transportation",
    ]
    assert coverage["other_need"] == "Childcare during rehearsals"


def test_repeated_research_does_not_change_need_mapping():
    initiative = SimpleNamespace(
        sponsorship_needs_json='["Scholarships"]', sponsorship_needs_other=""
    )
    assets = [asset(3, "Named Scholarship Sponsor")]
    assert build_need_coverage(initiative, assets) == build_need_coverage(
        initiative, assets
    )
