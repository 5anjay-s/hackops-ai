"""Unit tests for Intelligence Agent merge/construction behavior.

Tests that _merge() correctly constructs EnrichedHackathon with all fields
populated, preserves original Hackathon fields unchanged, and that
_validate_and_build() enforces field constraints.

Validates: Requirements 6.3, 6.4
"""

import pytest

from agents.intelligence_agent import _merge, _validate_and_build
from models.hackathon import EnrichedHackathon, Hackathon, IntelligenceResult


# --- Fixtures ---


def _sample_hackathon(**overrides) -> Hackathon:
    """Create a sample Hackathon with all fields populated."""
    defaults = {
        "title": "HackMIT 2025",
        "platform": "Devpost",
        "registration_url": "https://devpost.com/hackmit-2025",
        "registration_deadline": "2025-09-01",
        "submission_deadline": "2025-09-15",
        "organizer": "MIT",
        "themes": ["AI", "Web3", "Climate"],
        "mode": "hybrid",
        "location": "Cambridge, MA",
        "prize": "$10,000",
        "team_size": "2-5",
    }
    defaults.update(overrides)
    return Hackathon(**defaults)


def _sample_intelligence(**overrides) -> IntelligenceResult:
    """Create a sample IntelligenceResult with valid values."""
    defaults = {
        "priority": "High",
        "difficulty": "Hard",
        "winning_probability": 35,
        "recommended_stack": ["Python", "LangChain", "React", "AWS"],
        "recommended_team_size": 4,
        "execution_strategy": "Focus on AI theme, build MVP in first 48h, polish last 24h.",
        "summary": "High-priority AI hackathon with strong competition.",
    }
    defaults.update(overrides)
    return IntelligenceResult(**defaults)


# --- Tests for _merge() ---


class TestMerge:
    """Tests for _merge() function that constructs EnrichedHackathon."""

    def test_merge_returns_enriched_hackathon(self):
        """_merge() returns an EnrichedHackathon instance."""
        hackathon = _sample_hackathon()
        intelligence = _sample_intelligence()
        result = _merge(hackathon, intelligence)
        assert isinstance(result, EnrichedHackathon)

    def test_merge_populates_all_18_fields(self):
        """_merge() creates EnrichedHackathon with all 18 fields populated."""
        hackathon = _sample_hackathon()
        intelligence = _sample_intelligence()
        result = _merge(hackathon, intelligence)

        # 11 Hackathon fields
        assert result.title == "HackMIT 2025"
        assert result.platform == "Devpost"
        assert result.registration_url == "https://devpost.com/hackmit-2025"
        assert result.registration_deadline == "2025-09-01"
        assert result.submission_deadline == "2025-09-15"
        assert result.organizer == "MIT"
        assert result.themes == ["AI", "Web3", "Climate"]
        assert result.mode == "hybrid"
        assert result.location == "Cambridge, MA"
        assert result.prize == "$10,000"
        assert result.team_size == "2-5"

        # 7 Intelligence fields
        assert result.priority == "High"
        assert result.difficulty == "Hard"
        assert result.winning_probability == 35
        assert result.recommended_stack == ["Python", "LangChain", "React", "AWS"]
        assert result.recommended_team_size == 4
        assert result.execution_strategy == "Focus on AI theme, build MVP in first 48h, polish last 24h."
        assert result.summary == "High-priority AI hackathon with strong competition."

    def test_merge_preserves_hackathon_fields_unchanged(self):
        """All original Hackathon fields are preserved unchanged in merge."""
        hackathon = _sample_hackathon()
        intelligence = _sample_intelligence()
        result = _merge(hackathon, intelligence)

        # Every Hackathon field must exactly match the original
        assert result.title == hackathon.title
        assert result.platform == hackathon.platform
        assert result.registration_url == hackathon.registration_url
        assert result.registration_deadline == hackathon.registration_deadline
        assert result.submission_deadline == hackathon.submission_deadline
        assert result.organizer == hackathon.organizer
        assert result.themes == hackathon.themes
        assert result.mode == hackathon.mode
        assert result.location == hackathon.location
        assert result.prize == hackathon.prize
        assert result.team_size == hackathon.team_size

    def test_merge_preserves_none_optional_fields(self):
        """None values in optional Hackathon fields are preserved as None."""
        hackathon = _sample_hackathon(
            registration_deadline=None,
            submission_deadline=None,
            organizer=None,
            mode=None,
            location=None,
            prize=None,
            team_size=None,
        )
        intelligence = _sample_intelligence()
        result = _merge(hackathon, intelligence)

        assert result.registration_deadline is None
        assert result.submission_deadline is None
        assert result.organizer is None
        assert result.mode is None
        assert result.location is None
        assert result.prize is None
        assert result.team_size is None

    def test_merge_preserves_empty_themes_list(self):
        """An empty themes list is preserved, not replaced."""
        hackathon = _sample_hackathon(themes=[])
        intelligence = _sample_intelligence()
        result = _merge(hackathon, intelligence)

        assert result.themes == []

    def test_merge_intelligence_fields_from_result(self):
        """Intelligence fields come from the IntelligenceResult, not defaults."""
        hackathon = _sample_hackathon()
        intelligence = _sample_intelligence(
            priority="Low",
            difficulty="Easy",
            winning_probability=95,
            recommended_stack=["Rust"],
            recommended_team_size=1,
            execution_strategy="Solo sprint.",
            summary="Easy solo hackathon.",
        )
        result = _merge(hackathon, intelligence)

        assert result.priority == "Low"
        assert result.difficulty == "Easy"
        assert result.winning_probability == 95
        assert result.recommended_stack == ["Rust"]
        assert result.recommended_team_size == 1
        assert result.execution_strategy == "Solo sprint."
        assert result.summary == "Easy solo hackathon."


