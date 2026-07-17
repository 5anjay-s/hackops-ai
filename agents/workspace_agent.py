"""Workspace Agent: Synchronizes enriched hackathon data to Notion database.

Handles create, update, archive, and deduplication operations against the
Notion database using the (title, platform) pair as the unique key.
"""

import os
import time
from datetime import datetime, timezone
from typing import Optional

from notion_client import Client
from notion_client.errors import APIResponseError

from models.hackathon import EnrichedHackathon, SyncResult

# Initialize Notion client from environment
notion = Client(auth=os.environ.get("NOTION_TOKEN"))
DATABASE_ID = os.environ.get("DATABASE_ID", "")


def _notion_request_with_retry(fn, *args, **kwargs):
    """Call a Notion API function with exponential backoff on rate limiting.

    Retries up to 3 times (total 4 attempts including initial) when the Notion
    API returns a 429 rate limit response. Uses exponential backoff delays of
    1s, 2s, and 4s between retries.

    Args:
        fn: The Notion SDK function to call (e.g., notion.pages.create).
        *args: Positional arguments to pass to fn.
        **kwargs: Keyword arguments to pass to fn.

    Returns:
        The result of calling fn(*args, **kwargs).

    Raises:
        APIResponseError: If all retries are exhausted on rate limiting, or if
            a non-rate-limit API error occurs.
        Exception: Any non-APIResponseError exception is raised immediately.
    """
    max_retries = 3
    backoff_delays = [1, 2, 4]  # seconds

    for attempt in range(max_retries + 1):
        try:
            return fn(*args, **kwargs)
        except APIResponseError as e:
            if e.code == "rate_limited" and attempt < max_retries:
                time.sleep(backoff_delays[attempt])
            else:
                raise

    # Should not be reached, but just in case
    return fn(*args, **kwargs)


def sync_to_notion(hackathons: list[EnrichedHackathon]) -> SyncResult:
    """Sync enriched hackathons to Notion database.

    Main entry point for the Workspace Agent. Queries existing pages,
    deduplicates by (title, platform), creates/updates as needed, and
    archives expired entries.

    Args:
        hackathons: List of enriched hackathon objects to sync.

    Returns:
        SyncResult with processed, new, updated, archived, and failed counts.
        Invariant: new + updated + failed == processed.
    """
    new_count = 0
    updated_count = 0
    failed_count = 0

    # Step 1: Get all existing pages for deduplication
    try:
        existing_pages = _get_all_pages()
    except Exception:
        # If initial query fails, treat all as new entries (Requirement 8.5)
        existing_pages = []

    # Step 2: Build existing map of (title, platform) -> page_id
    existing_map: dict[tuple[str, str], str] = {}
    for page in existing_pages:
        title = page.get("title", "")
        platform = page.get("platform", "")
        page_id = page.get("page_id", "")
        if title and platform and page_id:
            existing_map[(title, platform)] = page_id

    # Step 3: Get next serial number
    next_serial = _get_next_serial(existing_pages)

    # Step 4: Process each hackathon
    for hackathon in hackathons:
        existing_page_id = _find_existing(
            hackathon.title, hackathon.platform, existing_map
        )

        try:
            if existing_page_id:
                # Update existing page
                success = _update_page(existing_page_id, hackathon)
                if success:
                    updated_count += 1
                else:
                    failed_count += 1
            else:
                # Create new page
                success = _create_page(hackathon, next_serial)
                if success:
                    new_count += 1
                    next_serial += 1
                else:
                    failed_count += 1
        except Exception:
            failed_count += 1

    # Step 5: Archive expired hackathons
    archived_count = _archive_expired(existing_pages)

    return SyncResult(
        processed=len(hackathons),
        new=new_count,
        updated=updated_count,
        archived=archived_count,
        failed=failed_count,
    )


def _get_all_pages() -> list[dict]:
    """Query all existing Notion pages in the database using pagination.

    Returns a list of dicts with keys: page_id, title, platform, deadline, status.
    Uses has_more/next_cursor pagination to retrieve all pages.
    """
    pages: list[dict] = []
    has_more = True
    next_cursor: Optional[str] = None

    while has_more:
        kwargs: dict = {"database_id": DATABASE_ID}
        if next_cursor:
            kwargs["start_cursor"] = next_cursor

        response = notion.databases.query(**kwargs)

        for page in response.get("results", []):
            page_data = _extract_page_data(page)
            if page_data:
                pages.append(page_data)

        has_more = response.get("has_more", False)
        next_cursor = response.get("next_cursor")

    return pages


