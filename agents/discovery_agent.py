"""Discovery Agent for HackOps AI.

Discovers hackathons from multiple platforms (Devpost, Devfolio, Unstop).
Visits individual detail pages for complete data extraction.
Normalizes all data into Hackathon dataclass instances.

This module provides the framework and entry point. Platform-specific scraping
logic is implemented in tasks 2.2, 2.4, 2.5.
"""

import re
import time
from typing import Optional

import requests
from bs4 import BeautifulSoup

from models.hackathon import Hackathon
from utils.dates import normalize_date
from utils.validation import validate_hackathon


# Minimum delay between consecutive requests to the same platform (seconds)
REQUEST_DELAY: float = 1.0

# HTTP request timeout (seconds)
REQUEST_TIMEOUT: int = 15

# Valid range for max_pages parameter
_MIN_PAGES: int = 1
_MAX_PAGES: int = 10
_DEFAULT_PAGES: int = 3

# Common HTTP headers for scraping
HEADERS: dict = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/json",
}

# Module-level last-request timestamps per platform for delay enforcement
_last_request_time: dict[str, float] = {
    "Devpost": 0.0,
    "Devfolio": 0.0,
    "Unstop": 0.0,
}


def _enforce_delay(platform: str) -> None:
    """Enforce minimum delay between requests to the same platform.

    Sleeps if less than REQUEST_DELAY seconds have elapsed since the
    last request to the given platform.

    Args:
        platform: One of "Devpost", "Devfolio", "Unstop".
    """
    now = time.time()
    elapsed = now - _last_request_time.get(platform, 0.0)
    if elapsed < REQUEST_DELAY:
        time.sleep(REQUEST_DELAY - elapsed)
    _last_request_time[platform] = time.time()


def _clamp_max_pages(max_pages: int) -> int:
    """Validate and clamp max_pages to the allowed range [1, 10].

    Args:
        max_pages: Requested number of pages.

    Returns:
        Clamped value within [_MIN_PAGES, _MAX_PAGES].
    """
    if not isinstance(max_pages, int) or max_pages < _MIN_PAGES:
        return _DEFAULT_PAGES
    if max_pages > _MAX_PAGES:
        return _MAX_PAGES
    return max_pages


def discover_all(max_pages: int = 3) -> list[Hackathon]:
    """Discover hackathons from all supported platforms.

    Calls each platform scraper, catches exceptions per platform,
    and combines results. Returns an empty list if all platforms fail.

    Args:
        max_pages: Maximum number of listing pages to fetch per platform (1-10).

    Returns:
        Combined list of validated Hackathon objects from all platforms.
        Never raises an exception.
    """
    max_pages = _clamp_max_pages(max_pages)
    all_hackathons: list[Hackathon] = []

    # Platform scrapers with their names for error reporting
    platform_scrapers = [
        ("Devpost", discover_devpost),
        ("Devfolio", discover_devfolio),
        ("Unstop", discover_unstop),
    ]

    for platform_name, scraper_fn in platform_scrapers:
        try:
            results = scraper_fn(max_pages=max_pages)
            all_hackathons.extend(results)
        except Exception as e:
            print(f"  [Discovery] Platform {platform_name} failed: {e}")
            continue

    # Deduplicate by registration_url
    seen_urls: set[str] = set()
    unique: list[Hackathon] = []
    for hackathon in all_hackathons:
        if hackathon.registration_url not in seen_urls:
            seen_urls.add(hackathon.registration_url)
            unique.append(hackathon)

    print(f"  [Discovery] Total: {len(unique)} unique hackathons from all platforms")
    return unique


