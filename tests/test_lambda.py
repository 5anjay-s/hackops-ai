"""Unit tests for Lambda Orchestrator (lambda_function.py).

Tests the lambda_handler function covering:
- Successful pipeline flow with mocked agents
- Empty discovery result short-circuit
- Exception handling returns 500
- Missing environment variables return 500
- Pipeline count invariant (new + updated + failed == processed)

Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 13.5
"""

import os
import sys
from unittest.mock import patch, MagicMock

import pytest

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.hackathon import Hackathon, EnrichedHackathon, SyncResult


class TestLambdaHandlerSuccess:
    """Test successful pipeline flow with mocked agents."""

    def setup_method(self):
        """Set required env vars before each test."""
        os.environ["NOTION_TOKEN"] = "test-notion-token"
        os.environ["DATABASE_ID"] = "test-database-id"

    def teardown_method(self):
        """Clean up env vars."""
        os.environ.pop("NOTION_TOKEN", None)
        os.environ.pop("DATABASE_ID", None)

    @patch("lambda_function.sync_to_notion")
    @patch("lambda_function.analyze_batch")
    @patch("lambda_function.discover_all")
    def test_successful_flow_returns_200_with_counts(
        self, mock_discover, mock_analyze, mock_sync
    ):
        """Full pipeline: discover → analyze → sync. Verify 200 with correct counts."""
        # Arrange
        hackathons = [
            Hackathon(
                title="HackMIT 2025",
                platform="Devpost",
                registration_url="https://devpost.com/hackmit",
                registration_deadline="2025-09-01",
                submission_deadline="2025-09-15",
                organizer="MIT",
                themes=["AI"],
                mode="online",
                location=None,
                prize="$10,000",
                team_size="2-5",
            ),
            Hackathon(
                title="BuildathonX",
                platform="Unstop",
                registration_url="https://unstop.com/buildathonx",
                registration_deadline="2025-10-01",
                submission_deadline=None,
                organizer="Unstop",
                themes=["Web3"],
                mode="hybrid",
                location="Delhi",
                prize="$5,000",
                team_size="3-4",
            ),
        ]
        enriched = [
            EnrichedHackathon(
                title="HackMIT 2025",
                platform="Devpost",
                registration_url="https://devpost.com/hackmit",
                registration_deadline="2025-09-01",
                submission_deadline="2025-09-15",
                organizer="MIT",
                themes=["AI"],
                mode="online",
                location=None,
                prize="$10,000",
                team_size="2-5",
                priority="High",
                difficulty="Hard",
                winning_probability=35,
                recommended_stack=["Python", "React"],
                recommended_team_size=4,
                execution_strategy="Build MVP fast",
                summary="Top hackathon",
            ),
            EnrichedHackathon(
                title="BuildathonX",
                platform="Unstop",
                registration_url="https://unstop.com/buildathonx",
                registration_deadline="2025-10-01",
                submission_deadline=None,
                organizer="Unstop",
                themes=["Web3"],
                mode="hybrid",
                location="Delhi",
                prize="$5,000",
                team_size="3-4",
                priority="Medium",
                difficulty="Medium",
                winning_probability=50,
                recommended_stack=["Python"],
                recommended_team_size=3,
                execution_strategy="Focus on theme",
                summary="Good hackathon",
            ),
        ]
        sync_result = SyncResult(processed=2, new=1, updated=1, archived=0, failed=0)

        mock_discover.return_value = hackathons
        mock_analyze.return_value = enriched
        mock_sync.return_value = sync_result

        # Act
        from lambda_function import lambda_handler

        response = lambda_handler({}, None)

        # Assert
        assert response["statusCode"] == 200
        assert response["body"]["processed"] == 2
        assert response["body"]["new"] == 1
        assert response["body"]["updated"] == 1
        assert response["body"]["failed"] == 0

        # Verify pipeline sequence
        mock_discover.assert_called_once()
        mock_analyze.assert_called_once_with(hackathons)
        mock_sync.assert_called_once_with(enriched)


class TestLambdaHandlerEmptyDiscovery:
    """Test empty discovery result short-circuit."""

    def setup_method(self):
        os.environ["NOTION_TOKEN"] = "test-notion-token"
        os.environ["DATABASE_ID"] = "test-database-id"

    def teardown_method(self):
        os.environ.pop("NOTION_TOKEN", None)
        os.environ.pop("DATABASE_ID", None)

    @patch("lambda_function.sync_to_notion")
    @patch("lambda_function.analyze_batch")
    @patch("lambda_function.discover_all")
    def test_empty_discovery_returns_200_with_zeros(
        self, mock_discover, mock_analyze, mock_sync
    ):
        """When discover_all returns [], skip analyze and sync, return all zeros."""
        mock_discover.return_value = []

        from lambda_function import lambda_handler

        response = lambda_handler({}, None)

        # Assert 200 with all zeros
        assert response["statusCode"] == 200
        assert response["body"]["processed"] == 0
        assert response["body"]["new"] == 0
        assert response["body"]["updated"] == 0
        assert response["body"]["failed"] == 0

        # Verify analyze_batch and sync_to_notion were NOT called
        mock_analyze.assert_not_called()
        mock_sync.assert_not_called()


