"""HackOps AI — Local development entry point.

Runs the full pipeline locally: Discovery → Intelligence → Workspace.
"""
import os
from dotenv import load_dotenv

from agents.discovery_agent import discover_all
from agents.intelligence_agent import analyze_batch
from agents.workspace_agent import sync_to_notion


def main():
    load_dotenv()

    # Validate required env vars
    if not os.environ.get("NOTION_TOKEN") or not os.environ.get("DATABASE_ID"):
        print("ERROR: NOTION_TOKEN and DATABASE_ID environment variables are required.")
        return

    print("[HackOps AI] Starting pipeline...")

    # Step 1: Discovery
    print("[Step 1] Discovering hackathons...")
    hackathons = discover_all(max_pages=3)
    print(f"  Found {len(hackathons)} hackathons")

    if not hackathons:
        print("  No hackathons found. Pipeline complete.")
        return

    # Step 2: Intelligence
    print("[Step 2] Analyzing hackathons...")
    enriched = analyze_batch(hackathons)
    print(f"  Enriched {len(enriched)} hackathons")

    # Step 3: Workspace
    print("[Step 3] Syncing to Notion...")
    result = sync_to_notion(enriched)

    print(f"\n[Results]")
    print(f"  Processed: {result.processed}")
    print(f"  New: {result.new}")
    print(f"  Updated: {result.updated}")
    print(f"  Archived: {result.archived}")
    print(f"  Failed: {result.failed}")


if __name__ == "__main__":
    main()
