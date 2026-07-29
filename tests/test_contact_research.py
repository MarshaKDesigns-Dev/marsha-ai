import json

import pytest
from pydantic import ValidationError
from types import SimpleNamespace
from unittest.mock import MagicMock

import services.contact_research as contact_research
from services.contact_research import (
    ContactResearchError,
    ContactResearchResult,
    research_opportunity_contact,
)


def result(**overrides):
    values = {
        "why_this_contact": "Verified on the organization's public website.",
        "confidence": "High",
        "evidence_urls": ["https://example.org/contact"],
        "result_type": "named_contact",
        "contact_name": "Jordan Lee",
        "title": "Partnerships Director",
    }
    values.update(overrides)
    return ContactResearchResult.model_validate(values)


def test_valid_named_contact():
    contact = result()

    assert contact.result_type.value == "named_contact"
    assert contact.contact_name == "Jordan Lee"


def test_valid_general_contact():
    contact = result(
        result_type="general_contact",
        contact_name=None,
        title=None,
        email="partnerships@example.org",
    )

    assert contact.result_type.value == "general_contact"
    assert contact.email == "partnerships@example.org"


def test_valid_no_contact_result():
    contact = result(
        result_type="no_contact",
        contact_name=None,
        title=None,
        evidence_urls=[],
        why_this_contact="No reliable public contact route was found.",
        confidence="Low",
    )

    assert contact.result_type.value == "no_contact"
    assert contact.contact_name is None


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("linkedin_url", "null"),
        ("contact_url", "None"),
        ("email", "N/A"),
    ),
)
def test_optional_contact_null_like_values_normalize_to_none(field, value):
    contact = result(**{field: value})

    assert getattr(contact, field) is None


def test_valid_named_contact_accepts_null_like_linkedin_value():
    contact = result(linkedin_url="  NuLl  ")

    assert contact.result_type.value == "named_contact"
    assert contact.linkedin_url is None


@pytest.mark.parametrize(
    "organization_name",
    (
        "Durham Performing Arts Center",
        "DURHAM PERFORMING ARTS CENTER",
    ),
)
def test_general_contact_organization_name_normalizes_to_none(
    organization_name,
):
    payload = {
        "result_type": "general_contact",
        "contact_name": organization_name,
        "contact_url": "https://www.dpacnc.com/connect/contact-us-2",
        "why_this_contact": "Official general contact page.",
        "confidence": "High",
        "evidence_urls": [
            "https://www.dpacnc.com/connect/contact-us-2",
        ],
    }

    contact = contact_research._validate_contact_research_output(
        json.dumps(payload),
        sponsor_name="Durham Performing Arts Center",
    )

    assert contact.contact_name is None
    assert contact.result_type.value == "general_contact"


def test_general_contact_generic_contact_us_label_normalizes_to_none():
    payload = {
        "result_type": "general_contact",
        "contact_name": "Contact Us",
        "contact_url": "https://example.org/contact",
        "why_this_contact": "Official general contact page.",
        "confidence": "High",
        "evidence_urls": ["https://example.org/contact"],
    }

    contact = contact_research._validate_contact_research_output(
        json.dumps(payload),
        sponsor_name="Example Sponsor",
    )

    assert contact.contact_name is None


def test_general_contact_actual_human_name_still_fails_validation():
    payload = {
        "result_type": "general_contact",
        "contact_name": "Jordan Lee",
        "contact_url": "https://example.org/contact",
        "why_this_contact": "Official general contact page.",
        "confidence": "High",
        "evidence_urls": ["https://example.org/contact"],
    }

    with pytest.raises(
        ValidationError,
        match="A general contact must not identify a named person",
    ):
        contact_research._validate_contact_research_output(
            json.dumps(payload),
            sponsor_name="Example Sponsor",
        )


def test_named_contact_human_name_is_not_normalized():
    expected = result(contact_name="Jordan Lee")

    contact = contact_research._validate_contact_research_output(
        expected.model_dump_json(),
        sponsor_name="Example Sponsor",
    )

    assert contact.contact_name == "Jordan Lee"
    assert contact.result_type.value == "named_contact"


