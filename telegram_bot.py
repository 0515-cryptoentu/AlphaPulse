"""
telegram_bot.py — AlphaPulse Telegram control interface.
 
Rewritten from v13 (Updater/dispatcher) to v20+ async API (Application).
 
Commands:
  /start    — greeting + command list
  /status   — bot mode, monitored wallets, open positions, heartbeat
  /pnl      — total P&L, win rate, trade count from trades.db
  /pause    — set PAUSED flag to stop copy_engine from executing new trades
  /resume   — clear PAUSED flag
  /wallets  — list monitored wallets with their current scores
  /balance  — current SOL wallet balance
  /help     — same as /start
"""
 
import asyncio
import logging
import sqlite3
from datetime import datetime
 
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.constants import ParseMode
 
import config
from utils import log
from wallet_manager import get_balance
 
# ── Global pause flag ────────────────────────────────────────────────────────
# Checked by copy_engine before executing any trade.
# Set/cleared by /pause and /resume commands.
PAUSED: bool = False
 
# ── Authorised user IDs ───────────────────────────────────────────────────────
# Leave empty to allow any Telegram user to control the bot.
# Set to your own Telegram user ID (integer) for security e.g. [123456789]
ALLOWED_USER_IDS: list[int] = []
 
 
def _is_allowed(update: Update) -> bool:
    if not ALLOWED_USER_IDS:
        return True
    return update.effective_user.id in ALLOWED_USER_IDS
 
 
def _fmt_wallet(addr: str) -> str:
    """Shorten a wallet address for display."""
    return f"`{addr[:6]}…{addr[-4:]}`"
 
 
def _get_pnl_stats() -> dict:
    """
    Pull trade stats from trades.db.
    Returns totals for buys, sells, win rate, and net P&L.
    """
    stats = {
        "total_trades": 0,
        "closed_trades": 0,
        "wins": 0,
        "total_buy_usd": 0.0,
        "total_sell_usd": 0.0,
        "pnl_usd": 0.0,
        "win_rate": 0.0,
    }
    try:
        conn = sqlite3.connect("trades.db")
        cur  = conn.cursor()
 
        cur.execute("SELECT COUNT(*) FROM trades WHERE token_symbol != 'AUTOSELL'")
        stats["total_trades"] = cur.fetchone()[0]
 
        cur.execute(
            """SELECT usd_value, sell_usd_value FROM trades
               WHERE token_symbol != 'AUTOSELL'
               AND sell_usd_value IS NOT NULL AND sell_usd_value != ''"""
        )
        closed = cur.fetchall()
        conn.close()
 
        stats["closed_trades"] = len(closed)
        for buy_usd, sell_usd in closed:
            buy  = float(buy_usd)
            sell = float(sell_usd)
            stats["total_buy_usd"]  += buy
            stats["total_sell_usd"] += sell
            if sell > buy:
                stats["wins"] += 1
 
        if stats["closed_trades"] > 0:
            stats["pnl_usd"]  = stats["total_sell_usd"] - stats["total_buy_usd"]
            stats["win_rate"] = stats["wins"] / stats["closed_trades"]
 
    except Exception as e:
        log(f"[TELEGRAM] DB error in _get_pnl_stats: {e}")
 
    return stats
 
 
def _get_heartbeat() -> str:
    try:
        with open("monitor_heartbeat.txt") as f:
            ts  = datetime.fromisoformat(f.read().strip())
            age = (datetime.utcnow() - ts).total_seconds()
            if age < 30:
                return "✅ Live"
            elif age < 120:
                return f"⚠️ {int(age)}s ago"
            else:
                return f"❌ Stale ({int(age//60)}m ago)"
    except Exception:
        return "❓ Unknown"
 
 
