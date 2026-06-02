"""Symbol extraction rules for listing vs generic posts."""

from src.scraper.symbol_extractor import extract_symbols, extract_tickers_from_title


def test_listing_title_only_no_body_fallback():
    ann = {
        "catalog_name": "new_cryptocurrency_listing",
        "title": "Binance Futures Will Launch USDⓈ-Margined BTCUSD1 Perpetual Contract",
        "body_text": "MULTI DATA NOT ID ONE LAYER mentioned in boilerplate",
    }
    known = {"MULTI", "DATA", "NOT", "ID", "ONE", "LAYER", "SOL", "PHAROS", "STAR"}
    assert extract_symbols(ann, known) == []


def test_listing_extracts_parentheses_ticker():
    ann = {
        "catalog_name": "new_cryptocurrency_listing",
        "title": "Binance Will List Solana (SOL)",
        "body_text": "MULTI DATA",
    }
    known = {"MULTI", "DATA", "SOL"}
    assert extract_symbols(ann, known) == ["SOL"]


def test_title_usdt_pairs_multiple():
    title = "Binance Futures Will Launch PHAROSUSDT and STARUSDT Perpetual Contracts"
    assert "PHAROS" in extract_tickers_from_title(title)
    assert "STAR" in extract_tickers_from_title(title)


def test_generic_post_can_use_body_when_no_title_tickers():
    ann = {
        "catalog_name": "latest_binance_news",
        "title": "Weekly update",
        "body_text": "Trading for PEPE continues.",
    }
    known = {"PEPE", "MULTI"}
    assert extract_symbols(ann, known) == ["PEPE"]
