# Solana Copy Trading Bot

This bot monitors high-performing Solana wallets and mirrors their trades using the Jupiter aggregator.
It connects to Telegram for basic control and logs trades in real-time.

## Setup Instructions

1. Install Python 3.10+.
2. Run `pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and fill in the required values:
   - `TELEGRAM_BOT_TOKEN`
   - `USER_WALLET_PRIVATE_KEY`
   - `RPC_URL` / `HELIUS_RPC_URL`
   - API keys for Cielo, Twitter, Birdeye, etc.
4. Start the bot: `python main.py`
5. Interact with it in Telegram using `/start` and `/status`.

Trade smart and only use funds you're willing to lose.

## Environment Variables

The bot reads credentials and API keys from environment variables. Refer to
`.env.example` for the full list of supported variables.
