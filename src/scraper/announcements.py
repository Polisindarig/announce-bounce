"""Binance announcement scraper.

Scrapes the official Binance announcement page (JS-rendered) and persists
each announcement as one JSON line in `data/raw/announcements.jsonl`.

Implementation outline (Phase 1 of the project plan):
1. Use Playwright to render the announcements listing page.
2. Paginate through all categories of interest.
3. For each announcement, capture: title, body_text, published_at_utc,
   category_native, tags, url, raw_html.
4. Rate-limit at 1 request / 2 seconds with exponential backoff (tenacity).
5. Deduplicate by URL.

This module is a stub. See docs/03-project-plan.md Phase 1 for the full spec.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Announcement:
    url: str
    title: str
    body_text: str
    published_at_utc: datetime
    category_native: str
    tags: list[str]
    raw_html: str


def scrape_announcements(
    start_date: datetime,
    end_date: datetime,
    output_path: str,
) -> int:
    """Scrape announcements in [start_date, end_date] to a JSONL file.

    Returns the number of announcements written.
    """
    raise NotImplementedError("Implement in Phase 1. See docs/03-project-plan.md.")
