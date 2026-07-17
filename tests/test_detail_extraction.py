"""Unit tests for _extract_hackathon_details retry logic.

Tests verify:
- Requirement 3.2: Retry once after 2-second delay on failure
- Requirement 3.3: Return partial data with None on retry failure
- Requirement 3.4: Never raise exceptions that halt the pipeline
- Requirement 12.2: Include hackathon with partial data after retry failure
"""

from unittest.mock import patch, MagicMock
import requests
import pytest

from agents.discovery_agent import _extract_hackathon_details, REQUEST_TIMEOUT


# Expected keys in the returned dict
EXPECTED_KEYS = {
    "registration_deadline",
    "submission_deadline",
    "prize",
    "themes",
    "team_size",
    "organizer",
    "mode",
    "location",
}


class TestDetailExtractionSuccess:
    """Tests for successful detail page fetches."""

    @patch("agents.discovery_agent.requests.get")
    @patch("agents.discovery_agent._enforce_delay")
    def test_returns_dict_with_expected_keys_on_success(self, mock_delay, mock_get):
        """On successful fetch, returns dict with all expected keys."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html><body><p>Some hackathon page</p></body></html>"
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = _extract_hackathon_details("https://example.com/hack", "Devpost")

        assert isinstance(result, dict)
        assert set(result.keys()) == EXPECTED_KEYS

    @patch("agents.discovery_agent.requests.get")
    @patch("agents.discovery_agent._enforce_delay")
    def test_calls_with_correct_timeout(self, mock_delay, mock_get):
        """Uses REQUEST_TIMEOUT (15s) for the request."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html><body></body></html>"
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        _extract_hackathon_details("https://example.com/hack", "Devpost")

        mock_get.assert_called_once()
        _, kwargs = mock_get.call_args
        assert kwargs["timeout"] == REQUEST_TIMEOUT


class TestDetailExtractionRetryOnFailure:
    """Tests for retry behavior on HTTP failures (Requirement 3.2)."""

    @patch("agents.discovery_agent.time.sleep")
    @patch("agents.discovery_agent.requests.get")
    @patch("agents.discovery_agent._enforce_delay")
    def test_retries_once_on_http_error(self, mock_delay, mock_get, mock_sleep):
        """On non-2xx response, retries once after 2-second delay."""
        # First call raises HTTPError, second call succeeds
        mock_resp_fail = MagicMock()
        mock_resp_fail.raise_for_status.side_effect = requests.exceptions.HTTPError("404")

        mock_resp_success = MagicMock()
        mock_resp_success.status_code = 200
        mock_resp_success.text = "<html><body><p>content</p></body></html>"
        mock_resp_success.raise_for_status = MagicMock()

        mock_get.side_effect = [mock_resp_fail, mock_resp_success]

        result = _extract_hackathon_details("https://example.com/hack", "Devpost")

        # Should have retried (2 get calls total)
        assert mock_get.call_count == 2
        # Should have slept 2 seconds before retry
        mock_sleep.assert_called_once_with(2)
        # Should return valid dict
        assert isinstance(result, dict)
        assert set(result.keys()) == EXPECTED_KEYS

    @patch("agents.discovery_agent.time.sleep")
    @patch("agents.discovery_agent.requests.get")
    @patch("agents.discovery_agent._enforce_delay")
    def test_retries_once_on_connection_error(self, mock_delay, mock_get, mock_sleep):
        """On connection error, retries once after 2-second delay."""
        # First call raises ConnectionError, second succeeds
        mock_resp_success = MagicMock()
        mock_resp_success.status_code = 200
        mock_resp_success.text = "<html><body></body></html>"
        mock_resp_success.raise_for_status = MagicMock()

        mock_get.side_effect = [
            requests.exceptions.ConnectionError("Connection refused"),
            mock_resp_success,
        ]

        result = _extract_hackathon_details("https://example.com/hack", "Devpost")

        assert mock_get.call_count == 2
        mock_sleep.assert_called_once_with(2)
        assert isinstance(result, dict)

    @patch("agents.discovery_agent.time.sleep")
    @patch("agents.discovery_agent.requests.get")
    @patch("agents.discovery_agent._enforce_delay")
    def test_retries_once_on_timeout(self, mock_delay, mock_get, mock_sleep):
        """On timeout (>15s), retries once after 2-second delay."""
        # First call raises Timeout, second succeeds
        mock_resp_success = MagicMock()
        mock_resp_success.status_code = 200
        mock_resp_success.text = "<html><body></body></html>"
        mock_resp_success.raise_for_status = MagicMock()

        mock_get.side_effect = [
            requests.exceptions.Timeout("Request timed out"),
            mock_resp_success,
        ]

        result = _extract_hackathon_details("https://example.com/hack", "Devpost")

        assert mock_get.call_count == 2
        mock_sleep.assert_called_once_with(2)
        assert isinstance(result, dict)

    @patch("agents.discovery_agent.time.sleep")
    @patch("agents.discovery_agent.requests.get")
    @patch("agents.discovery_agent._enforce_delay")
    def test_retry_delay_is_at_least_2_seconds(self, mock_delay, mock_get, mock_sleep):
        """The retry delay must be at least 2 seconds (Requirement 3.2)."""
        mock_get.side_effect = requests.exceptions.ConnectionError("fail")

        _extract_hackathon_details("https://example.com/hack", "Devpost")

        # The first sleep(2) is the retry delay; verify it's called with 2
        assert mock_sleep.call_args_list[0][0][0] >= 2


