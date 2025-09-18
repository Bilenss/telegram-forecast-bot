import asyncio
import logging
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from loguru import logger
import pandas as pd
from datetime import datetime
from ..config import TELEGRAM_TOKEN, PO_FETCH_ORDER, PO_USE_INTERCEPTOR, PO_USE_OCR, PO_USE_WS_FETCHER
from ..data_sources.fetchers import CompositeFetcher
from ..analysis.decision import run_analysis

# --- Logging Setup (as in your logs)
logger.add("bot.log", rotation="500 MB")
logger.info("Starting Telegram bot...")
# ---

# Global fetcher instance
fetcher = CompositeFetcher()

async def handle_forecast_request(update: Update, context):
    """
    Handles a request to get a forecast for a specific pair.
    """
    chat_id = update.effective_chat.id
    pair = "USDARS" # Example pair, replace with your logic to get it
    timeframe = "5m" # Example timeframe, replace with your logic

    await context.bot.send_message(chat_id=chat_id, text=f"Analyzing {pair} on {timeframe} timeframe...")

    try:
        # --- FIX IS HERE ---
        # The fetcher returns a tuple (df, source).
        # We need to unpack it correctly to get the DataFrame.
        df, source = await fetcher.fetch(symbol=pair, timeframe=timeframe, otc=True)
        # --- END OF FIX ---

        if df is None or df.empty:
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Analysis error\n\nReason: Could not fetch data. Try another pair or timeframe."
            )
            return

        # Now `df` is a DataFrame and the analysis can run
        forecast = await run_analysis(df)

        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Forecast for {pair} is: {forecast}"
        )

    except Exception as e:
        logger.error(f"Analysis error for {pair} {timeframe}: {e}")
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"❌ Analysis error\n\nReason: An unexpected error occurred. Please try again later."
        )

def main():
    """
    Main function to run the bot.
    """
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Register handlers
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_forecast_request))
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
