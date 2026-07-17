"""Date normalization utility for HackOps AI.

Normalizes raw date strings from various platform formats into ISO 8601 (YYYY-MM-DD).
"""

from datetime import datetime
from typing import Optional


# Supported date formats in order of attempted parsing
KNOWN_FORMATS = [
    "%Y-%m-%dT%H:%M:%S",   # ISO with time (2025-03-15T23:59:59)
    "%Y-%m-%dT%H:%M:%SZ",  # ISO with Z (2025-03-15T23:59:59Z)
    "%Y-%m-%d",             # ISO date only (2025-03-15)
    "%b %d, %Y",            # Abbreviated month (Jan 15, 2025)
    "%B %d, %Y",            # Full month (January 15, 2025)
    "%d %b %Y",             # Day first abbreviated (15 Jan 2025)
    "%d %B %Y",             # Day first full (15 January 2025)
    "%m/%d/%Y",             # US numeric (01/15/2025)
    "%d/%m/%Y",             # EU numeric (15/01/2025)
]

# Separators indicating a date range
_RANGE_SEPARATORS = [" - ", " to "]


def normalize_date(raw_date: Optional[str]) -> Optional[str]:
    """Normalize a raw date string to ISO 8601 format (YYYY-MM-DD).

    Supported formats:
    - ISO 8601 with time component (e.g., "2025-03-15T23:59:59Z")
    - Full month-name formats (e.g., "March 15, 2025", "15 March 2025")
    - Abbreviated month-name formats (e.g., "Mar 15, 2025")
    - Numeric formats with four-digit year (e.g., "2025-03-15", "03/15/2025", "15/03/2025")

    Date range handling:
    - If the raw date string contains " - " or " to ", parse and return the END date.

    Returns None for: None, empty, whitespace-only, or unparseable inputs.
    Never fabricates a date.

    Args:
        raw_date: A date string in one of the supported formats, or None.

    Returns:
        An ISO 8601 date string (YYYY-MM-DD) or None if the input cannot be parsed.
    """
    if raw_date is None:
        return None

    if not raw_date.strip():
        return None

    cleaned = raw_date.strip()

    # Handle date ranges by extracting the end date
    for sep in _RANGE_SEPARATORS:
        if sep in cleaned:
            parts = cleaned.split(sep)
            # Use the last part (end date)
            cleaned = parts[-1].strip()
            break

    # Try each known format
    for fmt in KNOWN_FORMATS:
        try:
            dt = datetime.strptime(cleaned, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    # Unparseable — return None, never fabricate
    return None
