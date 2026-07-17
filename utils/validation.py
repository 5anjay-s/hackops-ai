"""Hackathon data validation utility for HackOps AI.

Validates raw hackathon dictionaries and returns typed Hackathon dataclass
instances, or None if required validation fails.
"""

import re
from typing import Optional

from models.hackathon import Hackathon


# Allowed platform values
VALID_PLATFORMS = {"Devpost", "Devfolio", "Unstop"}

# ISO 8601 date pattern (YYYY-MM-DD)
_ISO_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Max field lengths
_MAX_TITLE_LENGTH = 200
_MAX_URL_LENGTH = 2048


def validate_hackathon(data: dict) -> Optional[Hackathon]:
    """Validate a raw hackathon dict and return a Hackathon instance or None.

    Validates required fields (title, platform, registration_url) and optional
    date fields. Returns None if any required validation fails, discarding
    invalid entries from the pipeline.

    Args:
        data: A dictionary with hackathon fields to validate.

    Returns:
        A valid Hackathon dataclass instance, or None if validation fails.
    """
    # Validate title: non-empty after trimming, max 200 chars
    title = data.get("title")
    if not isinstance(title, str):
        return None
    title = title.strip()
    if not title or len(title) > _MAX_TITLE_LENGTH:
        return None

    # Validate platform: must be one of the allowed values
    platform = data.get("platform")
    if platform not in VALID_PLATFORMS:
        return None

    # Validate registration_url: starts with "https://", max 2048 chars
    registration_url = data.get("registration_url")
    if not isinstance(registration_url, str):
        return None
    if not registration_url.startswith("https://"):
        return None
    if len(registration_url) > _MAX_URL_LENGTH:
        return None

    # Validate date fields if present and non-None
    registration_deadline = data.get("registration_deadline")
    if registration_deadline is not None:
        if not isinstance(registration_deadline, str):
            return None
        if not _ISO_DATE_PATTERN.match(registration_deadline):
            return None

    submission_deadline = data.get("submission_deadline")
    if submission_deadline is not None:
        if not isinstance(submission_deadline, str):
            return None
        if not _ISO_DATE_PATTERN.match(submission_deadline):
            return None

    # Extract optional fields (use None for missing/unavailable)
    organizer = data.get("organizer")
    themes = data.get("themes")
    if not isinstance(themes, list):
        themes = []
    mode = data.get("mode")
    location = data.get("location")
    prize = data.get("prize")
    team_size = data.get("team_size")

    return Hackathon(
        title=title,
        platform=platform,
        registration_url=registration_url,
        registration_deadline=registration_deadline,
        submission_deadline=submission_deadline,
        organizer=organizer,
        themes=themes,
        mode=mode,
        location=location,
        prize=prize,
        team_size=team_size,
    )