@pytest.mark.parametrize(
    ("wrapped", "expected"),
    (
        (
            "https://example.org/contact",
            "https://example.org/contact",
        ),
        (
            "[Contact Us](https://example.org/contact)",
            "https://example.org/contact",
        ),
        (
            "([Contact Us](https://example.org/contact))",
            "https://example.org/contact",
        ),
        (
            "(https://example.org/contact)",
            "https://example.org/contact",
        ),
        (
            "<https://example.org/contact>",
            "https://example.org/contact",
        ),
        (
            '"https://example.org/contact"',
            "https://example.org/contact",
        ),
        (
            "'https://example.org/contact'",
            "https://example.org/contact",
        ),
        (
            "[Contact](https://example.org/path/?utm_source=openai)",
            "https://example.org/path/?utm_source=openai",
        ),
    ),
)
def test_supported_contact_url_wrappers_preserve_destination(wrapped, expected):
    assert contact_research._unwrap_contact_url(wrapped) == expected


def test_markdown_label_is_never_used_as_contact_url():
    assert contact_research._unwrap_contact_url(
        "[Contact Us](https://example.org/contact)"
    ) == "https://example.org/contact"


@pytest.mark.parametrize(
    "invalid",
    (
        "Visit https://example.org/contact for help.",
        "https://example.org/one https://example.org/two",
    ),
)
def test_ambiguous_or_prose_contact_url_is_rejected(invalid):
    with pytest.raises(ValueError):
        contact_research._unwrap_contact_url(invalid)


def test_contact_and_linkedin_urls_use_same_narrow_normalization():
    payload = {
        "result_type": "named_contact",
        "contact_name": "Jordan Lee",
        "contact_url": "(https://example.org/contact/?utm_source=openai)",
        "linkedin_url": "<https://linkedin.com/in/jordan-lee/>",
        "why_this_contact": "Officially listed contact.",
        "confidence": "High",
        "evidence_urls": [
            "[Contact](https://example.org/contact/?utm_source=openai)",
        ],
    }

    contact = contact_research._validate_contact_research_output(
        json.dumps(payload),
        sponsor_name="Example Sponsor",
    )

    assert (
        contact.contact_url
        == "https://example.org/contact/?utm_source=openai"
    )
    assert contact.linkedin_url == "https://linkedin.com/in/jordan-lee/"
    assert contact.evidence_urls == [
        "https://example.org/contact/?utm_source=openai"
    ]


@pytest.mark.parametrize(
    "blank_values",
    (
        [""],
        ["   "],
        ["", "  ", "null", "N/A", "not available"],
    ),
)
def test_blank_evidence_entries_are_removed(blank_values):
    payload = {
        "result_type": "no_contact",
        "why_this_contact": "No verified route found.",
        "confidence": "Low",
        "evidence_urls": blank_values,
    }

    contact = contact_research._validate_contact_research_output(
        json.dumps(payload),
        sponsor_name="Example Sponsor",
    )

    assert contact.evidence_urls == []


def test_duplicate_evidence_urls_are_deduplicated_in_order():
    first = "https://example.org/contact"
    second = "https://example.org/leadership"
    payload = {
        "result_type": "named_contact",
        "contact_name": "Jordan Lee",
        "why_this_contact": "Officially listed contact.",
        "confidence": "High",
        "evidence_urls": [first, second, first],
    }

    contact = contact_research._validate_contact_research_output(
        json.dumps(payload),
        sponsor_name="Example Sponsor",
    )

    assert contact.evidence_urls == [first, second]


def test_blank_evidence_uses_exactly_cited_contact_url_unchanged():
    contact_url = (
        "https://example.org/contact/?utm_source=openai&ref=directory"
    )
    payload = {
        "result_type": "general_contact",
        "contact_url": contact_url,
        "why_this_contact": "Official contact page.",
        "confidence": "High",
        "evidence_urls": [""],
    }

    contact = contact_research._validate_contact_research_output(
        json.dumps(payload),
        sponsor_name="Example Sponsor",
        cited_urls_exact={contact_url},
    )

    assert contact.contact_url == contact_url
    assert contact.evidence_urls == [contact_url]