# ── Command handlers ─────────────────────────────────────────────────────────
 
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return
    mode = "🟡 PRACTICE" if config.PRACTICE_MODE else "🟢 LIVE"
    text = (
        f"*AlphaPulse* — Solana Copy Trading Bot\n"
        f"Mode: {mode}\n\n"
        f"*Commands:*\n"
        f"/status — bot health & open positions\n"
        f"/pnl — profit & loss summary\n"
        f"/balance — SOL wallet balance\n"
        f"/wallets — monitored wallets & scores\n"
        f"/pause — pause trade execution\n"
        f"/resume — resume trade execution\n"
        f"/help — show this message"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
 
 
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, context)
 
 
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return
 
    global PAUSED
    mode      = "🟡 PRACTICE" if config.PRACTICE_MODE else "🟢 LIVE"
    paused    = "⏸ PAUSED" if PAUSED else "▶️ Running"
    heartbeat = _get_heartbeat()
    stats     = _get_pnl_stats()
 
    try:
        import auto_sell
        open_pos = len(auto_sell.portfolio)
    except Exception:
        open_pos = 0
 
    wallets_fmt = "\n".join(
        f"  {_fmt_wallet(w)}" for w in config.MONITORED_WALLETS
    )
 
    text = (
        f"*AlphaPulse Status*\n\n"
        f"Mode: {mode}\n"
        f"State: {paused}\n"
        f"Monitor: {heartbeat}\n\n"
        f"*Portfolio*\n"
        f"Open positions: `{open_pos}`\n"
        f"Total trades: `{stats['total_trades']}`\n"
        f"Closed trades: `{stats['closed_trades']}`\n\n"
        f"*Wallets monitored:*\n{wallets_fmt}"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
 
 
async def cmd_pnl(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return
 
    stats = _get_pnl_stats()
 
    pnl_sign  = "+" if stats["pnl_usd"] >= 0 else ""
    pnl_emoji = "📈" if stats["pnl_usd"] >= 0 else "📉"
    win_pct   = f"{stats['win_rate']*100:.1f}%"
 
    # Win rate signal
    if stats["closed_trades"] < 10:
        wr_note = "_(need 10+ closed trades for reliable signal)_"
    elif stats["win_rate"] >= 0.55:
        wr_note = "✅ Above break-even threshold"
    else:
        wr_note = "⚠️ Below 55% — do not go live yet"
 
    text = (
        f"*AlphaPulse P&L*\n\n"
        f"{pnl_emoji} Net P&L: `{pnl_sign}${stats['pnl_usd']:.2f}`\n\n"
        f"Total invested: `${stats['total_buy_usd']:.2f}`\n"
        f"Total returned: `${stats['total_sell_usd']:.2f}`\n\n"
        f"Trades total: `{stats['total_trades']}`\n"
        f"Closed: `{stats['closed_trades']}`\n"
        f"Wins: `{stats['wins']}`\n"
        f"Win rate: `{win_pct}` {wr_note}"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
 
 
async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return
    try:
        bal = get_balance()
        text = f"*Wallet Balance*\n\n`{bal:.4f} SOL`"
    except Exception as e:
        text = f"⚠️ Could not fetch balance: `{e}`"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
 
 
async def cmd_wallets(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return
 
    try:
        from wallet_scorer import score_wallet
        lines = []
        for w in config.MONITORED_WALLETS:
            score = score_wallet(w)
            bar   = "█" * int(score * 10) + "░" * (10 - int(score * 10))
            emoji = "🟢" if score >= 0.6 else "🟡" if score >= 0.4 else "🔴"
            lines.append(
                f"{emoji} {_fmt_wallet(w)}\n"
                f"   Score: `{score:.2f}` `{bar}`"
            )
        body = "\n\n".join(lines)
    except Exception as e:
        body = f"Could not load scores: `{e}`"
 
    await update.message.reply_text(
        f"*Monitored Wallets*\n\n{body}",
        parse_mode=ParseMode.MARKDOWN
    )
 
 
async def cmd_pause(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return
    global PAUSED
    PAUSED = True
    log("[TELEGRAM] Bot PAUSED via Telegram command.")
    await update.message.reply_text(
        "⏸ *Bot paused.* No new trades will be executed.\n"
        "Send /resume to restart.",
        parse_mode=ParseMode.MARKDOWN
    )
 
 
async def cmd_resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return
    global PAUSED
    PAUSED = False
    log("[TELEGRAM] Bot RESUMED via Telegram command.")
    await update.message.reply_text(
        "▶️ *Bot resumed.* Copy trading is active.",
        parse_mode=ParseMode.MARKDOWN
    )
 
 
# ── Bot startup ───────────────────────────────────────────────────────────────
 
def start_bot() -> None:
    """
    Build and run the Telegram bot using the v20+ Application pattern.
    Blocking — runs until the process is killed.
    """
    token = config.TELEGRAM_BOT_TOKEN
    if not token:
        log("[TELEGRAM] No TELEGRAM_BOT_TOKEN set — skipping bot startup.")
        return
 
    app = Application.builder().token(token).build()
 
    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("help",    cmd_help))
    app.add_handler(CommandHandler("status",  cmd_status))
    app.add_handler(CommandHandler("pnl",     cmd_pnl))
    app.add_handler(CommandHandler("balance", cmd_balance))
    app.add_handler(CommandHandler("wallets", cmd_wallets))
    app.add_handler(CommandHandler("pause",   cmd_pause))
    app.add_handler(CommandHandler("resume",  cmd_resume))
 
    log("[TELEGRAM] Bot starting — polling for commands…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
