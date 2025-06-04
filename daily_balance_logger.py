import datetime
from wallet_manager import get_balance
import gspread

def log_daily_balance():
    try:
        gc = gspread.service_account(filename="google_credentials.json")
        sh = gc.open("Solana Copy Trades")
        summary_sheet = sh.worksheet("Daily Summary")

        balance = get_balance()
        now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        summary_sheet.append_row([now, balance])
        print(f"[✓] Logged balance {balance:.4f} SOL at {now}")
    except Exception as e:
        print(f"[✗] Failed to log daily balance: {e}")

if __name__ == "__main__":
    log_daily_balance()
