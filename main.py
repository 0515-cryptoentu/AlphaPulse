from telegram_bot import start_bot
from trade_monitor import monitor_loop

if __name__ == "__main__":
    import asyncio
    import threading

    threading.Thread(target=asyncio.run, args=(monitor_loop(),)).start()
    start_bot()