class TestLambdaHandlerExceptions:
    """Test exception handling returns 500."""

    def setup_method(self):
        os.environ["NOTION_TOKEN"] = "test-notion-token"
        os.environ["DATABASE_ID"] = "test-database-id"

    def teardown_method(self):
        os.environ.pop("NOTION_TOKEN", None)
        os.environ.pop("DATABASE_ID", None)

    @patch("lambda_function.discover_all")
    def test_discover_all_exception_returns_500(self, mock_discover):
        """When discover_all raises, lambda returns 500 with error message."""
        mock_discover.side_effect = Exception("Network timeout on Devpost")

        from lambda_function import lambda_handler

        response = lambda_handler({}, None)

        assert response["statusCode"] == 500
        assert "error" in response["body"]
        assert "Network timeout on Devpost" in response["body"]["error"]

    @patch("lambda_function.analyze_batch")
    @patch("lambda_function.discover_all")
    def test_analyze_batch_exception_returns_500(self, mock_discover, mock_analyze):
        """When analyze_batch raises, lambda returns 500."""
        mock_discover.return_value = [
            Hackathon(
                title="Test",
                platform="Devpost",
                registration_url="https://devpost.com/test",
            )
        ]
        mock_analyze.side_effect = Exception("Bedrock connection failed")

        from lambda_function import lambda_handler

        response = lambda_handler({}, None)

        assert response["statusCode"] == 500
        assert "Bedrock connection failed" in response["body"]["error"]

    @patch("lambda_function.sync_to_notion")
    @patch("lambda_function.analyze_batch")
    @patch("lambda_function.discover_all")
    def test_sync_to_notion_exception_returns_500(
        self, mock_discover, mock_analyze, mock_sync
    ):
        """When sync_to_notion raises, lambda returns 500."""
        mock_discover.return_value = [
            Hackathon(
                title="Test",
                platform="Devpost",
                registration_url="https://devpost.com/test",
            )
        ]
        mock_analyze.return_value = [
            EnrichedHackathon(
                title="Test",
                platform="Devpost",
                registration_url="https://devpost.com/test",
                priority="Medium",
                difficulty="Medium",
                winning_probability=50,
                recommended_stack=["Python"],
                recommended_team_size=3,
                execution_strategy="Build fast",
                summary="Test",
            )
        ]
        mock_sync.side_effect = Exception("Notion API unreachable")

        from lambda_function import lambda_handler

        response = lambda_handler({}, None)

        assert response["statusCode"] == 500
        assert "Notion API unreachable" in response["body"]["error"]


class TestLambdaHandlerMissingEnvVars:
    """Test missing environment variables return 500."""

    def teardown_method(self):
        """Ensure env vars are cleaned up."""
        os.environ.pop("NOTION_TOKEN", None)
        os.environ.pop("DATABASE_ID", None)

    def test_missing_notion_token_returns_500(self):
        """When NOTION_TOKEN is not set, lambda returns 500."""
        os.environ.pop("NOTION_TOKEN", None)
        os.environ["DATABASE_ID"] = "test-database-id"

        from lambda_function import lambda_handler

        response = lambda_handler({}, None)

        assert response["statusCode"] == 500
        assert "error" in response["body"]
        assert "NOTION_TOKEN" in response["body"]["error"]

    def test_missing_database_id_returns_500(self):
        """When DATABASE_ID is not set, lambda returns 500."""
        os.environ["NOTION_TOKEN"] = "test-notion-token"
        os.environ.pop("DATABASE_ID", None)

        from lambda_function import lambda_handler

        response = lambda_handler({}, None)

        assert response["statusCode"] == 500
        assert "error" in response["body"]
        assert "DATABASE_ID" in response["body"]["error"]

    def test_both_env_vars_missing_returns_500(self):
        """When both env vars missing, lambda returns 500 mentioning both."""
        os.environ.pop("NOTION_TOKEN", None)
        os.environ.pop("DATABASE_ID", None)

        from lambda_function import lambda_handler

        response = lambda_handler({}, None)

        assert response["statusCode"] == 500
        assert "error" in response["body"]
        assert "NOTION_TOKEN" in response["body"]["error"]
        assert "DATABASE_ID" in response["body"]["error"]

    def test_empty_notion_token_returns_500(self):
        """When NOTION_TOKEN is empty string, lambda returns 500."""
        os.environ["NOTION_TOKEN"] = ""
        os.environ["DATABASE_ID"] = "test-database-id"

        from lambda_function import lambda_handler

        response = lambda_handler({}, None)

        assert response["statusCode"] == 500
        assert "NOTION_TOKEN" in response["body"]["error"]

    def test_whitespace_only_database_id_returns_500(self):
        """When DATABASE_ID is whitespace only, lambda returns 500."""
        os.environ["NOTION_TOKEN"] = "test-notion-token"
        os.environ["DATABASE_ID"] = "   "

        from lambda_function import lambda_handler

        response = lambda_handler({}, None)

        assert response["statusCode"] == 500
        assert "DATABASE_ID" in response["body"]["error"]


