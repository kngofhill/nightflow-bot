import os
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import json
import asyncio
import traceback 

from telegram import Update, MenuButtonWebApp, WebAppInfo, LabeledPrice
import telegram.error as tg_error
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.ext import MessageHandler, filters, PreCheckoutQueryHandler

from dotenv import load_dotenv

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.db import (
    supabase_client,
    get_user_by_telegram_id,
    upsert_user,
    update_last_active,
    insert_notification,
    apply_pro_subscription_from_payment,
    revoke_pro_subscription,
)
from shared.subscription import (
    INVOICE_PAYLOAD_NIGHTFLOW_PRO,
    PRO_PRICE_STARS,
    SUBSCRIPTION_PERIOD_SECONDS,
    has_pro_entitlement,
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
        f"🎁 New accounts get a 14-day Pro trial (full features).\n"
        f"After that, stay on Free (today’s basics) or subscribe with {PRO_PRICE_STARS} Stars / 30 days via /subscribe.\n\n"
        f"Commands:\n"
        f"/subscribe — Nightflow Pro (Telegram Stars)\n"
        f"/pause — Pause notifications (Pro)\n"
        f"/resume — Resume notifications"
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


class RefundedPaymentFilter(filters.BaseFilter):
    def check_update(self, update: Update):
        m = update.message
        return bool(m and getattr(m, "refunded_payment", None))


async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send Telegram Stars invoice for Nightflow Pro (30-day recurring)."""
    # PTB 22.x send_invoice has no subscription_period kwarg; pass Bot API fields via api_kwargs.
    await context.bot.send_invoice(
        chat_id=update.effective_chat.id,
        title="Nightflow Pro",
        description=(
            "Full schedule, weekly report, suggestions, settings editing, "
            f"check-ins, and all reminders. {PRO_PRICE_STARS} Stars per 30 days (recurring)."
        ),
        payload=INVOICE_PAYLOAD_NIGHTFLOW_PRO,
        currency="XTR",
        prices=[LabeledPrice("Nightflow Pro", PRO_PRICE_STARS)],
        provider_token="",
        api_kwargs={"subscription_period": SUBSCRIPTION_PERIOD_SECONDS},
    )


async def precheckout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.pre_checkout_query
    if not q:
        return
    if q.invoice_payload != INVOICE_PAYLOAD_NIGHTFLOW_PRO:
        await q.answer(ok=False, error_message="Unknown product")
        return
    await q.answer(ok=True)


async def on_successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sp = update.message.successful_payment if update.message else None
    if not sp or sp.invoice_payload != INVOICE_PAYLOAD_NIGHTFLOW_PRO:
        return
    tid = update.effective_user.id
    exp = sp.subscription_expiration_date
    apply_pro_subscription_from_payment(tid, exp)
    await update.message.reply_text("Nightflow Pro is now active. Open the mini-app to use every feature.")


async def on_refunded_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rp = update.message.refunded_payment if update.message else None
    if not rp or rp.invoice_payload != INVOICE_PAYLOAD_NIGHTFLOW_PRO:
        return
    tid = update.effective_user.id
    revoke_pro_subscription(tid)
    await update.message.reply_text(
        "Your Stars payment was refunded. Pro access has been disabled immediately."
    )


async def check_scheduled_notifications(context: ContextTypes.DEFAULT_TYPE):
    """Background job for notifications."""
    # Your existing notification code - unchanged
    try:
        users_result = (
            supabase_client.table('users')
            .select('id, telegram_id, timezone, notification_enabled, trial_started_at, pro_expires_at')
            .eq('notification_enabled', True)
            .execute()
        )
        if not users_result.data:
            return

        for user in users_result.data:
            if not has_pro_entitlement(user):
                continue
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

async def log_errors(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Avoid noisy tracebacks for common Telegram conflicts (two pollers / webhook race)."""
    err = context.error
    if isinstance(err, tg_error.Conflict):
        logger.warning(
            "Telegram getUpdates conflict (only one bot poller allowed per token): %s",
            err,
        )
        return
    logger.error("Unhandled bot error", exc_info=err)


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
    application.add_handler(CommandHandler("subscribe", subscribe))
    application.add_handler(PreCheckoutQueryHandler(precheckout))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, on_successful_payment))
    application.add_handler(MessageHandler(RefundedPaymentFilter(), on_refunded_payment))
    application.add_error_handler(log_errors)

    # Schedule notifications
    if application.job_queue:
        application.job_queue.run_repeating(check_scheduled_notifications, interval=300, first=10)
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