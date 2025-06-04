from telegram_bot import start_bot
from copy_trader import monitor_wallets

if __name__ == "__main__":
    import asyncio
    import threading

    threading.Thread(target=asyncio.run, args=(monitor_wallets(),)).start()
    start_bot()