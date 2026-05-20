"""Binance announcement scraper.

Pulls historical announcements from the undocumented Binance CMS API:
  /bapi/composite/v1/public/cms/article/list/query  (per ``catalogId``)

By default scrapes **all** English announcement-center catalogs (8 IDs: listings,
news, activities, fiat, delisting, maintenance, API, airdrop). Use ``--catalogs``
to limit. Run ``--discover-catalogs`` to refresh IDs from Binance if categories change.

For each announcement: title, body, timestamps, category, raw HTML.
Rate-limited at 1 request / 2 seconds with exponential backoff.

See docs/03-project-plan.md Phase 1 for the full spec.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://www.binance.com"
LIST_ENDPOINT = "/bapi/composite/v1/public/cms/article/list/query"
DETAIL_ENDPOINT = "/bapi/composite/v1/public/cms/article/detail/query"
APEX_LIST_ENDPOINT = "/bapi/apex/v1/public/apex/cms/article/list/query"


def discover_announcement_catalogs(client: httpx.Client) -> dict[int, str]:
    """Return ``catalogId`` → slug from Binance apex combined feed (page 1).

    Use this to refresh :data:`CATALOG_IDS` if Binance adds categories.
    """
    data = _api_get(
        client,
        f"{BASE_URL}{APEX_LIST_ENDPOINT}",
        {"type": 1, "pageNo": 1, "pageSize": 1},
    )
    out: dict[int, str] = {}
    for c in (data.get("data") or {}).get("catalogs", []):
        cid = c.get("catalogId")
        if cid is None:
            continue
        name = str(c.get("catalogName") or f"catalog_{cid}")
        slug = name.lower().replace(" ", "_").replace("(", "").replace(")", "")
        out[int(cid)] = slug
    return dict(sorted(out.items()))

CATALOG_IDS = {
    # Full set of English announcement center catalogs (message center v2), May 2026.
    # Scrape all by default; use --catalogs to restrict.
    48: "new_cryptocurrency_listing",
    49: "latest_binance_news",
    50: "new_fiat_listings",
    51: "api_updates",
    93: "latest_activities",
    128: "crypto_airdrop",
    157: "wallet_maintenance_updates",
    161: "delisting",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": BASE_URL,
    "Referer": f"{BASE_URL}/en/support/announcement",
}

REQUEST_DELAY_S = 7.0
# Extra pause between catalogs to reduce 429 bursts when scraping many categories back-to-back.
INTER_CATALOG_PAUSE_S = 20.0
# When a list page has only already-seen IDs, skip long pacing (resume feels instant).
MIN_PAGE_SLEEP_S = 0.5
PAGE_SIZE = 20


@dataclass
class Announcement:
    announcement_id: str
    title: str
    body_html: str
    body_text: str
    published_at: str  # ISO-8601 UTC
    updated_at: str | None  # ISO-8601 UTC, if available
    scraped_at: str  # ISO-8601 UTC
    catalog_id: int
    catalog_name: str
    category_native: str
    url: str
    language: str = "en"


@dataclass
class ScrapeResult:
    total_fetched: int = 0
    total_written: int = 0
    total_skipped_duplicate: int = 0
    total_skipped_out_of_range: int = 0
    errors: list[str] = field(default_factory=list)


@retry(
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.ConnectError, httpx.ReadTimeout)),
    wait=wait_exponential(multiplier=2, min=8, max=120),
    stop=stop_after_attempt(12),
)
def _api_get(client: httpx.Client, url: str, params: dict) -> dict:
    """GET with retry + backoff. Raises on non-200 or unexpected JSON."""
    resp = client.get(url, params=params)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != "000000":
        raise httpx.HTTPStatusError(
            f"Binance API error: code={data.get('code')}, msg={data.get('message')}",
            request=resp.request,
            response=resp,
        )
    return data


def _ms_to_iso(ms: int | None) -> str | None:
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def _strip_html(html: str) -> str:
    """Minimal HTML tag removal. We keep body_html for re-parsing later."""
    from html import unescape

    import re

    text = re.sub(r"<[^>]+>", " ", html)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_article_detail(client: httpx.Client, article_code: str) -> dict | None:
    """Fetch full article body by article code."""
    try:
        data = _api_get(
            client,
            f"{BASE_URL}{DETAIL_ENDPOINT}",
            {"articleCode": article_code},
        )
        return data.get("data", {})
    except Exception as e:
        logger.warning("Failed to fetch detail for %s: %s", article_code, e)
        return None


def scrape_catalog(
    client: httpx.Client,
    catalog_id: int,
    start_ms: int,
    end_ms: int,
    seen_ids: set[str],
    record_sink: Callable[[Announcement], None] | None = None,
) -> list[Announcement]:
    """Scrape all announcements in a catalog within [start_ms, end_ms].

    If ``record_sink`` is set, each new ``Announcement`` is passed to it immediately
    (e.g. to ``flush`` JSONL) so a mid-catalog interrupt does not lose progress.
    """
    catalog_name = CATALOG_IDS.get(catalog_id, f"unknown_{catalog_id}")
    announcements: list[Announcement] = []
    page = 1
    reached_start = False

    while not reached_start:
        new_this_page = 0
        skipped_on_disk = 0
        logger.info(
            "Fetching catalog=%s (%s) page=%d", catalog_id, catalog_name, page
        )

        params = {
            "type": 1,
            "catalogId": catalog_id,
            "pageNo": page,
            "pageSize": PAGE_SIZE,
        }

        try:
            data = _api_get(client, f"{BASE_URL}{LIST_ENDPOINT}", params)
        except Exception as e:
            logger.error("Failed catalog=%d page=%d: %s", catalog_id, page, e)
            break

        catalogs = data.get("data", {}).get("catalogs", [])
        if not catalogs:
            break

        articles = catalogs[0].get("articles", [])
        if not articles:
            break

        for article in articles:
            release_ms = article.get("releaseDate")
            if release_ms is None:
                continue

            if release_ms > end_ms:
                continue
            if release_ms < start_ms:
                reached_start = True
                break

            article_id = str(article.get("id", article.get("code", "")))
            if article_id in seen_ids:
                skipped_on_disk += 1
                continue

            article_code = article.get("code", "")
            title = article.get("title", "")

            body_html = ""
            body_text = ""
            detail = fetch_article_detail(client, article_code)
            if detail:
                body_html = detail.get("body", "") or ""
                body_text = _strip_html(body_html) if body_html else ""

            now_iso = datetime.now(timezone.utc).isoformat()
            url = f"{BASE_URL}/en/support/announcement/{article_code}"

            ann = Announcement(
                announcement_id=article_id,
                title=title,
                body_html=body_html,
                body_text=body_text,
                published_at=_ms_to_iso(release_ms) or "",
                updated_at=_ms_to_iso(article.get("updateDate")),
                scraped_at=now_iso,
                catalog_id=catalog_id,
                catalog_name=catalog_name,
                category_native=catalog_name,
                url=url,
            )
            announcements.append(ann)
            if record_sink is not None:
                record_sink(ann)
            seen_ids.add(article_id)

            new_this_page += 1
            time.sleep(REQUEST_DELAY_S)

        logger.info(
            "catalog=%s page=%d: +%d new, %d skipped (already on disk)",
            catalog_id,
            page,
            new_this_page,
            skipped_on_disk,
        )

        if reached_start:
            break

        if len(articles) < PAGE_SIZE:
            break

        page += 1
        time.sleep(REQUEST_DELAY_S if new_this_page else MIN_PAGE_SLEEP_S)

    return announcements


def scrape_announcements(
    start_date: datetime,
    end_date: datetime,
    output_path: str | Path,
    catalog_ids: list[int] | None = None,
) -> ScrapeResult:
    """Scrape Binance announcements in [start_date, end_date] to a JSONL file.

    Args:
        start_date: Inclusive start (UTC).
        end_date: Inclusive end (UTC).
        output_path: Path to output JSONL file.
        catalog_ids: Which catalogs to scrape. Defaults to all known.

    Returns:
        ScrapeResult with counts and errors.
    """
    if catalog_ids is None:
        catalog_ids = list(CATALOG_IDS.keys())

    start_ms = int(start_date.timestamp() * 1000)
    end_ms = int(end_date.timestamp() * 1000)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    result = ScrapeResult()
    seen_ids: set[str] = set()

    if output_path.exists():
        with open(output_path) as f:
            for line in f:
                try:
                    obj = json.loads(line)
                    seen_ids.add(str(obj.get("announcement_id", "")))
                except json.JSONDecodeError:
                    pass
        logger.info("Loaded %d existing IDs from %s", len(seen_ids), output_path)

    client = httpx.Client(
        headers=HEADERS,
        timeout=30.0,
        follow_redirects=True,
    )

    try:
        with open(output_path, "a") as f:

            def _record(ann: Announcement) -> None:
                f.write(json.dumps(asdict(ann), ensure_ascii=False) + "\n")
                f.flush()

            for i, cat_id in enumerate(catalog_ids):
                if i > 0:
                    time.sleep(INTER_CATALOG_PAUSE_S)
                logger.info(
                    "--- Scraping catalog %d (%s) ---",
                    cat_id,
                    CATALOG_IDS.get(cat_id, "unknown"),
                )

                try:
                    anns = scrape_catalog(
                        client, cat_id, start_ms, end_ms, seen_ids, record_sink=_record
                    )
                except Exception as e:
                    msg = f"Catalog {cat_id} failed: {e}"
                    logger.error(msg)
                    result.errors.append(msg)
                    time.sleep(INTER_CATALOG_PAUSE_S * 2)
                    continue

                result.total_fetched += len(anns)
                result.total_written += len(anns)

                logger.info(
                    "Catalog %d: fetched %d announcements", cat_id, len(anns)
                )
    finally:
        client.close()

    logger.info(
        "Done: fetched=%d, written=%d, errors=%d",
        result.total_fetched,
        result.total_written,
        len(result.errors),
    )
    return result


def main():
    """CLI entry point."""
    import argparse

    import yaml

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="Scrape Binance announcements")
    parser.add_argument(
        "--config",
        default="config/data_window.yaml",
        help="Path to data_window.yaml",
    )
    parser.add_argument(
        "--output",
        default="data/raw/announcements.jsonl",
        help="Output JSONL path",
    )
    parser.add_argument(
        "--start",
        default="",
        help="ISO UTC start (overrides config window_start), e.g. 2025-06-01",
    )
    parser.add_argument(
        "--end",
        default="",
        help="ISO UTC end (overrides config window_end)",
    )
    parser.add_argument(
        "--catalogs",
        nargs="*",
        type=int,
        default=None,
        help="Catalog IDs to scrape (default: all)",
    )
    parser.add_argument(
        "--discover-catalogs",
        action="store_true",
        help="Print catalog IDs from Binance apex API (no scrape, no config needed).",
    )
    args = parser.parse_args()

    if args.discover_catalogs:
        client = httpx.Client(
            headers=HEADERS,
            timeout=30.0,
            follow_redirects=True,
        )
        try:
            disc = discover_announcement_catalogs(client)
            for cid, slug in disc.items():
                print(f"{cid}\t{slug}")
            print(f"\n{len(disc)} catalogs (compare with CATALOG_IDS in announcements.py).")
        finally:
            client.close()
        return

    with open(args.config) as f:
        config = yaml.safe_load(f)

    start_s = args.start.strip() or config["window_start"]
    end_s_raw = args.end.strip() or config["window_end"]
    start = datetime.fromisoformat(str(start_s).replace("Z", "+00:00"))
    end = datetime.fromisoformat(str(end_s_raw).replace("Z", "+00:00"))
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    # Date-only end (YAML ``2026-05-14``) → include that whole calendar day in UTC
    if "T" not in str(end_s_raw) and "t" not in str(end_s_raw):
        end = end.replace(hour=23, minute=59, second=59, microsecond=999999)

    logger.info("Scraping %s to %s → %s", start.isoformat(), end.isoformat(), args.output)

    result = scrape_announcements(
        start_date=start,
        end_date=end,
        output_path=args.output,
        catalog_ids=args.catalogs,
    )

    print(f"\nResults: {result.total_written} written, {len(result.errors)} errors")
    if result.errors:
        for err in result.errors:
            print(f"  ERROR: {err}")


if __name__ == "__main__":
    main()
