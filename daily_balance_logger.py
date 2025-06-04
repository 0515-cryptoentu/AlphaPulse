import datetime
from wallet_manager import get_balance
import gspread
import os
import logging
from utils import log


def log_daily_balance():
    try:
        creds_file = os.getenv("GOOGLE_CREDENTIALS", "google_credentials.json")
        gc = gspread.service_account(filename=creds_file)
        sh = gc.open("Solana Copy Trades")
        summary_sheet = sh.worksheet("Daily Summary")

        balance = get_balance()
        now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        summary_sheet.append_row([now, balance])
        log(f"[✓] Logged balance {balance:.4f} SOL at {now}", logging.INFO)
    except Exception as e:
        log(f"[✗] Failed to log daily balance: {e}", logging.ERROR)


if __name__ == "__main__":
    log_daily_balance()
