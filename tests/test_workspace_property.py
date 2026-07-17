"""Property-based tests for the Workspace Agent.

Covers Properties 1, 10, and 12 from the design document:
- Property 1: Pipeline count invariant
- Property 10: No duplicate Notion pages
- Property 12: Serial number contiguity

Uses hypothesis to generate EnrichedHackathon objects and verify universal
properties hold across all valid inputs.
"""

import os
import sys
from unittest.mock import MagicMock, patch

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Patch environment before importing workspace_agent
os.environ.setdefault("NOTION_TOKEN", "test-token")
os.environ.setdefault("DATABASE_ID", "test-db-id")

from hypothesis import given, settings
from hypothesis import strategies as st

from agents.workspace_agent import sync_to_notion, _find_existing, _get_next_serial
from models.hackathon import EnrichedHackathon, SyncResult


# --- Strategies ---

PLATFORMS = st.sampled_from(["Devpost", "Devfolio", "Unstop"])

_url_slugs = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Nd"), whitelist_characters="-"),
    min_size=1,
    max_size=30,
)

VALID_URLS = _url_slugs.map(lambda slug: f"https://example.com/{slug}")

ENRICHED_HACKATHON_STRATEGY = st.builds(
    EnrichedHackathon,
    title=st.text(min_size=1, max_size=50).filter(lambda t: t.strip()),
    platform=PLATFORMS,
    registration_url=VALID_URLS,
    registration_deadline=st.one_of(st.none(), st.just("2025-06-01")),
    submission_deadline=st.one_of(st.none(), st.just("2025-07-01")),
    organizer=st.one_of(st.none(), st.text(min_size=1, max_size=30)),
    themes=st.lists(st.text(min_size=1, max_size=20), max_size=5),
    mode=st.one_of(st.none(), st.sampled_from(["online", "offline", "hybrid"])),
    location=st.one_of(st.none(), st.text(min_size=1, max_size=30)),
    prize=st.one_of(st.none(), st.text(min_size=1, max_size=50)),
    team_size=st.one_of(st.none(), st.text(min_size=1, max_size=20)),
    priority=st.sampled_from(["High", "Medium", "Low"]),
    difficulty=st.sampled_from(["Easy", "Medium", "Hard"]),
    winning_probability=st.integers(min_value=0, max_value=100),
    recommended_stack=st.lists(st.text(min_size=1, max_size=20), min_size=1, max_size=5),
    recommended_team_size=st.integers(min_value=1, max_value=10),
    execution_strategy=st.text(min_size=1, max_size=100).filter(lambda t: t.strip()),
    summary=st.text(min_size=1, max_size=100).filter(lambda t: t.strip()),
)

ENRICHED_HACKATHON_LIST_STRATEGY = st.lists(
    ENRICHED_HACKATHON_STRATEGY, min_size=0, max_size=10
)


# --- Property 1: Pipeline count invariant ---


