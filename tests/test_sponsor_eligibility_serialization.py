"""Tests for persisted sponsor eligibility JSON."""

import pytest

from services.sponsor_eligibility import EligibilityFacts
from services.sponsor_eligibility_engine import SponsorEligibilityEngine
from services.sponsor_eligibility_serialization import (
    SponsorEligibilitySerializationError,
    deserialize_sponsor_eligibility,
    serialize_sponsor_eligibility,
)


def _analysis():
    return SponsorEligibilityEngine().evaluate(
        EligibilityFacts(
            mission="Support youth education.",
            location="Durham, NC",
            initiative_name="Youth Learning Festival",
            audience="Middle and high school students",
            needs="Program sponsorship",
            explicit_restrictions=["Political campaigns"],
        )
    )


def test_sponsor_eligibility_serialization_round_trip():
    analysis = _analysis()

    restored = deserialize_sponsor_eligibility(
        serialize_sponsor_eligibility(analysis)
    )

    assert restored == analysis
    assert restored.normalized_facts.audience == (
        "Middle and high school students"
    )
    assert restored.rule_version == "sponsor-eligibility-v1"
    assert restored.applied_rules
    assert restored.exclusion_sources


def test_absent_legacy_sponsor_eligibility_deserializes_as_none():
    assert deserialize_sponsor_eligibility(None) is None
    assert deserialize_sponsor_eligibility("") is None


def test_invalid_sponsor_eligibility_json_is_rejected():
    with pytest.raises(SponsorEligibilitySerializationError):
        deserialize_sponsor_eligibility('{"rule_version": "incomplete"}')
