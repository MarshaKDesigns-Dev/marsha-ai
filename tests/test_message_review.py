import json
from types import SimpleNamespace

import app as app_module


class FakeResponses:
    def __init__(self, captured):
        self.captured = captured

    def create(self, **kwargs):
        self.captured.update(kwargs)

        return SimpleNamespace(
            output_text=json.dumps(
                {
                    "improved_subject": "Test subject",
                    "improved_message": "Test message",
                    "review_notes": "Sender identity preserved.",
                    "risk_flags": [],
                }
            )
        )


class FakeClient:
    def __init__(self, captured):
        self.responses = FakeResponses(captured)


def test_message_review_requires_exact_sender_title(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        app_module,
        "client",
        lambda: FakeClient(captured),
    )

    monkeypatch.setattr(
        app_module,
        "get_worker_context",
        lambda: {
            "organization_name": "Test Organization",
            "organization_type": "Nonprofit",
            "location": "Durham, NC",
            "mission": "Serve the community.",
            "sender_name": "Marsha Shearin",
            "sender_title": "Assistant Director",
            "sender_email": "marsha@example.com",
            "website": "",
            "organization_phone": "",
            "initiative_name": "2026 Initiative",
            "fundraising_target": "$25,000",
            "deadline": "2026-09-18",
            "audience": "Community members",
            "needs": "Program support",
            "goals": "Secure sponsors",
        },
    )

    opportunity = SimpleNamespace(
        outreach_channel="email",
        parent_prospect="Test Prospect",
        recommended_target="Test Prospect — Durham",
        contact_name="Test Contact",
        title="General Manager",
        department="Community Partnerships",
        category="Automotive",
        email="contact@example.com",
        phone="919-555-0100",
        contact_url="",
        why_this_contact="Verified local contact.",
    )

    result = app_module.review_message_quality(
        opportunity,
        "Test subject",
        "My name is Marsha Shearin, Director of Test Organization.",
    )

    prompt = captured["input"]

    assert result["improved_message"] == "Test message"
    assert "Title: Assistant Director" in prompt
    assert (
        'Use the sender title exactly as provided: "Assistant Director".'
        in prompt
    )
    assert "Never shorten, promote, replace, or substitute the sender title." in prompt