class TestPipelineCountInvariant:
    """Property 1: Pipeline count invariant.

    For any pipeline execution that completes successfully, the sum of new,
    updated, and failed counts SHALL equal the processed count.

    **Validates: Requirements 1.3, 11.2**
    """

    @given(hackathons=ENRICHED_HACKATHON_LIST_STRATEGY)
    @settings(max_examples=200)
    @patch("agents.workspace_agent._get_all_pages", return_value=[])
    @patch("agents.workspace_agent.notion")
    def test_new_plus_updated_plus_failed_equals_processed(
        self, mock_notion, mock_get_all_pages, hackathons
    ):
        """**Validates: Requirements 1.3, 11.2**

        For any batch of EnrichedHackathon objects synced with an empty existing
        database, new + updated + failed must equal processed.
        """
        mock_notion.pages.create = MagicMock(return_value={"id": "new-page"})
        mock_notion.pages.update = MagicMock(return_value={"id": "updated-page"})

        result = sync_to_notion(hackathons)

        assert result.new + result.updated + result.failed == result.processed, (
            f"Invariant violated: new({result.new}) + updated({result.updated}) + "
            f"failed({result.failed}) != processed({result.processed})"
        )

    @given(hackathons=st.lists(ENRICHED_HACKATHON_STRATEGY, min_size=1, max_size=10))
    @settings(max_examples=200)
    @patch("agents.workspace_agent._get_all_pages", return_value=[])
    @patch("agents.workspace_agent.notion")
    def test_processed_equals_input_length(
        self, mock_notion, mock_get_all_pages, hackathons
    ):
        """**Validates: Requirements 1.3, 11.2**

        The processed count must always equal the number of input hackathons.
        """
        mock_notion.pages.create = MagicMock(return_value={"id": "new-page"})
        mock_notion.pages.update = MagicMock(return_value={"id": "updated-page"})

        result = sync_to_notion(hackathons)

        assert result.processed == len(hackathons), (
            f"processed({result.processed}) != len(hackathons)({len(hackathons)})"
        )

    @given(hackathons=st.lists(ENRICHED_HACKATHON_STRATEGY, min_size=1, max_size=8))
    @settings(max_examples=100)
    @patch("agents.workspace_agent._get_all_pages", return_value=[])
    @patch("agents.workspace_agent.notion")
    def test_invariant_holds_with_random_failures(
        self, mock_notion, mock_get_all_pages, hackathons
    ):
        """**Validates: Requirements 1.3, 11.2**

        Even when some create operations fail (raise exceptions), the invariant
        new + updated + failed == processed still holds.
        """
        # Make every other create call fail
        call_count = [0]

        def flaky_create(**kwargs):
            call_count[0] += 1
            if call_count[0] % 2 == 0:
                raise Exception("Simulated Notion failure")
            return {"id": f"page-{call_count[0]}"}

        mock_notion.pages.create = MagicMock(side_effect=flaky_create)
        mock_notion.pages.update = MagicMock(return_value={"id": "updated-page"})

        result = sync_to_notion(hackathons)

        assert result.new + result.updated + result.failed == result.processed, (
            f"Invariant violated with failures: new({result.new}) + updated({result.updated}) + "
            f"failed({result.failed}) != processed({result.processed})"
        )


# --- Property 10: No duplicate Notion pages ---


