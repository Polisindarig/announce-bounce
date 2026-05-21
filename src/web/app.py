"""Local dashboard for thesis MVP results."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.web import data_loader

STATIC = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Binance Sentiment Bot Dashboard", version="0.2.0")
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


# ── Overview ──────────────────────────────────────────────────────────────
@app.get("/api/overview")
def api_overview() -> dict:
    return data_loader.overview()


@app.get("/api/catalogs")
def api_catalogs() -> list:
    return data_loader.catalog_chart_data()


# ── Backtest (Phase 5) ───────────────────────────────────────────────────
@app.get("/api/backtest/{variant}")
def api_backtest(variant: str = "m0") -> dict:
    return data_loader.backtest_result(variant)


@app.get("/api/backtest/{variant}/trades")
def api_backtest_trades(variant: str = "m0") -> list:
    return data_loader.backtest_trades(variant)


@app.get("/api/backtest/{variant}/equity")
def api_backtest_equity(variant: str = "m0") -> list:
    return data_loader.backtest_equity_curve(variant)


# ── OOS (Phase 6) ────────────────────────────────────────────────────────
@app.get("/api/oos")
def api_oos() -> dict:
    return data_loader.oos_result()


# ── Robustness (Phase 7) ─────────────────────────────────────────────────
@app.get("/api/robustness")
def api_robustness() -> dict:
    return data_loader.robustness_result()


# ── Event study (Phase 4) ────────────────────────────────────────────────
@app.get("/api/event-study")
def api_event_study() -> dict:
    return data_loader.event_study_result()


@app.get("/api/event-study/listing-spot")
def api_event_study_listing_spot() -> dict:
    return data_loader.event_study_listing_spot()


# ── Sentiment (Phase 2) ─────────────────────────────────────────────────
@app.get("/api/sentiment")
def api_sentiment() -> dict:
    return data_loader.sentiment_summary()


# ── Bot operational state ────────────────────────────────────────────────
@app.get("/api/bot/state")
def api_bot_state() -> dict:
    return data_loader.bot_state()


@app.get("/api/latency/scenarios")
def api_latency_scenarios() -> dict:
    return data_loader.latency_scenarios()


@app.get("/api/trades/recent")
def api_trades_recent() -> list:
    return data_loader.recent_trades()


@app.get("/api/announcements/recent")
def api_announcements_recent() -> list:
    return data_loader.recent_announcements()


@app.get("/api/equity")
def api_equity() -> list:
    return data_loader.equity_curve()


# ── Legacy ───────────────────────────────────────────────────────────────
@app.get("/api/tier1/significant")
def api_tier1_significant(subset: str = "oos") -> list:
    return data_loader.tier1_significant_tests(subset)


@app.get("/api/listing/fdr")
def api_listing_fdr() -> dict:
    return data_loader.listing_fdr_summary()


@app.get("/api/mexc")
def api_mexc() -> dict:
    return data_loader.mexc_comparison()


@app.get("/api/listing/backtest")
def api_listing_backtest(balanced: bool = True) -> dict:
    return data_loader.listing_backtest("balanced" if balanced else "primary")


def main() -> None:
    import uvicorn

    uvicorn.run(
        "src.web.app:app",
        host="127.0.0.1",
        port=8765,
        reload=True,
    )


if __name__ == "__main__":
    main()