def _extract_page_data(page: dict) -> Optional[dict]:
    """Extract relevant fields from a Notion page result.

    Args:
        page: Raw Notion page object from database query.

    Returns:
        Dict with page_id, title, platform, deadline, status or None if
        essential fields cannot be extracted.
    """
    properties = page.get("properties", {})

    # Extract title
    title_prop = properties.get("Hackathon", {})
    title_list = title_prop.get("title", [])
    title = title_list[0].get("plain_text", "") if title_list else ""

    # Extract platform
    platform_prop = properties.get("Platform", {})
    platform_select = platform_prop.get("select")
    platform = platform_select.get("name", "") if platform_select else ""

    # Extract deadline
    deadline_prop = properties.get("Deadline", {})
    deadline_date = deadline_prop.get("date")
    deadline = deadline_date.get("start", "") if deadline_date else None

    # Extract status
    status_prop = properties.get("Status", {})
    status_obj = status_prop.get("status")
    status = status_obj.get("name", "") if status_obj else ""

    # Extract serial number
    serial_prop = properties.get("S.No", {})
    serial = serial_prop.get("number")

    return {
        "page_id": page.get("id", ""),
        "title": title,
        "platform": platform,
        "deadline": deadline,
        "status": status,
        "serial": serial,
    }


def _create_page(hackathon: EnrichedHackathon, serial: int) -> bool:
    """Create a new Notion page for a hackathon.

    Maps all EnrichedHackathon fields to Notion page properties per the
    database schema, assigns the serial number, and sets "Last Synced"
    to the current UTC timestamp.

    Args:
        hackathon: The enriched hackathon to create a page for.
        serial: The serial number to assign.

    Returns:
        True if creation succeeded, False otherwise.
    """
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    properties: dict = {
        "S.No": {"number": serial},
        "Hackathon": {
            "title": [{"text": {"content": hackathon.title}}]
        },
        "Platform": {"select": {"name": hackathon.platform}},
        "Themes": {
            "multi_select": [{"name": t} for t in hackathon.themes]
        },
        "Prize": {
            "rich_text": [{"text": {"content": hackathon.prize or ""}}]
        },
        "Team Size": {
            "rich_text": [{"text": {"content": hackathon.team_size or ""}}]
        },
        "Priority": {"select": {"name": hackathon.priority}},
        "Difficulty": {"select": {"name": hackathon.difficulty}},
        "Winning %": {"number": hackathon.winning_probability},
        "Suggested Stack": {
            "multi_select": [{"name": s} for s in hackathon.recommended_stack]
        },
        "Execution Strategy": {
            "rich_text": [{"text": {"content": hackathon.execution_strategy}}]
        },
        "Status": {"status": {"name": "In progress"}},
        "Registration Link": {"url": hackathon.registration_url},
        "Last Synced": {"date": {"start": now_utc}},
    }

    # Only set date properties if values are present
    if hackathon.registration_deadline:
        properties["Deadline"] = {
            "date": {"start": hackathon.registration_deadline}
        }
    else:
        properties["Deadline"] = {"date": None}

    if hackathon.submission_deadline:
        properties["Submission Deadline"] = {
            "date": {"start": hackathon.submission_deadline}
        }
    else:
        properties["Submission Deadline"] = {"date": None}

    try:
        _notion_request_with_retry(
            notion.pages.create,
            parent={"database_id": DATABASE_ID},
            properties=properties,
        )
        return True
    except Exception:
        return False


