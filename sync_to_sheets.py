import gspread
from oauth2client.service_account import ServiceAccountCredentials
import csv
import os

CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS", "google_credentials.json")
SHEET_NAME = "Solana Copy Trades"

def sync_csv_to_google_sheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
    client = gspread.authorize(creds)

    try:
        sheet = client.open(SHEET_NAME).sheet1
    except gspread.SpreadsheetNotFound:
        sheet = client.create(SHEET_NAME).sheet1

    with open("trade_log.csv", newline="") as f:
        reader = list(csv.reader(f))
        sheet.clear()
        sheet.update("A1", reader)

    print("✅ trade_log.csv synced to Google Sheets.")
