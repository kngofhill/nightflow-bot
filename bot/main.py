import os
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import json
import asyncio
import traceback 

from telegram import Update, MenuButtonWebApp, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.ext import MessageHandler, filters

from dotenv import load_dotenv

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.db import (
    supabase_client,
    get_user_by_telegram_id,
    upsert_user,
    update_last_active,
    insert_notification,
)
from shared.time_utils import (
    get_user_now_from_timezone_name,
    combine_local_date_and_time,
    DEFAULT_TIMEZONE
)
from shared.schedule_utils import safe_json_parse

load_dotenv()
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Your existing command handlers (start, pause, resume) remain the same
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome message - menu button already opens mini-app."""
    user = update.effective_user
    logger.info(f"Start command from user {user.id}")
    
    # Ensure user exists in DB
    db_user = get_user_by_telegram_id(user.id)
    if not db_user:
        upsert_user(user.id, user.username, user.first_name, None)
    update_last_active(user.id, datetime.now().isoformat())

    await update.message.reply_text(
        f"👋 Welcome to Nightflow, {user.first_name}!\n\n"
        f"Use the menu button below ⬇️ to open the app.\n\n"
        f"Commands:\n"
        f"/pause - Pause notifications\n"
        f"/resume - Resume notifications"
    )

async def pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pause notifications."""
    user_id = update.effective_user.id
    supabase_client.table("users").update({"notification_enabled": False}).eq("telegram_id", user_id).execute()
    await update.message.reply_text("Notifications paused. Use /resume to enable again.")

async def resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Resume notifications."""
    user_id = update.effective_user.id
    supabase_client.table("users").update({"notification_enabled": True}).eq("telegram_id", user_id).execute()
    await update.message.reply_text("Notifications resumed.")

# Webhook handler - this will receive all updates from Telegram


async def check_scheduled_notifications(context: ContextTypes.DEFAULT_TYPE):
    """Background job for notifications."""
    # Your existing notification code - unchanged
    try:
        users_result = (
            supabase_client.table('users')
            .select('id, telegram_id, timezone, notification_enabled')
            .eq('notification_enabled', True)
            .execute()
        )
        if not users_result.data:
            return

        for user in users_result.data:
            user_id = user['id']
            timezone_name = user.get('timezone') or DEFAULT_TIMEZONE
            now_local = get_user_now_from_timezone_name(timezone_name)
            today_local = now_local.date()
            current_hour_min = now_local.strftime("%H:%M")

            # Check if today is a day off
            daily = supabase_client.table('daily_schedules').select('shift_type').eq('user_id', user_id).eq('date', str(today_local)).execute()
            if daily.data and daily.data[0].get('shift_type') == 'off':
                continue

            # Get active constant schedule
            const = supabase_client.table('constant_schedules').select('*').eq('user_id', user_id).eq('active', True).execute()
            if not const.data:
                continue
            schedule = const.data[0]

            coffee = safe_json_parse(schedule.get('coffee_windows'))
            meal = safe_json_parse(schedule.get('meal_windows'))
            bright = safe_json_parse(schedule.get('brightness_windows'))

            for w in coffee or []:
                if w.get('time') == current_hour_min:
                    await send_notification_once(context, user_id, 'coffee', current_hour_min, today_local, w.get('message', '☕ Time for coffee!'))

            for w in meal or []:
                if w.get('time') == current_hour_min:
                    await send_notification_once(context, user_id, 'meal', current_hour_min, today_local, w.get('message', '🍽️ Time to eat!'))

            for w in bright or []:
                if w.get('time') == current_hour_min:
                    await send_notification_once(context, user_id, 'brightness', current_hour_min, today_local, w.get('message', '💡 Light reminder!'))

            sleep_start = schedule.get('sleep_start')
            if sleep_start:
                sleep_dt = combine_local_date_and_time(today_local, sleep_start, timezone_name)
                if sleep_dt and sleep_dt <= now_local:
                    sleep_dt += timedelta(days=1)
                if sleep_dt and (sleep_dt - timedelta(minutes=30)).strftime("%H:%M") == current_hour_min:
                    await send_notification_once(context, user_id, 'sleep', current_hour_min, today_local, f"😴 30 minutes until sleep time ({sleep_start}). Wind down.")
    except Exception as e:
        logger.error(f"Error in notifications: {e}")

async def send_notification_once(context, user_id, ntype, hhmm, local_date, message):
    """Helper to avoid duplicate notifications."""
    try:
        already = supabase_client.table("notifications").select("id").eq("user_id", user_id).eq("type", ntype).eq("sent", True).contains("metadata", {"slot": hhmm, "local_date": str(local_date)}).execute()
        if already.data:
            return
        await send_notification(context, user_id, message, ntype, {"slot": hhmm, "local_date": str(local_date)})
    except Exception as e:
        logger.error(f"Error in send_notification_once: {e}")

async def send_notification(context, user_id, message, ntype, metadata=None):
    """Send a Telegram message and log it."""
    try:
        user = supabase_client.table("users").select("telegram_id").eq("id", user_id).execute()
        if not user.data:
            return
        telegram_id = user.data[0]["telegram_id"]
        await context.bot.send_message(chat_id=telegram_id, text=message)
        supabase_client.table("notifications").insert({
            "user_id": user_id,
            "type": ntype,
            "scheduled_time": datetime.now(ZoneInfo("UTC")).isoformat(),
            "sent": True,
            "sent_at": datetime.now(ZoneInfo("UTC")).isoformat(),
            "message": message,
            "metadata": metadata or {}
        }).execute()
        logger.info(f"Sent {ntype} to user {user_id}")
    except Exception as e:
        logger.error(f"Error sending notification: {e}")

async def post_init(application: Application):
    """Set menu button and ensure we're in polling mode."""
    try:
        # IMPORTANT: Delete any existing webhook FIRST
        await application.bot.delete_webhook(drop_pending_updates=True)
        logger.info("✅ Webhook deleted - forcing polling mode")
        
        # Then set menu button (this doesn't affect polling)
        await application.bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="🌙 Nightflow",
                web_app=WebAppInfo(url="https://nightflow-bot-production.up.railway.app")
            )
        )
        logger.info("✅ Menu button set successfully")
    except Exception as e:
        logger.error(f"Failed to initialize: {e}")

def main():
    """Start the bot with polling (NOT webhook)."""
    token = os.getenv('TELEGRAM_TOKEN')
    if not token:
        logger.error("No TELEGRAM_TOKEN")
        return

    # Create application
    application = Application.builder().token(token).post_init(post_init).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("pause", pause))
    application.add_handler(CommandHandler("resume", resume))

    # Schedule notifications
    if application.job_queue:
        application.job_queue.run_repeating(check_scheduled_notifications, interval=60, first=10)
        logger.info("✅ Notification scheduler started")

    logger.info("🚀 Nightflow bot starting with POLLING...")
    
    # Start polling (NOT webhook)
    application.run_polling(allowed_updates=Update.ALL_TYPES)
if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        traceback.print_exc()