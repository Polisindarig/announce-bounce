"""Fast Binance announcement scraper — two-pass approach.

Pass 1 (fast): Fetch listing pages only (title + date + code). No detail calls.
               ~5 seconds per page, ~500 announcements/minute.
Pass 2 (slow): Fetch body HTML for each announcement via detail endpoint.
               Can be run later, incrementally.

This avoids the bottleneck of calling detail API for every single announcement
during the initial scrape.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://www.binance.com"
LIST_ENDPOINT = "/bapi/composite/v1/public/cms/article/list/query"
DETAIL_ENDPOINT = "/bapi/composite/v1/public/cms/article/detail/query"

CATALOG_IDS = {
    48: "new_cryptocurrency_listing",
    49: "latest_binance_news",
    50: "new_fiat_listings",
    157: "wallet_maintenance_updates",
    161: "delisting",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

PAGE_SIZE = 20


def _ms_to_iso(ms: int | None) -> str | None:
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def pass1_fetch_listings(
    output_path: Path,
    start_ms: int,
    end_ms: int,
    catalog_ids: list[int] | None = None,
) -> int:
    """Pass 1: fetch announcement metadata (no body). Fast."""
    if catalog_ids is None:
        catalog_ids = list(CATALOG_IDS.keys())

    output_path.parent.mkdir(parents=True, exist_ok=True)
    total = 0

    existing_codes: set[str] = set()
    if output_path.exists():
        for line in output_path.read_text().strip().split("\n"):
            if line.strip():
                row = json.loads(line)
                existing_codes.add(row.get("code", ""))
                total += 1
        logger.info("Resuming: %d existing announcements found", total)

    client = httpx.Client(headers=HEADERS, timeout=15, follow_redirects=True)
    try:
        with open(output_path, "a") as f:
            for cat_id in catalog_ids:
                cat_name = CATALOG_IDS.get(cat_id, f"unknown_{cat_id}")
                page = 1
                reached_start = False

                while not reached_start:
                    logger.info("catalog=%d (%s) page=%d", cat_id, cat_name, page)

                    data = None
                    for attempt in range(10):
                        try:
                            resp = client.get(
                                f"{BASE_URL}{LIST_ENDPOINT}",
                                params={
                                    "type": 1,
                                    "catalogId": cat_id,
                                    "pageNo": page,
                                    "pageSize": PAGE_SIZE,
                                },
                            )
                            if resp.status_code == 429:
                                wait = min(2 ** attempt * 5, 120)
                                logger.warning("429 on cat=%d page=%d, waiting %ds", cat_id, page, wait)
                                time.sleep(wait)
                                continue
                            resp.raise_for_status()
                            data = resp.json()
                            break
                        except Exception as e:
                            logger.error("Failed cat=%d page=%d attempt=%d: %s", cat_id, page, attempt, e)
                            time.sleep(5)
                    if data is None:
                        logger.error("Giving up on cat=%d page=%d after 10 attempts", cat_id, page)
                        break

                    if data.get("code") != "000000":
                        logger.error("API error: %s", data.get("message"))
                        break

                    catalogs = data.get("data", {}).get("catalogs", [])
                    if not catalogs:
                        break
                    articles = catalogs[0].get("articles", [])
                    if not articles:
                        break

                    for art in articles:
                        release_ms = art.get("releaseDate")
                        if release_ms is None:
                            continue
                        if release_ms > end_ms:
                            continue
                        if release_ms < start_ms:
                            reached_start = True
                            break

                        code = art.get("code", "")
                        if code in existing_codes:
                            continue
                        existing_codes.add(code)

                        row = {
                            "announcement_id": str(art.get("id", "")),
                            "code": code,
                            "title": art.get("title", ""),
                            "published_at": _ms_to_iso(release_ms),
                            "updated_at": _ms_to_iso(art.get("updateDate")),
                            "scraped_at": datetime.now(timezone.utc).isoformat(),
                            "catalog_id": cat_id,
                            "catalog_name": cat_name,
                            "url": f"{BASE_URL}/en/support/announcement/{art.get('code', '')}",
                            "body_html": "",
                            "body_text": "",
                            "language": "en",
                        }
                        f.write(json.dumps(row, ensure_ascii=False) + "\n")
                        total += 1

                    if len(articles) < PAGE_SIZE:
                        break

                    page += 1
                    time.sleep(3)

                logger.info("catalog %d done: %d total so far", cat_id, total)
                logger.info("Cooling down 30s before next catalog...")
                time.sleep(30)

    finally:
        client.close()

    logger.info("Pass 1 complete: %d announcements", total)
    return total


def pass2_fetch_bodies(jsonl_path: Path) -> int:
    """Pass 2: fill in body_html and body_text for announcements that lack them."""
    import re
    from html import unescape

    lines = jsonl_path.read_text().strip().split("\n")
    updated = 0
    client = httpx.Client(headers=HEADERS, timeout=15, follow_redirects=True)

    try:
        new_lines = []
        for i, line in enumerate(lines):
            row = json.loads(line)
            if row.get("body_html"):
                new_lines.append(line)
                continue

            code = row.get("code", "")
            if not code:
                new_lines.append(line)
                continue

            try:
                resp = client.get(
                    f"{BASE_URL}{DETAIL_ENDPOINT}",
                    params={"articleCode": code},
                )
                resp.raise_for_status()
                detail = resp.json().get("data", {})
                body_html = detail.get("body", "") or ""
                body_text = re.sub(r"<[^>]+>", " ", unescape(body_html))
                body_text = re.sub(r"\s+", " ", body_text).strip()
                row["body_html"] = body_html
                row["body_text"] = body_text
                updated += 1
            except Exception as e:
                logger.warning("Detail fetch failed for %s: %s", code, e)

            new_lines.append(json.dumps(row, ensure_ascii=False))

            if (i + 1) % 50 == 0:
                logger.info("Pass 2 progress: %d/%d (%d updated)", i + 1, len(lines), updated)

            time.sleep(1.5)

    finally:
        client.close()

    jsonl_path.write_text("\n".join(new_lines) + "\n")
    logger.info("Pass 2 complete: %d bodies fetched", updated)
    return updated


if __name__ == "__main__":
    import argparse

    import yaml

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/data_window.yaml")
    parser.add_argument("--output", default="data/raw/announcements.jsonl")
    parser.add_argument("--pass", dest="which_pass", choices=["1", "2", "both"], default="both")
    parser.add_argument("--catalogs", type=str, default=None, help="Comma-separated catalog IDs to scrape")
    args = parser.parse_args()

    with open(args.config) as f:
        cfg = yaml.safe_load(f)

    start = datetime.fromisoformat(cfg["window_start"]).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(cfg["window_end"]).replace(tzinfo=timezone.utc)
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    out = Path(args.output)

    cat_ids = None
    if args.catalogs:
        cat_ids = [int(x.strip()) for x in args.catalogs.split(",")]

    if args.which_pass in ("1", "both"):
        n = pass1_fetch_listings(out, start_ms, end_ms, catalog_ids=cat_ids)
        print(f"\nPass 1: {n} announcements saved to {out}")

    if args.which_pass in ("2", "both"):
        n = pass2_fetch_bodies(out)
        print(f"Pass 2: {n} bodies fetched")
