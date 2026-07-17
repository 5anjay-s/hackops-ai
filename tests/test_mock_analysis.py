"""Unit tests for Intelligence Agent mock analysis and fallback logic.

Tests cover:
- Mock produces valid IntelligenceResult for different hackathon inputs
- Same input always produces same output (deterministic - requirement 7.3)
- Fallback triggers on Bedrock failures (requirements 7.1, 7.2)
- Per-hackathon fallback (requirement 12.3)
- Entire batch fallback when credentials missing (requirement 7.1)
"""

import json
from json import JSONDecodeError
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

from agents.intelligence_agent import (
    _mock_analysis,
    analyze_batch,
    analyze_single,
    _check_bedrock_available,
)
from models.hackathon import Hackathon, IntelligenceResult, EnrichedHackathon


# --- Test fixtures ---


def _hackathon_with_prize() -> Hackathon:
    """Hackathon with a dollar-sign prize (High priority path)."""
    return Hackathon(
        title="HackMIT 2025",
        platform="Devpost",
        registration_url="https://devpost.com/hackmit-2025",
        registration_deadline="2025-09-01",
        submission_deadline="2025-09-15",
        organizer="MIT",
        themes=["AI", "Web3"],
        mode="hybrid",
        location="Cambridge, MA",
        prize="$10,000",
        team_size="2-5",
    )


def _hackathon_with_themes() -> Hackathon:
    """Hackathon with themes but no dollar prize (Medium priority path)."""
    return Hackathon(
        title="DevHacks 2025",
        platform="Devfolio",
        registration_url="https://devfolio.co/devhacks",
        themes=["Healthcare", "Education"],
    )


def _hackathon_minimal() -> Hackathon:
    """Minimal hackathon with no prize and no themes (Low priority path)."""
    return Hackathon(
        title="Weekend Hack",
        platform="Unstop",
        registration_url="https://unstop.com/weekend-hack",
    )


def _hackathon_prize_no_dollar() -> Hackathon:
    """Hackathon with prize but no dollar sign (should NOT be High priority)."""
    return Hackathon(
        title="Euro Hack",
        platform="Devpost",
        registration_url="https://devpost.com/euro-hack",
        prize="€5,000",
        themes=[],
    )


# --- Tests for _mock_analysis output validity (requirement 7.4) ---


class TestMockAnalysisValidity:
    """Verify mock produces valid IntelligenceResult objects."""

    def test_high_priority_when_prize_has_dollar(self):
        hackathon = _hackathon_with_prize()
        result = _mock_analysis(hackathon)

        assert isinstance(result, IntelligenceResult)
        assert result.priority == "High"
        assert result.difficulty == "Hard"
        assert result.winning_probability == 30

    def test_medium_priority_when_themes_present(self):
        hackathon = _hackathon_with_themes()
        result = _mock_analysis(hackathon)

        assert isinstance(result, IntelligenceResult)
        assert result.priority == "Medium"
        assert result.difficulty == "Medium"
        assert result.winning_probability == 50

    def test_low_priority_when_no_prize_no_themes(self):
        hackathon = _hackathon_minimal()
        result = _mock_analysis(hackathon)

        assert isinstance(result, IntelligenceResult)
        assert result.priority == "Low"
        assert result.difficulty == "Easy"
        assert result.winning_probability == 70

    def test_prize_without_dollar_sign_not_high_priority(self):
        hackathon = _hackathon_prize_no_dollar()
        result = _mock_analysis(hackathon)

        # Prize exists but no "$" — and no themes → Low priority
        assert result.priority == "Low"
        assert result.difficulty == "Easy"
        assert result.winning_probability == 70

    def test_priority_in_valid_set(self):
        for hackathon in [_hackathon_with_prize(), _hackathon_with_themes(), _hackathon_minimal()]:
            result = _mock_analysis(hackathon)
            assert result.priority in {"High", "Medium", "Low"}

    def test_difficulty_in_valid_set(self):
        for hackathon in [_hackathon_with_prize(), _hackathon_with_themes(), _hackathon_minimal()]:
            result = _mock_analysis(hackathon)
            assert result.difficulty in {"Easy", "Medium", "Hard"}

    def test_winning_probability_in_range(self):
        for hackathon in [_hackathon_with_prize(), _hackathon_with_themes(), _hackathon_minimal()]:
            result = _mock_analysis(hackathon)
            assert 0 <= result.winning_probability <= 100

    def test_recommended_stack_non_empty(self):
        for hackathon in [_hackathon_with_prize(), _hackathon_with_themes(), _hackathon_minimal()]:
            result = _mock_analysis(hackathon)
            assert isinstance(result.recommended_stack, list)
            assert len(result.recommended_stack) > 0

    def test_recommended_team_size_positive(self):
        for hackathon in [_hackathon_with_prize(), _hackathon_with_themes(), _hackathon_minimal()]:
            result = _mock_analysis(hackathon)
            assert result.recommended_team_size >= 1

    def test_execution_strategy_non_empty(self):
        for hackathon in [_hackathon_with_prize(), _hackathon_with_themes(), _hackathon_minimal()]:
            result = _mock_analysis(hackathon)
            assert isinstance(result.execution_strategy, str)
            assert len(result.execution_strategy.strip()) > 0

    def test_summary_non_empty(self):
        for hackathon in [_hackathon_with_prize(), _hackathon_with_themes(), _hackathon_minimal()]:
            result = _mock_analysis(hackathon)
            assert isinstance(result.summary, str)
            assert len(result.summary.strip()) > 0

    def test_summary_contains_platform(self):
        hackathon = _hackathon_with_prize()
        result = _mock_analysis(hackathon)
        assert hackathon.platform in result.summary


