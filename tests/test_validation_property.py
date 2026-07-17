"""Property-based tests for hackathon data validation.

**Property 3: Discovery output schema validity**
**Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5**

Uses hypothesis to generate Hackathon-like dicts and verify that
validate_hackathon accepts only valid data and never raises exceptions.
"""

import re
from hypothesis import given, assume, settings
from hypothesis import strategies as st

from models.hackathon import Hackathon
from utils.validation import validate_hackathon


# --- Strategies ---

VALID_PLATFORMS = ["Devpost", "Devfolio", "Unstop"]

_ISO_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def valid_title_strategy():
    """Generate non-empty titles up to 200 chars."""
    return st.text(
        alphabet=st.characters(blacklist_categories=("Cs",)),
        min_size=1,
        max_size=200,
    ).filter(lambda s: s.strip())


def valid_platform_strategy():
    """Generate a valid platform value."""
    return st.sampled_from(VALID_PLATFORMS)


def valid_url_strategy():
    """Generate a valid HTTPS URL within length limits."""
    return st.text(
        alphabet=st.characters(
            whitelist_categories=("Ll", "Lu", "Nd"),
            whitelist_characters="-._~:/?#[]@!$&'()*+,;=",
        ),
        min_size=1,
        max_size=200,
    ).map(lambda path: f"https://example.com/{path}")


def valid_date_strategy():
    """Generate a valid ISO 8601 date string or None."""
    return st.one_of(
        st.none(),
        st.dates().map(lambda d: d.strftime("%Y-%m-%d")),
    )


def valid_hackathon_dict_strategy():
    """Generate a dict representing a valid hackathon."""
    return st.fixed_dictionaries(
        {
            "title": valid_title_strategy(),
            "platform": valid_platform_strategy(),
            "registration_url": valid_url_strategy(),
            "registration_deadline": valid_date_strategy(),
            "submission_deadline": valid_date_strategy(),
            "organizer": st.one_of(st.none(), st.text(min_size=1, max_size=100)),
            "themes": st.lists(st.text(min_size=1, max_size=50), max_size=10),
            "mode": st.one_of(
                st.none(), st.sampled_from(["online", "offline", "hybrid"])
            ),
            "location": st.one_of(st.none(), st.text(min_size=1, max_size=100)),
            "prize": st.one_of(st.none(), st.text(min_size=1, max_size=200)),
            "team_size": st.one_of(st.none(), st.text(min_size=1, max_size=50)),
        }
    )


def invalid_hackathon_dict_strategy():
    """Generate a dict that should fail validation.

    Creates dicts with at least one invalid required field:
    empty title, bad platform, bad url, or bad date format.
    """
    invalid_title = st.one_of(
        st.just(""),
        st.just("   "),
        st.text(min_size=201, max_size=210),
        st.integers().map(str).map(lambda _: ""),  # empty after strip
    )

    invalid_platform = st.text(min_size=1, max_size=50).filter(
        lambda s: s not in VALID_PLATFORMS
    )

    invalid_url = st.one_of(
        st.just("http://example.com/hack"),
        st.just("ftp://example.com/hack"),
        st.just("not-a-url"),
        st.just(""),
    )

    invalid_date = st.one_of(
        st.just("not-a-date"),
        st.just("15-01-2025"),
        st.just("Jan 15, 2025"),
        st.just("2025/01/15"),
        st.just("12345"),
    )

    # Strategy 1: invalid title
    bad_title_dict = st.fixed_dictionaries(
        {
            "title": invalid_title,
            "platform": valid_platform_strategy(),
            "registration_url": valid_url_strategy(),
            "registration_deadline": valid_date_strategy(),
            "submission_deadline": valid_date_strategy(),
        }
    )

    # Strategy 2: invalid platform
    bad_platform_dict = st.fixed_dictionaries(
        {
            "title": valid_title_strategy(),
            "platform": invalid_platform,
            "registration_url": valid_url_strategy(),
            "registration_deadline": valid_date_strategy(),
            "submission_deadline": valid_date_strategy(),
        }
    )

    # Strategy 3: invalid URL
    bad_url_dict = st.fixed_dictionaries(
        {
            "title": valid_title_strategy(),
            "platform": valid_platform_strategy(),
            "registration_url": invalid_url,
            "registration_deadline": valid_date_strategy(),
            "submission_deadline": valid_date_strategy(),
        }
    )

    # Strategy 4: invalid date format
    bad_date_dict = st.fixed_dictionaries(
        {
            "title": valid_title_strategy(),
            "platform": valid_platform_strategy(),
            "registration_url": valid_url_strategy(),
            "registration_deadline": invalid_date,
            "submission_deadline": valid_date_strategy(),
        }
    )

    return st.one_of(bad_title_dict, bad_platform_dict, bad_url_dict, bad_date_dict)