class TestDetailExtractionRetryFailure:
    """Tests for behavior when retry also fails (Requirement 3.3)."""

    @patch("agents.discovery_agent.time.sleep")
    @patch("agents.discovery_agent.requests.get")
    @patch("agents.discovery_agent._enforce_delay")
    def test_returns_partial_data_on_double_failure(self, mock_delay, mock_get, mock_sleep):
        """When both attempts fail, returns dict with None for all fields."""
        mock_get.side_effect = requests.exceptions.ConnectionError("Connection refused")

        result = _extract_hackathon_details("https://example.com/hack", "Devpost")

        assert isinstance(result, dict)
        assert set(result.keys()) == EXPECTED_KEYS
        assert result["registration_deadline"] is None
        assert result["submission_deadline"] is None
        assert result["prize"] is None
        assert result["themes"] == []
        assert result["team_size"] is None
        assert result["organizer"] is None
        assert result["mode"] is None
        assert result["location"] is None

    @patch("agents.discovery_agent.time.sleep")
    @patch("agents.discovery_agent.requests.get")
    @patch("agents.discovery_agent._enforce_delay")
    def test_only_retries_once(self, mock_delay, mock_get, mock_sleep):
        """Makes at most 2 HTTP requests (1 initial + 1 retry)."""
        mock_get.side_effect = requests.exceptions.Timeout("timeout")

        _extract_hackathon_details("https://example.com/hack", "Devpost")

        # Should be exactly 2 calls: initial + one retry
        assert mock_get.call_count == 2

    @patch("agents.discovery_agent.time.sleep")
    @patch("agents.discovery_agent.requests.get")
    @patch("agents.discovery_agent._enforce_delay")
    def test_returns_partial_on_http_500_both_attempts(self, mock_delay, mock_get, mock_sleep):
        """HTTP 500 on both attempts returns partial data."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError("500 Server Error")
        mock_get.return_value = mock_resp

        result = _extract_hackathon_details("https://example.com/hack", "Devpost")

        assert result["registration_deadline"] is None
        assert result["submission_deadline"] is None
        assert result["prize"] is None


class TestDetailExtractionNeverRaises:
    """Tests verifying the function never raises exceptions (Requirement 3.4, 12.2)."""

    @patch("agents.discovery_agent.time.sleep")
    @patch("agents.discovery_agent.requests.get")
    @patch("agents.discovery_agent._enforce_delay")
    def test_never_raises_on_connection_error(self, mock_delay, mock_get, mock_sleep):
        """Connection errors never propagate to caller."""
        mock_get.side_effect = requests.exceptions.ConnectionError("Connection refused")

        # Should not raise
        result = _extract_hackathon_details("https://example.com/hack", "Devpost")
        assert isinstance(result, dict)

    @patch("agents.discovery_agent.time.sleep")
    @patch("agents.discovery_agent.requests.get")
    @patch("agents.discovery_agent._enforce_delay")
    def test_never_raises_on_timeout(self, mock_delay, mock_get, mock_sleep):
        """Timeout errors never propagate to caller."""
        mock_get.side_effect = requests.exceptions.Timeout("Request timed out")

        result = _extract_hackathon_details("https://example.com/hack", "Devpost")
        assert isinstance(result, dict)

    @patch("agents.discovery_agent.time.sleep")
    @patch("agents.discovery_agent.requests.get")
    @patch("agents.discovery_agent._enforce_delay")
    def test_never_raises_on_http_error(self, mock_delay, mock_get, mock_sleep):
        """HTTP errors never propagate to caller."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError("403 Forbidden")
        mock_get.return_value = mock_resp

        result = _extract_hackathon_details("https://example.com/hack", "Devpost")
        assert isinstance(result, dict)

    @patch("agents.discovery_agent.time.sleep")
    @patch("agents.discovery_agent.requests.get")
    @patch("agents.discovery_agent._enforce_delay")
    def test_never_raises_on_generic_exception(self, mock_delay, mock_get, mock_sleep):
        """Unexpected exceptions never propagate to caller."""
        mock_get.side_effect = RuntimeError("Unexpected error")

        result = _extract_hackathon_details("https://example.com/hack", "Devpost")
        assert isinstance(result, dict)

    @patch("agents.discovery_agent.time.sleep")
    @patch("agents.discovery_agent.requests.get")
    @patch("agents.discovery_agent._enforce_delay")
    def test_never_raises_on_ssl_error(self, mock_delay, mock_get, mock_sleep):
        """SSL errors never propagate to caller."""
        mock_get.side_effect = requests.exceptions.SSLError("SSL certificate verify failed")

        result = _extract_hackathon_details("https://example.com/hack", "Devpost")
        assert isinstance(result, dict)


