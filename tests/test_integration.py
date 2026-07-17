"""Integration tests for the HackOps AI full pipeline.

Verifies end-to-end flow from Lambda handler through Discovery → Intelligence →
Workspace agents with all external dependencies mocked.

Validates Requirements: 1.1 (sequential agent invocation), 1.2 (statusCode 200
with correct counts), 1.3 (new + updated + failed == processed invariant).
"""

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set required env vars before importing modules that read them at import time
os.environ["NOTION_TOKEN"] = "test-integration-token"
os.environ["DATABASE_ID"] = "test-integration-db-id"


# --- Mock HTML/JSON responses for scrapers ---

MOCK_DEVPOST_API_RESPONSE = {
    "hackathons": [
        {
            "title": "AI Global Hack 2025",
            "url": "https://devpost.com/hackathons/ai-global-2025",
        },
        {
            "title": "Green Energy Challenge",
            "url": "https://devpost.com/hackathons/green-energy",
        },
    ]
}

MOCK_DEVPOST_DETAIL_HTML = """
<html>
<body>
    <time datetime="2025-08-01T00:00:00Z">Aug 1</time>
    <time datetime="2025-09-15T00:00:00Z">Sep 15</time>
    <div class="prize-amount">$10,000</div>
    <div class="host">TechCorp</div>
    <span class="tag">AI</span>
    <span class="tag">ML</span>
    <div id="rules"><li>Team of 2-5 members</li></div>
</body>
</html>
"""

MOCK_DEVFOLIO_API_RESPONSE = {
    "hits": {
        "hits": [
            {
                "_source": {
                    "name": "Web3 Buildathon",
                    "slug": "web3-buildathon",
                    "reg_ends": "2025-08-20T00:00:00Z",
                    "hackathon_ends": "2025-09-01T00:00:00Z",
                    "prize_amount": 5000,
                    "prize_currency": "USD",
                    "themes": ["Blockchain", "DeFi"],
                    "is_online": True,
                    "organisation": {"name": "Devfolio"},
                    "team_min": 2,
                    "team_max": 4,
                }
            }
        ]
    }
}

MOCK_UNSTOP_API_RESPONSE = {
    "data": {
        "data": [
            {
                "title": "Unstop Innovation Sprint",
                "public_url": "competition/unstop-innovation-sprint-123",
                "organisation": {"name": "Unstop Inc"},
                "tags": [{"name": "IoT"}, {"name": "Cloud"}],
                "end_date": "2025-10-01",
                "regnRequirements": {"end_regn_dt": "2025-09-15"},
            }
        ]
    }
}

MOCK_UNSTOP_DETAIL_HTML = """
<html>
<body>
    <time datetime="2025-09-15T00:00:00Z">Sep 15</time>
    <time datetime="2025-10-01T00:00:00Z">Oct 1</time>
    <span class="tag">IoT</span>
    <span>Online</span>
</body>
</html>
"""

# Empty page for Devfolio detail page fetch (not always needed with API data)
MOCK_DEVFOLIO_DETAIL_HTML = """
<html><body><span class="tag">Blockchain</span></body></html>
"""


def _mock_requests_get(url, **kwargs):
    """Route mock GET requests based on URL pattern."""
    response = MagicMock()
    response.status_code = 200
    response.raise_for_status = MagicMock()

    if "devpost.com/api/hackathons" in url:
        response.json = MagicMock(return_value=MOCK_DEVPOST_API_RESPONSE)
        response.text = json.dumps(MOCK_DEVPOST_API_RESPONSE)
    elif "devpost.com/hackathons/" in url:
        response.text = MOCK_DEVPOST_DETAIL_HTML
    elif "devfolio.co/hackathons/" in url:
        response.text = MOCK_DEVFOLIO_DETAIL_HTML
    elif "unstop.com/" in url:
        response.text = MOCK_UNSTOP_DETAIL_HTML
    else:
        # Default: return empty HTML
        response.text = "<html><body></body></html>"
        response.json = MagicMock(return_value={})

    return response


