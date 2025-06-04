# Solana Copy Trading Bot

This bot monitors high-performing Solana wallets and mirrors their trades using the Jupiter aggregator.
It connects to Telegram for basic control and logs trades in real-time.

## Setup Instructions

1. Install Python 3.10+.
2. Run `pip install -r requirements.txt`
3. Fill in your `config.py` with:
   - Telegram bot token (via @BotFather)
   - Base64-encoded Solana private key
4. Start the bot: `python main.py`
5. Interact with it in Telegram using `/start` and `/status`.

Trade smart and only use funds you're willing to lose.