def _extract_hackathon_details(url: str, platform: str, retry: bool = True) -> dict:
    """Fetch a hackathon detail page and extract metadata with retry logic.

    On failure, retries once after 2 seconds. On second failure, returns
    partial data with None for all fields.

    Args:
        url: URL of the hackathon detail page.
        platform: Platform name for delay enforcement.
        retry: Whether to retry on failure (set to False on retry attempt).

    Returns:
        Dict with keys: registration_deadline, submission_deadline, prize,
        themes, team_size, organizer, mode, location. Missing fields are None.
    """
    empty = {
        "registration_deadline": None,
        "submission_deadline": None,
        "prize": None,
        "themes": [],
        "team_size": None,
        "organizer": None,
        "mode": None,
        "location": None,
    }

    try:
        _enforce_delay(platform)
        html_headers = {**HEADERS, "Accept": "text/html,application/xhtml+xml"}
        resp = requests.get(url, headers=html_headers, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return _parse_detail_html(resp.text)
    except (requests.RequestException, Exception) as e:
        print(f"  [{platform}] Detail fetch failed for {url}: {e}")
        if retry:
            time.sleep(2)
            return _extract_hackathon_details(url, platform, retry=False)
        return empty


def _parse_detail_html(html: str) -> dict:
    """Parse hackathon detail page HTML and extract metadata.

    Args:
        html: Raw HTML content of the detail page.

    Returns:
        Dict with extracted metadata fields.
    """
    soup = BeautifulSoup(html, "html.parser")

    info: dict = {
        "registration_deadline": None,
        "submission_deadline": None,
        "prize": None,
        "themes": [],
        "team_size": None,
        "organizer": None,
        "mode": None,
        "location": None,
    }

    # --- Deadlines ---
    time_tags = soup.find_all("time")
    dates_found = []
    for t in time_tags:
        dt = t.get("datetime", "")
        if dt:
            dates_found.append(dt)

    if dates_found:
        # Usually last date is submission deadline
        info["submission_deadline"] = normalize_date(dates_found[-1])
        if len(dates_found) >= 2:
            info["registration_deadline"] = normalize_date(dates_found[0])

    # Look for deadline in sidebar/rules section
    for label_el in soup.find_all(["strong", "b", "span", "h4", "h5"]):
        label_text = label_el.get_text(strip=True).lower()
        if "registration" in label_text and "deadline" in label_text:
            sibling = label_el.find_next_sibling()
            if sibling:
                parsed = normalize_date(sibling.get_text(strip=True))
                if parsed:
                    info["registration_deadline"] = parsed
        elif "submission" in label_text and "deadline" in label_text:
            sibling = label_el.find_next_sibling()
            if sibling:
                parsed = normalize_date(sibling.get_text(strip=True))
                if parsed:
                    info["submission_deadline"] = parsed

    # --- Prize ---
    prize_el = soup.find(class_="prize-amount") or soup.find(class_="total-prize")
    if prize_el:
        info["prize"] = prize_el.get_text(strip=True)[:200]

    if not info["prize"]:
        prizes_section = soup.find(id="prizes")
        if prizes_section:
            header = prizes_section.find(["h2", "h3", "strong"])
            if header:
                text = header.get_text(strip=True)
                if "$" in text or "prize" in text.lower():
                    info["prize"] = text[:200]

    if not info["prize"]:
        body_text = soup.get_text(" ", strip=True)
        match = re.search(r'\$[\d,]+(?:\s*(?:in\s+prizes|total))?', body_text)
        if match:
            info["prize"] = match.group(0)[:200]

    # --- Team Size ---
    rules_section = soup.find(id="rules") or soup.find(class_="rules")
    if rules_section:
        for el in rules_section.find_all(["p", "li"]):
            text = el.get_text(strip=True).lower()
            if "team" in text and ("member" in text or "size" in text or "person" in text or "people" in text):
                info["team_size"] = el.get_text(strip=True)[:100]
                break

    if not info["team_size"]:
        main = soup.find("main") or soup.find(id="content") or soup.find(class_="content")
        if main:
            for el in main.find_all(["p", "li", "span"]):
                text = el.get_text(strip=True).lower()
                if "team" in text and ("member" in text or "size" in text or "person" in text):
                    info["team_size"] = el.get_text(strip=True)[:100]
                    break

    # --- Themes ---
    theme_els = soup.find_all(class_="tag") or soup.find_all(class_="theme")
    for t in theme_els:
        txt = t.get_text(strip=True)
        if txt and txt not in info["themes"]:
            info["themes"].append(txt)

    if not info["themes"]:
        tags_section = soup.find(class_="software") or soup.find(class_="tags")
        if tags_section:
            for tag in tags_section.find_all(["a", "span", "li"]):
                txt = tag.get_text(strip=True)
                if txt and txt not in info["themes"]:
                    info["themes"].append(txt)

    # Truncate themes to max 20 items
    info["themes"] = info["themes"][:20]

    # --- Organizer ---
    org_el = (
        soup.find(class_="host")
        or soup.find(class_="organizer")
        or soup.find(class_="hosted-by")
    )
    if org_el:
        info["organizer"] = org_el.get_text(strip=True) or None

    if not info["organizer"]:
        managed = soup.find(string=lambda s: s and "Managed by" in s)
        if managed:
            parent = managed.find_parent()
            if parent:
                org_text = parent.get_text(strip=True).replace("Managed by", "").strip()
                info["organizer"] = org_text or None

    # --- Mode (online/offline/hybrid) ---
    info["mode"] = _extract_mode(soup)

    # --- Location ---
    info["location"] = _extract_location(soup)

    return info


def _extract_mode(soup: BeautifulSoup) -> Optional[str]:
    """Extract hackathon mode (online/offline/hybrid) from detail page.

    Args:
        soup: Parsed BeautifulSoup of the detail page.

    Returns:
        "online", "offline", "hybrid", or None if not determinable.
    """
    body_text = soup.get_text(" ", strip=True).lower()

    # Check for hybrid first (it often includes both "online" and "in-person")
    if "hybrid" in body_text:
        return "hybrid"
    # Check for explicit markers
    if "in-person" in body_text or "in person" in body_text or "offline" in body_text:
        if "online" in body_text or "virtual" in body_text:
            return "hybrid"
        return "offline"
    if "online" in body_text or "virtual" in body_text:
        return "online"

    return None


def _extract_location(soup: BeautifulSoup) -> Optional[str]:
    """Extract hackathon location from detail page.

    Args:
        soup: Parsed BeautifulSoup of the detail page.

    Returns:
        Location string or None if not found.
    """
    # Look for location-specific elements
    loc_el = (
        soup.find(class_="location")
        or soup.find(class_="venue")
        or soup.find(id="location")
    )
    if loc_el:
        text = loc_el.get_text(strip=True)
        if text:
            return text

    # Look for address or location in meta tags
    meta_loc = soup.find("meta", attrs={"name": "location"})
    if meta_loc and meta_loc.get("content"):
        return meta_loc["content"]

    # Look for location labels
    for label_el in soup.find_all(["strong", "b", "span", "h4", "h5"]):
        label_text = label_el.get_text(strip=True).lower()
        if "location" in label_text or "venue" in label_text:
            sibling = label_el.find_next_sibling()
            if sibling:
                text = sibling.get_text(strip=True)
                if text:
                    return text

    return None


def _fetch_devpost_listings(page: int = 1) -> list[dict]:
    """Fetch hackathon listings from the Devpost JSON API.

    Args:
        page: Page number to fetch.

    Returns:
        List of dicts with 'title' and 'url' keys, or empty list on failure.
    """
    _enforce_delay("Devpost")
    params = {"page": page, "status[]": "open", "order_by": "deadline-asc"}
    try:
        resp = requests.get(
            "https://devpost.com/api/hackathons",
            headers=HEADERS,
            params=params,
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as e:
        print(f"  [Devpost] API request failed (page {page}): {e}")
        return []

    results = []
    for item in data.get("hackathons", []):
        title = item.get("title", "").strip()
        url = item.get("url", "").strip()
        if title and url:
            results.append({"title": title, "url": url})

    return results


def _extract_devpost_detail(url: str) -> dict:
    """Extract detailed metadata from a Devpost hackathon detail page.

    Delegates to _extract_hackathon_details with platform="Devpost".

    Args:
        url: URL of the Devpost hackathon detail page.

    Returns:
        Dict with extracted metadata fields.
    """
    return _extract_hackathon_details(url, platform="Devpost")


def discover_devpost(max_pages: int = 3) -> list[Hackathon]:
    """Discover hackathons from Devpost.

    Fetches listing pages from the Devpost API and visits detail pages
    for complete metadata extraction.

    Args:
        max_pages: Maximum number of listing pages to fetch (1-10).

    Returns:
        List of validated Hackathon objects from Devpost.
    """
    max_pages = _clamp_max_pages(max_pages)
    all_listings: list[dict] = []

    for page in range(1, max_pages + 1):
        print(f"  [Devpost] Fetching listing page {page}...")
        listings = _fetch_devpost_listings(page=page)
        if not listings:
            break
        all_listings.extend(listings)

    # Deduplicate by URL
    seen: set[str] = set()
    unique: list[dict] = []
    for h in all_listings:
        if h["url"] not in seen:
            seen.add(h["url"])
            unique.append(h)

    print(f"  [Devpost] Found {len(unique)} hackathons, fetching details...")

    results: list[Hackathon] = []
    for i, listing in enumerate(unique, 1):
        print(f"  [Devpost] ({i}/{len(unique)}) {listing['title'][:50]}...")
        detail = _extract_devpost_detail(listing["url"])

        # Build raw data dict for validation
        raw_data = {
            "title": listing["title"],
            "platform": "Devpost",
            "registration_url": listing["url"],
            "registration_deadline": detail["registration_deadline"],
            "submission_deadline": detail["submission_deadline"],
            "prize": detail["prize"],
            "team_size": detail["team_size"],
            "themes": detail["themes"],
            "organizer": detail["organizer"],
            "mode": detail["mode"],
            "location": detail["location"],
        }

        hackathon = validate_hackathon(raw_data)
        if hackathon:
            results.append(hackathon)
        else:
            print(f"  [Devpost] Validation failed for: {listing['title'][:50]}")

    print(f"  [Devpost] Returning {len(results)} validated hackathons")
    return results


def discover_devfolio(max_pages: int = 3) -> list[Hackathon]:
    """Discover hackathons from Devfolio.

    Fetches hackathon listings from the Devfolio API and extracts
    metadata from detail pages.

    Args:
        max_pages: Maximum number of listing pages to fetch (1-10).

    Returns:
        List of validated Hackathon objects from Devfolio.
    """
    max_pages = _clamp_max_pages(max_pages)
    hackathons: list[Hackathon] = []

    try:
        listings = _fetch_devfolio_listings(max_pages)
    except Exception as e:
        print(f"  [Devfolio] Failed to fetch listings: {e}")
        return []

    for listing in listings:
        try:
            detail = _extract_devfolio_detail(listing)
            validated = validate_hackathon(detail)
            if validated is not None:
                hackathons.append(validated)
        except Exception as e:
            print(f"  [Devfolio] Skipping entry: {e}")
            continue

    print(f"  [Devfolio] Discovered {len(hackathons)} hackathons")
    return hackathons


def _fetch_devfolio_listings(max_pages: int) -> list[dict]:
    """Fetch hackathon listings from the Devfolio search API.

    Uses Devfolio's POST API to search for open hackathons, paginating
    through results up to max_pages.

    Args:
        max_pages: Maximum number of pages to fetch (each page has 15 results).

    Returns:
        List of raw listing dicts with at minimum 'name' and 'slug' fields.

    Raises:
        requests.RequestException: If the API is unreachable after retries.
    """
    api_url = "https://api.devfolio.co/api/search/hackathons"
    page_size = 15
    all_listings: list[dict] = []

    for page in range(max_pages):
        offset = page * page_size
        payload = {
            "type": "hackathon",
            "q": "",
            "filter": {"status": ["open"]},
            "from": offset,
            "size": page_size,
        }

        _enforce_delay("Devfolio")

        try:
            response = requests.post(
                api_url,
                json=payload,
                headers={**HEADERS, "Content-Type": "application/json"},
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
        except requests.RequestException as e:
            # Retry once after delay
            print(f"  [Devfolio] Page {page + 1} fetch failed, retrying: {e}")
            _enforce_delay("Devfolio")
            try:
                response = requests.post(
                    api_url,
                    json=payload,
                    headers={**HEADERS, "Content-Type": "application/json"},
                    timeout=REQUEST_TIMEOUT,
                )
                response.raise_for_status()
            except requests.RequestException as retry_e:
                print(f"  [Devfolio] Page {page + 1} retry failed: {retry_e}")
                break

        try:
            data = response.json()
        except (ValueError, AttributeError):
            print(f"  [Devfolio] Invalid JSON response on page {page + 1}")
            break

        # Extract hackathon hits from the response
        hits = data.get("hits", {}).get("hits", [])
        if not hits:
            break

        for hit in hits:
            source = hit.get("_source", {})
            if source.get("name") and source.get("slug"):
                all_listings.append(source)

        # Stop early if fewer results than page_size (last page)
        if len(hits) < page_size:
            break

    return all_listings


def _extract_devfolio_detail(listing: dict) -> dict:
    """Extract hackathon detail from a Devfolio listing and its detail page.

    Combines data available in the API listing response with additional
    data scraped from the detail page HTML.

    Args:
        listing: Raw listing dict from the Devfolio API response.

    Returns:
        Normalized dict ready for validate_hackathon().
    """
    slug = listing.get("slug", "")
    name = listing.get("name", "")
    registration_url = f"https://devfolio.co/hackathons/{slug}" if slug else ""

    # Extract data available from the API response directly
    reg_starts = listing.get("reg_starts")
    reg_ends = listing.get("reg_ends")
    hackathon_starts = listing.get("hackathon_starts")
    hackathon_ends = listing.get("hackathon_ends")

    # Use reg_ends as registration deadline, hackathon_ends as submission deadline
    registration_deadline = normalize_date(reg_ends)
    submission_deadline = normalize_date(hackathon_ends)

    # Extract prize from API if available
    prize_raw = listing.get("prize_amount")
    prize_currency = listing.get("prize_currency", "USD")
    prize = None
    if prize_raw is not None:
        try:
            prize_val = int(prize_raw)
            if prize_val > 0:
                prize = f"{prize_currency} {prize_val:,}"
        except (ValueError, TypeError):
            prize = str(prize_raw) if prize_raw else None

    # Extract themes/tags from API
    themes_raw = listing.get("themes", []) or []
    if not isinstance(themes_raw, list):
        themes_raw = []
    themes = [str(t).strip() for t in themes_raw if t and str(t).strip()]

    # Extract mode
    is_online = listing.get("is_online", False)
    mode = "online" if is_online else None

    # Extract organizer from API
    organizer = None
    org_data = listing.get("organisation")
    if isinstance(org_data, dict):
        organizer = org_data.get("name")
    elif isinstance(org_data, str) and org_data.strip():
        organizer = org_data.strip()

    # Extract team size
    team_size_min = listing.get("team_min")
    team_size_max = listing.get("team_max")
    team_size = None
    if team_size_min is not None and team_size_max is not None:
        try:
            ts_min = int(team_size_min)
            ts_max = int(team_size_max)
            if ts_min == ts_max:
                team_size = str(ts_min)
            else:
                team_size = f"{ts_min}-{ts_max}"
        except (ValueError, TypeError):
            pass

    # Extract location
    location = listing.get("location")
    if isinstance(location, str) and location.strip():
        location = location.strip()
    else:
        location = None

    # Visit detail page for additional metadata if needed
    if registration_url and (not themes or not prize or not organizer):
        page_detail = _fetch_devfolio_detail_page(registration_url)
        if not themes and page_detail.get("themes"):
            themes = page_detail["themes"]
        if not prize and page_detail.get("prize"):
            prize = page_detail["prize"]
        if not organizer and page_detail.get("organizer"):
            organizer = page_detail["organizer"]
        if not mode and page_detail.get("mode"):
            mode = page_detail["mode"]
        if not location and page_detail.get("location"):
            location = page_detail["location"]

    # Apply truncation limits
    if prize and len(prize) > 200:
        prize = prize[:200]
    if themes and len(themes) > 20:
        themes = themes[:20]
    if team_size and len(team_size) > 100:
        team_size = team_size[:100]

    return {
        "title": name,
        "platform": "Devfolio",
        "registration_url": registration_url,
        "registration_deadline": registration_deadline,
        "submission_deadline": submission_deadline,
        "organizer": organizer,
        "themes": themes,
        "mode": mode,
        "location": location,
        "prize": prize,
        "team_size": team_size,
    }


def _fetch_devfolio_detail_page(url: str, retry: bool = True) -> dict:
    """Fetch and parse a Devfolio hackathon detail page for additional metadata.

    Args:
        url: Full URL of the hackathon detail page.
        retry: Whether to retry on failure (used internally for recursion).

    Returns:
        Dict with optional keys: themes, prize, organizer, mode, location.
        Returns empty dict on failure.
    """
    _enforce_delay("Devfolio")

    try:
        response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as e:
        if retry:
            print(f"  [Devfolio] Detail page fetch failed, retrying: {e}")
            time.sleep(REQUEST_DELAY)
            return _fetch_devfolio_detail_page(url, retry=False)
        return {}

    result: dict = {}
    try:
        soup = BeautifulSoup(response.text, "html.parser")

        # Extract themes from page
        theme_elements = soup.find_all("span", class_=re.compile(r"tag|theme|chip", re.I))
        if theme_elements:
            themes = [el.get_text(strip=True) for el in theme_elements if el.get_text(strip=True)]
            if themes:
                result["themes"] = themes[:20]

        # Extract prize information
        prize_section = soup.find(string=re.compile(r"prize|reward", re.I))
        if prize_section:
            parent = prize_section.find_parent()
            if parent:
                prize_text = parent.get_text(strip=True)
                if prize_text and len(prize_text) <= 200:
                    result["prize"] = prize_text

        # Extract organizer
        org_section = soup.find(string=re.compile(r"organiz|hosted by", re.I))
        if org_section:
            parent = org_section.find_parent()
            if parent:
                org_text = parent.get_text(strip=True)
                if org_text and len(org_text) <= 200:
                    result["organizer"] = org_text

        # Extract mode (online/offline/hybrid)
        mode_section = soup.find(string=re.compile(r"\b(online|offline|hybrid)\b", re.I))
        if mode_section:
            mode_text = mode_section.strip().lower()
            if "hybrid" in mode_text:
                result["mode"] = "hybrid"
            elif "offline" in mode_text:
                result["mode"] = "offline"
            elif "online" in mode_text:
                result["mode"] = "online"

        # Extract location
        location_section = soup.find(string=re.compile(r"location|venue|city", re.I))
        if location_section:
            parent = location_section.find_parent()
            if parent:
                loc_text = parent.get_text(strip=True)
                if loc_text and len(loc_text) <= 200:
                    result["location"] = loc_text

    except Exception as e:
        print(f"  [Devfolio] Error parsing detail page: {e}")

    return result


def discover_unstop(max_pages: int = 3) -> list[Hackathon]:
    """Discover hackathons from Unstop.

    Fetches hackathon listings from the Unstop API and extracts
    metadata from detail pages for complete information.

    Args:
        max_pages: Maximum number of listing pages to fetch (1-10).

    Returns:
        List of validated Hackathon objects from Unstop.
    """
    max_pages = _clamp_max_pages(max_pages)
    hackathons: list[Hackathon] = []

    for page in range(1, max_pages + 1):
        print(f"  [Unstop] Fetching page {page}...")
        listings = _fetch_unstop_listings(page)
        if not listings:
            break

        for listing in listings:
            try:
                public_url = listing.get("public_url", "")
                if not public_url:
                    continue

                registration_url = f"https://unstop.com/{public_url}"

                # Visit detail page for complete metadata
                detail = _extract_unstop_detail(registration_url)

                # Extract basic info from listing API response
                title = (listing.get("title") or "").strip()
                if not title:
                    continue

                # Organization from listing
                organizer = None
                org_data = listing.get("organisation")
                if isinstance(org_data, dict):
                    org_name = (org_data.get("name") or "").strip()
                    if org_name:
                        organizer = org_name

                # Themes/tags from listing
                themes = _extract_unstop_themes(listing.get("tags", []))

                # Deadlines — prefer detail page, fall back to listing
                reg_deadline_raw = detail.get("registration_deadline") or listing.get("regnRequirements", {}).get("end_regn_dt")
                sub_deadline_raw = detail.get("submission_deadline") or listing.get("end_date")

                registration_deadline = normalize_date(reg_deadline_raw)
                submission_deadline = normalize_date(sub_deadline_raw)

                # Mode and location from detail page
                mode = detail.get("mode")
                location = detail.get("location")

                # Prize from detail page or listing
                prize = detail.get("prize") or _extract_unstop_prize_from_listing(listing)
                if prize and len(prize) > 200:
                    prize = prize[:200]

                # Team size from detail page or listing
                team_size = detail.get("team_size") or _extract_unstop_team_size_from_listing(listing)
                if team_size and len(team_size) > 100:
                    team_size = team_size[:100]

                # Truncate themes to max 20 items
                if len(themes) > 20:
                    themes = themes[:20]

                # Use detail page organizer if listing didn't have one
                if not organizer and detail.get("organizer"):
                    organizer = detail["organizer"]

                # Build data dict for validation
                hackathon_data = {
                    "title": title,
                    "platform": "Unstop",
                    "registration_url": registration_url,
                    "registration_deadline": registration_deadline,
                    "submission_deadline": submission_deadline,
                    "organizer": organizer,
                    "themes": themes,
                    "mode": mode,
                    "location": location,
                    "prize": prize,
                    "team_size": team_size,
                }

                validated = validate_hackathon(hackathon_data)
                if validated:
                    hackathons.append(validated)

            except Exception as e:
                print(f"  [Unstop] Failed to process listing: {e}")
                continue

    # Deduplicate by URL
    seen_urls: set[str] = set()
    unique: list[Hackathon] = []
    for h in hackathons:
        if h.registration_url not in seen_urls:
            seen_urls.add(h.registration_url)
            unique.append(h)

    print(f"  [Unstop] Found {len(unique)} hackathons")
    return unique


# ---------------------------------------------------------------------------
# Unstop helper functions
# ---------------------------------------------------------------------------

_UNSTOP_API_URL = "https://unstop.com/api/public/opportunity/search-new"


def _fetch_unstop_listings(page: int) -> list[dict]:
    """Fetch a page of hackathon listings from the Unstop search API.

    Args:
        page: Page number (1-indexed).

    Returns:
        List of raw listing dicts from the API, or empty list on failure.
    """
    params = {
        "opportunity": "hackathons",
        "oppstatus": "open",
        "page": page,
        "per_page": 15,
        "sort": "deadline",
    }

    try:
        _enforce_delay("Unstop")
        resp = requests.get(
            _UNSTOP_API_URL,
            headers=HEADERS,
            params=params,
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as e:
        print(f"  [Unstop] Failed to fetch page {page}: {e}")
        return []

    opportunities = data.get("data", {}).get("data", [])
    if not isinstance(opportunities, list):
        return []

    return opportunities


def _extract_unstop_detail(url: str) -> dict:
    """Visit an Unstop detail page and extract metadata.

    Attempts to fetch the detail page HTML and extract deadlines, prize,
    team size, mode, location, and organizer. Retries once on failure.

    Args:
        url: Full URL to the Unstop hackathon detail page.

    Returns:
        Dict with extracted fields (values may be None).
    """
    empty = {
        "registration_deadline": None,
        "submission_deadline": None,
        "prize": None,
        "team_size": None,
        "mode": None,
        "location": None,
        "organizer": None,
    }

    html = _fetch_unstop_detail_page(url, retry=True)
    if not html:
        return empty

    try:
        soup = BeautifulSoup(html, "html.parser")
        return _parse_unstop_detail_page(soup)
    except Exception as e:
        print(f"  [Unstop] Failed to parse detail page {url}: {e}")
        return empty


def _fetch_unstop_detail_page(url: str, retry: bool = True) -> Optional[str]:
    """Fetch the HTML content of an Unstop detail page with retry.

    Args:
        url: Full URL to fetch.
        retry: Whether to retry once on failure.

    Returns:
        HTML string content, or None on failure.
    """
    try:
        _enforce_delay("Unstop")
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as e:
        if retry:
            print(f"  [Unstop] Detail page fetch failed, retrying: {e}")
            time.sleep(2)
            return _fetch_unstop_detail_page(url, retry=False)
        print(f"  [Unstop] Detail page fetch failed after retry: {e}")
        return None


def _parse_unstop_detail_page(soup: BeautifulSoup) -> dict:
    """Parse an Unstop detail page for hackathon metadata.

    Args:
        soup: BeautifulSoup object of the detail page.

    Returns:
        Dict with extracted metadata fields.
    """
    result: dict = {
        "registration_deadline": None,
        "submission_deadline": None,
        "prize": None,
        "team_size": None,
        "mode": None,
        "location": None,
        "organizer": None,
    }

    # Extract dates from the page
    # Unstop typically shows dates in various containers
    date_elements = soup.find_all(string=re.compile(
        r"(registration|submission|deadline|end date|last date)",
        re.IGNORECASE,
    ))
    for el in date_elements:
        parent = el.parent
        if parent:
            # Look for sibling or nearby date text
            next_text = parent.get_text(separator=" ", strip=True)
            if re.search(r"registration", str(el), re.IGNORECASE):
                date_match = _find_date_in_text(next_text)
                if date_match:
                    result["registration_deadline"] = date_match
            elif re.search(r"(submission|end date|last date)", str(el), re.IGNORECASE):
                date_match = _find_date_in_text(next_text)
                if date_match:
                    result["submission_deadline"] = date_match

    # Extract prize information
    prize_section = soup.find(string=re.compile(r"(prize|reward)", re.IGNORECASE))
    if prize_section:
        prize_parent = prize_section.parent
        if prize_parent:
            prize_container = prize_parent.parent if prize_parent.parent else prize_parent
            prize_text = prize_container.get_text(separator=" ", strip=True)
            # Look for currency or "worth" patterns
            prize_match = re.search(
                r"([\₹\$€£]\s*[\d,]+(?:\s*(?:Lakhs?|Crore|K|M))?|"
                r"(?:INR|USD|EUR)\s*[\d,]+(?:\s*(?:Lakhs?|Crore|K|M))?|"
                r"(?:worth|prizes?)[:\s]*[^\n]{3,80})",
                prize_text,
                re.IGNORECASE,
            )
            if prize_match:
                result["prize"] = prize_match.group(0).strip()

    # Extract team size
    team_section = soup.find(string=re.compile(r"team\s*size", re.IGNORECASE))
    if team_section:
        team_parent = team_section.parent
        if team_parent:
            team_text = team_parent.get_text(separator=" ", strip=True)
            team_match = re.search(r"(\d+\s*[-–to]+\s*\d+|\d+)", team_text)
            if team_match:
                result["team_size"] = team_match.group(0).strip()

    # Extract mode (online/offline/hybrid)
    page_text = soup.get_text(separator=" ", strip=True).lower()
    if "hybrid" in page_text:
        result["mode"] = "hybrid"
    elif "online" in page_text or "virtual" in page_text:
        result["mode"] = "online"
    elif "offline" in page_text or "in-person" in page_text or "on-site" in page_text:
        result["mode"] = "offline"

    # Extract location
    location_section = soup.find(string=re.compile(r"(venue|location|city)", re.IGNORECASE))
    if location_section:
        loc_parent = location_section.parent
        if loc_parent:
            loc_text = loc_parent.get_text(separator=" ", strip=True)
            # Remove the label and get the value
            loc_cleaned = re.sub(r"^(venue|location|city)[:\s]*", "", loc_text, flags=re.IGNORECASE).strip()
            if loc_cleaned and len(loc_cleaned) < 200:
                result["location"] = loc_cleaned

    # Extract organizer
    org_section = soup.find(string=re.compile(r"(hosted by|organized by|organiser|organizer)", re.IGNORECASE))
    if org_section:
        org_parent = org_section.parent
        if org_parent:
            org_text = org_parent.get_text(separator=" ", strip=True)
            org_cleaned = re.sub(
                r"^(hosted by|organized by|organiser|organizer)[:\s]*",
                "",
                org_text,
                flags=re.IGNORECASE,
            ).strip()
            if org_cleaned and len(org_cleaned) < 200:
                result["organizer"] = org_cleaned

    return result


def _find_date_in_text(text: str) -> Optional[str]:
    """Find a date string within a block of text.

    Args:
        text: Text that may contain a date.

    Returns:
        A raw date string if found, or None.
    """
    # Match common date patterns
    patterns = [
        r"\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}Z?)?",  # ISO
        r"\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{4}",  # 15 Jan 2025
        r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2},?\s+\d{4}",  # Jan 15, 2025
        r"\d{1,2}/\d{1,2}/\d{4}",  # 01/15/2025
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(0)

    return None


def _extract_unstop_themes(tags: list) -> list[str]:
    """Extract theme names from Unstop API tags field.

    Args:
        tags: List of tag dicts or strings from the API response.

    Returns:
        List of theme name strings.
    """
    themes: list[str] = []
    if not isinstance(tags, list):
        return themes

    for tag in tags:
        if isinstance(tag, dict):
            name = (tag.get("name") or "").strip()
        else:
            name = str(tag).strip()
        if name:
            themes.append(name)

    return themes


def _extract_unstop_prize_from_listing(listing: dict) -> Optional[str]:
    """Extract prize info from the Unstop listing API response.

    Args:
        listing: Raw listing dict from the API.

    Returns:
        Prize string or None.
    """
    # Check for prizes in various API fields
    prizes = listing.get("prizes")
    if isinstance(prizes, list) and prizes:
        prize_parts = []
        for p in prizes:
            if isinstance(p, dict):
                name = p.get("name") or p.get("title") or ""
                value = p.get("cash") or p.get("value") or ""
                if name and value:
                    prize_parts.append(f"{name}: {value}")
                elif name:
                    prize_parts.append(str(name))
                elif value:
                    prize_parts.append(str(value))
        if prize_parts:
            return ", ".join(prize_parts)

    # Check for prize_amount or similar fields
    prize_amt = listing.get("prize_amount") or listing.get("prize")
    if prize_amt:
        return str(prize_amt).strip() or None

    return None


def _extract_unstop_team_size_from_listing(listing: dict) -> Optional[str]:
    """Extract team size info from the Unstop listing API response.

    Args:
        listing: Raw listing dict from the API.

    Returns:
        Team size string (e.g., "2-4") or None.
    """
    # Check regnRequirements for team info
    regn = listing.get("regnRequirements", {})
    if isinstance(regn, dict):
        min_size = regn.get("min_team_size")
        max_size = regn.get("max_team_size")
        if min_size and max_size:
            return f"{min_size}-{max_size}"
        elif max_size:
            return f"1-{max_size}"
        elif min_size:
            return str(min_size)

    return None