# --- Tests for _validate_and_build() ---


class TestValidateAndBuild:
    """Tests for _validate_and_build() that validates intelligence field values."""

    def test_valid_input_returns_intelligence_result(self):
        """Valid parsed dict returns a proper IntelligenceResult."""
        parsed = {
            "priority": "Medium",
            "difficulty": "Medium",
            "winning_probability": 50,
            "recommended_stack": ["Python", "React"],
            "recommended_team_size": 3,
            "execution_strategy": "Build an MVP quickly.",
            "summary": "A medium-priority hackathon.",
        }
        result = _validate_and_build(parsed)
        assert isinstance(result, IntelligenceResult)
        assert result.priority == "Medium"
        assert result.difficulty == "Medium"
        assert result.winning_probability == 50

    def test_invalid_priority_raises_value_error(self):
        """priority must be one of 'High', 'Medium', 'Low'."""
        parsed = {
            "priority": "Critical",
            "difficulty": "Medium",
            "winning_probability": 50,
            "recommended_stack": ["Python"],
            "recommended_team_size": 3,
            "execution_strategy": "Strategy here.",
            "summary": "Summary here.",
        }
        with pytest.raises(ValueError, match="Invalid priority"):
            _validate_and_build(parsed)

    def test_invalid_difficulty_raises_value_error(self):
        """difficulty must be one of 'Easy', 'Medium', 'Hard'."""
        parsed = {
            "priority": "High",
            "difficulty": "Extreme",
            "winning_probability": 50,
            "recommended_stack": ["Python"],
            "recommended_team_size": 3,
            "execution_strategy": "Strategy here.",
            "summary": "Summary here.",
        }
        with pytest.raises(ValueError, match="Invalid difficulty"):
            _validate_and_build(parsed)

    def test_winning_probability_below_zero_raises(self):
        """winning_probability must be >= 0."""
        parsed = {
            "priority": "High",
            "difficulty": "Hard",
            "winning_probability": -1,
            "recommended_stack": ["Python"],
            "recommended_team_size": 3,
            "execution_strategy": "Strategy here.",
            "summary": "Summary here.",
        }
        with pytest.raises(ValueError, match="winning_probability out of range"):
            _validate_and_build(parsed)

    def test_winning_probability_above_100_raises(self):
        """winning_probability must be <= 100."""
        parsed = {
            "priority": "High",
            "difficulty": "Hard",
            "winning_probability": 101,
            "recommended_stack": ["Python"],
            "recommended_team_size": 3,
            "execution_strategy": "Strategy here.",
            "summary": "Summary here.",
        }
        with pytest.raises(ValueError, match="winning_probability out of range"):
            _validate_and_build(parsed)

    def test_winning_probability_boundary_zero(self):
        """winning_probability of 0 is valid."""
        parsed = {
            "priority": "Low",
            "difficulty": "Easy",
            "winning_probability": 0,
            "recommended_stack": ["Go"],
            "recommended_team_size": 2,
            "execution_strategy": "Minimal effort.",
            "summary": "Low chance.",
        }
        result = _validate_and_build(parsed)
        assert result.winning_probability == 0

    def test_winning_probability_boundary_100(self):
        """winning_probability of 100 is valid."""
        parsed = {
            "priority": "High",
            "difficulty": "Easy",
            "winning_probability": 100,
            "recommended_stack": ["Python"],
            "recommended_team_size": 1,
            "execution_strategy": "Easy win.",
            "summary": "Guaranteed.",
        }
        result = _validate_and_build(parsed)
        assert result.winning_probability == 100

    def test_empty_recommended_stack_raises(self):
        """recommended_stack must be non-empty list."""
        parsed = {
            "priority": "High",
            "difficulty": "Hard",
            "winning_probability": 50,
            "recommended_stack": [],
            "recommended_team_size": 3,
            "execution_strategy": "Strategy here.",
            "summary": "Summary here.",
        }
        with pytest.raises(ValueError, match="recommended_stack must be a non-empty list"):
            _validate_and_build(parsed)

    def test_recommended_stack_truncated_to_10(self):
        """recommended_stack longer than 10 items is truncated to 10."""
        parsed = {
            "priority": "High",
            "difficulty": "Hard",
            "winning_probability": 50,
            "recommended_stack": [f"Tech{i}" for i in range(15)],
            "recommended_team_size": 3,
            "execution_strategy": "Strategy here.",
            "summary": "Summary here.",
        }
        result = _validate_and_build(parsed)
        assert len(result.recommended_stack) == 10

    def test_recommended_team_size_below_1_raises(self):
        """recommended_team_size must be >= 1."""
        parsed = {
            "priority": "High",
            "difficulty": "Hard",
            "winning_probability": 50,
            "recommended_stack": ["Python"],
            "recommended_team_size": 0,
            "execution_strategy": "Strategy here.",
            "summary": "Summary here.",
        }
        with pytest.raises(ValueError, match="recommended_team_size out of range"):
            _validate_and_build(parsed)

    def test_recommended_team_size_above_20_raises(self):
        """recommended_team_size must be <= 20."""
        parsed = {
            "priority": "High",
            "difficulty": "Hard",
            "winning_probability": 50,
            "recommended_stack": ["Python"],
            "recommended_team_size": 21,
            "execution_strategy": "Strategy here.",
            "summary": "Summary here.",
        }
        with pytest.raises(ValueError, match="recommended_team_size out of range"):
            _validate_and_build(parsed)

    def test_recommended_team_size_boundary_1(self):
        """recommended_team_size of 1 is valid."""
        parsed = {
            "priority": "Low",
            "difficulty": "Easy",
            "winning_probability": 70,
            "recommended_stack": ["Python"],
            "recommended_team_size": 1,
            "execution_strategy": "Solo work.",
            "summary": "Solo hackathon.",
        }
        result = _validate_and_build(parsed)
        assert result.recommended_team_size == 1

    def test_recommended_team_size_boundary_20(self):
        """recommended_team_size of 20 is valid."""
        parsed = {
            "priority": "High",
            "difficulty": "Hard",
            "winning_probability": 20,
            "recommended_stack": ["Python", "React"],
            "recommended_team_size": 20,
            "execution_strategy": "Large team hackathon.",
            "summary": "Enterprise hackathon.",
        }
        result = _validate_and_build(parsed)
        assert result.recommended_team_size == 20

    def test_empty_execution_strategy_raises(self):
        """execution_strategy must be non-empty."""
        parsed = {
            "priority": "High",
            "difficulty": "Hard",
            "winning_probability": 50,
            "recommended_stack": ["Python"],
            "recommended_team_size": 3,
            "execution_strategy": "",
            "summary": "Summary here.",
        }
        with pytest.raises(ValueError, match="execution_strategy must be non-empty"):
            _validate_and_build(parsed)

    def test_whitespace_only_execution_strategy_raises(self):
        """execution_strategy with only whitespace is treated as empty."""
        parsed = {
            "priority": "High",
            "difficulty": "Hard",
            "winning_probability": 50,
            "recommended_stack": ["Python"],
            "recommended_team_size": 3,
            "execution_strategy": "   ",
            "summary": "Summary here.",
        }
        with pytest.raises(ValueError, match="execution_strategy must be non-empty"):
            _validate_and_build(parsed)

    def test_execution_strategy_truncated_to_2000(self):
        """execution_strategy longer than 2000 chars is truncated."""
        parsed = {
            "priority": "High",
            "difficulty": "Hard",
            "winning_probability": 50,
            "recommended_stack": ["Python"],
            "recommended_team_size": 3,
            "execution_strategy": "x" * 2500,
            "summary": "Summary here.",
        }
        result = _validate_and_build(parsed)
        assert len(result.execution_strategy) == 2000

    def test_empty_summary_raises(self):
        """summary must be non-empty."""
        parsed = {
            "priority": "High",
            "difficulty": "Hard",
            "winning_probability": 50,
            "recommended_stack": ["Python"],
            "recommended_team_size": 3,
            "execution_strategy": "Strategy here.",
            "summary": "",
        }
        with pytest.raises(ValueError, match="summary must be non-empty"):
            _validate_and_build(parsed)

    def test_whitespace_only_summary_raises(self):
        """summary with only whitespace is treated as empty."""
        parsed = {
            "priority": "High",
            "difficulty": "Hard",
            "winning_probability": 50,
            "recommended_stack": ["Python"],
            "recommended_team_size": 3,
            "execution_strategy": "Strategy here.",
            "summary": "   \n  ",
        }
        with pytest.raises(ValueError, match="summary must be non-empty"):
            _validate_and_build(parsed)

    def test_summary_truncated_to_500(self):
        """summary longer than 500 chars is truncated."""
        parsed = {
            "priority": "Medium",
            "difficulty": "Medium",
            "winning_probability": 50,
            "recommended_stack": ["Python"],
            "recommended_team_size": 3,
            "execution_strategy": "Strategy.",
            "summary": "s" * 600,
        }
        result = _validate_and_build(parsed)
        assert len(result.summary) == 500

    def test_missing_field_raises_key_error(self):
        """Missing required field raises KeyError."""
        parsed = {
            "priority": "High",
            "difficulty": "Hard",
            # winning_probability missing
            "recommended_stack": ["Python"],
            "recommended_team_size": 3,
            "execution_strategy": "Strategy.",
            "summary": "Summary.",
        }
        with pytest.raises(KeyError):
            _validate_and_build(parsed)
