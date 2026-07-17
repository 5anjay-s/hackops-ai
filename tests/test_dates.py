"""Unit tests for the date normalization utility."""

import pytest
from utils.dates import normalize_date


class TestNormalizeDateNoneAndEmpty:
    """Tests for None, empty, and whitespace-only inputs."""

    def test_none_input(self):
        assert normalize_date(None) is None

    def test_empty_string(self):
        assert normalize_date("") is None

    def test_whitespace_only(self):
        assert normalize_date("   ") is None

    def test_tab_only(self):
        assert normalize_date("\t") is None

    def test_newline_only(self):
        assert normalize_date("\n") is None


class TestNormalizeDateISO:
    """Tests for ISO 8601 format inputs."""

    def test_iso_date_only(self):
        assert normalize_date("2025-03-15") == "2025-03-15"

    def test_iso_with_time(self):
        assert normalize_date("2025-03-15T23:59:59") == "2025-03-15"

    def test_iso_with_time_and_z(self):
        assert normalize_date("2025-03-15T23:59:59Z") == "2025-03-15"

    def test_iso_with_leading_whitespace(self):
        assert normalize_date("  2025-01-01") == "2025-01-01"

    def test_iso_with_trailing_whitespace(self):
        assert normalize_date("2025-12-31  ") == "2025-12-31"


class TestNormalizeDateMonthNames:
    """Tests for month-name format inputs."""

    def test_full_month_us_format(self):
        assert normalize_date("March 15, 2025") == "2025-03-15"

    def test_full_month_eu_format(self):
        assert normalize_date("15 March 2025") == "2025-03-15"

    def test_abbreviated_month_us_format(self):
        assert normalize_date("Mar 15, 2025") == "2025-03-15"

    def test_abbreviated_month_eu_format(self):
        assert normalize_date("15 Mar 2025") == "2025-03-15"

    def test_full_month_january(self):
        assert normalize_date("January 1, 2025") == "2025-01-01"

    def test_full_month_december(self):
        assert normalize_date("31 December 2025") == "2025-12-31"


class TestNormalizeDateNumeric:
    """Tests for numeric date formats."""

    def test_us_numeric(self):
        assert normalize_date("03/15/2025") == "2025-03-15"

    def test_eu_numeric(self):
        # Note: 15/03/2025 can only be EU format since 15 > 12
        assert normalize_date("15/03/2025") == "2025-03-15"

    def test_ambiguous_numeric_us_first(self):
        # 01/02/2025 is ambiguous - US format tried first gives Jan 2
        assert normalize_date("01/02/2025") == "2025-01-02"


class TestNormalizeDateRanges:
    """Tests for date range handling."""

    def test_dash_separator(self):
        assert normalize_date("2025-01-01 - 2025-03-15") == "2025-03-15"

    def test_to_separator(self):
        assert normalize_date("2025-01-01 to 2025-03-15") == "2025-03-15"

    def test_range_with_month_names(self):
        assert normalize_date("January 1, 2025 - March 15, 2025") == "2025-03-15"

    def test_range_with_to_keyword(self):
        assert normalize_date("Jan 1, 2025 to Mar 15, 2025") == "2025-03-15"


class TestNormalizeDateUnparseable:
    """Tests for unparseable inputs."""

    def test_random_text(self):
        assert normalize_date("invalid") is None

    def test_partial_date(self):
        assert normalize_date("March 2025") is None

    def test_number_only(self):
        assert normalize_date("12345") is None

    def test_two_digit_year(self):
        assert normalize_date("03/15/25") is None

    def test_special_characters(self):
        assert normalize_date("@#$%") is None
