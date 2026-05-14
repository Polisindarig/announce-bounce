"""Event-driven backtester.

Walks a stream of (announcement, 1m-OHLCV) events in time order:
    - opens positions from TradeDecision
    - tracks open positions bar-by-bar
    - exits at first of: TP hit, SL hit, time-stop
    - models taker fees (round-trip) and category-specific slippage
    - enforces a 30-second simulated execution delay after each announcement

Outputs a per-trade log and a summary metrics JSON.

See docs/02-methodology.md §6 and docs/03-project-plan.md Phase 5.
"""

from __future__ import annotations


def run_backtest(config_path: str) -> dict:
    """Run an OOS backtest from a YAML config and return summary metrics."""
    raise NotImplementedError("Implement in Phase 5. See docs/03-project-plan.md.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, help="Path to backtest config YAML.")
    args = parser.parse_args()
    result = run_backtest(args.config)
    print(result)