def test_blank_evidence_uses_exactly_cited_linkedin_url():
    linkedin_url = "https://linkedin.com/in/jordan-lee/?trk=public"
    payload = {
        "result_type": "named_contact",
        "contact_name": "Jordan Lee",
        "linkedin_url": linkedin_url,
        "why_this_contact": "Official staff listing.",
        "confidence": "High",
        "evidence_urls": [" "],
    }

    contact = contact_research._validate_contact_research_output(
        json.dumps(payload),
        sponsor_name="Example Sponsor",
        cited_urls_exact={linkedin_url},
    )

    assert contact.linkedin_url == linkedin_url
    assert contact.evidence_urls == [linkedin_url]


@pytest.mark.parametrize(
    "route",
    (
        {"contact_url": "https://example.org/contact"},
        {"email": "info@example.org"},
        {"phone": "919-555-0100"},
    ),
)
def test_blank_evidence_without_exactly_cited_url_still_fails(route):
    payload = {
        "result_type": "general_contact",
        "why_this_contact": "General contact route.",
        "confidence": "High",
        "evidence_urls": [""],
        **route,
    }

    with pytest.raises(ValidationError, match="require public evidence"):
        contact_research._validate_contact_research_output(
            json.dumps(payload),
            sponsor_name="Example Sponsor",
            cited_urls_exact={"https://different.example/contact"},
        )


def test_existing_nonempty_evidence_remains_unchanged():
    evidence_url = "https://example.org/contact"
    payload = {
        "result_type": "general_contact",
        "contact_url": "https://example.org/general",
        "why_this_contact": "Official general route.",
        "confidence": "High",
        "evidence_urls": [evidence_url],
    }

    contact = contact_research._validate_contact_research_output(
        json.dumps(payload),
        sponsor_name="Example Sponsor",
        cited_urls_exact={"https://example.org/general"},
    )

    assert contact.evidence_urls == [evidence_url]


def test_named_contact_without_evidence_is_rejected():
    with pytest.raises(ValidationError, match="require public evidence"):
        result(evidence_urls=[])


def test_general_contact_without_usable_route_is_rejected():
    with pytest.raises(ValidationError, match="requires an email, phone"):
        result(
            result_type="general_contact",
            contact_name=None,
            title=None,
        )


def test_no_contact_result_containing_contact_data_is_rejected():
    with pytest.raises(ValidationError, match="must not contain contact"):
        result(result_type="no_contact")


def provider_client(
    output_text,
    *,
    source_url="https://example.org/contact",
    input_tokens=None,
    output_tokens=None,
):
    response = SimpleNamespace(
        id="resp_contact",
        status="completed",
        incomplete_details=None,
        usage=SimpleNamespace(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=(
                input_tokens + output_tokens
                if input_tokens is not None and output_tokens is not None
                else None
            ),
        ),
        output=[
            {
                "type": "web_search_call",
                "status": "completed",
                "action": {
                    "sources": [{"url": source_url}],
                },
            },
            {
                "type": "message",
                "status": "completed",
                "content": [
                    {
                        "type": "output_text",
                        "text": output_text,
                    }
                ],
            },
        ],
    )
    raw_response = MagicMock()
    raw_response.parse.return_value = response
    raw_response.status_code = 200
    client = MagicMock()
    client.with_options.return_value.responses.with_raw_response.create.return_value = (
        raw_response
    )
    return client