class TestNoDuplicateNotionPages:
    """Property 10: No duplicate Notion pages.

    For any set of sync operations, at most one Notion page SHALL exist for
    any (title, platform) pair in the database after sync completes.

    **Validates: Requirements 8.2, 8.3, 8.4**
    """

    @given(
        hackathons=st.lists(ENRICHED_HACKATHON_STRATEGY, min_size=2, max_size=10)
    )
    @settings(max_examples=200)
    def test_find_existing_identifies_duplicates(self, hackathons):
        """**Validates: Requirements 8.2, 8.3, 8.4**

        When existing pages match some hackathons by (title, platform),
        _find_existing correctly returns the page_id for matches and None
        for non-matches.
        """
        # Build an existing_map from the first half of hackathons
        half = len(hackathons) // 2
        existing_map: dict[tuple[str, str], str] = {}
        for i, h in enumerate(hackathons[:half]):
            existing_map[(h.title, h.platform)] = f"page-{i}"

        # Verify _find_existing finds existing ones
        for h in hackathons[:half]:
            result = _find_existing(h.title, h.platform, existing_map)
            assert result is not None, (
                f"Expected to find existing page for ({h.title!r}, {h.platform!r})"
            )

        # Verify _find_existing returns None for truly new (title, platform) pairs
        for h in hackathons[half:]:
            if (h.title, h.platform) not in existing_map:
                result = _find_existing(h.title, h.platform, existing_map)
                assert result is None, (
                    f"Expected None for new ({h.title!r}, {h.platform!r}), got {result}"
                )

    @given(
        hackathons=st.lists(ENRICHED_HACKATHON_STRATEGY, min_size=2, max_size=8)
    )
    @settings(max_examples=200)
    @patch("agents.workspace_agent.notion")
    def test_duplicates_call_update_not_create(self, mock_notion, hackathons):
        """**Validates: Requirements 8.2, 8.3, 8.4**

        When hackathons with overlapping (title, platform) pairs exist in the
        database, update is called for existing ones and create for new ones.
        No duplicate pages are created.
        """
        # Simulate that first half already exists in Notion
        half = len(hackathons) // 2
        existing_pages = []
        for i, h in enumerate(hackathons[:half]):
            existing_pages.append({
                "page_id": f"existing-{i}",
                "title": h.title,
                "platform": h.platform,
                "deadline": h.registration_deadline,
                "status": "Active",
                "serial": i + 1,
            })

        mock_notion.pages.create = MagicMock(return_value={"id": "new-page"})
        mock_notion.pages.update = MagicMock(return_value={"id": "updated-page"})

        with patch("agents.workspace_agent._get_all_pages", return_value=existing_pages):
            result = sync_to_notion(hackathons)

        # The key invariant: no duplicate creates for existing (title, platform) pairs
        # Count how many unique (title, platform) pairs exist both in existing and input
        existing_keys = {(p["title"], p["platform"]) for p in existing_pages}
        input_keys = [(h.title, h.platform) for h in hackathons]

        expected_updates = sum(1 for k in input_keys if k in existing_keys)
        expected_creates = sum(1 for k in input_keys if k not in existing_keys)

        assert result.updated == expected_updates, (
            f"Expected {expected_updates} updates, got {result.updated}"
        )
        assert result.new == expected_creates, (
            f"Expected {expected_creates} creates, got {result.new}"
        )

    @given(
        data=st.data()
    )
    @settings(max_examples=200)
    @patch("agents.workspace_agent._get_all_pages", return_value=[])
    @patch("agents.workspace_agent.notion")
    def test_duplicate_input_hackathons_all_created_or_tracked(
        self, mock_notion, mock_get_all_pages, data
    ):
        """**Validates: Requirements 8.2, 8.3, 8.4**

        When the input itself contains duplicate (title, platform) pairs and
        the database is empty, only the first occurrence creates a new page.
        Subsequent duplicates are still processed (the map doesn't grow within
        a single sync run to include just-created pages), so all are counted.
        """
        # Generate a hackathon then duplicate it
        base = data.draw(ENRICHED_HACKATHON_STRATEGY)
        hackathons = [base, base]

        mock_notion.pages.create = MagicMock(return_value={"id": "new-page"})
        mock_notion.pages.update = MagicMock(return_value={"id": "updated-page"})

        result = sync_to_notion(hackathons)

        # The sync processes all items, invariant must hold
        assert result.new + result.updated + result.failed == result.processed


# --- Property 12: Serial number contiguity ---