# --- Tests for determinism (requirement 7.3) ---


class TestMockAnalysisDeterminism:
    """Verify same input always produces same output."""

    def test_identical_input_produces_identical_output(self):
        hackathon = _hackathon_with_prize()
        result1 = _mock_analysis(hackathon)
        result2 = _mock_analysis(hackathon)

        assert result1.priority == result2.priority
        assert result1.difficulty == result2.difficulty
        assert result1.winning_probability == result2.winning_probability
        assert result1.recommended_stack == result2.recommended_stack
        assert result1.recommended_team_size == result2.recommended_team_size
        assert result1.execution_strategy == result2.execution_strategy
        assert result1.summary == result2.summary

    def test_determinism_with_themes(self):
        hackathon = _hackathon_with_themes()
        result1 = _mock_analysis(hackathon)
        result2 = _mock_analysis(hackathon)

        assert result1.priority == result2.priority
        assert result1.difficulty == result2.difficulty
        assert result1.winning_probability == result2.winning_probability

    def test_determinism_minimal(self):
        hackathon = _hackathon_minimal()
        result1 = _mock_analysis(hackathon)
        result2 = _mock_analysis(hackathon)

        assert result1.priority == result2.priority
        assert result1.difficulty == result2.difficulty
        assert result1.winning_probability == result2.winning_probability

    def test_multiple_calls_same_result(self):
        """Call mock 10 times and verify all results are identical."""
        hackathon = _hackathon_with_prize()
        results = [_mock_analysis(hackathon) for _ in range(10)]

        for r in results[1:]:
            assert r.priority == results[0].priority
            assert r.difficulty == results[0].difficulty
            assert r.winning_probability == results[0].winning_probability
            assert r.recommended_stack == results[0].recommended_stack


# --- Tests for fallback triggers (requirements 7.1, 7.2, 12.3) ---


class TestFallbackTriggers:
    """Verify fallback triggers on various Bedrock failure scenarios."""

    @patch("agents.intelligence_agent._call_bedrock")
    def test_fallback_on_botocore_error(self, mock_bedrock):
        """BotoCoreError (e.g., timeout) triggers mock fallback."""
        mock_bedrock.side_effect = BotoCoreError()
        hackathon = _hackathon_with_prize()

        result = analyze_single(hackathon)

        assert isinstance(result, IntelligenceResult)
        assert result.priority == "High"  # Mock deterministic result

    @patch("agents.intelligence_agent._call_bedrock")
    def test_fallback_on_client_error(self, mock_bedrock):
        """ClientError (e.g., access denied) triggers mock fallback."""
        mock_bedrock.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "Access denied"}},
            "InvokeModel",
        )
        hackathon = _hackathon_with_themes()

        result = analyze_single(hackathon)

        assert isinstance(result, IntelligenceResult)
        assert result.priority == "Medium"  # Mock deterministic result

    @patch("agents.intelligence_agent._call_bedrock")
    def test_fallback_on_json_decode_error(self, mock_bedrock):
        """JSONDecodeError (invalid response) triggers mock fallback."""
        mock_bedrock.side_effect = JSONDecodeError("Expecting value", "", 0)
        hackathon = _hackathon_minimal()

        result = analyze_single(hackathon)

        assert isinstance(result, IntelligenceResult)
        assert result.priority == "Low"  # Mock deterministic result

    @patch("agents.intelligence_agent._call_bedrock")
    def test_fallback_on_value_error(self, mock_bedrock):
        """ValueError (invalid field values) triggers mock fallback."""
        mock_bedrock.side_effect = ValueError("Invalid priority: Unknown")
        hackathon = _hackathon_with_prize()

        result = analyze_single(hackathon)

        assert isinstance(result, IntelligenceResult)
        assert result.priority == "High"

    @patch("agents.intelligence_agent._call_bedrock")
    def test_fallback_on_key_error(self, mock_bedrock):
        """KeyError (missing fields in response) triggers mock fallback."""
        mock_bedrock.side_effect = KeyError("priority")
        hackathon = _hackathon_with_prize()

        result = analyze_single(hackathon)

        assert isinstance(result, IntelligenceResult)
        assert result.priority == "High"

    @patch("agents.intelligence_agent._call_bedrock")
    def test_fallback_on_generic_exception(self, mock_bedrock):
        """Any unexpected exception triggers mock fallback."""
        mock_bedrock.side_effect = RuntimeError("Unexpected error")
        hackathon = _hackathon_with_prize()

        result = analyze_single(hackathon)

        assert isinstance(result, IntelligenceResult)
        assert result.priority == "High"


