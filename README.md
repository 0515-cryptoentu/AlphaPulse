# Solana Copy Trading Bot

This project mirrors trades from selected Solana wallets using the Jupiter aggregator and reports status through Telegram. Trade details are logged locally for analysis.

## Setup Instructions

1. Clone the repository and install Python 3.10 or newer.
2. Run `pip install -r requirements.txt` to install dependencies.
3. Copy `.env.example` to `.env` and provide values for the variables listed below.
4. Review `config.py` and adjust `PRACTICE_MODE` or other settings as desired.
5. Start the main bot with `python main.py` and interact with it on Telegram using `/start` and `/status`.

## Environment Variables

The bot relies on several environment variables. Below is a summary; see `.env.example` for exact names.

| Variable | Description |
| --- | --- |
| `TELEGRAM_BOT_TOKEN` | Token for your Telegram bot. |
| `USER_WALLET_PRIVATE_KEY` | Base64 encoded secret key for the trading wallet. |
| `RPC_URL` | Solana RPC endpoint (default mainnet). |
| `HELIUS_RPC_URL` | Helius RPC endpoint used by monitoring scripts. |
| `CIELO_API_KEY` | API key for Cielo wallet data. |
| `TWITTER_API_KEY` / `TWITTER_API_SECRET` | Credentials for Twitter scraping. |
| `TWITTER_ACCESS_TOKEN` / `TWITTER_ACCESS_SECRET` | Twitter access token pair. |
| `BIRDEYE_API_KEY` | API key for price data. |
| `GOOGLE_CREDENTIALS` | Path to Google service account JSON for Sheets integration. |

## Running the Scripts

- `python main.py` – starts the Telegram bot and trading monitor.
- `python trade_monitor.py` – standalone monitor that triggers copy trades.
- `python wallet_scraper.py` – scrape active wallets from Cielo and Twitter.
- `python wallet_discovery.py` – analyze seed wallets and score activity.
- `python export_monitored_wallets.py` – export top wallets to `monitored_wallets.json`.
- `python generate_wallet.py` – generate a new Solana wallet key pair.
- `python portfolio_tracker.py` – upload a trade summary to Google Sheets.
- `python daily_balance_logger.py` – log your SOL balance to Google Sheets.
- `python sync_to_sheets.py` – push `trade_log.csv` to Google Sheets.
- `python auto_sell.py` – example of trailing stop logic for new tokens.
- `python wallet_curator.py` – update wallet statistics in the local database.

## Disclaimer

Cryptocurrency trading is highly volatile and risky. This project is provided for educational purposes only and does **not** constitute financial advice. Use it at your own risk and never trade more than you can afford to lose.
