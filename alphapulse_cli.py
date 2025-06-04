import argparse
import asyncio
import threading
from typing import Iterable


def run_bot(_: argparse.Namespace) -> None:
    """Start the Telegram bot alongside the trade monitor."""
    from telegram_bot import start_bot
    from trade_monitor import monitor_loop

    thread = threading.Thread(target=asyncio.run, args=(monitor_loop(),))
    thread.start()
    start_bot()


def run_scrape(_: argparse.Namespace) -> None:
    """Run the wallet scraping routine."""
    from wallet_scraper import scrape_all_wallets, export_json, add_wallet

    async def _scrape() -> None:
        wallet_list = [
            "9djU9o4CD14ak5G4TNLp1KvqbWZ4BptU6WyquvDjWYJz",
            "FjYFNY2KXwRbDMEiEdxAF3uCWJTL5sCHwMGR6ZaSkbtu",
        ]
        wallets = await scrape_all_wallets(wallet_list)
        if not wallets:
            fallback = [
                ("9djU9o4CD14ak5G4TNLp1KvqbWZ4BptU6WyquvDjWYJz", "known_trader"),
                ("FjYFNY2KXwRbDMEiEdxAF3uCWJTL5sCHwMGR6ZaSkbtu", "jito_whale"),
                ("5hFZ9vbK9gXx1NSeYZi1o9nPjLkgzBnJjqVXbVWuTbW", "dex_god"),
            ]
            for w, s in fallback:
                add_wallet(wallets, w, s)
        export_json(wallets)
        print("\N{WHITE HEAVY CHECK MARK} Scraping complete. Run wallet_curator.py to update stats.")

    asyncio.run(_scrape())


def run_train(args: Iterable[str]) -> None:
    """Delegate to the backtest module."""
    from training import backtest

    backtest.main(args)


def main(argv: Iterable[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="alphapulse", description="AlphaPulse utilities")
    sub = parser.add_subparsers(dest="command", required=True)

    p_bot = sub.add_parser("bot", help="Launch the trading bot")
    p_bot.set_defaults(func=run_bot)

    p_scrape = sub.add_parser("scrape", help="Scrape wallets from various sources")
    p_scrape.set_defaults(func=run_scrape)

    p_train = sub.add_parser("train", help="Run strategy backtests")
    p_train.add_argument("args", nargs=argparse.REMAINDER)
    p_train.set_defaults(func=lambda ns: run_train(ns.args))

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