# --- Property Tests ---


class TestDiscoveryOutputSchemaValidity:
    """Property 3: Discovery output schema validity.

    Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5
    """

    @given(data=valid_hackathon_dict_strategy())
    @settings(max_examples=200)
    def test_valid_hackathon_dicts_produce_hackathon_instance(self, data):
        """For valid hackathon dicts, validate_hackathon returns a Hackathon instance.

        **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5**

        A valid dict has:
        - title: non-empty after strip, ≤200 chars
        - platform: one of Devpost, Devfolio, Unstop
        - registration_url: starts with https://
        - dates: YYYY-MM-DD format or None
        """
        result = validate_hackathon(data)
        assert isinstance(result, Hackathon), (
            f"Expected Hackathon instance for valid input, got {type(result)}"
        )

        # Verify the returned Hackathon has correct required fields
        assert result.title == data["title"].strip()
        assert result.platform == data["platform"]
        assert result.registration_url == data["registration_url"]

        # Verify date fields are preserved correctly
        assert result.registration_deadline == data["registration_deadline"]
        assert result.submission_deadline == data["submission_deadline"]

    @given(data=invalid_hackathon_dict_strategy())
    @settings(max_examples=200)
    def test_invalid_hackathon_dicts_return_none(self, data):
        """For invalid hackathon dicts, validate_hackathon returns None.

        **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5**

        Invalid dicts have at least one of:
        - empty/too-long title
        - platform not in allowed set
        - URL not starting with https://
        - date not matching YYYY-MM-DD pattern
        """
        result = validate_hackathon(data)
        assert result is None, (
            f"Expected None for invalid input {data}, got {result}"
        )

    @given(data=st.one_of(
        # Completely arbitrary dicts with random keys/values
        st.dictionaries(
            keys=st.text(max_size=20),
            values=st.one_of(
                st.none(),
                st.booleans(),
                st.integers(),
                st.floats(allow_nan=False),
                st.text(max_size=100),
                st.lists(st.text(max_size=20), max_size=5),
            ),
            max_size=15,
        ),
        # Valid-ish dicts that may or may not pass
        valid_hackathon_dict_strategy(),
        # Invalid dicts
        invalid_hackathon_dict_strategy(),
        # Edge cases: empty dict, None-heavy dict
        st.just({}),
        st.just({"title": None, "platform": None, "registration_url": None}),
    ))
    @settings(max_examples=300)
    def test_validate_hackathon_never_raises(self, data):
        """validate_hackathon never raises exceptions regardless of input.

        **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5**

        No matter what dict is passed in, the function should return
        either a Hackathon instance or None, never raise an exception.
        """
        try:
            result = validate_hackathon(data)
        except Exception as e:
            raise AssertionError(
                f"validate_hackathon raised {type(e).__name__}: {e} "
                f"for input {data}"
            )

        # Result must be either a Hackathon instance or None
        assert result is None or isinstance(result, Hackathon), (
            f"Expected Hackathon or None, got {type(result)}: {result}"
        )
