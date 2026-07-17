"""Property-based tests for discovery resilience.

**Validates: Requirements 2.3, 3.3, 3.4, 12.1, 12.2**

Property 5: Discovery resilience
- discover_all() NEVER raises an exception regardless of which platform scrapers fail
- discover_all() always returns a list (possibly empty)
- The result is always a valid list of Hackathon objects
"""

from unittest.mock import patch

from hypothesis import given, settings
from hypothesis import strategies as st

from agents.discovery_agent import discover_all
from models.hackathon import Hackathon


# --- Strategies ---

# Strategy for generating valid Hackathon objects that scrapers might return
hackathon_strategy = st.builds(
    Hackathon,
    title=st.text(min_size=1, max_size=50).map(lambda s: s.strip() or "Test Hack"),
    platform=st.sampled_from(["Devpost", "Devfolio", "Unstop"]),
    registration_url=st.text(min_size=1, max_size=50).map(
        lambda s: f"https://example.com/{s.replace(' ', '-')}"
    ),
    registration_deadline=st.one_of(st.none(), st.just("2025-06-01")),
    submission_deadline=st.one_of(st.none(), st.just("2025-06-15")),
    organizer=st.one_of(st.none(), st.text(min_size=1, max_size=30)),
    themes=st.lists(st.text(min_size=1, max_size=20), max_size=5),
    mode=st.one_of(st.none(), st.sampled_from(["online", "offline", "hybrid"])),
    location=st.one_of(st.none(), st.text(min_size=1, max_size=30)),
    prize=st.one_of(st.none(), st.text(min_size=1, max_size=50)),
    team_size=st.one_of(st.none(), st.text(min_size=1, max_size=20)),
)

scraper_behavior_strategy = st.one_of(
    # Raises an exception
    st.sampled_from([
        RuntimeError("Connection timeout"),
        TimeoutError("Platform unreachable"),
        ValueError("Parse error"),
        OSError("Network error"),
        Exception("HTTP 503 Service Unavailable"),
    ]).map(lambda e: ("raise", e)),
    # Returns a list of hackathons
    st.lists(hackathon_strategy, min_size=1, max_size=5).map(
        lambda h: ("results", h)
    ),
    # Returns empty list
    st.just(("empty", [])),
)


def make_mock_scraper(behavior):
    """Create a mock scraper function based on the given behavior tuple."""
    action, payload = behavior

    def mock_scraper(max_pages=3):
        if action == "raise":
            raise payload
        elif action == "results":
            return payload
        else:  # "empty"
            return []

    return mock_scraper


class TestDiscoveryResilience:
    """Property 5: discover_all() never raises regardless of platform failures."""

    @given(
        devpost_behavior=scraper_behavior_strategy,
        devfolio_behavior=scraper_behavior_strategy,
        unstop_behavior=scraper_behavior_strategy,
    )
    @settings(max_examples=200)
    def test_discover_all_never_raises(
        self, devpost_behavior, devfolio_behavior, unstop_behavior
    ):
        """**Validates: Requirements 2.3, 3.3, 3.4, 12.1, 12.2**

        For any combination of platform scraper behaviors (raising exceptions,
        returning results, or returning empty), discover_all() must:
        1. Never raise an exception
        2. Always return a list
        3. Every item in the returned list is a Hackathon instance
        """
        mock_devpost = make_mock_scraper(devpost_behavior)
        mock_devfolio = make_mock_scraper(devfolio_behavior)
        mock_unstop = make_mock_scraper(unstop_behavior)

        with patch(
            "agents.discovery_agent.discover_devpost", side_effect=mock_devpost
        ), patch(
            "agents.discovery_agent.discover_devfolio", side_effect=mock_devfolio
        ), patch(
            "agents.discovery_agent.discover_unstop", side_effect=mock_unstop
        ):
            # discover_all must never raise
            result = discover_all(max_pages=3)

        # Must always return a list
        assert isinstance(result, list), (
            f"discover_all() returned {type(result).__name__}, expected list"
        )

        # Every item must be a Hackathon instance
        for item in result:
            assert isinstance(item, Hackathon), (
                f"Result contains {type(item).__name__}, expected Hackathon"
            )

    @given(
        devpost_behavior=scraper_behavior_strategy,
        devfolio_behavior=scraper_behavior_strategy,
        unstop_behavior=scraper_behavior_strategy,
    )
    @settings(max_examples=200)
    def test_result_length_bounded_by_successful_scrapers(
        self, devpost_behavior, devfolio_behavior, unstop_behavior
    ):
        """**Validates: Requirements 2.3, 12.1**

        The number of results returned should never exceed the total number
        of hackathons returned by successful (non-raising) scrapers.
        """
        mock_devpost = make_mock_scraper(devpost_behavior)
        mock_devfolio = make_mock_scraper(devfolio_behavior)
        mock_unstop = make_mock_scraper(unstop_behavior)

        # Count expected maximum results from successful scrapers
        max_expected = 0
        for behavior in [devpost_behavior, devfolio_behavior, unstop_behavior]:
            action, payload = behavior
            if action == "results":
                max_expected += len(payload)

        with patch(
            "agents.discovery_agent.discover_devpost", side_effect=mock_devpost
        ), patch(
            "agents.discovery_agent.discover_devfolio", side_effect=mock_devfolio
        ), patch(
            "agents.discovery_agent.discover_unstop", side_effect=mock_unstop
        ):
            result = discover_all(max_pages=3)

        # Result length cannot exceed total from successful scrapers
        # (deduplication may reduce it further)
        assert len(result) <= max_expected, (
            f"Got {len(result)} results but max expected from successful scrapers "
            f"was {max_expected}"
        )

    @given(
        devpost_behavior=st.just(("raise", RuntimeError("fail"))),
        devfolio_behavior=st.just(("raise", TimeoutError("timeout"))),
        unstop_behavior=st.just(("raise", OSError("network"))),
    )
    @settings(max_examples=10)
    def test_all_scrapers_fail_returns_empty_list(
        self, devpost_behavior, devfolio_behavior, unstop_behavior
    ):
        """**Validates: Requirements 2.3, 12.1**

        When ALL platform scrapers fail, discover_all() must return an
        empty list (never raise).
        """
        mock_devpost = make_mock_scraper(devpost_behavior)
        mock_devfolio = make_mock_scraper(devfolio_behavior)
        mock_unstop = make_mock_scraper(unstop_behavior)

        with patch(
            "agents.discovery_agent.discover_devpost", side_effect=mock_devpost
        ), patch(
            "agents.discovery_agent.discover_devfolio", side_effect=mock_devfolio
        ), patch(
            "agents.discovery_agent.discover_unstop", side_effect=mock_unstop
        ):
            result = discover_all(max_pages=3)

        assert result == [], (
            f"Expected empty list when all scrapers fail, got {len(result)} items"
        )
