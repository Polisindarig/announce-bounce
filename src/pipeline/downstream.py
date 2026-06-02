"""Full research pipeline: enrich → events → baseline → backtest → reports → manifest."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from src.analysis.events_summary import summarize_events, print_summary
from src.analysis.listing_backtest_report import build_listing_report
from src.analysis.listing_event_study import build_event_study_report
from src.analysis.tier1_event_study import build_tier1_report
from src.analysis.train_baseline import load_window_bounds, train_baseline
from src.backtest.engine import write_backtest_report
from src.processing.build_events import build_events_table
from src.scraper.listing_time import enrich_announcements_jsonl
from src.scraper.symbol_extractor import process_announcements
from src.utils.reproducibility_manifest import build_manifest, write_manifest

logger = logging.getLogger("src.pipeline.downstream")

DEFAULT_RAW = "data/raw/announcements_from_2025-06-01.jsonl"
DEFAULT_ENRICHED = "data/processed/announcements_with_symbols_june2025.jsonl"


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Full downstream research pipeline")
    parser.add_argument("--raw-jsonl", default=str(root / DEFAULT_RAW))
    parser.add_argument("--enriched-jsonl", default=str(root / DEFAULT_ENRICHED))
    parser.add_argument("--klines-dir", default=str(root / "data" / "raw" / "klines"))
    parser.add_argument("--events-out", default=str(root / "data" / "processed" / "events.parquet"))
    parser.add_argument("--report-out", default=str(root / "data" / "processed" / "train_baseline_report.json"))
    parser.add_argument("--config", default=str(root / "config" / "data_window.yaml"))
    parser.add_argument("--target", default="ret_5m_index_adj")
    parser.add_argument("--skip-symbols", action="store_true")
    parser.add_argument("--skip-listing-times", action="store_true")
    parser.add_argument("--skip-backtest", action="store_true")
    parser.add_argument("--skip-summary", action="store_true")
    parser.add_argument("--skip-listing-report", action="store_true")
    parser.add_argument("--skip-listing-fdr", action="store_true")
    parser.add_argument("--skip-tier1-fdr", action="store_true")
    parser.add_argument("--skip-manifest", action="store_true")
    parser.add_argument("--backtest-config", default=str(root / "config" / "backtest_baseline.yaml"))
    parser.add_argument("--backtest-report", default=str(root / "data" / "processed" / "backtest_oos_summary.json"))
    parser.add_argument("--summary-out", default=str(root / "data" / "processed" / "events_summary.json"))
    args = parser.parse_args()

    raw = Path(args.raw_jsonl)
    if not raw.exists():
        raise SystemExit(f"Missing raw announcements: {raw}")

    enriched = Path(args.enriched_jsonl)
    if not args.skip_symbols:
        logger.info("Step 1: symbol extraction → %s", enriched)
        n = process_announcements(raw, enriched)
        logger.info("Enriched %d announcements", n)

    if not args.skip_listing_times:
        logger.info("Step 1b: listing t_0 enrichment → %s", enriched)
        enrich_announcements_jsonl(enriched, enriched, Path(args.klines_dir))

    logger.info("Step 2: build events → %s", args.events_out)
    df = build_events_table(
        announcements_path=enriched,
        klines_dir=args.klines_dir,
        output_path=args.events_out,
    )
    logger.info("Events rows: %d", len(df))

    logger.info("Step 3: baseline regression → %s", args.report_out)
    bounds = load_window_bounds(Path(args.config))
    target = args.target if args.target in df.columns else "ret_5m_btc_adj"
    report = train_baseline(df, bounds, target_col=target)
    Path(args.report_out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.report_out, "w") as f:
        json.dump(report, f, indent=2)
    print(json.dumps({"baseline": report}, indent=2))

    if not args.skip_backtest:
        logger.info("Step 4: OOS backtest → %s", args.backtest_report)
        bt = write_backtest_report(args.backtest_config, args.backtest_report)
        print(json.dumps({"backtest_oos": bt}, indent=2))

    if not args.skip_summary:
        summary = summarize_events(df)
        with open(args.summary_out, "w") as f:
            json.dump(summary, f, indent=2)
        print_summary(summary)

    if not args.skip_listing_report:
        for cfg_name, out_name in (
            ("backtest_listing.yaml", "listing_backtest_report.json"),
            ("backtest_listing_balanced.yaml", "listing_backtest_report_balanced.json"),
        ):
            out_p = root / "data" / "processed" / out_name
            rep = build_listing_report(root / "config" / cfg_name)
            with open(out_p, "w") as f:
                json.dump(rep, f, indent=2)

    win = root / "config" / "listing_eval_window.yaml"
    if not args.skip_listing_fdr:
        fdr = build_event_study_report(Path(args.events_out), win, alpha=0.05)
        with open(root / "data/processed/listing_event_study_fdr.json", "w") as f:
            json.dump(fdr, f, indent=2)

    if not args.skip_tier1_fdr:
        t1 = build_tier1_report(Path(args.events_out), win, alpha=0.05, headline_baseline="index_adj")
        with open(root / "data/processed/tier1_event_study_fdr.json", "w") as f:
            json.dump(t1, f, indent=2)

    if not args.skip_manifest:
        artifacts = [
            Path(args.events_out),
            Path(args.report_out),
            Path(args.backtest_report),
            root / "data/processed/listing_backtest_report.json",
            root / "data/processed/tier1_event_study_fdr.json",
        ]
        configs = [
            Path(args.config),
            win,
            root / "config/oos.yaml",
            root / "config/backtest_baseline.yaml",
        ]
        manifest = build_manifest(root, artifacts, configs)
        mpath = root / "data/processed/reproducibility_manifest.json"
        write_manifest(mpath, manifest)
        logger.info("Reproducibility manifest → %s", mpath)

    logger.info("Pipeline complete.")


if __name__ == "__main__":
    main()
