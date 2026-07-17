"""Unit tests for discovery deduplication by registration_url.

Validates Requirement 2.5: The Discovery_Agent SHALL deduplicate results by
registration_url, retaining the first occurrence encountered and discarding
subsequent duplicates with the same URL.
"""

from unittest.mock import patch

from models.hackathon import Hackathon
from agents.discovery_agent import discover_all


def _make_hackathon(title: str, platform: str, url: str, **kwargs) -> Hackathon:
    """Helper to create a Hackathon with minimal required fields."""
    return Hackathon(
        title=title,
        platform=platform,
        registration_url=url,
        **kwargs,
    )


class TestDiscoverAllDeduplication:
    """Tests for deduplication logic in discover_all()."""

    @patch("agents.discovery_agent.discover_unstop")
    @patch("agents.discovery_agent.discover_devfolio")
    @patch("agents.discovery_agent.discover_devpost")
    def test_duplicates_removed_by_registration_url(
        self, mock_devpost, mock_devfolio, mock_unstop
    ):
        """Duplicate registration_urls across platforms are deduplicated."""
        shared_url = "https://devpost.com/hackathon-x"

        mock_devpost.return_value = [
            _make_hackathon("Hack X", "Devpost", shared_url),
        ]
        mock_devfolio.return_value = [
            _make_hackathon("Hack X Copy", "Devfolio", shared_url),
        ]
        mock_unstop.return_value = []

        results = discover_all(max_pages=1)

        assert len(results) == 1
        assert results[0].title == "Hack X"
        assert results[0].platform == "Devpost"

    @patch("agents.discovery_agent.discover_unstop")
    @patch("agents.discovery_agent.discover_devfolio")
    @patch("agents.discovery_agent.discover_devpost")
    def test_first_occurrence_retained(
        self, mock_devpost, mock_devfolio, mock_unstop
    ):
        """The first occurrence of a duplicated URL is retained, not the last."""
        url = "https://unstop.com/shared-hack"

        # Devpost returns first (iteration order)
        mock_devpost.return_value = [
            _make_hackathon("First Entry", "Devpost", url, prize="$5000"),
        ]
        mock_devfolio.return_value = [
            _make_hackathon("Second Entry", "Devfolio", url, prize="$10000"),
        ]
        mock_unstop.return_value = [
            _make_hackathon("Third Entry", "Unstop", url, prize="$20000"),
        ]

        results = discover_all(max_pages=1)

        assert len(results) == 1
        assert results[0].title == "First Entry"
        assert results[0].platform == "Devpost"
        assert results[0].prize == "$5000"

    @patch("agents.discovery_agent.discover_unstop")
    @patch("agents.discovery_agent.discover_devfolio")
    @patch("agents.discovery_agent.discover_devpost")
    def test_unique_urls_all_retained(
        self, mock_devpost, mock_devfolio, mock_unstop
    ):
        """Hackathons with different URLs are all retained."""
        mock_devpost.return_value = [
            _make_hackathon("Hack A", "Devpost", "https://devpost.com/a"),
            _make_hackathon("Hack B", "Devpost", "https://devpost.com/b"),
        ]
        mock_devfolio.return_value = [
            _make_hackathon("Hack C", "Devfolio", "https://devfolio.co/c"),
        ]
        mock_unstop.return_value = [
            _make_hackathon("Hack D", "Unstop", "https://unstop.com/d"),
        ]

        results = discover_all(max_pages=1)

        assert len(results) == 4
        urls = [h.registration_url for h in results]
        assert len(set(urls)) == 4

    @patch("agents.discovery_agent.discover_unstop")
    @patch("agents.discovery_agent.discover_devfolio")
    @patch("agents.discovery_agent.discover_devpost")
    def test_multiple_duplicates_within_same_platform(
        self, mock_devpost, mock_devfolio, mock_unstop
    ):
        """Duplicates within the same platform are also deduplicated."""
        url = "https://devpost.com/duplicate"

        mock_devpost.return_value = [
            _make_hackathon("First", "Devpost", url),
            _make_hackathon("Second", "Devpost", url),
            _make_hackathon("Third", "Devpost", url),
        ]
        mock_devfolio.return_value = []
        mock_unstop.return_value = []

        results = discover_all(max_pages=1)

        assert len(results) == 1
        assert results[0].title == "First"

    @patch("agents.discovery_agent.discover_unstop")
    @patch("agents.discovery_agent.discover_devfolio")
    @patch("agents.discovery_agent.discover_devpost")
    def test_empty_results_no_error(
        self, mock_devpost, mock_devfolio, mock_unstop
    ):
        """Deduplication handles empty results gracefully."""
        mock_devpost.return_value = []
        mock_devfolio.return_value = []
        mock_unstop.return_value = []

        results = discover_all(max_pages=1)

        assert results == []

    @patch("agents.discovery_agent.discover_unstop")
    @patch("agents.discovery_agent.discover_devfolio")
    @patch("agents.discovery_agent.discover_devpost")
    def test_order_preserved_after_dedup(
        self, mock_devpost, mock_devfolio, mock_unstop
    ):
        """Order of first occurrences is preserved after dedup."""
        mock_devpost.return_value = [
            _make_hackathon("A", "Devpost", "https://devpost.com/a"),
            _make_hackathon("B", "Devpost", "https://devpost.com/b"),
        ]
        mock_devfolio.return_value = [
            _make_hackathon("C", "Devfolio", "https://devfolio.co/c"),
            # Duplicate of A from Devpost
            _make_hackathon("A dup", "Devfolio", "https://devpost.com/a"),
        ]
        mock_unstop.return_value = [
            _make_hackathon("D", "Unstop", "https://unstop.com/d"),
        ]

        results = discover_all(max_pages=1)

        assert len(results) == 4
        titles = [h.title for h in results]
        assert titles == ["A", "B", "C", "D"]
