# Solana Copy Trading Bot

This bot monitors high-performing Solana wallets and mirrors their trades using the Jupiter aggregator. It connects to Telegram for basic control and logs trades in real time. Wallets are discovered from Twitter and Cielo and curated into a local database for continuous monitoring.

## Setup Instructions

1. Install Python 3.10+.
2. Run `pip install -e .`
3. Copy `.env.example` to `.env` and fill in the required values:
   - `TELEGRAM_BOT_TOKEN`
   - `USER_WALLET_PRIVATE_KEY`
   - `RPC_URL` / `HELIUS_RPC_URL`
   - API keys for Cielo, Twitter, Birdeye, etc.
4. Start the bot: `alphapulse bot`
5. Interact with it in Telegram using `/start` and `/status`.
6. Run `alphapulse scrape` regularly to refresh `monitored_wallets.json`.
7. Trade history is stored in both `trade_log.csv` and a SQLite database `trades.db`. The database is created automatically on first run.

## Training and Backtesting

Use the historical data in `trades.db` to experiment with different trading strategies. Run:

```bash
alphapulse train --db trades.db
```

The command supports options for position size, win rate, and other parameters to simulate how changes impact performance.

Trade smart and only use funds you're willing to lose.

## Environment Variables

The bot reads credentials and API keys from environment variables. Key values
include:

- `TELEGRAM_BOT_TOKEN` – token for the Telegram bot
- `USER_WALLET_PRIVATE_KEY` – base64 encoded private key for trading
- `RPC_URL` / `HELIUS_RPC_URL` – Solana RPC endpoints
- `CIELO_API_KEY` – API key for Cielo wallet scraping
- `TWITTER_API_KEY`, `TWITTER_API_SECRET`, etc. – Twitter credentials
- `BIRDEYE_API_KEY` – for token volume lookups

See `.env.example` for the complete list.

### Testing

Unit tests live in the `tests/` directory. Run them with:

```bash
pytest
```

These tests cover wallet loading and basic risk checks.

## License

This project is licensed under the [MIT License](LICENSE).

**Disclaimer:** This repository is for educational purposes only and does not
constitute financial advice. Cryptocurrency trading is highly volatile; use at
your own risk.
