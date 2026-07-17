"""Unit tests for utils/validation.py."""

import pytest

from models.hackathon import Hackathon
from utils.validation import validate_hackathon


class TestValidateHackathon:
    """Tests for validate_hackathon function."""

    def _valid_data(self, **overrides) -> dict:
        """Return a minimal valid hackathon dict with optional overrides."""
        base = {
            "title": "HackMIT 2025",
            "platform": "Devpost",
            "registration_url": "https://devpost.com/hackmit-2025",
            "registration_deadline": "2025-09-01",
            "submission_deadline": "2025-09-15",
            "organizer": "MIT",
            "themes": ["AI", "Web3"],
            "mode": "hybrid",
            "location": "Cambridge, MA",
            "prize": "$10,000",
            "team_size": "2-5",
        }
        base.update(overrides)
        return base

    # --- Happy path ---

    def test_valid_hackathon_returns_dataclass(self):
        data = self._valid_data()
        result = validate_hackathon(data)
        assert isinstance(result, Hackathon)
        assert result.title == "HackMIT 2025"
        assert result.platform == "Devpost"
        assert result.registration_url == "https://devpost.com/hackmit-2025"

    def test_valid_hackathon_with_none_dates(self):
        data = self._valid_data(registration_deadline=None, submission_deadline=None)
        result = validate_hackathon(data)
        assert result is not None
        assert result.registration_deadline is None
        assert result.submission_deadline is None

    def test_valid_hackathon_minimal_fields(self):
        data = {
            "title": "Test Hack",
            "platform": "Devfolio",
            "registration_url": "https://devfolio.co/test",
        }
        result = validate_hackathon(data)
        assert result is not None
        assert result.title == "Test Hack"
        assert result.platform == "Devfolio"
        assert result.themes == []
        assert result.organizer is None

    # --- Title validation ---

    def test_empty_title_returns_none(self):
        assert validate_hackathon(self._valid_data(title="")) is None

    def test_whitespace_only_title_returns_none(self):
        assert validate_hackathon(self._valid_data(title="   ")) is None

    def test_title_trimmed(self):
        result = validate_hackathon(self._valid_data(title="  Spaced Title  "))
        assert result is not None
        assert result.title == "Spaced Title"

    def test_title_over_200_chars_returns_none(self):
        long_title = "A" * 201
        assert validate_hackathon(self._valid_data(title=long_title)) is None

    def test_title_exactly_200_chars_is_valid(self):
        title = "A" * 200
        result = validate_hackathon(self._valid_data(title=title))
        assert result is not None
        assert result.title == title

    def test_non_string_title_returns_none(self):
        assert validate_hackathon(self._valid_data(title=123)) is None
        assert validate_hackathon(self._valid_data(title=None)) is None

    # --- Platform validation ---

    def test_valid_platforms(self):
        for platform in ["Devpost", "Devfolio", "Unstop"]:
            result = validate_hackathon(self._valid_data(platform=platform))
            assert result is not None
            assert result.platform == platform

    def test_invalid_platform_returns_none(self):
        assert validate_hackathon(self._valid_data(platform="GitHub")) is None
        assert validate_hackathon(self._valid_data(platform="devpost")) is None
        assert validate_hackathon(self._valid_data(platform="")) is None

    def test_none_platform_returns_none(self):
        assert validate_hackathon(self._valid_data(platform=None)) is None

    # --- Registration URL validation ---

    def test_url_must_start_with_https(self):
        assert validate_hackathon(self._valid_data(registration_url="http://example.com")) is None

    def test_url_non_string_returns_none(self):
        assert validate_hackathon(self._valid_data(registration_url=None)) is None
        assert validate_hackathon(self._valid_data(registration_url=123)) is None

    def test_url_over_2048_chars_returns_none(self):
        long_url = "https://example.com/" + "a" * 2030
        assert validate_hackathon(self._valid_data(registration_url=long_url)) is None

    def test_url_exactly_2048_chars_is_valid(self):
        url = "https://example.com/" + "a" * (2048 - len("https://example.com/"))
        assert len(url) == 2048
        result = validate_hackathon(self._valid_data(registration_url=url))
        assert result is not None

    # --- Date field validation ---

    def test_valid_iso_date_accepted(self):
        result = validate_hackathon(self._valid_data(registration_deadline="2025-01-15"))
        assert result is not None
        assert result.registration_deadline == "2025-01-15"

    def test_invalid_date_format_returns_none(self):
        assert validate_hackathon(self._valid_data(registration_deadline="Jan 15, 2025")) is None
        assert validate_hackathon(self._valid_data(registration_deadline="15-01-2025")) is None
        assert validate_hackathon(self._valid_data(registration_deadline="not-a-date")) is None

    def test_non_string_date_returns_none(self):
        assert validate_hackathon(self._valid_data(registration_deadline=12345)) is None

    def test_submission_deadline_invalid_returns_none(self):
        assert validate_hackathon(self._valid_data(submission_deadline="2025/01/15")) is None

    # --- Optional field handling ---

    def test_missing_optional_fields_default_to_none(self):
        data = {
            "title": "Min Hack",
            "platform": "Unstop",
            "registration_url": "https://unstop.com/min-hack",
        }
        result = validate_hackathon(data)
        assert result is not None
        assert result.organizer is None
        assert result.mode is None
        assert result.location is None
        assert result.prize is None
        assert result.team_size is None

    def test_themes_defaults_to_empty_list(self):
        data = {
            "title": "Hack",
            "platform": "Devpost",
            "registration_url": "https://devpost.com/hack",
        }
        result = validate_hackathon(data)
        assert result.themes == []

    def test_themes_non_list_defaults_to_empty(self):
        result = validate_hackathon(self._valid_data(themes="not a list"))
        assert result is not None
        assert result.themes == []
