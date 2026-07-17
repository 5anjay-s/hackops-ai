"""Property-based tests for date normalization utility.

**Validates: Requirements 4.1, 4.3, 4.4, 4.5**

Property 2: Date normalization correctness
- For any random string input, normalize_date always returns either None or a valid YYYY-MM-DD string
- For known valid date format strings, normalize_date returns the expected parsed date
- normalize_date never fabricates dates (output is always derivable from input)
"""

import re
from datetime import datetime

from hypothesis import given, assume, settings
from hypothesis import strategies as st

from utils.dates import normalize_date, KNOWN_FORMATS


# Regex pattern for a valid ISO 8601 date (YYYY-MM-DD)
ISO_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class TestDateNormalizationOutputValidity:
    """Property: normalize_date always returns None or a valid YYYY-MM-DD string."""

    @given(st.text())
    @settings(max_examples=200)
    def test_output_is_none_or_valid_iso_date(self, raw_input: str):
        """**Validates: Requirements 4.1, 4.3**

        For any arbitrary text input, normalize_date must return either:
        - None (unparseable input)
        - A string matching the YYYY-MM-DD format that represents a real calendar date
        """
        result = normalize_date(raw_input)

        if result is not None:
            # Must match YYYY-MM-DD pattern
            assert ISO_DATE_PATTERN.match(result), (
                f"Output '{result}' does not match YYYY-MM-DD pattern"
            )
            # Must be a real calendar date (not e.g. 2025-13-45)
            try:
                datetime.strptime(result, "%Y-%m-%d")
            except ValueError:
                raise AssertionError(
                    f"Output '{result}' matches pattern but is not a valid calendar date"
                )

    @given(st.none())
    def test_none_input_returns_none(self, raw_input):
        """**Validates: Requirements 4.3**

        None input must always produce None output.
        """
        assert normalize_date(raw_input) is None

    @given(st.from_regex(r"^\s+$", fullmatch=True))
    @settings(max_examples=50)
    def test_whitespace_only_returns_none(self, raw_input: str):
        """**Validates: Requirements 4.3**

        Whitespace-only strings must always produce None output.
        """
        assert normalize_date(raw_input) is None


class TestDateNormalizationKnownFormats:
    """Property: Known valid date format strings are correctly parsed."""

    @given(
        st.dates(
            min_value=datetime(1900, 1, 1).date(),
            max_value=datetime(2099, 12, 31).date(),
        )
    )
    @settings(max_examples=200)
    def test_iso_date_format_parsed_correctly(self, d):
        """**Validates: Requirements 4.1, 4.5**

        Any valid date formatted as YYYY-MM-DD must be parsed back to itself.
        """
        raw = d.strftime("%Y-%m-%d")
        result = normalize_date(raw)
        assert result == raw

    @given(
        st.dates(
            min_value=datetime(1900, 1, 1).date(),
            max_value=datetime(2099, 12, 31).date(),
        ),
        st.integers(min_value=0, max_value=23),
        st.integers(min_value=0, max_value=59),
        st.integers(min_value=0, max_value=59),
    )
    @settings(max_examples=200)
    def test_iso_datetime_with_z_parsed_correctly(self, d, hour, minute, second):
        """**Validates: Requirements 4.1, 4.5**

        Any valid ISO 8601 datetime with Z suffix must parse to the date portion.
        """
        raw = f"{d.strftime('%Y-%m-%d')}T{hour:02d}:{minute:02d}:{second:02d}Z"
        result = normalize_date(raw)
        assert result == d.strftime("%Y-%m-%d")

    @given(
        st.dates(
            min_value=datetime(1900, 1, 1).date(),
            max_value=datetime(2099, 12, 31).date(),
        )
    )
    @settings(max_examples=200)
    def test_full_month_name_us_format_parsed(self, d):
        """**Validates: Requirements 4.1, 4.5**

        Dates formatted as 'Month Day, Year' must parse correctly.
        """
        raw = d.strftime("%B %d, %Y")
        result = normalize_date(raw)
        assert result == d.strftime("%Y-%m-%d")

    @given(
        st.dates(
            min_value=datetime(1900, 1, 1).date(),
            max_value=datetime(2099, 12, 31).date(),
        )
    )
    @settings(max_examples=200)
    def test_abbreviated_month_us_format_parsed(self, d):
        """**Validates: Requirements 4.1, 4.5**

        Dates formatted as 'Mon Day, Year' (abbreviated) must parse correctly.
        """
        raw = d.strftime("%b %d, %Y")
        result = normalize_date(raw)
        assert result == d.strftime("%Y-%m-%d")

    @given(
        st.dates(
            min_value=datetime(1900, 1, 1).date(),
            max_value=datetime(2099, 12, 31).date(),
        )
    )
    @settings(max_examples=200)
    def test_day_first_full_month_format_parsed(self, d):
        """**Validates: Requirements 4.1, 4.5**

        Dates formatted as 'Day Month Year' must parse correctly.
        """
        raw = d.strftime("%d %B %Y")
        result = normalize_date(raw)
        assert result == d.strftime("%Y-%m-%d")


class TestDateNormalizationNoFabrication:
    """Property: normalize_date never fabricates dates not derivable from input."""

    @given(
        st.dates(
            min_value=datetime(1900, 1, 1).date(),
            max_value=datetime(2099, 12, 31).date(),
        ),
        st.dates(
            min_value=datetime(1900, 1, 1).date(),
            max_value=datetime(2099, 12, 31).date(),
        ),
    )
    @settings(max_examples=200)
    def test_date_range_returns_end_date(self, start_date, end_date):
        """**Validates: Requirements 4.4, 4.5**

        For date ranges with ' - ' separator, the END date is returned.
        """
        raw = f"{start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}"
        result = normalize_date(raw)
        assert result == end_date.strftime("%Y-%m-%d")

    @given(
        st.dates(
            min_value=datetime(1900, 1, 1).date(),
            max_value=datetime(2099, 12, 31).date(),
        ),
        st.dates(
            min_value=datetime(1900, 1, 1).date(),
            max_value=datetime(2099, 12, 31).date(),
        ),
    )
    @settings(max_examples=200)
    def test_date_range_to_separator_returns_end_date(self, start_date, end_date):
        """**Validates: Requirements 4.4, 4.5**

        For date ranges with ' to ' separator, the END date is returned.
        """
        raw = f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"
        result = normalize_date(raw)
        assert result == end_date.strftime("%Y-%m-%d")

    @given(st.text())
    @settings(max_examples=200)
    def test_output_date_components_present_in_input(self, raw_input: str):
        """**Validates: Requirements 4.4**

        If normalize_date returns a date, its year, month, or day components
        must be derivable from the input string (no fabrication).
        The output date's numeric components should appear somewhere in the input.
        """
        result = normalize_date(raw_input)

        if result is not None:
            # Parse the output date
            dt = datetime.strptime(result, "%Y-%m-%d")
            year_str = str(dt.year)
            # At minimum, the year must be present in the input
            # (since all supported formats include a 4-digit year)
            assert year_str in raw_input, (
                f"Output year {year_str} not found in input '{raw_input}' — "
                f"possible date fabrication"
            )
