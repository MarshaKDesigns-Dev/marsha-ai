"""Explain how approved assets cover the customer's selected needs."""

from __future__ import annotations

import re
from typing import Any, Iterable

from services.sponsorship_context import json_list


NEED_TERMS = {
    "Cash Sponsorship": ("cash sponsorship", "cash sponsor", "title sponsor"),
    "Scholarships": ("scholarship",),
    "Venue": ("venue",),
    "Meeting Space": ("meeting space", "conference room", "coworking"),
    "Flowers": ("flower", "floral", "florist"),
    "Photography": ("photograph", "photo"),
    "Videography": ("videograph", "video production", "video highlights"),
    "Printing": ("printing partner", "printer", "supplies the official souvenir program"),
    "Marketing": ("marketing", "promotion", "advertising"),
    "Transportation": ("transportation", "transport", "shuttle", "vehicle"),
    "Hotels": ("hotel", "lodging", "accommodation"),
    "Catering": ("cater", "food", "beverage"),
    "Crowns": ("crown", "tiara"),
    "Trophies": ("trophy", "trophies"),
    "Awards": ("award sponsor", "awards partner", "provides awards"),
    "Hair": ("hair", "salon"),
    "Makeup": ("makeup", "cosmetic"),
    "Boutique/Fashion": ("boutique", "fashion", "apparel", "wardrobe"),
    "Jewelry": ("jewelry", "jewellery", "accessory"),
    "Gift Bags": ("gift bag", "welcome bag", "swag bag"),
    "Audio": ("audio", "sound"),
    "Lighting": ("lighting",),
    "DJ": (" dj ", "disc jockey"),
    "Stage": ("stage rental", "staging elements", "stage production"),
    "Volunteers": ("volunteer partner", "provides volunteers", "volunteer staffing"),
    "Community Partners": ("community partner", "community organization"),
    "Colleges": ("college", "university", "higher education"),
    "Government": ("government", "public agency", "municipal"),
    "Media Partners": ("media partner", "broadcast partner", "publisher"),
}


def _searchable_asset_text(asset: Any) -> str:
    values = (
        getattr(asset, "name", ""),
        getattr(asset, "description", ""),
        getattr(asset, "sponsor_value", ""),
        getattr(asset, "value", ""),
        getattr(asset, "delivery_method", ""),
    )
    combined = " ".join(str(value or "") for value in values).casefold()
    return " " + re.sub(r"\s+", " ", combined) + " "


def build_need_coverage(initiative: Any, assets: Iterable[Any]) -> dict[str, Any]:
    """Return deterministic, read-only need-to-approved-asset coverage."""

    selected_needs = json_list(
        getattr(initiative, "sponsorship_needs_json", "[]")
    )
    other_need = str(
        getattr(initiative, "sponsorship_needs_other", "") or ""
    ).strip()
    selected_needs = [need for need in selected_needs if need != "Other"]
    assets = list(assets)
    asset_needs = {asset.id: [] for asset in assets}
    uncovered_needs = []

    for need in selected_needs:
        terms = NEED_TERMS.get(need, (need.casefold(),))
        matched = []
        for asset in assets:
            text = _searchable_asset_text(asset)
            if any(term.casefold() in text for term in terms):
                asset_needs[asset.id].append(need)
                matched.append(asset.id)
        if not matched:
            uncovered_needs.append(need)

    return {
        "selected_needs": selected_needs,
        "asset_needs": asset_needs,
        "uncovered_needs": uncovered_needs,
        "other_need": other_need,
    }