class TestLambdaHandlerCountInvariant:
    """Test invariant: new + updated + failed == processed."""

    def setup_method(self):
        os.environ["NOTION_TOKEN"] = "test-notion-token"
        os.environ["DATABASE_ID"] = "test-database-id"

    def teardown_method(self):
        os.environ.pop("NOTION_TOKEN", None)
        os.environ.pop("DATABASE_ID", None)

    @patch("lambda_function.sync_to_notion")
    @patch("lambda_function.analyze_batch")
    @patch("lambda_function.discover_all")
    def test_count_invariant_holds(self, mock_discover, mock_analyze, mock_sync):
        """Verify new + updated + failed == processed in response body."""
        hackathons = [
            Hackathon(
                title=f"Hack {i}",
                platform="Devpost",
                registration_url=f"https://devpost.com/hack-{i}",
            )
            for i in range(5)
        ]
        enriched = [
            EnrichedHackathon(
                title=f"Hack {i}",
                platform="Devpost",
                registration_url=f"https://devpost.com/hack-{i}",
                priority="Medium",
                difficulty="Medium",
                winning_probability=50,
                recommended_stack=["Python"],
                recommended_team_size=3,
                execution_strategy="Plan and execute",
                summary="A hackathon",
            )
            for i in range(5)
        ]
        # 5 processed: 2 new + 2 updated + 1 failed = 5
        sync_result = SyncResult(processed=5, new=2, updated=2, archived=1, failed=1)

        mock_discover.return_value = hackathons
        mock_analyze.return_value = enriched
        mock_sync.return_value = sync_result

        from lambda_function import lambda_handler

        response = lambda_handler({}, None)

        assert response["statusCode"] == 200
        body = response["body"]
        assert body["new"] + body["updated"] + body["failed"] == body["processed"]

    @patch("lambda_function.sync_to_notion")
    @patch("lambda_function.analyze_batch")
    @patch("lambda_function.discover_all")
    def test_count_invariant_all_new(self, mock_discover, mock_analyze, mock_sync):
        """Invariant holds when all hackathons are new."""
        hackathons = [
            Hackathon(
                title="New Hack",
                platform="Devfolio",
                registration_url="https://devfolio.co/new",
            )
        ]
        enriched = [
            EnrichedHackathon(
                title="New Hack",
                platform="Devfolio",
                registration_url="https://devfolio.co/new",
                priority="Low",
                difficulty="Easy",
                winning_probability=70,
                recommended_stack=["JavaScript"],
                recommended_team_size=2,
                execution_strategy="Quick prototype",
                summary="Easy win",
            )
        ]
        sync_result = SyncResult(processed=1, new=1, updated=0, archived=0, failed=0)

        mock_discover.return_value = hackathons
        mock_analyze.return_value = enriched
        mock_sync.return_value = sync_result

        from lambda_function import lambda_handler

        response = lambda_handler({}, None)

        body = response["body"]
        assert body["new"] + body["updated"] + body["failed"] == body["processed"]

    @patch("lambda_function.sync_to_notion")
    @patch("lambda_function.analyze_batch")
    @patch("lambda_function.discover_all")
    def test_count_invariant_all_failed(self, mock_discover, mock_analyze, mock_sync):
        """Invariant holds when all operations fail."""
        hackathons = [
            Hackathon(
                title=f"Hack {i}",
                platform="Unstop",
                registration_url=f"https://unstop.com/hack-{i}",
            )
            for i in range(3)
        ]
        enriched = [
            EnrichedHackathon(
                title=f"Hack {i}",
                platform="Unstop",
                registration_url=f"https://unstop.com/hack-{i}",
                priority="Medium",
                difficulty="Medium",
                winning_probability=50,
                recommended_stack=["Python"],
                recommended_team_size=3,
                execution_strategy="Try hard",
                summary="Tough",
            )
            for i in range(3)
        ]
        sync_result = SyncResult(processed=3, new=0, updated=0, archived=0, failed=3)

        mock_discover.return_value = hackathons
        mock_analyze.return_value = enriched
        mock_sync.return_value = sync_result

        from lambda_function import lambda_handler

        response = lambda_handler({}, None)

        body = response["body"]
        assert body["new"] + body["updated"] + body["failed"] == body["processed"]
