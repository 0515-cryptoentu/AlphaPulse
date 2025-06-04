from telegram_bot import start_bot
from trade_monitor import supervisor_loop

if __name__ == "__main__":
    import asyncio
    import threading

    threading.Thread(target=asyncio.run, args=(supervisor_loop(),)).start()
    start_bot()