def test_contact_discovery_uses_structured_web_search_and_validates_result(
    monkeypatch,
):
    monkeypatch.setattr(
        contact_research,
        "_context_record",
        lambda model, record_id: None,
    )
    expected = result()
    client = provider_client(expected.model_dump_json())

    actual = research_opportunity_contact(
        SimpleNamespace(
            parent_prospect="Example Sponsor",
            recommended_target="Example Sponsor",
            category="Community Partner",
            organization_id=None,
            initiative_id=None,
            sponsorship_asset_id=None,
            sponsor_prospect_id=None,
        ),
        client=client,
    )

    request = (
        client.with_options.return_value.responses.with_raw_response.create
    ).call_args.kwargs
    assert actual == expected
    assert request["tools"] == [{"type": "web_search"}]
    assert request["include"] == ["web_search_call.action.sources"]
    assert "ContactResearchResult" in request["text"]["format"]["name"]
    assert "1. Official organization Contact Us page" in request["input"]
    assert "11. General phone number" in request["input"]
    assert "already determined that this organization is" in request["input"]
    assert "worth pursuing" in request["input"]
    assert "Do not determine, re-evaluate, or re-prove sponsorship" in (
        request["input"]
    )
    assert "contact_name as JSON null" in request["input"]
    assert "title as JSON null" in request["input"]
    assert "linkedin_url as JSON null" in request["input"]
    assert "JSON array of raw URL strings only" in request["input"]
    assert "Do not use Markdown links" in request["input"]
    assert "including its query" in request["input"]
    assert "Never return empty strings inside evidence_urls" in request["input"]
    assert "exact same raw provider-returned URL" in request["input"]


def test_official_contact_page_supports_general_contact_without_eligibility_evidence(
    monkeypatch,
):
    monkeypatch.setattr(
        contact_research,
        "_context_record",
        lambda model, record_id: None,
    )
    contact_url = "https://www.dpacnc.com/connect/contact-us-2"
    expected = result(
        result_type="general_contact",
        contact_name=None,
        title=None,
        contact_url=contact_url,
        evidence_urls=[contact_url],
        why_this_contact="DPAC's official Contact Us page provides a route.",
    )
    client = provider_client(
        expected.model_dump_json(),
        source_url=contact_url,
    )

    actual = research_opportunity_contact(
        SimpleNamespace(
            parent_prospect="Durham Performing Arts Center (DPAC)",
            recommended_target="Durham Performing Arts Center (DPAC)",
            category="In-Kind Partner",
            organization_id=None,
            initiative_id=None,
            sponsorship_asset_id=None,
            sponsor_prospect_id=None,
        ),
        client=client,
    )

    request = (
        client.with_options.return_value.responses.with_raw_response.create
    ).call_args.kwargs
    assert actual == expected
    assert actual.result_type.value == "general_contact"
    assert actual.contact_url == contact_url
    assert "Official Contact Us pages" in request["input"]
    assert "does not need to prove" in request["input"]
    assert "sponsorship eligibility" in request["input"]


def test_markdown_wrapped_provider_contact_url_is_accepted_when_cited(
    monkeypatch,
):
    monkeypatch.setattr(
        contact_research,
        "_context_record",
        lambda model, record_id: None,
    )
    contact_url = (
        "https://www.dpacnc.com/connect/contact-us-2/?utm_source=openai"
    )
    provider_output = json.dumps(
        {
            "result_type": "general_contact",
            "contact_name": None,
            "title": None,
            "contact_url": f"[Contact DPAC]({contact_url})",
            "linkedin_url": None,
            "why_this_contact": "Official general contact route.",
            "confidence": "High",
            "evidence_urls": [f"([Contact DPAC]({contact_url}))"],
        }
    )
    client = provider_client(provider_output, source_url=contact_url)

    actual = research_opportunity_contact(
        SimpleNamespace(
            parent_prospect="Durham Performing Arts Center (DPAC)",
            organization_id=None,
            initiative_id=None,
            sponsorship_asset_id=None,
            sponsor_prospect_id=None,
        ),
        client=client,
    )

    assert actual.contact_url == contact_url
    assert actual.evidence_urls == [contact_url]


def test_extracted_contact_url_absent_from_provider_citations_is_rejected(
    monkeypatch,
):
    monkeypatch.setattr(
        contact_research,
        "_context_record",
        lambda model, record_id: None,
    )
    unsupported_url = "https://example.org/contact"
    provider_output = json.dumps(
        {
            "result_type": "general_contact",
            "contact_url": f"[Contact]({unsupported_url})",
            "why_this_contact": "General contact route.",
            "confidence": "High",
            "evidence_urls": [f"[Contact]({unsupported_url})"],
        }
    )
    client = provider_client(
        provider_output,
        source_url="https://different.example/contact",
    )

    with pytest.raises(ContactResearchError, match="not present"):
        research_opportunity_contact(
            SimpleNamespace(
                parent_prospect="Example Sponsor",
                organization_id=None,
                initiative_id=None,
                sponsorship_asset_id=None,
                sponsor_prospect_id=None,
            ),
            client=client,
        )