class TestDetailExtractionNoRetryFlag:
    """Tests for when retry=False is passed (second attempt)."""

    @patch("agents.discovery_agent.time.sleep")
    @patch("agents.discovery_agent.requests.get")
    @patch("agents.discovery_agent._enforce_delay")
    def test_no_retry_returns_empty_immediately(self, mock_delay, mock_get, mock_sleep):
        """When retry=False, returns partial data immediately on failure."""
        mock_get.side_effect = requests.exceptions.ConnectionError("fail")

        result = _extract_hackathon_details(
            "https://example.com/hack", "Devpost", retry=False
        )

        # Should only make 1 request (no retry)
        assert mock_get.call_count == 1
        assert result["registration_deadline"] is None
        assert result["submission_deadline"] is None

    @patch("agents.discovery_agent.time.sleep")
    @patch("agents.discovery_agent.requests.get")
    @patch("agents.discovery_agent._enforce_delay")
    def test_no_retry_does_not_sleep(self, mock_delay, mock_get, mock_sleep):
        """When retry=False, no 2-second delay is applied."""
        mock_get.side_effect = requests.exceptions.Timeout("timeout")

        _extract_hackathon_details("https://example.com/hack", "Devpost", retry=False)

        # sleep should not be called for the retry delay
        mock_sleep.assert_not_called()


class TestDetailExtractionPlatformDelay:
    """Tests verifying delay enforcement between requests."""

    @patch("agents.discovery_agent.time.sleep")
    @patch("agents.discovery_agent.requests.get")
    @patch("agents.discovery_agent._enforce_delay")
    def test_enforces_platform_delay(self, mock_delay, mock_get, mock_sleep):
        """Calls _enforce_delay with the platform name before each request."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html><body></body></html>"
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        _extract_hackathon_details("https://example.com/hack", "Devpost")

        mock_delay.assert_called_with("Devpost")

    @patch("agents.discovery_agent.time.sleep")
    @patch("agents.discovery_agent.requests.get")
    @patch("agents.discovery_agent._enforce_delay")
    def test_enforces_delay_for_different_platforms(self, mock_delay, mock_get, mock_sleep):
        """Works with all supported platforms."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html><body></body></html>"
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        _extract_hackathon_details("https://devfolio.co/hack", "Devfolio")
        mock_delay.assert_called_with("Devfolio")

        _extract_hackathon_details("https://unstop.com/hack", "Unstop")
        mock_delay.assert_called_with("Unstop")