# --- Tests for per-hackathon fallback (requirement 12.3) ---


class TestPerHackathonFallback:
    """If Bedrock fails for one item, use mock for that item, continue batch."""

    @patch("agents.intelligence_agent._check_bedrock_available", return_value=True)
    @patch("agents.intelligence_agent._call_bedrock")
    def test_partial_bedrock_failure_uses_mock_for_failed_items(
        self, mock_bedrock, mock_check
    ):
        """When Bedrock fails for some items, those get mock, others get Bedrock results."""
        hackathons = [_hackathon_with_prize(), _hackathon_with_themes(), _hackathon_minimal()]

        # First call succeeds, second fails, third succeeds
        success_result = IntelligenceResult(
            priority="High",
            difficulty="Hard",
            winning_probability=45,
            recommended_stack=["Python", "TensorFlow"],
            recommended_team_size=4,
            execution_strategy="Focus on AI innovation.",
            summary="Strong AI hackathon.",
        )
        mock_bedrock.side_effect = [
            success_result,
            BotoCoreError(),  # Second item fails
            success_result,
        ]

        results = analyze_batch(hackathons)

        assert len(results) == 3
        # First and third got Bedrock result
        assert results[0].winning_probability == 45
        # Second got mock fallback (themes present → Medium)
        assert results[1].priority == "Medium"
        assert results[1].winning_probability == 50
        # Third got Bedrock result
        assert results[2].winning_probability == 45


# --- Tests for entire batch fallback when credentials missing (requirement 7.1) ---


class TestCredentialsMissingFallback:
    """If credentials are missing, fall back to mock for entire batch."""

    @patch("agents.intelligence_agent.boto3.client")
    def test_credentials_missing_falls_back_entire_batch(self, mock_boto_client):
        """When boto3 client creation fails, all items use mock."""
        mock_boto_client.side_effect = NoCredentialsError()

        hackathons = [_hackathon_with_prize(), _hackathon_with_themes(), _hackathon_minimal()]
        results = analyze_batch(hackathons)

        assert len(results) == 3
        # All should be mock results
        assert results[0].priority == "High"
        assert results[0].winning_probability == 30
        assert results[1].priority == "Medium"
        assert results[1].winning_probability == 50
        assert results[2].priority == "Low"
        assert results[2].winning_probability == 70

    @patch("agents.intelligence_agent.boto3.client")
    def test_credentials_missing_never_calls_bedrock(self, mock_boto_client):
        """When credentials missing, _call_bedrock is never invoked."""
        mock_boto_client.side_effect = NoCredentialsError()

        hackathons = [_hackathon_with_prize()]

        with patch("agents.intelligence_agent._call_bedrock") as mock_call:
            results = analyze_batch(hackathons)
            mock_call.assert_not_called()

        assert len(results) == 1

    @patch("agents.intelligence_agent.boto3.client")
    def test_check_bedrock_available_returns_false_on_error(self, mock_boto_client):
        """_check_bedrock_available returns False when client creation fails."""
        mock_boto_client.side_effect = BotoCoreError()
        assert _check_bedrock_available() is False

    @patch("agents.intelligence_agent.boto3.client")
    def test_check_bedrock_available_returns_true_on_success(self, mock_boto_client):
        """_check_bedrock_available returns True when client is created."""
        mock_boto_client.return_value = MagicMock()
        assert _check_bedrock_available() is True


# --- Tests for empty batch handling ---


class TestEmptyBatch:
    """Verify empty input produces empty output."""

    @patch("agents.intelligence_agent._check_bedrock_available", return_value=True)
    def test_empty_list_returns_empty(self, mock_check):
        results = analyze_batch([])
        assert results == []

    @patch("agents.intelligence_agent._check_bedrock_available", return_value=False)
    def test_empty_list_with_mock_fallback_returns_empty(self, mock_check):
        results = analyze_batch([])
        assert results == []


# --- Tests for timeout configuration ---


class TestTimeoutConfiguration:
    """Verify the Bedrock timeout is configured correctly."""

    def test_timeout_is_10_seconds(self):
        from agents.intelligence_agent import _BEDROCK_TIMEOUT
        assert _BEDROCK_TIMEOUT == 10

    def test_boto_config_uses_timeout(self):
        from agents.intelligence_agent import _BOTO_CONFIG
        assert _BOTO_CONFIG.read_timeout == 10
        assert _BOTO_CONFIG.connect_timeout == 10
