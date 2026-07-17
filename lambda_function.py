"""HackOps AI Lambda Orchestrator.

AWS Lambda entry point that coordinates the three-agent pipeline:
Discovery → Intelligence → Workspace.

Contains zero business logic — only agent invocations in sequence
and aggregation of the Workspace Agent SyncResult into the response body.
"""

import os
from typing import Any

from agents.discovery_agent import discover_all
from agents.intelligence_agent import analyze_batch
from agents.workspace_agent import sync_to_notion


def lambda_handler(event: dict, context: Any) -> dict:
    """AWS Lambda entry point triggered by EventBridge Scheduler.

    Orchestrates the pipeline: discover → analyze → sync.

    Args:
        event: EventBridge scheduled event payload.
        context: AWS Lambda context object.

    Returns:
        dict with statusCode and body containing pipeline results or error.
    """
    # Step 1: Validate required environment variables
    notion_token = os.environ.get("NOTION_TOKEN", "").strip()
    database_id = os.environ.get("DATABASE_ID", "").strip()

    if not notion_token or not database_id:
        missing = []
        if not notion_token:
            missing.append("NOTION_TOKEN")
        if not database_id:
            missing.append("DATABASE_ID")
        return {
            "statusCode": 500,
            "body": {
                "error": f"Missing required environment variable(s): {', '.join(missing)}"
            },
        }

    try:
        # Step 2: Discovery — find hackathons from all platforms
        hackathons = discover_all()

        # Step 3: Short-circuit if no hackathons found
        if not hackathons:
            return {
                "statusCode": 200,
                "body": {
                    "processed": 0,
                    "new": 0,
                    "updated": 0,
                    "failed": 0,
                },
            }

        # Step 4: Intelligence — enrich with AI analysis
        enriched = analyze_batch(hackathons)

        # Step 5: Workspace — sync to Notion database
        result = sync_to_notion(enriched)

        # Step 6: Return aggregated SyncResult
        return {
            "statusCode": 200,
            "body": {
                "processed": result.processed,
                "new": result.new,
                "updated": result.updated,
                "failed": result.failed,
            },
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "body": {"error": str(e)},
        }
