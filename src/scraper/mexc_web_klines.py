"""MEXC **web** kline API — same feed the exchange chart uses in the browser.

Discovered from the trade page (e.g. ``/exchange/BTC_USDT``) network traffic::

    GET https://www.mexc.com/api/platform/spot/kline/web/kline/query
        ?symbolId=<uuid>
        &interval=Min1|Min5|Min15|...
        &start=<unix_seconds>
        &end=<unix_seconds>
        &openPriceMode=LAST_CLOSE

This is **not** ``https://api.mexc.com/api/v3/klines``. Retention / behaviour can differ.

**Akamai:** requests from some datacenters get ``Access Denied``. Run this on your own PC /
home IP if you see HTML error pages.

``symbolId`` comes from ``/api/platform/spot/market-v2/web/symbolsV2`` (cached locally).
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pandas as pd

logger = logging.getLogger(__name__)

SYMBOLS_V2_URL = "https://www.mexc.com/api/platform/spot/market-v2/web/symbolsV2"
WEB_KLINE_URL = "https://www.mexc.com/api/platform/spot/kline/web/kline/query"

# Browser-like headers help pass Akamai on residential IPs.
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Origin": "https://www.mexc.com",
    "Referer": "https://www.mexc.com/exchange/BTC_USDT",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Ch-Ua": '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"macOS"',
}


def exchange_url_for_pair(pair: str) -> str:
    if pair.upper().endswith("USDT"):
        return f"https://www.mexc.com/exchange/{pair[:-4].upper()}_USDT"
    return "https://www.mexc.com/exchange/BTC_USDT"


def warm_mexc_cookies(client: httpx.Client, pair: str = "BTCUSDT") -> None:
    """Prime Akamai / session cookies (best-effort)."""
    for url in ("https://www.mexc.com/", exchange_url_for_pair(pair)):
        r = client.get(url)
        logger.info("Warm GET %s → %s", url, r.status_code)


INTERVAL_MIN1 = "Min1"
# Web UI uses ~2000 points per request for coarser intervals; for 1m stay conservative.
MAX_1M_BARS_PER_REQUEST = 1500


def _extract_symbol_rows(payload: object) -> list[dict]:
    """Normalize symbolsV2 JSON into a list of dict-like symbol records."""
    if not isinstance(payload, dict):
        return []
    data = payload.get("data", payload)
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        # Current MEXC shape: ``data.symbols`` is ``{ "USDT": [ { "id", "vn", ... }, ... ], ... }``
        syms = data.get("symbols")
        if isinstance(syms, dict):
            rows: list[dict] = []
            for quote, items in syms.items():
                if not isinstance(items, list):
                    continue
                for x in items:
                    if isinstance(x, dict):
                        r = dict(x)
                        r["_mexc_quote"] = str(quote)
                        rows.append(r)
            if rows:
                return rows
        for key in ("symbols", "spotSymbols", "list", "items"):
            v = data.get(key)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
    return []


def _row_symbol_id(row: dict) -> str | None:
    for k in ("symbolId", "id", "symbolID", "mexcSymbolId"):
        v = row.get(k)
        if v:
            return str(v)
    return None


def load_symbol_id_map(
    cache_path: Path,
    client: httpx.Client,
    force_refresh: bool = False,
    pair_hint: str = "BTCUSDT",
) -> dict[str, str]:
    """Map ``BTCUSDT`` → ``symbolId`` (UUID). Cached as JSON."""
    cache_path = Path(cache_path)
    if cache_path.exists() and not force_refresh:
        with open(cache_path) as f:
            cached = json.load(f)
        if isinstance(cached, dict) and len(cached) > 0:
            return cached

    warm_mexc_cookies(client, pair_hint)
    logger.info("Fetching %s …", SYMBOLS_V2_URL)
    r = client.get(SYMBOLS_V2_URL)
    r.raise_for_status()
    payload = r.json()
    rows = _extract_symbol_rows(payload)
    out: dict[str, str] = {}
    for row in rows:
        sid = _row_symbol_id(row)
        if not sid:
            continue
        for k in ("symbolName", "symbol", "currencyPair"):
            v = row.get(k)
            if not isinstance(v, str):
                continue
            raw = v.replace("-", "_").upper()
            if "_" in raw:
                base, quote = raw.split("_", 1)
                key = f"{base}{quote}"
                out.setdefault(key, sid)
        b = row.get("vcoinName") or row.get("baseCurrency") or row.get("vn")
        q = row.get("market") or row.get("quoteCurrency") or row.get("_mexc_quote")
        if isinstance(b, str) and isinstance(q, str):
            out.setdefault(f"{b.upper()}{q.upper()}", sid)

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w") as f:
        json.dump(out, f, indent=0, sort_keys=True)
    logger.info("Cached %d symbolIds → %s", len(out), cache_path)
    return out


def _coerce_ts_series(raw: list) -> pd.Series:
    nums = [int(float(x)) for x in raw]
    unit = "s" if nums and max(nums) < 10_000_000_000 else "ms"
    return pd.to_datetime(nums, unit=unit, utc=True)


def _parse_kline_payload(payload: dict) -> pd.DataFrame:
    """Turn web kline JSON into OHLCV frame (best-effort; MEXC may change shape)."""
    if not isinstance(payload, dict):
        return pd.DataFrame()
    if str(payload.get("code", "0")) not in ("0", "200", "200000"):
        logger.warning("MEXC web kline non-zero code: %s", payload.get("code"))

    data = payload.get("data", payload)

    # Parallel arrays: {"time":[...],"open":[...], ...}
    if isinstance(data, dict) and isinstance(data.get("time"), list):
        t = data["time"]
        try:
            ot = _coerce_ts_series(t)
        except Exception:
            return pd.DataFrame()
        def series(key: str, alt: str | None = None) -> list[float]:
            arr = data.get(key) or (data.get(alt) if alt else None)
            if not isinstance(arr, list) or len(arr) != len(t):
                return [float("nan")] * len(t)
            return [float(x) for x in arr]

        vol: list[float] | None = None
        for k in ("vol", "v", "volume", "amount"):
            arr = data.get(k)
            if isinstance(arr, list) and len(arr) == len(t):
                vol = [float(x) for x in arr]
                break
        if vol is None:
            vol = [0.0] * len(t)

        df = pd.DataFrame(
            {
                "open_time": ot,
                "open": series("open", "o"),
                "high": series("high", "h"),
                "low": series("low", "l"),
                "close": series("close", "c"),
                "volume": vol,
            }
        )
        df["close_time"] = df["open_time"] + pd.Timedelta(seconds=59)
        df["symbol"] = "WEB"
        return df

    # List of candle objects
    if isinstance(data, list) and data and isinstance(data[0], dict):
        rows = data

        def pick(r: dict, *names: str):
            for n in names:
                for k, v in r.items():
                    if str(k).lower() == n.lower():
                        return v
            return None

        times: list[int] = []
        opens, highs, lows, closes, vols = [], [], [], [], []
        for r in rows:
            ts = pick(r, "time", "t", "openTime", "timestamp")
            if ts is None:
                continue
            times.append(int(float(ts)))
            opens.append(float(pick(r, "open", "o") or 0))
            highs.append(float(pick(r, "high", "h") or 0))
            lows.append(float(pick(r, "low", "l") or 0))
            closes.append(float(pick(r, "close", "c") or 0))
            vv = pick(r, "volume", "vol", "v", "amount")
            vols.append(float(vv or 0))
        if not times:
            return pd.DataFrame()
        unit = "s" if max(times) < 10_000_000_000 else "ms"
        df = pd.DataFrame(
            {
                "open_time": pd.to_datetime(times, unit=unit, utc=True),
                "open": opens,
                "high": highs,
                "low": lows,
                "close": closes,
                "volume": vols,
            }
        )
        df["close_time"] = df["open_time"] + pd.Timedelta(seconds=59)
        df["symbol"] = "WEB"
        return df

    logger.warning("Unrecognized kline JSON shape; data_type=%s", type(data).__name__)
    return pd.DataFrame()


def fetch_web_klines(
    symbol_id: str,
    start: datetime,
    end: datetime,
    interval: str = INTERVAL_MIN1,
    client: httpx.Client | None = None,
) -> pd.DataFrame:
    """Fetch klines between start and end (UTC) via the **web** endpoint."""
    own = client is None
    if own:
        client = httpx.Client(headers=DEFAULT_HEADERS, timeout=60.0, follow_redirects=True)

    start = start.astimezone(timezone.utc)
    end = end.astimezone(timezone.utc)

    all_parts: list[pd.DataFrame] = []
    chunk_seconds = MAX_1M_BARS_PER_REQUEST * 60 if interval == INTERVAL_MIN1 else 86400 * 7

    try:
        cursor = start
        while cursor < end:
            chunk_end = min(cursor + timedelta(seconds=chunk_seconds), end)
            params = {
                "symbolId": symbol_id,
                "interval": interval,
                "openPriceMode": "LAST_CLOSE",
                "start": int(cursor.timestamp()),
                "end": int(chunk_end.timestamp()),
            }
            r = client.get(WEB_KLINE_URL, params=params)
            if r.headers.get("content-type", "").startswith("text/html"):
                logger.error(
                    "MEXC returned HTML (Akamai / block?). Try from home IP. Snippet: %s",
                    r.text[:200],
                )
                break
            r.raise_for_status()
            part = _parse_kline_payload(r.json())
            if part.empty:
                logger.warning("Empty parse for chunk %s → %s", cursor, chunk_end)
            else:
                all_parts.append(part)
            cursor = chunk_end
            time.sleep(0.25)
    finally:
        if own:
            client.close()

    if not all_parts:
        return pd.DataFrame()
    df = pd.concat(all_parts, ignore_index=True)
    df = df.drop_duplicates(subset=["open_time"]).sort_values("open_time")
    return df


def fetch_pair_web_klines(
    pair: str,
    start: datetime,
    end: datetime,
    cache_path: Path = Path("data/raw/mexc_symbol_map.json"),
) -> pd.DataFrame:
    """Resolve ``pair`` (BTCUSDT) to ``symbolId`` and fetch web klines."""
    client = httpx.Client(headers=DEFAULT_HEADERS, timeout=60.0, follow_redirects=True)
    try:
        smap = load_symbol_id_map(cache_path, client, pair_hint=pair.upper())
        sid = smap.get(pair.upper())
        if not sid:
            logger.error("No symbolId for %s in map (keys sample: %s)", pair, list(smap)[:8])
            return pd.DataFrame()
        return fetch_web_klines(sid, start, end, client=client)
    finally:
        client.close()


def main() -> None:
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    p = argparse.ArgumentParser(description="MEXC web chart kline downloader")
    p.add_argument("--pair", default="BTCUSDT")
    p.add_argument("--hours", type=float, default=48.0)
    p.add_argument("--output", default="")
    args = p.parse_args()

    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=args.hours)
    df = fetch_pair_web_klines(args.pair, start, end)
    print("bars", len(df))
    if df.empty:
        return
    out = Path(args.output) if args.output else Path("data/raw/mexc_web_klines") / f"{args.pair}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    print("wrote", out)


if __name__ == "__main__":
    main()