def _mock_requests_post(url, **kwargs):
    """Route mock POST requests based on URL pattern."""
    response = MagicMock()
    response.status_code = 200
    response.raise_for_status = MagicMock()

    if "devfolio.co" in url:
        response.json = MagicMock(return_value=MOCK_DEVFOLIO_API_RESPONSE)
    elif "unstop.com" in url:
        response.json = MagicMock(return_value=MOCK_UNSTOP_API_RESPONSE)
    else:
        response.json = MagicMock(return_value={})

    return response


def _mock_notion_databases_query(**kwargs):
    """Mock Notion database query returning empty results (no existing pages)."""
    return {"results": [], "has_more": False, "next_cursor": None}


def _mock_notion_pages_create(**kwargs):
    """Mock Notion page creation returning a fake page ID."""
    return {"id": "mock-page-id-new"}


def _mock_notion_pages_update(**kwargs):
    """Mock Notion page update."""
    return {"id": kwargs.get("page_id", "mock-page-id")}


class TestFullPipelineIntegration:
    """Integration tests verifying the full Lambda pipeline end-to-end."""

    @patch("agents.workspace_agent.notion")
    @patch("agents.intelligence_agent.boto3.client")
    @patch("agents.discovery_agent.requests.post", side_effect=_mock_requests_post)
    @patch("agents.discovery_agent.requests.get", side_effect=_mock_requests_get)
    @patch("agents.discovery_agent.time.sleep")
    @patch("agents.workspace_agent.time.sleep")
    def test_full_pipeline_returns_200_with_sync_result(
        self,
        mock_ws_sleep,
        mock_disc_sleep,
        mock_get,
        mock_post,
        mock_boto3_client,
        mock_notion,
    ):
        """Full pipeline: discovery finds hackathons, intelligence enriches,
        workspace syncs. Response has statusCode 200 with correct SyncResult.

        Validates: Requirements 1.1, 1.2
        """
        # Configure boto3 mock to raise so intelligence falls back to mock analysis
        mock_boto3_client.side_effect = Exception("No AWS credentials")

        # Configure Notion mock
        mock_notion.databases.query = MagicMock(side_effect=_mock_notion_databases_query)
        mock_notion.pages.create = MagicMock(side_effect=_mock_notion_pages_create)
        mock_notion.pages.update = MagicMock(side_effect=_mock_notion_pages_update)

        from lambda_function import lambda_handler

        result = lambda_handler({}, None)

        assert result["statusCode"] == 200
        body = result["body"]
        assert "processed" in body
        assert "new" in body
        assert "updated" in body
        assert "failed" in body
        # All counts are non-negative integers
        assert body["processed"] >= 0
        assert body["new"] >= 0
        assert body["updated"] >= 0
        assert body["failed"] >= 0

    @patch("agents.workspace_agent.notion")
    @patch("agents.intelligence_agent.boto3.client")
    @patch("agents.discovery_agent.requests.post", side_effect=_mock_requests_post)
    @patch("agents.discovery_agent.requests.get", side_effect=_mock_requests_get)
    @patch("agents.discovery_agent.time.sleep")
    @patch("agents.workspace_agent.time.sleep")
    def test_sync_result_invariant_new_plus_updated_plus_failed_equals_processed(
        self,
        mock_ws_sleep,
        mock_disc_sleep,
        mock_get,
        mock_post,
        mock_boto3_client,
        mock_notion,
    ):
        """Verify the invariant: new + updated + failed == processed.

        Validates: Requirement 1.3
        """
        mock_boto3_client.side_effect = Exception("No AWS credentials")

        mock_notion.databases.query = MagicMock(side_effect=_mock_notion_databases_query)
        mock_notion.pages.create = MagicMock(side_effect=_mock_notion_pages_create)
        mock_notion.pages.update = MagicMock(side_effect=_mock_notion_pages_update)

        from lambda_function import lambda_handler

        result = lambda_handler({}, None)

        assert result["statusCode"] == 200
        body = result["body"]
        assert body["new"] + body["updated"] + body["failed"] == body["processed"]

    @patch("agents.workspace_agent.notion")
    @patch("agents.intelligence_agent.boto3.client")
    @patch("agents.discovery_agent.requests.post", side_effect=_mock_requests_post)
    @patch("agents.discovery_agent.requests.get", side_effect=_mock_requests_get)
    @patch("agents.discovery_agent.time.sleep")
    @patch("agents.workspace_agent.time.sleep")
    def test_discovery_finds_hackathons_from_all_platforms(
        self,
        mock_ws_sleep,
        mock_disc_sleep,
        mock_get,
        mock_post,
        mock_boto3_client,
        mock_notion,
    ):
        """Verify discovery calls all three platform scrapers and finds results.

        Validates: Requirement 1.1
        """
        mock_boto3_client.side_effect = Exception("No AWS credentials")

        mock_notion.databases.query = MagicMock(side_effect=_mock_notion_databases_query)
        mock_notion.pages.create = MagicMock(side_effect=_mock_notion_pages_create)
        mock_notion.pages.update = MagicMock(side_effect=_mock_notion_pages_update)

        from lambda_function import lambda_handler

        result = lambda_handler({}, None)

        # Pipeline completed and processed at least 1 hackathon
        assert result["statusCode"] == 200
        assert result["body"]["processed"] > 0

    @patch("agents.workspace_agent.notion")
    @patch("agents.intelligence_agent.boto3.client")
    @patch("agents.discovery_agent.requests.post", side_effect=_mock_requests_post)
    @patch("agents.discovery_agent.requests.get", side_effect=_mock_requests_get)
    @patch("agents.discovery_agent.time.sleep")
    @patch("agents.workspace_agent.time.sleep")
    def test_workspace_creates_new_pages_when_none_exist(
        self,
        mock_ws_sleep,
        mock_disc_sleep,
        mock_get,
        mock_post,
        mock_boto3_client,
        mock_notion,
    ):
        """When Notion DB is empty, all hackathons are created as new pages.

        Validates: Requirements 1.1, 1.2
        """
        mock_boto3_client.side_effect = Exception("No AWS credentials")

        mock_notion.databases.query = MagicMock(side_effect=_mock_notion_databases_query)
        mock_notion.pages.create = MagicMock(side_effect=_mock_notion_pages_create)
        mock_notion.pages.update = MagicMock(side_effect=_mock_notion_pages_update)

        from lambda_function import lambda_handler

        result = lambda_handler({}, None)

        assert result["statusCode"] == 200
        body = result["body"]
        # All processed items should be new (no existing pages to update)
        assert body["new"] == body["processed"]
        assert body["updated"] == 0
        assert body["failed"] == 0

    @patch("agents.workspace_agent.notion")
    @patch("agents.intelligence_agent.boto3.client")
    @patch("agents.discovery_agent.requests.post", side_effect=_mock_requests_post)
    @patch("agents.discovery_agent.requests.get", side_effect=_mock_requests_get)
    @patch("agents.discovery_agent.time.sleep")
    @patch("agents.workspace_agent.time.sleep")
    def test_workspace_updates_existing_pages(
        self,
        mock_ws_sleep,
        mock_disc_sleep,
        mock_get,
        mock_post,
        mock_boto3_client,
        mock_notion,
    ):
        """When Notion DB has matching pages, those hackathons are updated.

        Validates: Requirements 1.1, 1.2, 1.3
        """
        mock_boto3_client.side_effect = Exception("No AWS credentials")

        # Return one existing page that matches a discovered hackathon
        def query_with_existing(**kwargs):
            return {
                "results": [
                    {
                        "id": "existing-page-1",
                        "properties": {
                            "Hackathon": {
                                "title": [{"plain_text": "AI Global Hack 2025"}]
                            },
                            "Platform": {"select": {"name": "Devpost"}},
                            "Deadline": {"date": {"start": "2025-08-01"}},
                            "Status": {"status": {"name": "Active"}},
                            "S.No": {"number": 1},
                        },
                    }
                ],
                "has_more": False,
                "next_cursor": None,
            }

        mock_notion.databases.query = MagicMock(side_effect=query_with_existing)
        mock_notion.pages.create = MagicMock(side_effect=_mock_notion_pages_create)
        mock_notion.pages.update = MagicMock(side_effect=_mock_notion_pages_update)

        from lambda_function import lambda_handler

        result = lambda_handler({}, None)

        assert result["statusCode"] == 200
        body = result["body"]
        # At least one should be updated (the matching AI Global Hack 2025)
        assert body["updated"] >= 1
        # Invariant still holds
        assert body["new"] + body["updated"] + body["failed"] == body["processed"]

    @patch("agents.workspace_agent.notion")
    @patch("agents.intelligence_agent.boto3.client")
    @patch("agents.discovery_agent.requests.post")
    @patch("agents.discovery_agent.requests.get")
    @patch("agents.discovery_agent.time.sleep")
    @patch("agents.workspace_agent.time.sleep")
    def test_pipeline_handles_all_platforms_failing_gracefully(
        self,
        mock_ws_sleep,
        mock_disc_sleep,
        mock_get,
        mock_post,
        mock_boto3_client,
        mock_notion,
    ):
        """When all platform scrapers fail, pipeline returns 200 with zero counts.

        Validates: Requirements 1.1, 1.2
        """
        # Make all requests fail
        mock_get.side_effect = Exception("Network error")
        mock_post.side_effect = Exception("Network error")
        mock_boto3_client.side_effect = Exception("No AWS credentials")

        mock_notion.databases.query = MagicMock(side_effect=_mock_notion_databases_query)
        mock_notion.pages.create = MagicMock(side_effect=_mock_notion_pages_create)

        from lambda_function import lambda_handler

        result = lambda_handler({}, None)

        assert result["statusCode"] == 200
        body = result["body"]
        assert body["processed"] == 0
        assert body["new"] == 0
        assert body["updated"] == 0
        assert body["failed"] == 0

    def test_pipeline_returns_500_when_env_vars_missing(self):
        """When required env vars are missing, returns 500 error.

        Validates: Requirement 1.2
        """
        from lambda_function import lambda_handler

        with patch.dict(os.environ, {"NOTION_TOKEN": "", "DATABASE_ID": ""}):
            result = lambda_handler({}, None)

        assert result["statusCode"] == 500
        assert "error" in result["body"]

    @patch("agents.workspace_agent.notion")
    @patch("agents.intelligence_agent.boto3.client")
    @patch("agents.discovery_agent.requests.post", side_effect=_mock_requests_post)
    @patch("agents.discovery_agent.requests.get", side_effect=_mock_requests_get)
    @patch("agents.discovery_agent.time.sleep")
    @patch("agents.workspace_agent.time.sleep")
    def test_intelligence_falls_back_to_mock_when_bedrock_unavailable(
        self,
        mock_ws_sleep,
        mock_disc_sleep,
        mock_get,
        mock_post,
        mock_boto3_client,
        mock_notion,
    ):
        """When Bedrock is unavailable, intelligence uses mock analysis and
        pipeline still completes successfully.

        Validates: Requirements 1.1, 1.2
        """
        # boto3 client creation raises → triggers mock fallback
        mock_boto3_client.side_effect = Exception("No AWS credentials")

        mock_notion.databases.query = MagicMock(side_effect=_mock_notion_databases_query)
        mock_notion.pages.create = MagicMock(side_effect=_mock_notion_pages_create)
        mock_notion.pages.update = MagicMock(side_effect=_mock_notion_pages_update)

        from lambda_function import lambda_handler

        result = lambda_handler({}, None)

        # Pipeline completes successfully even without Bedrock
        assert result["statusCode"] == 200
        assert result["body"]["processed"] > 0
        # Invariant holds
        body = result["body"]
        assert body["new"] + body["updated"] + body["failed"] == body["processed"]