def _update_page(page_id: str, hackathon: EnrichedHackathon) -> bool:
    """Update an existing Notion page with latest hackathon data.

    Overwrites all properties except S.No (serial number is preserved).
    Sets "Last Synced" to the current UTC timestamp.

    Args:
        page_id: The Notion page ID to update.
        hackathon: The enriched hackathon with updated data.

    Returns:
        True if update succeeded, False otherwise.
    """
    try:
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+00:00")

        properties: dict = {
            # Title
            "Hackathon": {
                "title": [{"text": {"content": hackathon.title}}]
            },
            # Platform (select)
            "Platform": {
                "select": {"name": hackathon.platform}
            },
            # Deadline (date) — nullable
            "Deadline": {
                "date": {"start": hackathon.registration_deadline}
                if hackathon.registration_deadline
                else None
            },
            # Submission Deadline (date) — nullable
            "Submission Deadline": {
                "date": {"start": hackathon.submission_deadline}
                if hackathon.submission_deadline
                else None
            },
            # Themes (multi-select)
            "Themes": {
                "multi_select": [{"name": t} for t in hackathon.themes]
            },
            # Prize (rich text) — nullable
            "Prize": {
                "rich_text": [{"text": {"content": hackathon.prize}}]
                if hackathon.prize
                else []
            },
            # Team Size (rich text) — nullable
            "Team Size": {
                "rich_text": [{"text": {"content": hackathon.team_size}}]
                if hackathon.team_size
                else []
            },
            # Priority (select)
            "Priority": {
                "select": {"name": hackathon.priority}
            },
            # Difficulty (select)
            "Difficulty": {
                "select": {"name": hackathon.difficulty}
            },
            # Winning % (number)
            "Winning %": {
                "number": hackathon.winning_probability
            },
            # Suggested Stack (multi-select)
            "Suggested Stack": {
                "multi_select": [{"name": s} for s in hackathon.recommended_stack]
            },
            # Execution Strategy (rich text)
            "Execution Strategy": {
                "rich_text": [{"text": {"content": hackathon.execution_strategy}}]
                if hackathon.execution_strategy
                else []
            },
            # Registration Link (url)
            "Registration Link": {
                "url": hackathon.registration_url
            },
            # Last Synced (date) — current UTC timestamp
            "Last Synced": {
                "date": {"start": now_utc}
            },
        }

        _notion_request_with_retry(
            notion.pages.update, page_id=page_id, properties=properties
        )
        return True
    except Exception:
        return False


def _archive_expired(existing_pages: list[dict]) -> int:
    """Archive hackathons past their registration deadline.

    Sets Status to "Expired" for pages whose registration_deadline
    is before today's date (UTC) and whose status is not already "Expired".
    Pages with None deadline are never archived (Requirement 9.4).

    Args:
        existing_pages: List of existing page metadata dicts with keys:
            page_id, title, platform, deadline, status.

    Returns:
        Count of pages successfully archived.
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    archived = 0

    for page in existing_pages:
        deadline = page.get("deadline")
        status = page.get("status", "")

        # Do NOT archive pages with None deadline (Requirement 9.4)
        if deadline is None:
            continue

        # Archive if deadline < today and not already expired
        if deadline < today and status != "Done":
            try:
                notion.pages.update(
                    page_id=page["page_id"],
                    properties={"Status": {"status": {"name": "Done"}}},
                )
                archived += 1
            except Exception:
                # Non-critical: skip this page and continue (Requirement 11.5)
                continue

    return archived


def _get_next_serial(existing_pages: list[dict]) -> int:
    """Determine the next serial number for new entries.

    Finds the maximum serial number among existing pages and returns
    max + 1. If no pages exist, starts from 1. If the serial query
    fails (e.g., all serials are None), falls back to len(existing_pages) + 1.

    Args:
        existing_pages: List of existing page metadata dicts, each expected
            to contain a "serial" key with an int or None value.

    Returns:
        The next serial number to use (always a positive integer).
    """
    if not existing_pages:
        return 1

    try:
        serials = [
            p.get("serial")
            for p in existing_pages
            if p.get("serial") is not None
        ]
        if serials:
            return max(serials) + 1
        # No valid serials found — fall back to page count + 1
        return len(existing_pages) + 1
    except Exception:
        # Fall back to page count + 1 on any failure
        return len(existing_pages) + 1


def _find_existing(
    title: str, platform: str, existing_map: dict[tuple[str, str], str]
) -> Optional[str]:
    """Find an existing page by (title, platform) pair.

    Uses case-sensitive string comparison per Requirement 8.2.

    Args:
        title: The hackathon title.
        platform: The hackathon platform.
        existing_map: Map of (title, platform) -> page_id.

    Returns:
        The page_id if found, None otherwise.
    """
    return existing_map.get((title, platform))
