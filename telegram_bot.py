from telegram.ext import Updater, CommandHandler
import config

def start(update, context):
    update.message.reply_text("Copy Trading Bot is running!")

def status(update, context):
    update.message.reply_text("Currently monitoring:\n" + "\n".join(config.MONITORED_WALLETS))

def start_bot():
    updater = Updater(config.TELEGRAM_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("status", status))
    updater.start_polling()
    updater.idle()

