"""Unit tests for Workspace Agent: _get_next_serial and _create_page."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Patch environment before importing workspace_agent
os.environ.setdefault("NOTION_TOKEN", "test-token")
os.environ.setdefault("DATABASE_ID", "test-db-id")

from agents.workspace_agent import _get_next_serial, _create_page
from models.hackathon import EnrichedHackathon


class TestGetNextSerial:
    """Tests for _get_next_serial logic."""

    def test_empty_pages_returns_1(self):
        """If no pages exist, serial starts at 1."""
        assert _get_next_serial([]) == 1

    def test_single_page_with_serial(self):
        """Returns max serial + 1 when pages have serial numbers."""
        pages = [{"serial": 5, "page_id": "a", "title": "X", "platform": "Devpost"}]
        assert _get_next_serial(pages) == 6

    def test_multiple_pages_returns_max_plus_one(self):
        """Finds the max serial among multiple pages."""
        pages = [
            {"serial": 3, "page_id": "a"},
            {"serial": 7, "page_id": "b"},
            {"serial": 2, "page_id": "c"},
        ]
        assert _get_next_serial(pages) == 8

    def test_all_none_serials_falls_back_to_page_count(self):
        """Falls back to len(pages) + 1 when all serials are None."""
        pages = [
            {"serial": None, "page_id": "a"},
            {"serial": None, "page_id": "b"},
            {"serial": None, "page_id": "c"},
        ]
        assert _get_next_serial(pages) == 4  # len(3) + 1

    def test_mixed_none_and_valid_serials(self):
        """Ignores None serials and uses max of valid ones."""
        pages = [
            {"serial": None, "page_id": "a"},
            {"serial": 10, "page_id": "b"},
            {"serial": None, "page_id": "c"},
            {"serial": 5, "page_id": "d"},
        ]
        assert _get_next_serial(pages) == 11

    def test_serial_of_1_returns_2(self):
        """Edge case: single page with serial 1."""
        pages = [{"serial": 1, "page_id": "a"}]
        assert _get_next_serial(pages) == 2


class TestCreatePage:
    """Tests for _create_page Notion property mapping."""

    def _make_hackathon(self, **overrides) -> EnrichedHackathon:
        defaults = {
            "title": "Test Hackathon",
            "platform": "Devpost",
            "registration_url": "https://devpost.com/test",
            "registration_deadline": "2025-09-01",
            "submission_deadline": "2025-09-15",
            "organizer": "TestOrg",
            "themes": ["AI", "Web3"],
            "mode": "online",
            "location": None,
            "prize": "$10,000",
            "team_size": "2-5",
            "priority": "High",
            "difficulty": "Hard",
            "winning_probability": 35,
            "recommended_stack": ["Python", "React"],
            "recommended_team_size": 4,
            "execution_strategy": "Build MVP fast",
            "summary": "A great hackathon",
        }
        defaults.update(overrides)
        return EnrichedHackathon(**defaults)

    @patch("agents.workspace_agent.notion")
    def test_create_page_calls_notion_with_correct_properties(self, mock_notion):
        """Verify _create_page maps all fields to correct Notion property format."""
        mock_notion.pages.create = MagicMock(return_value={"id": "new-page-id"})
        hackathon = self._make_hackathon()

        result = _create_page(hackathon, serial=5)

        assert result is True
        mock_notion.pages.create.assert_called_once()
        call_kwargs = mock_notion.pages.create.call_args[1]

        assert call_kwargs["parent"] == {"database_id": "test-db-id"}
        props = call_kwargs["properties"]

        # Verify serial number
        assert props["S.No"] == {"number": 5}

        # Verify title
        assert props["Hackathon"]["title"][0]["text"]["content"] == "Test Hackathon"

        # Verify platform
        assert props["Platform"] == {"select": {"name": "Devpost"}}

        # Verify dates
        assert props["Deadline"] == {"date": {"start": "2025-09-01"}}
        assert props["Submission Deadline"] == {"date": {"start": "2025-09-15"}}

        # Verify themes
        assert props["Themes"] == {
            "multi_select": [{"name": "AI"}, {"name": "Web3"}]
        }

        # Verify rich text fields
        assert props["Prize"]["rich_text"][0]["text"]["content"] == "$10,000"
        assert props["Team Size"]["rich_text"][0]["text"]["content"] == "2-5"
        assert props["Execution Strategy"]["rich_text"][0]["text"]["content"] == "Build MVP fast"

        # Verify selects
        assert props["Priority"] == {"select": {"name": "High"}}
        assert props["Difficulty"] == {"select": {"name": "Hard"}}

        # Verify number
        assert props["Winning %"] == {"number": 35}

        # Verify multi-select stack
        assert props["Suggested Stack"] == {
            "multi_select": [{"name": "Python"}, {"name": "React"}]
        }

        # Verify status
        assert props["Status"] == {"status": {"name": "Active"}}

        # Verify URL
        assert props["Registration Link"] == {"url": "https://devpost.com/test"}

        # Verify Last Synced is set (ISO 8601 UTC format)
        last_synced = props["Last Synced"]["date"]["start"]
        assert last_synced.endswith("Z")
        assert "T" in last_synced

    @patch("agents.workspace_agent.notion")
    def test_create_page_with_none_deadlines(self, mock_notion):
        """When deadlines are None, date properties should be set to None."""
        mock_notion.pages.create = MagicMock(return_value={"id": "new-page-id"})
        hackathon = self._make_hackathon(
            registration_deadline=None, submission_deadline=None
        )

        result = _create_page(hackathon, serial=1)

        assert result is True
        props = mock_notion.pages.create.call_args[1]["properties"]
        assert props["Deadline"] == {"date": None}
        assert props["Submission Deadline"] == {"date": None}

    @patch("agents.workspace_agent.notion")
    def test_create_page_with_none_prize_and_team_size(self, mock_notion):
        """When prize/team_size are None, rich text should contain empty string."""
        mock_notion.pages.create = MagicMock(return_value={"id": "new-page-id"})
        hackathon = self._make_hackathon(prize=None, team_size=None)

        result = _create_page(hackathon, serial=1)

        assert result is True
        props = mock_notion.pages.create.call_args[1]["properties"]
        assert props["Prize"]["rich_text"][0]["text"]["content"] == ""
        assert props["Team Size"]["rich_text"][0]["text"]["content"] == ""

    @patch("agents.workspace_agent.notion")
    def test_create_page_returns_false_on_exception(self, mock_notion):
        """If Notion API raises, _create_page returns False."""
        mock_notion.pages.create = MagicMock(side_effect=Exception("API error"))
        hackathon = self._make_hackathon()

        result = _create_page(hackathon, serial=1)

        assert result is False

    @patch("agents.workspace_agent.notion")
    def test_create_page_empty_themes_and_stack(self, mock_notion):
        """Empty lists produce empty multi_select arrays."""
        mock_notion.pages.create = MagicMock(return_value={"id": "new-page-id"})
        hackathon = self._make_hackathon(themes=[], recommended_stack=[])

        result = _create_page(hackathon, serial=1)

        assert result is True
        props = mock_notion.pages.create.call_args[1]["properties"]
        assert props["Themes"] == {"multi_select": []}
        assert props["Suggested Stack"] == {"multi_select": []}


# --- Task 6.4: Deduplication matching and archive logic tests ---

from agents.workspace_agent import _find_existing, _archive_expired


class TestFindExisting:
    """Tests for _find_existing — case-sensitive deduplication lookup."""

    def test_finds_exact_match(self):
        """Returns page_id when (title, platform) matches exactly."""
        existing_map = {
            ("HackMIT 2025", "Devpost"): "page-123",
            ("BuildathonX", "Unstop"): "page-456",
        }
        result = _find_existing("HackMIT 2025", "Devpost", existing_map)
        assert result == "page-123"

    def test_returns_none_when_not_found(self):
        """Returns None when (title, platform) not in map."""
        existing_map = {("HackMIT 2025", "Devpost"): "page-123"}
        result = _find_existing("Other Hack", "Devpost", existing_map)
        assert result is None

    def test_case_sensitive_title(self):
        """Does not match when title case differs (case-sensitive per Req 8.2)."""
        existing_map = {("HackMIT 2025", "Devpost"): "page-123"}
        result = _find_existing("hackmit 2025", "Devpost", existing_map)
        assert result is None

    def test_case_sensitive_platform(self):
        """Does not match when platform case differs."""
        existing_map = {("HackMIT 2025", "Devpost"): "page-123"}
        result = _find_existing("HackMIT 2025", "devpost", existing_map)
        assert result is None

    def test_empty_map(self):
        """Returns None for empty existing_map."""
        result = _find_existing("HackMIT", "Devpost", {})
        assert result is None


class TestArchiveExpired:
    """Tests for _archive_expired — archiving pages past their deadline."""

    @patch("agents.workspace_agent.notion")
    def test_archives_expired_page(self, mock_notion):
        """Archives a page whose deadline is before today."""
        mock_notion.pages.update = MagicMock()

        pages = [
            {
                "page_id": "page-1",
                "title": "Old Hack",
                "platform": "Devpost",
                "deadline": "2020-01-01",
                "status": "Active",
            }
        ]

        result = _archive_expired(pages)
        assert result == 1
        mock_notion.pages.update.assert_called_once_with(
            page_id="page-1",
            properties={"Status": {"status": {"name": "Expired"}}},
        )

    @patch("agents.workspace_agent.notion")
    def test_does_not_archive_none_deadline(self, mock_notion):
        """Does NOT archive pages with None deadline (Requirement 9.4)."""
        mock_notion.pages.update = MagicMock()

        pages = [
            {
                "page_id": "page-1",
                "title": "No Deadline Hack",
                "platform": "Devpost",
                "deadline": None,
                "status": "Active",
            }
        ]

        result = _archive_expired(pages)
        assert result == 0
        mock_notion.pages.update.assert_not_called()

    @patch("agents.workspace_agent.notion")
    def test_does_not_archive_already_expired(self, mock_notion):
        """Does NOT re-archive pages already with status "Expired"."""
        mock_notion.pages.update = MagicMock()

        pages = [
            {
                "page_id": "page-1",
                "title": "Already Expired",
                "platform": "Devpost",
                "deadline": "2020-01-01",
                "status": "Expired",
            }
        ]

        result = _archive_expired(pages)
        assert result == 0
        mock_notion.pages.update.assert_not_called()

    @patch("agents.workspace_agent.notion")
    def test_does_not_archive_future_deadline(self, mock_notion):
        """Does NOT archive pages with deadline in the future."""
        mock_notion.pages.update = MagicMock()

        pages = [
            {
                "page_id": "page-1",
                "title": "Future Hack",
                "platform": "Devpost",
                "deadline": "2099-12-31",
                "status": "Active",
            }
        ]

        result = _archive_expired(pages)
        assert result == 0
        mock_notion.pages.update.assert_not_called()

    @patch("agents.workspace_agent.notion")
    def test_continues_on_api_failure(self, mock_notion):
        """Continues processing when archive API call fails for one page."""
        mock_notion.pages.update = MagicMock(
            side_effect=[Exception("API error"), None]
        )

        pages = [
            {
                "page_id": "page-1",
                "title": "Fail Hack",
                "platform": "Devpost",
                "deadline": "2020-01-01",
                "status": "Active",
            },
            {
                "page_id": "page-2",
                "title": "Success Hack",
                "platform": "Devpost",
                "deadline": "2020-06-01",
                "status": "Active",
            },
        ]

        result = _archive_expired(pages)
        # Only the second page was archived successfully
        assert result == 1
        assert mock_notion.pages.update.call_count == 2

    @patch("agents.workspace_agent.notion")
    def test_mixed_pages(self, mock_notion):
        """Correctly handles a mix of expired, future, None, and already-expired."""
        mock_notion.pages.update = MagicMock()

        pages = [
            {"page_id": "p1", "title": "A", "platform": "Devpost", "deadline": "2020-01-01", "status": "Active"},
            {"page_id": "p2", "title": "B", "platform": "Devpost", "deadline": None, "status": "Active"},
            {"page_id": "p3", "title": "C", "platform": "Devpost", "deadline": "2099-12-31", "status": "Active"},
            {"page_id": "p4", "title": "D", "platform": "Devpost", "deadline": "2021-06-01", "status": "Expired"},
        ]

        result = _archive_expired(pages)
        # Only p1 should be archived (expired deadline, not already "Expired")
        assert result == 1
        mock_notion.pages.update.assert_called_once_with(
            page_id="p1",
            properties={"Status": {"status": {"name": "Expired"}}},
        )


# --- Tests for _update_page (Task 6.3) ---

from agents.workspace_agent import _update_page


class TestUpdatePage:
    """Tests for _update_page Notion property mapping."""

    def _make_hackathon(self, **overrides) -> EnrichedHackathon:
        defaults = {
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
            "priority": "High",
            "difficulty": "Hard",
            "winning_probability": 35,
            "recommended_stack": ["Python", "React", "AWS"],
            "recommended_team_size": 4,
            "execution_strategy": "Focus on AI theme, build MVP in 48h.",
            "summary": "Top-tier hackathon.",
        }
        defaults.update(overrides)
        return EnrichedHackathon(**defaults)

    @patch("agents.workspace_agent.notion")
    def test_update_page_success(self, mock_notion):
        """Test successful page update returns True."""
        mock_notion.pages.update = MagicMock(return_value={"id": "page-123"})
        hackathon = self._make_hackathon()

        result = _update_page("page-123", hackathon)

        assert result is True
        mock_notion.pages.update.assert_called_once()

    @patch("agents.workspace_agent.notion")
    def test_update_page_uses_correct_page_id(self, mock_notion):
        """Test that update is called with the correct page_id."""
        mock_notion.pages.update = MagicMock(return_value={"id": "page-456"})
        hackathon = self._make_hackathon()

        _update_page("page-456", hackathon)

        call_kwargs = mock_notion.pages.update.call_args[1]
        assert call_kwargs["page_id"] == "page-456"

    @patch("agents.workspace_agent.notion")
    def test_update_page_does_not_include_serial(self, mock_notion):
        """S.No must NOT be included in update properties (preserve existing)."""
        mock_notion.pages.update = MagicMock(return_value={"id": "page-123"})
        hackathon = self._make_hackathon()

        _update_page("page-123", hackathon)

        props = mock_notion.pages.update.call_args[1]["properties"]
        assert "S.No" not in props

    @patch("agents.workspace_agent.notion")
    def test_update_page_maps_title(self, mock_notion):
        """Title is mapped to the Hackathon title property."""
        mock_notion.pages.update = MagicMock(return_value={"id": "page-123"})
        hackathon = self._make_hackathon()

        _update_page("page-123", hackathon)

        props = mock_notion.pages.update.call_args[1]["properties"]
        assert props["Hackathon"] == {
            "title": [{"text": {"content": "HackMIT 2025"}}]
        }

    @patch("agents.workspace_agent.notion")
    def test_update_page_maps_platform(self, mock_notion):
        """Platform is mapped to a select property."""
        mock_notion.pages.update = MagicMock(return_value={"id": "page-123"})
        hackathon = self._make_hackathon()

        _update_page("page-123", hackathon)

        props = mock_notion.pages.update.call_args[1]["properties"]
        assert props["Platform"] == {"select": {"name": "Devpost"}}

    @patch("agents.workspace_agent.notion")
    def test_update_page_maps_deadlines(self, mock_notion):
        """Deadlines with values map to date properties."""
        mock_notion.pages.update = MagicMock(return_value={"id": "page-123"})
        hackathon = self._make_hackathon()

        _update_page("page-123", hackathon)

        props = mock_notion.pages.update.call_args[1]["properties"]
        assert props["Deadline"] == {"date": {"start": "2025-09-01"}}
        assert props["Submission Deadline"] == {"date": {"start": "2025-09-15"}}

    @patch("agents.workspace_agent.notion")
    def test_update_page_null_deadlines(self, mock_notion):
        """None deadlines result in null date properties."""
        mock_notion.pages.update = MagicMock(return_value={"id": "page-123"})
        hackathon = self._make_hackathon(
            registration_deadline=None, submission_deadline=None
        )

        _update_page("page-123", hackathon)

        props = mock_notion.pages.update.call_args[1]["properties"]
        assert props["Deadline"] == {"date": None}
        assert props["Submission Deadline"] == {"date": None}

    @patch("agents.workspace_agent.notion")
    def test_update_page_null_optional_text_fields(self, mock_notion):
        """None prize/team_size result in empty rich_text arrays."""
        mock_notion.pages.update = MagicMock(return_value={"id": "page-123"})
        hackathon = self._make_hackathon(prize=None, team_size=None)

        _update_page("page-123", hackathon)

        props = mock_notion.pages.update.call_args[1]["properties"]
        assert props["Prize"] == {"rich_text": []}
        assert props["Team Size"] == {"rich_text": []}

    @patch("agents.workspace_agent.notion")
    def test_update_page_maps_intelligence_fields(self, mock_notion):
        """Intelligence fields (priority, difficulty, etc.) are correctly mapped."""
        mock_notion.pages.update = MagicMock(return_value={"id": "page-123"})
        hackathon = self._make_hackathon()

        _update_page("page-123", hackathon)

        props = mock_notion.pages.update.call_args[1]["properties"]
        assert props["Priority"] == {"select": {"name": "High"}}
        assert props["Difficulty"] == {"select": {"name": "Hard"}}
        assert props["Winning %"] == {"number": 35}
        assert props["Suggested Stack"] == {
            "multi_select": [
                {"name": "Python"},
                {"name": "React"},
                {"name": "AWS"},
            ]
        }

    @patch("agents.workspace_agent.notion")
    def test_update_page_maps_registration_link(self, mock_notion):
        """Registration URL is mapped to the URL property."""
        mock_notion.pages.update = MagicMock(return_value={"id": "page-123"})
        hackathon = self._make_hackathon()

        _update_page("page-123", hackathon)

        props = mock_notion.pages.update.call_args[1]["properties"]
        assert props["Registration Link"] == {
            "url": "https://devpost.com/hackmit-2025"
        }

    @patch("agents.workspace_agent.notion")
    def test_update_page_sets_last_synced_utc(self, mock_notion):
        """Last Synced is set to a UTC timestamp with +00:00 offset."""
        mock_notion.pages.update = MagicMock(return_value={"id": "page-123"})
        hackathon = self._make_hackathon()

        _update_page("page-123", hackathon)

        props = mock_notion.pages.update.call_args[1]["properties"]
        last_synced = props["Last Synced"]
        assert "date" in last_synced
        assert "start" in last_synced["date"]
        ts = last_synced["date"]["start"]
        assert "+00:00" in ts
        assert "T" in ts

    @patch("agents.workspace_agent.notion")
    def test_update_page_exception_returns_false(self, mock_notion):
        """API exceptions result in False return value."""
        mock_notion.pages.update = MagicMock(
            side_effect=Exception("Notion API error")
        )
        hackathon = self._make_hackathon()

        result = _update_page("page-123", hackathon)

        assert result is False

    @patch("agents.workspace_agent.notion")
    def test_update_page_maps_themes(self, mock_notion):
        """Themes are mapped as multi-select options."""
        mock_notion.pages.update = MagicMock(return_value={"id": "page-123"})
        hackathon = self._make_hackathon()

        _update_page("page-123", hackathon)

        props = mock_notion.pages.update.call_args[1]["properties"]
        assert props["Themes"] == {
            "multi_select": [{"name": "AI"}, {"name": "Web3"}]
        }

    @patch("agents.workspace_agent.notion")
    def test_update_page_empty_themes(self, mock_notion):
        """Empty themes list results in empty multi-select array."""
        mock_notion.pages.update = MagicMock(return_value={"id": "page-123"})
        hackathon = self._make_hackathon(themes=[])

        _update_page("page-123", hackathon)

        props = mock_notion.pages.update.call_args[1]["properties"]
        assert props["Themes"] == {"multi_select": []}

    @patch("agents.workspace_agent.notion")
    def test_update_page_empty_execution_strategy(self, mock_notion):
        """Empty execution_strategy results in empty rich_text array."""
        mock_notion.pages.update = MagicMock(return_value={"id": "page-123"})
        hackathon = self._make_hackathon(execution_strategy="")

        _update_page("page-123", hackathon)

        props = mock_notion.pages.update.call_args[1]["properties"]
        assert props["Execution Strategy"] == {"rich_text": []}


# --- Task 6.5: Rate limit handling with exponential backoff tests ---

from httpx import Headers
from notion_client.errors import APIResponseError as _APIResponseError
from agents.workspace_agent import _notion_request_with_retry


def _make_rate_limit_error():
    """Create an APIResponseError that simulates a 429 rate limit."""
    return _APIResponseError(
        code="rate_limited",
        status=429,
        message="Rate limited",
        headers=Headers(),
        raw_body_text="",
    )


def _make_api_error(code="validation_error", status=400):
    """Create a non-rate-limit APIResponseError."""
    return _APIResponseError(
        code=code,
        status=status,
        message="Bad request",
        headers=Headers(),
        raw_body_text="",
    )


class TestNotionRequestWithRetry:
    """Tests for _notion_request_with_retry — exponential backoff on 429."""

    def test_success_on_first_attempt(self):
        """Returns result when function succeeds immediately."""
        fn = MagicMock(return_value="success")
        result = _notion_request_with_retry(fn, "arg1", key="val")
        assert result == "success"
        fn.assert_called_once_with("arg1", key="val")

    @patch("agents.workspace_agent.time.sleep")
    def test_retries_on_rate_limited(self, mock_sleep):
        """Retries with backoff when APIResponseError with code='rate_limited'."""
        rate_limit_error = _make_rate_limit_error()

        fn = MagicMock(side_effect=[rate_limit_error, "success"])
        result = _notion_request_with_retry(fn)
        assert result == "success"
        assert fn.call_count == 2
        mock_sleep.assert_called_once_with(1)  # First backoff is 1s

    @patch("agents.workspace_agent.time.sleep")
    def test_exponential_backoff_delays(self, mock_sleep):
        """Backoff delays are 1s, 2s, 4s for retries 1, 2, 3."""
        errors = [_make_rate_limit_error() for _ in range(3)]

        fn = MagicMock(side_effect=[*errors, "success"])
        result = _notion_request_with_retry(fn)
        assert result == "success"
        assert fn.call_count == 4
        assert mock_sleep.call_args_list == [
            ((1,),),
            ((2,),),
            ((4,),),
        ]

    @patch("agents.workspace_agent.time.sleep")
    def test_raises_after_max_retries_exhausted(self, mock_sleep):
        """Raises APIResponseError after 3 retries (4 total attempts)."""
        rate_limit_error = _make_rate_limit_error()

        fn = MagicMock(side_effect=rate_limit_error)

        with pytest.raises(_APIResponseError):
            _notion_request_with_retry(fn)

        assert fn.call_count == 4  # 1 initial + 3 retries
        assert mock_sleep.call_count == 3

    def test_non_rate_limit_error_raises_immediately(self):
        """Non-rate-limit APIResponseError is raised without retry."""
        api_error = _make_api_error()

        fn = MagicMock(side_effect=api_error)

        with pytest.raises(_APIResponseError):
            _notion_request_with_retry(fn)

        assert fn.call_count == 1  # No retries

    def test_non_api_error_raises_immediately(self):
        """Non-APIResponseError exceptions are raised immediately (no retry)."""
        fn = MagicMock(side_effect=ValueError("something went wrong"))

        with pytest.raises(ValueError):
            _notion_request_with_retry(fn)

        assert fn.call_count == 1

    @patch("agents.workspace_agent.time.sleep")
    def test_create_page_uses_retry(self, mock_sleep):
        """_create_page retries on rate limit via the retry wrapper."""
        rate_limit_error = _make_rate_limit_error()

        with patch("agents.workspace_agent.notion") as mock_notion:
            mock_notion.pages.create = MagicMock(
                side_effect=[rate_limit_error, {"id": "new-page"}]
            )
            hackathon = EnrichedHackathon(
                title="Test",
                platform="Devpost",
                registration_url="https://devpost.com/test",
                registration_deadline=None,
                submission_deadline=None,
                organizer=None,
                themes=[],
                mode=None,
                location=None,
                prize=None,
                team_size=None,
                priority="Medium",
                difficulty="Medium",
                winning_probability=50,
                recommended_stack=["Python"],
                recommended_team_size=3,
                execution_strategy="Build fast",
                summary="Test hack",
            )
            result = _create_page(hackathon, serial=1)
            assert result is True
            assert mock_notion.pages.create.call_count == 2
            mock_sleep.assert_called_once_with(1)

    @patch("agents.workspace_agent.time.sleep")
    def test_update_page_uses_retry(self, mock_sleep):
        """_update_page retries on rate limit via the retry wrapper."""
        rate_limit_error = _make_rate_limit_error()

        with patch("agents.workspace_agent.notion") as mock_notion:
            mock_notion.pages.update = MagicMock(
                side_effect=[rate_limit_error, {"id": "page-123"}]
            )
            hackathon = EnrichedHackathon(
                title="Test",
                platform="Devpost",
                registration_url="https://devpost.com/test",
                registration_deadline=None,
                submission_deadline=None,
                organizer=None,
                themes=[],
                mode=None,
                location=None,
                prize=None,
                team_size=None,
                priority="Medium",
                difficulty="Medium",
                winning_probability=50,
                recommended_stack=["Python"],
                recommended_team_size=3,
                execution_strategy="Build fast",
                summary="Test hack",
            )
            result = _update_page("page-123", hackathon)
            assert result is True
            assert mock_notion.pages.update.call_count == 2
            mock_sleep.assert_called_once_with(1)


# --- Task 6.6: Sync result counting invariant tests ---

from agents.workspace_agent import sync_to_notion


class TestSyncResultInvariant:
    """Tests verifying new + updated + failed == processed invariant."""

    def _make_hackathon(self, title="Test Hack", platform="Devpost") -> EnrichedHackathon:
        return EnrichedHackathon(
            title=title,
            platform=platform,
            registration_url=f"https://devpost.com/{title.lower().replace(' ', '-')}",
            registration_deadline="2099-12-31",
            submission_deadline="2099-12-31",
            organizer="TestOrg",
            themes=["AI"],
            mode="online",
            location=None,
            prize="$1000",
            team_size="2-4",
            priority="Medium",
            difficulty="Medium",
            winning_probability=50,
            recommended_stack=["Python"],
            recommended_team_size=3,
            execution_strategy="Build fast",
            summary="A hackathon",
        )

    @patch("agents.workspace_agent._archive_expired", return_value=0)
    @patch("agents.workspace_agent._get_all_pages", return_value=[])
    @patch("agents.workspace_agent.notion")
    def test_invariant_all_new(self, mock_notion, mock_get_pages, mock_archive):
        """When all hackathons are new, new == processed and invariant holds."""
        mock_notion.pages.create = MagicMock(return_value={"id": "new-page"})

        hackathons = [self._make_hackathon(f"Hack {i}") for i in range(5)]
        result = sync_to_notion(hackathons)

        assert result.processed == 5
        assert result.new + result.updated + result.failed == result.processed
        assert result.new == 5
        assert result.updated == 0
        assert result.failed == 0

    @patch("agents.workspace_agent._archive_expired", return_value=2)
    @patch("agents.workspace_agent._get_all_pages")
    @patch("agents.workspace_agent.notion")
    def test_invariant_all_updated(self, mock_notion, mock_get_pages, mock_archive):
        """When all hackathons exist, updated == processed and invariant holds."""
        mock_notion.pages.update = MagicMock(return_value={"id": "page-id"})
        mock_get_pages.return_value = [
            {"page_id": f"page-{i}", "title": f"Hack {i}", "platform": "Devpost", "deadline": "2099-12-31", "status": "Active", "serial": i + 1}
            for i in range(3)
        ]

        hackathons = [self._make_hackathon(f"Hack {i}") for i in range(3)]
        result = sync_to_notion(hackathons)

        assert result.processed == 3
        assert result.new + result.updated + result.failed == result.processed
        assert result.updated == 3
        assert result.new == 0
        assert result.failed == 0
        # Archived is tracked separately
        assert result.archived == 2

    @patch("agents.workspace_agent._archive_expired", return_value=0)
    @patch("agents.workspace_agent._get_all_pages", return_value=[])
    @patch("agents.workspace_agent.notion")
    def test_invariant_with_failures(self, mock_notion, mock_get_pages, mock_archive):
        """When some creates fail, new + failed == processed and invariant holds."""
        mock_notion.pages.create = MagicMock(
            side_effect=[{"id": "p1"}, Exception("fail"), {"id": "p3"}, Exception("fail")]
        )

        hackathons = [self._make_hackathon(f"Hack {i}") for i in range(4)]
        result = sync_to_notion(hackathons)

        assert result.processed == 4
        assert result.new + result.updated + result.failed == result.processed

    @patch("agents.workspace_agent._archive_expired", return_value=1)
    @patch("agents.workspace_agent._get_all_pages")
    @patch("agents.workspace_agent.notion")
    def test_invariant_mixed_new_update_fail(self, mock_notion, mock_get_pages, mock_archive):
        """Mixed scenario: some new, some updated, some failed — invariant holds."""
        # Two existing pages
        mock_get_pages.return_value = [
            {"page_id": "page-0", "title": "Hack 0", "platform": "Devpost", "deadline": "2099-12-31", "status": "Active", "serial": 1},
            {"page_id": "page-1", "title": "Hack 1", "platform": "Devpost", "deadline": "2099-12-31", "status": "Active", "serial": 2},
        ]
        # update succeeds for first, fails for second; create succeeds for third
        mock_notion.pages.update = MagicMock(
            side_effect=[{"id": "page-0"}, Exception("update fail")]
        )
        mock_notion.pages.create = MagicMock(return_value={"id": "new-page"})

        hackathons = [
            self._make_hackathon("Hack 0"),  # exists -> update (success)
            self._make_hackathon("Hack 1"),  # exists -> update (fail)
            self._make_hackathon("Hack 2"),  # new -> create (success)
        ]
        result = sync_to_notion(hackathons)

        assert result.processed == 3
        assert result.new + result.updated + result.failed == result.processed
        assert result.new == 1
        assert result.updated == 1
        assert result.failed == 1
        # Archived tracked separately
        assert result.archived == 1

    @patch("agents.workspace_agent._archive_expired", return_value=0)
    @patch("agents.workspace_agent._get_all_pages", return_value=[])
    @patch("agents.workspace_agent.notion")
    def test_invariant_empty_input(self, mock_notion, mock_get_pages, mock_archive):
        """Empty input yields processed=0 and invariant holds trivially."""
        result = sync_to_notion([])

        assert result.processed == 0
        assert result.new + result.updated + result.failed == result.processed
        assert result.new == 0
        assert result.updated == 0
        assert result.failed == 0