def test_contact_prompt_excludes_prior_evidence_but_retains_identity_context(
    monkeypatch,
):
    opportunity_source = "https://www.dpacnc.com/partners"
    prospect_source = "https://www.dpacnc.com/support/sponsorship"
    assignment_source = "https://www.dpacnc.com/research/source"
    organization = SimpleNamespace(
        name="Bright Futures Community Foundation",
        location="Durham, NC",
        mission="Community leadership development",
    )
    initiative = SimpleNamespace(name="2027 Leadership Summit")
    asset = SimpleNamespace(name="Main Stage AV & Staging")
    prospect = SimpleNamespace(
        company_name="Durham Performing Arts Center (DPAC)",
        website=opportunity_source,
        location="Durham, North Carolina",
        evidence_json=f'[{{"url": "{prospect_source}"}}]',
        research_assignment_evidence_json=(
            f'[{{"url": "{assignment_source}"}}]'
        ),
    )

    def context_record(model, record_id):
        records = {
            ("Organization", 1): organization,
            ("SponsorshipInitiative", 2): initiative,
            ("SponsorshipAsset", 3): asset,
            ("SponsorProspect", 4): prospect,
        }
        return records.get((model.__name__, record_id))

    monkeypatch.setattr(
        contact_research,
        "_context_record",
        context_record,
    )
    expected = result(
        result_type="no_contact",
        contact_name=None,
        title=None,
        evidence_urls=[],
        why_this_contact="No verified public communication route was found.",
        confidence="Low",
    )
    client = provider_client(expected.model_dump_json())

    research_opportunity_contact(
        SimpleNamespace(
            parent_prospect="DPAC",
            recommended_target="DPAC",
            category="Performing Arts",
            organization_id=1,
            initiative_id=2,
            sponsorship_asset_id=3,
            sponsor_prospect_id=4,
            sources_json=f'[{{"url": "{opportunity_source}"}}]',
            research_assignment_evidence_json=(
                f'[{{"url": "{assignment_source}"}}]'
            ),
        ),
        client=client,
    )

    prompt = (
        client.with_options.return_value.responses.with_raw_response.create
    ).call_args.kwargs["input"]
    assert "Durham Performing Arts Center (DPAC)" in prompt
    assert "Known official domain (identity only): www.dpacnc.com" in prompt
    assert "Known geography: Durham, North Carolina" in prompt
    assert "Bright Futures Community Foundation" in prompt
    assert "Organization location: Durham, NC" in prompt
    assert "2027 Leadership Summit" in prompt
    assert "Main Stage AV & Staging" in prompt
    assert opportunity_source not in prompt
    assert prospect_source not in prompt
    assert assignment_source not in prompt
    assert "/partners" not in prompt
    assert "Conduct a new web search" in prompt
    assert "Do not reuse URLs from prior sponsor research" in prompt
    assert "copied exactly from the current provider web-search" in prompt
    assert "merely because it is predictable" in prompt


def test_no_verified_public_route_returns_no_contact(monkeypatch):
    monkeypatch.setattr(
        contact_research,
        "_context_record",
        lambda model, record_id: None,
    )
    expected = result(
        result_type="no_contact",
        contact_name=None,
        title=None,
        evidence_urls=[],
        why_this_contact="No verified public communication route was found.",
        confidence="Low",
    )
    client = provider_client(expected.model_dump_json())

    actual = research_opportunity_contact(
        SimpleNamespace(
            parent_prospect="Example Sponsor",
            organization_id=None,
            initiative_id=None,
            sponsorship_asset_id=None,
            sponsor_prospect_id=None,
        ),
        client=client,
    )

    assert actual == expected
    assert actual.result_type.value == "no_contact"


