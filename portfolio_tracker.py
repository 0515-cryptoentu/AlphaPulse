import pandas as pd
from collections import defaultdict
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
from datetime import datetime

# Set up Google Sheets connection
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]
creds_file = os.getenv("GOOGLE_CREDENTIALS", "google_credentials.json")
creds = ServiceAccountCredentials.from_json_keyfile_name(creds_file, scope)
client = gspread.authorize(creds)

try:
    # Load and clean trade log
    df = pd.read_csv("trade_log.csv")

    # ✅ Explicit format enforcement + space trimming
    df["timestamp"] = pd.to_datetime(
        df["timestamp"].astype(str).str.strip(),
        format="%Y-%m-%dT%H:%M:%SZ",
        errors="coerce",
    )

    # ✅ Drop any rows where datetime parsing failed
    df = df.dropna(subset=["timestamp"])
    if df.empty:
        print("[!] No valid rows found in trade_log.csv.")
        exit()

    # Group by token
    grouped = df.groupby("token_mint")

    summary_data = []
    for mint, group in grouped:
        token = group["token_symbol"].iloc[0]
        sol_spent = group["amount_sol"].sum()
        usd_spent = group["usd_value"].sum()
        num_trades = len(group)

        simulated_value = usd_spent * 1.1  # +10% hypothetical ROI
        roi = (simulated_value - usd_spent) / usd_spent * 100 if usd_spent else 0

        summary_data.append(
            [
                token,
                round(sol_spent, 4),
                round(usd_spent, 2),
                num_trades,
                round(simulated_value, 2),
                f"{roi:.2f}%",
            ]
        )

    # Upload to Google Sheets
    sh = client.open("Solana Copy Trades")
    sheet = sh.worksheet("Portfolio")
    sheet.clear()
    sheet.update(
        "A1",
        [
            [
                "Token",
                "SOL Spent",
                "USD Spent",
                "# of Trades",
                "Simulated Value (+10%)",
                "ROI (%)",
            ]
        ]
        + summary_data,
    )

    print("[✓] Portfolio summary uploaded to Google Sheets.")

except Exception as e:
    print(f"[✗] Failed to update portfolio: {e}")
