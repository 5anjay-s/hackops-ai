"""Property-based tests for discovery deduplication.

**Validates: Requirements 2.5**

Property 4: Discovery deduplication
- For any list of Hackathon objects with overlapping registration_urls,
  discover_all() returns no duplicate registration_urls in its output.
- The output length is always <= total input length.
- Every URL in the output appeared in at least one input list.
"""

from unittest.mock import patch

from hypothesis import given, settings
from hypothesis import strategies as st

from models.hackathon import Hackathon
from agents.discovery_agent import discover_all


# --- Strategies ---

PLATFORMS = st.sampled_from(["Devpost", "Devfolio", "Unstop"])

# Generate valid HTTPS URLs for registration_url
_url_slugs = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Nd"), whitelist_characters="-"),
    min_size=1,
    max_size=30,
)

VALID_URLS = _url_slugs.map(lambda slug: f"https://example.com/{slug}")


def hackathon_strategy(url_pool: st.SearchStrategy = VALID_URLS) -> st.SearchStrategy:
    """Strategy to generate a valid Hackathon object with a URL from the given pool."""
    return st.builds(
        Hackathon,
        title=st.text(min_size=1, max_size=50).filter(lambda t: t.strip()),
        platform=PLATFORMS,
        registration_url=url_pool,
    )


# Strategy for a list of hackathons where some share the same URLs (duplicates)
def hackathon_list_with_duplicates():
    """Generate a list of Hackathons where some share the same registration_url."""
    # First generate a small pool of URLs, then build hackathons picking from that pool
    return st.lists(
        st.text(
            alphabet=st.characters(whitelist_categories=("Ll", "Nd"), whitelist_characters="-"),
            min_size=1,
            max_size=20,
        ),
        min_size=1,
        max_size=5,
    ).flatmap(
        lambda slugs: st.lists(
            st.builds(
                Hackathon,
                title=st.text(min_size=1, max_size=50).filter(lambda t: t.strip()),
                platform=PLATFORMS,
                registration_url=st.sampled_from(
                    [f"https://example.com/{s}" for s in slugs]
                ),
            ),
            min_size=1,
            max_size=20,
        )
    )


# --- Tests ---


class TestDiscoveryDeduplicationProperty:
    """Property 4: Discovery deduplication guarantees no duplicate URLs in output."""

    @given(hackathons=hackathon_list_with_duplicates())
    @settings(max_examples=200)
    @patch("agents.discovery_agent.discover_unstop")
    @patch("agents.discovery_agent.discover_devfolio")
    @patch("agents.discovery_agent.discover_devpost")
    def test_no_duplicate_urls_in_output(
        self, mock_devpost, mock_devfolio, mock_unstop, hackathons
    ):
        """**Validates: Requirements 2.5**

        For any collection of Hackathon objects (potentially with overlapping
        registration_urls), discover_all() must return a list with no two items
        sharing the same registration_url.
        """
        # Split hackathons across the three mocked scrapers
        third = len(hackathons) // 3
        mock_devpost.return_value = hackathons[:third]
        mock_devfolio.return_value = hackathons[third: 2 * third]
        mock_unstop.return_value = hackathons[2 * third:]

        results = discover_all(max_pages=1)

        # No duplicates in output
        output_urls = [h.registration_url for h in results]
        assert len(output_urls) == len(set(output_urls)), (
            f"Duplicate URLs found in output: {output_urls}"
        )

    @given(hackathons=hackathon_list_with_duplicates())
    @settings(max_examples=200)
    @patch("agents.discovery_agent.discover_unstop")
    @patch("agents.discovery_agent.discover_devfolio")
    @patch("agents.discovery_agent.discover_devpost")
    def test_output_length_lte_input_length(
        self, mock_devpost, mock_devfolio, mock_unstop, hackathons
    ):
        """**Validates: Requirements 2.5**

        The output list length must always be <= the total number of input
        hackathons across all platforms.
        """
        # All hackathons go through devpost for simplicity
        mock_devpost.return_value = hackathons
        mock_devfolio.return_value = []
        mock_unstop.return_value = []

        results = discover_all(max_pages=1)

        assert len(results) <= len(hackathons), (
            f"Output length {len(results)} exceeds input length {len(hackathons)}"
        )

    @given(hackathons=hackathon_list_with_duplicates())
    @settings(max_examples=200)
    @patch("agents.discovery_agent.discover_unstop")
    @patch("agents.discovery_agent.discover_devfolio")
    @patch("agents.discovery_agent.discover_devpost")
    def test_all_output_urls_present_in_input(
        self, mock_devpost, mock_devfolio, mock_unstop, hackathons
    ):
        """**Validates: Requirements 2.5**

        Every registration_url in the output must have appeared in at least
        one of the input lists. discover_all() must never fabricate URLs.
        """
        # Distribute across platforms
        half = len(hackathons) // 2
        mock_devpost.return_value = hackathons[:half]
        mock_devfolio.return_value = hackathons[half:]
        mock_unstop.return_value = []

        results = discover_all(max_pages=1)

        input_urls = {h.registration_url for h in hackathons}
        for result in results:
            assert result.registration_url in input_urls, (
                f"Output URL '{result.registration_url}' was not in the input"
            )