def test_existing_opportunity_url_not_returned_by_current_search_is_rejected(
    monkeypatch,
):
    existing_url = "https://www.dpacnc.com/partners"
    current_search_url = "https://www.dpacnc.com/connect/contact-us-2"

    def context_record(model, record_id):
        if record_id == 12:
            return SimpleNamespace(
                company_name="Durham Performing Arts Center (DPAC)",
                website=existing_url,
            )
        return None

    monkeypatch.setattr(
        contact_research,
        "_context_record",
        context_record,
    )
    unsupported = result(
        result_type="general_contact",
        contact_name=None,
        title=None,
        contact_url=existing_url,
        evidence_urls=[existing_url],
    )
    client = provider_client(
        unsupported.model_dump_json(),
        source_url=current_search_url,
    )

    with pytest.raises(ContactResearchError) as captured:
        research_opportunity_contact(
            SimpleNamespace(
                parent_prospect="Durham Performing Arts Center (DPAC)",
                organization_id=None,
                initiative_id=None,
                sponsorship_asset_id=None,
                sponsor_prospect_id=12,
            ),
            client=client,
        )

    assert existing_url in str(captured.value)
    assert "not present in the provider's web-search" in str(captured.value)


def test_invalid_ai_output_is_rejected(monkeypatch):
    monkeypatch.setattr(
        contact_research,
        "_context_record",
        lambda model, record_id: None,
    )
    client = provider_client(
        '{"result_type":"named_contact",'
        '"why_this_contact":"Unsupported",'
        '"confidence":"low","evidence_urls":[]}',
        input_tokens=456,
        output_tokens=123,
    )

    with pytest.raises(
        ContactResearchError,
        match="ValidationError",
    ) as captured:
        research_opportunity_contact(
            SimpleNamespace(
                parent_prospect="Example Sponsor",
                organization_id=None,
                initiative_id=None,
                sponsorship_asset_id=None,
                sponsor_prospect_id=None,
            ),
            client=client,
        )

    assert "contact_name" in str(captured.value)
    assert "A named contact requires contact_name." in str(captured.value)
    assert captured.value.provider_response_id == "resp_contact"
    assert captured.value.input_tokens == 456
    assert captured.value.output_tokens == 123


def test_openai_exception_preserves_original_message(monkeypatch):
    monkeypatch.setattr(
        contact_research,
        "_context_record",
        lambda model, record_id: None,
    )
    client = MagicMock()
    client.with_options.return_value.responses.with_raw_response.create.side_effect = (
        RuntimeError("provider request exploded")
    )

    with pytest.raises(
        ContactResearchError,
        match="RuntimeError: provider request exploded",
    ):
        research_opportunity_contact(
            SimpleNamespace(
                parent_prospect="Example Sponsor",
                organization_id=None,
                initiative_id=None,
                sponsorship_asset_id=None,
                sponsor_prospect_id=None,
            ),
            client=client,
        )


def test_rejected_evidence_urls_and_policy_are_preserved(monkeypatch):
    monkeypatch.setattr(
        contact_research,
        "_context_record",
        lambda model, record_id: None,
    )
    unsupported = result(
        evidence_urls=[
            "https://example.org/contact",
            "https://example.org/leadership",
        ]
    )
    client = provider_client(
        unsupported.model_dump_json(),
        source_url="https://example.org/unrelated-source",
        input_tokens=500,
        output_tokens=200,
    )

    with pytest.raises(ContactResearchError) as captured:
        research_opportunity_contact(
            SimpleNamespace(
                parent_prospect="Example Sponsor",
                organization_id=None,
                initiative_id=None,
                sponsorship_asset_id=None,
                sponsor_prospect_id=None,
            ),
            client=client,
        )

    message = str(captured.value)
    assert "https://example.org/contact" in message
    assert "https://example.org/leadership" in message
    assert message.count("not present in the provider's web-search") == 2
    assert (
        "every evidence URL must be a public HTTP/HTTPS URL returned in "
        "the provider's web_search_call citations or source list"
    ) in message
    assert captured.value.provider_response_id == "resp_contact"
    assert captured.value.input_tokens == 500
    assert captured.value.output_tokens == 200