class TestSerialNumberContiguity:
    """Property 12: Serial number contiguity.

    For any batch of newly created pages within a single sync run, the
    assigned serial numbers SHALL form a contiguous ascending sequence
    starting from the next value after the highest existing serial.

    **Validates: Requirements 10.1, 10.2**
    """

    @given(
        hackathons=st.lists(ENRICHED_HACKATHON_STRATEGY, min_size=1, max_size=10)
    )
    @settings(max_examples=200)
    @patch("agents.workspace_agent._get_all_pages", return_value=[])
    @patch("agents.workspace_agent.notion")
    def test_serials_contiguous_from_1_when_empty_db(
        self, mock_notion, mock_get_all_pages, hackathons
    ):
        """**Validates: Requirements 10.1, 10.2**

        When no existing pages exist, serial numbers start at 1 and form
        a contiguous ascending sequence.
        """
        # Track serial numbers passed to _create_page via notion.pages.create
        serials_assigned: list[int] = []

        def capture_create(**kwargs):
            props = kwargs.get("properties", {})
            serial = props.get("S.No", {}).get("number")
            if serial is not None:
                serials_assigned.append(serial)
            return {"id": f"page-{serial}"}

        mock_notion.pages.create = MagicMock(side_effect=capture_create)
        mock_notion.pages.update = MagicMock(return_value={"id": "updated-page"})

        sync_to_notion(hackathons)

        # All should be new creates since DB is empty
        assert len(serials_assigned) == len(hackathons), (
            f"Expected {len(hackathons)} creates, got {len(serials_assigned)}"
        )

        # Verify contiguous ascending from 1
        expected = list(range(1, len(hackathons) + 1))
        assert serials_assigned == expected, (
            f"Serial numbers not contiguous: {serials_assigned}, expected {expected}"
        )

    @given(
        hackathons=st.lists(ENRICHED_HACKATHON_STRATEGY, min_size=1, max_size=8),
        existing_max_serial=st.integers(min_value=1, max_value=100),
    )
    @settings(max_examples=200)
    @patch("agents.workspace_agent.notion")
    def test_serials_start_after_existing_max(
        self, mock_notion, hackathons, existing_max_serial
    ):
        """**Validates: Requirements 10.1, 10.2**

        When existing pages have a max serial number N, new pages get serials
        starting from N+1, forming a contiguous ascending sequence.
        """
        # Create existing pages with serials up to existing_max_serial
        existing_pages = [
            {
                "page_id": f"existing-{i}",
                "title": f"Existing Hack {i}",
                "platform": "Devpost",
                "deadline": "2099-12-31",
                "status": "Active",
                "serial": existing_max_serial - i,
            }
            for i in range(min(3, existing_max_serial))
        ]

        serials_assigned: list[int] = []

        def capture_create(**kwargs):
            props = kwargs.get("properties", {})
            serial = props.get("S.No", {}).get("number")
            if serial is not None:
                serials_assigned.append(serial)
            return {"id": f"page-{serial}"}

        mock_notion.pages.create = MagicMock(side_effect=capture_create)
        mock_notion.pages.update = MagicMock(return_value={"id": "updated-page"})

        with patch("agents.workspace_agent._get_all_pages", return_value=existing_pages):
            sync_to_notion(hackathons)

        if serials_assigned:
            # First serial should be existing_max_serial + 1
            assert serials_assigned[0] == existing_max_serial + 1, (
                f"First serial {serials_assigned[0]} != expected {existing_max_serial + 1}"
            )

            # All serials must be contiguous ascending
            for i in range(1, len(serials_assigned)):
                assert serials_assigned[i] == serials_assigned[i - 1] + 1, (
                    f"Serial gap at position {i}: {serials_assigned[i-1]} -> {serials_assigned[i]}"
                )

    @given(
        hackathons=st.lists(ENRICHED_HACKATHON_STRATEGY, min_size=1, max_size=6)
    )
    @settings(max_examples=100)
    @patch("agents.workspace_agent._get_all_pages", return_value=[])
    @patch("agents.workspace_agent.notion")
    def test_serials_strictly_ascending(
        self, mock_notion, mock_get_all_pages, hackathons
    ):
        """**Validates: Requirements 10.1, 10.2**

        Serial numbers assigned within a single sync must be strictly ascending
        (each serial > previous serial).
        """
        serials_assigned: list[int] = []

        def capture_create(**kwargs):
            props = kwargs.get("properties", {})
            serial = props.get("S.No", {}).get("number")
            if serial is not None:
                serials_assigned.append(serial)
            return {"id": f"page-{serial}"}

        mock_notion.pages.create = MagicMock(side_effect=capture_create)
        mock_notion.pages.update = MagicMock(return_value={"id": "updated-page"})

        sync_to_notion(hackathons)

        # Verify strictly ascending
        for i in range(1, len(serials_assigned)):
            assert serials_assigned[i] > serials_assigned[i - 1], (
                f"Serials not strictly ascending at position {i}: "
                f"{serials_assigned[i-1]} >= {serials_assigned[i]}"
            )
